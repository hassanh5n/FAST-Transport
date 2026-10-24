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

class StudentProfileViewSet(viewsets.ModelViewSet):
    queryset = StudentProfile.objects.all()
    serializer_class = StudentProfileSerializer
    permission_classes = [IsStudentCreateOnly] #Students create, Admin full accces

    def get_queryset(self):
        user = self.request.user
        # Scope on staff status, not group membership: drivers and group-less
        # users must only ever see their own profile.
        profiles = StudentProfile.objects.select_related("user")
        if user.is_staff:
            return profiles.all()
        return profiles.filter(user=user)


class SemesterViewSet(viewsets.ModelViewSet):
    queryset = Semester.objects.order_by("id")
    serializer_class = SemesterSerializer
    permission_classes = [IsStudentCreateOnly] # Students create, Admin full acccess


class SemesterRegistrationViewSet(viewsets.ModelViewSet):
    queryset = SemesterRegistration.objects.all()
    serializer_class = SemesterRegistrationSerializer
    permission_classes = [IsStudentCreateOnly] # Students create, Admin full access

    def get_queryset(self):
        user = self.request.user
        registrations = SemesterRegistration.objects.select_related(
            "student__user", "semester", "route", "stop",
        ).defer("route__geometry")  # never returned (RouteSerializer)
        if user.is_staff:
            return registrations.all()
        return registrations.filter(student__user=user)


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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def download_transport_card(request):
    """The rider's printable transport card for the active semester (see transport_card.py)."""
    from ..seatallocation import payment_settled
    from ..transport_card import CardData, build_transport_card_pdf

    profile = StudentProfile.objects.select_related("user").filter(user=request.user).first()
    if not profile:
        return Response({"detail": "Student profile not found"}, status=404)

    active_semester = Semester.objects.filter(is_active=True).first()
    if not active_semester:
        return Response({"detail": "No active semester"}, status=404)

    registration = SemesterRegistration.objects.filter(
        student=profile, semester=active_semester,
    ).select_related("route", "stop").first()
    seat_obj = None
    if registration:
        seat_obj = SeatAllocation.objects.select_related("route_assignment__bus").filter(
            registration=registration
        ).first()

    # The card is proof of a paid seat, so it is only issued for one.
    if not (seat_obj and payment_settled(registration)):
        return Response(
            {"detail": "Your transport card is available once your seat is allocated and your fee is paid."},
            status=403,
        )

    route, stop = registration.route, registration.stop
    seat_number = seat_obj.seat_number
    bus_number = seat_obj.route_assignment.bus.bus_number

    # Pickup and drop-off times at this rider's own stop.
    morning_eta = evening_eta = ""
    if route and stop:
        route_stop = RouteStop.objects.filter(route=route, stop=stop).first()
        if route_stop:
            morning_eta = _clock(route_stop.morning_eta)
            evening_eta = _clock(route_stop.evening_eta)

    valid_until = ""
    if active_semester.end_date and active_semester.end_date > active_semester.start_date:
        valid_until = active_semester.end_date.strftime("%d %b %Y").lstrip("0")

    portal = (getattr(settings, "EMAIL_PORTAL_URL", "") or "").replace("https://", "").replace("http://", "").rstrip("/")
    now = timezone.localtime()
    data = CardData(
        name=profile.user.get_full_name() or profile.user.username,
        user_type=profile.get_user_type_display(),
        id_value=profile.roll_number or "",
        department=profile.department,
        batch=profile.batch,
        semester=str(active_semester),
        valid_until=valid_until,
        route=route.name if route else "",
        stop=stop.name if stop else "",
        bus=bus_number or "",
        seat=str(seat_number) if seat_number else "",
        morning_eta=morning_eta,
        evening_eta=evening_eta,
        status="Active",
        status_ok=True,
        card_number=f"FC-{active_semester.year}-{profile.pk:05d}",
        portal_url=portal,
        generated_at=now.strftime("%d %b %Y, %I:%M %p").lstrip("0").replace(", 0", ", "),
    )
    pdf = build_transport_card_pdf(data)

    filename = f"transport_card_{profile.display_id.replace(' ', '_')}_{active_semester.name.replace(' ', '_')}.pdf"
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _clock(value):
    """datetime.time -> "7:35 AM"; "" when unset."""
    return value.strftime("%I:%M %p").lstrip("0") if value else ""
