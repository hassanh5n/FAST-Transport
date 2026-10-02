from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.db.models import Count, Exists, OuterRef, Q, Prefetch
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core.mail import send_mail
from django.conf import settings
from django.core.cache import cache
from datetime import timedelta
import random
import string as _string
import hashlib
import math
from collections import Counter
from decimal import Decimal
from rest_framework.response import Response
from rest_framework import viewsets,permissions
from rest_framework.decorators import action
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
import requests as req_lib
from rest_framework.decorators import api_view, permission_classes
from django.http import HttpResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
import io
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from ..permissions import (
    IsAdmin,
    IsStudent,
    IsAdminOrReadOnly,
    IsStudentCreateOnly
)
from ..models import (
    BusLocationPing,
    StudentProfile,
    Semester,
    Route,
    Stop,
    RouteStop,
    Bus,
    Driver,
    RouteAssignment,
    SemesterRegistration,
    SeatAllocation,
    Waitlist,
    FeeVerification,
    Complaint,
    RouteChangeRequest,
    MaintenanceSchedule,
    Notification,
    TransportRegistration,
    Challan,
    OTPVerification,
    Incident,
    CrimeRiskZone,
)

from ..serializers import (
    ChallanSerializer,
    UserSerializer,
    StudentProfileSerializer,
    SemesterSerializer,
    RouteSerializer,
    StopSerializer,
    RouteStopSerializer,
    BusSerializer,
    DriverSerializer,
    RouteAssignmentSerializer,
    SemesterRegistrationSerializer,
    SeatAllocationSerializer,
    WaitlistSerializer,
    FeeVerificationSerializer,
    ComplaintSerializer,
    RouteChangeRequestSerializer,
    MaintenanceScheduleSerializer,
    NotificationSerializer,
    StudentProfileCreateSerializer,
    TransportRegistrationSerializer,
    BusLocationPingSerializer,
    IncidentSerializer,
    CrimeRiskZoneSerializer,
)

from ..seatallocation import (
    allocate_seat_for_student,
    allocate_seat_on_assignment,
    reassign_seat_on_assignment,
    add_to_waitlist,
    issue_challan,
    pick_route_for_stop,
    release_seat,
    waitlist_summary,
    reindex_waitlist,
    promote_next_from_waitlist,
    SEAT_OFFER_HOURS,
)
from ..crime_risk import _setting_bbox
from ..rbac import get_effective_permissions, is_super_admin, staff_with_module

from .maps import _map_cache_key
from .routes import RouteViewSet

# ── Driver console ───────────────────────────────────────────────────────────
# Drivers are admin-created logins linked to a Driver row (Driver.user). Every
# endpoint below is scoped to the requesting driver's own active assignment.


class IsDriver(permissions.BasePermission):
    """A signed-in user whose account is linked to a Driver record."""

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and Driver.objects.filter(user=request.user).exists()
        )

AVERAGE_CITY_SPEED_MPS = 5.5   # ~20 km/h door to door in city traffic
ROAD_DETOUR_FACTOR = 1.3       # straight line -> road distance
STOP_DWELL_SECONDS = 60        # boarding time at each intermediate stop


def _driver_for(user):
    return Driver.objects.filter(user=user).first()


def _driver_assignment(driver):
    """The driver's active assignment, preferring the active semester."""
    qs = RouteAssignment.objects.filter(driver=driver, is_active=True).select_related(
        "route", "bus", "semester"
    )
    return qs.filter(semester__is_active=True).first() or qs.order_by("-created_at").first()


def _haversine_m(a, b):
    (lng1, lat1), (lng2, lat2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)
    return 2 * 6371000 * math.asin(math.sqrt(h))


def _route_legs(coordinates):
    """[(duration_s, distance_m)] per leg from the road router, or None."""
    # 4 decimals (~11 m) so consecutive pings from a parked bus share a cache hit.
    path = ";".join(f"{lng:.4f},{lat:.4f}" for lng, lat in coordinates)
    cache_key = _map_cache_key("eta", path)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        response = req_lib.get(
            f"{settings.MAP_ROUTING_URL}/route/v1/driving/{path}",
            params={"overview": "false"},
            timeout=6,
        )
        response.raise_for_status()
        legs = [(leg["duration"], leg["distance"]) for leg in response.json()["routes"][0]["legs"]]
    except (req_lib.RequestException, ValueError, KeyError, IndexError, TypeError):
        return None
    cache.set(cache_key, legs, timeout=60)
    return legs


def _stop_etas(origin, route_stops):
    """Cumulative ETA from origin (lng, lat) through route_stops, in order."""
    if not route_stops:
        return [], None
    coordinates = [origin] + [(float(rs.stop.longitude), float(rs.stop.latitude)) for rs in route_stops]
    # ponytail: OSRM durations are free-flow; scale them if drivers report ETAs as optimistic at rush hour.
    legs, source = _route_legs(coordinates), "road"
    if legs is None or len(legs) != len(route_stops):
        source = "estimate"
        legs = []
        for a, b in zip(coordinates, coordinates[1:]):
            distance = _haversine_m(a, b) * ROAD_DETOUR_FACTOR
            legs.append((distance / AVERAGE_CITY_SPEED_MPS, distance))

    etas, elapsed, travelled = [], 0.0, 0.0
    for index, (route_stop, (duration, distance)) in enumerate(zip(route_stops, legs)):
        elapsed += duration + (STOP_DWELL_SECONDS if index else 0)
        travelled += distance
        etas.append({
            "route_stop_id": route_stop.id,
            "eta_seconds": round(elapsed),
            "distance_m": round(travelled),
        })
    return etas, source


@api_view(["GET"])
@permission_classes([IsDriver])
def driver_overview(request):
    """Bus, route, ordered stops with per-stop rider counts, and the passenger list."""
    driver = _driver_for(request.user)
    assignment = _driver_assignment(driver)
    data = {
        "driver": {
            "id": driver.id,
            "name": driver.name,
            "phone": driver.phone,
            "license_no": driver.license_no,
            "is_available": driver.is_available,
        },
        "assignment": None,
        "route_map": None,
        "stops": [],
        "passengers": [],
        "last_ping": None,
    }
    if not assignment:
        return Response(data)

    route, bus = assignment.route, assignment.bus
    route_map = RouteViewSet()._map_route_data(route)

    passengers = []
    seats = SeatAllocation.objects.filter(route_assignment=assignment).select_related(
        "registration__student__user", "registration__stop"
    ).order_by("seat_number")
    for seat in seats:
        registration = seat.registration
        user = registration.student.user
        passengers.append({
            "seat_number": seat.seat_number,
            "roll_number": registration.student.roll_number,
            "name": f"{user.first_name} {user.last_name}".strip() or user.username,
            "stop_id": registration.stop_id,
            "stop_name": registration.stop.name,
            "status": registration.status,
        })
    riders_per_stop = Counter(p["stop_id"] for p in passengers)
    ping = bus.location_pings.order_by("-recorded_at").first()

    data.update({
        "assignment": {
            "id": assignment.id,
            "semester": str(assignment.semester),
            "bus": {
                "id": bus.id,
                "bus_number": bus.bus_number,
                "model": bus.model,
                "capacity": bus.capacity,
                "is_active": bus.is_active,
                "is_off_route": bus.is_off_route,
            },
            "route": {"id": route.id, "name": route.name, "description": route.description},
        },
        "route_map": route_map,
        "stops": [
            {**stop, "student_count": riders_per_stop.get(stop["id"], 0)}
            for stop in route_map["stops"]
        ],
        "passengers": passengers,
        "last_ping": {
            "latitude": float(ping.latitude),
            "longitude": float(ping.longitude),
            "recorded_at": ping.recorded_at,
            "distance_from_route_m": ping.distance_from_route_m,
        } if ping else None,
    })
    return Response(data)


@api_view(["POST"])
@permission_classes([IsDriver])
def driver_location(request):
    """
    A GPS fix from the driver's phone. Stored as a BusLocationPing, so the
    existing geofence signal still flags off-route buses, and answered with
    live ETAs for the stops the driver has not reached yet.
    """
    assignment = _driver_assignment(_driver_for(request.user))
    if not assignment:
        return Response({"detail": "You have no active bus assignment."}, status=400)

    try:
        latitude = float(request.data["latitude"])
        longitude = float(request.data["longitude"])
    except (KeyError, TypeError, ValueError):
        raise ValidationError("Latitude and longitude are required.")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValidationError("Coordinates are out of range.")

    remaining = request.data.get("remaining") or []
    if not isinstance(remaining, list) or len(remaining) > 60:
        raise ValidationError({"remaining": "Send up to 60 route stop IDs."})
    try:
        remaining = [int(item) for item in remaining]
    except (TypeError, ValueError):
        raise ValidationError({"remaining": "Route stop IDs must be integers."})

    # ponytail: one row per 15 s ping per bus; prune old pings with a cron once the table grows.
    ping = BusLocationPing.objects.create(
        bus=assignment.bus,
        latitude=Decimal(f"{latitude:.6f}"),
        longitude=Decimal(f"{longitude:.6f}"),
    )
    assignment.bus.refresh_from_db(fields=["is_off_route"])

    by_id = RouteStop.objects.filter(route=assignment.route, id__in=remaining).select_related("stop").in_bulk()
    etas, source = _stop_etas((longitude, latitude), [by_id[i] for i in remaining if i in by_id])

    return Response({
        "recorded_at": ping.recorded_at,
        "is_off_route": assignment.bus.is_off_route,
        "distance_from_route_m": ping.distance_from_route_m,
        "etas": etas,
        "eta_source": source,
    })
