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

class BusSerializer(serializers.ModelSerializer):
    total_seats = serializers.IntegerField(source="capacity", read_only=True)
    occupied_seats = serializers.SerializerMethodField()
    available_seats = serializers.SerializerMethodField()

    class Meta:
        model = Bus
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']

    def get_occupied_seats(self, obj):
        return SeatAllocation.objects.filter(
            route_assignment__bus=obj,
            route_assignment__is_active=True,
        ).count()

    def get_available_seats(self, obj):
        occupied = self.get_occupied_seats(obj)
        return max(obj.capacity - occupied, 0)


class DriverSerializer(serializers.ModelSerializer):
    # Login is optional. Admin sets username + password to let a driver sign in;
    # later edits may change either one, and a blank value leaves it unchanged.
    username = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=150)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True,
                                     style={"input_type": "password"})
    login_username = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = '__all__'
        read_only_fields = ['user', 'created_at', 'updated_at']

    def get_login_username(self, obj):
        return obj.user.username if obj.user_id else None

    def validate(self, attrs):
        username = (attrs.get("username") or "").strip()
        password = attrs.get("password") or ""
        user = getattr(self.instance, "user", None)

        if username:
            try:
                User._meta.get_field("username").run_validators(username)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"username": exc.messages})
            clash = User.objects.filter(username__iexact=username)
            if user:
                clash = clash.exclude(pk=user.pk)
            if clash.exists():
                raise serializers.ValidationError({"username": "This username is already taken."})
        if password and len(password) < 8:
            raise serializers.ValidationError({"password": "Password must be at least 8 characters."})
        if user is None and bool(username) != bool(password):
            raise serializers.ValidationError(
                {"password" if username else "username": "Username and password are both needed to create a login."}
            )

        attrs["username"] = username
        return attrs

    def create(self, validated_data):
        login = validated_data.pop("username", ""), validated_data.pop("password", "")
        with transaction.atomic():
            driver = super().create(validated_data)
            self._save_login(driver, *login)
        return driver

    def update(self, instance, validated_data):
        login = validated_data.pop("username", ""), validated_data.pop("password", "")
        with transaction.atomic():
            driver = super().update(instance, validated_data)
            self._save_login(driver, *login)
        return driver

    @staticmethod
    def _save_login(driver, username, password):
        user = driver.user
        if not (username or password):
            # Keep the navbar name in step with the driver record.
            if user and user.first_name != driver.name[:150]:
                user.first_name = driver.name[:150]
                user.save(update_fields=["first_name"])
            return
        user = user or User(username=username)
        if username:
            user.username = username
        user.first_name = driver.name[:150]
        if password:
            user.set_password(password)
        user.save()
        user.groups.add(Group.objects.get_or_create(name="Driver")[0])
        if driver.user_id != user.pk:
            driver.user = user
            driver.save(update_fields=["user"])


class RouteAssignmentSerializer(serializers.ModelSerializer):

    route = RouteSerializer(read_only=True)  # READ (for responses)
    bus = BusSerializer(read_only=True)
    driver = DriverSerializer(read_only=True)
    semester = SemesterSerializer(read_only=True)

    route_id = serializers.PrimaryKeyRelatedField(  # WRITE (for requests)
        queryset=Route.objects.all(),
        source="route",
        write_only=True
    )

    bus_id = serializers.PrimaryKeyRelatedField(
        queryset=Bus.objects.all(),
        source="bus",
        write_only=True
    )

    driver_id = serializers.PrimaryKeyRelatedField(
        queryset=Driver.objects.all(),
        source="driver",
        write_only=True
    )

    semester_id = serializers.PrimaryKeyRelatedField(
        queryset=Semester.objects.all(),
        source="semester",
        write_only=True
    )

    def validate(self, data):
        instance = self.instance

        # Resolve fields: prefer incoming data, fall back to existing instance values
        bus = data.get("bus") or (instance.bus if instance else None)
        driver = data.get("driver") or (instance.driver if instance else None)
        semester = data.get("semester") or (instance.semester if instance else None)
        route = data.get("route") or (instance.route if instance else None)

        # If is_active is being set to True, ensure all related objects are active
        is_active = data.get("is_active", instance.is_active if instance else None)
        if is_active:
            if route and not route.is_active:
                raise serializers.ValidationError(
                    "Cannot activate assignment: the route is inactive."
                )
            if bus and not bus.is_active:
                raise serializers.ValidationError(
                    "Cannot activate assignment: the bus is inactive."
                )
            if driver and not driver.is_available:
                raise serializers.ValidationError(
                    "Cannot activate assignment: the driver is unavailable."
                )
            if semester and not semester.is_active:
                raise serializers.ValidationError(
                    "Cannot activate assignment: the semester is inactive."
                )

        # Prevent duplicate bus+semester assignment (skip current instance on update)
        qs_bus = RouteAssignment.objects.filter(
            bus=bus,
            semester=semester,
            is_active=True
        )
        if instance:
            qs_bus = qs_bus.exclude(pk=instance.pk)
        if bus and semester and is_active and qs_bus.exists():
            raise serializers.ValidationError(
                "This bus is already assigned in this semester."
            )

        # Prevent duplicate driver+semester assignment
        qs_driver = RouteAssignment.objects.filter(
            driver=driver,
            semester=semester,
            is_active=True
        )
        if instance:
            qs_driver = qs_driver.exclude(pk=instance.pk)
        if driver and semester and is_active and qs_driver.exists():
            raise serializers.ValidationError(
                "This driver is already assigned in this semester."
            )

        return data

    class Meta:
        model = RouteAssignment
        fields = "__all__"
        read_only_fields = ["created_at"]
 


class MaintenanceScheduleSerializer(serializers.ModelSerializer):
    bus = BusSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = MaintenanceSchedule
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'completed_date']
    
    
class BusLocationPingSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusLocationPing
        fields = ["id", "bus", "latitude", "longitude", "distance_from_route_m", "recorded_at"]
        read_only_fields = ["distance_from_route_m", "recorded_at"]
