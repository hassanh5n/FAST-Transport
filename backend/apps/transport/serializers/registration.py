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

from .core import SemesterSerializer, StudentProfileSerializer
from .fleet import RouteAssignmentSerializer
from .routes import RouteSerializer, StopSerializer

class SemesterRegistrationSerializer(serializers.ModelSerializer):
    student = StudentProfileSerializer(read_only=True)
    semester = SemesterSerializer(read_only=True)
    route = RouteSerializer(read_only=True)
    stop = StopSerializer(read_only=True)

    class Meta:
        model = SemesterRegistration
        fields = '__all__'
        read_only_fields = ['registered_at', 'updated_at']

class TransportRegistrationSerializer(serializers.ModelSerializer):
    route_name = serializers.CharField(source='route.name', read_only=True)
    stop_name = serializers.CharField(source='stop.name', read_only=True)
    semester_name = serializers.CharField(source='semester.name', read_only=True)

    stop_id = serializers.PrimaryKeyRelatedField(
        queryset=Stop.objects.all(),
        source="stop",
        write_only=True,
        required=False,
    )
    semester_id = serializers.PrimaryKeyRelatedField(
        queryset=Semester.objects.all(),
        source="semester",
        write_only=True
    )
    route_stop_id = serializers.PrimaryKeyRelatedField(
        queryset=RouteStop.objects.select_related("route", "stop"),
        source="route_stop",
        write_only=True,
        required=False,
    )
    semester = serializers.PrimaryKeyRelatedField(read_only=True)
    stop = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = TransportRegistration
        fields = [
            "id",
            "semester_id", "stop_id", "route_stop_id",
            "semester", "stop",
            "semester_name", "stop_name", "route_name",
            "status", "fee_amount", "is_paid", "created_at",
        ]
        read_only_fields = ["student", "route", "created_at"]

    def validate(self, attrs):
        route_stop = attrs.pop("route_stop", None)
        stop = attrs.get("stop")
        if route_stop:
            if stop and stop.pk != route_stop.stop_id:
                raise serializers.ValidationError({"route_stop_id": "The selected route stop does not match stop_id."})
            attrs["stop"] = route_stop.stop
            attrs["selected_route_stop"] = route_stop
        elif not stop:
            raise serializers.ValidationError({"route_stop_id": "Select a route stop on the map."})
        return attrs

class SeatAllocationSerializer(serializers.ModelSerializer):
    registration = SemesterRegistrationSerializer(read_only=True)
    route_assignment = RouteAssignmentSerializer(read_only=True)

    class Meta:
        model = SeatAllocation
        fields = '__all__'
        read_only_fields = ['allocated_at']


class WaitlistSerializer(serializers.ModelSerializer):
    registration = SemesterRegistrationSerializer(read_only=True)
    student_name = serializers.SerializerMethodField()
    roll_number = serializers.CharField(
        source="registration.student.roll_number", read_only=True)
    route_name = serializers.CharField(
        source="registration.route.name", read_only=True)
    stop_name = serializers.CharField(
        source="registration.stop.name", read_only=True)

    class Meta:
        model = Waitlist
        fields = '__all__'
        read_only_fields = ['added_at', 'offered_at', 'offer_expires_at']

    def get_student_name(self, obj):
        user = obj.registration.student.user
        return f"{user.first_name} {user.last_name}".strip() or user.username


class RouteChangeRequestSerializer(serializers.ModelSerializer):
    # Read (nested, for responses)
    registration = SemesterRegistrationSerializer(read_only=True)
    current_route = RouteSerializer(read_only=True)
    requested_route = RouteSerializer(read_only=True)
    requested_stop = StopSerializer(read_only=True)
 
    # Write — only stop ID, route is auto-determined
    requested_stop_id = serializers.PrimaryKeyRelatedField(
        queryset=Stop.objects.all(),
        source="requested_stop",
        write_only=True,
    )
 
    # Computed seat availability on the requested route (shown to admin)
    available_seats = serializers.SerializerMethodField()
 
    class Meta:
        model = RouteChangeRequest
        fields = [
            "id",
            "registration",
            "current_route",
            "requested_route",
            "requested_stop",
            "requested_stop_id",    # write-only
            "status",
            "admin_remarks",
            "requested_at",
            "resolved_at",
            "available_seats",
        ]
        read_only_fields = ["requested_at", "resolved_at", "status", "admin_remarks"]

    def validate(self, data):
        """Auto-resolve which route serves the requested stop."""
        stop = data.get("requested_stop")
        if stop:
            route_stop = RouteStop.objects.filter(stop=stop).select_related("route").first()
            if not route_stop:
                raise serializers.ValidationError(
                    {"requested_stop_id": "No route currently serves this stop."}
                )
            data["requested_route"] = route_stop.route
        return data
 
    def get_available_seats(self, obj):
        """How many seats are free on the requested route for that semester."""
        registration = obj.registration
        if not registration:
            return None
        if not obj.requested_route:
            return 0
        assignment = RouteAssignment.objects.filter(
            route=obj.requested_route,
            semester=registration.semester,
            is_active=True,
        ).first()
        if not assignment:
            return 0
        occupied = SeatAllocation.objects.filter(route_assignment=assignment).count()
        return max(assignment.bus.capacity - occupied, 0)
