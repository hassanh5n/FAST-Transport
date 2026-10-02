from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
import random
import string

from .core import Semester, StudentProfile

class FeeVerification(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=0, default=0.0)
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    challan_number = models.CharField(max_length=50, default="N/A")
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.roll_number} - {self.semester.name}"

class Challan(models.Model):
    registration = models.OneToOneField(
        "TransportRegistration",
        on_delete=models.CASCADE,
        related_name="challan"
    )
    student = models.ForeignKey("StudentProfile", on_delete=models.CASCADE)

    amount = models.DecimalField(max_digits=10, decimal_places=0)

    status = models.CharField(
        max_length=20,
        choices=[
            ("unpaid", "Unpaid"),
            ("paid", "Paid"),
        ],
        default="unpaid"
    )

    # A challan is only issued once a seat is actually held, and that hold is
    # not open-ended: miss this deadline and the seat passes to the next
    # student in the queue.
    payment_due_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_expired(self):
        return (
            self.status != "paid"
            and self.payment_due_at is not None
            and timezone.now() > self.payment_due_at
        )

    def __str__(self):
        return f"Challan {self.id} - {self.student}"
