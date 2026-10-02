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

class FeeVerificationViewSet(viewsets.ModelViewSet):
    queryset = FeeVerification.objects.all()
    serializer_class = FeeVerificationSerializer
    permission_classes = [IsAdminOrReadOnly] # Admin full access, Students read only

    def verify_fee(fee, admin_user):
        fee.is_verified = True
        fee.verified_by = admin_user
        fee.verified_at = timezone.now()
        fee.save()

        # Update transport registration
        TransportRegistration.objects.filter(
            student=fee.student,
            semester=fee.semester
        ).update(status="approved")

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_challan(request, pk):
    try:
        profile = StudentProfile.objects.get(user=request.user)
    except StudentProfile.DoesNotExist:
        return Response({"detail": "Student profile not found"}, status=404)
 
    try:
        registration = TransportRegistration.objects.get(id=pk, student=profile)
    except TransportRegistration.DoesNotExist:
        return Response({"detail": "Registration not found"}, status=404)
 
    # Auto-create challan if it was missed during registration
    challan, created = Challan.objects.get_or_create(
        registration=registration,
        student=profile,
        defaults={
            "amount": registration.semester.fee if hasattr(registration.semester, "fee") else 0,
            "status": "unpaid"
        }
    )
 
    data = ChallanSerializer(challan).data
    # ADDED: expose the registration status so the frontend can show
    # "waiting for verification" vs "approved" without a separate API call
    data["registration_status"] = registration.status
    return Response(data)

def _mark_seat_confirmed(profile, semester):
    """
    Payment received: a held seat becomes an owned one.

    Clears the payment deadline and flips both registration records, so the
    student never sees "Seat Held" with a countdown after they have paid.
    """
    semester_registration = SemesterRegistration.objects.filter(
        student=profile, semester=semester
    ).first()
    if semester_registration and semester_registration.status != "Confirmed":
        semester_registration.status = "Confirmed"
        semester_registration.save(update_fields=["status", "updated_at"])

    TransportRegistration.objects.filter(
        student=profile, semester=semester
    ).exclude(status="Cancelled").update(status="Approved")

    Challan.objects.filter(
        registration__student=profile,
        registration__semester=semester,
        status="paid",
    ).update(payment_due_at=None)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pay_challan(request, pk):
    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        return Response({"detail": "Profile not found"}, status=404)

    try:
        challan = Challan.objects.get(registration__id=pk, student=profile)
    except Challan.DoesNotExist:
        return Response({"detail": "Challan not found"}, status=404)

    if challan.status == "paid":
        return Response({"detail": "Already paid"}, status=400)

    challan.status = "paid"
    challan.save()

    _mark_seat_confirmed(profile, challan.registration.semester)

    # Create or update FeeVerification record
    fee_verification, _ = FeeVerification.objects.get_or_create(
        student=profile,
        semester=challan.registration.semester,
        defaults={
            "amount": challan.amount,
            "challan_number": f"CHN-{challan.id:04d}",
        }
    )

    # Notify all admin/staff users
    admin_users = staff_with_module("fees")  # only admins who handle fees
    for admin in admin_users:
        Notification.objects.create(
            user=admin,
            title="Fee Payment Received",
            message=f"Student {profile.roll_number} has paid transport fees for {challan.registration.semester.name}. Please verify.",
            type="info"
        )

    return Response(ChallanSerializer(challan).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_fee(request, pk):
    if not request.user.is_staff:
        return Response({"detail": "Unauthorized"}, status=403)

    try:
        fee = FeeVerification.objects.get(pk=pk)
    except FeeVerification.DoesNotExist:
        return Response({"detail": "Fee verification not found"}, status=404)

    fee.is_verified = True
    fee.verified_by = request.user
    fee.verified_at = timezone.now()
    fee.save()

    # Approve the transport registration
    registrations_qs = TransportRegistration.objects.filter(
        student=fee.student,
        semester=fee.semester
    )
    registrations_qs.update(status="Approved")

    first_registration = registrations_qs.select_related("route", "stop").first()
    if first_registration and first_registration.route and first_registration.stop:
        semester_registration, _ = SemesterRegistration.objects.update_or_create(
            student=fee.student,
            semester=fee.semester,
            defaults={
                "route": first_registration.route,
                "stop": first_registration.stop,
                "status": "Approved",
            },
        )

        if not SeatAllocation.objects.filter(registration=semester_registration).exists():
            allocate_seat_for_student(semester_registration)

    # Notify the student
    Notification.objects.create(
        user=fee.student.user,
        title="Fee Verified",
        message=f"Your transport fee for {fee.semester.name} has been verified. Your registration is now approved.",
        type="info"
    )

    return Response({"detail": "Fee verified successfully"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_fee_verifications(request):
    if not request.user.is_staff:
        return Response({"detail": "Unauthorized"}, status=403)

    fees = FeeVerification.objects.select_related(
        "student__user", "semester", "verified_by"
    ).order_by("is_verified", "-created_at")

    def full_name(user):
        name = f"{user.first_name} {user.last_name}".strip()
        return name if name else user.username

    data = [
        {
            "id": f.id,
            "roll_number": f.student.roll_number,
            "student_name": full_name(f.student.user),
            "semester": f.semester.name,
            "amount": str(f.amount),
            "challan_number": f.challan_number,
            "is_verified": f.is_verified,
            "verified_by": full_name(f.verified_by) if f.verified_by else None,
            "verified_at": f.verified_at,
            "created_at": f.created_at,
        }
        for f in fees
    ]
    return Response(data)


# ── Stripe Payment + OTP Verification ────────────────────────────────────────



@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_payment_intent(request, pk):
    """
    POST /api/transport-registrations/<pk>/create-payment-intent/
    Creates a Stripe PaymentIntent in test/sandbox mode.
    Returns client_secret for the frontend to confirm payment.
    """
    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        return Response({"detail": "Student profile not found"}, status=404)

    registration = TransportRegistration.objects.filter(pk=pk, student=profile).first()
    if not registration:
        return Response({"detail": "Registration not found"}, status=404)

    challan = Challan.objects.filter(registration=registration).first()
    if not challan:
        return Response({"detail": "Challan not found"}, status=404)

    if challan.status == "paid":
        return Response({"detail": "Already paid"}, status=400)

    stripe_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    if stripe_key and stripe_key.startswith("sk_test_") and stripe_key != "sk_test_placeholder":
        import stripe as _stripe
        _stripe.api_key = stripe_key
        try:
            intent = _stripe.PaymentIntent.create(
                amount=int(challan.amount * 100),
                currency="pkr",
                metadata={"challan_id": challan.id, "user_id": request.user.id},
            )
            return Response({
                "client_secret": intent.client_secret,
                "payment_intent_id": intent.id,
                "amount": str(challan.amount),
                "simulated": False,
            })
        except Exception as e:
            return Response({"detail": f"Stripe error: {str(e)}"}, status=500)
    else:
        import uuid
        simulated_secret = f"pi_sim_{uuid.uuid4().hex[:16]}_secret_{uuid.uuid4().hex[:16]}"
        return Response({
            "client_secret": simulated_secret,
            "payment_intent_id": f"pi_sim_{uuid.uuid4().hex[:16]}",
            "amount": str(challan.amount),
            "simulated": True,
        })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_stripe_payment(request, pk):
    """
    POST /api/transport-registrations/<pk>/confirm-stripe-payment/
    Called after Stripe confirms payment on frontend.
    Generates OTP, emails it, and returns 200.
    """
    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        return Response({"detail": "Student profile not found"}, status=404)

    registration = TransportRegistration.objects.filter(pk=pk, student=profile).first()
    if not registration:
        return Response({"detail": "Registration not found"}, status=404)

    challan = Challan.objects.filter(registration=registration).first()
    if not challan:
        return Response({"detail": "Challan not found"}, status=404)

    if challan.status == "paid":
        return Response({"detail": "Already paid"}, status=400)

    otp_code = ''.join(random.choices(_string.digits, k=6))
    expires = timezone.now() + timedelta(minutes=10)

    OTPVerification.objects.update_or_create(
        user=request.user,
        defaults={"otp": otp_code, "expires_at": expires, "is_used": False},
    )

    try:
        send_mail(
            subject="Fleetcentric.ai — Payment OTP",
            message=(
                f"Hello {request.user.username},\n\n"
                f"Your payment verification OTP is: {otp_code}\n\n"
                f"This code expires in 10 minutes.\n\n"
                f"Amount: PKR {challan.amount}\n"
                f"If you did not initiate this payment, please ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[request.user.email],
            fail_silently=False,
        )
    except Exception:
        pass  # Don't block if email sending fails in dev

    return Response({
        "message": "OTP sent to your email",
        "email_hint": request.user.email[:3] + "***" + request.user.email[request.user.email.index("@"):],
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_payment_otp(request, pk):
    """
    POST /api/transport-registrations/<pk>/verify-payment-otp/
    Body: { "otp": "123456" }
    Verifies the OTP and marks challan as paid + creates FeeVerification.
    """
    otp_input = request.data.get("otp", "").strip()
    if not otp_input:
        return Response({"detail": "OTP is required."}, status=400)

    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        return Response({"detail": "Student profile not found"}, status=404)

    registration = TransportRegistration.objects.filter(pk=pk, student=profile).first()
    if not registration:
        return Response({"detail": "Registration not found"}, status=404)

    challan = Challan.objects.filter(registration=registration).first()
    if not challan:
        return Response({"detail": "Challan not found"}, status=404)

    if challan.status == "paid":
        return Response({"detail": "Already paid"}, status=400)

    try:
        otp_record = OTPVerification.objects.get(user=request.user)
    except OTPVerification.DoesNotExist:
        return Response({"detail": "No OTP found. Please request a new one."}, status=404)

    if otp_record.is_used:
        return Response({"detail": "OTP has already been used."}, status=400)

    if timezone.now() > otp_record.expires_at:
        return Response({"detail": "OTP has expired. Please request a new one."}, status=400)

    if otp_record.otp != otp_input:
        return Response({"detail": "Invalid OTP. Please try again."}, status=400)

    with transaction.atomic():
        otp_record.is_used = True
        otp_record.save()

        challan.status = "paid"
        challan.save()

        _mark_seat_confirmed(profile, registration.semester)

        FeeVerification.objects.get_or_create(
            student=profile,
            semester=registration.semester,
            defaults={
                "amount": challan.amount,
                "challan_number": f"CHN-{challan.id:04d}",
            },
        )

        admin_users = staff_with_module("fees")  # only admins who handle fees
        for admin in admin_users:
            Notification.objects.create(
                user=admin,
                title="Fee Payment Received (Stripe + OTP)",
                message=(
                    f"Student {profile.roll_number} has paid transport fees "
                    f"for {registration.semester.name} via Stripe. "
                    f"Amount: PKR {challan.amount}. Please verify."
                ),
                type="info",
            )

    return Response({
        "detail": "Payment verified successfully. Challan marked as paid.",
        "challan_status": "paid",
    })
