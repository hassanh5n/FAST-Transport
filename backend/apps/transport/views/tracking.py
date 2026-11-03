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
from ..transport_status import CLOSED_STATUSES, current_semester_q

from .routes import RouteViewSet

# a view — auth question first, see below
class BusLocationPingCreateView(generics.CreateAPIView):
    queryset = BusLocationPing.objects.all()
    serializer_class = BusLocationPingSerializer
    permission_classes = [AllowAny]  # see note below


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_bus_tracking(request):
    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        return Response({"detail": "Profile not found"}, status=404)

    # Only an open registration in the current semester: a past semester's
    # route is not this student's bus any more.
    registration = TransportRegistration.objects.filter(
        current_semester_q(),
        student=profile,
        route__isnull=False
    ).exclude(status__in=CLOSED_STATUSES).select_related('route', 'stop').order_by("-created_at").first()

    if not registration:
        return Response({"detail": "No active registration found"}, status=404)

    route = registration.route

    route_map = RouteViewSet()._map_route_data(route, fetch=True)
    stops = [
        {
            "name": stop["name"],
            "lat": stop["latitude"],
            "lng": stop["longitude"],
            "order": stop["stop_order"],
            "morning_eta": stop["morning_eta"],
            "est_morning_eta": stop["est_morning_eta"],
            "est_evening_eta": stop["est_evening_eta"],
            "is_campus": stop["is_campus"],
            "boarding": stop["boarding"],  # where on the main road the bus picks up
            "walk_m": stop["walk_m"],
        }
        for stop in route_map["stops"]
    ]

    assignment = (
        RouteAssignment.objects
        .filter(route=route, is_active=True)
        .select_related('bus', 'driver')
        .first()
    )

    bus_info = {
        "bus_number": assignment.bus.bus_number,
        "driver_name": assignment.driver.name,
        "driver_phone": assignment.driver.phone,
    } if assignment else None

    return Response({
        "route_name": route.name,
        "geometry": route_map["geometry"],
        "stops": stops,
        "bus": bus_info,
        "student_stop_name": registration.stop.name,
    })


ITECKNOLOGI_BASE = "https://iot.itecknologi.com/fleet"

LIVE_FLEET_FRESHNESS_SECONDS = 60
# Older than live, a position is still shown as "last known" for this long, so a bus whose
# tracker or driver's phone goes quiet stays on the map with its age. Past it (yesterday's
# trip) the bus has no position.
LAST_KNOWN_MAX_SECONDS = 12 * 60 * 60


def _parse_tracker_timestamp(value):
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _location_status(position_timestamp, now):
    if position_timestamp is None:
        return "offline"
    age = (now - position_timestamp).total_seconds()
    return "live" if 0 <= age <= LIVE_FLEET_FRESHNESS_SECONDS else "stale"


def _best_position(tracker, ping, now):
    """
    The freshest position for a bus from its GPS tracker and the driver's newest phone
    ping, or None. Returns {latitude, longitude, timestamp, age_seconds, source}, where
    source is "tracker" or "driver".
    """
    candidates = []
    if tracker and tracker.get("latitude") is not None:
        # A tracker that sends no time is taken as reporting now.
        candidates.append((tracker.get("position_timestamp") or now, "tracker",
                           tracker["latitude"], tracker["longitude"]))
    if ping is not None:
        candidates.append((ping.recorded_at, "driver", float(ping.latitude), float(ping.longitude)))
    if not candidates:
        return None
    timestamp, source, latitude, longitude = max(candidates, key=lambda item: item[0])
    age = max(0, (now - timestamp).total_seconds())
    if age > LAST_KNOWN_MAX_SECONDS:
        return None
    return {"latitude": latitude, "longitude": longitude, "timestamp": timestamp,
            "age_seconds": round(age), "source": source}


def _fetch_tracker_location(bus):
    cache_key = f"admin-live-fleet:tracker:{bus.id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    token = bus.tracker_token
    if not token:
        result = {"status": "no_tracker", "error": "No tracker is configured."}
        cache.set(cache_key, result, 30)
        return result
    try:
        response = req_lib.get(
            f"{ITECKNOLOGI_BASE}/live_data_api_token.php",
            params={"token": token},
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        latitude = float(data["lat"])
        longitude = float(data["lng"])
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("Tracker returned coordinates outside valid ranges.")
        result = {
            "status": "provider",
            "latitude": latitude,
            "longitude": longitude,
            "speed_kmh": data.get("speed"),
            "heading_degrees": data.get("angle"),
            "ignition": data.get("ign_value") == 1,
            "position_timestamp": _parse_tracker_timestamp(data.get("message")),
        }
        cache.set(cache_key, result, 5)
        return result
    except (req_lib.RequestException, ValueError, KeyError, TypeError) as exc:
        result = {"status": "offline", "error": str(exc)}
        cache.set(cache_key, result, 2)
        return result


def _serialize_fleet_bus(bus, now):
    assignment = bus.active_assignments[0] if bus.active_assignments else None
    tracker = _fetch_tracker_location(bus)
    ping = bus.recent_location_pings[0] if bus.recent_location_pings else None
    best = _best_position(tracker, ping, now)

    if best is None:
        # No position in the last 12 hours: say why (no tracker fitted, or offline).
        latitude = longitude = position_timestamp = age_seconds = None
        source = status = tracker.get("status")
    else:
        latitude, longitude = best["latitude"], best["longitude"]
        position_timestamp, age_seconds = best["timestamp"], best["age_seconds"]
        live = age_seconds <= LIVE_FLEET_FRESHNESS_SECONDS
        if best["source"] == "driver":
            source = "ping"
            status = "ping" if live else "last_known"
        else:
            source = tracker.get("status")
            status = "live" if live else "stale"
    return {
        "bus_id": bus.id,
        "bus_number": bus.bus_number,
        "model": bus.model,
        "is_active": bus.is_active,
        "status": status,
        "latitude": latitude,
        "longitude": longitude,
        "speed_kmh": tracker.get("speed_kmh") if source != "ping" else None,
        "heading_degrees": tracker.get("heading_degrees") if source != "ping" else None,
        "ignition": tracker.get("ignition") if source != "ping" else None,
        "position_timestamp": position_timestamp,
        "position_age_seconds": age_seconds,
        "source": source,
        "route": {"id": assignment.route_id, "name": assignment.route.name} if assignment else None,
        "driver": {"id": assignment.driver_id, "name": assignment.driver.name} if assignment else None,
        "capacity": assignment.bus.capacity if assignment else None,
        "allocated_seats": getattr(assignment, "allocated_seats", 0) if assignment else 0,
        "available_seats": max(assignment.bus.capacity - assignment.allocated_seats, 0) if assignment else None,
        "is_off_route": bus.is_off_route,
        "distance_from_route_m": bus.recent_location_pings[0].distance_from_route_m if bus.recent_location_pings else None,
        "error": tracker.get("error"),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_live_fleet(request):
    """Return one normalized snapshot for every active bus in the fleet."""
    # Filtering on the semester inside the prefetch saves a round trip to the database
    # on every poll, and the dashboard polls every 8 s.
    assignments = RouteAssignment.objects.filter(
        is_active=True,
        semester__is_active=True,
    ).select_related("route", "driver").defer("route__geometry").annotate(
        allocated_seats=Count("seatallocation", distinct=True),
    )
    buses = list(
        Bus.objects.filter(is_active=True)
        .prefetch_related(
            Prefetch("routeassignment_set", queryset=assignments, to_attr="active_assignments"),
            Prefetch(
                "location_pings",
                queryset=BusLocationPing.objects.order_by("-recorded_at")[:1],
                to_attr="recent_location_pings",
            ),
        )
        .order_by("bus_number", "id")
    )
    now = timezone.now()
    results = []
    with ThreadPoolExecutor(max_workers=min(8, max(len(buses), 1))) as executor:
        futures = [executor.submit(_serialize_fleet_bus, bus, now) for bus in buses]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: (item["route"]["name"] if item["route"] else "", item["bus_number"], item["bus_id"]))
    return Response({
        "server_time": now,
        "freshness_threshold_seconds": LIVE_FLEET_FRESHNESS_SECONDS,
        "last_known_max_seconds": LAST_KNOWN_MAX_SECONDS,
        "buses": results,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def live_bus_location(request):
    """
    Where the student's bus is: the newer of its GPS tracker and the driver's phone.
    When both have gone quiet, the last known position is still returned (up to 12 h old)
    with its real time, so the page can say "last seen 5 min ago" instead of nothing.
    """
    from ..models import SemesterRegistration, RouteAssignment

    try:
        profile = request.user.studentprofile
    except Exception:
        return Response({"detail": "No student profile."}, status=404)
    registration = SemesterRegistration.objects.filter(
        student=profile, semester__is_active=True,
    ).select_related("route", "stop").first()
    if not registration:
        return Response({"detail": "No active registration"}, status=404)
    assignment = RouteAssignment.objects.filter(
        route=registration.route, semester__is_active=True, is_active=True,
    ).select_related("bus", "driver").first()
    if not assignment:
        return Response({"detail": "No active bus assignment"}, status=404)

    bus = assignment.bus
    now = timezone.now()
    # Same cached lookup as the admin fleet map (5 s), so students polling every 8 s
    # do not each call the tracker company.
    tracker = _fetch_tracker_location(bus) if bus.tracker_token else {}
    ping = bus.location_pings.order_by("-recorded_at").first()
    best = _best_position(tracker, ping, now)
    if best is None:
        return Response({"detail": "Your bus has not shared a location in the last 12 hours."}, status=503)

    from_tracker = best["source"] == "tracker"
    return Response({
        "lat": best["latitude"],
        "lng": best["longitude"],
        "speed": tracker.get("speed_kmh") if from_tracker else None,
        "heading": tracker.get("heading_degrees") if from_tracker else None,
        "ignition": tracker.get("ignition") if from_tracker else None,
        "timestamp": best["timestamp"],
        "age_seconds": best["age_seconds"],
        "is_live": best["age_seconds"] <= LIVE_FLEET_FRESHNESS_SECONDS,
        "source": best["source"],          # "tracker" or "driver"
        "bus_number": bus.bus_number,
        "driver_name": assignment.driver.name if assignment.driver else None,
        "route_name": registration.route.name,
        "student_stop": registration.stop.name if registration.stop else None,
    })
