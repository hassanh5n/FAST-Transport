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
