"""
End the transport registrations of every semester whose end date has passed.

Normally this runs by itself on API traffic (SemesterRolloverMiddleware). Run it by
hand, or from a cron job if one is ever added:

    python manage.py close_ended_semesters --settings=config.settings.prod

Use --dry-run to see what would be closed without changing anything.
"""

from django.core.management.base import BaseCommand

from apps.transport.semester_lifecycle import close_ended_semesters


class Command(BaseCommand):
    help = "Close semesters past their end date and revert their transport users to site users."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be closed without closing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        results = close_ended_semesters(dry_run=dry_run)
        if not results:
            self.stdout.write("No ended semesters to close.")
            return
        for semester, count in results:
            verb = "would close" if dry_run else "Closed"
            self.stdout.write(f"{verb} {semester} (ended {semester.end_date}): {count} registration(s) ended")
