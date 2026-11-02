"""JWT authentication that looks the user up once per request.

AdminAccessMiddleware authenticates admin requests to check module permissions,
then DRF authenticates the same request again. Each lookup is a round trip to the
database (~170 ms to the hosted Supabase), and the permission check and most
views then fetch the user's admin, student or driver profile one by one.
"""
from django.contrib.auth.models import User
from django.db.models import OuterRef
from rest_framework_simplejwt.authentication import JWTAuthentication

from .transport_status import registration_status_subquery


class _UsersWithProfiles:
    """Stands in for the user model in JWTAuthentication.get_user, so the user comes
    back with every profile the request may need, in the same query. The passenger's
    current registration status rides along too (an indexed subquery, no extra round
    trip), for current_user_payload's transport_status."""
    DoesNotExist = User.DoesNotExist

    class _Manager:
        # A property, not a class attribute: the subquery compares against today's
        # date, which must be read per request, not once at import.
        def __getattr__(self, name):
            qs = User.objects.select_related(
                "admin_profile__role", "studentprofile", "driver_profile"
            ).annotate(
                current_registration_status=registration_status_subquery(student__user_id=OuterRef("pk"))
            )
            return getattr(qs, name)

    objects = _Manager()


class SharedJWTAuthentication(JWTAuthentication):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_model = _UsersWithProfiles  # the parent sets the plain user model

    def authenticate(self, request):
        # DRF wraps the Django request; the middleware sees the Django request itself.
        # The result is kept on the Django request so both share one lookup. A bad
        # token raises and is not kept, so DRF still returns its proper 401.
        django_request = getattr(request, "_request", request)
        if not hasattr(django_request, "_jwt_auth_result"):
            django_request._jwt_auth_result = super().authenticate(request)
        return django_request._jwt_auth_result
