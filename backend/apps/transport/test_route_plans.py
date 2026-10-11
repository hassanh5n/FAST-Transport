"""Tests for route plans: file round trip, activation, and students left unserved."""
import datetime
import json

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase

from . import route_plans
from .models import (
    AdminProfile, Bus, Driver, Notification, Route, RouteAssignment, RoutePlan, RouteStop,
    SeatAllocation, Semester, SemesterRegistration, Stop, StudentProfile, TransportRegistration,
)

# R1 loses stop B and gets a new ETA, R2 is dropped, R3 is new with a new stop.
PLAN_B = {
    "plan": {"name": "Plan B", "description": "Winter"},
    "routes": [
        {"name": "  r1 ", "status": "published", "stops": [
            {"name": "Stop A", "latitude": 24.90, "longitude": 67.00, "morning_eta": "8:00"},
        ]},
        {"name": "R3", "stops": [
            {"name": "Stop D", "latitude": 24.99, "longitude": 67.09, "evening_eta": "17:30"},
        ]},
    ],
}


class RoutePlanTests(APITestCase):
    def setUp(self):
        self.boss = User.objects.create_user("boss", password="Str0ng!pass9", is_staff=True)
        AdminProfile.objects.create(user=self.boss, is_super_admin=True)
        self.client.force_authenticate(self.boss)

        self.a = Stop.objects.create(name="Stop A", latitude="24.900000", longitude="67.000000", address="A road")
        self.b = Stop.objects.create(name="Stop B", latitude="24.910000", longitude="67.010000")
        self.c = Stop.objects.create(name="Stop C", latitude="24.920000", longitude="67.020000")
        self.r1 = Route.objects.create(name="R1", description="First")
        self.r2 = Route.objects.create(name="R2", description="Second")
        RouteStop.objects.create(route=self.r1, stop=self.a, stop_order=1, morning_eta=datetime.time(7, 0))
        RouteStop.objects.create(route=self.r1, stop=self.b, stop_order=2, evening_eta=datetime.time(16, 40))
        RouteStop.objects.create(route=self.r2, stop=self.c, stop_order=1)

        semester = Semester.objects.create(name="Fall", is_active=True)
        self.student_user = User.objects.create_user("stud", password="Str0ng!pass9")
        student = StudentProfile.objects.create(user=self.student_user, roll_number="22K-0001")
        self.assignment = RouteAssignment.objects.create(
            route=self.r1, semester=semester,
            bus=Bus.objects.create(bus_number="B-1", capacity=10),
            driver=Driver.objects.create(name="Driver"),
        )
        TransportRegistration.objects.create(student=student, semester=semester, route=self.r1, stop=self.b, status="Approved")
        registration = SemesterRegistration.objects.create(student=student, semester=semester, route=self.r1, stop=self.b)
        self.seat = SeatAllocation.objects.create(registration=registration, route_assignment=self.assignment, seat_number=1)

        self.current = RoutePlan.objects.get(is_active=True)  # seeded by migration 0023

    def upload(self, name, content):
        return self.client.post("/api/route-plans/import/", {"file": SimpleUploadedFile(name, content.encode())}, format="multipart")

    def stops_of(self, route):
        return [
            (rs.stop.name, route_plans._eta(rs.morning_eta), route_plans._eta(rs.evening_eta))
            for rs in RouteStop.objects.filter(route=route).order_by("stop_order")
        ]

    def test_export_then_import_round_trips(self):
        live = route_plans.snapshot_live()["routes"]
        for kind in ("json", "csv"):
            exported = self.client.get(f"/api/route-plans/{self.current.id}/export/?file={kind}")
            self.assertEqual(exported.status_code, 200)
            res = self.upload(f"plan.{kind}", exported.content.decode("utf-8"))
            self.assertEqual(res.status_code, 201, res.content)
            self.assertEqual((res.data["is_active"], res.data["route_count"], res.data["stop_count"]), (False, 2, 4))  # + campus
            detail = self.client.get(f"/api/route-plans/{res.data['id']}/").data
            # Same routes, now ending at the campus stop the import adds.
            self.assertEqual([{**r, "stops": r["stops"][:-1]} for r in detail["routes"]], live)
            self.assertEqual({r["stops"][-1]["name"] for r in detail["routes"]}, {"FAST NUCES Main Campus"})
            # Importing never touches the live routes.
            preview = self.client.get(f"/api/route-plans/{res.data['id']}/preview/").data
            self.assertEqual((preview["routes"]["updated"], preview["moved_students"]), (["R1", "R2"], []))

    def test_activate_swaps_routes_moves_riders_and_swaps_back(self):
        plan_b = self.upload("b.json", json.dumps(PLAN_B)).data
        self.assertEqual(plan_b["name"], "Plan B")
        self.assertEqual(self.stops_of(self.r1), [("Stop A", "07:00", None), ("Stop B", None, "16:40")])  # untouched so far
        # Importing creates the plan's new stops right away (for the address fill); routes wait for activation.
        self.assertEqual(sorted(s["name"] for s in plan_b["stops"]["created"]), ["FAST NUCES Main Campus", "Stop D"])

        preview = self.client.get(f"/api/route-plans/{plan_b['id']}/preview/").data
        self.assertEqual(preview["routes"], {"created": ["R3"], "updated": ["r1"], "unchanged": 0, "removed": ["R2"], "archived": []})
        moved = preview["moved_students"]
        self.assertEqual([(m["roll_number"], m["from_stop"], m["to_route"], m["to_stop"], m["seat"]) for m in moved],
                         [("22K-0001", "Stop B", "R1", "Stop A", "kept")])
        self.assertEqual(preview["affected_students"], [])
        # A preview writes nothing and notifies nobody.
        self.assertFalse(Route.objects.filter(name="R3").exists())
        self.assertTrue(Route.objects.filter(pk=self.r2.pk).exists())
        self.assertEqual(TransportRegistration.objects.get().stop_id, self.b.id)
        self.assertFalse(Notification.objects.filter(user=self.student_user).exists())

        res = self.client.post(f"/api/route-plans/{plan_b['id']}/activate/")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(list(RoutePlan.objects.filter(is_active=True).values_list("name", flat=True)), ["Plan B"])

        # Same Route row, new stops ending at campus; R2 and the stops nobody uses are gone.
        self.assertEqual(self.stops_of(self.r1), [("Stop A", "08:00", None), ("FAST NUCES Main Campus", None, None)])
        self.assertFalse(Route.objects.filter(pk=self.r2.pk).exists())
        self.assertFalse(Stop.objects.filter(pk__in=[self.b.pk, self.c.pk]).exists())
        # The rider moved to the nearest stop on their route and kept seat and bus.
        self.assertEqual((TransportRegistration.objects.get().route_id, TransportRegistration.objects.get().stop_id), (self.r1.id, self.a.id))
        self.assertTrue(SeatAllocation.objects.filter(pk=self.seat.pk).exists())
        self.assertTrue(RouteAssignment.objects.get(pk=self.assignment.pk).is_active)
        self.assertEqual(Notification.objects.filter(user=self.student_user, title="Your transport stop has changed").count(), 1)
        self.assertEqual(self.client.get("/api/route-plans/attention/").data, [])

        # Swapping back restores the original plan's routes.
        res = self.client.post(f"/api/route-plans/{self.current.id}/activate/")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.stops_of(self.r1), [("Stop A", "07:00", None), ("Stop B", None, "16:40")])
        self.assertTrue(Route.objects.filter(name="R2").exists())
        self.assertFalse(Route.objects.filter(name="R3").exists())
        self.assertEqual(self.client.get("/api/route-plans/attention/").data, [])
        # Plan B was captured as it ran, so it can be activated again later.
        self.assertEqual(len(RoutePlan.objects.get(name="Plan B").data["routes"]), 2)

    def test_buses_follow_the_admins_pick_and_unpicked_riders_are_queued(self):
        plan = RoutePlan.objects.create(name="Next", data={"routes": [
            {"name": "R9", "description": "x", "status": "published", "stops": [
                {"name": "Near B", "latitude": 24.9101, "longitude": 67.0101, "morning_eta": None, "evening_eta": None},
            ]},
        ]})
        preview = route_plans.preview(plan)
        self.assertEqual([(b["bus"], b["from_route"], b["to_route"]) for b in preview["buses"]], [("B-1", "R1", None)])
        self.assertEqual(preview["moved_students"][0]["seat"], "queued")

        # Picking R9 for the bus keeps the student's seat.
        picked = route_plans.preview(plan, {str(self.assignment.id): "R9"})
        self.assertEqual((picked["buses"][0]["to_route"], picked["moved_students"][0]["seat"]), ("R9", "kept"))
        self.assertIn("errors", route_plans.preview(plan, {str(self.assignment.id): "Nope"}))

        # Leaving it unassigned: the bus loses the old route, the student waits first in line on R9.
        route_plans.activate(plan)
        registration = SemesterRegistration.objects.get()
        self.assertEqual((registration.route.name, registration.stop.name, registration.status), ("R9", "Near B", "Waitlisted"))
        self.assertEqual(registration.waitlist.status, "waiting")
        self.assertFalse(RouteAssignment.objects.exists())
        self.assertTrue(Bus.objects.exists() and Driver.objects.exists())  # buses and drivers are kept
        self.assertEqual(TransportRegistration.objects.get().status, "Waitlisted")

    def test_routes_other_semesters_use_are_archived_not_deleted(self):
        old = Semester.objects.create(name="Spring", is_active=False)
        other = StudentProfile.objects.create(user=User.objects.create_user("old", password="Str0ng!pass9"), roll_number="21K-0001")
        TransportRegistration.objects.create(student=other, semester=old, route=self.r2, stop=self.c, status="Approved")
        plan = self.upload("b.json", json.dumps(PLAN_B)).data
        report = self.client.post(f"/api/route-plans/{plan['id']}/activate/").data
        self.assertEqual((report["routes"]["removed"], report["routes"]["archived"]), ([], ["R2"]))
        self.assertTrue(Stop.objects.filter(pk=self.c.pk).exists())  # still on the archived route

    def test_campus_is_never_a_pickup_stop(self):
        self.upload("b.json", json.dumps(PLAN_B))
        campus = Stop.objects.get(is_campus=True)
        self.client.force_authenticate(self.student_user)
        res = self.client.post("/api/transport-registrations/", {"stop_id": campus.id, "semester_id": Semester.objects.get().id})
        self.assertEqual(res.status_code, 400)
        self.assertIn("campus", str(res.data).lower())

    def test_only_one_active_plan_and_it_cannot_be_deleted(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoutePlan.objects.create(name="Second", is_active=True)
        self.assertEqual(self.client.delete(f"/api/route-plans/{self.current.id}/").status_code, 400)
        self.assertEqual(self.client.post(f"/api/route-plans/{self.current.id}/activate/").status_code, 400)

        copy = self.client.post(f"/api/route-plans/{self.current.id}/duplicate/", {"name": "Backup"})
        self.assertEqual((copy.status_code, copy.data["name"], copy.data["route_count"]), (201, "Backup", 2))
        self.assertEqual(self.client.delete(f"/api/route-plans/{copy.data['id']}/").status_code, 204)

    def test_bad_files_are_rejected_whole(self):
        res = self.upload("bad.csv", (
            "route_name,name,latitude,longitude,morning_eta\n"
            "R9,Good,24.9,67.0,07:00\n"
            "R9,No Coords,,x,\n"
            "R9,Bad Time,24.95,67.05,25:99\n"
            ",Orphan,24.96,67.06,\n"
        ))
        self.assertEqual(res.status_code, 400)
        errors = " ".join(res.data["file"])
        for expected in ("Row 3:", "Row 4: morning_eta", "Row 5: route name is missing"):
            self.assertIn(expected, errors)
        self.assertEqual(RoutePlan.objects.count(), 1)

        self.assertEqual(self.upload("p.json", "{not json").status_code, 400)
        self.assertEqual(self.upload("p.csv", "name,latitude\nX,1\n").status_code, 400)
        self.assertEqual(self.upload("p.txt", "x").status_code, 400)

    def test_students_cannot_use_route_plans(self):
        self.client.force_authenticate(self.student_user)
        self.assertEqual(self.client.get("/api/route-plans/").status_code, 403)
        self.assertEqual(self.upload("b.json", json.dumps(PLAN_B)).status_code, 403)
        self.assertEqual(self.client.post(f"/api/route-plans/{self.current.id}/activate/").status_code, 403)
