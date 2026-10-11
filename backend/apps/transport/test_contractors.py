"""Tests for contractors: assignment guard and route plans carrying the contractor."""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from . import route_plans
from .models import AdminProfile, Bus, Contractor, Driver, Route, RoutePlan, Semester


class ContractorTests(APITestCase):
    def setUp(self):
        boss = User.objects.create_user("boss", password="Str0ng!pass9", is_staff=True)
        AdminProfile.objects.create(user=boss, is_super_admin=True)
        self.client.force_authenticate(boss)
        self.jadoon = Contractor.objects.get(name="Jadoon")  # seeded by migration 0024
        self.nadeem = Contractor.objects.get(name="Nadeem")
        self.semester = Semester.objects.create(name="Fall", is_active=True)

    def assign(self, route, bus, driver):
        return self.client.post("/api/route-assignments/", {
            "route_id": route.id, "bus_id": bus.id, "driver_id": driver.id, "semester_id": self.semester.id,
        })

    def test_contractors_are_listed(self):
        names = [item["name"] for item in self.client.get("/api/contractors/").json()]
        self.assertEqual(names, ["Jadoon", "Nadeem"])

    def test_assignment_must_stay_within_one_contractor(self):
        route = Route.objects.create(name="Jadoon R-17", contractor=self.jadoon)
        nadeem_bus = Bus.objects.create(bus_number="N-1", capacity=40, contractor=self.nadeem)
        driver = Driver.objects.create(name="Ali", contractor=self.jadoon)
        response = self.assign(route, nadeem_bus, driver)
        self.assertEqual(response.status_code, 400)
        self.assertIn("same contractor", str(response.json()))

        jadoon_bus = Bus.objects.create(bus_number="J-1", capacity=40, contractor=self.jadoon)
        self.assertEqual(self.assign(route, jadoon_bus, driver).status_code, 201)
        # A bus with no contractor yet is still allowed.
        other = Route.objects.create(name="Jadoon R-2", contractor=self.jadoon)
        loose = Driver.objects.create(name="Bilal")
        self.assertEqual(self.assign(other, Bus.objects.create(bus_number="X-1", capacity=40), loose).status_code, 201)

    def test_plan_sets_contractor_from_file_or_route_name(self):
        plan = RoutePlan.objects.create(name="Fall 2026", data={"routes": [
            {"name": "Jadoon R-17", "description": "x", "status": "published", "contractor": None, "stops": []},
            {"name": "Express 1", "description": "x", "status": "published", "contractor": "nadeem", "stops": []},
            {"name": "Shuttle", "description": "x", "status": "published", "contractor": None, "stops": []},
        ]})
        route_plans.activate(plan)
        self.assertEqual(Route.objects.get(name="Jadoon R-17").contractor, self.jadoon)
        self.assertEqual(Route.objects.get(name="Express 1").contractor, self.nadeem)
        self.assertIsNone(Route.objects.get(name="Shuttle").contractor)

        snapshot = route_plans.snapshot_live()
        self.assertEqual({r["name"]: r["contractor"] for r in snapshot["routes"]}["Express 1"], "Nadeem")
        self.assertIn("contractor", route_plans.export_csv(plan).splitlines()[0])

    def test_unknown_contractor_blocks_activation(self):
        plan = RoutePlan.objects.create(name="Bad", data={"routes": [
            {"name": "R1", "description": "x", "status": "published", "contractor": "Nobody", "stops": []},
        ]})
        with self.assertRaises(route_plans.PlanError):
            route_plans.activate(plan)
