from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
import random
import string

class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    roll_number = models.CharField(max_length=20, unique=True)
    department = models.CharField(max_length=10, default="N/A")
    batch = models.CharField(max_length=10, default="N/A")
    phone = models.CharField(max_length=20, default="N/A")
    address = models.TextField(default="N/A")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.roll_number} ({self.user.username})"


class Semester(models.Model):
    name = models.CharField(max_length=50, default="N/A")
    year = models.IntegerField(default=2026)
    term = models.CharField(max_length=10, default="N/A")
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=False)
    registration_open = models.BooleanField(default=False)
    # Admin-set cut-off. New registrations stop at this moment, and it is the
    # normal payment deadline for a held seat. Null means no deadline, in which
    # case registration_open is the only gate.
    registration_deadline = models.DateTimeField(null=True, blank=True)
    # The transport fee for this semester, set by an admin. Single source of
    # truth: challans read it from here instead of each caller hardcoding an
    # amount, which previously left 45000 in one place and 5000 in another.
    transport_fee = models.DecimalField(max_digits=10, decimal_places=0, default=5000)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def deadline_passed(self):
        return (
            self.registration_deadline is not None
            and timezone.now() > self.registration_deadline
        )

    @property
    def accepts_registrations(self):
        """Open for new registrations: the flag is on AND the date has not passed."""
        return self.is_active and self.registration_open and not self.deadline_passed

    def __str__(self):
        # Semester names are entered by hand and often already contain the year
        # ("Spring 2026"), which would otherwise render as "Spring 2026 2026".
        # Only append the year when the name does not already carry it.
        name = (self.name or "").strip()
        if not name:
            return str(self.year)
        return name if str(self.year) in name else f"{name} {self.year}"


class Route(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]

    name = models.CharField(max_length=100, default="N/A")
    description = models.TextField(default="No description")
    is_active = models.BooleanField(default=True)
    # Cached road-following GeoJSON. Ordered RouteStop records remain the source
    # of truth, so a routing-provider outage never makes a route uneditable.
    geometry = models.JSONField(null=True, blank=True)
    geometry_updated_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="published")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Stop(models.Model):
    name = models.CharField(max_length=100, default="N/A")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, default=0.0)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, default=0.0)
    address = models.TextField(default="N/A")
    is_active = models.BooleanField(default=True)
    location_source = models.CharField(max_length=30, default="manual")
    location_accuracy_m = models.PositiveIntegerField(null=True, blank=True)
    provider_place_id = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class RouteStop(models.Model):
    route = models.ForeignKey(Route, on_delete=models.CASCADE)
    stop = models.ForeignKey(Stop, on_delete=models.CASCADE)
    stop_order = models.IntegerField(default=1)
    morning_eta = models.TimeField(null=True, blank=True)
    evening_eta = models.TimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.route.name} - {self.stop.name} ({self.stop_order})"

    class Meta:
        ordering = ["route_id", "stop_order"]
        constraints = [
            models.UniqueConstraint(fields=["route", "stop"], name="unique_stop_per_route"),
            models.UniqueConstraint(fields=["route", "stop_order"], name="unique_stop_order_per_route"),
            models.CheckConstraint(condition=models.Q(stop_order__gt=0), name="route_stop_order_positive"),
        ]

class Bus(models.Model):
    bus_number = models.CharField(max_length=20, default="N/A")
    capacity = models.IntegerField(default=0)
    model = models.CharField(max_length=100, default="N/A")
    tracker_token = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_off_route = models.BooleanField(default=False)              # <- new
    last_off_route_alert_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.bus_number

class Driver(models.Model):
    # Optional login, created by an admin. Null for drivers who never sign in.
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="driver_profile")
    name = models.CharField(max_length=150, default="N/A")
    cnic = models.CharField(max_length=15, default="N/A")
    license_no = models.CharField(max_length=30, default="N/A")
    phone = models.CharField(max_length=20, default="N/A")
    address = models.TextField(default="N/A")
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class RouteAssignment(models.Model):
    route = models.ForeignKey(Route, on_delete=models.CASCADE)
    bus = models.ForeignKey(Bus, on_delete=models.CASCADE)
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.route.name} - {self.bus.bus_number} - {self.driver.name}"

class MaintenanceSchedule(models.Model):
    bus = models.ForeignKey(Bus, on_delete=models.CASCADE)
    maintenance_type = models.CharField(max_length=50, default="General")
    description = models.TextField(default="N/A")
    scheduled_date = models.DateField(default=timezone.now)
    completed_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=15, default="Pending")
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.bus.bus_number} - {self.maintenance_type}"
