"""
Super-admin endpoints: manage admins, roles and read the activity log.

All routes live under /api/admin-management/ and are restricted to super
admins by AdminAccessMiddleware (and again by IsSuperAdmin below).
"""
from datetime import datetime, time

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.views import TokenObtainPairView

from . import audit
from .models import AdminActivityLog, AdminProfile, AdminRole
from .rbac import (
    LEVELS, MODULES, NONE, PRESET_ROLES, clean_permissions,
    get_effective_permissions, is_super_admin,
)


class IsSuperAdmin(BasePermission):
    message = "Only the super admin can access this."

    def has_permission(self, request, view):
        return is_super_admin(request.user)


# ── Serializers ─────────────────────────────────────────────────────────────
class PermissionsField(serializers.JSONField):
    def to_internal_value(self, data):
        data = super().to_internal_value(data) or {}
        if not isinstance(data, dict):
            raise serializers.ValidationError("Must be an object of {module: level}.")
        bad = [k for k, v in data.items() if k not in MODULES or v not in LEVELS]
        if bad:
            raise serializers.ValidationError(f"Invalid module/level for: {', '.join(bad)}")
        return data


class AdminRoleSerializer(serializers.ModelSerializer):
    permissions = PermissionsField(required=False)
    admin_count = serializers.SerializerMethodField()

    class Meta:
        model = AdminRole
        fields = ["id", "name", "description", "permissions", "is_system", "admin_count", "created_at", "updated_at"]
        read_only_fields = ["is_system", "created_at", "updated_at"]

    def get_admin_count(self, obj):
        return obj.admins.count()

    def validate_permissions(self, value):
        return clean_permissions(value, allow_none=False)


class AdminUserSerializer(serializers.ModelSerializer):
    """A staff user + their AdminProfile, flattened."""
    password           = serializers.CharField(write_only=True, required=False, allow_blank=False)
    is_super_admin     = serializers.BooleanField(required=False)
    role               = serializers.PrimaryKeyRelatedField(queryset=AdminRole.objects.all(), required=False, allow_null=True)
    custom_permissions = PermissionsField(required=False)
    role_name          = serializers.SerializerMethodField()
    effective_permissions = serializers.SerializerMethodField()
    created_by         = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name", "is_active", "password",
            "is_super_admin", "role", "role_name", "custom_permissions", "effective_permissions",
            "created_by", "date_joined", "last_login",
        ]
        read_only_fields = ["date_joined", "last_login"]

    def _profile(self, obj):
        return getattr(obj, "admin_profile", None)

    def to_representation(self, obj):
        data = super().to_representation(obj)
        p = self._profile(obj)
        data["is_super_admin"] = is_super_admin(obj)
        data["role"] = p.role_id if p else None
        data["custom_permissions"] = (p.custom_permissions if p else {}) or {}
        return data

    def get_role_name(self, obj):
        p = self._profile(obj)
        return p.role.name if p and p.role else None

    def get_effective_permissions(self, obj):
        return get_effective_permissions(obj)

    def get_created_by(self, obj):
        p = self._profile(obj)
        return p.created_by.username if p and p.created_by else None

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "Password is required for a new admin."})
        return attrs

    @transaction.atomic
    def create(self, validated):
        profile_data = {
            "is_super_admin": validated.pop("is_super_admin", False),
            "role": validated.pop("role", None),
            "custom_permissions": clean_permissions(validated.pop("custom_permissions", {})),
        }
        password = validated.pop("password")
        user = User(**validated, is_staff=True)
        user.set_password(password)
        user.save()
        AdminProfile.objects.create(user=user, created_by=self.context["request"].user, **profile_data)
        return user

    @transaction.atomic
    def update(self, user, validated):
        request_user = self.context["request"].user
        profile, _ = AdminProfile.objects.get_or_create(user=user)

        if user.pk == request_user.pk:
            if validated.get("is_super_admin") is False or validated.get("is_active") is False:
                raise serializers.ValidationError("You cannot remove your own super admin access or deactivate yourself.")

        if validated.get("is_super_admin") is False and is_super_admin(user):
            others = [u for u in User.objects.filter(is_staff=True, is_active=True).exclude(pk=user.pk) if is_super_admin(u)]
            if not others:
                raise serializers.ValidationError("At least one active super admin must remain.")
            if user.is_superuser:
                user.is_superuser = False

        password = validated.pop("password", None)
        for field in ("is_super_admin", "role", "custom_permissions"):
            if field in validated:
                value = validated.pop(field)
                if field == "custom_permissions":
                    value = clean_permissions(value)
                setattr(profile, field, value)
        for key, value in validated.items():
            setattr(user, key, value)
        if password:
            user.set_password(password)
        user.is_staff = True
        user.save()
        profile.save()
        return user


class ActivityLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    module_label = serializers.SerializerMethodField()

    class Meta:
        model = AdminActivityLog
        fields = [
            "id", "actor", "actor_username", "actor_name", "action", "module", "module_label",
            "model_name", "object_id", "object_repr", "description", "changes",
            "method", "path", "ip_address", "request_id", "created_at",
        ]

    def get_actor_name(self, obj):
        if obj.actor:
            return f"{obj.actor.first_name} {obj.actor.last_name}".strip() or obj.actor.username
        return obj.actor_username

    def get_module_label(self, obj):
        if obj.module == "admin_management":
            return "Admin Management"
        return MODULES.get(obj.module, (obj.module or "—",))[0]


# ── Views ───────────────────────────────────────────────────────────────────
@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def modules_meta(request):
    """Module list + levels so the frontend can build permission grids."""
    return Response({
        "modules": [{"key": k, "label": v[0], "description": v[1]} for k, v in MODULES.items()],
        "levels": list(LEVELS),
        "presets": [p["name"] for p in PRESET_ROLES],
    })


class AdminRoleViewSet(viewsets.ModelViewSet):
    queryset = AdminRole.objects.all()
    serializer_class = AdminRoleSerializer
    permission_classes = [IsSuperAdmin]
    pagination_class = None

    def destroy(self, request, *args, **kwargs):
        role = self.get_object()
        if role.is_system:
            return Response({"detail": "Preset roles can be edited but not deleted."}, status=400)
        if role.admins.exists():
            return Response({"detail": "Role is assigned to admins. Reassign them first."}, status=400)
        return super().destroy(request, *args, **kwargs)


class AdminUserViewSet(viewsets.ModelViewSet):
    serializer_class = AdminUserSerializer
    permission_classes = [IsSuperAdmin]
    pagination_class = None
    http_method_names = ["get", "post", "patch", "head", "options"]  # deactivate instead of delete

    def get_queryset(self):
        return (
            User.objects.filter(is_staff=True)
            .select_related("admin_profile", "admin_profile__role", "admin_profile__created_by")
            .order_by("-is_active", "username")
        )


class _Page:
    DEFAULT, MAX = 25, 200


@api_view(["GET"])
@permission_classes([IsSuperAdmin])
def activity_logs(request):
    """
    Filterable activity log.
    ?actor=<id>&module=<key>&action=<create|update|delete|action|login>
    &date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&q=<text>&page=1&page_size=25
    Returns {items, total, page, page_size, pages} (not DRF pagination shape).
    """
    qs = AdminActivityLog.objects.select_related("actor")
    p = request.query_params
    if p.get("actor"):
        qs = qs.filter(actor_id=p["actor"])
    if p.get("module"):
        qs = qs.filter(module=p["module"])
    if p.get("action"):
        qs = qs.filter(action=p["action"])
    tz = timezone.get_current_timezone()
    try:
        if p.get("date_from"):
            d = datetime.strptime(p["date_from"], "%Y-%m-%d").date()
            qs = qs.filter(created_at__gte=timezone.make_aware(datetime.combine(d, time.min), tz))
        if p.get("date_to"):
            d = datetime.strptime(p["date_to"], "%Y-%m-%d").date()
            qs = qs.filter(created_at__lte=timezone.make_aware(datetime.combine(d, time.max), tz))
    except ValueError:
        return Response({"detail": "Dates must be YYYY-MM-DD."}, status=400)
    if p.get("q"):
        q = p["q"].strip()
        qs = qs.filter(
            Q(description__icontains=q) | Q(object_repr__icontains=q)
            | Q(actor_username__icontains=q) | Q(model_name__icontains=q)
        )

    try:
        page = max(1, int(p.get("page", 1)))
        size = min(_Page.MAX, max(1, int(p.get("page_size", _Page.DEFAULT))))
    except ValueError:
        page, size = 1, _Page.DEFAULT
    total = qs.count()
    items = qs[(page - 1) * size: page * size]
    return Response({
        "items": ActivityLogSerializer(items, many=True).data,
        "total": total,
        "page": page,
        "page_size": size,
        "pages": (total + size - 1) // size,
    })


# ── Login logging ───────────────────────────────────────────────────────────
class LoggedTokenObtainPairView(TokenObtainPairView):
    """Same as SimpleJWT's login view, but records admin logins."""

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0])
        user = getattr(serializer, "user", None)
        if user is not None and user.is_staff:
            token = audit.begin(user, request)
            try:
                audit.write_log(
                    action="login",
                    module="admin_management",
                    model_name="User",
                    object_id=user.pk,
                    object_repr=user.username,
                    description=f"{user.username} signed in",
                )
            finally:
                audit.end(token)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)
