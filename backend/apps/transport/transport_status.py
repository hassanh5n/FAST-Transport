"""
Is this person a transport user right now, or just someone with a site account?

Every signed-up student or faculty member is a site user. They only become a
transport user through a TransportRegistration in the *current* semester: one
that is active and whose end date has not passed. A registration in an ended
semester counts for nothing, so a student falls back to a plain site user the
day their semester ends, even before close_ended_semesters() tidies the rows up.

Three states, kept deliberately coarse so every screen agrees on them:

    none        - site account only; may browse and register
    applying    - registered this semester but not yet confirmed
                  (pending, seat held awaiting payment, payment under review, waitlisted)
    registered  - confirmed transport user for this semester (fee approved)
"""
from django.db.models import F, Q, Subquery
from django.utils import timezone

NONE, APPLYING, REGISTERED = "none", "applying", "registered"

APPLYING_STATUSES = ("Pending", "Seat Held", "payment_submitted", "Waitlisted")
REGISTERED_STATUSES = ("Approved",)
# Registrations in these states never make someone a transport user. "Ended" is
# set by close_ended_semesters() on everything left open when a semester ends.
CLOSED_STATUSES = ("Cancelled", "Rejected", "Ended")


def current_semester_q(prefix="semester__"):
    """Filter for 'belongs to the current semester': active and not past its end date.

    Same rule as Semester.has_ended: an end date not after the start date was never
    set, so that semester stays current until an admin switches it off."""
    return Q(**{f"{prefix}is_active": True}) & (
        Q(**{f"{prefix}end_date__gte": timezone.localdate()})
        | Q(**{f"{prefix}end_date__lte": F(f"{prefix}start_date")})
    )


def classify(registration_status):
    if registration_status in REGISTERED_STATUSES:
        return REGISTERED
    if registration_status in APPLYING_STATUSES:
        return APPLYING
    return NONE


def current_registration(profile):
    """The profile's open TransportRegistration in the current semester, or None."""
    from .models import TransportRegistration

    return (
        TransportRegistration.objects.filter(current_semester_q(), student=profile)
        .exclude(status__in=CLOSED_STATUSES)
        .select_related("semester")
        .order_by("-created_at")
        .first()
    )


def transport_status_for(profile):
    """{status, semester, registration_status} for one profile (one query)."""
    registration = current_registration(profile) if profile else None
    if registration is None:
        return {"status": NONE, "semester": None, "registration_status": None}
    return {
        "status": classify(registration.status),
        "semester": registration.semester.name,
        "registration_status": registration.status,
    }


def registration_status_subquery(**outer):
    """The status of the newest open current-semester registration, as a Subquery to
    annotate onto another query, so lists and the user lookup get it without a query
    of their own (each query is a ~170 ms round trip to Supabase, see docs/PERF.md).

    `outer` says how to reach the student from the outer row, e.g.
    registration_status_subquery(student_id=OuterRef("pk")) on StudentProfile.
    NULL means no open registration, i.e. NONE."""
    from .models import TransportRegistration

    return Subquery(
        TransportRegistration.objects.filter(current_semester_q(), **outer)
        .exclude(status__in=CLOSED_STATUSES)
        .order_by("-created_at")
        .values("status")[:1]
    )


def filter_by_transport_status(queryset, status, field):
    """Keep rows whose annotated registration status (`field`) classifies as `status`."""
    if status == REGISTERED:
        return queryset.filter(**{f"{field}__in": REGISTERED_STATUSES})
    if status == APPLYING:
        return queryset.filter(**{f"{field}__in": APPLYING_STATUSES})
    if status == NONE:
        return queryset.filter(**{f"{field}__isnull": True})
    return queryset


def payload(registration_status):
    """The `transport_status` object sent to the frontend."""
    return {"status": classify(registration_status), "registration_status": registration_status}
