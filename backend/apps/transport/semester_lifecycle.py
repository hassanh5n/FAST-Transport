"""
Close semesters whose end date has passed.

When a semester ends its transport users go back to being plain site users.
transport_status.py already stops counting an ended semester's registrations the
moment its end date passes; this module makes the records say so too:

  * the semester is switched off (is_active and registration_open cleared), so the
    many lookups that filter on semester__is_active stop finding it;
  * every registration still open in it is marked "Ended";
  * its waitlist is cancelled and unpaid challans can no longer be paid;
  * each affected student gets a notification.

Seat allocations are kept as history. Deleting one would fire the promotion
receiver in signals.py and seat the next waitlisted student in a semester that
is already over.

There is no scheduler in this project, so close_ended_semesters_if_due() is called
by SemesterRolloverMiddleware on API traffic, at most once per CHECK_INTERVAL per
process. The `close_ended_semesters` management command runs the same code for a
cron job or by hand.
"""
import logging
import threading
import time

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .transport_status import CLOSED_STATUSES, REGISTERED_STATUSES

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 15 * 60  # seconds between checks from request traffic

_lock = threading.Lock()
_last_check = None  # monotonic time of the last check; None until the first one


def ended_semesters(today=None):
    """Semesters past their end date that still have something open."""
    from .models import Semester, TransportRegistration

    today = today or timezone.localdate()
    # end_date > start_date: same rule as Semester.has_ended, so a semester left on
    # the default end date (its creation day) is never closed by surprise.
    past = Semester.objects.filter(end_date__lt=today, end_date__gt=F("start_date"))
    with_open = TransportRegistration.objects.filter(semester__in=past).exclude(
        status__in=CLOSED_STATUSES
    ).values("semester_id")
    return past.filter(is_active=True) | past.filter(registration_open=True) | past.filter(id__in=with_open)


NOTIFICATION_BATCH = 1000


def close_semester(semester):
    """Close one ended semester. Returns the number of registrations ended.

    Every step is a set-based UPDATE or a batched INSERT, so the query count does not
    grow with the number of students; only the (user id, status) pairs needed for
    the notifications are read into memory."""
    from .models import Notification, Semester, SemesterRegistration, TransportRegistration, Waitlist

    with transaction.atomic():
        # Lock the row: with several server workers, two can find the same ended
        # semester at once. The second waits here, then finds nothing left open,
        # so no student is notified twice.
        semester = Semester.objects.select_for_update().get(pk=semester.pk)
        open_regs = TransportRegistration.objects.filter(semester=semester).exclude(
            status__in=CLOSED_STATUSES
        )
        recipients = list(open_regs.values_list("student__user_id", "status"))

        # Waitlist first, so nothing below can promote anyone into this semester.
        Waitlist.objects.filter(
            registration__semester=semester, status__in=("waiting", "offered")
        ).update(status="cancelled")
        SemesterRegistration.objects.filter(semester=semester).exclude(
            status__in=CLOSED_STATUSES
        ).update(status="Ended")
        open_regs.update(status="Ended")

        if semester.is_active or semester.registration_open:
            semester.is_active = False
            semester.registration_open = False
            semester.save(update_fields=["is_active", "registration_open"])

        ended = (
            f"{semester.name} is over, so your transport registration for it has "
            f"ended. Register again when registration opens for the next semester."
        )
        unfinished = (
            f"{semester.name} ended before your transport registration was "
            f"completed, so it has been closed. You have not been charged for it. "
            f"Register again when registration opens for the next semester."
        )
        Notification.objects.bulk_create(
            (
                Notification(
                    user_id=user_id,
                    title=f"{semester.name} transport has ended",
                    message=ended if status in REGISTERED_STATUSES else unfinished,
                    type="info",
                )
                for user_id, status in recipients
            ),
            batch_size=NOTIFICATION_BATCH,
        )
    return len(recipients)


def close_ended_semesters(today=None, dry_run=False):
    """Close every ended semester. Returns [(semester, registrations_ended)]."""
    from .models import TransportRegistration

    results = []
    for semester in ended_semesters(today).distinct().order_by("end_date"):
        if dry_run:
            count = TransportRegistration.objects.filter(semester=semester).exclude(
                status__in=CLOSED_STATUSES
            ).count()
        else:
            count = close_semester(semester)
        results.append((semester, count))
    return results


def close_ended_semesters_if_due():
    """Run close_ended_semesters() at most once per CHECK_INTERVAL. Never raises."""
    global _last_check
    now = time.monotonic()
    if _last_check is not None and now - _last_check < CHECK_INTERVAL:
        return
    if not _lock.acquire(blocking=False):
        return
    try:
        _last_check = now
        for semester, count in close_ended_semesters():
            logger.info("Closed ended semester %s (%d registrations ended)", semester, count)
    except Exception:  # a failed tidy-up must never break the request that triggered it
        logger.exception("close_ended_semesters failed")
    finally:
        _lock.release()
