"""
Admin activity logging.

How it works
------------
1. ``AdminAccessMiddleware`` stores the current staff request in a context
   variable (actor, IP, method, path, request id).
2. Generic ``pre_save`` / ``post_save`` / ``post_delete`` receivers below log
   every create / update / delete made while that context is set, with a
   field-level diff for updates.
3. If a write request finishes successfully without touching any tracked
   model (e.g. it only used ``queryset.update()``), the middleware writes one
   generic "action" entry so nothing an admin does goes unrecorded.

Student requests never set the context, so they are never logged.
"""
import contextvars
import datetime
import decimal
import uuid

from django.apps import apps
from django.contrib.auth.models import User
from django.db.models.signals import pre_save, post_save, post_delete

_ctx = contextvars.ContextVar("admin_audit_ctx", default=None)

# Models that are noisy or system-generated side effects — never logged.
EXCLUDED_MODELS = {
    "transport.adminactivitylog",
    "transport.notification",
    "transport.buslocationping",
    "transport.otpverification",
    "transport.externalcrimeevent",
    "transport.crimeriskzone",
    "transport.crimerisksnapshot",
}

MODEL_MODULE = {
    "studentprofile": "students",
    "semesterregistration": "students",
    "semester": "semesters",
    "route": "routes", "stop": "routes", "routestop": "routes",
    "bus": "fleet", "driver": "fleet", "routeassignment": "fleet", "maintenanceschedule": "fleet",
    "transportregistration": "seats", "seatallocation": "seats", "waitlist": "seats",
    "feeverification": "fees", "challan": "fees",
    "complaint": "complaints",
    "routechangerequest": "route_requests",
    "incident": "incidents",
    "adminrole": "admin_management", "adminprofile": "admin_management", "user": "admin_management",
}

SENSITIVE_FIELDS = {"password", "tracker_token", "otp", "otp_code", "code", "token"}
IGNORED_FIELDS = {"updated_at", "last_login"}
MAX_VALUE_LEN = 300


# ── Context ─────────────────────────────────────────────────────────────────
def begin(user, request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
    ctx = {
        "user": user,
        "ip": ip or None,
        "method": request.method,
        "path": request.path[:255],
        "request_id": uuid.uuid4().hex,
        "count": 0,
    }
    return _ctx.set(ctx)


def end(token):
    _ctx.reset(token)


def current():
    return _ctx.get()


# ── Helpers ─────────────────────────────────────────────────────────────────
def _jsonable(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (dict, list)):
        text = str(value)
        return value if len(text) <= MAX_VALUE_LEN else text[:MAX_VALUE_LEN] + "…"
    text = str(value)
    return text if len(text) <= MAX_VALUE_LEN else text[:MAX_VALUE_LEN] + "…"


def _field_values(instance):
    values = {}
    for field in instance._meta.concrete_fields:
        if field.name in IGNORED_FIELDS:
            continue
        values[field.name] = getattr(instance, field.attname)
    return values


def _mask(name, value):
    return "••••••" if name in SENSITIVE_FIELDS and value not in (None, "") else _jsonable(value)


def _label(instance):
    return instance._meta.label_lower


def _tracked(instance):
    label = _label(instance)
    if label in EXCLUDED_MODELS:
        return False
    return label.startswith("transport.") or label == "auth.user"


def write_log(*, action, module="", model_name="", object_id="", object_repr="",
              description="", changes=None, ctx=None, actor=None):
    from .models import AdminActivityLog
    ctx = ctx or current() or {}
    actor = actor or ctx.get("user")
    if ctx:
        ctx["count"] = ctx.get("count", 0) + 1
    return AdminActivityLog.objects.create(
        actor=actor if actor and actor.pk else None,
        actor_username=getattr(actor, "username", "") or "",
        action=action,
        module=module,
        model_name=model_name,
        object_id=str(object_id or "")[:64],
        object_repr=str(object_repr or "")[:255],
        description=description[:500],
        changes=changes or {},
        method=ctx.get("method", ""),
        path=ctx.get("path", ""),
        ip_address=ctx.get("ip"),
        request_id=ctx.get("request_id", ""),
    )


# ── Signal receivers ────────────────────────────────────────────────────────
def _pre_save(sender, instance, raw=False, **kwargs):
    if raw or current() is None or not _tracked(instance) or instance.pk is None:
        return
    try:
        old = sender._default_manager.get(pk=instance.pk)
        instance._audit_old = _field_values(old)
    except sender.DoesNotExist:
        instance._audit_old = None


def _post_save(sender, instance, created, raw=False, **kwargs):
    if raw or current() is None or not _tracked(instance):
        return
    new = _field_values(instance)
    verbose = instance._meta.verbose_name.title()
    if created or getattr(instance, "_audit_old", None) is None:
        changes = {k: {"to": _mask(k, v)} for k, v in new.items() if v not in (None, "", [], {})}
        action, desc = "create", f"Created {verbose} “{instance}”"
    else:
        old = instance._audit_old
        changes = {
            k: {"from": _mask(k, old.get(k)), "to": _mask(k, v)}
            for k, v in new.items() if old.get(k) != v
        }
        if not changes:
            return
        action = "update"
        desc = f"Updated {verbose} “{instance}” ({', '.join(list(changes)[:6])})"
    instance._audit_old = None
    write_log(
        action=action,
        module=MODEL_MODULE.get(instance._meta.model_name, ""),
        model_name=instance._meta.verbose_name.title(),
        object_id=instance.pk,
        object_repr=str(instance),
        description=desc,
        changes=changes,
    )


def _post_delete(sender, instance, **kwargs):
    if current() is None or not _tracked(instance):
        return
    snapshot = {k: {"from": _mask(k, v)} for k, v in _field_values(instance).items() if v not in (None, "")}
    write_log(
        action="delete",
        module=MODEL_MODULE.get(instance._meta.model_name, ""),
        model_name=instance._meta.verbose_name.title(),
        object_id=instance.pk,
        object_repr=str(instance),
        description=f"Deleted {instance._meta.verbose_name.title()} “{instance}”",
        changes=snapshot,
    )


def connect():
    models = list(apps.get_app_config("transport").get_models()) + [User]
    for model in models:
        uid = f"admin_audit_{model._meta.label_lower}"
        pre_save.connect(_pre_save, sender=model, dispatch_uid=uid + "_pre")
        post_save.connect(_post_save, sender=model, dispatch_uid=uid + "_post")
        post_delete.connect(_post_delete, sender=model, dispatch_uid=uid + "_del")
