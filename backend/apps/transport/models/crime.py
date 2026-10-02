from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
import random
import string

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
