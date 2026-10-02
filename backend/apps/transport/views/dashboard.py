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
