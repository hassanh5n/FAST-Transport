import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.transport import semester_lifecycle
from apps.transport.models import (
    Bus, Challan, Driver, Notification, Route, RouteAssignment, SeatAllocation, Semester,
    SemesterRegistration, Stop, StudentProfile, TransportRegistration, Waitlist,
)
from apps.transport.semester_lifecycle import close_ended_semesters
from apps.transport.transport_status import transport_status_for


def _day(offset):
    return timezone.localdate() + datetime.timedelta(days=offset)


class SemesterFixture(TestCase):
    def setUp(self):
        self.route = Route.objects.create(name="R-1")
        self.stop = Stop.objects.create(name="Stop A", latitude=24.9, longitude=67.1)
        self.ended = Semester.objects.create(
            name="Spring 2026", is_active=True, registration_open=True,
            start_date=_day(-150), end_date=_day(-1),
        )
        self.current = Semester.objects.create(
            name="Fall 2026", is_active=True, start_date=_day(-10), end_date=_day(120),
        )
        self.assignment = RouteAssignment.objects.create(
            route=self.route, semester=self.ended,
            bus=Bus.objects.create(bus_number="ABC-1", capacity=40), driver=Driver.objects.create(name="D"),
        )

    def student(self, roll):
        user = User.objects.create_user(roll, f"{roll}@nu.edu.pk", "x")
        return StudentProfile.objects.create(user=user, roll_number=roll)

    def register(self, profile, semester, status):
        sem_reg = SemesterRegistration.objects.create(
            student=profile, semester=semester, route=self.route, stop=self.stop, status=status)
        reg = TransportRegistration.objects.create(
            student=profile, semester=semester, route=self.route, stop=self.stop, status=status)
        return sem_reg, reg


class TransportStatusTests(SemesterFixture):
    def test_site_user_without_registration_is_none(self):
        self.assertEqual(transport_status_for(self.student("24K-0001"))["status"], "none")

    def test_pending_or_waitlisted_this_semester_is_applying(self):
        for i, status in enumerate(("Pending", "Seat Held", "payment_submitted", "Waitlisted")):
            profile = self.student(f"24K-01{i}")
            self.register(profile, self.current, status)
            self.assertEqual(transport_status_for(profile)["status"], "applying", status)

    def test_approved_this_semester_is_registered(self):
        profile = self.student("24K-0002")
        self.register(profile, self.current, "Approved")
        self.assertEqual(
            transport_status_for(profile),
            {"status": "registered", "semester": "Fall 2026", "registration_status": "Approved"},
        )

    def test_ended_semester_stops_counting_before_the_job_runs(self):
        profile = self.student("24K-0003")
        self.register(profile, self.ended, "Approved")
        self.assertTrue(Semester.objects.get(pk=self.ended.pk).is_active)  # not closed yet
        self.assertEqual(transport_status_for(profile)["status"], "none")

    def test_cancelled_registration_is_none(self):
        profile = self.student("24K-0004")
        self.register(profile, self.current, "Cancelled")
        self.assertEqual(transport_status_for(profile)["status"], "none")

    def test_current_user_payload_carries_transport_status(self):
        profile = self.student("24K-0005")
        self.register(profile, self.current, "Approved")
        client = APIClient()
        client.force_authenticate(profile.user)
        self.assertEqual(client.get("/api/user/").json()["transport_status"]["status"], "registered")

    def test_status_rides_along_in_the_single_user_lookup(self):
        # docs/PERF.md: /api/user/ is one query (~170 ms to Supabase); the status must
        # come with the JWT user lookup, not as a second round trip.
        from rest_framework_simplejwt.tokens import RefreshToken
        profile = self.student("24K-0008")
        self.register(profile, self.current, "Pending")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(profile.user).access_token}")
        with self.assertNumQueries(1):
            body = client.get("/api/user/").json()
        self.assertEqual(body["transport_status"], {"status": "applying", "registration_status": "Pending"})

    def test_admin_can_filter_students_by_status_on_the_server(self):
        plain, applying, approved = self.student("24K-0020"), self.student("24K-0021"), self.student("24K-0022")
        self.register(applying, self.current, "Waitlisted")
        self.register(approved, self.current, "Approved")
        self.register(plain, self.ended, "Approved")  # last semester's rider is a site user now
        admin = User.objects.create_superuser("admin", "admin@nu.edu.pk", "x")
        client = APIClient()
        client.force_authenticate(admin)
        for status, expected in (("none", plain), ("applying", applying), ("registered", approved)):
            body = client.get("/api/students/", {"transport_status": status}).json()
            self.assertEqual([row["id"] for row in body.get("results", body)], [expected.id], status)

    def test_admin_student_list_shows_each_status(self):
        plain, approved = self.student("24K-0006"), self.student("24K-0007")
        self.register(approved, self.current, "Approved")
        admin = User.objects.create_superuser("admin", "admin@nu.edu.pk", "x")
        client = APIClient()
        client.force_authenticate(admin)
        body = client.get("/api/students/").json()
        rows = {row["id"]: row["transport_status"] for row in body.get("results", body)}
        self.assertEqual((rows[plain.id], rows[approved.id]), ("none", "registered"))

    def test_registration_closes_once_the_semester_has_ended(self):
        self.assertFalse(self.ended.accepts_registrations)


class CloseEndedSemesterTests(SemesterFixture):
    def test_ended_semester_is_closed_and_students_revert(self):
        approved = self.student("24K-0010")
        sem_reg, reg = self.register(approved, self.ended, "Approved")
        SeatAllocation.objects.create(registration=sem_reg, route_assignment=self.assignment, seat_number=1)
        waiting = self.student("24K-0011")
        waiting_sem_reg, waiting_reg = self.register(waiting, self.ended, "Waitlisted")
        Waitlist.objects.create(registration=waiting_sem_reg)
        cancelled = self.student("24K-0012")
        _, cancelled_reg = self.register(cancelled, self.ended, "Cancelled")

        results = close_ended_semesters()

        self.assertEqual([(s.pk, n) for s, n in results], [(self.ended.pk, 2)])
        self.ended.refresh_from_db()
        self.assertFalse(self.ended.is_active or self.ended.registration_open)
        for obj in (reg, waiting_reg, sem_reg, waiting_sem_reg):
            obj.refresh_from_db()
            self.assertEqual(obj.status, "Ended")
        cancelled_reg.refresh_from_db()
        self.assertEqual(cancelled_reg.status, "Cancelled")
        self.assertEqual(Waitlist.objects.get().status, "cancelled")
        # Seats stay as history; deleting them would promote the waitlist.
        self.assertEqual(SeatAllocation.objects.count(), 1)
        self.assertEqual(
            set(Notification.objects.values_list("user__username", flat=True)), {"24K-0010", "24K-0011"})
        self.assertEqual(transport_status_for(approved)["status"], "none")

    def test_current_semester_is_left_alone(self):
        profile = self.student("24K-0013")
        _, reg = self.register(profile, self.current, "Approved")
        close_ended_semesters()
        reg.refresh_from_db()
        self.current.refresh_from_db()
        self.assertEqual((reg.status, self.current.is_active), ("Approved", True))

    def test_running_twice_changes_nothing_more(self):
        self.register(self.student("24K-0014"), self.ended, "Approved")
        close_ended_semesters()
        self.assertEqual(close_ended_semesters(), [])
        self.assertEqual(Notification.objects.count(), 1)

    def test_semester_left_on_the_default_end_date_never_ends(self):
        # end_date defaults to the creation day; that is "not set", not "ended".
        unset = Semester.objects.create(
            name="No end date", is_active=True, start_date=_day(-30), end_date=_day(-30))
        profile = self.student("24K-0018")
        _, reg = self.register(profile, unset, "Approved")
        self.assertFalse(unset.has_ended)
        self.assertEqual(transport_status_for(profile)["status"], "registered")
        close_ended_semesters()
        reg.refresh_from_db()
        self.assertEqual(reg.status, "Approved")

    def test_dry_run_changes_nothing(self):
        _, reg = self.register(self.student("24K-0015"), self.ended, "Pending")
        self.assertEqual([n for _, n in close_ended_semesters(dry_run=True)], [1])
        reg.refresh_from_db()
        self.assertEqual(reg.status, "Pending")

    def test_api_traffic_closes_ended_semesters(self):
        profile = self.student("24K-0016")
        _, reg = self.register(profile, self.ended, "Approved")
        semester_lifecycle._last_check = None
        client = APIClient()
        client.force_authenticate(profile.user)
        client.get("/api/user/")
        reg.refresh_from_db()
        self.assertEqual(reg.status, "Ended")

    def test_ended_challan_cannot_be_paid(self):
        profile = self.student("24K-0017")
        _, reg = self.register(profile, self.ended, "Seat Held")
        Challan.objects.create(registration=reg, student=profile, amount=50000)
        client = APIClient()
        client.force_authenticate(profile.user)
        res = client.post(f"/api/transport-registrations/{reg.pk}/challan/pay/")
        self.assertEqual(res.status_code, 400)
        self.assertIn("has ended", res.json()["detail"])
        self.assertEqual(Challan.objects.get().status, "unpaid")
