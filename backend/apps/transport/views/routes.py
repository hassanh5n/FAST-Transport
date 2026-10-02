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

from .maps import _display_route_geometry

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
