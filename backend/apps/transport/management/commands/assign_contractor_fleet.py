"""
Give every route a bus and a driver from its own contractor, for one semester.

    python manage.py assign_contractor_fleet "Claude outputs/fast_karachi_fall2026.json"          # show the plan
    python manage.py assign_contractor_fleet "Claude outputs/fast_karachi_fall2026.json" --apply  # save it

The timetable file is optional. With it, a route gets the driver the timetable
names for it ({"routes": [{"operator", "code", "driver"}]}), matched by name among
that contractor's drivers. Otherwise, and for anything still missing:

* a route keeps its current bus or driver when it already belongs to the route's contractor;
* the rest come from the contractor's free buses (by bus number) and drivers (by name).

Existing assignments are updated in place, so students keep their seats; a bus is
only used when it has at least as many seats as the route already has allocated.
Only active, published routes with a contractor are touched.
"""

import json
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max

from apps.transport.models import Bus, Driver, Route, RouteAssignment, SeatAllocation, Semester


def _key(name):
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def _timetable_drivers(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise CommandError(f"Cannot read {path}: {exc}")
    return {
        _key(f'{route.get("operator", "")} {route.get("code", "")}'): route.get("driver")
        for route in data.get("routes", []) if route.get("driver")
    }


def _find_driver(name, drivers):
    """The one driver called `name` (exactly, or as a whole word of a longer name), else None."""
    wanted = _key(name)
    exact = [driver for driver in drivers if _key(driver.name) == wanted]
    if len(exact) == 1:
        return exact[0], ""
    if len(exact) > 1:
        return None, f'{len(exact)} drivers are called "{name}"'
    words = str(name).lower().split()
    partial = [driver for driver in drivers if all(word in str(driver.name).lower().split() for word in words)]
    if len(partial) == 1:
        return partial[0], ""
    if len(partial) > 1:
        return None, f'"{name}" matches {len(partial)} drivers'
    return None, f'no driver called "{name}"'


class Command(BaseCommand):
    help = "Assign each route a bus and driver of its own contractor (dry run unless --apply)."

    def add_arguments(self, parser):
        parser.add_argument("timetable", nargs="?", help="Timetable JSON naming each route's driver (optional).")
        parser.add_argument("--semester", type=int, help="Semester id (default: the active semester).")
        parser.add_argument("--apply", action="store_true", help="Save the assignments (default: only show them).")

    def handle(self, timetable=None, semester=None, apply=False, **options):
        semester_obj = (
            Semester.objects.filter(pk=semester).first() if semester
            else Semester.objects.filter(is_active=True).order_by("-id").first()
        )
        if semester_obj is None:
            raise CommandError("No such semester." if semester else "No active semester. Pass --semester.")
        named = _timetable_drivers(timetable) if timetable else {}

        routes = list(
            Route.objects.filter(is_active=True, status="published", contractor__isnull=False)
            .select_related("contractor").order_by("contractor__name", "name")
        )
        current = {}
        for assignment in (RouteAssignment.objects.filter(semester=semester_obj, is_active=True, route__in=routes)
                           .select_related("bus", "driver", "bus__contractor", "driver__contractor").order_by("id")):
            current.setdefault(assignment.route_id, []).append(assignment)
        seats_needed = dict(
            SeatAllocation.objects.filter(route_assignment__semester=semester_obj)
            .values("route_assignment").annotate(top=Max("seat_number")).values_list("route_assignment", "top")
        )

        # One slot per assignment a route already has, or one new slot.
        slots = []
        for route in routes:
            for assignment in current.get(route.id) or [None]:
                slots.append({"route": route, "assignment": assignment, "bus": None, "driver": None, "notes": []})

        buses = {}
        drivers = {}
        for bus in Bus.objects.filter(is_active=True, contractor__isnull=False).order_by("bus_number"):
            buses.setdefault(bus.contractor_id, []).append(bus)
        for driver in Driver.objects.filter(is_available=True, contractor__isnull=False).order_by("name"):
            drivers.setdefault(driver.contractor_id, []).append(driver)
        taken_buses, taken_drivers = set(), set()

        def need(slot):
            return seats_needed.get(slot["assignment"].id, 0) if slot["assignment"] else 0

        # 1. The driver the timetable names for the route.
        for slot in slots:
            name = named.get(_key(slot["route"].name))
            if not name or slot["driver"] or slot is not next(s for s in slots if s["route"] is slot["route"]):
                continue
            driver, problem = _find_driver(name, drivers.get(slot["route"].contractor_id, []))
            if driver and driver.id not in taken_drivers:
                slot["driver"] = driver
                taken_drivers.add(driver.id)
            elif driver:
                slot["notes"].append(f"timetable driver {driver.name} already has a route")
            else:
                slot["notes"].append(f"timetable: {problem}")

        # 2. Keep what already belongs to the right contractor.
        for slot in slots:
            assignment, owner = slot["assignment"], slot["route"].contractor_id
            if not assignment:
                continue
            bus = assignment.bus
            if bus.contractor_id == owner and bus.is_active and bus.id not in taken_buses and bus.capacity >= need(slot):
                slot["bus"] = bus
                taken_buses.add(bus.id)
            driver = assignment.driver
            if not slot["driver"] and driver.contractor_id == owner and driver.is_available and driver.id not in taken_drivers:
                slot["driver"] = driver
                taken_drivers.add(driver.id)

        # 3. Fill the rest from the contractor's free buses and drivers.
        for slot in slots:
            owner = slot["route"].contractor_id
            if not slot["bus"]:
                free = [bus for bus in buses.get(owner, []) if bus.id not in taken_buses and bus.capacity >= need(slot)]
                if free:
                    slot["bus"] = free[0]
                    taken_buses.add(free[0].id)
                else:
                    slot["notes"].append(f"no free {slot['route'].contractor.name} bus with {need(slot)}+ seats")
            if not slot["driver"]:
                free = [driver for driver in drivers.get(owner, []) if driver.id not in taken_drivers]
                if free:
                    slot["driver"] = free[0]
                    taken_drivers.add(free[0].id)
                else:
                    slot["notes"].append(f"no free {slot['route'].contractor.name} driver")

        changed = created = incomplete = 0
        self.stdout.write(f"Semester: {semester_obj}\n")
        for slot in slots:
            route, assignment, bus, driver = slot["route"], slot["assignment"], slot["bus"], slot["driver"]
            before = f"{assignment.bus.bus_number} / {assignment.driver.name}" if assignment else "none"
            after = f"{bus.bus_number if bus else '?'} / {driver.name if driver else '?'}"
            if not (bus and driver):
                incomplete += 1
                status = "SKIP"
            elif not assignment:
                created += 1
                status = "new"
            elif (assignment.bus_id, assignment.driver_id) != (bus.id, driver.id):
                changed += 1
                status = "change"
            else:
                status = "ok"
            note = f"  ({'; '.join(slot['notes'])})" if slot["notes"] else ""
            self.stdout.write(f"{status:7} {route.contractor.name:10} {route.name:22} {before:32} -> {after}{note}")

        if apply:
            with transaction.atomic():
                for slot in slots:
                    route, assignment, bus, driver = slot["route"], slot["assignment"], slot["bus"], slot["driver"]
                    if not (bus and driver):
                        continue
                    if assignment is None:
                        RouteAssignment.objects.create(route=route, bus=bus, driver=driver, semester=semester_obj, is_active=True)
                    elif (assignment.bus_id, assignment.driver_id) != (bus.id, driver.id):
                        assignment.bus, assignment.driver = bus, driver
                        assignment.save(update_fields=["bus", "driver"])

        verb = "Saved" if apply else "Would save"
        self.stdout.write(self.style.SUCCESS(
            f"\n{verb}: {changed} changed, {created} new. {incomplete} route(s) left without a full bus and driver."
        ))
        if not apply and (changed or created):
            self.stdout.write("Run again with --apply to save.")
