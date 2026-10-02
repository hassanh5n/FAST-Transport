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

from .core import SemesterSerializer, StudentProfileSerializer, UserSerializer

class ChallanSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    semester_name = serializers.CharField(source='registration.semester.name', read_only=True)
    route_name = serializers.CharField(source='registration.route.name', read_only=True)
    stop_name = serializers.CharField(source='registration.stop.name', read_only=True)

    def get_student_name(self, obj):
        user = obj.student.user
        name = f"{user.first_name} {user.last_name}".strip()
        return name if name else user.username

    class Meta:
        model = Challan
        fields = [
            "id",
            "registration",
            "student_name",
            "semester_name",
            "route_name",
            "stop_name",
            "amount",
            "status",
            # The seat behind this challan is only held until this moment.
            "payment_due_at",
            "created_at",
        ]

class FeeVerificationSerializer(serializers.ModelSerializer):
    student = StudentProfileSerializer(read_only=True)
    semester = SemesterSerializer(read_only=True)
    verified_by = UserSerializer(read_only=True)

    class Meta:
        model = FeeVerification
        fields = '__all__'
        read_only_fields = ['created_at', 'verified_at']
