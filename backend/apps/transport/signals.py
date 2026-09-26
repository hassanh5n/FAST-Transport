from django.db.models.signals import post_save, post_delete
from django.db import transaction
from django.dispatch import receiver
from .models import Route, Stop, RouteStop, Bus, Driver, Semester, RouteAssignment, FeeVerification, SemesterRegistration, BusLocationPing, Notification, User, SeatAllocation
from .seatallocation import (
    allocate_seat_for_student,
    promote_next_from_waitlist,
    promotion_suppressed,
)
from .geofencing import is_off_route
from .emails import send_notification_email
from django.utils import timezone


@receiver(post_save, sender=Notification)
def email_notification_to_user(sender, instance, created, **kwargs):
    """
    Mirror every newly created in-app notification to the recipient's inbox.

    Hooking the model rather than each Notification.objects.create() call site
    means all eight existing sites — and any added later — get email for free.
    Delivery is threaded and fail-silent; see apps/transport/emails.py.
    """
    if created:
        send_notification_email(instance)

def _deactivate_assignments(**filter_kwargs):
    """Set is_active=False on all active RouteAssignments matching the filter."""
    RouteAssignment.objects.filter(is_active=True, **filter_kwargs).update(is_active=False)


@receiver(post_save, sender=Route)
def deactivate_on_route_inactive(sender, instance, **kwargs):
    if not instance.is_active:
        _deactivate_assignments(route=instance)


@receiver(post_save, sender=Bus)
def deactivate_on_bus_inactive(sender, instance, **kwargs):
    if not instance.is_active:
        _deactivate_assignments(bus=instance)


@receiver(post_save, sender=Driver)
def deactivate_on_driver_unavailable(sender, instance, **kwargs):
    if not instance.is_available:
        _deactivate_assignments(driver=instance)


@receiver(post_save, sender=Semester)
def deactivate_on_semester_inactive(sender, instance, **kwargs):
    if not instance.is_active:
        _deactivate_assignments(semester=instance)


@receiver(post_save, sender=Stop)
def invalidate_geometry_after_stop_change(sender, instance, created, **kwargs):
    """A moved/disabled stop invalidates every cached road line that uses it."""
    if not created:
        Route.objects.filter(routestop__stop=instance).update(
            geometry=None,
            geometry_updated_at=None,
        )


@receiver(post_save, sender=RouteStop)
@receiver(post_delete, sender=RouteStop)
def invalidate_geometry_after_route_stop_change(sender, instance, **kwargs):
    Route.objects.filter(pk=instance.route_id).update(
        geometry=None,
        geometry_updated_at=None,
    )

@receiver(post_save, sender=FeeVerification)
def handle_fee_verification(sender, instance, created, **kwargs):
    if instance.is_verified:
        try:
            registration = SemesterRegistration.objects.get(
                student=instance.student,
                semester=instance.semester
            )

            # Avoid duplicate allocation
            if not registration.seatallocation_set.exists():
                allocate_seat_for_student(registration)

        except SemesterRegistration.DoesNotExist:
            pass

@receiver(post_save, sender=BusLocationPing)
def check_bus_geofence(sender, instance, created, **kwargs):
    if not created:
        return
    assignment = RouteAssignment.objects.filter(bus=instance.bus, is_active=True).first()
    if not assignment:
        return

    off_route, distance = is_off_route(instance.latitude, instance.longitude, assignment.route)
    instance.distance_from_route_m = distance
    instance.save(update_fields=["distance_from_route_m"])

    bus = instance.bus
    if off_route and not bus.is_off_route:
        from .rbac import staff_with_module
        for admin in staff_with_module("fleet"):  # only admins who handle the fleet
            Notification.objects.create(
                user=admin, type="alert",
                title=f"Bus {bus.bus_number} is off route",
                message=f"Currently {distance:.0f}m from its assigned route ({assignment.route.name}).",
            )
        bus.is_off_route = True
        bus.last_off_route_alert_at = timezone.now()
        bus.save(update_fields=["is_off_route", "last_off_route_alert_at"])
    elif not off_route and bus.is_off_route:
        bus.is_off_route = False
        bus.save(update_fields=["is_off_route"])


@receiver(post_delete, sender=SeatAllocation)
def promote_waitlist_on_seat_release(sender, instance, **kwargs):
    """
    A freed seat goes to the front of that route's queue.

    This is the mechanism the waitlist previously lacked entirely: positions
    were assigned but nothing ever consumed them, so a queued student waited
    forever even while seats sat empty. Fires on cancellation, admin deletion
    and expired offers alike.

    Skipped during a reassign, where the delete is immediately followed by a
    new allocation for the same student (see suppress_promotion).
    """
    if promotion_suppressed():
        return

    registration = instance.registration
    route = registration.route
    semester = registration.semester
    if not route or not semester:
        return

    # Run after the surrounding transaction commits, so the seat really is free
    # by the time we look for one.
    transaction.on_commit(lambda: promote_next_from_waitlist(route, semester))
