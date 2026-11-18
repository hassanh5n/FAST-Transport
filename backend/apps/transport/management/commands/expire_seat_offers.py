"""
Release seats whose payment deadline has passed.

This already runs on its own from API traffic (offer_expiry.py, called by
SemesterRolloverMiddleware). Use the command to run it by hand or from cron:

    python manage.py expire_seat_offers --settings=config.settings.prod

Use --dry-run to see what would be released without changing anything.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.transport.offer_expiry import expire_overdue_offers


def _label(challan):
    registration = challan.registration
    route = registration.route.name if registration.route else "no route"
    due = timezone.localtime(challan.payment_due_at)
    return f"{registration.student.display_id} — {route} (due {due:%d %b %H:%M})"


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
        closed, challans = expire_overdue_offers(dry_run=dry_run)

        for semester in closed:
            deadline = timezone.localtime(semester.registration_deadline)
            if dry_run:
                self.stdout.write(f"[dry-run] would close registration for {semester}")
            else:
                self.stdout.write(self.style.WARNING(
                    f"Closed registration for {semester} (deadline {deadline:%d %b %Y %H:%M})"
                ))

        if not challans:
            self.stdout.write("No expired seat offers.")
            return

        for challan in challans:
            if dry_run:
                self.stdout.write(f"[dry-run] would release: {_label(challan)}")
            else:
                self.stdout.write(self.style.WARNING(f"Released: {_label(challan)}"))

        if dry_run:
            self.stdout.write(f"{len(challans)} offer(s) would be released.")
        else:
            self.stdout.write(self.style.SUCCESS(f"Released {len(challans)} expired seat offer(s)."))
