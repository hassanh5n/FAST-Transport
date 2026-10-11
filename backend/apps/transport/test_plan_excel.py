"""Tests for importing a route plan from an Excel workbook (one sheet per contractor)."""
import io

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook
from rest_framework.test import APITestCase

from . import route_plans
from .models import AdminProfile, Contractor, Route, RoutePlan, RouteStop, Stop

HEADER = ["Route", "Stop", "Latitude", "Longitude", "Map link", "Location status"]


def workbook(sheets):
    book = Workbook()
    book.remove(book.active)
    for title, rows in sheets.items():
        sheet = book.create_sheet(title)
        sheet.append([f"{title} — Stops by Route"])  # title rows above the header, like the real sheet
        sheet.append(["152 route-stop entries"])
        sheet.append([])
        for row in rows:
            sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


class ExcelPlanImportTests(APITestCase):
    def setUp(self):
        boss = User.objects.create_user("boss", password="Str0ng!pass9", is_staff=True)
        AdminProfile.objects.create(user=boss, is_super_admin=True)
        self.client.force_authenticate(boss)
        # An old stop 19 m from a new one, with a different name: must stay a separate stop.
        self.old = Stop.objects.create(name="Johar", latitude="24.904637", longitude="67.113506", address="Old")
        # An old stop at exactly the same spot: reused.
        self.same = Stop.objects.create(name="Dolmen Mall", latitude="24.935560", longitude="67.040230", address="Kept")

    def upload(self, content, name="routes.xlsx"):
        return self.client.post("/api/route-plans/import/", {"file": SimpleUploadedFile(name, content)}, format="multipart")

    def test_workbook_becomes_an_inactive_plan_with_stops_created(self):
        res = self.upload(workbook({
            "Jadoon Routes": [HEADER,
                ["Jadoon R-5B", "Dolmen Mall", 24.93556, 67.04023, "https://maps", "landmark_matched"],
                ["Jadoon R-5B", "5 Star", 24.940487, 67.046194, "", "auto_checked"]],
            "Nadeem Routes": [HEADER,
                ["Nadeem 39", "Johar More", 24.904474, 67.113549, "", "auto_checked"],
                ["Nadeem 39", "Star Gate", 24.887124, 67.155791, "", "auto_checked"]],
        }))
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual((res.data["is_active"], res.data["route_count"]), (False, 2))
        self.assertEqual(sorted(s["name"] for s in res.data["stops"]["created"]), ["5 Star", "FAST NUCES Main Campus", "Johar More", "Star Gate"])
        self.assertTrue(Stop.objects.get(name="FAST NUCES Main Campus").is_campus)
        self.assertEqual(res.data["stops"]["reused"], 1)
        self.assertEqual(Stop.objects.get(name="Johar More").address, "N/A")
        self.assertFalse(Route.objects.exists())  # routes wait for activation

        plan = RoutePlan.objects.get(pk=res.data["id"])
        routes = {r["name"]: r for r in route_plans.plan_snapshot(plan)["routes"]}
        # No order or times in the sheet: farthest from campus first, and every route ends at campus.
        self.assertEqual([s["name"] for s in routes["Nadeem 39"]["stops"]], ["Johar More", "Star Gate", "FAST NUCES Main Campus"])

        route_plans.activate(plan)
        r39 = Route.objects.get(name="Nadeem 39")
        self.assertEqual(r39.contractor, Contractor.objects.get(name="Nadeem"))
        self.assertEqual(
            list(RouteStop.objects.filter(route=r39).values_list("stop__name", flat=True)),
            ["Johar More", "Star Gate", "FAST NUCES Main Campus"],
        )
        r5b = Route.objects.get(name="Jadoon R-5B")
        self.assertIn(self.same.id, RouteStop.objects.filter(route=r5b).values_list("stop_id", flat=True))
        self.assertEqual(Stop.objects.filter(name="Johar More").count(), 1)  # import + activation made one stop

    def test_times_order_the_stops_and_am_pm_is_read(self):
        res = self.upload(workbook({"Sheet": [
            ["Route", "Stop", "Lat", "Lng", "Morning time", "Evening time"],
            ["Jadoon R-2", "Second", 24.95, 67.14, "7:10 AM", "4:40 PM"],
            ["Jadoon R-2", "First", 24.96, 67.12, "6:55 am", "4:55 PM"],
            ["Jadoon R-2", "FAST", 24.8570, 67.2647, "8:00 AM", "4:00 PM"],  # the sheet's own campus row
        ]}))
        self.assertEqual(res.status_code, 201, res.content)
        stops = route_plans.plan_snapshot(RoutePlan.objects.get(pk=res.data["id"]))["routes"][0]["stops"]
        self.assertEqual([(s["name"], s["morning_eta"], s["evening_eta"]) for s in stops],
                         [("First", "06:55", "16:55"), ("Second", "07:10", "16:40"), ("FAST NUCES Main Campus", "08:00", "16:00")])

    def test_bad_workbooks_are_rejected(self):
        self.assertEqual(self.upload(b"not a zip").status_code, 400)
        res = self.upload(workbook({"Sheet": [["Name", "Lat"], ["X", 1]]}))
        self.assertEqual(res.status_code, 400)
        self.assertIn("Route and Stop", " ".join(res.data["file"]))
        res = self.upload(workbook({"Sheet": [HEADER, ["Jadoon R-2", "Nowhere", "", "", "", ""]]}))
        self.assertEqual(res.status_code, 400)
        self.assertEqual(RoutePlan.objects.filter(is_active=False).count(), 0)

    def test_address_save_keeps_road_line_but_a_move_clears_it(self):
        route = Route.objects.create(name="R")
        RouteStop.objects.create(route=route, stop=self.old, stop_order=1)  # linking a stop clears the line itself
        Route.objects.filter(pk=route.pk).update(geometry={"type": "LineString", "coordinates": [[67, 24], [67.1, 24.1]]})
        self.old.address = "Gulistan-e-Johar, Karachi"
        self.old.save()
        route.refresh_from_db()
        self.assertIsNotNone(route.geometry)
        self.old.latitude = "24.910000"
        self.old.save()
        route.refresh_from_db()
        self.assertIsNone(route.geometry)
