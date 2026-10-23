"""One-click fleet assignment for the active semester.

plan() proposes route / bus / driver pairs without saving anything; the admin page
shows them, the admin drops any they do not want, and apply() saves the rest.

The order of work:
  1. Every active, published route with no active assignment gets one bus and driver,
     busiest routes first, and the biggest free buses go to the busiest routes.
  2. Then, while buses are left, the route with the most students over its seats
     gets another bus.
A bus and driver only go to a route of their own contractor; a bus or driver with no
contractor yet can go anywhere its partner's contractor allows (the same rule the
assignment form enforces).
"""
from django.db import transaction
from django.db.models import Count, Q

from .models import Bus, Driver, Route, RouteAssignment, Semester, SemesterRegistration

# Registrations that no longer need a seat.
CLOSED_REGISTRATIONS = ("Cancelled", "Rejected")


class AutoAssignError(Exception):
    pass


def _fits(owner, item):
    return owner is None or item.contractor_id is None or item.contractor_id == owner


def _pick(pool, owner):
    """The first item in `pool` for contractor `owner`: its own contractor's first, then one
    with no contractor. `pool` is already in preference order. Removes and returns it."""
    for exact in (True, False):
        for index, item in enumerate(pool):
            if (item.contractor_id == owner) if exact else _fits(owner, item):
                return pool.pop(index)
    return None


def plan(semester=None):
    semester = semester or Semester.objects.filter(is_active=True).first()
    if semester is None:
        raise AutoAssignError("There is no active semester to assign buses for.")

    active = RouteAssignment.objects.filter(semester=semester, is_active=True)
    routes = list(
        Route.objects.filter(is_active=True, status="published")
        .defer("geometry")
        .annotate(students=Count(
            "semesterregistration",
            filter=Q(semesterregistration__semester=semester)
            & ~Q(semesterregistration__status__in=CLOSED_REGISTRATIONS),
            distinct=True,
        ))
        .order_by("name", "id")
    )
    seats = {route.id: 0 for route in routes}
    for route_id, capacity in active.values_list("route_id", "bus__capacity"):
        if route_id in seats:
            seats[route_id] += capacity or 0
    covered = set(active.values_list("route_id", flat=True))

    # Largest buses first, so the busiest routes get the most seats.
    buses = list(
        Bus.objects.filter(is_active=True)
        .exclude(pk__in=active.values("bus_id"))
        .order_by("-capacity", "bus_number", "id")
    )
    drivers = list(
        Driver.objects.filter(is_available=True)
        .exclude(pk__in=active.values("driver_id"))
        .order_by("name", "id")
    )

    proposals, unplaced = [], []

    def take(route, reason):
        bus = _pick(buses, route.contractor_id)
        if bus is None:
            return "No free bus from this route's contractor."
        driver = _pick(drivers, route.contractor_id or bus.contractor_id)
        if driver is None:
            buses.insert(0, bus)
            buses.sort(key=lambda b: (-b.capacity, b.bus_number, b.id))
            return "No free driver from this route's contractor."
        seats[route.id] += bus.capacity
        proposals.append({
            "route_id": route.id, "route": route.name, "contractor": route.contractor_id,
            "bus_id": bus.id, "bus": bus.bus_number, "capacity": bus.capacity,
            "driver_id": driver.id, "driver": driver.name,
            "students": route.students, "seats_after": seats[route.id], "reason": reason,
        })
        return None

    # 1. Routes with no bus at all, busiest first.
    for route in sorted((r for r in routes if r.id not in covered), key=lambda r: (-r.students, r.name)):
        problem = take(route, "No bus yet")
        if problem:
            unplaced.append({"route_id": route.id, "route": route.name, "reason": problem})

    # 2. Extra buses where students outnumber seats, biggest shortfall first.
    blocked = set()
    while buses and drivers:
        short = [r for r in routes if r.id not in blocked and r.students > seats[r.id]]
        if not short:
            break
        route = max(short, key=lambda r: (r.students - seats[r.id], -r.id))
        gap = route.students - seats[route.id]
        if take(route, f"{gap} more student{'s' if gap != 1 else ''} than seats"):
            blocked.add(route.id)

    return {
        "semester": {"id": semester.id, "name": str(semester)},
        "proposals": proposals,
        "unplaced": unplaced,
        "spare_buses": [{"id": b.id, "bus_number": b.bus_number, "capacity": b.capacity, "contractor": b.contractor_id} for b in buses],
        "spare_drivers": [{"id": d.id, "name": d.name, "contractor": d.contractor_id} for d in drivers],
        "students": {route.id: route.students for route in routes},
    }


def apply(rows, serializer_class):
    """Save the chosen proposals, all or none. Each row goes through the same validation as
    the assignment form, so two rows sharing a bus or driver, or a clash with an assignment
    made since the preview, stops the whole batch. Returns the saved assignments."""
    semester = Semester.objects.filter(is_active=True).first()
    if semester is None:
        raise AutoAssignError("There is no active semester to assign buses for.")
    if not rows:
        raise AutoAssignError("Choose at least one assignment to save.")
    saved, errors = [], []
    with transaction.atomic():
        for index, row in enumerate(rows, start=1):
            serializer = serializer_class(data={
                "route_id": row.get("route_id"), "bus_id": row.get("bus_id"),
                "driver_id": row.get("driver_id"), "semester_id": semester.id, "is_active": True,
            })
            if serializer.is_valid():
                saved.append(serializer.save())
            else:
                errors.append({"row": index, "errors": serializer.errors})
        if errors:
            raise AutoAssignError(errors)  # leaving the block this way undoes the rows saved so far
    return saved
