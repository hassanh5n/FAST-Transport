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
from .. import audit
from .. import auto_assign
from ..fleet_import import import_buses, import_drivers, parse_csv


def _import_csv(request, importer, model_name):
    """Shared upload handling for the bus and driver CSV imports."""
    upload = request.FILES.get("file")
    if not upload:
        raise ValidationError({"file": "Choose a CSV file."})
    if not upload.name.lower().endswith(".csv"):
        raise ValidationError({"file": "Only .csv files are supported."})
    if upload.size > 2 * 1024 * 1024:
        raise ValidationError({"file": "The file must be smaller than 2 MB."})
    try:
        report = importer(parse_csv(upload.read()))
    except ValueError as exc:
        raise ValidationError({"file": str(exc)})

    audit.write_log(
        action="create",
        module="fleet",
        model_name=model_name,
        description=(
            f"Imported {model_name}s from {upload.name}: {len(report['created'])} created, "
            f"{len(report['skipped'])} skipped, {len(report['invalid'])} invalid."
        ),
    )
    return Response(report, status=status.HTTP_201_CREATED)


class BusViewSet(viewsets.ModelViewSet):
    queryset = Bus.objects.order_by("bus_number", "id")
    serializer_class = BusSerializer
    permission_classes = [IsAdmin] # Only Admin full access

    @action(detail=False, methods=["post"], url_path="import")
    def import_file(self, request):
        """Bulk-create buses from a CSV; duplicates (bus number / tracker token) are skipped."""
        return _import_csv(request, import_buses, "bus")

    @action(detail=False, methods=["get"])
    def available(self, request):

        assigned = RouteAssignment.objects.filter(
            is_active=True
        ).values_list("bus_id", flat=True)

        buses = Bus.objects.exclude(id__in=assigned)

        serializer = self.get_serializer(buses, many=True)

        return Response(serializer.data)


class DriverViewSet(viewsets.ModelViewSet):
    queryset = Driver.objects.select_related("user").order_by("name", "id")  # login_username, without a query per driver
    serializer_class = DriverSerializer
    permission_classes = [IsAdmin]  # keeps admin-only for all other actions

    @action(detail=False, methods=["post"], url_path="import")
    def import_file(self, request):
        """Bulk-create drivers from a CSV; duplicates (CNIC / license number) are skipped."""
        return _import_csv(request, import_drivers, "driver")

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
    queryset = RouteAssignment.objects.order_by("-is_active", "route__name").select_related(
        "route",
        "bus",
        "driver",
        "semester"
    ).defer("route__geometry")  # never returned (RouteSerializer); ~4 KB a row from Supabase
    serializer_class = RouteAssignmentSerializer
    permission_classes = [IsAdmin] # Only Admin full access

    @action(detail=False, methods=["get"], url_path="auto-plan")
    def auto_plan(self, request):
        """What one-click assignment would do this semester, without saving anything."""
        try:
            return Response(auto_assign.plan())
        except auto_assign.AutoAssignError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], url_path="auto-assign")
    def auto_assign(self, request):
        """Save the proposals the admin kept: [{route_id, bus_id, driver_id}, ...]."""
        try:
            saved = auto_assign.apply(request.data.get("assignments") or [], RouteAssignmentSerializer)
        except auto_assign.AutoAssignError as exc:
            detail = exc.args[0]
            return Response(
                {"detail": detail} if isinstance(detail, str) else {"detail": "Some assignments could not be saved.", "rows": detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(saved, many=True).data, status=status.HTTP_201_CREATED)



class MaintenanceScheduleViewSet(viewsets.ModelViewSet):
    queryset = MaintenanceSchedule.objects.all()
    serializer_class = MaintenanceScheduleSerializer
    permission_classes = [IsAdmin] # Only Admin full access
