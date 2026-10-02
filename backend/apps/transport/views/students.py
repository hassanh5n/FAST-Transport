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
        if user.is_staff:
            return StudentProfile.objects.all()
        return StudentProfile.objects.filter(user=user)


class SemesterViewSet(viewsets.ModelViewSet):
    queryset = Semester.objects.all()
    serializer_class = SemesterSerializer
    permission_classes = [IsStudentCreateOnly] # Students create, Admin full acccess


class SemesterRegistrationViewSet(viewsets.ModelViewSet):
    queryset = SemesterRegistration.objects.all()
    serializer_class = SemesterRegistrationSerializer
    permission_classes = [IsStudentCreateOnly] # Students create, Admin full access

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return SemesterRegistration.objects.all()
        return SemesterRegistration.objects.filter(student__user=user)


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

    story.append(Paragraph("Fleetcentric.ai", title_style))
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
