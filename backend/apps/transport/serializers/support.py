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

from .core import SemesterSerializer, UserSerializer
from .routes import RouteSerializer

class ComplaintSerializer(serializers.ModelSerializer):
    submitted_by = UserSerializer(read_only=True)
    semester = SemesterSerializer(read_only=True)
    route = RouteSerializer(read_only=True)
    resolved_by = UserSerializer(read_only=True)

    class Meta:
        model = Complaint
        fields = '__all__'
        read_only_fields = ['created_at', 'resolved_at']


class NotificationSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['created_at']


class IncidentSerializer(serializers.ModelSerializer):
    reported_by  = UserSerializer(read_only=True)
    reviewed_by  = UserSerializer(read_only=True)
    incident_type_display = serializers.CharField(source="get_incident_type_display", read_only=True)
    severity_display      = serializers.CharField(source="get_severity_display",      read_only=True)

    class Meta:
        model  = Incident
        fields = [
            "id",
            "reported_by",
            "incident_type",
            "incident_type_display",
            "severity",
            "severity_display",
            "latitude",
            "longitude",
            "radius_meters",
            "description",
            "status",
            "admin_notes",
            "reviewed_by",
            "reviewed_at",
            "created_at",
            "occurred_at",
            "expires_at",
        ]
        read_only_fields = [
            "reported_by", "status", "admin_notes",
            "reviewed_by", "reviewed_at", "created_at",
        ]

    def validate(self, attrs):
        latitude = attrs.get("latitude")
        longitude = attrs.get("longitude")
        radius_meters = attrs.get("radius_meters")

        if latitude is not None and not -90 <= latitude <= 90:
            raise serializers.ValidationError({"latitude": "Latitude must be between -90 and 90."})
        if longitude is not None and not -180 <= longitude <= 180:
            raise serializers.ValidationError({"longitude": "Longitude must be between -180 and 180."})
        if radius_meters is not None and not 50 <= radius_meters <= 2000:
            raise serializers.ValidationError({"radius_meters": "Radius must be between 50 and 2,000 metres."})

        occurred_at = attrs.get("occurred_at")
        if occurred_at is not None and occurred_at > timezone.now():
            raise serializers.ValidationError({"occurred_at": "Occurrence time cannot be in the future."})
        return attrs
