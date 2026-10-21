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

from .maps import (
    AVERAGE_CITY_SPEED_MPS, ROAD_DETOUR_FACTOR, STOP_DWELL_SECONDS,
    _haversine_m, _main_road_trip, _map_cache_key,
)
from ..corridor import ROUTE_LINE_VERSION, project

ON_LINE_M = 400  # a bus this close to its saved line is timed along it, without the router
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

def _driver_for(user):
    return Driver.objects.filter(user=user).first()


def _driver_assignment(driver):
    """The driver's active assignment, preferring the active semester."""
    qs = RouteAssignment.objects.filter(driver=driver, is_active=True).select_related(
        "route", "bus", "semester"
    )
    return qs.filter(semester__is_active=True).first() or qs.order_by("-created_at").first()


def _route_legs(coordinates):
    """[(duration_s, distance_m)] per leg along main roads, or None."""
    # 4 decimals (~11 m) so consecutive pings from a parked bus share a cache hit.
    path = ";".join(f"{lng:.4f},{lat:.4f}" for lng, lat in coordinates)
    cache_key = _map_cache_key("eta-main-road", path)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    trip = _main_road_trip([(round(lng, 4), round(lat, 4)) for lng, lat in coordinates], timeout=6)
    if trip is None:
        return None
    cache.set(cache_key, trip[1], timeout=60)
    return trip[1]


def _line_etas(origin, route_stops, geometry):
    """ETAs read off the route's saved main-road line, or None when it does not apply.

    The bus is placed on the line; each stop's ETA is the line's drive time from
    there to the stop's boarding point, plus boarding time at the stops between.
    """
    if not isinstance(geometry, dict) or geometry.get("v") != ROUTE_LINE_VERSION:
        return None
    saved = geometry.get("stops")
    line = geometry.get("coordinates")
    if not isinstance(saved, list) or not isinstance(line, list) or len(line) < 2:
        return None
    distance, along, *_ = project(line, origin)
    if distance > ON_LINE_M:
        return None
    by_pin = {(round(float(stop["pin"][0]), 5), round(float(stop["pin"][1]), 5)): stop for stop in saved}
    marks = sorted((stop["km"] * 1000, stop["s"]) for stop in saved)

    def seconds_at(metres):
        for (m1, s1), (m2, s2) in zip(marks, marks[1:]):
            if m1 <= metres <= m2:
                return s1 + (s2 - s1) * ((metres - m1) / (m2 - m1) if m2 > m1 else 0)
        return marks[0][1] if metres < marks[0][0] else marks[-1][1]

    now = seconds_at(along)
    etas = []
    for index, route_stop in enumerate(route_stops):
        stop = by_pin.get((round(float(route_stop.stop.longitude), 5), round(float(route_stop.stop.latitude), 5)))
        if stop is None:
            return None  # the line predates a stop change
        etas.append({
            "route_stop_id": route_stop.id,
            "eta_seconds": round(max(0, stop["s"] - now) + STOP_DWELL_SECONDS * index),
            "distance_m": round(max(0, stop["km"] * 1000 - along)),
        })
    return etas


def _stop_etas(origin, route_stops, geometry=None):
    """Cumulative ETA from origin (lng, lat) through route_stops, in order."""
    if not route_stops:
        return [], None
    etas = _line_etas(origin, route_stops, geometry)
    if etas is not None:
        return etas, "road"
    coordinates = [origin] + [(float(rs.stop.longitude), float(rs.stop.latitude)) for rs in route_stops]
    # ponytail: routed durations are free-flow; scale them if drivers report ETAs as optimistic at rush hour.
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
    etas, source = _stop_etas(
        (longitude, latitude), [by_id[i] for i in remaining if i in by_id], assignment.route.geometry,
    )

    return Response({
        "recorded_at": ping.recorded_at,
        "is_off_route": assignment.bus.is_off_route,
        "distance_from_route_m": ping.distance_from_route_m,
        "etas": etas,
        "eta_source": source,
    })
