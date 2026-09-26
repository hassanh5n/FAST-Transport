from django.contrib import admin
from .models import Bus, BusLocationPing, Incident


@admin.register(Bus)
class BusAdmin(admin.ModelAdmin):
    list_display = ["bus_number", "capacity", "is_active", "is_off_route", "last_off_route_alert_at"]


@admin.register(BusLocationPing)
class BusLocationPingAdmin(admin.ModelAdmin):
    list_display = ["bus", "latitude", "longitude", "distance_from_route_m", "recorded_at"]
    readonly_fields = ["distance_from_route_m"]


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ["id", "incident_type", "severity", "status", "reported_by", "occurred_at", "created_at"]
    list_filter = ["status", "severity", "incident_type"]
    search_fields = ["reported_by__username", "description"]

from .models import AdminRole, AdminProfile, AdminActivityLog


@admin.register(AdminRole)
class AdminRoleAdmin(admin.ModelAdmin):
    list_display = ["name", "is_system", "updated_at"]


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "is_super_admin", "role", "created_by", "created_at"]
    list_filter = ["is_super_admin", "role"]


@admin.register(AdminActivityLog)
class AdminActivityLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "actor_username", "action", "module", "model_name", "object_repr"]
    list_filter = ["action", "module"]
    search_fields = ["actor_username", "description", "object_repr"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False  # the log is append-only
