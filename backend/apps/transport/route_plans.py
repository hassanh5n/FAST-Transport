"""Route plans: snapshot the live routes, read/write plan files, and swap plans.

A plan is a JSON snapshot of every route with its ordered stops and ETAs.
Activating one writes it onto the live Route/RouteStop tables. Routes are
matched by name so their IDs survive the swap, which is what keeps students,
seats, waitlists and bus assignments attached. Every route ends at the FAST
campus stop. Routes and stops the new plan does not use are removed after their
buses (as the admin picks) and students (to the nearest stop) have moved onto
the new routes; see _switch_over.

Stops are matched on exact coordinates only; a matched stop keeps its live
name and address. Importing a plan (CSV, JSON or an Excel workbook) creates its
missing stops straight away so their addresses can be filled in before the plan
goes live.
"""
import csv
import datetime
import hashlib
import io
import json
import re
from decimal import Decimal

from django.db import DatabaseError, transaction
from django.db.models import Max, Q
from django.utils import timezone

from . import audit
from .models import (
    Contractor, Notification, Route, RouteAssignment, RoutePlan, RouteStop, SeatAllocation, Semester,
    SemesterRegistration, Stop, TransportRegistration, Waitlist,
)
from .seatallocation import suppress_promotion
from .signals import routes_rewritten_in_bulk
from .road_lines import schedule_road_line_build
from .rbac import MANAGE, staff_with_module
from .stop_import import _build_stop, _distance_m, _norm_name

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROUTES = 200
MAX_STOPS = 5000
MAX_ERRORS = 50
STATUSES = {"draft", "published"}
NO_ADDRESS = "N/A"  # Stop.address placeholder; plans store it as ""
# The single-route export uses these same names, so a route CSV imports as a one-route plan.
CSV_COLUMNS = [
    "route_name", "route_description", "route_status", "contractor", "stop_order",
    "name", "latitude", "longitude", "address", "morning_eta", "evening_eta",
]
_TIME = re.compile(r"^(\d{1,2}):(\d{2})(?::\d{2})?\s*([ap])?\.?m?\.?$", re.IGNORECASE)
# FAST NUCES Karachi Main Campus. With no stop order or times, a route starts at
# the stop farthest from campus and works inwards.
CAMPUS = (24.8569128, 67.2646384)
CAMPUS_NAME = "FAST NUCES Main Campus"
CAMPUS_RADIUS_M = 500  # a file's own "FAST" stop within this distance is replaced by the campus stop
# Spreadsheet headings people actually use, mapped to the plan's column names.
HEADER_ALIASES = {
    "route": "route_name", "route name": "route_name", "route_name": "route_name",
    "stop": "name", "stop name": "name", "stop_name": "name", "name": "name",
    "lat": "latitude", "latitude": "latitude",
    "lng": "longitude", "lon": "longitude", "long": "longitude", "longitude": "longitude",
    "order": "stop_order", "stop order": "stop_order", "stop_order": "stop_order", "sequence": "stop_order",
    "morning": "morning_eta", "morning eta": "morning_eta", "morning time": "morning_eta",
    "morning_eta": "morning_eta", "pickup time": "morning_eta", "pick up time": "morning_eta",
    "evening": "evening_eta", "evening eta": "evening_eta", "evening time": "evening_eta",
    "evening_eta": "evening_eta", "drop time": "evening_eta", "drop off time": "evening_eta",
    "contractor": "contractor", "address": "address",
    "description": "route_description", "route description": "route_description", "route_description": "route_description",
    "status": "route_status", "route status": "route_status", "route_status": "route_status",
}
MAX_SHEET_ROWS = MAX_STOPS + 1000


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
            **({"campus": True} if rs.stop.is_campus else {}),
        })
    return {
        "version": 1,
        "routes": [
            {
                "name": route.name,
                "description": route.description,
                "status": route.status,
                "contractor": route.contractor.name if route.contractor_id else None,
                "geometry": route.geometry,
                "stops": stops_by_route.get(route.id, []),
            }
            for route in Route.objects.exclude(status="archived").select_related("contractor").order_by("name", "id")
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
        head = {
            "route_name": route["name"], "route_description": route["description"],
            "route_status": route["status"], "contractor": route.get("contractor") or "",
        }
        for stop in route["stops"] or [{}]:  # a route without stops still gets its own row
            writer.writerow({**head, **{key: "" if value is None else value for key, value in stop.items()}})
    return "﻿" + out.getvalue()  # the BOM makes Excel read the file as UTF-8


def _parse_time(value):
    """"7:05", "07:05" or "07:05:00" -> "07:05"; blank -> None. Raises ValueError otherwise."""
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    match = _TIME.match(text)
    hour = int(match[1]) if match else 99
    if match and match[3]:  # 7:30 AM / 1:15 pm
        hour = 99 if not 1 <= hour <= 12 else hour % 12 + (12 if match[3].lower() == "p" else 0)
    if not match or hour > 23 or int(match[2]) > 59:
        raise ValueError(f'"{text}" is not a time like 07:30.')
    return f"{hour:02d}:{match[2]}"


def _lower_keys(row):
    return {str(key or "").strip().lower(): (value.strip() if isinstance(value, str) else value) for key, value in row.items()}


def _heading(name):
    key = " ".join(str(name or "").strip().lower().replace("_", " ").split())
    return HEADER_ALIASES.get(key) or HEADER_ALIASES.get(key.replace(" ", "_")) or key


def _cell(value):
    """Excel hands back times as time/datetime objects; plans store "HH:MM" text."""
    if isinstance(value, (datetime.time, datetime.datetime)):
        return value.strftime("%H:%M")
    return value.strip() if isinstance(value, str) else value


def _tabular_rows(header, rows):
    """[(row number, {canonical column: value})] from a header and its data rows."""
    keys = [_heading(name) for name in header]
    if "route_name" not in keys:
        raise PlanError("The file needs a Route column (plus Stop, Latitude and Longitude for each stop).")
    out = []
    for number, values in rows:
        row = {key: _cell(value) for key, value in zip(keys, values) if key}
        for field in ("morning_eta", "evening_eta"):
            value = row.get(field)
            if isinstance(value, float) and 0 <= value < 1:  # Excel stores a time as a fraction of a day
                minutes = round(value * 24 * 60)
                row[field] = f"{minutes // 60:02d}:{minutes % 60:02d}"
        out.append((number, row))
    return out


def _rows_from_csv(text):
    lines = list(csv.reader(io.StringIO(text)))
    if not lines:
        return []
    return _tabular_rows(lines[0], [(number, line) for number, line in enumerate(lines[1:], start=2)])


def _rows_from_xlsx(raw):
    """Every sheet's rows. Each sheet's header is the first row naming a Route and a Stop column,
    so title rows above it and columns like "Map link" are skipped."""
    from openpyxl import load_workbook  # only needed for Excel uploads

    try:
        book = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception:  # openpyxl raises many types for a damaged or non-Excel file
        raise PlanError("The file is not a readable Excel (.xlsx) workbook.")
    rows, total = [], 0
    for sheet in book.worksheets:
        header = None
        for number, values in enumerate(sheet.iter_rows(values_only=True), start=1):
            total += 1
            if total > MAX_SHEET_ROWS:
                raise PlanError(f"A plan can have at most {MAX_STOPS} route stops.")
            if header is None:
                keys = {_heading(value) for value in values}
                if {"route_name", "name"} <= keys:
                    header = values
                continue
            rows.append((f"{sheet.title} row {number}", header, values))
    book.close()
    if not rows:
        raise PlanError("No sheet has a header row with Route and Stop columns.")
    out = []
    for where, header, values in rows:
        out.extend(_tabular_rows(header, [(where, values)]))
    return out


def _raw_routes_from_rows(rows):
    routes = {}
    for line, row in rows:
        if all(value in (None, "") for value in row.values()):
            continue
        where = line if isinstance(line, str) else f"Row {line}"
        route = routes.setdefault(_norm_name(row.get("route_name") or "") or where, {
            "where": where,
            "name": row.get("route_name"),
            "description": row.get("route_description"),
            "status": row.get("route_status"),
            "contractor": row.get("contractor"),
            "stops": [],
        })
        if any(row.get(key) not in (None, "") for key in ("name", "latitude", "longitude")):
            route["stops"].append({**row, "where": where})
    return list(routes.values())


def _far_from_campus_first(item):
    return -_distance_m(item["latitude"], item["longitude"], *CAMPUS)


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
            "contractor": route.get("contractor"),
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
    elif stops and all(item["morning_eta"] for _, item in stops):
        stops.sort(key=lambda pair: pair[1]["morning_eta"])  # pickup times give the order
    else:
        stops.sort(key=lambda pair: _far_from_campus_first(pair[1]))
    return [{**item, "stop_order": n} for n, item in enumerate(_end_at_campus([item for _, item in stops]), start=1)]


def _end_at_campus(stops):
    """Every route ends at the campus stop. A stop the file put at campus is replaced
    by it (keeping its times), so a route never visits FAST twice."""
    near = [s for s in stops if -_far_from_campus_first(s) <= CAMPUS_RADIUS_M]
    campus = {
        "name": CAMPUS_NAME, "latitude": CAMPUS[0], "longitude": CAMPUS[1], "address": "",
        "morning_eta": near[0]["morning_eta"] if near else None,
        "evening_eta": near[0]["evening_eta"] if near else None,
        "campus": True,
    }
    return [s for s in stops if s not in near] + [campus]


def parse_plan_file(filename, raw):
    """Return (snapshot, {"name", "description"}). Raises PlanError listing every problem found."""
    if len(raw) > MAX_FILE_BYTES:
        raise PlanError("The file must be smaller than 10 MB.")
    meta = {}
    lower = filename.lower()
    if lower.endswith(".xlsx"):
        raw_routes = _raw_routes_from_rows(_rows_from_xlsx(raw))
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise PlanError("The file is not UTF-8 text.")
        if lower.endswith(".json"):
            raw_routes, meta = _raw_routes_from_json(text)
        else:
            try:
                raw_routes = _raw_routes_from_rows(_rows_from_csv(text))
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
            "contractor": str(raw_route.get("contractor") or "").strip() or None,
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

def _place(lat, lng):
    return (round(float(lat), 6), round(float(lng), 6))  # Stop stores 6 decimals (~0.1 m)


class _StopMatcher:
    """Finds the live stop a plan stop means, or records it as one to create.

    Only a stop at exactly the same coordinates counts as the same stop, whatever
    its name: two stops even a few metres apart stay separate. A dict keyed on the
    coordinates makes each lookup O(1), so a 300-stop plan matches in milliseconds.
    """

    def __init__(self):
        self.by_place = {}
        for stop in Stop.objects.order_by("-is_active", "id"):  # prefer an active stop at a shared spot
            self.by_place.setdefault(_place(stop.latitude, stop.longitude), {"stop": stop, "name": stop.name})

    def match(self, spec):
        key = _place(spec["latitude"], spec["longitude"])
        entry = self.by_place.get(key)
        if entry is None:
            entry = self.by_place[key] = {"stop": None, "name": spec["name"], "spec": spec}
        return entry


def _contractor_id(spec, contractors, errors):
    """The plan's contractor, else the first word of the route name ("Jadoon R-17"), else none."""
    named = spec.get("contractor")
    if named:
        if _norm_name(named) not in contractors:
            errors.append('Route "%s": unknown contractor "%s".' % (spec["name"], named))
        return contractors.get(_norm_name(named))
    return contractors.get(_norm_name(spec["name"].split()[0]))


def resolve(snapshot):
    """Work out what applying `snapshot` would do. Reads only; apply/preview both build on it."""
    matcher = _StopMatcher()
    contractors = {_norm_name(name): pk for pk, name in Contractor.objects.values_list("id", "name")}
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
            errors.append(f'Route "{spec["name"]}": two of its stops have exactly the same coordinates.')
        planned = [
            (entry["stop"].id if entry["stop"] else None, stop["morning_eta"], stop["evening_eta"])
            for entry, stop in zip(entries, spec["stops"])
        ]
        contractor_id = _contractor_id(spec, contractors, errors)
        changed = live is None or (
            live.status != spec["status"]
            or live.description != spec["description"]
            or live.contractor_id != contractor_id
            or planned != live_stops.get(live.id, [])
        )
        routes.append({"spec": spec, "live": live, "entries": entries, "changed": changed, "contractor_id": contractor_id})

    used = {id(entry): entry for item in routes for entry in item["entries"]}.values()
    return {
        "routes": routes,
        "errors": errors,
        "new_stops": [entry for entry in used if entry["stop"] is None],
        "reactivate": [entry["stop"] for entry in used if entry["stop"] is not None and not entry["stop"].is_active],
        # Live routes the plan does not mention; activation removes them.
        "dropped": [route for group in live_by_name.values() for route in group],
    }


# ── Students left without a served stop ──────────────────────────────────────

def live_coverage():
    """(route_id, stop_id) pairs students can ride today, and the routes that are running."""
    running = set(Route.objects.filter(is_active=True, status="published").values_list("id", flat=True))
    pairs = set(
        RouteStop.objects.filter(route_id__in=running, stop__is_active=True).values_list("route_id", "stop_id")
    )
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


# ── Preview and activation ───────────────────────────────────────────────────
#
# Activating a plan is one transaction (_switch_over) that writes everything and
# sends nothing. preview() runs the very same transaction and rolls it back, so
# what the admin is shown is exactly what activation will do. Notifications are
# only created after the real transaction commits (each one is also emailed).

MOVE_WARN_M = 1000  # moves longer than this are flagged in the preview


class _Rollback(Exception):
    def __init__(self, report):
        self.report = report


def _create_stops(entries):
    """Create the stops `entries` describe in one query, and point each entry at its stop."""
    created = Stop.objects.bulk_create([
        Stop(
            name=entry["spec"]["name"],
            latitude=Decimal(str(round(entry["spec"]["latitude"], 6))),
            longitude=Decimal(str(round(entry["spec"]["longitude"], 6))),
            address=entry["spec"].get("address") or NO_ADDRESS,
            location_source="import",
            is_campus=bool(entry["spec"].get("campus")),
        )
        for entry in entries
    ])
    for entry, stop in zip(entries, created):
        entry["stop"] = stop
    return created


def _flag_campus(pairs):
    """Mark the stops plan specs call the campus (an existing stop may have been reused)."""
    ids = [entry["stop"].pk for entry, spec in pairs if spec.get("campus") and entry["stop"] is not None]
    Stop.objects.filter(pk__in=ids, is_campus=False).update(is_campus=True)


def create_plan_stops(snapshot):
    """Create every stop the plan needs that does not exist yet, so addresses can be
    filled in before the plan goes live. Routes are not touched. Returns a report."""
    matcher = _StopMatcher()
    specs = [stop for route in snapshot["routes"] for stop in route["stops"]]
    entries = [matcher.match(stop) for stop in specs]
    unique = list({id(entry): entry for entry in entries}.values())
    new = [entry for entry in unique if entry["stop"] is None]
    with transaction.atomic():
        created = _create_stops(new)
        _flag_campus(zip(entries, specs))
    return {
        "created": [
            {"id": s.id, "name": s.name, "address": s.address, "latitude": float(s.latitude), "longitude": float(s.longitude)}
            for s in created
        ],
        "reused": len(unique) - len(new),
    }


def _apply(resolution):
    """Write the plan's routes and stops. Sets item["route"] to each plan route's live row."""
    _create_stops(resolution["new_stops"])
    _flag_campus((entry, stop) for item in resolution["routes"] for entry, stop in zip(item["entries"], item["spec"]["stops"]))
    for stop in resolution["reactivate"]:
        stop.is_active = True
        stop.save(update_fields=["is_active"])  # save, not update(): the signal drops stale route geometry

    # A handful of set-based queries, not several per route: each one is a round
    # trip to the database, which is slow over a long network path.
    routes = resolution["routes"]
    new = [item for item in routes if item["live"] is None]
    for item, route in zip(new, Route.objects.bulk_create([Route(name=item["spec"]["name"]) for item in new])):
        item["route"] = route
    for item in routes:
        item.setdefault("route", item["live"])
    changed = [item for item in routes if item["live"] is None or item["changed"]]
    with routes_rewritten_in_bulk():  # geometry is written below, so skip the per-row invalidation
        RouteStop.objects.filter(route__in=[item["route"] for item in changed]).delete()
    RouteStop.objects.bulk_create([
        RouteStop(
            route=item["route"], stop=entry["stop"], stop_order=order,
            morning_eta=stop["morning_eta"], evening_eta=stop["evening_eta"],
        )
        for item in changed
        for order, (entry, stop) in enumerate(zip(item["entries"], item["spec"]["stops"]), start=1)
    ])
    now = timezone.now()
    for item in changed:
        route, spec = item["route"], item["spec"]
        route.description = spec["description"]
        route.status = spec["status"]
        route.contractor_id = item["contractor_id"]
        route.geometry = spec.get("geometry")
        route.geometry_updated_at = now if route.geometry else None
        route.updated_at = now
    Route.objects.bulk_update(
        [item["route"] for item in changed],
        ["description", "status", "contractor", "geometry", "geometry_updated_at", "updated_at"],
    )
    schedule_road_line_build()  # plan routes without a saved line get one in the background


def _nearest(choices, lat, lng):
    """(distance_m, route_id, stop) of the closest (route_id, stop) pair, or None."""
    # ponytail: linear scan; ~300 stops x a few hundred students is well under a second.
    return min(
        ((_distance_m(lat, lng, float(stop.latitude), float(stop.longitude)), route_id, stop) for route_id, stop in choices),
        key=lambda found: (found[0], found[1]),
        default=None,
    )


def _move_buses(dropped_ids, plan_routes, bus_routes, errors):
    """Move each bus on a removed route to the route the admin picked. Returns the choices shown in the report."""
    by_name = {_norm_name(route.name): route for route in plan_routes}
    choices = []
    for assignment in (
        RouteAssignment.objects.filter(route_id__in=dropped_ids, is_active=True)
        .select_related("route", "bus", "driver").order_by("route__name", "bus__bus_number")
    ):
        picked = str(bus_routes.get(str(assignment.id)) or "")
        target = by_name.get(_norm_name(picked)) if picked else None
        if picked and target is None:
            errors.append(f'Bus {assignment.bus.bus_number}: route "{picked}" is not in this plan.')
        owners = {x for x in (assignment.bus.contractor_id, assignment.driver.contractor_id) if x}
        if target is not None and target.contractor_id and owners - {target.contractor_id}:
            errors.append(f"Bus {assignment.bus.bus_number}: route {target.name} belongs to another contractor.")
            target = None
        choices.append({
            "assignment_id": assignment.id,
            "bus": assignment.bus.bus_number,
            "driver": assignment.driver.name,
            "contractor": next(iter(owners), None),
            "from_route": assignment.route.name,
            "to_route": target.name if target else None,
        })
        if target is not None:
            assignment.route = target
            assignment.save(update_fields=["route"])
    return choices


def _move_students(semester, plan_routes):
    """Put every active registration whose route/stop the plan dropped on the nearest plan stop.

    A student whose bus moved to a plan route goes to the nearest stop on that route
    and keeps the seat; one whose route survived keeps it; anyone else goes to the
    nearest stop anywhere. Returns (moves, registrations that lost their seat)."""
    route_by_id = {route.id: route for route in plan_routes}
    on_route = {}
    for rs in RouteStop.objects.filter(route__in=plan_routes, stop__is_campus=False, stop__is_active=True).select_related("stop"):
        on_route.setdefault(rs.route_id, []).append(rs.stop)
    served = {(route_id, stop.id) for route_id, stops in on_route.items() for stop in stops}
    everywhere = [(route_id, stop) for route_id, stops in sorted(on_route.items(), key=lambda pair: route_by_id[pair[0]].name) for stop in stops]

    semester_regs = {
        reg.student_id: reg for reg in SemesterRegistration.objects.filter(semester=semester).exclude(status__in=("Cancelled", "Rejected"))
    }
    seat_route = {
        seat.registration_id: seat.route_assignment.route_id
        for seat in SeatAllocation.objects.filter(registration__semester=semester).select_related("route_assignment")
    }
    moves, lost_seat, moved_regs, moved_sem_regs = [], [], [], []
    for reg in (
        TransportRegistration.objects.filter(semester=semester).exclude(status__in=("Cancelled", "Rejected"))
        .select_related("student__user", "stop", "route").order_by("student__roll_number")
    ):
        if (reg.route_id, reg.stop_id) in served:
            continue
        sem_reg = semester_regs.get(reg.student_id)
        seat_on = seat_route.get(sem_reg.id) if sem_reg else None
        home = seat_on if seat_on in on_route else reg.route_id if reg.route_id in on_route else None
        lat, lng = float(reg.stop.latitude), float(reg.stop.longitude)
        found = _nearest([(home, stop) for stop in on_route[home]], lat, lng) if home else None
        found = found or _nearest(everywhere, lat, lng)
        if found is None:
            continue  # the plan has no pickup stops at all; find_orphans reports these
        distance, route_id, stop = found
        seat = "none" if seat_on is None else "kept" if seat_on == route_id else "queued"
        user = reg.student.user
        moves.append({
            "registration_id": reg.id,
            "user_id": user.id,
            "roll_number": reg.student.roll_number,
            "name": f"{user.first_name} {user.last_name}".strip() or user.username,
            "from_route": reg.route.name if reg.route else None,
            "from_stop": reg.stop.name,
            "to_route": route_by_id[route_id].name,
            "to_stop": stop.name,
            "distance_m": round(distance),
            "far": distance > MOVE_WARN_M,
            "seat": seat,
        })
        reg.route_id, reg.stop = route_id, stop
        moved_regs.append(reg)
        if sem_reg:
            sem_reg.route_id, sem_reg.stop = route_id, stop
            moved_sem_regs.append(sem_reg)
            if seat == "queued":
                lost_seat.append(sem_reg)
    TransportRegistration.objects.bulk_update(moved_regs, ["route", "stop"])
    SemesterRegistration.objects.bulk_update(moved_sem_regs, ["route", "stop"])

    # Anything else this semester still on a dropped route or stop (cancelled or rejected
    # registrations, mostly) moves quietly too, so removing the old routes never deletes it.
    done = {TransportRegistration: {reg.pk for reg in moved_regs}, SemesterRegistration: {reg.pk for reg in moved_sem_regs}}
    for model in (TransportRegistration, SemesterRegistration):
        quiet = []
        for reg in model.objects.filter(semester=semester).exclude(pk__in=done[model]).select_related("stop"):
            if (reg.route_id, reg.stop_id) in served:
                continue
            found = _nearest(everywhere, float(reg.stop.latitude), float(reg.stop.longitude))
            if found:
                reg.route_id, reg.stop = found[1], found[2]
                quiet.append(reg)
        model.objects.bulk_update(quiet, ["route", "stop"])
    return moves, lost_seat


def _queue_for_new_route(registrations):
    """Students whose old bus did not come with them wait first in line for a seat on their new route.
    Written directly (not via add_to_waitlist) so they get one notification about the move, not two."""
    if not registrations:
        return
    semester_id = registrations[0].semester_id
    last = dict(
        Waitlist.objects.filter(registration__semester_id=semester_id)
        .values_list("registration__route_id").annotate(Max("position"))
    )
    existing = {entry.registration_id: entry for entry in Waitlist.objects.filter(registration__in=registrations)}
    new = []
    for reg in registrations:
        last[reg.route_id] = position = (last.get(reg.route_id) or 0) + 1
        entry = existing.get(reg.pk) or Waitlist(registration=reg)
        entry.position, entry.status, entry.offered_at, entry.offer_expires_at = position, "waiting", None, None
        if entry.pk is None:
            new.append(entry)
    Waitlist.objects.bulk_update(existing.values(), ["position", "status", "offered_at", "offer_expires_at"])
    Waitlist.objects.bulk_create(new)
    SemesterRegistration.objects.filter(pk__in=[reg.pk for reg in registrations]).update(status="Waitlisted")
    TransportRegistration.objects.filter(
        semester_id=semester_id, student_id__in=[reg.student_id for reg in registrations],
    ).exclude(status__in=("Cancelled", "Rejected")).update(status="Waitlisted")


def _remove_unused(dropped):
    """Delete the routes and stops the new plan does not use. Anything another semester's
    registrations still point at is archived/deactivated instead, so history survives."""
    referenced = set(TransportRegistration.objects.filter(route__in=dropped).values_list("route_id", flat=True))
    referenced |= set(SemesterRegistration.objects.filter(route__in=dropped).values_list("route_id", flat=True))
    keep = [route for route in dropped if route.id in referenced]
    gone = [route for route in dropped if route.id not in referenced]
    Route.objects.filter(pk__in=[route.pk for route in keep]).update(status="archived")
    # Unmapped buses on these routes lose their assignment (and its seats) with the route.
    with routes_rewritten_in_bulk():
        Route.objects.filter(pk__in=[route.pk for route in gone]).delete()

    unused = Stop.objects.filter(routestop__isnull=True)
    still_referenced = unused.filter(Q(transportregistration__isnull=False) | Q(semesterregistration__isnull=False)).distinct()
    deactivated = still_referenced.filter(is_active=True).update(is_active=False)
    _, per_model = unused.exclude(pk__in=still_referenced.values("pk")).delete()
    return {
        "removed": [route.name for route in gone],
        "archived": [route.name for route in keep],
        "stops_removed": per_model.get(Stop._meta.label, 0),
        "stops_deactivated": deactivated,
    }


def _switch_over(plan, bus_routes):
    """Make `plan` the live plan inside the caller's transaction. Returns (report, notifications)."""
    resolution = resolve(plan_snapshot(plan))
    errors = list(resolution["errors"])
    if errors:
        raise PlanError(errors)
    semester = Semester.objects.filter(is_active=True).first()

    with audit.suspended(), suppress_promotion():
        for current in RoutePlan.objects.filter(is_active=True).exclude(pk=plan.pk):
            current.data = snapshot_live()  # keep the outgoing plan exactly as it was live
            current.is_active = False
            current.save(update_fields=["data", "is_active", "updated_at"])
        _apply(resolution)
        plan_routes = [item["route"] for item in resolution["routes"]]
        dropped = resolution["dropped"]
        buses = _move_buses({route.id for route in dropped}, plan_routes, bus_routes or {}, errors)
        if errors:
            raise PlanError(errors)
        moves, lost_seat = _move_students(semester, plan_routes) if semester else ([], [])
        removed = _remove_unused(dropped)
        _queue_for_new_route(lost_seat)
        plan.is_active = True
        plan.activated_at = timezone.now()
        plan.save(update_fields=["is_active", "activated_at", "updated_at"])

    routes = resolution["routes"]
    report = {
        "routes": {
            "created": [item["spec"]["name"] for item in routes if item["live"] is None],
            "updated": [item["spec"]["name"] for item in routes if item["live"] is not None and item["changed"]],
            "unchanged": sum(1 for item in routes if not item["changed"]),
            "removed": removed["removed"],
            "archived": removed["archived"],
        },
        "stops": {
            "created": [entry["name"] for entry in resolution["new_stops"]],
            "reactivated": [stop.name for stop in resolution["reactivate"]],
            "removed": removed["stops_removed"],
            "deactivated": removed["stops_deactivated"],
        },
        "buses": buses,
        "plan_routes": [{"name": route.name, "contractor": route.contractor_id} for route in sorted(plan_routes, key=lambda r: r.name)],
        "moved_students": [{k: v for k, v in move.items() if k != "user_id"} for move in moves],
        "affected_students": find_orphans(*live_coverage()),
        "errors": [],
    }
    notes = [_move_note(move) for move in moves]
    return report, notes


def _move_note(move):
    seat = {
        "kept": " Your bus moved to this route with you, so you keep your seat.",
        "queued": " Your old bus is not on this route yet, so you are queued for a seat and will be notified when one is ready.",
        "none": "",
    }[move["seat"]]
    return (
        move["user_id"],
        "Your transport stop has changed",
        f'The new route plan is live. Your stop is now "{move["to_stop"]}" on route {move["to_route"]} '
        f'({move["distance_m"]} m from your previous stop "{move["from_stop"]}").{seat} '
        f"If another stop suits you better, submit a route change request.",
    )


def preview(plan, bus_routes=None):
    """Exactly what activating `plan` would change: runs the activation and rolls it back."""
    plan = RoutePlan.objects.get(pk=plan.pk)  # a copy: the dry run marks it active in memory
    if plan.is_active:
        return {"errors": ["This plan is already active."]}
    try:
        with transaction.atomic():
            # Two previews (or a preview and an activation) would rewrite the same rows and
            # wait on each other; the second one is told straight away instead of hanging.
            list(RoutePlan.objects.select_for_update(nowait=True).filter(Q(pk=plan.pk) | Q(is_active=True)))
            report, _ = _switch_over(plan, bus_routes)
            raise _Rollback(report)
    except _Rollback as done:
        return done.report
    except PlanError as exc:
        return {"errors": exc.errors}
    except DatabaseError:
        return {"errors": ["Another preview or activation is running. Try again in a few seconds."], "busy": True}


def activate(plan, user=None, bus_routes=None):
    """Make `plan` the live plan. Returns the same report as preview()."""
    with transaction.atomic():
        locked = list(RoutePlan.objects.select_for_update().filter(Q(pk=plan.pk) | Q(is_active=True)))
        plan = next((item for item in locked if item.pk == plan.pk), None)
        if plan is None:
            raise PlanError("This plan no longer exists.")
        if plan.is_active:
            raise PlanError("This plan is already active.")
        report, notes = _switch_over(plan, bus_routes)
        audit.write_log(
            action="update", module="routes", model_name="Route Plan",
            object_id=plan.pk, object_repr=plan.name, actor=user,
            description=(
                f'Activated route plan "{plan.name}": {len(report["routes"]["created"])} routes created, '
                f'{len(report["routes"]["updated"])} updated, {len(report["routes"]["removed"])} removed, '
                f'{len(report["moved_students"])} students moved.'
            ),
        )

    # Only now that everything is saved: one notification (and email) per moved student.
    for user_id, title, message in notes:
        Notification.objects.create(user_id=user_id, type="warning", title=title, message=message)
    if report["moved_students"] or report["affected_students"]:
        for admin in staff_with_module("routes", MANAGE):
            Notification.objects.create(
                user=admin,
                type="alert",
                title=f'Route plan "{plan.name}" activated',
                message=(
                    f'{len(report["moved_students"])} student(s) were moved to the nearest stop on the new routes'
                    + (f', {len(report["affected_students"])} still need a stop (see Route Plans > Needs attention)' if report["affected_students"] else "")
                    + "."
                ),
            )
    return report
