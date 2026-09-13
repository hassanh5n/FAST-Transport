"""
Seat allocation and the waitlist queue.

The rule this module enforces: **a student is never charged for a seat that
does not exist.** Registering on a full route puts you in a queue with no
challan. A challan is only issued when a seat is actually held for you, and
that hold expires after SEAT_OFFER_HOURS so the queue keeps moving.

When a seat is released — a student cancels, an admin deletes an allocation,
an offer lapses unpaid — the next student in that route's queue is promoted
automatically (see the post_delete receiver in signals.py).
"""

import contextlib
import threading
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    SeatAllocation,
    Waitlist,
    RouteAssignment,
    RouteStop,
    TransportRegistration,
    FeeVerification,
    Challan,
    Notification,
)

# A held seat is normally payable until the semester's registration deadline.
# But a seat freed close to (or after) that deadline would leave the promoted
# student no usable time, so they always get at least this many days.
SEAT_OFFER_GRACE_DAYS = 5

# Fallback when a semester has no deadline set at all.
SEAT_OFFER_HOURS = SEAT_OFFER_GRACE_DAYS * 24

# Last-resort fee if a semester somehow has none set. The real amount lives on
# Semester.transport_fee, which an admin controls.
DEFAULT_FEE_AMOUNT = 5000


def fee_for_semester(semester):
    """The transport fee an admin set for this semester."""
    amount = getattr(semester, "transport_fee", None)
    return amount if amount else DEFAULT_FEE_AMOUNT


# ── Promotion suppression ────────────────────────────────────────────────────
# Reassigning a student deletes their allocation and immediately creates
# another. Without this guard the post_delete receiver would hand the
# just-freed seat to a waitlisted student mid-reassign, and the student being
# moved could end up with nothing.
_local = threading.local()


def promotion_suppressed():
    return getattr(_local, "suppress", False)


@contextlib.contextmanager
def suppress_promotion():
    previous = getattr(_local, "suppress", False)
    _local.suppress = True
    try:
        yield
    finally:
        _local.suppress = previous


# ── Queue helpers ────────────────────────────────────────────────────────────

def _waiting_queryset(route, semester):
    return Waitlist.objects.filter(
        registration__route=route,
        registration__semester=semester,
        status="waiting",
    ).order_by("position", "added_at")


def reindex_waitlist(route, semester):
    """Renumber a route's queue to a contiguous 1..n, preserving order."""
    for index, entry in enumerate(_waiting_queryset(route, semester), start=1):
        if entry.position != index:
            Waitlist.objects.filter(pk=entry.pk).update(position=index)


def waitlist_summary(registration):
    """{position, total, ...} for a student's queue, or None if not queued."""
    entry = Waitlist.objects.filter(registration=registration).first()
    if not entry or entry.status not in ("waiting", "offered"):
        return None
    total = _waiting_queryset(registration.route, registration.semester).count()
    return {
        "position": entry.position,
        "total": max(total, entry.position),
        "status": entry.status,
        "offer_expires_at": entry.offer_expires_at,
    }


def _remove_waitlist_entry(registration):
    entry = Waitlist.objects.filter(registration=registration).first()
    if not entry:
        return
    route, semester = registration.route, registration.semester
    entry.delete()
    reindex_waitlist(route, semester)


# ── Seat capacity ────────────────────────────────────────────────────────────

def _get_next_available_seat_number(route_assignment):
    """
    The lowest free seat number on this bus, or None when it is full.

    Capacity is judged by how many students are already seated, not by which
    seat numbers happen to be in use - the two are not the same thing. A row
    whose seat_number falls outside the current capacity (left behind when an
    admin lowers a bus's capacity, or written straight through the seat
    allocation endpoint) leaves a gap inside the 1..capacity range, and the old
    number-only scan handed that gap out, seating a third student on a two-seat
    bus. Counting rows first closes that hole.
    """
    occupied_seats = list(
        SeatAllocation.objects.filter(route_assignment=route_assignment)
        .values_list("seat_number", flat=True)
    )
    capacity = route_assignment.bus.capacity
    if len(occupied_seats) >= capacity:
        return None

    taken = set(occupied_seats)
    for seat_number in range(1, capacity + 1):
        if seat_number not in taken:
            return seat_number
    return None


def seats_free_on_assignment(assignment):
    """Seats still free on one bus. Never negative, even if capacity was cut."""
    taken = SeatAllocation.objects.filter(route_assignment=assignment).count()
    return max(assignment.bus.capacity - taken, 0)


def free_seats_on_route(route, semester):
    """Seats still free across every active assignment for this route."""
    assignments = RouteAssignment.objects.filter(
        route=route, semester=semester, is_active=True, bus__is_active=True
    ).select_related("bus")
    return sum(seats_free_on_assignment(assignment) for assignment in assignments)


def pick_route_for_stop(stop, semester):
    """
    Choose which route serves a student, given only their stop.

    Students pick a stop, not a route. When several routes serve that stop we
    pick one that can actually seat them; only if every option is full does it
    fall back to the shortest queue, so a waitlisted student waits behind as
    few people as possible.

    Returns (route_stop, has_free_seat) or (None, False).
    """
    candidates = list(
        RouteStop.objects.filter(
            stop=stop,
            route__is_active=True,
            route__status="published",
            route__routeassignment__semester=semester,
            route__routeassignment__is_active=True,
        )
        .select_related("route")
        .distinct()
    )
    if not candidates:
        return None, False

    with_capacity = [(rs, free_seats_on_route(rs.route, semester)) for rs in candidates]
    seated = [(rs, free) for rs, free in with_capacity if free > 0]
    if seated:
        # Most headroom first, so registrations spread across buses instead of
        # filling one and immediately queueing on it.
        seated.sort(key=lambda pair: pair[1], reverse=True)
        return seated[0][0], True

    candidates.sort(key=lambda rs: _waiting_queryset(rs.route, semester).count())
    return candidates[0], False


# ── Challan issuing ──────────────────────────────────────────────────────────

def compute_payment_due(semester, now=None):
    """
    When must this student pay?

    The semester deadline, or SEAT_OFFER_GRACE_DAYS from now — whichever is
    later. So a student promoted a month early pays by the deadline, while one
    promoted two days before it still gets a full grace period rather than an
    unusable window.
    """
    now = now or timezone.now()
    grace = now + timedelta(days=SEAT_OFFER_GRACE_DAYS)
    deadline = getattr(semester, "registration_deadline", None)
    if deadline is None:
        return grace
    return max(deadline, grace)


def issue_challan(transport_registration, amount=None):
    """
    Create (or refresh) the challan for a held seat and start the payment clock.

    Only ever called once a seat exists — this is the guarantee that nobody
    pays for a seat they do not have.
    """
    semester = transport_registration.semester
    due_at = compute_payment_due(semester)
    fee = amount or fee_for_semester(semester)

    challan, created = Challan.objects.get_or_create(
        registration=transport_registration,
        student=transport_registration.student,
        defaults={
            "amount": fee,
            "status": "unpaid",
            "payment_due_at": due_at,
        },
    )
    if not created and challan.status != "paid":
        # Keep an unpaid challan in step with the current fee and deadline.
        challan.amount = fee
        challan.payment_due_at = due_at
        challan.save(update_fields=["amount", "payment_due_at"])

    if transport_registration.fee_amount != fee:
        transport_registration.fee_amount = fee
        transport_registration.save(update_fields=["fee_amount"])

    return challan, due_at


def _transport_registration_for(registration):
    return TransportRegistration.objects.filter(
        student=registration.student, semester=registration.semester
    ).order_by("-created_at").first()


def payment_settled(registration):
    """
    Has this student actually paid for the seat?

    Holding a seat is not the same as owning it: until the fee is paid the hold
    can still expire. Reporting such a seat as "Confirmed" contradicts the
    countdown shown to the student, so status is derived from payment instead
    of being set optimistically at allocation time.
    """
    if FeeVerification.objects.filter(
        student=registration.student,
        semester=registration.semester,
        is_verified=True,
    ).exists():
        return True

    transport_registration = _transport_registration_for(registration)
    if transport_registration and Challan.objects.filter(
        registration=transport_registration, status="paid"
    ).exists():
        return True

    return False


# ── Allocation ───────────────────────────────────────────────────────────────

def allocate_seat_on_assignment(registration, assignment):
    """Allocate a seat on a specific active route assignment."""
    if SeatAllocation.objects.filter(registration=registration).exists():
        return "Seat already allocated"

    if assignment.route_id != registration.route_id or assignment.semester_id != registration.semester_id:
        return "Assignment does not match student's route and semester"

    if not assignment.is_active:
        return "Route assignment is inactive"

    if not assignment.bus.is_active:
        return "Assigned bus is inactive"

    with transaction.atomic():
        locked_assignment = (
            RouteAssignment.objects.select_for_update()
            .select_related("bus").get(pk=assignment.pk)
        )

        seat_number = _get_next_available_seat_number(locked_assignment)
        if seat_number is None:
            return "Bus is full"

        SeatAllocation.objects.create(
            registration=registration,
            route_assignment=locked_assignment,
            seat_number=seat_number,
        )

    _remove_waitlist_entry(registration)

    settled = payment_settled(registration)
    registration.status = "Confirmed" if settled else "Seat Held"
    registration.save(update_fields=["status", "updated_at"])

    Notification.objects.create(
        user=registration.student.user,
        title="Seat Allocation Update",
        message=(
            f"Your seat has been allocated. Seat No: {seat_number}"
            if settled else
            f"Seat No: {seat_number} is being held for you. It is confirmed "
            f"once the transport fee is paid."
        ),
        type="info",
    )

    return "Seat Allocated"


def reassign_seat_on_assignment(registration, assignment):
    """Move an already allocated student to another active assignment."""
    current_allocation = SeatAllocation.objects.select_related("route_assignment").filter(
        registration=registration
    ).first()
    if not current_allocation:
        return "No seat allocated for this registration"

    if assignment.route_id != registration.route_id or assignment.semester_id != registration.semester_id:
        return "Assignment does not match student's route and semester"

    if not assignment.is_active:
        return "Route assignment is inactive"

    if not assignment.bus.is_active:
        return "Assigned bus is inactive"

    if current_allocation.route_assignment_id == assignment.id:
        return "Student is already assigned to this bus"

    # The delete below must not trigger a promotion into the seat this student
    # is being moved out of, or they could lose it to the queue mid-move.
    with suppress_promotion():
        with transaction.atomic():
            assignment_ids = sorted([current_allocation.route_assignment_id, assignment.id])
            locked_assignments = {
                item.id: item
                for item in RouteAssignment.objects.select_for_update()
                .select_related("bus").filter(id__in=assignment_ids)
            }

            target_assignment = locked_assignments.get(assignment.id)
            if not target_assignment or not target_assignment.is_active or not target_assignment.bus.is_active:
                return "Route assignment is inactive"

            seat_number = _get_next_available_seat_number(target_assignment)
            if seat_number is None:
                return "Bus is full"

            SeatAllocation.objects.filter(pk=current_allocation.pk).delete()
            SeatAllocation.objects.create(
                registration=registration,
                route_assignment=target_assignment,
                seat_number=seat_number,
            )

    Notification.objects.create(
        user=registration.student.user,
        title="Seat Allocation Update",
        message=(
            f"Your seat has been changed to bus {assignment.bus.bus_number}. "
            f"New seat number: {seat_number}"
        ),
        type="info",
    )

    return "Seat Reassigned"


def add_to_waitlist(registration):
    """
    Queue a student for a route. No challan is created here — that is the
    entire point of the waitlist.
    """
    existing = Waitlist.objects.filter(registration=registration).first()
    if existing and existing.status in ("waiting", "offered"):
        return existing

    with transaction.atomic():
        # Lock the queue so two simultaneous registrations cannot be handed the
        # same position, which the old .count() + 1 allowed.
        last = (
            Waitlist.objects.select_for_update()
            .filter(
                registration__route=registration.route,
                registration__semester=registration.semester,
            )
            .order_by("-position")
            .first()
        )
        next_position = (last.position + 1) if last else 1

        if existing:
            existing.position = next_position
            existing.status = "waiting"
            existing.offered_at = None
            existing.offer_expires_at = None
            existing.save(update_fields=["position", "status", "offered_at", "offer_expires_at"])
            entry = existing
        else:
            entry = Waitlist.objects.create(
                registration=registration,
                position=next_position,
                status="waiting",
            )

    registration.status = "Waitlisted"
    registration.save(update_fields=["status", "updated_at"])

    transport_registration = _transport_registration_for(registration)
    if transport_registration:
        transport_registration.status = "Waitlisted"
        transport_registration.save(update_fields=["status"])

    total = _waiting_queryset(registration.route, registration.semester).count()
    Notification.objects.create(
        user=registration.student.user,
        title="You are on the waiting list",
        message=(
            f"Route {registration.route.name} is currently full. You are number "
            f"{entry.position} of {total} in the queue. You have not been charged — "
            f"a challan is only issued once a seat is confirmed for you."
        ),
        type="warning",
    )
    return entry


def promote_next_from_waitlist(route, semester):
    """
    Give a freed seat to the student at the front of the queue.

    Called whenever a seat is released. Issues their challan, starts the
    48-hour payment clock and notifies them. Returns the promoted
    SemesterRegistration, or None if the queue is empty or no seat is free.
    """
    entry = _waiting_queryset(route, semester).select_related(
        "registration__student__user"
    ).first()
    if not entry:
        return None

    assignments = list(
        RouteAssignment.objects.filter(
            route=route, semester=semester, is_active=True, bus__is_active=True
        ).select_related("bus")
    )
    if not assignments:
        return None
    assignments.sort(key=lambda a: seats_free_on_assignment(a), reverse=True)

    registration = entry.registration
    result = "Bus is full"
    for assignment in assignments:
        result = allocate_seat_on_assignment(registration, assignment)
        if result != "Bus is full":
            break
    if result != "Seat Allocated":
        return None

    transport_registration = _transport_registration_for(registration)
    due_at = None
    if transport_registration:
        _, due_at = issue_challan(transport_registration)
        transport_registration.status = "Seat Held"
        transport_registration.save(update_fields=["status"])

    seat = SeatAllocation.objects.filter(registration=registration).first()
    deadline_text = (
        f" Please pay by {timezone.localtime(due_at).strftime('%d %b %Y, %H:%M')} "
        f"or the seat will pass to the next student on the list."
        if due_at else ""
    )
    Notification.objects.create(
        user=registration.student.user,
        title="A seat is now available for you",
        message=(
            f"A seat has opened on route {route.name} and has been reserved for you"
            + (f" (Seat No: {seat.seat_number})." if seat else ".")
            + deadline_text
        ),
        type="warning",
    )
    return registration


def release_seat(registration):
    """
    Free a student's seat. The post_delete receiver promotes the next student.
    """
    allocation = SeatAllocation.objects.filter(registration=registration).first()
    if not allocation:
        return False
    allocation.delete()
    return True


def allocate_seat_for_student(registration):
    """
    Try to seat a student; queue them if the route is full.

    Returns one of: "Seat Allocated", "Added to Waitlist",
    "Seat already allocated", "Already on waitlist", "No active bus assignment".
    """
    route = registration.route
    semester = registration.semester

    if SeatAllocation.objects.filter(registration=registration).exists():
        return "Seat already allocated"

    existing = Waitlist.objects.filter(registration=registration).first()
    if existing and existing.status in ("waiting", "offered"):
        return "Already on waitlist"

    # Every bus on the route, emptiest first. Trying only the first assignment
    # queued students behind a full bus while a second bus on the same route
    # still had room - and free_seats_on_route(), which the registration flow
    # uses to decide whether a seat exists at all, counts every bus.
    assignments = list(
        RouteAssignment.objects.filter(
            route=route, semester=semester, is_active=True, bus__is_active=True
        ).select_related("bus")
    )

    if not assignments:
        return "No active bus assignment"

    assignments.sort(key=lambda a: seats_free_on_assignment(a), reverse=True)

    last_result = "Bus is full"
    for assignment in assignments:
        last_result = allocate_seat_on_assignment(registration, assignment)
        if last_result != "Bus is full":
            return last_result

    add_to_waitlist(registration)
    return "Added to Waitlist"
