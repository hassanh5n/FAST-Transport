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
