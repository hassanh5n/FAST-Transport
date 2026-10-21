"""
Release seats whose payment deadline has passed.

A promoted student holds a seat for SEAT_OFFER_HOURS. If they do not pay in
that window the seat is released, which cascades into promoting the next
student in the queue (via the post_delete receiver in signals.py).

Run this on a schedule — e.g. hourly:

    python manage.py expire_seat_offers --settings=config.settings.prod

Use --dry-run to see what would be released without changing anything.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.transport.models import (
    Challan,
    SeatAllocation,
    SemesterRegistration,
    Notification,
)
from apps.transport.models import Semester
from apps.transport.seatallocation import SEAT_OFFER_GRACE_DAYS


class Command(BaseCommand):
    help = "Release held seats whose payment deadline has expired."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be released without releasing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        now = timezone.now()

        # Registration closes automatically once the deadline passes, so an
        # admin forgetting to flip the switch cannot leave it open all term.
        stale = Semester.objects.filter(
            registration_open=True,
            registration_deadline__isnull=False,
            registration_deadline__lt=now,
        )
        for semester in stale:
            if dry_run:
                self.stdout.write(f"[dry-run] would close registration for {semester}")
            else:
                semester.registration_open = False
                semester.save(update_fields=["registration_open"])
                self.stdout.write(self.style.WARNING(
                    f"Closed registration for {semester} (deadline "
                    f"{timezone.localtime(semester.registration_deadline):%d %b %Y %H:%M})"
                ))

        expired = (
            Challan.objects.filter(
                status="unpaid",
                payment_due_at__isnull=False,
                payment_due_at__lt=now,
                registration__status="Seat Held",
            )
            .select_related("registration__student__user", "registration__semester")
        )

        if not expired.exists():
            self.stdout.write("No expired seat offers.")
            return

        released = 0
        for challan in expired:
            transport_registration = challan.registration
            student = transport_registration.student
            semester = transport_registration.semester

            registration = SemesterRegistration.objects.filter(
                student=student, semester=semester
            ).first()
            allocation = (
                SeatAllocation.objects.filter(registration=registration).first()
                if registration else None
            )

            label = (
                f"{student.display_id} — "
                f"{transport_registration.route.name if transport_registration.route else 'no route'} "
                f"(due {timezone.localtime(challan.payment_due_at):%d %b %H:%M})"
            )

            if dry_run:
                self.stdout.write(f"[dry-run] would release: {label}")
                continue

            if allocation:
                # Deleting the allocation fires the promotion receiver, which
                # hands this seat to the next student in the queue.
                allocation.delete()

            transport_registration.status = "Cancelled"
            transport_registration.save(update_fields=["status"])

            if registration:
                registration.status = "Cancelled"
                registration.save(update_fields=["status", "updated_at"])

            Notification.objects.create(
                user=student.user,
                title="Seat offer expired",
                message=(
                    f"Your reserved seat was released because the fee was not paid "
                    f"by the deadline. You have not been charged. You may register "
                    f"again to rejoin the queue while registration remains open."
                ),
                type="warning",
            )
            released += 1
            self.stdout.write(self.style.WARNING(f"Released: {label}"))

        if dry_run:
            self.stdout.write(f"{expired.count()} offer(s) would be released.")
        else:
            self.stdout.write(self.style.SUCCESS(f"Released {released} expired seat offer(s)."))
