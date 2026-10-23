from rest_framework.decorators import throttle_classes
from apps.transport.throttles import AuthRateThrottle, OtpRateThrottle
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
from apps.transport.emails import display_name, send_otp_email
from apps.transport.otp import check_otp, generate_otp
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
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

def current_user_payload(user):
    """Who is signed in and what they may open. Also sent with the login tokens, so the
    login page does not need a second request for it."""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_staff": user.is_staff,
        "user_type": getattr(getattr(user, "studentprofile", None), "user_type", None),
        # driver_profile comes with the user (SharedJWTAuthentication), so no extra query
        "role": "staff" if user.is_staff else ("driver" if hasattr(user, "driver_profile") else "student"),
        "is_super_admin": is_super_admin(user),
        "admin_role": (
            user.admin_profile.role.name
            if user.is_staff and hasattr(user, "admin_profile") and user.admin_profile.role
            else None
        ),
        "permissions": get_effective_permissions(user) if user.is_staff else {},
    }


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(current_user_payload(request.user))


class StudentSignupView(generics.CreateAPIView):
    throttle_classes = [AuthRateThrottle]
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
                "failed_attempts": 0,
            }
        )

        # Send OTP email. If this fails the user is still created (they can resend),
        # but the response must say so instead of claiming the email went out.
        self.otp_email_sent = True
        try:
            send_otp_email(
                user.email, otp_code, purpose="verify",
                name=display_name(user),
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send OTP email to {user.email}: {e}")
            self.otp_email_sent = False

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        if not self.otp_email_sent:
            return Response(
                {
                    "detail": "Account created, but we could not send the OTP email. "
                              "Use Resend OTP on the next page, or contact the transport office.",
                    "otp_email_sent": False,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {
                "detail": "Account created. Please check your email for the OTP verification code.",
                "otp_email_sent": True,
            },
            status=status.HTTP_201_CREATED
        )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def verify_otp(request):
    """
    POST /api/verify-otp/
    Body: { "email": "...", "otp": "123456" }
    """
    email = request.data.get("email", "").strip()
    otp_input = request.data.get("otp", "").strip()

    if not email or not otp_input:
        return Response({"detail": "Email and OTP are required."}, status=400)

    users = User.objects.filter(email=email, is_active=False)
    if users.count() > 1:
        return Response({"detail": "Multiple accounts found. Contact support."}, status=400)
    user = users.first()
    # Unknown email, no code, wrong code: one generic answer (see check_otp),
    # so this endpoint does not reveal which emails have pending sign-ups.
    otp_record = OTPVerification.objects.filter(user=user).first() if user else None

    error = check_otp(otp_record, otp_input)
    if error:
        return Response({"detail": error}, status=400)

    # All good — activate user and mark OTP used
    otp_record.is_used = True
    otp_record.save()
    user.is_active = True
    user.save()

    return Response({"detail": "Email verified successfully. You can now log in."})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
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
 
    otp_code = generate_otp()
    OTPVerification.objects.create(
        user=user,
        otp=otp_code,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
 
    try:
        send_otp_email(
            email, otp_code, purpose="verify",
            name=display_name(user),
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to resend OTP email to {email}: {e}")
        return Response(
            {"detail": "We could not send the OTP email right now. Please try again later "
                       "or contact the transport office."},
            status=503,
        )

    return Response({"detail": "If that email is registered, a new OTP has been sent."})
    

@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
def forgot_password(request):
    """
    POST /api/forgot-password/
    Body: { "email": "k220001@nu.edu.pk" }
 
    Sends a password-reset OTP to the email.
    Always answers the same way, whether or not the email has an account, so
    this endpoint cannot be used to find out who is registered.
    """
    generic = Response({"detail": "If that email has an account, a reset code is on its way."})
    email = request.data.get("email", "").lower().strip()
    if not email:
        return Response({"detail": "Email is required."}, status=400)

    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        return generic

    # One code per minute. Answer generically here too: a "please wait" reply
    # would only ever be seen for real accounts.
    existing = OTPVerification.objects.filter(user=user).first()
    if existing:
        if (timezone.now() - existing.created_at).total_seconds() < 60:
            return generic
        existing.delete()

    otp_code = generate_otp()
    OTPVerification.objects.create(
        user=user,
        otp=otp_code,
        expires_at=timezone.now() + timedelta(minutes=10),
    )

    try:
        send_otp_email(email, otp_code, purpose="reset", name=display_name(user))
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to send password reset email: {e}")
        return Response({"detail": "We could not send the email right now. Try again later."}, status=503)

    return generic
 
 
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthRateThrottle])
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
 
    user = User.objects.filter(email__iexact=email).first()
    # Same answer for an unknown email as for a wrong code, so this endpoint
    # cannot be used to find out which emails have accounts.
    otp_obj = OTPVerification.objects.filter(user=user).first() if user else None
    error = check_otp(otp_obj, otp_code)
    if error:
        return Response({"detail": error}, status=400)

    try:
        validate_password(new_password, user=user)
    except DjangoValidationError as exc:
        return Response({"detail": " ".join(exc.messages)}, status=400)

    user.set_password(new_password)
    user.save()
    otp_obj.delete()
 
    return Response({"detail": "Password reset successfully. You can now log in."})
