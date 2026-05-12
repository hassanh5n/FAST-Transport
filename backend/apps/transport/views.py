from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.db.models import Count, Exists, OuterRef
from django.db import transaction
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
import random
import string as _string
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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
import io
from .permissions import (
    IsAdmin,
    IsStudent,
    IsAdminOrReadOnly,
    IsStudentCreateOnly
)
from .models import (
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
)

from .serializers import (
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
    TransportRegistrationSerializer
)
from .seatallocation import (
    allocate_seat_for_student,
    allocate_seat_on_assignment,
    reassign_seat_on_assignment,
)

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
        })


class StudentProfileViewSet(viewsets.ModelViewSet):
    queryset = StudentProfile.objects.all()
    serializer_class = StudentProfileSerializer
    permission_classes = [IsStudentCreateOnly] #Students create, Admin full accces

    def get_queryset(self):
        user = self.request.user
        if user.groups.filter(name="Student").exists():
            return StudentProfile.objects.filter(user=user) # Student sees only their own profile
        return StudentProfile.objects.all() # Admin sees all profiles


class SemesterViewSet(viewsets.ModelViewSet):
    queryset = Semester.objects.all()
    serializer_class = SemesterSerializer
    permission_classes = [IsStudentCreateOnly] # Students create, Admin full acccess


class RouteViewSet(viewsets.ModelViewSet):
    queryset = Route.objects.all()
    serializer_class = RouteSerializer
    permission_classes = [IsAdminOrReadOnly] # Admin full access, Students read only

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


class StopViewSet(viewsets.ModelViewSet):
    queryset = Stop.objects.all()
    serializer_class = StopSerializer
    permission_classes = [IsAdminOrReadOnly] # Admin full access, Students read only


class RouteStopViewSet(viewsets.ModelViewSet):
    queryset = RouteStop.objects.all()
    serializer_class = RouteStopSerializer
    permission_classes = [IsAdminOrReadOnly] # Admin full access, Students read only


class BusViewSet(viewsets.ModelViewSet):
    queryset = Bus.objects.all()
    serializer_class = BusSerializer
    permission_classes = [IsAdmin] # Only Admin full access

    @action(detail=False, methods=["get"])
    def available(self, request):

        assigned = RouteAssignment.objects.filter(
            is_active=True
        ).values_list("bus_id", flat=True)

        buses = Bus.objects.exclude(id__in=assigned)

        serializer = self.get_serializer(buses, many=True)

        return Response(serializer.data)


class DriverViewSet(viewsets.ModelViewSet):
    queryset = Driver.objects.all()
    serializer_class = DriverSerializer
    permission_classes = [IsAdmin]  # keeps admin-only for all other actions

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
    queryset = RouteAssignment.objects.all().select_related(
        "route",
        "bus",
        "driver",
        "semester"
    )
    serializer_class = RouteAssignmentSerializer
    permission_classes = [IsAdmin] # Only Admin full access


class SemesterRegistrationViewSet(viewsets.ModelViewSet):
    queryset = SemesterRegistration.objects.all()
    serializer_class = SemesterRegistrationSerializer
    permission_classes = [IsStudentCreateOnly] # Students create, Admin full access

    def get_queryset(self):
        user = self.request.user
        if user.groups.filter(name="Student").exists():
            student_profile = StudentProfile.objects.get(user=user)
            return SemesterRegistration.objects.filter(student=student_profile)
        return SemesterRegistration.objects.all()

class TransportRegistrationViewSet(viewsets.ModelViewSet):
    queryset = TransportRegistration.objects.all()
    serializer_class = TransportRegistrationSerializer
    permission_classes = [IsStudentCreateOnly]

    def get_queryset(self):
        user = self.request.user
        profile = StudentProfile.objects.filter(user=user).first()

        if not profile:
            return TransportRegistration.objects.none()

        return TransportRegistration.objects.filter(student=profile)
    
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated])
    def my_registration(self, request):
        user = request.user
        profile = StudentProfile.objects.filter(user=user).first()

        if not profile:
            return Response(
                {"detail": "Student profile not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        registration = TransportRegistration.objects.filter(student=profile).first()

        if not registration:
            return Response(
                {"detail": "No transport registration found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(registration)
        return Response(serializer.data)

    def perform_create(self, serializer):
        profile = StudentProfile.objects.get(user=self.request.user)

        stop = serializer.validated_data["stop"]
        semester = serializer.validated_data["semester"]

        route_stop = RouteStop.objects.filter(stop=stop).first()
        if not route_stop:
            raise ValidationError("No route found for this stop")

        fee = FeeVerification.objects.filter(
            student=profile,
            semester=semester,
            is_verified=True
        ).first()

        reg_status = "Approved" if fee else "Pending"
        registration = serializer.save(
            student=profile,
            route=route_stop.route,
            semester=semester,
            status=reg_status
        )

        semester_registration, _ = SemesterRegistration.objects.update_or_create(
            student=profile,
            semester=semester,
            defaults={
                "route": route_stop.route,
                "stop": stop,
                "status": reg_status,
            },
        )

        if fee and not SeatAllocation.objects.filter(registration=semester_registration).exists():
            allocate_seat_for_student(semester_registration)

        amount = 45000
        Challan.objects.get_or_create(
            registration=registration,
            student=profile,
            defaults={"amount": amount, "status": "unpaid"}
        )

class SeatAllocationViewSet(viewsets.ModelViewSet):
    queryset = SeatAllocation.objects.all()
    serializer_class = SeatAllocationSerializer
    permission_classes = [IsAdmin] # Only Admin full access

    def _assignment_options_by_route_semester(self):
        active_assignments = list(
            RouteAssignment.objects.filter(
                is_active=True,
                route__is_active=True,
                bus__is_active=True,
                semester__is_active=True,
            ).select_related("route", "semester", "bus", "driver")
        )

        seat_counts = {
            row["route_assignment"]: row["count"]
            for row in SeatAllocation.objects.filter(route_assignment__in=active_assignments)
            .values("route_assignment")
            .annotate(count=Count("id"))
        }

        assignment_by_route_semester = {}
        for assignment in active_assignments:
            occupied_seats = seat_counts.get(assignment.id, 0)
            available_seats = max(assignment.bus.capacity - occupied_seats, 0)
            key = (assignment.route_id, assignment.semester_id)
            assignment_by_route_semester.setdefault(key, []).append(
                {
                    "id": assignment.id,
                    "bus_number": assignment.bus.bus_number,
                    "driver_name": assignment.driver.name,
                    "total_seats": assignment.bus.capacity,
                    "occupied_seats": occupied_seats,
                    "available_seats": available_seats,
                }
            )

        return assignment_by_route_semester

    @action(detail=False, methods=["get"], url_path="eligible-registrations")
    def eligible_registrations(self, request):
        verified_fee_exists = FeeVerification.objects.filter(
            student=OuterRef("student"),
            semester=OuterRef("semester"),
            is_verified=True,
        )
        seat_exists = SeatAllocation.objects.filter(registration=OuterRef("pk"))

        registrations = (
            SemesterRegistration.objects.select_related(
                "student__user", "semester", "route", "stop"
            )
            .annotate(has_verified_fee=Exists(verified_fee_exists), has_seat=Exists(seat_exists))
            .filter(has_verified_fee=True, has_seat=False)
            .order_by("semester__name", "student__roll_number")
        )

        assignment_by_route_semester = self._assignment_options_by_route_semester()

        data = []
        for registration in registrations:
            assignment_options = assignment_by_route_semester.get(
                (registration.route_id, registration.semester_id),
                [],
            )
            data.append(
                {
                    "registration_id": registration.id,
                    "roll_number": registration.student.roll_number,
                    "student_name": registration.student.user.username,
                    "semester": registration.semester.name,
                    "route": registration.route.name,
                    "stop": registration.stop.name,
                    "status": registration.status,
                    "assignment_options": assignment_options,
                }
            )

        return Response(data)

    @action(detail=False, methods=["get"], url_path="current-allocations")
    def current_allocations(self, request):
        verified_fee_exists = FeeVerification.objects.filter(
            student=OuterRef("registration__student"),
            semester=OuterRef("registration__semester"),
            is_verified=True,
        )

        allocations = (
            SeatAllocation.objects.select_related(
                "registration__student__user",
                "registration__semester",
                "registration__route",
                "registration__stop",
                "route_assignment__bus",
            )
            .annotate(has_verified_fee=Exists(verified_fee_exists))
            .filter(has_verified_fee=True)
            .order_by("registration__semester__name", "registration__student__roll_number")
        )

        assignment_by_route_semester = self._assignment_options_by_route_semester()

        data = []
        for allocation in allocations:
            registration = allocation.registration
            assignment_options = assignment_by_route_semester.get(
                (registration.route_id, registration.semester_id),
                [],
            )
            adjusted_options = []
            for option in assignment_options:
                adjusted_options.append(
                    {
                        **option,
                        "available_seats": (
                            option["available_seats"] + 1
                            if option["id"] == allocation.route_assignment_id
                            else option["available_seats"]
                        ),
                    }
                )

            data.append(
                {
                    "registration_id": registration.id,
                    "roll_number": registration.student.roll_number,
                    "student_name": registration.student.user.username,
                    "semester": registration.semester.name,
                    "route": registration.route.name,
                    "stop": registration.stop.name,
                    "status": registration.status,
                    "current_bus": allocation.route_assignment.bus.bus_number,
                    "current_seat_number": allocation.seat_number,
                    "current_route_assignment_id": allocation.route_assignment_id,
                    "assignment_options": adjusted_options,
                }
            )

        return Response(data)

    @action(detail=False, methods=["post"], url_path="assign")
    def assign(self, request):
        registration_id = request.data.get("registration_id")
        route_assignment_id = request.data.get("route_assignment_id")

        if not registration_id or not route_assignment_id:
            return Response(
                {"detail": "registration_id and route_assignment_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            registration = SemesterRegistration.objects.select_related(
                "student__user", "semester", "route"
            ).get(pk=registration_id)
        except SemesterRegistration.DoesNotExist:
            return Response({"detail": "Registration not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            assignment = RouteAssignment.objects.select_related(
                "route", "semester", "bus", "driver"
            ).get(pk=route_assignment_id, is_active=True)
        except RouteAssignment.DoesNotExist:
            return Response(
                {"detail": "Active route assignment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if assignment.route_id != registration.route_id or assignment.semester_id != registration.semester_id:
            return Response(
                {"detail": "Selected assignment does not match student's route and semester."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        has_verified_fee = FeeVerification.objects.filter(
            student=registration.student,
            semester=registration.semester,
            is_verified=True,
        ).exists()
        if not has_verified_fee:
            return Response(
                {"detail": "Student fee is not verified for this semester."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        allocation_result = allocate_seat_on_assignment(registration, assignment)
        if allocation_result != "Seat Allocated":
            return Response({"detail": allocation_result}, status=status.HTTP_400_BAD_REQUEST)

        TransportRegistration.objects.filter(
            student=registration.student,
            semester=registration.semester,
        ).update(status="Approved", is_paid=True)

        seat = SeatAllocation.objects.filter(registration=registration).first()

        return Response(
            {
                "detail": "Seat assigned successfully.",
                "registration_id": registration.id,
                "route_assignment_id": assignment.id,
                "seat_number": seat.seat_number if seat else None,
            }
        )

    @action(detail=False, methods=["post"], url_path="reassign")
    def reassign(self, request):
        registration_id = request.data.get("registration_id")
        route_assignment_id = request.data.get("route_assignment_id")

        if not registration_id or not route_assignment_id:
            return Response(
                {"detail": "registration_id and route_assignment_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            registration = SemesterRegistration.objects.select_related(
                "student__user", "semester", "route"
            ).get(pk=registration_id)
        except SemesterRegistration.DoesNotExist:
            return Response({"detail": "Registration not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            assignment = RouteAssignment.objects.select_related(
                "route", "semester", "bus", "driver"
            ).get(pk=route_assignment_id, is_active=True)
        except RouteAssignment.DoesNotExist:
            return Response(
                {"detail": "Active route assignment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        has_verified_fee = FeeVerification.objects.filter(
            student=registration.student,
            semester=registration.semester,
            is_verified=True,
        ).exists()
        if not has_verified_fee:
            return Response(
                {"detail": "Student fee is not verified for this semester."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reassign_result = reassign_seat_on_assignment(registration, assignment)
        if reassign_result != "Seat Reassigned":
            return Response({"detail": reassign_result}, status=status.HTTP_400_BAD_REQUEST)

        seat = SeatAllocation.objects.filter(registration=registration).first()
        return Response(
            {
                "detail": "Seat reassigned successfully.",
                "registration_id": registration.id,
                "route_assignment_id": assignment.id,
                "seat_number": seat.seat_number if seat else None,
            }
        )


class WaitlistViewSet(viewsets.ModelViewSet):
    queryset = Waitlist.objects.all()
    serializer_class = WaitlistSerializer
    permission_classes = [IsAdminOrReadOnly] # Admin full access, Students read only

    def get_queryset(self):
        user = self.request.user
        if user.groups.filter(name="Student").exists():
            student_profile = StudentProfile.objects.get(user=user)
            return Waitlist.objects.filter(registration__student=student_profile)
        return Waitlist.objects.all()


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


class ComplaintViewSet(viewsets.ModelViewSet):
    queryset = Complaint.objects.all()
    serializer_class = ComplaintSerializer
    permission_classes = [IsStudentCreateOnly] # Students create, Admin full access

    def get_queryset(self):
        user = self.request.user
        if user.groups.filter(name="Student").exists():
            return Complaint.objects.filter(submitted_by=user)
        return Complaint.objects.all()

    def perform_create(self, serializer):
        serializer.save(submitted_by=self.request.user)

    @action(detail=True, methods=["patch"], permission_classes=[IsAdmin])
    def resolve(self, request, pk=None):
        complaint = self.get_object()
        admin_response = (request.data.get("admin_response") or "").strip()

        if not admin_response:
            return Response(
                {"detail": "admin_response is required to resolve a complaint."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        complaint.status = "Resolved"
        complaint.admin_response = admin_response
        complaint.resolved_by = request.user
        complaint.resolved_at = timezone.now()
        complaint.save(update_fields=["status", "admin_response", "resolved_by", "resolved_at"])

        serializer = self.get_serializer(complaint)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RouteChangeRequestViewSet(viewsets.ModelViewSet):
    serializer_class = RouteChangeRequestSerializer
    permission_classes = [IsAuthenticated]
 
    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return RouteChangeRequest.objects.select_related(
                "registration__student__user",
                "registration__semester",
                "current_route",
                "requested_route",
                "requested_stop",
            ).order_by("status", "-requested_at")
        # Student sees only their own requests
        profile = StudentProfile.objects.filter(user=user).first()
        if not profile:
            return RouteChangeRequest.objects.none()
        return RouteChangeRequest.objects.filter(
            registration__student=profile
        ).select_related(
            "registration__semester",
            "current_route",
            "requested_route",
            "requested_stop",
        ).order_by("-requested_at")
 
    def perform_create(self, serializer):
        user = self.request.user
        profile = StudentProfile.objects.filter(user=user).first()
        if not profile:
            raise ValidationError("Student profile not found.")

        requested_stop = serializer.validated_data.get("requested_stop")

        registration = SemesterRegistration.objects.filter(
            student=profile,
            semester__is_active=True,
        ).first()
        if not registration:
            raise ValidationError("No active semester registration found.")

        # Block if they pick the exact same stop they already have
        if requested_stop and registration.stop == requested_stop:
            raise ValidationError("You are already assigned to this stop.")

        # Block duplicate pending requests
        if RouteChangeRequest.objects.filter(
            registration=registration,
            status="Pending",
        ).exists():
            raise ValidationError("You already have a pending route change request.")

        serializer.save(
            registration=registration,
            current_route=registration.route,
            status="Pending",
        )
 
    # ── Student cancels their own pending request ─────────────────────────────
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def cancel(self, request, pk=None):
        profile = StudentProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response({"detail": "Profile not found."}, status=404)
 
        try:
            rcr = RouteChangeRequest.objects.get(pk=pk, registration__student=profile)
        except RouteChangeRequest.DoesNotExist:
            return Response({"detail": "Request not found."}, status=404)
 
        if rcr.status != "Pending":
            return Response({"detail": "Only pending requests can be cancelled."}, status=400)
 
        rcr.status = "Cancelled"
        rcr.resolved_at = timezone.now()
        rcr.save()
        return Response({"detail": "Request cancelled."})
 
    # ── Admin approves ────────────────────────────────────────────────────────
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def approve(self, request, pk=None):
        if not request.user.is_staff:
            return Response({"detail": "Unauthorized."}, status=403)
 
        try:
            rcr = RouteChangeRequest.objects.select_related(
                "registration__student__user",
                "registration__semester",
                "registration__route",
                "registration__stop",
                "requested_route",
                "requested_stop",
            ).get(pk=pk)
        except RouteChangeRequest.DoesNotExist:
            return Response({"detail": "Request not found."}, status=404)
 
        if rcr.status != "Pending":
            return Response({"detail": "Only pending requests can be approved."}, status=400)
 
        registration = rcr.registration
        semester = registration.semester
        student = registration.student
        new_route = rcr.requested_route
        new_stop = rcr.requested_stop
 
        # Check if there is an active assignment + available seat on new route
        new_assignment = RouteAssignment.objects.filter(
            route=new_route,
            semester=semester,
            is_active=True,
        ).first()
        if not new_assignment:
            return Response({"detail": "No active bus assignment for the requested route."}, status=400)
 
        from .seatallocation import _get_next_available_seat_number
        available_seat = _get_next_available_seat_number(new_assignment)
        if available_seat is None:
            return Response({"detail": "No seats available on the requested route."}, status=400)
 
        with transaction.atomic():
            # 1. Free old seat allocation
            SeatAllocation.objects.filter(registration=registration).delete()
 
            # 2. Update the SemesterRegistration to new route + stop
            registration.route = new_route
            registration.stop = new_stop
            registration.save(update_fields=["route", "stop", "updated_at"])
 
            # 3. Allocate seat on new route
            SeatAllocation.objects.create(
                registration=registration,
                route_assignment=new_assignment,
                seat_number=available_seat,
            )
 
            # 4. Update TransportRegistration too (keeps data consistent)
            TransportRegistration.objects.filter(
                student=student,
                semester=semester,
            ).update(route=new_route, stop=new_stop)
 
            # 5. Resolve the request
            rcr.status = "Approved"
            rcr.admin_remarks = request.data.get("admin_remarks", "")
            rcr.resolved_at = timezone.now()
            rcr.save()
 
        # Notify student
        Notification.objects.create(
            user=student.user,
            title="Route Change Approved",
            message=(
                f"Your route change request to {new_route.name} has been approved. "
                f"New stop: {new_stop.name}. Seat no: {available_seat}."
            ),
            type="info",
        )
 
        return Response({"detail": "Route change approved and seat allocated."})
 
    # ── Admin denies ──────────────────────────────────────────────────────────
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def deny(self, request, pk=None):
        if not request.user.is_staff:
            return Response({"detail": "Unauthorized."}, status=403)
 
        try:
            rcr = RouteChangeRequest.objects.get(pk=pk)
        except RouteChangeRequest.DoesNotExist:
            return Response({"detail": "Request not found."}, status=404)
 
        if rcr.status != "Pending":
            return Response({"detail": "Only pending requests can be denied."}, status=400)
 
        rcr.status = "Rejected"
        rcr.admin_remarks = request.data.get("admin_remarks", "")
        rcr.resolved_at = timezone.now()
        rcr.save()
 
        Notification.objects.create(
            user=rcr.registration.student.user,
            title="Route Change Denied",
            message=(
                f"Your route change request to {rcr.requested_route.name} was denied. "
                f"Reason: {rcr.admin_remarks or 'No reason provided.'}"
            ),
            type="warning",
        )
 
        return Response({"detail": "Route change request denied."})
 


class MaintenanceScheduleViewSet(viewsets.ModelViewSet):
    queryset = MaintenanceSchedule.objects.all()
    serializer_class = MaintenanceScheduleSerializer
    permission_classes = [IsAdmin] # Only Admin full access


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [IsAdminOrReadOnly] # Admin full access, Students read only

    def get_queryset(self):
        user = self.request.user
        if user.groups.filter(name="Student").exists():
            return Notification.objects.filter(user=user)
        return Notification.objects.all()


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

        # Send OTP email
        send_mail(
            subject="Your FAST Transport OTP Code",
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
        subject="Your FAST Transport OTP",
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
        subject="Reset your FAST Transport password",
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
            if active_registration:
                seat_obj = SeatAllocation.objects.select_related("route_assignment__bus").filter(registration=active_registration).first()
                if seat_obj:
                    seat = {"seat_number": seat_obj.seat_number, "allocated_at": seat_obj.allocated_at}
                    bus_number = seat_obj.route_assignment.bus.bus_number
                else:
                    waitlist_obj = Waitlist.objects.filter(registration=active_registration).first()
                    if waitlist_obj:
                        waitlist_position = waitlist_obj.position

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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
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
    admin_users = User.objects.filter(is_staff=True)
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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_bus_tracking(request):
    profile = StudentProfile.objects.filter(user=request.user).first()
    if not profile:
        return Response({"detail": "Profile not found"}, status=404)

    registration = TransportRegistration.objects.filter(
        student=profile,
        route__isnull=False
    ).select_related('route', 'stop').first()

    if not registration:
        return Response({"detail": "No active registration found"}, status=404)

    route = registration.route

    route_stops = (
        RouteStop.objects
        .filter(route=route)
        .select_related('stop')
        .order_by('stop_order')
    )

    stops = [
        {
            "name": rs.stop.name,
            "lat": float(rs.stop.latitude),
            "lng": float(rs.stop.longitude),
            "order": rs.stop_order,
            "morning_eta": str(rs.morning_eta) if rs.morning_eta else None,
        }
        for rs in route_stops
    ]

    assignment = (
        RouteAssignment.objects
        .filter(route=route, is_active=True)
        .select_related('bus', 'driver')
        .first()
    )

    bus_info = {
        "bus_number": assignment.bus.bus_number,
        "driver_name": assignment.driver.name,
        "driver_phone": assignment.driver.phone,
    } if assignment else None

    return Response({
        "route_name": route.name,
        "stops": stops,
        "bus": bus_info,
        "student_stop_name": registration.stop.name,
    })


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
            subject="FAST Transport — Payment OTP",
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

        FeeVerification.objects.get_or_create(
            student=profile,
            semester=registration.semester,
            defaults={
                "amount": challan.amount,
                "challan_number": f"CHN-{challan.id:04d}",
            },
        )

        admin_users = User.objects.filter(is_staff=True)
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


# Map each route to its tracker token
BUS_TRACKER_TOKENS = {
    # Route assignment ID → iTecknologi token
    # You'll fill these in once you have tokens for each bus
    "default": "YgIw0Z",
}

ITECKNOLOGI_BASE = "https://iot.itecknologi.com/fleet"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def live_bus_location(request):
    """
    Returns real GPS coordinates for the student's assigned bus.
    Falls back to last known position if GPS is stale.
    """
    from .models import SeatAllocation, SemesterRegistration, RouteAssignment
    
    # Get student's active registration
    try:
        profile = request.user.studentprofile
        registration = SemesterRegistration.objects.filter(
            student=profile,
            semester__is_active=True
        ).select_related("route", "stop").first()
        
        if not registration:
            return Response({"detail": "No active registration"}, status=404)
        
        # Find route assignment (which bus is on this route)
        assignment = RouteAssignment.objects.filter(
            route=registration.route,
            semester__is_active=True,
            is_active=True
        ).select_related("bus").first()
        
        if not assignment:
            return Response({"detail": "No active bus assignment"}, status=404)
        
        # Get the tracker token for this bus
        # You can store this on the Bus model (see Step 3)
        token = getattr(assignment.bus, 'tracker_token', None) or BUS_TRACKER_TOKENS["default"]
        
    except Exception as e:
        return Response({"detail": str(e)}, status=500)
    
    # Call iTecknologi API
    try:
        resp = req_lib.get(
        "https://iot.itecknologi.com/fleet/live_data_api_token.php",
        params={"token": token},
        timeout=5
        )
        resp.raise_for_status()
        gps_data = resp.json()

        if not gps_data.get("status"):
            return Response({"detail": "Tracker returned no data"}, status=503)

        d = gps_data["data"]

        return Response({
            "lat":         d["lat"],
            "lng":         d["lng"],
            "speed":       d["speed"],
            "heading":     d["angle"],           # "angle" → heading
            "ignition":    d["ign_value"] == 1,  # 0/1 int → bool
            "timestamp":   d["message"],
            "vehicle":     gps_data.get("vehicle"),   # "JE-5354"
            "model":       gps_data.get("model"),     # "MINI BUS"
            "bus_number":  assignment.bus.bus_number,
            "driver_name": assignment.driver.name,
            "route_name":  registration.route.name,
            "student_stop": registration.stop.name,
        })
    
    except req_lib.Timeout:
        return Response({"detail": "GPS tracker timeout"}, status=503)
    except Exception as e:
        return Response({"detail": f"Tracker error: {str(e)}"}, status=502)


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

    # Header
    story.append(Paragraph("FAST NUCES", title_style))
    story.append(Paragraph("Transport Management System", subtitle_style))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("STUDENT TRANSPORT CARD", ParagraphStyle(
        "cardtitle", parent=styles["Heading1"], alignment=TA_CENTER,
        fontSize=16, textColor=colors.HexColor("#1a3c5e")
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
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3c5e")),
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
        ("BOX", (0, 0), (-1, -1), 1.5, colors.HexColor("#1a3c5e")),
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


