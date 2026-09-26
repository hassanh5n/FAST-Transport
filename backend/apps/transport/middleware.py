"""
Central gate for admin requests.

For every /api/ request made by a staff user this middleware:
  * enforces module permissions (see rbac.PATH_RULES), returning 403 when the
    admin's role does not allow it;
  * opens the audit context so model changes are written to the activity log.

Students and anonymous requests pass straight through untouched.
"""
from django.http import JsonResponse
from rest_framework_simplejwt.authentication import JWTAuthentication

from . import audit
from .rbac import MODULES, SUPER, check_path_access

API_PREFIX = "/api/"
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_jwt = JWTAuthentication()


def _resolve_user(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user
    try:
        result = _jwt.authenticate(request)
    except Exception:
        return None  # invalid/expired token: let DRF return the proper 401
    return result[0] if result else None


class AdminAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(API_PREFIX):
            return self.get_response(request)

        user = _resolve_user(request)
        if user is None or not user.is_active or not user.is_staff:
            return self.get_response(request)

        api_path = request.path[len(API_PREFIX):]
        allowed, module, level = check_path_access(user, api_path, request.method)
        if not allowed:
            if module == SUPER:
                detail = "Only the super admin can access this."
            else:
                label = MODULES.get(module, (module,))[0]
                need = "view" if level == "view" else "make changes in"
                detail = f"Your admin role does not allow you to {need} {label}."
            return JsonResponse({"detail": detail, "code": "module_forbidden", "module": module}, status=403)

        token = audit.begin(user, request)
        try:
            response = self.get_response(request)
            ctx = audit.current()
            if (
                request.method in WRITE_METHODS
                and 200 <= response.status_code < 300
                and module  # personal endpoints (notifications, profile) are not logged
                and ctx is not None
                and ctx.get("count", 0) == 0
            ):
                audit.write_log(
                    action="action",
                    module="admin_management" if module == SUPER else module,
                    description=f"{request.method} {request.path}",
                    ctx=ctx,
                )
            return response
        finally:
            audit.end(token)
