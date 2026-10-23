"""One-click fleet assignment: plan() proposes, apply() saves the chosen rows."""

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from . import auto_assign
from .models import (
    Bus, Contractor, Driver, Route, RouteAssignment, Semester, SemesterRegistration, Stop, StudentProfile,
)
from .serializers import RouteAssignmentSerializer


class AutoAssignTests(TestCase):
    def setUp(self):
        self.semester = Semester.objects.create(name="Fall", year=2026, term="F", is_active=True)
        self.jadoon, _ = Contractor.objects.get_or_create(name="Jadoon")
        self.nadeem, _ = Contractor.objects.get_or_create(name="Nadeem")
        self.stop = Stop.objects.create(name="Gawalia", latitude="24.96", longitude="67.12")
        self.busy = self.route("J Busy", self.jadoon, students=5)
        self.quiet = self.route("J Quiet", self.jadoon, students=1)
        self.n_route = self.route("N One", self.nadeem, students=2)
        self.j_big = Bus.objects.create(bus_number="J-BIG", capacity=3, contractor=self.jadoon, is_active=True)
        self.j_small = Bus.objects.create(bus_number="J-SMALL", capacity=2, contractor=self.jadoon, is_active=True)
        self.j_spare = Bus.objects.create(bus_number="J-SPARE", capacity=2, contractor=self.jadoon, is_active=True)
        self.n_bus = Bus.objects.create(bus_number="N-01", capacity=40, contractor=self.nadeem, is_active=True)
        for name in ("Asad", "Bilal", "Danish"):
            Driver.objects.create(name=name, contractor=self.jadoon)
        Driver.objects.create(name="Iqbal", contractor=self.nadeem)

    def route(self, name, contractor, students):
        route = Route.objects.create(name=name, contractor=contractor, status="published", is_active=True)
        for n in range(students):
            user = User.objects.create_user(username=f"{name}-{n}".replace(" ", ""), password="pass12345")
            student = StudentProfile.objects.create(
                user=user, roll_number=f"{name}-{n}", department="CS", batch="26", phone="0", address="x",
            )
            SemesterRegistration.objects.create(student=student, semester=self.semester, route=route, stop=self.stop)
        return route

    def test_covers_busiest_routes_first_with_the_biggest_buses_of_their_contractor(self):
        result = auto_assign.plan()
        first = {(p["route"], p["bus"]) for p in result["proposals"] if p["reason"] == "No bus yet"}
        self.assertEqual(first, {("J Busy", "J-BIG"), ("J Quiet", "J-SMALL"), ("N One", "N-01")})

    def test_adds_a_bus_where_students_outnumber_seats(self):
        extra = [p for p in auto_assign.plan()["proposals"] if p["reason"] != "No bus yet"]
        # J Busy: 5 students, 3 seats after its first bus, so it gets the spare bus too.
        self.assertEqual([(p["route"], p["bus"], p["reason"]) for p in extra], [("J Busy", "J-SPARE", "2 more students than seats")])

    def test_never_crosses_contractors(self):
        result = auto_assign.plan()
        owners = {b.id: b.contractor_id for b in Bus.objects.all()}
        drivers = {d.id: d.contractor_id for d in Driver.objects.all()}
        for p in result["proposals"]:
            self.assertEqual({owners[p["bus_id"]], drivers[p["driver_id"]]}, {p["contractor"]})

    def test_reports_a_route_it_cannot_cover(self):
        self.n_bus.is_active = False
        self.n_bus.save()
        result = auto_assign.plan()
        self.assertEqual(result["unplaced"], [{"route_id": self.n_route.id, "route": "N One", "reason": "No free bus from this route's contractor."}])
        self.assertIn("Iqbal", [d["name"] for d in result["spare_drivers"]])

    def test_skips_routes_that_already_have_a_bus(self):
        driver = Driver.objects.get(name="Iqbal")
        RouteAssignment.objects.create(route=self.n_route, bus=self.n_bus, driver=driver, semester=self.semester)
        self.assertNotIn("N One", [p["route"] for p in auto_assign.plan()["proposals"]])

    def test_apply_saves_every_row_or_none(self):
        rows = auto_assign.plan()["proposals"]
        clash = dict(rows[0], route_id=rows[1]["route_id"])  # the first row's bus a second time
        with self.assertRaises(auto_assign.AutoAssignError):
            auto_assign.apply(rows + [clash], RouteAssignmentSerializer)
        self.assertFalse(RouteAssignment.objects.exists())

        saved = auto_assign.apply(rows, RouteAssignmentSerializer)
        self.assertEqual(len(saved), len(rows))
        self.assertEqual(auto_assign.plan()["proposals"], [])  # nothing left to do

    def test_endpoints_are_for_admins(self):
        client = APIClient()
        student = User.objects.get(username="JBusy-0")
        client.force_authenticate(student)
        self.assertEqual(client.get("/api/route-assignments/auto-plan/").status_code, 403)

        admin = User.objects.create_user(username="boss", password="pass12345", is_staff=True, is_superuser=True)
        client.force_authenticate(admin)
        plan = client.get("/api/route-assignments/auto-plan/").json()
        keep = [{k: p[k] for k in ("route_id", "bus_id", "driver_id")} for p in plan["proposals"][:2]]
        response = client.post("/api/route-assignments/auto-assign/", {"assignments": keep}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(RouteAssignment.objects.filter(is_active=True).count(), 2)
