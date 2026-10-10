"""Route plans: snapshot the live routes, read/write plan files, and swap plans.

A plan is a JSON snapshot of every route with its ordered stops and ETAs.
Activating one writes it onto the live Route/RouteStop tables. Routes are
matched by name so their IDs survive the swap, which is what keeps students,
seats, waitlists and bus assignments attached. A live route the plan does not
mention is archived, never deleted (deleting a Route cascades to registrations)
and never deactivated (that permanently drops its bus assignments).

Stops are matched like the stop import does: same name, else within
DUPLICATE_RADIUS_M. A matched stop keeps its live coordinates and address.
"""
import csv
import hashlib
import io
import json
import re
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from . import audit
from .models import Notification, Route, RoutePlan, RouteStop, Semester, Stop, TransportRegistration
from .rbac import MANAGE, staff_with_module
from .stop_import import DUPLICATE_RADIUS_M, _build_stop, _distance_m, _norm_name

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROUTES = 200
MAX_STOPS = 5000
MAX_ERRORS = 50
STATUSES = {"draft", "published"}
NO_ADDRESS = "N/A"  # Stop.address placeholder; plans store it as ""
# The single-route export uses these same names, so a route CSV imports as a one-route plan.
CSV_COLUMNS = [
    "route_name", "route_description", "route_status", "stop_order",
    "name", "latitude", "longitude", "address", "morning_eta", "evening_eta",
]
_TIME = re.compile(r"^(\d{1,2}):(\d{2})(?::\d{2})?$")


class PlanError(ValueError):
    """A plan file or plan that cannot be used. `errors` is a list of readable reasons."""

    def __init__(self, errors):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__(" ".join(self.errors))


# ── Snapshots ────────────────────────────────────────────────────────────────

def _eta(value):
    return value.strftime("%H:%M") if value else None


def snapshot_live():
    """The live routes (everything not archived) as a plan snapshot."""
    stops_by_route = {}
    for rs in RouteStop.objects.select_related("stop").order_by("route_id", "stop_order"):
        stops = stops_by_route.setdefault(rs.route_id, [])
        stops.append({
            "stop_order": len(stops) + 1,
            "name": rs.stop.name,
            "latitude": float(rs.stop.latitude),
            "longitude": float(rs.stop.longitude),
            "address": "" if rs.stop.address == NO_ADDRESS else rs.stop.address,
            "morning_eta": _eta(rs.morning_eta),
            "evening_eta": _eta(rs.evening_eta),
        })
    return {
        "version": 1,
        "routes": [
            {
                "name": route.name,
                "description": route.description,
                "status": route.status,
                "geometry": route.geometry,
                "stops": stops_by_route.get(route.id, []),
            }
            for route in Route.objects.exclude(status="archived").order_by("name", "id")
        ],
    }


def plan_snapshot(plan):
    """A plan's routes. The active plan is read from the live tables, not from `data`."""
    if plan.is_active:
        return snapshot_live()
    return {"version": 1, "routes": (plan.data or {}).get("routes", [])}


def counts(snapshot):
    routes = snapshot.get("routes", [])
    stops = {_norm_name(stop["name"]) for route in routes for stop in route["stops"]}
    return {"route_count": len(routes), "stop_count": len(stops)}


def fingerprint(snapshot):
    """Changes whenever the plan's routes do; the admin page keys its cached map picture on it."""
    return hashlib.md5(json.dumps(snapshot.get("routes", []), sort_keys=True).encode()).hexdigest()[:16]


def free_name(base):
    """`base`, or `base (2)`, `base (3)`… — whichever no plan uses yet."""
    base = (str(base or "").strip() or "Route plan")[:90]
    name, n = base, 1
    while RoutePlan.objects.filter(name__iexact=name).exists():
        n += 1
        name = f"{base} ({n})"
    return name


# ── Files ────────────────────────────────────────────────────────────────────

def export_json(plan):
    snapshot = plan_snapshot(plan)
    return json.dumps(
        {"version": 1, "plan": {"name": plan.name, "description": plan.description}, "routes": snapshot["routes"]},
        indent=2,
    )


def export_csv(plan):
    """One row per route stop. Geometry is left out: it is a cache the map rebuilds."""
    out = io.StringIO()
    writer = csv.DictWriter(out, CSV_COLUMNS, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    for route in plan_snapshot(plan)["routes"]:
        head = {"route_name": route["name"], "route_description": route["description"], "route_status": route["status"]}
        for stop in route["stops"] or [{}]:  # a route without stops still gets its own row
            writer.writerow({**head, **{key: "" if value is None else value for key, value in stop.items()}})
    return "﻿" + out.getvalue()  # the BOM makes Excel read the file as UTF-8


def _parse_time(value):
    """"7:05", "07:05" or "07:05:00" -> "07:05"; blank -> None. Raises ValueError otherwise."""
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    match = _TIME.match(text)
    if not match or int(match[1]) > 23 or int(match[2]) > 59:
        raise ValueError(f'"{text}" is not a time like 07:30.')
    return f"{int(match[1]):02d}:{match[2]}"


def _lower_keys(row):
    return {str(key or "").strip().lower(): (value.strip() if isinstance(value, str) else value) for key, value in row.items()}


def _raw_routes_from_csv(text):
    reader = csv.DictReader(io.StringIO(text))
    if "route_name" not in [str(name or "").strip().lower() for name in reader.fieldnames or []]:
        raise PlanError("The CSV needs a route_name column (plus name, latitude, longitude for each stop).")
    routes = {}
    for line, raw in enumerate(reader, start=2):  # line 1 is the header
        row = _lower_keys(raw)
        if all(value in (None, "") for value in row.values()):
            continue
        where = f"Row {line}"
        route = routes.setdefault(_norm_name(row.get("route_name") or "") or where, {
            "where": where,
            "name": row.get("route_name"),
            "description": row.get("route_description"),
            "status": row.get("route_status"),
            "stops": [],
        })
        if any(row.get(key) not in (None, "") for key in ("name", "latitude", "longitude")):
            route["stops"].append({**row, "where": where})
    return list(routes.values())


def _raw_routes_from_json(text):
    try:
        data = json.loads(text)
    except ValueError:
        raise PlanError("The file is not valid JSON.")
    routes = data.get("routes") if isinstance(data, dict) else None
    if not isinstance(routes, list) or not all(isinstance(route, dict) for route in routes):
        raise PlanError('JSON must look like {"routes": [{"name": ..., "stops": [...]}]}.')
    raw = []
    for index, route in enumerate(routes, start=1):
        route = _lower_keys(route)
        where = f'Route {index} ("{route.get("name") or ""}")'
        stops = route.get("stops") or []
        if not isinstance(stops, list) or not all(isinstance(stop, dict) for stop in stops):
            raise PlanError(f"{where}: stops must be a list.")
        raw.append({
            "where": where,
            "name": route.get("name"),
            "description": route.get("description"),
            "status": route.get("status"),
            "geometry": route.get("geometry"),
            "stops": [{**_lower_keys(stop), "where": f"{where}, stop {n}"} for n, stop in enumerate(stops, start=1)],
        })
    plan = data.get("plan") if isinstance(data.get("plan"), dict) else {}
    return raw, plan


def _clean_stops(raw_stops, errors):
    stops, seen = [], set()
    for raw in raw_stops:
        where = raw["where"]
        stop, reason = _build_stop(raw)  # the stop import's name/coordinate checks
        if stop is None:
            errors.append(f"{where}: {reason}")
            continue
        key = _norm_name(stop.name)
        if key in seen:
            errors.append(f'{where}: "{stop.name}" appears more than once on this route.')
            continue
        seen.add(key)
        item = {
            "name": stop.name,
            "latitude": float(stop.latitude),
            "longitude": float(stop.longitude),
            "address": "" if stop.address == NO_ADDRESS else stop.address,
        }
        for field in ("morning_eta", "evening_eta"):
            try:
                item[field] = _parse_time(raw.get(field))
            except ValueError as exc:
                errors.append(f"{where}: {field} {exc}")
                item[field] = None
        order = raw.get("stop_order")
        try:
            item["stop_order"] = None if order in (None, "") else int(float(order))
        except (TypeError, ValueError):
            errors.append(f'{where}: stop_order "{order}" is not a number.')
            item["stop_order"] = None
        stops.append((where, item))

    orders = [item["stop_order"] for _, item in stops]
    if any(order is not None for order in orders):
        if any(order is None for order in orders):
            errors.append(f"{stops[0][0]}: give every stop on the route a stop_order, or none of them.")
        elif len(set(orders)) != len(orders):
            errors.append(f"{stops[0][0]}: two stops on this route share a stop_order.")
        else:
            stops.sort(key=lambda pair: pair[1]["stop_order"])
    # Without stop_order the file's own order is the route order.
    return [{**item, "stop_order": n} for n, (_, item) in enumerate(stops, start=1)]


def parse_plan_file(filename, raw):
    """Return (snapshot, {"name", "description"}). Raises PlanError listing every problem found."""
    if len(raw) > MAX_FILE_BYTES:
        raise PlanError("The file must be smaller than 10 MB.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise PlanError("The file is not UTF-8 text.")

    meta = {}
    if filename.lower().endswith(".json"):
        raw_routes, meta = _raw_routes_from_json(text)
    else:
        try:
            raw_routes = _raw_routes_from_csv(text)
        except csv.Error as exc:
            raise PlanError(f"Could not read the CSV file: {exc}")

    if not raw_routes:
        raise PlanError("The file has no routes.")
    if len(raw_routes) > MAX_ROUTES:
        raise PlanError(f"A plan can have at most {MAX_ROUTES} routes (this file has {len(raw_routes)}).")
    if sum(len(route["stops"]) for route in raw_routes) > MAX_STOPS:
        raise PlanError(f"A plan can have at most {MAX_STOPS} route stops.")

    errors, routes, seen = [], [], set()
    for raw_route in raw_routes:
        where = raw_route["where"]
        name = str(raw_route.get("name") or "").strip()
        if not name:
            errors.append(f"{where}: route name is missing.")
            continue
        if len(name) > 100:
            errors.append(f"{where}: route name is longer than 100 characters.")
        if _norm_name(name) in seen:
            errors.append(f'{where}: the route "{name}" appears more than once.')
        seen.add(_norm_name(name))

        status = str(raw_route.get("status") or "published").strip().lower()
        if status not in STATUSES:
            errors.append(f'{where}: status "{status}" must be draft or published.')
        geometry = raw_route.get("geometry") or None
        if geometry is not None and not (
            isinstance(geometry, dict) and geometry.get("type") == "LineString"
            and isinstance(geometry.get("coordinates"), list)
        ):
            errors.append(f"{where}: geometry must be a GeoJSON LineString.")
        routes.append({
            "name": name,
            "description": str(raw_route.get("description") or "").strip() or "No description",
            "status": status,
            "geometry": geometry,
            "stops": _clean_stops(raw_route["stops"], errors),
        })

    if errors:
        extra = len(errors) - MAX_ERRORS
        raise PlanError(errors[:MAX_ERRORS] + ([f"…and {extra} more problems."] if extra > 0 else []))
    return {"version": 1, "routes": routes}, {
        "name": str(meta.get("name") or "").strip(),
        "description": str(meta.get("description") or "").strip(),
    }


# ── Matching a plan to the live tables ───────────────────────────────────────

class _StopMatcher:
    """Finds the live stop a plan stop means, or records it as one to create."""

    def __init__(self):
        self.entries = [
            {"stop": stop, "name": stop.name, "lat": float(stop.latitude), "lng": float(stop.longitude)}
            for stop in Stop.objects.order_by("id")
        ]
        self.by_name = {}
        for entry in self.entries:
            self.by_name.setdefault(_norm_name(entry["name"]), entry)

    def match(self, spec):
        key = _norm_name(spec["name"])
        # ponytail: linear scan per stop; fine up to MAX_STOPS, use a grid index if plans grow.
        entry = self.by_name.get(key) or next(
            (e for e in self.entries
             if _distance_m(spec["latitude"], spec["longitude"], e["lat"], e["lng"]) <= DUPLICATE_RADIUS_M),
            None,
        )
        if entry is None:
            entry = {"stop": None, "name": spec["name"], "lat": spec["latitude"], "lng": spec["longitude"], "spec": spec}
            self.entries.append(entry)
            self.by_name[key] = entry
        return entry


def resolve(snapshot):
    """Work out what applying `snapshot` would do. Reads only; apply/preview both build on it."""
    matcher = _StopMatcher()
    live_by_name = {}
    for route in Route.objects.order_by("id"):
        live_by_name.setdefault(_norm_name(route.name), []).append(route)
    live_stops = {}
    for rs in RouteStop.objects.order_by("route_id", "stop_order"):
        live_stops.setdefault(rs.route_id, []).append((rs.stop_id, _eta(rs.morning_eta), _eta(rs.evening_eta)))

    routes, errors = [], []
    for spec in snapshot.get("routes", []):
        candidates = live_by_name.get(_norm_name(spec["name"]), [])
        live = candidates.pop(0) if candidates else None  # popped, so what stays in live_by_name is unmatched
        entries = [matcher.match(stop) for stop in spec["stops"]]
        ids = [id(entry) for entry in entries]
        if len(set(ids)) != len(ids):
            # RouteStop allows a stop once per route; two plan stops landed on the same one.
            errors.append(f'Route "{spec["name"]}": two of its stops are the same existing stop (same place within {DUPLICATE_RADIUS_M} m).')
        planned = [
            (entry["stop"].id if entry["stop"] else None, stop["morning_eta"], stop["evening_eta"])
            for entry, stop in zip(entries, spec["stops"])
        ]
        changed = live is None or (
            live.status != spec["status"]
            or live.description != spec["description"]
            or planned != live_stops.get(live.id, [])
        )
        routes.append({"spec": spec, "live": live, "entries": entries, "changed": changed})

    used = {id(entry): entry for item in routes for entry in item["entries"]}.values()
    return {
        "routes": routes,
        "errors": errors,
        "new_stops": [entry for entry in used if entry["stop"] is None],
        "reactivate": [entry["stop"] for entry in used if entry["stop"] is not None and not entry["stop"].is_active],
        "archive": [
            route for group in live_by_name.values() for route in group
            if route.status != "archived"
        ],
    }


# ── Students left without a served stop ──────────────────────────────────────

def live_coverage():
    """(route_id, stop_id) pairs students can ride today, and the routes that are running."""
    running = set(Route.objects.filter(is_active=True, status="published").values_list("id", flat=True))
    pairs = set(
        RouteStop.objects.filter(route_id__in=running, stop__is_active=True).values_list("route_id", "stop_id")
    )
    return pairs, running


def _plan_coverage(resolution):
    pairs, running = set(), set()
    for item in resolution["routes"]:
        route = item["live"]
        if route is None or not route.is_active or item["spec"]["status"] != "published":
            continue  # a brand-new route has no students yet
        running.add(route.id)
        pairs.update((route.id, entry["stop"].id) for entry in item["entries"] if entry["stop"] is not None)
    return pairs, running


def find_orphans(pairs, running):
    """Active-semester registrations whose route/stop is not in `pairs`."""
    semester = Semester.objects.filter(is_active=True).first()
    if semester is None:
        return []
    served_stops = {stop_id for _, stop_id in pairs}
    orphans = []
    # TransportRegistration is the master record (see RouteViewSet.overview).
    registrations = (
        TransportRegistration.objects.filter(semester=semester)
        .exclude(status__in=("Cancelled", "Rejected"))
        .select_related("student__user", "stop", "route")
        .order_by("student__roll_number")
    )
    for reg in registrations:
        if reg.route_id is None:
            if reg.stop_id in served_stops:
                continue
            reason = f'No running route serves the stop "{reg.stop.name}".'
        elif (reg.route_id, reg.stop_id) in pairs:
            continue
        elif reg.route_id not in running:
            reason = f'Route "{reg.route.name}" is not running.'
        else:
            reason = f'The stop "{reg.stop.name}" is not on route "{reg.route.name}".'
        user = reg.student.user
        orphans.append({
            "registration_id": reg.id,
            "student_id": reg.student_id,
            "user_id": user.id,
            "roll_number": reg.student.roll_number,
            "name": f"{user.first_name} {user.last_name}".strip() or user.username,
            "route": reg.route.name if reg.route else None,
            "stop": reg.stop.name,
            "status": reg.status,
            "reason": reason,
        })
    return orphans


def _newly_affected(after, before):
    known = {orphan["registration_id"] for orphan in before}
    return [orphan for orphan in after if orphan["registration_id"] not in known]


# ── Preview and activation ───────────────────────────────────────────────────

def _report(resolution, affected):
    routes = resolution["routes"]
    return {
        "routes": {
            "created": [item["spec"]["name"] for item in routes if item["live"] is None],
            "updated": [item["spec"]["name"] for item in routes if item["live"] is not None and item["changed"]],
            "unchanged": sum(1 for item in routes if not item["changed"]),
            "archived": [route.name for route in resolution["archive"]],
        },
        "stops": {
            "created": [entry["name"] for entry in resolution["new_stops"]],
            "reactivated": [stop.name for stop in resolution["reactivate"]],
        },
        "affected_students": affected,
        "errors": resolution["errors"],
    }


def preview(plan):
    """What activating `plan` would change. Writes nothing."""
    resolution = resolve(plan_snapshot(plan))
    affected = _newly_affected(find_orphans(*_plan_coverage(resolution)), find_orphans(*live_coverage()))
    return _report(resolution, affected)


def _apply(resolution):
    for entry in resolution["new_stops"]:
        spec = entry["spec"]
        entry["stop"] = Stop.objects.create(
            name=spec["name"],
            latitude=Decimal(str(round(spec["latitude"], 6))),
            longitude=Decimal(str(round(spec["longitude"], 6))),
            address=spec.get("address") or NO_ADDRESS,
            location_source="import",
        )
    for stop in resolution["reactivate"]:
        stop.is_active = True
        stop.save(update_fields=["is_active"])  # save, not update(): the signal drops stale route geometry

    for item in resolution["routes"]:
        spec, route = item["spec"], item["live"]
        if route is None:
            route = Route.objects.create(name=spec["name"])
        elif not item["changed"]:
            continue
        # Same order as the route builder: the RouteStop delete signal clears
        # geometry, so geometry is written last.
        RouteStop.objects.filter(route=route).delete()
        RouteStop.objects.bulk_create([
            RouteStop(
                route=route, stop=entry["stop"], stop_order=order,
                morning_eta=stop["morning_eta"], evening_eta=stop["evening_eta"],
            )
            for order, (entry, stop) in enumerate(zip(item["entries"], spec["stops"]), start=1)
        ])
        route.description = spec["description"]
        route.status = spec["status"]
        route.geometry = spec.get("geometry")
        route.geometry_updated_at = timezone.now() if route.geometry else None
        route.save(update_fields=["description", "status", "geometry", "geometry_updated_at", "updated_at"])

    # update(), not save(): archiving must not touch is_active or its signal.
    Route.objects.filter(pk__in=[route.pk for route in resolution["archive"]]).update(status="archived")


def activate(plan, user=None):
    """Make `plan` the live plan. Returns the same report as preview()."""
    with transaction.atomic():
        locked = list(RoutePlan.objects.select_for_update().filter(Q(pk=plan.pk) | Q(is_active=True)))
        plan = next((item for item in locked if item.pk == plan.pk), None)
        if plan is None:
            raise PlanError("This plan no longer exists.")
        if plan.is_active:
            raise PlanError("This plan is already active.")

        resolution = resolve(plan_snapshot(plan))
        if resolution["errors"]:
            raise PlanError(resolution["errors"])
        before = find_orphans(*live_coverage())

        # One summary entry below instead of a log row per route stop.
        with audit.suspended():
            for current in locked:
                if current.is_active:
                    current.data = snapshot_live()  # keep the outgoing plan exactly as it was live
                    current.is_active = False
                    current.save(update_fields=["data", "is_active", "updated_at"])
            _apply(resolution)
            plan.is_active = True
            plan.activated_at = timezone.now()
            plan.save(update_fields=["is_active", "activated_at", "updated_at"])

        affected = _newly_affected(find_orphans(*live_coverage()), before)
        report = _report(resolution, affected)
        audit.write_log(
            action="update", module="routes", model_name="Route Plan",
            object_id=plan.pk, object_repr=plan.name, actor=user,
            description=(
                f'Activated route plan "{plan.name}": {len(report["routes"]["created"])} routes created, '
                f'{len(report["routes"]["updated"])} updated, {len(report["routes"]["archived"])} archived, '
                f'{len(affected)} students affected.'
            ),
        )

    for orphan in affected:
        Notification.objects.create(
            user_id=orphan["user_id"],
            type="warning",
            title="Your transport route has changed",
            message=(
                f"The route plan was updated and your registration is affected. {orphan['reason']} "
                f"Please submit a route change request to choose a new stop. Your current seat is kept until then."
            ),
        )
    if affected:
        for admin in staff_with_module("routes", MANAGE):
            Notification.objects.create(
                user=admin,
                type="alert",
                title=f'Route plan "{plan.name}" activated',
                message=f"{len(affected)} registered student(s) are on a route or stop the new plan no longer serves. See Route Plans > Needs attention.",
            )
    return report
