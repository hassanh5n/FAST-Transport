from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.db.models import Count, Exists, OuterRef, Q
from django.db import transaction
from django.utils import timezone
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
from .permissions import (
    IsAdmin,
    IsStudent,
    IsAdminOrReadOnly,
    IsStudentCreateOnly
)
from .models import (
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

from .serializers import (
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

from .seatallocation import (
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
from .crime_risk import _setting_bbox
from .rbac import get_effective_permissions, is_super_admin, staff_with_module


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def crime_risk_zones(request):
    """Return generated, aggregated crime-risk cells for the map viewport.

    This endpoint intentionally queries only ExternalCrimeEvent-derived
    snapshots through CrimeRiskZone. Student Incident reports are unrelated.
    """
    raw_bbox = request.query_params.get("bbox", "")
    if raw_bbox:
        try:
            values = [float(value) for value in raw_bbox.split(",")]
            if len(values) != 4:
                raise ValueError
            min_lng, min_lat, max_lng, max_lat = values
            if min_lng >= max_lng or min_lat >= max_lat:
                raise ValueError
        except ValueError:
            return Response({"detail": "bbox must be minLng,minLat,maxLng,maxLat."}, status=400)
    else:
        min_lat, min_lng, max_lat, max_lng = _setting_bbox()

    zones = CrimeRiskZone.objects.filter(
        is_active=True,
        current_score__isnull=False,
        min_latitude__lte=max_lat,
        max_latitude__gte=min_lat,
        min_longitude__lte=max_lng,
        max_longitude__gte=min_lng,
    ).order_by("zone_id")
    features = []
    for zone in zones:
        props = CrimeRiskZoneSerializer(zone).data
        geometry = props.pop("geometry")
        features.append({"type": "Feature", "id": zone.zone_id, "properties": props, "geometry": geometry})

    return Response({
        "type": "FeatureCollection",
        "features": features,
        "available": bool(features),
        "source_configured": bool(getattr(settings, "CRIME_RISK_FEED_URL", "")),
        "message": None if features else (
            "Risk data is unavailable until an approved geocoded crime feed is configured."
            if not getattr(settings, "CRIME_RISK_FEED_URL", "")
            else "No scored crime-risk data is available for this viewport yet."
        ),
    })


def _valid_karachi_coordinate(latitude, longitude):
    """Keep admin map lookups constrained to the deployment's service area."""
    return 24.4 <= latitude <= 25.4 and 66.5 <= longitude <= 67.8


def _map_cache_key(prefix, value):
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"map:{prefix}:{digest}"


@api_view(["POST"])
@permission_classes([IsAdmin])
def resolve_map_location(request):
    """Rate-limited, cached admin-only forward and reverse geocoding proxy."""
    action_name = request.data.get("action")
    params = {"format": "jsonv2", "addressdetails": 1, "limit": 5}
    if action_name == "search":
        query = str(request.data.get("query", "")).strip()
        if len(query) < 3 or len(query) > 160:
            raise ValidationError({"query": "Enter between 3 and 160 characters."})
        # Keep results local to Karachi; an admin can still set an exact pin.
        params.update({"q": f"{query}, Karachi, Pakistan", "viewbox": "66.5,25.4,67.8,24.4", "bounded": 1})
        cache_value = f"search:{query.lower()}"
        endpoint = "/search"
    elif action_name == "reverse":
        try:
            latitude = float(request.data["latitude"])
            longitude = float(request.data["longitude"])
        except (KeyError, TypeError, ValueError):
            raise ValidationError("Latitude and longitude are required.")
        if not _valid_karachi_coordinate(latitude, longitude):
            raise ValidationError("Location must be within the Karachi service area.")
        params.update({"lat": latitude, "lon": longitude, "zoom": 18})
        cache_value = f"reverse:{latitude:.6f},{longitude:.6f}"
        endpoint = "/reverse"
    else:
        raise ValidationError({"action": "Use 'search' or 'reverse'."})

    cache_key = _map_cache_key("geocode", cache_value)
    cached = cache.get(cache_key)
    if cached is not None:
        return Response({"results": cached, "cached": True})

    # Respect shared geocoder capacity even when several admins use the page.
    if not cache.add("map:geocode:rate-lock", True, timeout=1):
        return Response({"detail": "Please wait a moment before another location lookup."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
    try:
        response = req_lib.get(
            f"{settings.MAP_GEOCODING_URL}{endpoint}",
            params=params,
            headers={"User-Agent": settings.MAP_GEOCODING_USER_AGENT},
            timeout=5,
        )
        response.raise_for_status()
        raw_results = response.json()
    except (req_lib.RequestException, ValueError):
        return Response({"detail": "Location service is unavailable. Place the pin manually."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    if action_name == "reverse":
        raw_results = [raw_results] if raw_results else []
    results = [
        {
            "latitude": float(item["lat"]),
            "longitude": float(item["lon"]),
            "label": item.get("display_name", "Selected location"),
            "provider_place_id": f"{item.get('osm_type', '')}:{item.get('osm_id', '')}",
        }
        for item in raw_results
        if item.get("lat") is not None and item.get("lon") is not None
    ]
    cache.set(cache_key, results, timeout=60 * 60 * 24 * 30)
    return Response({"results": results, "cached": False})


@api_view(["POST"])
@permission_classes([IsAdmin])
def preview_route_geometry(request):
    """Server-side road routing used by the admin route builder before save."""
    stop_ids = request.data.get("stop_ids")
    if not isinstance(stop_ids, list) or not 2 <= len(stop_ids) <= 60:
        raise ValidationError({"stop_ids": "Provide between 2 and 60 ordered stop IDs."})
    try:
        normalized_ids = [int(stop_id) for stop_id in stop_ids]
    except (TypeError, ValueError):
        raise ValidationError({"stop_ids": "Stop IDs must be integers."})
    if len(set(normalized_ids)) != len(normalized_ids):
        raise ValidationError({"stop_ids": "A stop can only appear once."})

    stops_by_id = Stop.objects.in_bulk(normalized_ids)
    if len(stops_by_id) != len(normalized_ids) or any(not stops_by_id[stop_id].is_active for stop_id in normalized_ids):
        raise ValidationError({"stop_ids": "One or more selected stops are unavailable."})
    coordinates = [(float(stops_by_id[stop_id].longitude), float(stops_by_id[stop_id].latitude)) for stop_id in normalized_ids]
    if any(lng == 0 and lat == 0 for lng, lat in coordinates):
        raise ValidationError({"stop_ids": "Each selected stop needs a valid map location."})

    geometry, source = _road_geometry(coordinates)
    return Response({"geometry": geometry, "source": source})


def _is_line_string(geometry):
    return (
        isinstance(geometry, dict)
        and geometry.get("type") == "LineString"
        and isinstance(geometry.get("coordinates"), list)
        and len(geometry["coordinates"]) >= 2
    )


def _is_straight_fallback(geometry, stop_coordinates):
    if not _is_line_string(geometry) or len(stop_coordinates) < 2:
        return False
    try:
        points = [(float(point[0]), float(point[1])) for point in geometry["coordinates"]]
        start = (float(stop_coordinates[0][0]), float(stop_coordinates[0][1]))
        end = (float(stop_coordinates[-1][0]), float(stop_coordinates[-1][1]))
    except (TypeError, ValueError, IndexError):
        return False

    tolerance = 1e-5
    if any(max(abs(point[index] - expected[index]) for index in (0, 1)) > tolerance
           for point, expected in ((points[0], start), (points[-1], end))):
        return False

    delta_lng = end[0] - start[0]
    delta_lat = end[1] - start[1]
    length_squared = delta_lng ** 2 + delta_lat ** 2
    if length_squared == 0:
        return False
    return all(
        abs(delta_lng * (point[1] - start[1]) - delta_lat * (point[0] - start[0]))
        <= tolerance * max(1, length_squared ** 0.5)
        for point in points
    )


def _road_geometry(coordinates):
    """Return a road line when available; never cache a straight-line fallback."""
    fallback = {"type": "LineString", "coordinates": [[lng, lat] for lng, lat in coordinates]}
    if len(coordinates) < 2:
        return fallback, "fallback"

    cache_key = _map_cache_key("route", ";".join(f"{lng:.6f},{lat:.6f}" for lng, lat in coordinates))
    cached = cache.get(cache_key)
    if isinstance(cached, dict) and cached.get("source") == "provider" and _is_line_string(cached.get("geometry")):
        return cached["geometry"], "cache"
    try:
        coordinate_path = ";".join(f"{lng},{lat}" for lng, lat in coordinates)
        response = req_lib.get(
            f"{settings.MAP_ROUTING_URL}/route/v1/driving/{coordinate_path}",
            params={"overview": "full", "geometries": "geojson"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        routed_geometry = payload.get("routes", [{}])[0].get("geometry")
        if _is_line_string(routed_geometry):
            cache.set(cache_key, {"geometry": routed_geometry, "source": "provider"}, timeout=60 * 60 * 24 * 7)
            return routed_geometry, "provider"
    except (req_lib.RequestException, ValueError, IndexError, AttributeError):
        pass
    return fallback, "fallback"


def _display_route_geometry(route, fallback_geometry):
    geometry = route.geometry if isinstance(route.geometry, dict) else None
    # A previous provider outage may have persisted a rounded or interpolated
    # stop-to-stop fallback. Treat any collinear fallback as stale.
    if not _is_line_string(geometry) or _is_straight_fallback(geometry, fallback_geometry):
        return _road_geometry(fallback_geometry)
    return geometry, "stored"
# a view — auth question first, see below
class BusLocationPingCreateView(generics.CreateAPIView):
    queryset = BusLocationPing.objects.all()
    serializer_class = BusLocationPingSerializer
    permission_classes = [AllowAny]  # see note below
class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_staff": user.is_staff,
            "role": "staff" if user.is_staff else (
                "driver" if Driver.objects.filter(user=user).exists() else "student"
            ),
            "is_super_admin": is_super_admin(user),
            "admin_role": (
                user.admin_profile.role.name
                if user.is_staff and hasattr(user, "admin_profile") and user.admin_profile.role
                else None
            ),
            "permissions": get_effective_permissions(user) if user.is_staff else {},
        })


class StudentProfileViewSet(viewsets.ModelViewSet):
    queryset = StudentProfile.objects.all()
    serializer_class = StudentProfileSerializer
    permission_classes = [IsStudentCreateOnly] #Students create, Admin full accces

    def get_queryset(self):
        user = self.request.user
        # Scope on staff status, not group membership: drivers and group-less
        # users must only ever see their own profile.
        if user.is_staff:
            return StudentProfile.objects.all()
        return StudentProfile.objects.filter(user=user)


class SemesterViewSet(viewsets.ModelViewSet):
    queryset = Semester.objects.all()
    serializer_class = SemesterSerializer
    permission_classes = [IsStudentCreateOnly] # Students create, Admin full acccess


class RouteViewSet(viewsets.ModelViewSet):
    queryset = Route.objects.all()
    serializer_class = RouteSerializer
    permission_classes = [IsAdminOrReadOnly] # Admin full access, Students read only

    def _map_route_data(self, route):
        route_stops = list(
            RouteStop.objects.filter(route=route, stop__is_active=True)
            .select_related("stop")
            .order_by("stop_order")
        )
        stops = [
            {
                "id": route_stop.stop_id,
                "route_stop_id": route_stop.id,
                "name": route_stop.stop.name,
                "address": route_stop.stop.address,
                "latitude": float(route_stop.stop.latitude),
                "longitude": float(route_stop.stop.longitude),
                "stop_order": route_stop.stop_order,
                "morning_eta": str(route_stop.morning_eta) if route_stop.morning_eta else None,
                "evening_eta": str(route_stop.evening_eta) if route_stop.evening_eta else None,
            }
            for route_stop in route_stops
            if not (float(route_stop.stop.latitude) == 0 and float(route_stop.stop.longitude) == 0)
        ]
        fallback_geometry = [[stop["longitude"], stop["latitude"]] for stop in stops]
        geometry, geometry_source = _display_route_geometry(route, fallback_geometry)
        return {
            "id": route.id,
            "name": route.name,
            "description": route.description,
            "status": route.status,
            "is_active": route.is_active,
            "geometry": geometry,
            "geometry_is_cached": geometry_source in {"stored", "cache"},
            "stops": stops,
        }

    @action(detail=False, methods=["get"], url_path="map")
    def map(self, request):
        """Compact network payload consumed by the student and admin map views."""
        routes = Route.objects.filter(is_active=True, status="published")
        return Response({"routes": [self._map_route_data(route) for route in routes]})

    @action(detail=True, methods=["get"], url_path="map-detail")
    def map_detail(self, request, pk=None):
        return Response(self._map_route_data(self.get_object()))

    @action(detail=True, methods=["patch"], url_path="builder", permission_classes=[IsAdmin])
    def builder(self, request, pk=None):
        """Atomically replace a route's ordered stops from the map route builder."""
        route = self.get_object()
        stops_payload = request.data.get("stops")
        if not isinstance(stops_payload, list) or not stops_payload:
            raise ValidationError({"stops": "Add at least one stop before saving the route."})

        stop_ids = []
        normalized = []
        for index, item in enumerate(stops_payload, start=1):
            try:
                stop_id = int(item["stop_id"])
            except (KeyError, TypeError, ValueError):
                raise ValidationError({"stops": f"Stop #{index} is invalid."})
            if stop_id in stop_ids:
                raise ValidationError({"stops": "A stop can only appear once on a route."})
            stop_ids.append(stop_id)
            normalized.append({
                "stop_id": stop_id,
                "stop_order": index,
                "morning_eta": item.get("morning_eta") or None,
                "evening_eta": item.get("evening_eta") or None,
            })

        if Stop.objects.filter(id__in=stop_ids, is_active=True).count() != len(stop_ids):
            raise ValidationError({"stops": "One or more selected stops are inactive or no longer exist."})

        geometry = request.data.get("geometry")
        if geometry is not None and (
            not isinstance(geometry, dict) or geometry.get("type") != "LineString" or not isinstance(geometry.get("coordinates"), list)
        ):
            raise ValidationError({"geometry": "Geometry must be a GeoJSON LineString."})

        with transaction.atomic():
            RouteStop.objects.filter(route=route).delete()
            RouteStop.objects.bulk_create([RouteStop(route=route, **item) for item in normalized])
            route.geometry = geometry
            route.geometry_updated_at = timezone.now() if geometry else None
            if request.data.get("status") in {"draft", "published", "archived"}:
                route.status = request.data["status"]
            route.save(update_fields=["geometry", "geometry_updated_at", "status", "updated_at"])

        return Response(self._map_route_data(route))

    @action(detail=True, methods=["get"])
    def details(self, request, pk=None):

        route = self.get_object()

        assignment = RouteAssignment.objects.filter(
            route=route,
            is_active=True
        ).select_related("bus", "driver").first()

        if not assignment:
            return Response({"message": "No assignment yet"})

        data = {
            "route": route.name,
            "bus": assignment.bus.bus_number,
            "driver": assignment.driver.name,
            "capacity": assignment.bus.capacity
        }

        return Response(data)

    @action(detail=True, methods=["get"], permission_classes=[IsAdmin])
    def overview(self, request, pk=None):
        """
        Full admin view of a single route: its stops, the bus + driver currently
        assigned to it, and every student registered on it this semester
        (Approved / Pending / payment_submitted / Rejected alike).
        """
        route = self.get_object()

        # ── Semester ────────────────────────────────────────────────────────
        # Prefer the active semester; fall back to the most recent one so the
        # page still renders something useful between semesters.
        semester = Semester.objects.filter(is_active=True).first()
        if semester is None:
            semester = Semester.objects.order_by("-year", "-start_date").first()

        # ── Bus + driver ────────────────────────────────────────────────────
        assignment_qs = RouteAssignment.objects.filter(
            route=route, is_active=True
        ).select_related("bus", "driver", "semester")

        assignment = None
        if semester is not None:
            assignment = assignment_qs.filter(semester=semester).first()
        if assignment is None:
            assignment = assignment_qs.order_by("-created_at").first()

        assignment_data = None
        if assignment:
            bus, driver = assignment.bus, assignment.driver
            assignment_data = {
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
                "driver": {
                    "id": driver.id,
                    "name": driver.name,
                    "phone": driver.phone,
                    "cnic": driver.cnic,
                    "license_no": driver.license_no,
                    "address": driver.address,
                    "is_available": driver.is_available,
                },
            }

        # ── Stops ───────────────────────────────────────────────────────────
        stops = [
            {
                "id": rs.id,
                "stop_order": rs.stop_order,
                "name": rs.stop.name,
                "address": rs.stop.address,
                "morning_eta": rs.morning_eta,
                "evening_eta": rs.evening_eta,
            }
            for rs in RouteStop.objects.filter(route=route)
            .select_related("stop")
            .order_by("stop_order")
        ]

        # ── Registered students ─────────────────────────────────────────────
        # TransportRegistration is the master record: it is the only one that
        # reliably carries Pending / Rejected rows.
        reg_qs = TransportRegistration.objects.filter(route=route)
        if semester is not None:
            reg_qs = reg_qs.filter(semester=semester)
        reg_qs = reg_qs.select_related("student__user", "stop").order_by(
            "student__roll_number"
        )

        # Seat numbers live on SeatAllocation -> SemesterRegistration, so build
        # a {student_id: seat_number} map in one query instead of per row.
        seat_map = {}
        if semester is not None:
            seat_map = dict(
                SeatAllocation.objects.filter(
                    registration__route=route,
                    registration__semester=semester,
                ).values_list("registration__student_id", "seat_number")
            )

        # Payment status is DERIVED, not read from TransportRegistration.is_paid.
        # That flag is only written by the manual seat-assign action, so students
        # who paid via challan/Stripe or were cleared by an admin fee verification
        # keep is_paid=False and would render as UNPAID. The truth lives on the
        # Challan and on FeeVerification, so read through to those instead.
        paid_registration_ids = set(
            Challan.objects.filter(
                registration__route=route, status="paid"
            ).values_list("registration_id", flat=True)
        )
        verified_fee_student_ids = set()
        if semester is not None:
            verified_fee_student_ids = set(
                FeeVerification.objects.filter(
                    semester=semester, is_verified=True
                ).values_list("student_id", flat=True)
            )

        students = []
        for reg in reg_qs:
            profile = reg.student
            user = profile.user
            full_name = f"{user.first_name} {user.last_name}".strip() or user.username
            is_paid = (
                reg.id in paid_registration_ids
                or profile.id in verified_fee_student_ids
                or reg.is_paid
            )
            students.append({
                "registration_id": reg.id,
                "student_id": profile.id,
                "roll_number": profile.roll_number,
                "name": full_name,
                "email": user.email,
                "department": profile.department,
                "batch": profile.batch,
                "phone": profile.phone,
                "stop": reg.stop.name if reg.stop else None,
                "status": reg.status,
                "is_paid": is_paid,
                "fee_amount": reg.fee_amount,
                "seat_number": seat_map.get(profile.id),
                "registered_at": reg.created_at,
            })

        # ── Stats ───────────────────────────────────────────────────────────
        capacity = assignment_data["bus"]["capacity"] if assignment_data else None
        approved = sum(1 for s in students if s["status"] == "Approved")
        pending = sum(
            1 for s in students if s["status"] in ("Pending", "payment_submitted")
        )
        rejected = sum(1 for s in students if s["status"] == "Rejected")

        return Response({
            "route": {
                "id": route.id,
                "name": route.name,
                "description": route.description,
                "is_active": route.is_active,
            },
            "semester": str(semester) if semester else None,
            "assignment": assignment_data,
            "stops": stops,
            "students": students,
            "stats": {
                "capacity": capacity,
                "registered": len(students),
                "approved": approved,
                "pending": pending,
                "rejected": rejected,
                "paid": sum(1 for s in students if s["is_paid"]),
                "seats_left": (capacity - approved) if capacity is not None else None,
            },
        })


class StopViewSet(viewsets.ModelViewSet):
    queryset = Stop.objects.all()
    serializer_class = StopSerializer
    permission_classes = [IsAdminOrReadOnly] # Admin full access, Students read only


class RouteStopViewSet(viewsets.ModelViewSet):
    queryset = RouteStop.objects.all()
    serializer_class = RouteStopSerializer
    permission_classes = [IsAdminOrReadOnly] # Admin full access, Students read only


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def eligible_route_stops(request):
    """Selectable route-stop pairs for the map-first registration flow."""
    semester_id = request.query_params.get("semester")
    semester = None
    if semester_id:
        semester = Semester.objects.filter(pk=semester_id).first()
    else:
        semester = Semester.objects.filter(is_active=True).first()

    if not semester:
        return Response({"detail": "No active semester found."}, status=status.HTTP_404_NOT_FOUND)
    if not semester.accepts_registrations:
        detail = (
            "The registration deadline for this semester has passed."
            if semester.deadline_passed
            else "Registration is not open for this semester."
        )
        return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

    active_assignment_routes = RouteAssignment.objects.filter(
        semester=semester, is_active=True, route__is_active=True
    ).values_list("route_id", flat=True)
    route_stops = list(
        RouteStop.objects.filter(
            route_id__in=active_assignment_routes,
            route__status="published",
            stop__is_active=True,
        )
        .select_related("route", "stop")
        .order_by("route__name", "stop_order")
    )
    stops_by_route = {}
    for route_stop in route_stops:
        if float(route_stop.stop.latitude) != 0 or float(route_stop.stop.longitude) != 0:
            stops_by_route.setdefault(route_stop.route_id, []).append(route_stop)
    route_geometries = {
        route_id: _display_route_geometry(
            stops[0].route,
            [[float(stop.stop.longitude), float(stop.stop.latitude)] for stop in stops],
        )[0]
        for route_id, stops in stops_by_route.items()
    }
    return Response({
        "semester": {"id": semester.id, "name": semester.name},
        "route_geometries": route_geometries,
        "route_stops": [
            {
                "id": route_stop.id,
                "route_id": route_stop.route_id,
                "route_name": route_stop.route.name,
                "route_description": route_stop.route.description,
                "stop_id": route_stop.stop_id,
                "stop_name": route_stop.stop.name,
                "address": route_stop.stop.address,
                "latitude": float(route_stop.stop.latitude),
                "longitude": float(route_stop.stop.longitude),
                "stop_order": route_stop.stop_order,
                "morning_eta": str(route_stop.morning_eta) if route_stop.morning_eta else None,
                "evening_eta": str(route_stop.evening_eta) if route_stop.evening_eta else None,
            }
            for route_stop in route_stops
            if not (float(route_stop.stop.latitude) == 0 and float(route_stop.stop.longitude) == 0)
        ],
    })


class BusViewSet(viewsets.ModelViewSet):
    queryset = Bus.objects.all()
    serializer_class = BusSerializer
    permission_classes = [IsAdmin] # Only Admin full access

    @action(detail=False, methods=["get"])
    def available(self, request):

        assigned = RouteAssignment.objects.filter(
            is_active=True
        ).values_list("bus_id", flat=True)

        buses = Bus.objects.exclude(id__in=assigned)

        serializer = self.get_serializer(buses, many=True)

        return Response(serializer.data)


class DriverViewSet(viewsets.ModelViewSet):
    queryset = Driver.objects.all()
    serializer_class = DriverSerializer
    permission_classes = [IsAdmin]  # keeps admin-only for all other actions

    def perform_destroy(self, instance):
        # Never leave an orphan account that can still sign in.
        user = instance.user
        instance.delete()
        if user:
            user.delete()

    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated])
    def public_detail(self, request, pk=None):
        try:
            driver = Driver.objects.get(pk=pk)
            return Response({
                "name": driver.name,
                "phone": driver.phone,
                "license_number": driver.license_no,
                "is_available": driver.is_available,
            })
        except Driver.DoesNotExist:
            return Response({"error": "Driver not found"}, status=404)

    @action(detail=False, methods=["get"])
    def available(self, request):
        assigned = RouteAssignment.objects.filter(
            is_active=True
        ).values_list("driver_id", flat=True)
        drivers = Driver.objects.exclude(id__in=assigned)
        serializer = self.get_serializer(drivers, many=True)
        return Response(serializer.data)


class RouteAssignmentViewSet(viewsets.ModelViewSet):
    queryset = RouteAssignment.objects.all().select_related(
        "route",
        "bus",
        "driver",
        "semester"
    )
    serializer_class = RouteAssignmentSerializer
    permission_classes = [IsAdmin] # Only Admin full access


class SemesterRegistrationViewSet(viewsets.ModelViewSet):
    queryset = SemesterRegistration.objects.all()
    serializer_class = SemesterRegistrationSerializer
    permission_classes = [IsStudentCreateOnly] # Students create, Admin full access

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return SemesterRegistration.objects.all()
        return SemesterRegistration.objects.filter(student__user=user)

class TransportRegistrationViewSet(viewsets.ModelViewSet):
    queryset = TransportRegistration.objects.all()
    serializer_class = TransportRegistrationSerializer
    permission_classes = [IsStudentCreateOnly]

    def get_queryset(self):
        user = self.request.user
        profile = StudentProfile.objects.filter(user=user).first()

        if not profile:
            return TransportRegistration.objects.none()

        return TransportRegistration.objects.filter(student=profile)
    
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def my_registration(self, request):
        user = request.user
        profile = StudentProfile.objects.filter(user=user).first()

        if not profile:
            return Response(
                {"detail": "Student profile not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        registration = TransportRegistration.objects.filter(student=profile).first()

        if not registration:
            return Response(
                {"detail": "No transport registration found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(registration)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def cancel(self, request, pk=None):
        """
        Withdraw a registration — from a held seat or from the queue.

        Releasing a seat fires the promotion receiver, so the next student in
        the queue is seated immediately rather than waiting for an admin.
        """
        profile = StudentProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response({"detail": "Student profile not found."}, status=404)

        registration = TransportRegistration.objects.filter(pk=pk, student=profile).first()
        if not registration:
            return Response({"detail": "Registration not found."}, status=404)

        if registration.status == "Cancelled":
            return Response({"detail": "This registration is already cancelled."}, status=400)

        challan = Challan.objects.filter(registration=registration).first()
        if challan and challan.status == "paid":
            return Response(
                {"detail": "This registration is already paid. Please contact the "
                           "transport office to cancel and arrange a refund."},
                status=400,
            )

        semester_registration = SemesterRegistration.objects.filter(
            student=profile, semester=registration.semester
        ).first()

        released = False
        if semester_registration:
            released = release_seat(semester_registration)

            entry = Waitlist.objects.filter(registration=semester_registration).first()
            if entry:
                route, semester = semester_registration.route, semester_registration.semester
                entry.delete()
                reindex_waitlist(route, semester)

            semester_registration.status = "Cancelled"
            semester_registration.save(update_fields=["status", "updated_at"])

        if challan and challan.status != "paid":
            challan.delete()

        registration.status = "Cancelled"
        registration.save(update_fields=["status"])

        Notification.objects.create(
            user=request.user,
            title="Registration cancelled",
            message=(
                "Your transport registration has been cancelled. "
                + ("Your seat has been released to the next student in the queue."
                   if released else "You have been removed from the waiting list.")
            ),
            type="info",
        )

        return Response({
            "detail": "Registration cancelled.",
            "seat_released": released,
        })

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated],
            url_path="waitlist-status")
    def waitlist_status(self, request):
        """Live queue position for the logged-in student, plus any offer clock."""
        profile = StudentProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response({"detail": "Student profile not found."}, status=404)

        semester = Semester.objects.filter(is_active=True).first()
        registration = SemesterRegistration.objects.filter(
            student=profile, semester=semester
        ).select_related("route").first() if semester else None

        if not registration:
            return Response({"waitlist": None, "seat": None})

        seat = SeatAllocation.objects.select_related(
            "route_assignment__bus"
        ).filter(registration=registration).first()

        transport_registration = TransportRegistration.objects.filter(
            student=profile, semester=semester
        ).order_by("-created_at").first()
        challan = (
            Challan.objects.filter(registration=transport_registration).first()
            if transport_registration else None
        )

        return Response({
            # The cancel endpoint acts on the TransportRegistration, so the
            # client needs its id, not the SemesterRegistration's.
            "registration_id": transport_registration.id if transport_registration else None,
            "route": registration.route.name if registration.route else None,
            "status": transport_registration.status if transport_registration else None,
            "waitlist": waitlist_summary(registration),
            "seat": {
                "seat_number": seat.seat_number,
                "bus": seat.route_assignment.bus.bus_number,
            } if seat else None,
            "payment_due_at": challan.payment_due_at if challan else None,
            "challan_status": challan.status if challan else None,
            "offer_hours": SEAT_OFFER_HOURS,
        })

    def perform_create(self, serializer):
        """
        Register a student: hold a seat first, and only then issue a challan.

        The previous flow created a challan unconditionally, so a student could
        pay in full and then be told the route was full — with no refund path
        and no way out. Now a full route means a queue place and no charge; the
        challan is issued when a seat actually exists.
        """
        profile = StudentProfile.objects.get(user=self.request.user)

        stop = serializer.validated_data["stop"]
        semester = serializer.validated_data["semester"]
        route_stop = serializer.validated_data.pop("selected_route_stop", None)

        if route_stop is None:
            # Students choose a stop; the route is derived. Where a stop is
            # served by several routes we pick one that can seat them rather
            # than rejecting the request.
            route_stop, _has_seat = pick_route_for_stop(stop, semester)
            if route_stop is None:
                raise ValidationError({"stop_id": "No active route currently serves this stop."})

        if not route_stop.route.is_active or route_stop.route.status != "published":
            raise ValidationError("No route found for this stop")
        if not semester.accepts_registrations:
            raise ValidationError({"semester_id": (
                "The registration deadline for this semester has passed."
                if semester.deadline_passed
                else "Registration is not open for this semester."
            )})

        registration = serializer.save(
            student=profile,
            route=route_stop.route,
            semester=semester,
            status="Pending",
        )

        semester_registration, _ = SemesterRegistration.objects.update_or_create(
            student=profile,
            semester=semester,
            defaults={
                "route": route_stop.route,
                "stop": stop,
                "status": "Pending",
            },
        )

        # Already paid in a previous flow? Honour it rather than re-charging.
        fee = FeeVerification.objects.filter(
            student=profile, semester=semester, is_verified=True
        ).first()

        result = allocate_seat_for_student(semester_registration)

        if result in ("Seat Allocated", "Seat already allocated"):
            registration.status = "Approved" if fee else "Seat Held"
            registration.save(update_fields=["status"])
            if not fee:
                issue_challan(registration)
        elif result == "Added to Waitlist":
            # No challan: the student is queued and has not been charged.
            registration.status = "Waitlisted"
            registration.save(update_fields=["status"])
        else:
            # No active bus yet — leave pending for an admin to resolve, and
            # still do not charge.
            registration.status = "Pending"
            registration.save(update_fields=["status"])

class SeatAllocationViewSet(viewsets.ModelViewSet):
    queryset = SeatAllocation.objects.all()
    serializer_class = SeatAllocationSerializer
    permission_classes = [IsAdmin] # Only Admin full access

    # Raw create/update wrote a SeatAllocation with whatever seat_number was
    # posted: no capacity check, no lock, no waitlist bookkeeping. That is how
    # rows numbered outside a bus's capacity appeared, which in turn let the
    # seat picker hand the same bus out again. Seats are now created and moved
    # only through the assign / reassign actions below, which lock the
    # assignment and respect capacity. Deletion stays, since releasing a seat
    # is safe and promotes the next student on the waitlist.
    _MANUAL_WRITE_DETAIL = (
        "Seats cannot be written directly. Use /seat-allocations/assign/ to "
        "seat a student and /seat-allocations/reassign/ to move one, so that "
        "bus capacity and the waitlist stay correct."
    )

    def create(self, request, *args, **kwargs):
        return Response({"detail": self._MANUAL_WRITE_DETAIL}, status=405)

    def update(self, request, *args, **kwargs):
        return Response({"detail": self._MANUAL_WRITE_DETAIL}, status=405)

    def partial_update(self, request, *args, **kwargs):
        return Response({"detail": self._MANUAL_WRITE_DETAIL}, status=405)

    def _assignment_options_by_route_semester(self):
        active_assignments = list(
            RouteAssignment.objects.filter(
                is_active=True,
                route__is_active=True,
                bus__is_active=True,
                semester__is_active=True,
            ).select_related("route", "semester", "bus", "driver")
        )

        seat_counts = {
            row["route_assignment"]: row["count"]
            for row in SeatAllocation.objects.filter(route_assignment__in=active_assignments)
            .values("route_assignment")
            .annotate(count=Count("id"))
        }

        assignment_by_route_semester = {}
        for assignment in active_assignments:
            occupied_seats = seat_counts.get(assignment.id, 0)
            available_seats = max(assignment.bus.capacity - occupied_seats, 0)
            key = (assignment.route_id, assignment.semester_id)
            assignment_by_route_semester.setdefault(key, []).append(
                {
                    "id": assignment.id,
                    "bus_number": assignment.bus.bus_number,
                    "driver_name": assignment.driver.name,
                    "total_seats": assignment.bus.capacity,
                    "occupied_seats": occupied_seats,
                    "available_seats": available_seats,
                }
            )

        return assignment_by_route_semester

    @action(detail=False, methods=["get"], url_path="eligible-registrations")
    def eligible_registrations(self, request):
        verified_fee_exists = FeeVerification.objects.filter(
            student=OuterRef("student"),
            semester=OuterRef("semester"),
            is_verified=True,
        )
        seat_exists = SeatAllocation.objects.filter(registration=OuterRef("pk"))

        registrations = (
            SemesterRegistration.objects.select_related(
                "student__user", "semester", "route", "stop"
            )
            .annotate(has_verified_fee=Exists(verified_fee_exists), has_seat=Exists(seat_exists))
            .filter(has_verified_fee=True, has_seat=False)
            .order_by("semester__name", "student__roll_number")
        )

        assignment_by_route_semester = self._assignment_options_by_route_semester()

        data = []
        for registration in registrations:
            assignment_options = assignment_by_route_semester.get(
                (registration.route_id, registration.semester_id),
                [],
            )
            data.append(
                {
                    "registration_id": registration.id,
                    "roll_number": registration.student.roll_number,
                    "student_name": f"{registration.student.user.first_name} {registration.student.user.last_name}".strip() or registration.student.user.username,
                    "semester": registration.semester.name,
                    "route": registration.route.name,
                    "stop": registration.stop.name,
                    "status": registration.status,
                    "assignment_options": assignment_options,
                }
            )

        return Response(data)

    @action(detail=False, methods=["get"], url_path="current-allocations")
    def current_allocations(self, request):
        verified_fee_exists = FeeVerification.objects.filter(
            student=OuterRef("registration__student"),
            semester=OuterRef("registration__semester"),
            is_verified=True,
        )

        allocations = (
            SeatAllocation.objects.select_related(
                "registration__student__user",
                "registration__semester",
                "registration__route",
                "registration__stop",
                "route_assignment__bus",
            )
            .annotate(has_verified_fee=Exists(verified_fee_exists))
            .filter(has_verified_fee=True)
            .order_by("registration__semester__name", "registration__student__roll_number")
        )

        assignment_by_route_semester = self._assignment_options_by_route_semester()

        data = []
        for allocation in allocations:
            registration = allocation.registration
            assignment_options = assignment_by_route_semester.get(
                (registration.route_id, registration.semester_id),
                [],
            )
            adjusted_options = []
            for option in assignment_options:
                adjusted_options.append(
                    {
                        **option,
                        "available_seats": (
                            option["available_seats"] + 1
                            if option["id"] == allocation.route_assignment_id
                            else option["available_seats"]
                        ),
                    }
                )

            data.append(
                {
                    "registration_id": registration.id,
                    "roll_number": registration.student.roll_number,
                    "student_name": f"{registration.student.user.first_name} {registration.student.user.last_name}".strip() or registration.student.user.username,
                    "semester": registration.semester.name,
                    "route": registration.route.name,
                    "stop": registration.stop.name,
                    "status": registration.status,
                    "current_bus": allocation.route_assignment.bus.bus_number,
                    "current_seat_number": allocation.seat_number,
                    "current_route_assignment_id": allocation.route_assignment_id,
                    "assignment_options": adjusted_options,
                }
            )

        return Response(data)

    @action(detail=False, methods=["post"], url_path="assign")
    def assign(self, request):
        registration_id = request.data.get("registration_id")
        route_assignment_id = request.data.get("route_assignment_id")

        if not registration_id or not route_assignment_id:
            return Response(
                {"detail": "registration_id and route_assignment_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            registration = SemesterRegistration.objects.select_related(
                "student__user", "semester", "route"
            ).get(pk=registration_id)
        except SemesterRegistration.DoesNotExist:
            return Response({"detail": "Registration not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            assignment = RouteAssignment.objects.select_related(
                "route", "semester", "bus", "driver"
            ).get(pk=route_assignment_id, is_active=True)
        except RouteAssignment.DoesNotExist:
            return Response(
                {"detail": "Active route assignment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if assignment.route_id != registration.route_id or assignment.semester_id != registration.semester_id:
            return Response(
                {"detail": "Selected assignment does not match student's route and semester."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        has_verified_fee = FeeVerification.objects.filter(
            student=registration.student,
            semester=registration.semester,
            is_verified=True,
        ).exists()
        if not has_verified_fee:
            return Response(
                {"detail": "Student fee is not verified for this semester."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        allocation_result = allocate_seat_on_assignment(registration, assignment)
        if allocation_result != "Seat Allocated":
            return Response({"detail": allocation_result}, status=status.HTTP_400_BAD_REQUEST)

        TransportRegistration.objects.filter(
            student=registration.student,
            semester=registration.semester,
        ).update(status="Approved", is_paid=True)

        seat = SeatAllocation.objects.filter(registration=registration).first()

        return Response(
            {
                "detail": "Seat assigned successfully.",
                "registration_id": registration.id,
                "route_assignment_id": assignment.id,
                "seat_number": seat.seat_number if seat else None,
            }
        )

    @action(detail=False, methods=["post"], url_path="reassign")
    def reassign(self, request):
        registration_id = request.data.get("registration_id")
        route_assignment_id = request.data.get("route_assignment_id")

        if not registration_id or not route_assignment_id:
            return Response(
                {"detail": "registration_id and route_assignment_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            registration = SemesterRegistration.objects.select_related(
                "student__user", "semester", "route"
            ).get(pk=registration_id)
        except SemesterRegistration.DoesNotExist:
            return Response({"detail": "Registration not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            assignment = RouteAssignment.objects.select_related(
                "route", "semester", "bus", "driver"
            ).get(pk=route_assignment_id, is_active=True)
        except RouteAssignment.DoesNotExist:
            return Response(
                {"detail": "Active route assignment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        has_verified_fee = FeeVerification.objects.filter(
            student=registration.student,
            semester=registration.semester,
            is_verified=True,
        ).exists()
        if not has_verified_fee:
            return Response(
                {"detail": "Student fee is not verified for this semester."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reassign_result = reassign_seat_on_assignment(registration, assignment)
        if reassign_result != "Seat Reassigned":
            return Response({"detail": reassign_result}, status=status.HTTP_400_BAD_REQUEST)

        seat = SeatAllocation.objects.filter(registration=registration).first()
        return Response(
            {
                "detail": "Seat reassigned successfully.",
                "registration_id": registration.id,
                "route_assignment_id": assignment.id,
                "seat_number": seat.seat_number if seat else None,
            }
        )


class WaitlistViewSet(viewsets.ModelViewSet):
    queryset = Waitlist.objects.all()
    serializer_class = WaitlistSerializer
    permission_classes = [IsAdminOrReadOnly] # Admin full access, Students read only

    def get_queryset(self):
        # Scope on staff status, not group membership: a student who was never
        # added to the "Student" group would otherwise read every other
        # student's queue entry.
        user = self.request.user
        base = Waitlist.objects.select_related(
            "registration__student__user",
            "registration__route",
            "registration__stop",
        )
        if user.is_staff:
            return base
        profile = StudentProfile.objects.filter(user=user).first()
        if not profile:
            return Waitlist.objects.none()
        return base.filter(registration__student=profile)

    @action(detail=False, methods=["get"], permission_classes=[IsAdmin])
    def overview(self, request):
        """
        The waiting list grouped by route, with each route's seat position.

        Queues are per route: position 1 on 6B is a different person from
        position 1 on 5B, so they are never shown as one combined list.
        """
        semester = Semester.objects.filter(is_active=True).first()
        if not semester:
            return Response({"semester": None, "routes": []})

        entries = (
            Waitlist.objects.filter(
                registration__semester=semester,
                status__in=["waiting", "offered"],
            )
            .select_related(
                "registration__student__user",
                "registration__route",
                "registration__stop",
            )
            .order_by("registration__route__name", "position", "added_at")
        )

        grouped = {}
        for entry in entries:
            registration = entry.registration
            route = registration.route
            if route is None:
                continue
            grouped.setdefault(route.id, {"route": route, "entries": []})
            grouped[route.id]["entries"].append(entry)

        # Include routes with free seats but nobody queued, so an admin can see
        # capacity sitting idle.
        for assignment in RouteAssignment.objects.filter(
            semester=semester, is_active=True
        ).select_related("route"):
            grouped.setdefault(assignment.route_id,
                               {"route": assignment.route, "entries": []})

        routes = []
        for data in grouped.values():
            route = data["route"]
            assignments = RouteAssignment.objects.filter(
                route=route, semester=semester, is_active=True
            ).select_related("bus", "driver")

            capacity = sum(a.bus.capacity for a in assignments)
            occupied = SeatAllocation.objects.filter(
                route_assignment__in=assignments
            ).count()
            free = max(capacity - occupied, 0)

            routes.append({
                "route_id": route.id,
                "route_name": route.name,
                "buses": [a.bus.bus_number for a in assignments],
                "drivers": [a.driver.name for a in assignments],
                "capacity": capacity,
                "occupied": occupied,
                "free_seats": free,
                "queue_length": len(data["entries"]),
                "queue": [
                    {
                        "id": entry.id,
                        "position": entry.position,
                        "status": entry.status,
                        "roll_number": entry.registration.student.roll_number,
                        "name": (
                            f"{entry.registration.student.user.first_name} "
                            f"{entry.registration.student.user.last_name}"
                        ).strip() or entry.registration.student.user.username,
                        "email": entry.registration.student.user.email,
                        "phone": entry.registration.student.phone,
                        "stop": entry.registration.stop.name if entry.registration.stop else None,
                        "added_at": entry.added_at,
                        "offer_expires_at": entry.offer_expires_at,
                    }
                    for entry in data["entries"]
                ],
            })

        routes.sort(key=lambda item: item["route_name"])
        return Response({"semester": str(semester), "routes": routes})

    @action(detail=False, methods=["post"], permission_classes=[IsAdmin],
            url_path="fill-empty-seats")
    def fill_empty_seats(self, request):
        """
        Seat as many queued students as there is room for.

        Promotion normally happens automatically when a seat is released, but
        capacity can also appear without any seat being freed — an admin raises
        a bus's capacity, or adds a second bus to a route. Nothing deletes a
        SeatAllocation in those cases, so no signal fires. This closes that gap.
        """
        semester = Semester.objects.filter(is_active=True).first()
        if not semester:
            return Response({"detail": "No active semester."}, status=400)

        route_id = request.data.get("route_id")
        routes = Route.objects.filter(is_active=True)
        if route_id:
            routes = routes.filter(pk=route_id)

        promoted = []
        for route in routes:
            # Keep promoting while seats remain and the queue is not empty.
            while True:
                registration = promote_next_from_waitlist(route, semester)
                if registration is None:
                    break
                promoted.append({
                    "route": route.name,
                    "roll_number": registration.student.roll_number,
                })

        return Response({
            "detail": (
                f"Seated {len(promoted)} student(s) from the waiting list."
                if promoted else
                "No students could be seated — no free seats, or the queues are empty."
            ),
            "promoted": promoted,
        })


class FeeVerificationViewSet(viewsets.ModelViewSet):
    queryset = FeeVerification.objects.all()
    serializer_class = FeeVerificationSerializer
    permission_classes = [IsAdminOrReadOnly] # Admin full access, Students read only

    def verify_fee(fee, admin_user):
        fee.is_verified = True
        fee.verified_by = admin_user
        fee.verified_at = timezone.now()
        fee.save()

        # Update transport registration
        TransportRegistration.objects.filter(
            student=fee.student,
            semester=fee.semester
        ).update(status="approved")


class ComplaintViewSet(viewsets.ModelViewSet):
    queryset = Complaint.objects.all()
    serializer_class = ComplaintSerializer
    permission_classes = [IsStudentCreateOnly] # Students create, Admin full access

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Complaint.objects.all()
        return Complaint.objects.filter(submitted_by=user)

    def perform_create(self, serializer):
        serializer.save(submitted_by=self.request.user)

    @action(detail=True, methods=["patch"], permission_classes=[IsAdmin])
    def resolve(self, request, pk=None):
        complaint = self.get_object()
        admin_response = (request.data.get("admin_response") or "").strip()

        if not admin_response:
            return Response(
                {"detail": "admin_response is required to resolve a complaint."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        complaint.status = "Resolved"
        complaint.admin_response = admin_response
        complaint.resolved_by = request.user
        complaint.resolved_at = timezone.now()
        complaint.save(update_fields=["status", "admin_response", "resolved_by", "resolved_at"])

        serializer = self.get_serializer(complaint)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RouteChangeRequestViewSet(viewsets.ModelViewSet):
    serializer_class = RouteChangeRequestSerializer
    permission_classes = [IsAuthenticated]
 
    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return RouteChangeRequest.objects.select_related(
                "registration__student__user",
                "registration__semester",
                "current_route",
                "requested_route",
                "requested_stop",
            ).order_by("status", "-requested_at")
        # Student sees only their own requests
        profile = StudentProfile.objects.filter(user=user).first()
        if not profile:
            return RouteChangeRequest.objects.none()
        return RouteChangeRequest.objects.filter(
            registration__student=profile
        ).select_related(
            "registration__semester",
            "current_route",
            "requested_route",
            "requested_stop",
        ).order_by("-requested_at")
 
    def perform_create(self, serializer):
        user = self.request.user
        profile = StudentProfile.objects.filter(user=user).first()
        if not profile:
            raise ValidationError("Student profile not found.")

        requested_stop = serializer.validated_data.get("requested_stop")

        registration = SemesterRegistration.objects.filter(
            student=profile,
            semester__is_active=True,
        ).first()
        if not registration:
            raise ValidationError("No active semester registration found.")

        # Block if they pick the exact same stop they already have
        if requested_stop and registration.stop == requested_stop:
            raise ValidationError("You are already assigned to this stop.")

        # Block duplicate pending requests
        if RouteChangeRequest.objects.filter(
            registration=registration,
            status="Pending",
        ).exists():
            raise ValidationError("You already have a pending route change request.")

        serializer.save(
            registration=registration,
            current_route=registration.route,
            status="Pending",
        )
 
    # ── Student cancels their own pending request ─────────────────────────────
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def cancel(self, request, pk=None):
        profile = StudentProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response({"detail": "Profile not found."}, status=404)
 
        try:
            rcr = RouteChangeRequest.objects.get(pk=pk, registration__student=profile)
        except RouteChangeRequest.DoesNotExist:
            return Response({"detail": "Request not found."}, status=404)
 
        if rcr.status != "Pending":
            return Response({"detail": "Only pending requests can be cancelled."}, status=400)
 
        rcr.status = "Cancelled"
        rcr.resolved_at = timezone.now()
        rcr.save()
        return Response({"detail": "Request cancelled."})
 
    # ── Admin approves ────────────────────────────────────────────────────────
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def approve(self, request, pk=None):
        if not request.user.is_staff:
            return Response({"detail": "Unauthorized."}, status=403)
 
        try:
            rcr = RouteChangeRequest.objects.select_related(
                "registration__student__user",
                "registration__semester",
                "registration__route",
                "registration__stop",
                "requested_route",
                "requested_stop",
            ).get(pk=pk)
        except RouteChangeRequest.DoesNotExist:
            return Response({"detail": "Request not found."}, status=404)
 
        if rcr.status != "Pending":
            return Response({"detail": "Only pending requests can be approved."}, status=400)
 
        registration = rcr.registration
        semester = registration.semester
        student = registration.student
        new_route = rcr.requested_route
        new_stop = rcr.requested_stop
 
        # Every bus on the requested route, emptiest first — a route may carry
        # more than one, and the second could have the only free seat.
        from .seatallocation import (
            _get_next_available_seat_number,
            seats_free_on_assignment,
        )

        new_assignments = list(
            RouteAssignment.objects.filter(
                route=new_route,
                semester=semester,
                is_active=True,
                bus__is_active=True,
            ).select_related("bus")
        )
        if not new_assignments:
            return Response({"detail": "No active bus assignment for the requested route."}, status=400)

        new_assignments.sort(key=lambda a: seats_free_on_assignment(a), reverse=True)
        if seats_free_on_assignment(new_assignments[0]) <= 0:
            return Response({"detail": "No seats available on the requested route."}, status=400)

        available_seat = None
        new_assignment = None

        # The seat is chosen inside the transaction, under a row lock on the
        # assignment. Choosing it beforehand let two approvals read the same
        # free seat and both write it.
        with transaction.atomic():
            locked_assignments = {
                item.id: item
                for item in RouteAssignment.objects.select_for_update()
                .select_related("bus")
                .filter(id__in=[a.id for a in new_assignments])
            }

            for candidate in new_assignments:
                locked = locked_assignments.get(candidate.id, candidate)
                seat_number = _get_next_available_seat_number(locked)
                if seat_number is not None:
                    new_assignment = locked
                    available_seat = seat_number
                    break

            if available_seat is None:
                return Response(
                    {"detail": "No seats available on the requested route."},
                    status=400,
                )

            # 1. Free old seat allocation. The post_delete receiver offers that
            #    seat to the old route's queue once this commits, which is what
            #    should happen — the student is leaving that route for good.
            SeatAllocation.objects.filter(registration=registration).delete()

            # 2. Update the SemesterRegistration to new route + stop
            registration.route = new_route
            registration.stop = new_stop
            registration.save(update_fields=["route", "stop", "updated_at"])

            # 3. Allocate seat on new route
            SeatAllocation.objects.create(
                registration=registration,
                route_assignment=new_assignment,
                seat_number=available_seat,
            )

            # 4. Update TransportRegistration too (keeps data consistent)
            TransportRegistration.objects.filter(
                student=student,
                semester=semester,
            ).update(route=new_route, stop=new_stop)
 
            # 5. Resolve the request
            rcr.status = "Approved"
            rcr.admin_remarks = request.data.get("admin_remarks", "")
            rcr.resolved_at = timezone.now()
            rcr.save()
 
        # Notify student
        Notification.objects.create(
            user=student.user,
            title="Route Change Approved",
            message=(
                f"Your route change request to {new_route.name} has been approved. "
                f"New stop: {new_stop.name}. Seat no: {available_seat}."
            ),
            type="info",
        )
 
        return Response({"detail": "Route change approved and seat allocated."})
 
    # ── Admin denies ──────────────────────────────────────────────────────────
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def deny(self, request, pk=None):
        if not request.user.is_staff:
            return Response({"detail": "Unauthorized."}, status=403)
 
        try:
            rcr = RouteChangeRequest.objects.get(pk=pk)
        except RouteChangeRequest.DoesNotExist:
            return Response({"detail": "Request not found."}, status=404)
 
        if rcr.status != "Pending":
            return Response({"detail": "Only pending requests can be denied."}, status=400)
 
        rcr.status = "Rejected"
        rcr.admin_remarks = request.data.get("admin_remarks", "")
        rcr.resolved_at = timezone.now()
        rcr.save()
 
        Notification.objects.create(
            user=rcr.registration.student.user,
            title="Route Change Denied",
            message=(
                f"Your route change request to {rcr.requested_route.name} was denied. "
                f"Reason: {rcr.admin_remarks or 'No reason provided.'}"
            ),
            type="warning",
        )
 
        return Response({"detail": "Route change request denied."})
 


class MaintenanceScheduleViewSet(viewsets.ModelViewSet):
    queryset = MaintenanceSchedule.objects.all()
    serializer_class = MaintenanceScheduleSerializer
    permission_classes = [IsAdmin] # Only Admin full access


class NotificationViewSet(viewsets.ModelViewSet):
    """
    A user's own notifications. Nobody — staff included — reads anyone else's
    through this endpoint.

    The previous get_queryset() returned Notification.objects.all() to any user
    who was not in a "Student" group, and the React bell filtered the result
    client-side. That still shipped every user's notifications over the wire,
    so any authenticated account could read them straight from the API.
    Scoping to request.user here is the actual fix; the client-side filter is
    now redundant.
    """
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    # Owner-scoped, so users may mark their own notifications read and delete
    # them. IsAdminOrReadOnly would have 403'd students on both.
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Notification.objects
            .filter(user=self.request.user)
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        # Notifications are raised by the system, never posted by a client
        # on someone else's behalf.
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        notification = self.get_object()  # already owner-scoped
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])
        return Response(self.get_serializer(notification).data)

    @action(detail=True, methods=["post"], url_path="mark-unread")
    def mark_unread(self, request, pk=None):
        notification = self.get_object()
        if notification.is_read:
            notification.is_read = False
            notification.save(update_fields=["is_read"])
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"detail": "All notifications marked as read.",
                         "updated": updated})

    @action(detail=False, methods=["delete", "post"], url_path="clear-all")
    def clear_all(self, request):
        deleted, _ = self.get_queryset().delete()
        return Response({"detail": "All notifications cleared.",
                         "deleted": deleted})


class StudentSignupView(generics.CreateAPIView):
    serializer_class = StudentProfileCreateSerializer
    permission_classes = [AllowAny]  # allow anyone to access
    def perform_create(self, serializer):
        # Save user but keep inactive until OTP verified
        profile = serializer.save()
        user = profile.user
        user.is_active = False
        user.save()

        # Generate OTP and store it
        otp_code = generate_otp()
        OTPVerification.objects.update_or_create(
            user=user,
            defaults={
                "otp": otp_code,
                "expires_at": timezone.now() + timedelta(minutes=10),
                "is_used": False,
            }
        )

        # Send OTP email — if this fails we still want the user created
        try:
            send_mail(
                subject="Your FAST Transport OTP Code",
                message=(
                    f"Hello {user.username},\n\n"
                    f"Your OTP verification code is: {otp_code}\n\n"
                    f"This code expires in 10 minutes.\n\n"
                    f"If you did not request this, please ignore this email."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send OTP email to {user.email}: {e}")
            # Don't raise — user is created, they can request a resend

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            {"detail": "Account created. Please check your email for the OTP verification code."},
            status=status.HTTP_201_CREATED
        )


def generate_otp():
    return str(random.randint(100000, 999999))
@api_view(["POST"])
@permission_classes([AllowAny])
def verify_otp(request):
    """
    POST /api/verify-otp/
    Body: { "email": "...", "otp": "123456" }
    """
    email = request.data.get("email", "").strip()
    otp_input = request.data.get("otp", "").strip()

    if not email or not otp_input:
        return Response({"detail": "Email and OTP are required."}, status=400)

    try:
        users = User.objects.filter(email=email, is_active=False)

        if not users.exists():
            return Response({"detail": "No pending account found with this email."}, status=404)

        if users.count() > 1:
            return Response({"detail": "Multiple accounts found. Contact support."}, status=400)

        user = users.first()
    except User.DoesNotExist:
        return Response({"detail": "No account found with this email."}, status=404)

    try:
        otp_record = OTPVerification.objects.get(user=user)
    except OTPVerification.DoesNotExist:
        return Response({"detail": "No OTP found for this account."}, status=404)

    if otp_record.is_used:
        return Response({"detail": "OTP has already been used."}, status=400)

    if timezone.now() > otp_record.expires_at:
        return Response({"detail": "OTP has expired. Please request a new one."}, status=400)

    if otp_record.otp != otp_input:
        return Response({"detail": "Invalid OTP. Please try again."}, status=400)

    # All good — activate user and mark OTP used
    otp_record.is_used = True
    otp_record.save()
    user.is_active = True
    user.save()

    return Response({"detail": "Email verified successfully. You can now log in."})


@api_view(["POST"])
@permission_classes([AllowAny])
def resend_otp(request):
    email = request.data.get("email", "").lower().strip()
    if not email:
        return Response({"detail": "Email is required."}, status=400)
 
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        # Don't reveal whether the email exists
        return Response({"detail": "If that email is registered, a new OTP has been sent."})
 
    # ── Rate limit: one OTP per 60 seconds ───────────────────────────────────
    existing = OTPVerification.objects.filter(user=user).first()
    if existing:
        seconds_since = (timezone.now() - existing.created_at).total_seconds()
        if seconds_since < 60:
            wait = int(60 - seconds_since)
            return Response(
                {"detail": f"Please wait {wait} seconds before requesting another OTP."},
                status=429,
            )
        existing.delete()
 
    otp_code = ''.join(random.choices(_string.digits, k=6))
    OTPVerification.objects.create(
        user=user,
        otp=otp_code,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
 
    send_mail(
        subject="Your FAST Transport OTP",
        message=f"Your OTP is: {otp_code}\nIt expires in 10 minutes.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
 
    return Response({"detail": "If that email is registered, a new OTP has been sent."})
    

@api_view(["POST"])
@permission_classes([AllowAny])
def forgot_password(request):
    """
    POST /api/forgot-password/
    Body: { "email": "k220001@nu.edu.pk" }
 
    Sends a password-reset OTP to the email.
    Returns 404 if the email is not registered.
    """
    email = request.data.get("email", "").lower().strip()
    if not email:
        return Response({"detail": "Email is required."}, status=400)
 
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response({"detail": "No account found with this email address."}, status=404)
 
    # Rate limit: same 60-second window as resend_otp
    existing = OTPVerification.objects.filter(user=user).first()
    if existing:
        seconds_since = (timezone.now() - existing.created_at).total_seconds()
        if seconds_since < 60:
            wait = int(60 - seconds_since)
            return Response(
                {"detail": f"Please wait {wait} seconds before requesting another reset OTP."},
                status=429,
            )
        existing.delete()
 
    otp_code = ''.join(random.choices(_string.digits, k=6))
    OTPVerification.objects.create(
        user=user,
        otp=otp_code,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
 
    send_mail(
        subject="Reset your FAST Transport password",
        message=(
            f"Your password reset OTP is: {otp_code}\n"
            "It expires in 10 minutes.\n\n"
            "If you did not request this, ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
 
    return Response({"detail": "A password reset OTP has been sent to your email."})
 
 
@api_view(["POST"])
@permission_classes([AllowAny])
def reset_password(request):
    """
    POST /api/reset-password/
    Body: { "email": "k220001@nu.edu.pk", "otp": "123456", "new_password": "..." }
    """
    email        = request.data.get("email", "").lower().strip()
    otp_code     = request.data.get("otp", "").strip()
    new_password = request.data.get("new_password", "").strip()
 
    if not all([email, otp_code, new_password]):
        return Response({"detail": "email, otp, and new_password are all required."}, status=400)
 
    if len(new_password) < 8:
        return Response({"detail": "Password must be at least 8 characters."}, status=400)
 
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response({"detail": "Invalid credentials."}, status=400)
 
    try:
        otp_obj = OTPVerification.objects.get(user=user, otp=otp_code)
    except OTPVerification.DoesNotExist:
        return Response({"detail": "Invalid or expired OTP."}, status=400)
 
    if not otp_obj.is_valid():
        otp_obj.delete()
        return Response({"detail": "OTP has expired. Please request a new one."}, status=400)
 
    user.set_password(new_password)
    user.save()
    otp_obj.delete()
 
    return Response({"detail": "Password reset successfully. You can now log in."})



class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.is_staff:
            data = {
                "role": "staff",
                "stats": {
                    "total_students": StudentProfile.objects.count(),
                    "active_buses": Bus.objects.filter(is_active=True).count(),
                    "active_routes": Route.objects.filter(is_active=True).count(),
                    "active_route_assignments": RouteAssignment.objects.filter(is_active=True).count(),
                    "pending_complaints": Complaint.objects.filter(status="Pending").count(),
                    "open_route_change_requests": RouteChangeRequest.objects.filter(status="Pending").count(),
                    "unverified_fees": FeeVerification.objects.filter(is_verified=False).count(),
                    "pending_maintenance": MaintenanceSchedule.objects.filter(status="Pending").count(),
                },
            }
        else:
            try:
                profile = StudentProfile.objects.get(user=user)
            except StudentProfile.DoesNotExist:
                return Response({"detail": "Student profile not found."}, status=status.HTTP_404_NOT_FOUND)

            active_semester = Semester.objects.filter(is_active=True).first()

            registrations = SemesterRegistration.objects.filter(student=profile).select_related("semester", "route", "stop")
            active_registration = registrations.filter(semester__is_active=True).first()

            transport_registration = None
            if active_semester:
                transport_registration = TransportRegistration.objects.filter(
                    student=profile,
                    semester=active_semester,
                ).select_related("semester", "route", "stop").first()

            registration_semester = None
            if active_registration:
                registration_semester = active_registration.semester
            elif transport_registration:
                registration_semester = transport_registration.semester

            fee_submitted_for_registration = False
            fee_verified_for_registration = False
            if registration_semester:
                fee_submitted_for_registration = FeeVerification.objects.filter(
                    student=profile,
                    semester=registration_semester,
                ).exists()
                fee_verified_for_registration = FeeVerification.objects.filter(
                    student=profile,
                    semester=registration_semester,
                    is_verified=True,
                ).exists()

            bus_number = None

            seat = None
            waitlist_position = None
            waitlist_detail = None
            if active_registration:
                seat_obj = SeatAllocation.objects.select_related("route_assignment__bus").filter(registration=active_registration).first()
                if seat_obj:
                    seat = {"seat_number": seat_obj.seat_number, "allocated_at": seat_obj.allocated_at}
                    bus_number = seat_obj.route_assignment.bus.bus_number
                else:
                    waitlist_obj = Waitlist.objects.filter(registration=active_registration).first()
                    if waitlist_obj:
                        waitlist_position = waitlist_obj.position
                        waitlist_detail = waitlist_summary(active_registration)

                    assignment = RouteAssignment.objects.select_related("bus").filter(
                        route=active_registration.route,
                        semester=active_registration.semester,
                        is_active=True,
                    ).first()
                    if assignment:
                        bus_number = assignment.bus.bus_number
            elif transport_registration:
                assignment = RouteAssignment.objects.select_related("bus").filter(
                    route=transport_registration.route,
                    semester=transport_registration.semester,
                    is_active=True,
                ).first()
                if assignment:
                    bus_number = assignment.bus.bus_number

            fees = FeeVerification.objects.filter(student=profile).select_related("semester")
            complaints = Complaint.objects.filter(submitted_by=user).order_by("-created_at")[:5]
            notifications = Notification.objects.filter(user=user).order_by("-created_at")[:5]

            data = {
                "role": "student",
                "profile": {
                    "first_name": profile.user.first_name,
                    "last_name": profile.user.last_name,
                    "roll_number": profile.roll_number,
                    "department": profile.department,
                    "batch": profile.batch,
                    "phone": profile.phone,
                    "address": profile.address,
                },
                "active_registration": {
                    "semester": (
                        active_registration.semester.name
                        if active_registration
                        else transport_registration.semester.name
                    ),
                    "route": (
                        active_registration.route.name
                        if active_registration
                        else transport_registration.route.name if transport_registration.route else None
                    ),
                    "stop": (
                        active_registration.stop.name
                        if active_registration
                        else transport_registration.stop.name
                    ),
                    "status": (
                        active_registration.status
                        if active_registration
                        else transport_registration.status
                    ),
                    "bus": bus_number,
                    "fee_submitted": fee_submitted_for_registration,
                    "fee_verified": fee_verified_for_registration,
                } if (active_registration or transport_registration) else None,
                "seat": seat,
                "waitlist_position": waitlist_position,
                "waitlist": waitlist_detail,
                "fee_summary": [
                    {
                        "semester": f.semester.name,
                        "amount": str(f.amount),
                        "is_verified": f.is_verified,
                        "challan_number": f.challan_number,
                    }
                    for f in fees
                ],
                "recent_complaints": [
                    {
                        "subject": c.subject,
                        "status": c.status,
                        "priority": c.priority,
                        "created_at": c.created_at,
                    }
                    for c in complaints
                ],
                "recent_notifications": [
                    {
                        "title": n.title,
                        "message": n.message,
                        "type": n.type,
                        "is_read": n.is_read,
                        "created_at": n.created_at,
                    }
                    for n in notifications
                ],
            }

        return Response(data)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Student registered successfully"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAdmin])
def students_list(request):
    students = StudentProfile.objects.select_related("user").all()

    data = []
    for s in students:
        data.append({
            "id": s.id,
            "username": s.user.username,
            "email": s.user.email,
            "roll_number": s.roll_number,
            "department": s.department,
            "batch": s.batch,
            "phone": s.phone
        })

    return Response(data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_challan(request, pk):
    try:
        profile = StudentProfile.objects.get(user=request.user)
    except StudentProfile.DoesNotExist:
        return Response({"detail": "Student profile not found"}, status=404)
 
    try:
        registration = TransportRegistration.objects.get(id=pk, student=profile)
    except TransportRegistration.DoesNotExist:
        return Response({"detail": "Registration not found"}, status=404)
 
    # Auto-create challan if it was missed during registration
    challan, created = Challan.objects.get_or_create(
        registration=registration,
        student=profile,
        defaults={
            "amount": registration.semester.fee if hasattr(registration.semester, "fee") else 0,
            "status": "unpaid"
        }
    )
 
    data = ChallanSerializer(challan).data
    # ADDED: expose the registration status so the frontend can show
    # "waiting for verification" vs "approved" without a separate API call
    data["registration_status"] = registration.status
    return Response(data)

def _mark_seat_confirmed(profile, semester):
    """
    Payment received: a held seat becomes an owned one.

    Clears the payment deadline and flips both registration records, so the
    student never sees "Seat Held" with a countdown after they have paid.
    """
    semester_registration = SemesterRegistration.objects.filter(
        student=profile, semester=semester
    ).first()
    if semester_registration and semester_registration.status != "Confirmed":
        semester_registration.status = "Confirmed"
        semester_registration.save(update_fields=["status", "updated_at"])

    TransportRegistration.objects.filter(
        student=profile, semester=semester
    ).exclude(status="Cancelled").update(status="Approved")

    Challan.objects.filter(
        registration__student=profile,
        registration__semester=semester,
        status="paid",
    ).update(payment_due_at=None)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pay_challan(request, pk):
    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        return Response({"detail": "Profile not found"}, status=404)

    try:
        challan = Challan.objects.get(registration__id=pk, student=profile)
    except Challan.DoesNotExist:
        return Response({"detail": "Challan not found"}, status=404)

    if challan.status == "paid":
        return Response({"detail": "Already paid"}, status=400)

    challan.status = "paid"
    challan.save()

    _mark_seat_confirmed(profile, challan.registration.semester)

    # Create or update FeeVerification record
    fee_verification, _ = FeeVerification.objects.get_or_create(
        student=profile,
        semester=challan.registration.semester,
        defaults={
            "amount": challan.amount,
            "challan_number": f"CHN-{challan.id:04d}",
        }
    )

    # Notify all admin/staff users
    admin_users = staff_with_module("fees")  # only admins who handle fees
    for admin in admin_users:
        Notification.objects.create(
            user=admin,
            title="Fee Payment Received",
            message=f"Student {profile.roll_number} has paid transport fees for {challan.registration.semester.name}. Please verify.",
            type="info"
        )

    return Response(ChallanSerializer(challan).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_fee(request, pk):
    if not request.user.is_staff:
        return Response({"detail": "Unauthorized"}, status=403)

    try:
        fee = FeeVerification.objects.get(pk=pk)
    except FeeVerification.DoesNotExist:
        return Response({"detail": "Fee verification not found"}, status=404)

    fee.is_verified = True
    fee.verified_by = request.user
    fee.verified_at = timezone.now()
    fee.save()

    # Approve the transport registration
    registrations_qs = TransportRegistration.objects.filter(
        student=fee.student,
        semester=fee.semester
    )
    registrations_qs.update(status="Approved")

    first_registration = registrations_qs.select_related("route", "stop").first()
    if first_registration and first_registration.route and first_registration.stop:
        semester_registration, _ = SemesterRegistration.objects.update_or_create(
            student=fee.student,
            semester=fee.semester,
            defaults={
                "route": first_registration.route,
                "stop": first_registration.stop,
                "status": "Approved",
            },
        )

        if not SeatAllocation.objects.filter(registration=semester_registration).exists():
            allocate_seat_for_student(semester_registration)

    # Notify the student
    Notification.objects.create(
        user=fee.student.user,
        title="Fee Verified",
        message=f"Your transport fee for {fee.semester.name} has been verified. Your registration is now approved.",
        type="info"
    )

    return Response({"detail": "Fee verified successfully"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_fee_verifications(request):
    if not request.user.is_staff:
        return Response({"detail": "Unauthorized"}, status=403)

    fees = FeeVerification.objects.select_related(
        "student__user", "semester", "verified_by"
    ).order_by("is_verified", "-created_at")

    def full_name(user):
        name = f"{user.first_name} {user.last_name}".strip()
        return name if name else user.username

    data = [
        {
            "id": f.id,
            "roll_number": f.student.roll_number,
            "student_name": full_name(f.student.user),
            "semester": f.semester.name,
            "amount": str(f.amount),
            "challan_number": f.challan_number,
            "is_verified": f.is_verified,
            "verified_by": full_name(f.verified_by) if f.verified_by else None,
            "verified_at": f.verified_at,
            "created_at": f.created_at,
        }
        for f in fees
    ]
    return Response(data)


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


# ── Stripe Payment + OTP Verification ────────────────────────────────────────



@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_payment_intent(request, pk):
    """
    POST /api/transport-registrations/<pk>/create-payment-intent/
    Creates a Stripe PaymentIntent in test/sandbox mode.
    Returns client_secret for the frontend to confirm payment.
    """
    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        return Response({"detail": "Student profile not found"}, status=404)

    registration = TransportRegistration.objects.filter(pk=pk, student=profile).first()
    if not registration:
        return Response({"detail": "Registration not found"}, status=404)

    challan = Challan.objects.filter(registration=registration).first()
    if not challan:
        return Response({"detail": "Challan not found"}, status=404)

    if challan.status == "paid":
        return Response({"detail": "Already paid"}, status=400)

    stripe_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    if stripe_key and stripe_key.startswith("sk_test_") and stripe_key != "sk_test_placeholder":
        import stripe as _stripe
        _stripe.api_key = stripe_key
        try:
            intent = _stripe.PaymentIntent.create(
                amount=int(challan.amount * 100),
                currency="pkr",
                metadata={"challan_id": challan.id, "user_id": request.user.id},
            )
            return Response({
                "client_secret": intent.client_secret,
                "payment_intent_id": intent.id,
                "amount": str(challan.amount),
                "simulated": False,
            })
        except Exception as e:
            return Response({"detail": f"Stripe error: {str(e)}"}, status=500)
    else:
        import uuid
        simulated_secret = f"pi_sim_{uuid.uuid4().hex[:16]}_secret_{uuid.uuid4().hex[:16]}"
        return Response({
            "client_secret": simulated_secret,
            "payment_intent_id": f"pi_sim_{uuid.uuid4().hex[:16]}",
            "amount": str(challan.amount),
            "simulated": True,
        })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_stripe_payment(request, pk):
    """
    POST /api/transport-registrations/<pk>/confirm-stripe-payment/
    Called after Stripe confirms payment on frontend.
    Generates OTP, emails it, and returns 200.
    """
    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        return Response({"detail": "Student profile not found"}, status=404)

    registration = TransportRegistration.objects.filter(pk=pk, student=profile).first()
    if not registration:
        return Response({"detail": "Registration not found"}, status=404)

    challan = Challan.objects.filter(registration=registration).first()
    if not challan:
        return Response({"detail": "Challan not found"}, status=404)

    if challan.status == "paid":
        return Response({"detail": "Already paid"}, status=400)

    otp_code = ''.join(random.choices(_string.digits, k=6))
    expires = timezone.now() + timedelta(minutes=10)

    OTPVerification.objects.update_or_create(
        user=request.user,
        defaults={"otp": otp_code, "expires_at": expires, "is_used": False},
    )

    try:
        send_mail(
            subject="FAST Transport — Payment OTP",
            message=(
                f"Hello {request.user.username},\n\n"
                f"Your payment verification OTP is: {otp_code}\n\n"
                f"This code expires in 10 minutes.\n\n"
                f"Amount: PKR {challan.amount}\n"
                f"If you did not initiate this payment, please ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[request.user.email],
            fail_silently=False,
        )
    except Exception:
        pass  # Don't block if email sending fails in dev

    return Response({
        "message": "OTP sent to your email",
        "email_hint": request.user.email[:3] + "***" + request.user.email[request.user.email.index("@"):],
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_payment_otp(request, pk):
    """
    POST /api/transport-registrations/<pk>/verify-payment-otp/
    Body: { "otp": "123456" }
    Verifies the OTP and marks challan as paid + creates FeeVerification.
    """
    otp_input = request.data.get("otp", "").strip()
    if not otp_input:
        return Response({"detail": "OTP is required."}, status=400)

    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        return Response({"detail": "Student profile not found"}, status=404)

    registration = TransportRegistration.objects.filter(pk=pk, student=profile).first()
    if not registration:
        return Response({"detail": "Registration not found"}, status=404)

    challan = Challan.objects.filter(registration=registration).first()
    if not challan:
        return Response({"detail": "Challan not found"}, status=404)

    if challan.status == "paid":
        return Response({"detail": "Already paid"}, status=400)

    try:
        otp_record = OTPVerification.objects.get(user=request.user)
    except OTPVerification.DoesNotExist:
        return Response({"detail": "No OTP found. Please request a new one."}, status=404)

    if otp_record.is_used:
        return Response({"detail": "OTP has already been used."}, status=400)

    if timezone.now() > otp_record.expires_at:
        return Response({"detail": "OTP has expired. Please request a new one."}, status=400)

    if otp_record.otp != otp_input:
        return Response({"detail": "Invalid OTP. Please try again."}, status=400)

    with transaction.atomic():
        otp_record.is_used = True
        otp_record.save()

        challan.status = "paid"
        challan.save()

        _mark_seat_confirmed(profile, registration.semester)

        FeeVerification.objects.get_or_create(
            student=profile,
            semester=registration.semester,
            defaults={
                "amount": challan.amount,
                "challan_number": f"CHN-{challan.id:04d}",
            },
        )

        admin_users = staff_with_module("fees")  # only admins who handle fees
        for admin in admin_users:
            Notification.objects.create(
                user=admin,
                title="Fee Payment Received (Stripe + OTP)",
                message=(
                    f"Student {profile.roll_number} has paid transport fees "
                    f"for {registration.semester.name} via Stripe. "
                    f"Amount: PKR {challan.amount}. Please verify."
                ),
                type="info",
            )

    return Response({
        "detail": "Payment verified successfully. Challan marked as paid.",
        "challan_status": "paid",
    })


# Map each route to its tracker token
BUS_TRACKER_TOKENS = {
    # Route assignment ID → iTecknologi token
    # You'll fill these in once you have tokens for each bus
    "default": "YgIw0Z",
}

ITECKNOLOGI_BASE = "https://iot.itecknologi.com/fleet"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def live_bus_location(request):
    """
    Returns real GPS coordinates for the student's assigned bus.
    Falls back to last known position if GPS is stale.
    """
    from .models import SeatAllocation, SemesterRegistration, RouteAssignment
    
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_transport_card(request):
    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        return Response({"detail": "Student profile not found"}, status=404)

    active_semester = Semester.objects.filter(is_active=True).first()
    if not active_semester:
        return Response({"detail": "No active semester"}, status=404)

    # Get registration info
    registration = SemesterRegistration.objects.filter(
        student=profile,
        semester=active_semester,
    ).select_related("route", "stop").first()

    transport_reg = TransportRegistration.objects.filter(
        student=profile,
        semester=active_semester,
    ).select_related("route", "stop").first()

    # Get seat & bus info
    seat_number = None
    bus_number = None
    route_name = None
    stop_name = None

    if registration:
        seat_obj = SeatAllocation.objects.select_related(
            "route_assignment__bus"
        ).filter(registration=registration).first()
        if seat_obj:
            seat_number = seat_obj.seat_number
            bus_number = seat_obj.route_assignment.bus.bus_number
        route_name = registration.route.name if registration.route else None
        stop_name = registration.stop.name if registration.stop else None
    elif transport_reg:
        assignment = RouteAssignment.objects.select_related("bus").filter(
            route=transport_reg.route,
            semester=active_semester,
            is_active=True,
        ).first()
        if assignment:
            bus_number = assignment.bus.bus_number
        route_name = transport_reg.route.name if transport_reg.route else None
        stop_name = transport_reg.stop.name if transport_reg.stop else None

    # Build PDF in memory
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm,
    )

    styles = getSampleStyleSheet()
    center_style = ParagraphStyle("center", parent=styles["Normal"], alignment=TA_CENTER)
    title_style = ParagraphStyle("title", parent=styles["Title"], alignment=TA_CENTER, fontSize=20)
    subtitle_style = ParagraphStyle("subtitle", parent=styles["Normal"], alignment=TA_CENTER, fontSize=12, textColor=colors.grey)

    story = []

    # Header — brand logo, then the issuing institution.
    # A missing asset must never 500 the download, so fall back to text only.
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "assets", "fleetcentric_logo.png")
    if os.path.exists(logo_path):
        logo_width = 6.5 * cm
        # Source artwork is 1024x358, so keep that ratio rather than hardcoding
        # a height that would distort the mark.
        logo = RLImage(logo_path, width=logo_width, height=logo_width * 358 / 1024)
        logo.hAlign = "CENTER"
        story.append(logo)
        story.append(Spacer(1, 0.45 * cm))

    story.append(Paragraph("FAST NUCES", title_style))
    story.append(Paragraph("Transport Management System", subtitle_style))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("STUDENT TRANSPORT CARD", ParagraphStyle(
        "cardtitle", parent=styles["Heading1"], alignment=TA_CENTER,
        fontSize=16, textColor=colors.HexColor("#00254D")
    )))
    story.append(Spacer(1, 0.8*cm))

    # Info table
    data = [
        ["FIELD", "DETAILS"],
        ["Student Name", profile.user.get_full_name() or profile.user.username],
        ["Roll Number", profile.roll_number],
        ["Department", profile.department],
        ["Batch", profile.batch],
        ["Semester", active_semester.name],
        ["Route", route_name or "N/A"],
        ["Stop", stop_name or "N/A"],
        ["Bus Number", bus_number or "N/A"],
        ["Seat Number", str(seat_number) if seat_number else "Not Allocated"],
        ["Status", "APPROVED" if (registration or transport_reg) else "N/A"],
    ]

    table = Table(data, colWidths=[6*cm, 10*cm])
    table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00254D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 12),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),

        # Data rows
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 11),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f5f8fc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef3fa")]),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 10),

        # Border
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("BOX", (0, 0), (-1, -1), 1.5, colors.HexColor("#00254D")),
    ]))

    story.append(table)
    story.append(Spacer(1, 1*cm))

    # Footer note
    story.append(Paragraph(
        "This card is valid for the current semester only. Please carry it while using university transport.",
        ParagraphStyle("footer", parent=styles["Normal"], alignment=TA_CENTER,
                       fontSize=9, textColor=colors.grey)
    ))

    doc.build(story)
    buffer.seek(0)

    filename = f"transport_card_{profile.roll_number}_{active_semester.name.replace(' ', '_')}.pdf"
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Incidents
# ─────────────────────────────────────────────────────────────────────────────

class IncidentViewSet(viewsets.ModelViewSet):
    """
    Students: create incidents, list their own.
    Admins:   full CRUD, approve / reject.
    """
    serializer_class   = IncidentSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Students can submit and view only their own reports. Review and
        # administration remain staff-only, including edits and deletions.
        if self.request.user.is_staff or self.action in {"list", "create"}:
            return [IsAuthenticated()]
        return [IsAdmin()]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Incident.objects.select_related(
                "reported_by", "reviewed_by"
            ).order_by("status", "-created_at")
        # Students see only their own incidents
        return Incident.objects.filter(
            reported_by=user
        ).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(reported_by=self.request.user)

    # ── Admin: approve ──────────────────────────────────────────────────────
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def approve(self, request, pk=None):
        if not request.user.is_staff:
            return Response({"detail": "Unauthorized."}, status=403)

        try:
            incident = Incident.objects.get(pk=pk)
        except Incident.DoesNotExist:
            return Response({"detail": "Incident not found."}, status=404)

        if incident.status != "Pending":
            return Response({"detail": "Only pending incidents can be approved."}, status=400)

        incident.status      = "Approved"
        incident.reviewed_by = request.user
        incident.reviewed_at = timezone.now()
        incident.admin_notes = request.data.get("admin_notes", "")
        incident.save()

        # Notify the reporter
        Notification.objects.create(
            user=incident.reported_by,
            title="Incident Report Approved",
            message=(
                f"Your {incident.get_incident_type_display()} incident report has been "
                f"approved and is now visible on the live map."
            ),
            type="info",
        )

        return Response({"detail": "Incident approved and visible on the live map."})

    # ── Admin: reject ───────────────────────────────────────────────────────
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def reject(self, request, pk=None):
        if not request.user.is_staff:
            return Response({"detail": "Unauthorized."}, status=403)

        try:
            incident = Incident.objects.get(pk=pk)
        except Incident.DoesNotExist:
            return Response({"detail": "Incident not found."}, status=404)

        if incident.status != "Pending":
            return Response({"detail": "Only pending incidents can be rejected."}, status=400)

        admin_notes = request.data.get("admin_notes", "").strip()

        incident.status      = "Rejected"
        incident.reviewed_by = request.user
        incident.reviewed_at = timezone.now()
        incident.admin_notes = admin_notes
        incident.save()

        # Notify the reporter
        Notification.objects.create(
            user=incident.reported_by,
            title="Incident Report Rejected",
            message=(
                f"Your {incident.get_incident_type_display()} incident report was rejected. "
                f"Reason: {admin_notes or 'No reason provided.'}"
            ),
            type="warning",
        )

        return Response({"detail": "Incident rejected."})


@api_view(["GET"])
@permission_classes([AllowAny])
def approved_incidents(request):
    """
    Public endpoint — returns all approved, non-expired incidents.
    Used by the LiveMap to render colored overlay circles.
    """
    now = timezone.now()
    qs  = Incident.objects.filter(status="Approved").filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    ).select_related("reported_by")

    data = []
    for inc in qs:
        data.append({
            "id":           inc.id,
            "incident_type": inc.incident_type,
            "incident_type_display": inc.get_incident_type_display(),
            "severity":     inc.severity,
            "latitude":     float(inc.latitude),
            "longitude":    float(inc.longitude),
            "radius_meters": inc.radius_meters,
            "description":  inc.description,
            "occurred_at":  inc.occurred_at.isoformat(),
            "created_at":   inc.created_at.isoformat(),
            "reporter":     inc.reported_by.get_full_name() or inc.reported_by.username,
        })

    return Response(data)


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