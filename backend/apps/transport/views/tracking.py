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

    registration = TransportRegistration.objects.filter(
        student=profile,
        route__isnull=False
    ).select_related('route', 'stop').first()

    if not registration:
        return Response({"detail": "No active registration found"}, status=404)

    route = registration.route

    route_stops = (
        RouteStop.objects
        .filter(route=route)
        .select_related('stop')
        .order_by('stop_order')
    )

    stops = [
        {
            "name": rs.stop.name,
            "lat": float(rs.stop.latitude),
            "lng": float(rs.stop.longitude),
            "order": rs.stop_order,
            "morning_eta": str(rs.morning_eta) if rs.morning_eta else None,
        }
        for rs in route_stops
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
        "stops": stops,
        "bus": bus_info,
        "student_stop_name": registration.stop.name,
    })


# Map each route to its tracker token
BUS_TRACKER_TOKENS = {
    # Route assignment ID → iTecknologi token
    # You'll fill these in once you have tokens for each bus
    "default": "YgIw0Z",
}

ITECKNOLOGI_BASE = "https://iot.itecknologi.com/fleet"

LIVE_FLEET_FRESHNESS_SECONDS = 60


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
    source = tracker.get("status")
    latitude = tracker.get("latitude")
    longitude = tracker.get("longitude")
    position_timestamp = tracker.get("position_timestamp")

    if latitude is None and bus.recent_location_pings:
        ping = bus.recent_location_pings[0]
        ping_age = (now - ping.recorded_at).total_seconds()
        if ping_age <= LIVE_FLEET_FRESHNESS_SECONDS:
            latitude = float(ping.latitude)
            longitude = float(ping.longitude)
            position_timestamp = ping.recorded_at
            source = "ping"

    status = "ping" if source == "ping" else (_location_status(position_timestamp, now) if latitude is not None else source)
    return {
        "bus_id": bus.id,
        "bus_number": bus.bus_number,
        "model": bus.model,
        "is_active": bus.is_active,
        "status": status,
        "latitude": latitude,
        "longitude": longitude,
        "speed_kmh": tracker.get("speed_kmh"),
        "heading_degrees": tracker.get("heading_degrees"),
        "ignition": tracker.get("ignition"),
        "position_timestamp": position_timestamp,
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
    active_semester = Semester.objects.filter(is_active=True).first()
    assignments = RouteAssignment.objects.filter(
        is_active=True,
        semester=active_semester,
    ).select_related("route", "driver").annotate(
        allocated_seats=Count("seatallocation", distinct=True),
    ) if active_semester else RouteAssignment.objects.none()
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
        "buses": results,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def live_bus_location(request):
    """
    Returns real GPS coordinates for the student's assigned bus.
    Falls back to last known position if GPS is stale.
    """
    from ..models import SeatAllocation, SemesterRegistration, RouteAssignment
    
    # Get student's active registration
    try:
        profile = request.user.studentprofile
        registration = SemesterRegistration.objects.filter(
            student=profile,
            semester__is_active=True
        ).select_related("route", "stop").first()
        
        if not registration:
            return Response({"detail": "No active registration"}, status=404)
        
        # Find route assignment (which bus is on this route)
        assignment = RouteAssignment.objects.filter(
            route=registration.route,
            semester__is_active=True,
            is_active=True
        ).select_related("bus").first()
        
        if not assignment:
            return Response({"detail": "No active bus assignment"}, status=404)
        
        # Get the tracker token for this bus
        # You can store this on the Bus model (see Step 3)
        token = getattr(assignment.bus, 'tracker_token', None) or BUS_TRACKER_TOKENS["default"]
        
    except Exception as e:
        return Response({"detail": str(e)}, status=500)
    
    # Call iTecknologi API
    try:
        resp = req_lib.get(
        "https://iot.itecknologi.com/fleet/live_data_api_token.php",
        params={"token": token},
        timeout=5
        )
        resp.raise_for_status()
        gps_data = resp.json()

        if not gps_data.get("status"):
            return Response({"detail": "Tracker returned no data"}, status=503)

        d = gps_data["data"]

        return Response({
            "lat":         d["lat"],
            "lng":         d["lng"],
            "speed":       d["speed"],
            "heading":     d["angle"],           # "angle" → heading
            "ignition":    d["ign_value"] == 1,  # 0/1 int → bool
            "timestamp":   d["message"],
            "vehicle":     gps_data.get("vehicle"),   # "JE-5354"
            "model":       gps_data.get("model"),     # "MINI BUS"
            "bus_number":  assignment.bus.bus_number,
            "driver_name": assignment.driver.name,
            "route_name":  registration.route.name,
            "student_stop": registration.stop.name,
        })
    
    except req_lib.Timeout:
        return Response({"detail": "GPS tracker timeout"}, status=503)
    except Exception as e:
        return Response({"detail": f"Tracker error: {str(e)}"}, status=502)
