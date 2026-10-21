"""Route overview: one row per student, and counters that match the bus."""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from .models import (
    AdminProfile, Bus, Driver, Route, RouteAssignment, RouteStop, SeatAllocation,
    Semester, SemesterRegistration, Stop, StudentProfile, TransportRegistration,
)


class RouteOverviewTests(APITestCase):
    def setUp(self):
        boss = User.objects.create_user("boss", password="Str0ng!pass9", is_staff=True)
        AdminProfile.objects.create(user=boss, is_super_admin=True)
        self.client.force_authenticate(boss)

        self.semester = Semester.objects.create(name="Fall 2026", year=2026, is_active=True)
        self.route = Route.objects.create(name="R-1")
        stop = Stop.objects.create(name="Usman Ghani Masjid", latitude="24.9", longitude="67.1")
        RouteStop.objects.create(route=self.route, stop=stop, stop_order=1)
        assignment = RouteAssignment.objects.create(
            route=self.route, semester=self.semester,
            bus=Bus.objects.create(bus_number="GHI-789", capacity=30),
            driver=Driver.objects.create(name="Suhaib"),
        )

        def person(username, roll=None, faculty=False):
            user = User.objects.create_user(username, first_name=username.title())
            return StudentProfile.objects.create(user=user, roll_number=roll, user_type=int(faculty))

        def register(profile, status, seat=None):
            reg = TransportRegistration.objects.create(
                student=profile, semester=self.semester, stop=stop, route=self.route, status=status,
            )
            if seat:
                sem_reg, _ = SemesterRegistration.objects.get_or_create(
                    student=profile, semester=self.semester, defaults={"route": self.route, "stop": stop},
                )
                SeatAllocation.objects.create(registration=sem_reg, route_assignment=assignment, seat_number=seat)
            return reg

        shayan = person("shayan", "23K-0629")
        self.cancelled = register(shayan, "Cancelled")
        self.current = register(shayan, "Seat Held", seat=1)
        register(person("hassan", "23K-0769"), "Approved", seat=2)
        register(person("aiman", faculty=True), "Approved", seat=3)
        register(person("gone", "23K-0001"), "Cancelled")  # cancelled and never came back

    def test_shows_latest_registration_per_student_and_true_counts(self):
        data = self.client.get(f"/api/routes/{self.route.id}/overview/").data
        rows = {s["name"]: s for s in data["students"]}

        self.assertEqual(len(data["students"]), 4)  # Shayan once, plus Hassan, Aiman, Gone
        self.assertEqual(rows["Shayan"]["registration_id"], self.current.id)
        self.assertEqual((rows["Shayan"]["status"], rows["Shayan"]["seat_number"]), ("Seat Held", 1))
        self.assertEqual((rows["Gone"]["status"], rows["Gone"]["seat_number"]), ("Cancelled", None))

        stats = data["stats"]
        self.assertEqual(stats["registered"], 3)  # the never-returned cancel is not counted
        self.assertEqual(stats["approved"], 2)
        self.assertEqual(stats["pending"], 1)     # the held seat
        self.assertEqual(stats["seats_left"], 27)  # 30 seats, 3 taken
