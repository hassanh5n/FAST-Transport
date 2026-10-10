from django.contrib.auth.models import User
from django.db import models


class RoutePlan(models.Model):
    """
    A named, complete set of routes with their ordered stops and ETAs.

    Exactly one plan is active. The active plan IS the live Route/RouteStop
    tables, so its `data` is only refreshed when another plan replaces it; read
    it through route_plans.plan_snapshot(). Inactive plans live in `data` and
    are written onto the live tables by route_plans.activate().
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, default="")
    data = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "name"]
        constraints = [
            # Only the database can guarantee a single active plan against
            # two admins activating at the same moment.
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="one_active_route_plan",
            ),
        ]

    def __str__(self):
        return self.name
