import datetime
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.transport import transport_card
from apps.transport.models import (
    Bus, Challan, Driver, FeeVerification, Route, RouteAssignment, RouteStop, SeatAllocation, Semester,
    SemesterRegistration, Stop, StudentProfile, TransportRegistration,
)

URL = "/api/download-transport-card/"


def _pdf_bytes(res):
    return b"".join(res.streaming_content if res.streaming else [res.content])


class TransportCardContentTests(TestCase):
    """What the card says, checked on the data handed to the renderer."""

    def setUp(self):
        self.user = User.objects.create_user("stu", "stu@nu.edu.pk", "x", first_name="Hassan", last_name="Nafees")
        self.profile = StudentProfile.objects.create(user=self.user, roll_number="23K-0769", department="CS", batch="2023")
        self.semester = Semester.objects.create(
            name="Fall 2026", year=2026, is_active=True,
            start_date=datetime.date(2026, 8, 20), end_date=datetime.date(2027, 1, 15),
        )
        self.route = Route.objects.create(name="Jadoon R-5B")
        self.stop = Stop.objects.create(name="Moti Mahal", latitude=24.9, longitude=67.1)
        RouteStop.objects.create(route=self.route, stop=self.stop, stop_order=1,
                                 morning_eta=datetime.time(7, 20), evening_eta=datetime.time(16, 35))
        bus = Bus.objects.create(bus_number="ABC-123", capacity=40)
        driver = Driver.objects.create(name="Driver")
        self.assignment = RouteAssignment.objects.create(route=self.route, bus=bus, driver=driver, semester=self.semester)
        self.registration = SemesterRegistration.objects.create(
            student=self.profile, semester=self.semester, route=self.route, stop=self.stop, status="Seat Held")
        self.transport_reg = TransportRegistration.objects.create(
            student=self.profile, semester=self.semester, stop=self.stop, route=self.route, status="Seat Held")
        SeatAllocation.objects.create(registration=self.registration, route_assignment=self.assignment, seat_number=2)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _card(self):
        real = transport_card.build_transport_card_pdf
        with mock.patch.object(transport_card, "build_transport_card_pdf", side_effect=real) as spy:
            res = self.client.get(URL)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(_pdf_bytes(res).startswith(b"%PDF"))
        return spy.call_args.args[0]

    def test_unpaid_held_seat_cannot_download(self):
        res = self.client.get(URL)
        self.assertEqual(res.status_code, 403)
        self.assertIn("fee is paid", res.json()["detail"])

    def test_registered_without_a_seat_cannot_download(self):
        SeatAllocation.objects.all().delete()
        Challan.objects.create(registration=self.transport_reg, student=self.profile, amount=50000, status="paid")
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_unregistered_user_cannot_download(self):
        other = User.objects.create_user("new", "new@nu.edu.pk", "x")
        StudentProfile.objects.create(user=other, roll_number="24K-0001")
        client = APIClient()
        client.force_authenticate(other)
        self.assertEqual(client.get(URL).status_code, 403)

    def test_faculty_with_verified_fee_and_no_roll_number_gets_a_pdf(self):
        self.profile.user_type, self.profile.roll_number = StudentProfile.FACULTY, None
        self.profile.save()
        FeeVerification.objects.create(student=self.profile, semester=self.semester, amount=9000, is_verified=True)
        card = self._card()
        self.assertEqual((card.user_type, card.id_value), ("Faculty", ""))

    def test_dashboard_unlocks_the_card_only_after_payment(self):
        self.assertFalse(self.client.get("/api/dashboard/").json()["card_available"])
        Challan.objects.create(registration=self.transport_reg, student=self.profile, amount=50000, status="paid")
        self.assertTrue(self.client.get("/api/dashboard/").json()["card_available"])

    def test_paid_seat_shows_active_with_stop_times_and_validity(self):
        Challan.objects.create(registration=self.transport_reg, student=self.profile, amount=50000, status="paid")
        card = self._card()
        self.assertEqual(card.status, "Active")
        self.assertTrue(card.status_ok)
        self.assertEqual((card.route, card.stop, card.bus), ("Jadoon R-5B", "Moti Mahal", "ABC-123"))
        self.assertEqual((card.morning_eta, card.evening_eta), ("7:20 AM", "4:35 PM"))
        self.assertEqual(card.valid_until, "15 Jan 2027")
        self.assertEqual(card.id_value, "23K-0769")
        self.assertEqual(card.card_number, f"FC-2026-{self.profile.pk:05d}")

    def test_name_outside_the_bundled_font_still_renders(self):
        Challan.objects.create(registration=self.transport_reg, student=self.profile, amount=50000, status="paid")
        self.user.first_name, self.user.last_name = "حسن", "Ali"
        self.user.save()
        self._card()

    def test_blank_timetable_uses_the_same_estimate_as_the_route_map(self):
        Challan.objects.create(registration=self.transport_reg, student=self.profile, amount=50000, status="paid")
        campus = Stop.objects.create(name="FAST Campus", latitude=24.8569, longitude=67.2646, is_campus=True)
        RouteStop.objects.filter(route=self.route).update(morning_eta=None, evening_eta=None)
        RouteStop.objects.create(route=self.route, stop=campus, stop_order=2)
        card = self._card()
        from apps.transport.views.routes import RouteViewSet
        self.route.refresh_from_db()
        stops = RouteViewSet()._map_route_data(self.route)["stops"]  # what /api/routes/map/ sends
        mine = next(s for s in stops if s["id"] == self.stop.pk)
        self.assertTrue(card.morning_eta and card.evening_eta)
        def clock(v):
            h, m = (int(x) for x in v.split(":")[:2])
            return f"{(h % 12) or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"
        self.assertEqual(card.morning_eta, clock(mine["est_morning_eta"]))
        self.assertEqual(card.evening_eta, clock(mine["est_evening_eta"]))
