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
                subject="Your Fleetcentric.ai OTP Code",
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
        subject="Your Fleetcentric.ai OTP",
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
        subject="Reset your Fleetcentric.ai password",
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
