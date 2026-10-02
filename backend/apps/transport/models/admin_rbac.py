from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
import random
import string

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
