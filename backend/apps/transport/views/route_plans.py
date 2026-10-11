import json
import re

from django.http import HttpResponse
from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .. import route_plans
from ..models import RoutePlan
from ..permissions import IsAdmin
from ..serializers import RoutePlanSerializer


class RoutePlanViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Stored route plans. New plans come from import or duplicate, never a bare POST."""

    queryset = RoutePlan.objects.all()
    serializer_class = RoutePlanSerializer
    permission_classes = [IsAdmin]
    pagination_class = None  # a handful of plans; the page needs all of them to find the active one

    def retrieve(self, request, *args, **kwargs):
        plan = self.get_object()
        return Response({**self.get_serializer(plan).data, "routes": route_plans.plan_snapshot(plan)["routes"]})

    def perform_destroy(self, instance):
        if instance.is_active:
            raise ValidationError({"detail": "The active plan cannot be deleted. Activate another plan first."})
        instance.delete()

    def _create(self, request, name, description, data):
        plan = RoutePlan.objects.create(
            name=route_plans.free_name(name), description=description, data=data, created_by=request.user,
        )
        return Response(self.get_serializer(plan).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        """Copy a plan. On the active plan this saves the current live routes as a new plan."""
        plan = self.get_object()
        name = str(request.data.get("name") or "").strip() or f"{plan.name} copy"
        return self._create(request, name, plan.description, route_plans.plan_snapshot(plan))

    @action(detail=False, methods=["post"], url_path="import")
    def import_file(self, request):
        """Store an uploaded CSV/JSON file as a new inactive plan. Live routes are not touched."""
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": ["Choose an Excel, CSV or JSON file."]})
        if not upload.name.lower().endswith((".xlsx", ".csv", ".json")):
            raise ValidationError({"file": ["Only .xlsx, .csv or .json files are supported."]})
        if upload.size > route_plans.MAX_FILE_BYTES:
            raise ValidationError({"file": ["The file must be smaller than 10 MB."]})
        try:
            snapshot, meta = route_plans.parse_plan_file(upload.name, upload.read())
        except route_plans.PlanError as exc:
            raise ValidationError({"file": exc.errors})
        name = str(request.data.get("name") or "").strip() or meta["name"] or upload.name.rsplit(".", 1)[0]
        with transaction.atomic():
            response = self._create(request, name, meta["description"], snapshot)
            # The plan stays inactive, but its stops exist now so the page can fill in their addresses.
            response.data["stops"] = route_plans.create_plan_stops(snapshot)
        return response

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        # `?file=`, because DRF reserves `?format=` for content negotiation.
        plan = self.get_object()
        kind = "json" if request.query_params.get("file") == "json" else "csv"
        content = route_plans.export_json(plan) if kind == "json" else route_plans.export_csv(plan)
        slug = re.sub(r"[^a-z0-9]+", "-", plan.name.lower()).strip("-") or "plan"
        response = HttpResponse(content, content_type="application/json" if kind == "json" else "text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="route_plan_{slug}.{kind}"'
        return response

    @staticmethod
    def _bus_routes(raw):
        """{assignment id: new route name} picked in the activation dialog."""
        if isinstance(raw, str):
            try:
                raw = json.loads(raw or "{}")
            except ValueError:
                raise ValidationError({"bus_routes": "Must be a JSON object."})
        if not isinstance(raw, dict):
            raise ValidationError({"bus_routes": "Must be a JSON object."})
        return {str(key): str(value or "") for key, value in raw.items()}

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        bus_routes = self._bus_routes(request.query_params.get("bus_routes") or "{}")
        return Response(route_plans.preview(self.get_object(), bus_routes))

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        try:
            report = route_plans.activate(self.get_object(), request.user, self._bus_routes(request.data.get("bus_routes") or {}))
        except route_plans.PlanError as exc:
            raise ValidationError({"detail": exc.errors})
        return Response(report)

    @action(detail=False, methods=["get"])
    def attention(self, request):
        """Students currently registered on a route or stop that is not being served."""
        return Response(route_plans.find_orphans(*route_plans.live_coverage()))
