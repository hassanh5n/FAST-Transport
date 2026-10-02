"""
Role-based access control for admin (staff) users.

Model
-----
* Super admin  — ``user.is_superuser`` or ``AdminProfile.is_super_admin``.
  Full access to every module plus Admin Management and Activity Logs.
* Sub-admin    — ``is_staff`` user with an ``AdminProfile``. Effective access
  = the assigned preset role's permissions, overlaid by that admin's
  ``custom_permissions`` (custom always wins, so it can grant OR revoke).
* Staff with no profile — no module access (safe default).

Each module has three levels: ``none`` < ``view`` < ``manage``.
Read requests (GET/HEAD/OPTIONS) need ``view``; everything else needs
``manage``.

Enforcement happens centrally in ``middleware.AdminAccessMiddleware`` using
``PATH_RULES`` below, so every endpoint (viewsets, custom actions and
function views) is covered without touching each view. Students are never
affected — the middleware only applies to staff.
"""
import re

NONE, VIEW, MANAGE = "none", "view", "manage"
LEVELS = (NONE, VIEW, MANAGE)
_RANK = {NONE: 0, VIEW: 1, MANAGE: 2}

# key -> (label, description). Order is the order shown in the UI.
MODULES = {
    "students":       ("Students",                 "Student profiles and semester registrations"),
    "semesters":      ("Semesters",                "Semesters, deadlines and transport fee"),
    "routes":         ("Routes & Stops",           "Routes, stops, route builder and maps"),
    "fleet":          ("Fleet",                    "Buses, drivers, route assignments, maintenance"),
    "seats":          ("Registrations & Seats",    "Transport registrations, seat allocation, waiting list"),
    "fees":           ("Fee Verification",         "Challans and fee verification"),
    "complaints":     ("Complaints",               "View complaints and reply / resolve them"),
    "route_requests": ("Route Change Requests",    "Approve or deny route change requests"),
    "incidents":      ("Incidents",                "Review, approve or reject incident reports"),
    "export":         ("Export Data",              "Download data exports (view only)"),
}

# Preset roles seeded by migration 0021 (editable afterwards by super admin).
PRESET_ROLES = [
    {
        "name": "Complaints Officer",
        "description": "Handles student complaints and replies.",
        "permissions": {"complaints": MANAGE, "students": VIEW},
    },
    {
        "name": "Finance Officer",
        "description": "Verifies fee payments and exports finance data.",
        "permissions": {"fees": MANAGE, "students": VIEW, "seats": VIEW, "export": VIEW},
    },
    {
        "name": "Fleet Manager",
        "description": "Manages buses, drivers, routes and stops.",
        "permissions": {"fleet": MANAGE, "routes": MANAGE, "incidents": VIEW},
    },
    {
        "name": "Registration Officer",
        "description": "Handles registrations, seat allocation, waiting list and route changes.",
        "permissions": {
            "seats": MANAGE, "route_requests": MANAGE, "semesters": MANAGE,
            "students": VIEW, "routes": VIEW, "fleet": VIEW,
        },
    },
    {
        "name": "Safety Officer",
        "description": "Reviews incident reports.",
        "permissions": {"incidents": MANAGE, "routes": VIEW},
    },
    {
        "name": "Auditor (Read-only)",
        "description": "Can view every module but cannot change anything.",
        "permissions": {m: VIEW for m in MODULES},
    },
]

SUPER = "__super__"

# (regex on the path after /api/, module, extra modules that may READ it,
#  public_read) — first match wins.
#  public_read=True: any staff user may GET it (students can already read
#  these endpoints, so hiding them from staff would only break pages).
PATH_RULES = [
    (r"^admin-management/",                         SUPER,            (),                               False),
    (r"^admin/live-fleet/",                          "fleet",          (),                               False),
    (r"^students(-list)?/",                         "students",       ("export", "fees", "seats", "complaints"), False),
    (r"^semester-registrations/",                   "students",       ("export", "seats"),              False),
    (r"^semesters/",                                "semesters",      (),                               True),
    (r"^routes/\d+/(overview|map-detail)/",         "routes",         ("fleet", "seats"),               False),
    (r"^(routes|stops|routestops)/",                "routes",         (),                               True),
    (r"^admin/maps/",                               "routes",         (),                               False),
    (r"^(buses|drivers|route-assignments)/",        "fleet",          ("routes", "seats", "incidents"), False),
    (r"^maintenance-schedules/",                    "fleet",          (),                               False),
    (r"^(seat-allocations|waitlist)/",              "seats",          ("export", "route_requests"),     False),
    (r"^transport-registrations/",                  "seats",          ("fees", "students"),             False),
    (r"^fee-verifications/",                        "fees",           ("export",),                      False),
    (r"^complaints/",                               "complaints",     ("export",),                      False),
    (r"^route-change-requests/",                    "route_requests", (),                               False),
    (r"^incidents/",                                "incidents",      (),                               False),
]
_COMPILED = [(re.compile(p), m, extra, pub) for p, m, extra, pub in PATH_RULES]

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def clean_permissions(perms, allow_none=True):
    """Keep only known modules and valid levels."""
    out = {}
    for key, level in (perms or {}).items():
        if key in MODULES and level in LEVELS:
            if level == NONE and not allow_none:
                continue
            out[key] = level
    return out


def is_super_admin(user):
    if not user or not user.is_authenticated or not user.is_staff:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, "admin_profile", None)
    return bool(profile and profile.is_super_admin)


def get_effective_permissions(user):
    """Return {module: level} for every module."""
    if is_super_admin(user):
        return {m: MANAGE for m in MODULES}
    perms = {m: NONE for m in MODULES}
    if not user or not user.is_authenticated or not user.is_staff:
        return perms
    profile = getattr(user, "admin_profile", None)
    if profile is None:
        return perms
    if profile.role_id and profile.role:
        perms.update(clean_permissions(profile.role.permissions))
    perms.update(clean_permissions(profile.custom_permissions))
    return perms


def has_module_perm(user, module, level=VIEW):
    if is_super_admin(user):
        return True
    return _RANK[get_effective_permissions(user).get(module, NONE)] >= _RANK[level]


def check_path_access(user, api_path, method):
    """
    Decide whether a staff user may call ``api_path`` (path after /api/).
    Returns (allowed: bool, module_key_or_None, needed_level).
    """
    for rx, module, extra, public_read in _COMPILED:
        if not rx.match(api_path):
            continue
        is_read = method.upper() in SAFE_METHODS
        needed = VIEW if is_read else MANAGE
        if module == SUPER:
            return is_super_admin(user), SUPER, MANAGE
        if is_super_admin(user):
            return True, module, needed
        if is_read and public_read:
            return True, module, needed
        if has_module_perm(user, module, needed):
            return True, module, needed
        if is_read and any(has_module_perm(user, m, VIEW) for m in extra):
            return True, module, needed
        return False, module, needed
    return True, None, None  # not a module-protected endpoint


def staff_with_module(module, level=VIEW):
    """Active staff users who can access ``module`` (used for notifications)."""
    from django.contrib.auth.models import User
    users = User.objects.filter(is_staff=True, is_active=True).select_related(
        "admin_profile", "admin_profile__role"
    )
    return [u for u in users if has_module_perm(u, module, level)]
