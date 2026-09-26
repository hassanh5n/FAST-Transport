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
 
class BusLocationPing(models.Model):
    bus = models.ForeignKey(Bus, on_delete=models.CASCADE, related_name="location_pings")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    distance_from_route_m = models.FloatField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.bus.bus_number} @ {self.recorded_at}"


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


class ExternalCrimeEvent(models.Model):
    """Crime records imported from an external, licensed/official feed.

    This is deliberately separate from Incident: student reports are not a
    crime-risk input and never participate in the scoring pipeline.
    """

    source_event_id = models.CharField(max_length=180, unique=True)
    source_name = models.CharField(max_length=120, default="external")
    category = models.CharField(max_length=80)
    severity = models.PositiveSmallIntegerField(default=5)
    latitude = models.FloatField()
    longitude = models.FloatField()
    location_precision_m = models.PositiveIntegerField(null=True, blank=True)
    occurred_at = models.DateTimeField()
    source_updated_at = models.DateTimeField(null=True, blank=True)
    imported_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["occurred_at"]),
            models.Index(fields=["latitude", "longitude"]),
        ]

    def __str__(self):
        return f"{self.source_name}:{self.source_event_id} ({self.category})"


class CrimeRiskZone(models.Model):
    """Automatically generated map cell; no manually drawn boundaries."""

    zone_id = models.CharField(max_length=80, unique=True)
    geometry = models.JSONField()
    min_latitude = models.FloatField()
    min_longitude = models.FloatField()
    max_latitude = models.FloatField()
    max_longitude = models.FloatField()
    current_score = models.FloatField(null=True, blank=True)
    current_level = models.CharField(max_length=20, default="unclassified")
    confidence = models.CharField(max_length=20, default="none")
    source_updated_at = models.DateTimeField(null=True, blank=True)
    algorithm_version = models.CharField(max_length=30, default="v1")
    is_active = models.BooleanField(default=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["min_latitude", "max_latitude"]),
            models.Index(fields=["min_longitude", "max_longitude"]),
            models.Index(fields=["current_level"]),
        ]

    def __str__(self):
        return self.zone_id


class CrimeRiskSnapshot(models.Model):
    """Immutable-ish audit record for each automated scoring run."""

    zone = models.ForeignKey(CrimeRiskZone, on_delete=models.CASCADE, related_name="snapshots")
    period_days = models.PositiveIntegerField(default=90)
    score = models.FloatField(null=True, blank=True)
    level = models.CharField(max_length=20, default="unclassified")
    confidence = models.CharField(max_length=20, default="none")
    event_count = models.PositiveIntegerField(default=0)
    category_breakdown = models.JSONField(default=dict)
    algorithm_version = models.CharField(max_length=30, default="v1")
    calculated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["zone", "-calculated_at"])]


# ── Admin RBAC & activity log ────────────────────────────────────────────────
# See apps/transport/rbac.py for how these are enforced.

class AdminRole(models.Model):
    """A named permission preset, e.g. "Complaints Officer"."""
    name        = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=255, blank=True, default="")
    # {"complaints": "manage", "students": "view", ...}
    permissions = models.JSONField(default=dict, blank=True)
    is_system   = models.BooleanField(default=False)  # seeded preset
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class AdminProfile(models.Model):
    """Admin-side settings for a staff user."""
    user               = models.OneToOneField(User, on_delete=models.CASCADE, related_name="admin_profile")
    is_super_admin     = models.BooleanField(default=False)
    role               = models.ForeignKey(AdminRole, null=True, blank=True, on_delete=models.SET_NULL, related_name="admins")
    # Per-admin overrides on top of the role: {"complaints": "none" | "view" | "manage"}
    custom_permissions = models.JSONField(default=dict, blank=True)
    created_by         = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="admins_created")
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({'super admin' if self.is_super_admin else self.role or 'custom'})"


class AdminActivityLog(models.Model):
    ACTION_CHOICES = [
        ("create", "Create"),
        ("update", "Update"),
        ("delete", "Delete"),
        ("action", "Action"),
        ("login", "Login"),
    ]

    actor          = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="admin_activity")
    actor_username = models.CharField(max_length=150, blank=True, default="")  # kept if user is deleted
    action         = models.CharField(max_length=10, choices=ACTION_CHOICES)
    module         = models.CharField(max_length=40, blank=True, default="")
    model_name     = models.CharField(max_length=80, blank=True, default="")
    object_id      = models.CharField(max_length=64, blank=True, default="")
    object_repr    = models.CharField(max_length=255, blank=True, default="")
    description    = models.CharField(max_length=500, blank=True, default="")
    # {"field": {"from": old, "to": new}}
    changes        = models.JSONField(default=dict, blank=True)
    method         = models.CharField(max_length=10, blank=True, default="")
    path           = models.CharField(max_length=255, blank=True, default="")
    ip_address     = models.GenericIPAddressField(null=True, blank=True)
    request_id     = models.CharField(max_length=32, blank=True, default="", db_index=True)
    created_at     = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["actor", "-created_at"]),
            models.Index(fields=["module", "-created_at"]),
        ]

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.actor_username} {self.action} {self.model_name} {self.object_id}"
