from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
import random
import string

from .core import Route, Semester

class Complaint(models.Model):
    submitted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="complaints_submitted")
    semester = models.ForeignKey(Semester, on_delete=models.SET_NULL, null=True, blank=True)
    route = models.ForeignKey(Route, on_delete=models.SET_NULL, null=True, blank=True)
    category = models.CharField(max_length=20, default="General")
    subject = models.CharField(max_length=200, default="N/A")
    description = models.TextField(default="N/A")
    status = models.CharField(max_length=15, default="Pending")
    priority = models.CharField(max_length=10, default="Normal")
    admin_response = models.TextField(default="N/A")
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="complaints_resolved")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.subject} ({self.submitted_by.username})"


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('alert', 'Alert'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200, default="N/A")
    message = models.TextField(default="N/A")
    type = models.CharField(max_length=15, choices=NOTIFICATION_TYPES, default='info')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.title}"

class OTPVerification(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="otp_verification")
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
 
    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at
 
    def __str__(self):
        return f"OTP for {self.user.username}"


class Incident(models.Model):
    INCIDENT_TYPES = [
        ("traffic_jam",   "Traffic Jam"),
        ("robbery",       "Robbery"),
        ("road_closure",  "Road Closure"),
        ("flooding",      "Flooding"),
        ("accident",      "Accident"),
        ("other",         "Other"),
    ]

    SEVERITY_CHOICES = [
        ("low",    "Low"),
        ("medium", "Medium"),
        ("high",   "High"),
    ]

    STATUS_CHOICES = [
        ("Pending",  "Pending"),
        ("Approved", "Approved"),
        ("Rejected", "Rejected"),
    ]

    reported_by   = models.ForeignKey(User, on_delete=models.CASCADE, related_name="incidents_reported")
    incident_type = models.CharField(max_length=20, choices=INCIDENT_TYPES, default="other")
    severity      = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default="low")
    latitude      = models.DecimalField(max_digits=9, decimal_places=6)
    longitude     = models.DecimalField(max_digits=9, decimal_places=6)
    radius_meters = models.IntegerField(default=200)
    description   = models.TextField(blank=True, default="")

    status        = models.CharField(max_length=10, choices=STATUS_CHOICES, default="Pending")
    admin_notes   = models.TextField(blank=True, default="")
    reviewed_by   = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="incidents_reviewed")
    reviewed_at   = models.DateTimeField(null=True, blank=True)

    created_at    = models.DateTimeField(auto_now_add=True)
    # This is intentionally distinct from created_at: a student may report an
    # incident some time after it happened.
    occurred_at   = models.DateTimeField(default=timezone.now)
    expires_at    = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_incident_type_display()} ({self.severity}) by {self.reported_by.username}"
