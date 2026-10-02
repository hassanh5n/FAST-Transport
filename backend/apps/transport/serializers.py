from rest_framework import serializers
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from .models import (
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

class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name',
                  'full_name', 'is_active', 'role']

    def get_role(self, obj):
        return "Admin" if obj.is_staff else "Student"

    def get_full_name(self, obj):
        name = f"{obj.first_name} {obj.last_name}".strip()
        return name if name else obj.username


class CrimeRiskZoneSerializer(serializers.ModelSerializer):
    """Public, aggregated representation; raw external crime events stay server-side."""

    class Meta:
        model = CrimeRiskZone
        fields = [
            "zone_id", "geometry", "current_score", "current_level",
            "confidence", "source_updated_at", "algorithm_version",
        ]


class StudentProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = StudentProfile
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class SemesterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Semester
        fields = '__all__'
        read_only_fields = ['created_at']


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


class ComplaintSerializer(serializers.ModelSerializer):
    submitted_by = UserSerializer(read_only=True)
    semester = SemesterSerializer(read_only=True)
    route = RouteSerializer(read_only=True)
    resolved_by = UserSerializer(read_only=True)

    class Meta:
        model = Complaint
        fields = '__all__'
        read_only_fields = ['created_at', 'resolved_at']


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
 


class MaintenanceScheduleSerializer(serializers.ModelSerializer):
    bus = BusSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = MaintenanceSchedule
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at', 'completed_date']


class NotificationSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['created_at']

# Serializer for creating User + StudentProfile together
class StudentProfileCreateSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True)
    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    last_name = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = StudentProfile
        fields = ['username', 'email', 'password', 'first_name', 'last_name',
                  'roll_number', 'department', 'batch', 'phone', 'address']

    def create(self, validated_data):
        from django.contrib.auth.models import User, Group

        username = validated_data.pop('username')
        email = validated_data.pop('email')
        password = validated_data.pop('password')
        first_name = validated_data.pop('first_name', '')
        last_name = validated_data.pop('last_name', '')

        user = User.objects.create_user(
            username=username, email=email, password=password,
            first_name=first_name, last_name=last_name
        )

        student_group, _ = Group.objects.get_or_create(name="Student")
        user.groups.add(student_group)

        profile = StudentProfile.objects.create(user=user, **validated_data)
        return profile
    
    
class BusLocationPingSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusLocationPing
        fields = ["id", "bus", "latitude", "longitude", "distance_from_route_m", "recorded_at"]
        read_only_fields = ["distance_from_route_m", "recorded_at"]


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