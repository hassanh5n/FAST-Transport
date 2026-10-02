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

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def cancel(self, request, pk=None):
        """
        Withdraw a registration — from a held seat or from the queue.

        Releasing a seat fires the promotion receiver, so the next student in
        the queue is seated immediately rather than waiting for an admin.
        """
        profile = StudentProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response({"detail": "Student profile not found."}, status=404)

        registration = TransportRegistration.objects.filter(pk=pk, student=profile).first()
        if not registration:
            return Response({"detail": "Registration not found."}, status=404)

        if registration.status == "Cancelled":
            return Response({"detail": "This registration is already cancelled."}, status=400)

        challan = Challan.objects.filter(registration=registration).first()
        if challan and challan.status == "paid":
            return Response(
                {"detail": "This registration is already paid. Please contact the "
                           "transport office to cancel and arrange a refund."},
                status=400,
            )

        semester_registration = SemesterRegistration.objects.filter(
            student=profile, semester=registration.semester
        ).first()

        released = False
        if semester_registration:
            released = release_seat(semester_registration)

            entry = Waitlist.objects.filter(registration=semester_registration).first()
            if entry:
                route, semester = semester_registration.route, semester_registration.semester
                entry.delete()
                reindex_waitlist(route, semester)

            semester_registration.status = "Cancelled"
            semester_registration.save(update_fields=["status", "updated_at"])

        if challan and challan.status != "paid":
            challan.delete()

        registration.status = "Cancelled"
        registration.save(update_fields=["status"])

        Notification.objects.create(
            user=request.user,
            title="Registration cancelled",
            message=(
                "Your transport registration has been cancelled. "
                + ("Your seat has been released to the next student in the queue."
                   if released else "You have been removed from the waiting list.")
            ),
            type="info",
        )

        return Response({
            "detail": "Registration cancelled.",
            "seat_released": released,
        })

    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated],
            url_path="waitlist-status")
    def waitlist_status(self, request):
        """Live queue position for the logged-in student, plus any offer clock."""
        profile = StudentProfile.objects.filter(user=request.user).first()
        if not profile:
            return Response({"detail": "Student profile not found."}, status=404)

        semester = Semester.objects.filter(is_active=True).first()
        registration = SemesterRegistration.objects.filter(
            student=profile, semester=semester
        ).select_related("route").first() if semester else None

        if not registration:
            return Response({"waitlist": None, "seat": None})

        seat = SeatAllocation.objects.select_related(
            "route_assignment__bus"
        ).filter(registration=registration).first()

        transport_registration = TransportRegistration.objects.filter(
            student=profile, semester=semester
        ).order_by("-created_at").first()
        challan = (
            Challan.objects.filter(registration=transport_registration).first()
            if transport_registration else None
        )

        return Response({
            # The cancel endpoint acts on the TransportRegistration, so the
            # client needs its id, not the SemesterRegistration's.
            "registration_id": transport_registration.id if transport_registration else None,
            "route": registration.route.name if registration.route else None,
            "status": transport_registration.status if transport_registration else None,
            "waitlist": waitlist_summary(registration),
            "seat": {
                "seat_number": seat.seat_number,
                "bus": seat.route_assignment.bus.bus_number,
            } if seat else None,
            "payment_due_at": challan.payment_due_at if challan else None,
            "challan_status": challan.status if challan else None,
            "offer_hours": SEAT_OFFER_HOURS,
        })

    def perform_create(self, serializer):
        """
        Register a student: hold a seat first, and only then issue a challan.

        The previous flow created a challan unconditionally, so a student could
        pay in full and then be told the route was full — with no refund path
        and no way out. Now a full route means a queue place and no charge; the
        challan is issued when a seat actually exists.
        """
        profile = StudentProfile.objects.get(user=self.request.user)

        stop = serializer.validated_data["stop"]
        semester = serializer.validated_data["semester"]
        route_stop = serializer.validated_data.pop("selected_route_stop", None)

        if route_stop is None:
            # Students choose a stop; the route is derived. Where a stop is
            # served by several routes we pick one that can seat them rather
            # than rejecting the request.
            route_stop, _has_seat = pick_route_for_stop(stop, semester)
            if route_stop is None:
                raise ValidationError({"stop_id": "No active route currently serves this stop."})

        if not route_stop.route.is_active or route_stop.route.status != "published":
            raise ValidationError("No route found for this stop")
        if not semester.accepts_registrations:
            raise ValidationError({"semester_id": (
                "The registration deadline for this semester has passed."
                if semester.deadline_passed
                else "Registration is not open for this semester."
            )})

        registration = serializer.save(
            student=profile,
            route=route_stop.route,
            semester=semester,
            status="Pending",
        )

        semester_registration, _ = SemesterRegistration.objects.update_or_create(
            student=profile,
            semester=semester,
            defaults={
                "route": route_stop.route,
                "stop": stop,
                "status": "Pending",
            },
        )

        # Already paid in a previous flow? Honour it rather than re-charging.
        fee = FeeVerification.objects.filter(
            student=profile, semester=semester, is_verified=True
        ).first()

        result = allocate_seat_for_student(semester_registration)

        if result in ("Seat Allocated", "Seat already allocated"):
            registration.status = "Approved" if fee else "Seat Held"
            registration.save(update_fields=["status"])
            if not fee:
                issue_challan(registration)
        elif result == "Added to Waitlist":
            # No challan: the student is queued and has not been charged.
            registration.status = "Waitlisted"
            registration.save(update_fields=["status"])
        else:
            # No active bus yet — leave pending for an admin to resolve, and
            # still do not charge.
            registration.status = "Pending"
            registration.save(update_fields=["status"])

class SeatAllocationViewSet(viewsets.ModelViewSet):
    queryset = SeatAllocation.objects.all()
    serializer_class = SeatAllocationSerializer
    permission_classes = [IsAdmin] # Only Admin full access

    # Raw create/update wrote a SeatAllocation with whatever seat_number was
    # posted: no capacity check, no lock, no waitlist bookkeeping. That is how
    # rows numbered outside a bus's capacity appeared, which in turn let the
    # seat picker hand the same bus out again. Seats are now created and moved
    # only through the assign / reassign actions below, which lock the
    # assignment and respect capacity. Deletion stays, since releasing a seat
    # is safe and promotes the next student on the waitlist.
    _MANUAL_WRITE_DETAIL = (
        "Seats cannot be written directly. Use /seat-allocations/assign/ to "
        "seat a student and /seat-allocations/reassign/ to move one, so that "
        "bus capacity and the waitlist stay correct."
    )

    def create(self, request, *args, **kwargs):
        return Response({"detail": self._MANUAL_WRITE_DETAIL}, status=405)

    def update(self, request, *args, **kwargs):
        return Response({"detail": self._MANUAL_WRITE_DETAIL}, status=405)

    def partial_update(self, request, *args, **kwargs):
        return Response({"detail": self._MANUAL_WRITE_DETAIL}, status=405)

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
                    "student_name": f"{registration.student.user.first_name} {registration.student.user.last_name}".strip() or registration.student.user.username,
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
                    "student_name": f"{registration.student.user.first_name} {registration.student.user.last_name}".strip() or registration.student.user.username,
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
        # Scope on staff status, not group membership: a student who was never
        # added to the "Student" group would otherwise read every other
        # student's queue entry.
        user = self.request.user
        base = Waitlist.objects.select_related(
            "registration__student__user",
            "registration__route",
            "registration__stop",
        )
        if user.is_staff:
            return base
        profile = StudentProfile.objects.filter(user=user).first()
        if not profile:
            return Waitlist.objects.none()
        return base.filter(registration__student=profile)

    @action(detail=False, methods=["get"], permission_classes=[IsAdmin])
    def overview(self, request):
        """
        The waiting list grouped by route, with each route's seat position.

        Queues are per route: position 1 on 6B is a different person from
        position 1 on 5B, so they are never shown as one combined list.
        """
        semester = Semester.objects.filter(is_active=True).first()
        if not semester:
            return Response({"semester": None, "routes": []})

        entries = (
            Waitlist.objects.filter(
                registration__semester=semester,
                status__in=["waiting", "offered"],
            )
            .select_related(
                "registration__student__user",
                "registration__route",
                "registration__stop",
            )
            .order_by("registration__route__name", "position", "added_at")
        )

        grouped = {}
        for entry in entries:
            registration = entry.registration
            route = registration.route
            if route is None:
                continue
            grouped.setdefault(route.id, {"route": route, "entries": []})
            grouped[route.id]["entries"].append(entry)

        # Include routes with free seats but nobody queued, so an admin can see
        # capacity sitting idle.
        for assignment in RouteAssignment.objects.filter(
            semester=semester, is_active=True
        ).select_related("route"):
            grouped.setdefault(assignment.route_id,
                               {"route": assignment.route, "entries": []})

        routes = []
        for data in grouped.values():
            route = data["route"]
            assignments = RouteAssignment.objects.filter(
                route=route, semester=semester, is_active=True
            ).select_related("bus", "driver")

            capacity = sum(a.bus.capacity for a in assignments)
            occupied = SeatAllocation.objects.filter(
                route_assignment__in=assignments
            ).count()
            free = max(capacity - occupied, 0)

            routes.append({
                "route_id": route.id,
                "route_name": route.name,
                "buses": [a.bus.bus_number for a in assignments],
                "drivers": [a.driver.name for a in assignments],
                "capacity": capacity,
                "occupied": occupied,
                "free_seats": free,
                "queue_length": len(data["entries"]),
                "queue": [
                    {
                        "id": entry.id,
                        "position": entry.position,
                        "status": entry.status,
                        "roll_number": entry.registration.student.roll_number,
                        "name": (
                            f"{entry.registration.student.user.first_name} "
                            f"{entry.registration.student.user.last_name}"
                        ).strip() or entry.registration.student.user.username,
                        "email": entry.registration.student.user.email,
                        "phone": entry.registration.student.phone,
                        "stop": entry.registration.stop.name if entry.registration.stop else None,
                        "added_at": entry.added_at,
                        "offer_expires_at": entry.offer_expires_at,
                    }
                    for entry in data["entries"]
                ],
            })

        routes.sort(key=lambda item: item["route_name"])
        return Response({"semester": str(semester), "routes": routes})

    @action(detail=False, methods=["post"], permission_classes=[IsAdmin],
            url_path="fill-empty-seats")
    def fill_empty_seats(self, request):
        """
        Seat as many queued students as there is room for.

        Promotion normally happens automatically when a seat is released, but
        capacity can also appear without any seat being freed — an admin raises
        a bus's capacity, or adds a second bus to a route. Nothing deletes a
        SeatAllocation in those cases, so no signal fires. This closes that gap.
        """
        semester = Semester.objects.filter(is_active=True).first()
        if not semester:
            return Response({"detail": "No active semester."}, status=400)

        route_id = request.data.get("route_id")
        routes = Route.objects.filter(is_active=True)
        if route_id:
            routes = routes.filter(pk=route_id)

        promoted = []
        for route in routes:
            # Keep promoting while seats remain and the queue is not empty.
            while True:
                registration = promote_next_from_waitlist(route, semester)
                if registration is None:
                    break
                promoted.append({
                    "route": route.name,
                    "roll_number": registration.student.roll_number,
                })

        return Response({
            "detail": (
                f"Seated {len(promoted)} student(s) from the waiting list."
                if promoted else
                "No students could be seated — no free seats, or the queues are empty."
            ),
            "promoted": promoted,
        })


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
 
        # Every bus on the requested route, emptiest first — a route may carry
        # more than one, and the second could have the only free seat.
        from ..seatallocation import (
            _get_next_available_seat_number,
            seats_free_on_assignment,
        )

        new_assignments = list(
            RouteAssignment.objects.filter(
                route=new_route,
                semester=semester,
                is_active=True,
                bus__is_active=True,
            ).select_related("bus")
        )
        if not new_assignments:
            return Response({"detail": "No active bus assignment for the requested route."}, status=400)

        new_assignments.sort(key=lambda a: seats_free_on_assignment(a), reverse=True)
        if seats_free_on_assignment(new_assignments[0]) <= 0:
            return Response({"detail": "No seats available on the requested route."}, status=400)

        available_seat = None
        new_assignment = None

        # The seat is chosen inside the transaction, under a row lock on the
        # assignment. Choosing it beforehand let two approvals read the same
        # free seat and both write it.
        with transaction.atomic():
            locked_assignments = {
                item.id: item
                for item in RouteAssignment.objects.select_for_update()
                .select_related("bus")
                .filter(id__in=[a.id for a in new_assignments])
            }

            for candidate in new_assignments:
                locked = locked_assignments.get(candidate.id, candidate)
                seat_number = _get_next_available_seat_number(locked)
                if seat_number is not None:
                    new_assignment = locked
                    available_seat = seat_number
                    break

            if available_seat is None:
                return Response(
                    {"detail": "No seats available on the requested route."},
                    status=400,
                )

            # 1. Free old seat allocation. The post_delete receiver offers that
            #    seat to the old route's queue once this commits, which is what
            #    should happen — the student is leaving that route for good.
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
