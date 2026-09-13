"""
Make over-allocation impossible, and clean up the rows that already exist.

Before this migration nothing stopped a bus carrying more students than it has
seats: capacity was judged by which seat *numbers* were in use, so any row
numbered outside the current capacity opened a gap that was handed out again,
and no database constraint backed the check. Routes could therefore show
"3/2 seats taken".

The data step repairs existing rows, keeping the students who were seated
first and returning the extras to the waitlist rather than silently dropping
them. The schema step then adds the two constraints that prevent a repeat.
"""
from django.db import migrations, models


def repair_seat_allocations(apps, schema_editor):
    SeatAllocation = apps.get_model("transport", "SeatAllocation")
    RouteAssignment = apps.get_model("transport", "RouteAssignment")
    Waitlist = apps.get_model("transport", "Waitlist")
    SemesterRegistration = apps.get_model("transport", "SemesterRegistration")

    bumped = []

    # 1. One seat per student: keep the earliest, drop the rest outright.
    seen = set()
    for allocation in SeatAllocation.objects.order_by("allocated_at", "id"):
        if allocation.registration_id in seen:
            allocation.delete()
        else:
            seen.add(allocation.registration_id)

    # 2. One student per seat, and never more students than the bus holds.
    for assignment in RouteAssignment.objects.select_related("bus"):
        capacity = assignment.bus.capacity
        allocations = list(
            SeatAllocation.objects.filter(route_assignment=assignment)
            .order_by("allocated_at", "id")
        )

        keep, overflow = allocations[:capacity], allocations[capacity:]

        for allocation in overflow:
            bumped.append(allocation.registration_id)
            allocation.delete()

        # Renumber what remains as 1..n, so no row sits outside capacity and no
        # number is used twice. Done in two passes, via temporary negative
        # numbers, so the new unique constraint cannot be tripped mid-renumber.
        for index, allocation in enumerate(keep, start=1):
            if allocation.seat_number != index:
                allocation.seat_number = -allocation.id
                allocation.save(update_fields=["seat_number"])
        for index, allocation in enumerate(keep, start=1):
            if allocation.seat_number != index:
                allocation.seat_number = index
                allocation.save(update_fields=["seat_number"])

    # 3. Students who lost a seat they should never have had go to the back of
    #    their route's queue instead of disappearing.
    for registration_id in bumped:
        entry = Waitlist.objects.filter(registration_id=registration_id).first()
        if entry:
            if entry.status not in ("waiting", "offered"):
                entry.status = "waiting"
                entry.save(update_fields=["status"])
            continue
        registration = SemesterRegistration.objects.filter(pk=registration_id).first()
        if registration is None:
            continue
        position = Waitlist.objects.filter(
            registration__route_id=registration.route_id,
            registration__semester_id=registration.semester_id,
            status="waiting",
        ).count() + 1
        Waitlist.objects.create(
            registration_id=registration_id,
            position=position,
            status="waiting",
        )


def noop(apps, schema_editor):
    """Repaired data is correct data; there is nothing to undo."""


class Migration(migrations.Migration):

    dependencies = [
        ("transport", "0018_merge_20260904_1747"),
    ]

    operations = [
        migrations.RunPython(repair_seat_allocations, noop),
        migrations.AddConstraint(
            model_name="seatallocation",
            constraint=models.UniqueConstraint(
                fields=("route_assignment", "seat_number"),
                name="uniq_seat_number_per_assignment",
            ),
        ),
        migrations.AddConstraint(
            model_name="seatallocation",
            constraint=models.UniqueConstraint(
                fields=("registration",),
                name="uniq_seat_per_registration",
            ),
        ),
    ]
