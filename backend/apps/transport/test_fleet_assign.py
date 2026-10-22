"""assign_contractor_fleet: each route runs its own contractor's bus and driver."""

import json
import os
import tempfile
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from .models import (
    Bus, Contractor, Driver, Route, RouteAssignment, SeatAllocation, SemesterRegistration,
    Semester, Stop, StudentProfile,
)


class AssignContractorFleetTests(TestCase):
    def setUp(self):
        self.semester = Semester.objects.create(name="Fall", year=2026, term="F", is_active=True)
        self.jadoon, _ = Contractor.objects.get_or_create(name="Jadoon")
        self.nadeem, _ = Contractor.objects.get_or_create(name="Nadeem")
        self.r2 = Route.objects.create(name="Jadoon R-2", contractor=self.jadoon, status="published", is_active=True)
        self.r3 = Route.objects.create(name="Jadoon R-3", contractor=self.jadoon, status="published", is_active=True)
        self.n1 = Route.objects.create(name="Nadeem 1", contractor=self.nadeem, status="published", is_active=True)
        self.j_small = Bus.objects.create(bus_number="J-01", capacity=2, contractor=self.jadoon, is_active=True)
        self.j_big = Bus.objects.create(bus_number="J-02", capacity=40, contractor=self.jadoon, is_active=True)
        self.n_bus = Bus.objects.create(bus_number="N-01", capacity=40, contractor=self.nadeem, is_active=True)
        self.sabir = Driver.objects.create(name="Muhammad Sabir", contractor=self.jadoon)
        self.zeeshan = Driver.objects.create(name="Zeeshan", contractor=self.jadoon)
        self.iqbal = Driver.objects.create(name="Iqbal Khatak", contractor=self.nadeem)

        # R-2 is wrongly run by Nadeem's bus and driver, and has three seats taken.
        self.wrong = RouteAssignment.objects.create(route=self.r2, bus=self.n_bus, driver=self.iqbal, semester=self.semester)
        stop = Stop.objects.create(name="Gawalia", latitude="24.96", longitude="67.12")
        for seat in (1, 2, 3):
            user = User.objects.create_user(username=f"s{seat}", password="pass12345")
            student = StudentProfile.objects.create(user=user, roll_number=f"26K-{seat}", department="CS", batch="26", phone="0", address="x")
            registration = SemesterRegistration.objects.create(student=student, semester=self.semester, route=self.r2, stop=stop, status="Confirmed")
            SeatAllocation.objects.create(registration=registration, route_assignment=self.wrong, seat_number=seat)

        timetable = {"routes": [
            {"operator": "Jadoon", "code": "R-2", "driver": "Sabir"},
            {"operator": "Nadeem", "code": "1", "driver": "Iqbal Khatak"},
        ]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(timetable, handle)
        self.addCleanup(os.remove, handle.name)
        self.timetable = handle.name

    def run_command(self, *args):
        out = StringIO()
        call_command("assign_contractor_fleet", self.timetable, *args, stdout=out)
        return out.getvalue()

    def test_dry_run_changes_nothing(self):
        report = self.run_command()
        self.assertIn("Would save: 1 changed, 2 new", report)
        self.wrong.refresh_from_db()
        self.assertEqual((self.wrong.bus, self.wrong.driver), (self.n_bus, self.iqbal))
        self.assertEqual(RouteAssignment.objects.count(), 1)

    def test_apply_matches_contractors_and_keeps_seats(self):
        self.run_command("--apply")
        self.wrong.refresh_from_db()
        # Fixed in place: Jadoon's bus with room for the 3 seated students, timetable driver.
        self.assertEqual((self.wrong.bus, self.wrong.driver), (self.j_big, self.sabir))
        self.assertEqual(SeatAllocation.objects.filter(route_assignment=self.wrong).count(), 3)

        r3 = RouteAssignment.objects.get(route=self.r3)
        self.assertEqual((r3.bus, r3.driver), (self.j_small, self.zeeshan))
        n1 = RouteAssignment.objects.get(route=self.n1)
        self.assertEqual((n1.bus, n1.driver), (self.n_bus, self.iqbal))
        for assignment in RouteAssignment.objects.all():
            self.assertEqual(
                {assignment.route.contractor_id, assignment.bus.contractor_id, assignment.driver.contractor_id},
                {assignment.route.contractor_id},
            )

        self.assertIn("0 changed, 0 new", self.run_command("--apply"))  # running it again is a no-op
