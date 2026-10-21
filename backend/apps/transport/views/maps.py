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
import logging
import time
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
from ..corridor import ROUTE_LINE_VERSION, build_corridor, haversine_m, route_through
from ..rbac import get_effective_permissions, is_super_admin, staff_with_module

logger = logging.getLogger(__name__)


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
    params = {"format": "jsonv2", "addressdetails": 1, "limit": 5, "accept-language": "en"}
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
        cache_value = f"reverse:en:{latitude:.6f},{longitude:.6f}"
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


# 5 decimals is ~1 m; the simplify tolerance (~2 m) drops points a map can't show.
LINE_DECIMALS = 5
LINE_TOLERANCE_DEG = 2e-5


def _compact_line(geometry):
    """Shrink a road line for transport: Douglas-Peucker simplify, then round.

    The router returns every road node at 6 decimals, which made the network map
    payload ~440 KB. Endpoints are always kept. Non-LineStrings pass through.
    """
    if not _is_line_string(geometry):
        return geometry
    try:
        points = [(float(p[0]), float(p[1])) for p in geometry["coordinates"]]
    except (TypeError, ValueError, IndexError):
        return geometry
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (x1, y1), (x2, y2) = points[first], points[last]
        dx, dy = x2 - x1, y2 - y1
        length = (dx * dx + dy * dy) ** 0.5
        farthest, index = 0.0, None
        for i in range(first + 1, last):
            px, py = points[i]
            if length:
                distance = abs(dy * (px - x1) - dx * (py - y1)) / length
            else:
                distance = ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
            if distance > farthest:
                farthest, index = distance, i
        if index is not None and farthest > LINE_TOLERANCE_DEG:
            keep[index] = True
            stack += [(first, index), (index, last)]
    coordinates = [
        [round(x, LINE_DECIMALS), round(y, LINE_DECIMALS)]
        for (x, y), kept in zip(points, keep) if kept
    ]
    return {**geometry, "coordinates": coordinates}  # keeps leg_seconds


AVERAGE_CITY_SPEED_MPS = 5.5   # ~20 km/h door to door in city traffic
ROAD_DETOUR_FACTOR = 1.3       # straight line -> road distance
STOP_DWELL_SECONDS = 60        # boarding time at each intermediate stop


def _haversine_m(a, b):
    return haversine_m(a, b)


def _main_road_trip(coordinates, timeout=15):
    """Drive through `coordinates` in order on main roads: (line, [(seconds, metres)] per leg), or None.

    Used for live ETAs from a bus's position. Any number of points works: the
    router is asked in chunks. Saved route lines use build_corridor instead.
    """
    trip = route_through(coordinates, timeout=timeout)
    if trip is None:
        return None
    line, _, legs = trip
    return line, legs


def _road_geometry(coordinates):
    """The main-road line for stops in this order, as (geometry, source).

    The line is routed only through the stops it must turn in for (see corridor.py);
    every other stop is served at its boarding point, the closest point of the line.
    The geometry carries, per stop: its pin, the boarding point, the walk to it and
    the drive time from the first stop (`stops`), plus `leg_seconds` for the stop
    ETAs. A straight-line fallback is never cached.
    """
    fallback = {"type": "LineString", "coordinates": [[lng, lat] for lng, lat in coordinates]}
    if len(coordinates) < 2:
        return fallback, "fallback"

    cache_key = _map_cache_key(
        f"corridor-v{ROUTE_LINE_VERSION}",
        f"{settings.MAP_STOP_WALK_M};" + ";".join(f"{lng:.6f},{lat:.6f}" for lng, lat in coordinates),
    )
    cached = cache.get(cache_key)
    if isinstance(cached, dict) and cached.get("source") == "provider" and _is_line_string(cached.get("geometry")):
        return cached["geometry"], "cache"
    corridor = build_corridor(coordinates)
    if corridor is None:
        return fallback, "fallback"
    stops = [
        {"pin": [round(lng, 5), round(lat, 5)], **stop}
        for (lng, lat), stop in zip(coordinates, corridor["stops"])
    ]
    geometry = _compact_line({
        "type": "LineString",
        "coordinates": corridor["line"],
        "v": ROUTE_LINE_VERSION,
        "leg_seconds": [max(0, b["s"] - a["s"]) for a, b in zip(stops, stops[1:])],
        "stops": stops,
        "anchors": corridor["anchors"],
        "turn_ins": corridor["turn_ins"],
        "length_m": corridor["length_m"],
    })
    cache.set(cache_key, {"geometry": geometry, "source": "provider"}, timeout=60 * 60 * 24 * 7)
    return geometry, "provider"


def _matches_stops(geometry, stop_coordinates):
    """A saved line belongs to these stops: same count, same pins, same order."""
    stops = geometry.get("stops")
    if not isinstance(stops, list) or len(stops) != len(stop_coordinates):
        return False
    try:
        return all(
            abs(float(stop["pin"][0]) - float(lng)) < 1e-5 and abs(float(stop["pin"][1]) - float(lat)) < 1e-5
            for stop, (lng, lat) in zip(stops, stop_coordinates)
        )
    except (KeyError, TypeError, ValueError, IndexError):
        return False


def attach_boarding(stops, geometry):
    """Give each stop dict `boarding` ([lng, lat] where the bus picks up) and `walk_m`,
    and return the geometry as sent to the browser (just the line).

    Stops with no saved line (drawn stop to stop) board at their own pin.
    """
    saved = geometry.get("stops") if isinstance(geometry, dict) else None
    matched = isinstance(saved, list) and len(saved) == len(stops)
    for index, stop in enumerate(stops):
        if matched:
            stop["boarding"] = saved[index]["at"]
            stop["walk_m"] = saved[index]["walk_m"]
        else:
            stop["boarding"] = [stop["longitude"], stop["latitude"]]
            stop["walk_m"] = 0
    if not isinstance(geometry, dict):
        return geometry
    return {"type": geometry.get("type"), "coordinates": geometry.get("coordinates", [])}


def _clock_seconds(value):
    hours, minutes, *seconds = (int(part) for part in str(value).split(":"))
    return hours * 3600 + minutes * 60 + (seconds[0] if seconds else 0)


def add_stop_etas(stops, geometry):
    """Give every stop `est_morning_eta` and `est_evening_eta` ("HH:MM:00").

    A time set in the timetable is kept as is. A blank one is worked out from the
    main-road drive time between stops: the morning run arrives at the last stop
    (campus) and the evening run leaves it, so both are counted back from the last
    stop, from its own time or the campus defaults. Each stop dict needs latitude,
    longitude, morning_eta and evening_eta.
    """
    legs = geometry.get("leg_seconds") if isinstance(geometry, dict) else None
    if not isinstance(legs, list) or len(legs) != len(stops) - 1:
        # No routed line yet: straight-line distance at city speed.
        points = [(stop["longitude"], stop["latitude"]) for stop in stops]
        legs = [_haversine_m(a, b) * ROAD_DETOUR_FACTOR / AVERAGE_CITY_SPEED_MPS for a, b in zip(points, points[1:])]
    runs = (
        ("morning_eta", settings.CAMPUS_MORNING_ARRIVAL, -1),
        ("evening_eta", settings.CAMPUS_EVENING_DEPARTURE, 1),
    )
    for field, campus_time, direction in runs:
        seconds = None
        for index in reversed(range(len(stops))):
            if stops[index].get(field):
                seconds = _clock_seconds(stops[index][field])
            elif seconds is None:
                seconds = _clock_seconds(campus_time)
            else:
                seconds += direction * (legs[index] + STOP_DWELL_SECONDS)
            minutes = round(seconds / 60) % (24 * 60)
            stops[index][f"est_{field}"] = f"{minutes // 60:02d}:{minutes % 60:02d}:00"
    return stops


def _display_route_geometry(route, fallback_geometry, fetch=False):
    """The route's saved road line, as (geometry, source).

    Page loads (fetch=False) never call the routing service: a route without a saved
    line is drawn stop to stop at once, instead of the page waiting up to 8 s per
    route. fetch=True (one route at a time) asks the service and saves the result.
    """
    geometry = route.geometry if isinstance(route.geometry, dict) else None
    # A line saved before the current routing (version), for other stops, or a
    # straight stop-to-stop fallback from a provider outage is rebuilt.
    if (_is_line_string(geometry) and geometry.get("v") == ROUTE_LINE_VERSION
            and _matches_stops(geometry, fallback_geometry)
            and not _is_straight_fallback(geometry, fallback_geometry)):
        return _compact_line(geometry), "stored"
    if not fetch:
        return {"type": "LineString", "coordinates": [[lng, lat] for lng, lat in fallback_geometry]}, "fallback"
    geometry, source = _road_geometry(fallback_geometry)
    if source in ("provider", "cache"):
        Route.objects.filter(pk=route.pk).update(geometry=geometry, geometry_updated_at=timezone.now())
        route.geometry = geometry
        return geometry, "stored"
    return geometry, source
