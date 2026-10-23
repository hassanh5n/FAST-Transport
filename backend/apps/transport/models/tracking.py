from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
import random
import string

from .core import Bus

 
class BusLocationPing(models.Model):
    bus = models.ForeignKey(Bus, on_delete=models.CASCADE, related_name="location_pings")
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    distance_from_route_m = models.FloatField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # The live fleet reads each bus's latest ping on every poll; without this the
        # lookup scans every ping the bus ever sent, and drivers ping every few seconds.
        indexes = [models.Index(fields=["bus", "-recorded_at"], name="ping_bus_latest_idx")]

    def __str__(self):
        return f"{self.bus.bus_number} @ {self.recorded_at}"
