"""
Release held seats whose payment deadline has passed.

A promoted student holds a seat until their challan's payment_due_at (see
seatallocation.compute_payment_due). If they have not paid by then the seat is
released, and deleting the SeatAllocation fires the promotion receiver in
signals.py, so the next student in the queue gets it.

There is no scheduler in this project, so expire_overdue_offers_if_due() runs
from SemesterRolloverMiddleware on API traffic, at most once per CHECK_INTERVAL
per process. The payment endpoints also refuse an overdue challan
(views/fees.py), so the gap between checks cannot be used to pay late. The
`expire_seat_offers` management command runs the same code by hand or from cron.

Only registrations still in "Seat Held" are touched. An admin who verifies a
fee approves the registration without marking the challan paid, and that
student must keep their seat.
"""
import logging
import threading
import time

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 10 * 60  # seconds between checks from request traffic

_lock = threading.Lock()
_last_check = None  # monotonic time of the last check; None until the first one


def close_past_deadline_registration(now=None, dry_run=False):
    """Switch off registration for semesters whose deadline has passed. Returns those semesters."""
    from .models import Semester

    now = now or timezone.now()
    stale = list(Semester.objects.filter(
        registration_open=True,
        registration_deadline__isnull=False,
        registration_deadline__lt=now,
    ))
    if not dry_run:
        for semester in stale:
            semester.registration_open = False
            semester.save(update_fields=["registration_open"])
    return stale


def overdue_offers(now=None):
    """Unpaid challans past their deadline whose seat is still only held."""
    from .models import Challan

    return Challan.objects.filter(
        status="unpaid",
        payment_due_at__isnull=False,
        payment_due_at__lt=now or timezone.now(),
        registration__status="Seat Held",
    )


def release_offer(challan_id, now=None):
    """
    Release one overdue held seat. Returns the challan, or None if it was paid
    or released in the meantime.

    The challan row is locked and the overdue test repeated under the lock, so
    two server workers (or a worker and the management command) can never
    release, notify or promote twice for the same seat.
    """
    from .models import Notification, SeatAllocation, SemesterRegistration

    with transaction.atomic():
        challan = (
            overdue_offers(now)
            .select_for_update(of=("self",))
            .filter(pk=challan_id)
            .first()
        )
        if challan is None:
            return None

        transport_registration = challan.registration
        student = transport_registration.student
        registration = SemesterRegistration.objects.filter(
            student=student, semester=transport_registration.semester
        ).first()

        if registration:
            # Deleting the allocation fires the promotion receiver, which hands
            # this seat to the next student in the queue once this commits.
            SeatAllocation.objects.filter(registration=registration).delete()
            registration.status = "Cancelled"
            registration.save(update_fields=["status", "updated_at"])

        transport_registration.status = "Cancelled"
        transport_registration.save(update_fields=["status"])

        Notification.objects.create(
            user=student.user,
            title="Seat offer expired",
            message=(
                "Your reserved seat was released because the fee was not paid "
                "by the deadline. You have not been charged. You may register "
                "again to rejoin the queue while registration remains open."
            ),
            type="warning",
        )
    return challan


def expire_overdue_offers(now=None, dry_run=False):
    """
    Close past-deadline registration, then release every overdue held seat.

    Returns (semesters closed, challans released). With dry_run nothing
    changes and the second list is the challans that would be released.
    """
    now = now or timezone.now()
    closed = close_past_deadline_registration(now, dry_run=dry_run)
    due = list(overdue_offers(now).select_related(
        "registration__student__user", "registration__route", "registration__semester",
    ))
    if dry_run:
        return closed, due
    released = [challan for challan in (release_offer(c.pk, now) for c in due) if challan]
    return closed, released


def expire_overdue_offers_if_due():
    """Run expire_overdue_offers() at most once per CHECK_INTERVAL. Never raises."""
    global _last_check
    now = time.monotonic()
    if _last_check is not None and now - _last_check < CHECK_INTERVAL:
        return
    if not _lock.acquire(blocking=False):
        return
    try:
        _last_check = now
        closed, released = expire_overdue_offers()
        for semester in closed:
            logger.info("Closed registration for %s (deadline passed)", semester)
        if released:
            logger.info("Released %d expired seat offer(s)", len(released))
    except Exception:  # a failed tidy-up must never break the request that triggered it
        logger.exception("expire_overdue_offers failed")
    finally:
        _lock.release()
