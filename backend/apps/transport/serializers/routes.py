from rest_framework import serializers
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from ..models import (
    Challan,
    StudentProfile,
    Semester,
    Route,
    Stop,
    RouteStop,
    Bus,
    Driver,
    RouteAssignment,
    SemesterRegistration,
    SeatAllocation,
    Waitlist,
    FeeVerification,
    Complaint,
    RouteChangeRequest,
    MaintenanceSchedule,
    Notification,
    TransportRegistration,
    BusLocationPing,
    Incident,
    CrimeRiskZone,
)

class CrimeRiskZoneSerializer(serializers.ModelSerializer):
    """Public, aggregated representation; raw external crime events stay server-side."""

    class Meta:
        model = CrimeRiskZone
        fields = [
            "zone_id", "geometry", "current_score", "current_level",
            "confidence", "source_updated_at", "algorithm_version",
        ]


class RouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Route
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class StopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stop
        fields = '__all__'
        read_only_fields = ['created_at']

    def validate(self, attrs):
        """Reject unusable active stop coordinates while preserving old inactive data."""
        latitude = attrs.get("latitude", getattr(self.instance, "latitude", None))
        longitude = attrs.get("longitude", getattr(self.instance, "longitude", None))
        is_active = attrs.get("is_active", getattr(self.instance, "is_active", True))

        if not is_active:
            return attrs
        if latitude is None or longitude is None:
            raise serializers.ValidationError("Active stops require latitude and longitude.")
        if not (-90 <= float(latitude) <= 90):
            raise serializers.ValidationError({"latitude": "Latitude must be between -90 and 90."})
        if not (-180 <= float(longitude) <= 180):
            raise serializers.ValidationError({"longitude": "Longitude must be between -180 and 180."})
        if float(latitude) == 0 and float(longitude) == 0:
            raise serializers.ValidationError("0,0 is not a valid active pickup stop.")
        return attrs


class RouteStopSerializer(serializers.ModelSerializer):
    route_name = serializers.CharField(source="route.name", read_only=True)
    stop_name = serializers.CharField(source="stop.name", read_only=True)

    route = serializers.PrimaryKeyRelatedField(queryset=Route.objects.all())
    stop = serializers.PrimaryKeyRelatedField(queryset=Stop.objects.all())
    bus_number = serializers.SerializerMethodField()
    driver_name = serializers.SerializerMethodField()
    driver_id = serializers.SerializerMethodField()

    class Meta:
        model = RouteStop
        fields = [
            "id",
            "route",
            "stop",
            "stop_order",
            "morning_eta",
            "evening_eta",
            "route_name",
            "stop_name",
            "bus_number",
            "driver_name",
            "driver_id",
        ]

    def get_bus_number(self, obj):
        assignment = obj.route.routeassignment_set.filter(is_active=True).first()
        if assignment and assignment.bus:
            return assignment.bus.bus_number
        return None


    def get_driver_name(self, obj):
        assignment = obj.route.routeassignment_set.filter(is_active=True).first()
        if assignment and assignment.driver:
            return assignment.driver.name
        return None
    def get_driver_id(self, obj):                      # ← add this method
        assignment = obj.route.routeassignment_set.filter(is_active=True).first()
        if assignment and assignment.driver:
            return assignment.driver.id
        return None
