from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
import random
import string

from .core import Route, RouteAssignment, Semester, Stop, StudentProfile

class SemesterRegistration(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    route = models.ForeignKey(Route, on_delete=models.CASCADE)
    stop = models.ForeignKey(Stop, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default="Pending")
    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student.roll_number} - {self.semester.name}"
    
class TransportRegistration(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        # A seat is physically held for this student, but the fee is unpaid and
        # the hold expires. This is the state between allocation and payment.
        ("Seat Held", "Seat Held"),
        ("Approved", "Approved"),
        ("payment_submitted", "Payment Submitted"),
        # No seat was available; the student is queued and has NOT been charged.
        ("Waitlisted", "Waitlisted"),
        ("Cancelled", "Cancelled"),
        ("Rejected", "Rejected"),
    ]

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    stop = models.ForeignKey(Stop, on_delete=models.CASCADE)

    # Route will be auto-assigned
    route = models.ForeignKey(Route, on_delete=models.SET_NULL, null=True, blank=True)

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="Pending")

    fee_amount = models.DecimalField(max_digits=8, decimal_places=0, default=5000)
    is_paid = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

class SeatAllocation(models.Model):
    registration = models.ForeignKey(SemesterRegistration, on_delete=models.CASCADE)
    route_assignment = models.ForeignKey(RouteAssignment, on_delete=models.CASCADE)
    seat_number = models.IntegerField(default=1)
    allocated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # Two students can never hold the same seat on the same bus, and a
            # student can never hold two seats. Application code already checks
            # both, but only the database can enforce them against concurrent
            # requests and against rows written by other code paths.
            models.UniqueConstraint(
                fields=["route_assignment", "seat_number"],
                name="uniq_seat_number_per_assignment",
            ),
            models.UniqueConstraint(
                fields=["registration"],
                name="uniq_seat_per_registration",
            ),
        ]

    def __str__(self):
        return f"Seat {self.seat_number} - {self.registration.student.roll_number}"

class Waitlist(models.Model):
    """
    A queue of students waiting for a seat on a route, for one semester.

    Entries are never charged. A student only receives a challan once they are
    promoted and a seat is actually held for them, which is what stops anyone
    paying for a seat that may never exist.
    """

    STATUS_CHOICES = [
        ("waiting",   "Waiting"),
        # Promoted: a seat is held and a challan issued, pending payment.
        ("offered",   "Offered"),
        # The offer lapsed unpaid and the seat moved on.
        ("expired",   "Expired"),
        ("cancelled", "Cancelled"),
    ]

    registration = models.OneToOneField(SemesterRegistration, on_delete=models.CASCADE)
    position = models.IntegerField(default=1)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="waiting")
    offered_at = models.DateTimeField(null=True, blank=True)
    offer_expires_at = models.DateTimeField(null=True, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "added_at"]

    def __str__(self):
        return f"{self.registration.student.roll_number} - Position {self.position}"

class RouteChangeRequest(models.Model):
    registration = models.ForeignKey(SemesterRegistration, on_delete=models.CASCADE)
    current_route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="current_routes")
    requested_route = models.ForeignKey(Route, on_delete=models.SET_NULL, related_name="requested_routes", null=True, blank=True)
    requested_stop = models.ForeignKey(Stop, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default="Pending")
    admin_remarks = models.TextField(default="N/A")
    requested_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.registration.student.roll_number} - {self.current_route.name} -> {self.requested_route.name}"
