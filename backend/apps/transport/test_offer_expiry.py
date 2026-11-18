"""
Seat offers expire on their own: an unpaid held seat past its deadline is
released on API traffic and passes to the next student in the queue, and the
student who missed the deadline can no longer pay for it.
"""
import datetime
import io
import time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.transport import offer_expiry
from apps.transport.models import (
    Bus, Challan, Driver, FeeVerification, Notification, Route, RouteAssignment, RouteStop,
    SeatAllocation, Semester, SemesterRegistration, Stop, StudentProfile, TransportRegistration,
    Waitlist,
)


class OfferExpiryFixture(TestCase):
    """One route, one bus with one seat: the first student holds it, the second queues."""

    def setUp(self):
        offer_expiry._last_check = None  # the throttle is per process; start every test fresh
        self.semester = Semester.objects.create(
            name="Fall 2026", is_active=True, registration_open=True,
            start_date=timezone.localdate() - datetime.timedelta(days=10),
            end_date=timezone.localdate() + datetime.timedelta(days=120),
        )
        self.route = Route.objects.create(name="Route A", is_active=True)
        self.stop = Stop.objects.create(name="Stop A", latitude=24.9, longitude=67.1)
        RouteStop.objects.create(route=self.route, stop=self.stop, stop_order=1)
        self.assignment = RouteAssignment.objects.create(
            route=self.route, semester=self.semester, is_active=True,
            bus=Bus.objects.create(bus_number="BUS-1", capacity=1, is_active=True),
            driver=Driver.objects.create(name="Driver 1", is_available=True),
        )
        self.admin = User.objects.create_user("admin", "admin@nu.edu.pk", "x", is_staff=True)

    def tearDown(self):
        offer_expiry._last_check = None

    def student(self, roll):
        user = User.objects.create_user(roll, f"{roll}@nu.edu.pk", "x")
        return StudentProfile.objects.create(user=user, roll_number=roll)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def register(self, profile):
        res = self.client_for(profile.user).post(
            "/api/transport-registrations/",
            {"stop_id": self.stop.id, "semester_id": self.semester.id}, format="json",
        )
        self.assertEqual(res.status_code, 201, res.content)
        return TransportRegistration.objects.get(student=profile, semester=self.semester)

    def make_overdue(self, registration, hours=1):
        Challan.objects.filter(registration=registration).update(
            payment_due_at=timezone.now() - datetime.timedelta(hours=hours))

    def holder_and_queue(self):
        """First student holds the only seat, second is waitlisted."""
        holder, queued = self.student("24K-0001"), self.student("24K-0002")
        holder_reg = self.register(holder)
        queued_reg = self.register(queued)
        self.assertEqual(holder_reg.status, "Seat Held")
        self.assertEqual(queued_reg.status, "Waitlisted")
        self.assertFalse(Challan.objects.filter(registration=queued_reg).exists())
        return holder, holder_reg, queued, queued_reg

    def hit_api(self, user, interval_passed=True):
        """
        Any API request; promotion runs on commit, so execute those callbacks.

        The registrations in the fixture are API traffic too and already used up
        the current check interval, so by default the request is made as if the
        interval had passed. Pass interval_passed=False to test the throttle.
        """
        if interval_passed:
            offer_expiry._last_check = None
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client_for(user).get("/api/user/")
        self.assertEqual(res.status_code, 200)
        return res


class ExpiryWorkflowTests(OfferExpiryFixture):
    def test_overdue_seat_passes_to_next_student_on_api_traffic(self):
        holder, holder_reg, queued, queued_reg = self.holder_and_queue()
        self.make_overdue(holder_reg)

        # Nobody runs a command: an ordinary request from anyone triggers it.
        self.hit_api(queued.user)

        holder_reg.refresh_from_db()
        self.assertEqual(holder_reg.status, "Cancelled")
        self.assertEqual(
            SemesterRegistration.objects.get(student=holder, semester=self.semester).status, "Cancelled")
        self.assertFalse(SeatAllocation.objects.filter(registration__student=holder).exists())
        self.assertTrue(Notification.objects.filter(user=holder.user, title="Seat offer expired").exists())

        queued_reg.refresh_from_db()
        self.assertEqual(queued_reg.status, "Seat Held")
        self.assertTrue(SeatAllocation.objects.filter(
            registration__student=queued, route_assignment=self.assignment).exists())
        challan = Challan.objects.get(registration=queued_reg)
        self.assertEqual(challan.status, "unpaid")
        self.assertGreater(challan.payment_due_at, timezone.now())
        self.assertTrue(Notification.objects.filter(
            user=queued.user, title="A seat is now available for you").exists())
        self.assertFalse(Waitlist.objects.filter(registration__student=queued, status="waiting").exists())

    def test_promoted_student_can_pay_and_is_approved(self):
        holder, holder_reg, queued, queued_reg = self.holder_and_queue()
        self.make_overdue(holder_reg)
        self.hit_api(queued.user)

        res = self.client_for(queued.user).post(f"/api/transport-registrations/{queued_reg.pk}/challan/pay/")

        self.assertEqual(res.status_code, 200, res.content)
        queued_reg.refresh_from_db()
        self.assertEqual(queued_reg.status, "Approved")
        self.assertEqual(
            SemesterRegistration.objects.get(student=queued, semester=self.semester).status, "Confirmed")

    def test_student_who_missed_the_deadline_cannot_pay_after_release(self):
        holder, holder_reg, queued, _ = self.holder_and_queue()
        self.make_overdue(holder_reg)
        self.hit_api(queued.user)

        res = self.client_for(holder.user).post(f"/api/transport-registrations/{holder_reg.pk}/challan/pay/")

        self.assertEqual(res.status_code, 400)
        self.assertEqual(Challan.objects.get(registration=holder_reg).status, "unpaid")

    def test_running_again_releases_and_notifies_nothing_more(self):
        _, holder_reg, queued, _ = self.holder_and_queue()
        self.make_overdue(holder_reg)
        self.hit_api(queued.user)
        notifications = Notification.objects.count()

        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(offer_expiry.expire_overdue_offers(), ([], []))
        self.assertEqual(Notification.objects.count(), notifications)


class LatePaymentGuardTests(OfferExpiryFixture):
    """The guard holds even in the window before the next expiry check."""

    def setUp(self):
        super().setUp()
        self.holder, self.holder_reg, _, _ = self.holder_and_queue()
        self.make_overdue(self.holder_reg)
        offer_expiry._last_check = time.monotonic()  # a check just ran, so none runs now

    def test_overdue_challan_cannot_be_paid(self):
        res = self.client_for(self.holder.user).post(
            f"/api/transport-registrations/{self.holder_reg.pk}/challan/pay/")
        self.assertEqual(res.status_code, 400)
        self.assertIn("deadline", res.json()["detail"])
        self.assertEqual(Challan.objects.get(registration=self.holder_reg).status, "unpaid")
        # The guard refuses the payment; releasing the seat is the expiry job's work.
        self.assertTrue(SeatAllocation.objects.filter(registration__student=self.holder).exists())

    def test_overdue_challan_cannot_start_a_card_payment(self):
        res = self.client_for(self.holder.user).post(
            f"/api/transport-registrations/{self.holder_reg.pk}/create-payment-intent/")
        self.assertEqual(res.status_code, 400)
        self.assertIn("deadline", res.json()["detail"])

    def test_seat_within_deadline_can_still_be_paid(self):
        Challan.objects.filter(registration=self.holder_reg).update(
            payment_due_at=timezone.now() + datetime.timedelta(hours=1))
        res = self.client_for(self.holder.user).post(
            f"/api/transport-registrations/{self.holder_reg.pk}/challan/pay/")
        self.assertEqual(res.status_code, 200, res.content)


class WhatExpiryLeavesAloneTests(OfferExpiryFixture):
    def test_seat_not_yet_due_is_kept(self):
        _, holder_reg, queued, _ = self.holder_and_queue()
        self.hit_api(queued.user)
        holder_reg.refresh_from_db()
        self.assertEqual(holder_reg.status, "Seat Held")

    def test_paid_seat_is_kept_even_with_an_old_deadline(self):
        holder, holder_reg, queued, _ = self.holder_and_queue()
        self.client_for(holder.user).post(f"/api/transport-registrations/{holder_reg.pk}/challan/pay/")
        self.make_overdue(holder_reg)
        self.hit_api(queued.user)
        holder_reg.refresh_from_db()
        self.assertEqual(holder_reg.status, "Approved")
        self.assertTrue(SeatAllocation.objects.filter(registration__student=holder).exists())

    def test_seat_verified_by_the_office_is_kept(self):
        # verify_fee approves the registration but leaves the challan "unpaid".
        holder, holder_reg, queued, _ = self.holder_and_queue()
        fee = FeeVerification.objects.create(
            student=holder, semester=self.semester, amount=50000, challan_number="CHN-1")
        res = self.client_for(self.admin).post(f"/api/fee-verifications/{fee.id}/verify/")
        self.assertEqual(res.status_code, 200)
        self.make_overdue(holder_reg)

        self.hit_api(queued.user)

        holder_reg.refresh_from_db()
        self.assertEqual(holder_reg.status, "Approved")
        self.assertTrue(SeatAllocation.objects.filter(registration__student=holder).exists())


class ThrottleAndSafetyTests(OfferExpiryFixture):
    def test_checks_at_most_once_per_interval(self):
        _, holder_reg, queued, _ = self.holder_and_queue()
        self.hit_api(queued.user)  # a check runs: nothing due yet
        self.make_overdue(holder_reg)

        self.hit_api(queued.user, interval_passed=False)  # inside the interval: skipped
        holder_reg.refresh_from_db()
        self.assertEqual(holder_reg.status, "Seat Held")

        offer_expiry._last_check -= offer_expiry.CHECK_INTERVAL + 1  # the interval has passed
        self.hit_api(queued.user, interval_passed=False)
        holder_reg.refresh_from_db()
        self.assertEqual(holder_reg.status, "Cancelled")

    def test_a_failing_check_never_breaks_the_request(self):
        holder = self.student("24K-0009")
        with patch("apps.transport.offer_expiry.expire_overdue_offers", side_effect=RuntimeError("db down")):
            with self.assertLogs("apps.transport.offer_expiry", level="ERROR"):
                self.hit_api(holder.user)

    def test_registration_closes_once_its_deadline_passes(self):
        Semester.objects.filter(pk=self.semester.pk).update(
            registration_deadline=timezone.now() - datetime.timedelta(minutes=5))
        self.hit_api(self.student("24K-0010").user)
        self.semester.refresh_from_db()
        self.assertFalse(self.semester.registration_open)


class ExpireSeatOffersCommandTests(OfferExpiryFixture):
    def test_dry_run_reports_and_changes_nothing(self):
        _, holder_reg, _, _ = self.holder_and_queue()
        self.make_overdue(holder_reg)
        out = io.StringIO()
        call_command("expire_seat_offers", "--dry-run", stdout=out)
        self.assertIn("would release: 24K-0001", out.getvalue())
        holder_reg.refresh_from_db()
        self.assertEqual(holder_reg.status, "Seat Held")

    def test_command_releases_and_promotes(self):
        _, holder_reg, queued, queued_reg = self.holder_and_queue()
        self.make_overdue(holder_reg)
        out = io.StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("expire_seat_offers", stdout=out)
        self.assertIn("Released 1 expired seat offer(s).", out.getvalue())
        queued_reg.refresh_from_db()
        self.assertEqual(queued_reg.status, "Seat Held")
