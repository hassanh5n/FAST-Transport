"""Tests for bulk stop import (CSV/JSON)."""
import json

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from .models import AdminActivityLog, AdminProfile, Stop

CSV = (
    "name,latitude,longitude,status,landmark_or_hint,,map_link\n"
    ",,,,,,\n"                                              # blank row: dropped
    "Babul Islam,24.97614,67.05541,ok,Mosque,,http://x\n"   # created
    "  HASSAN   square ,24.95,67.10,ok,,,\n"                # same name as DB stop
    "Near Hassan,24.902520,67.072900,ok,,,\n"               # ~0.5 m from DB stop
    "Ayesha Manzil,24.927333,67.064578,ok,,,\n"             # created
    "Ayesha Manzil More,24.927333,67.064578,ok,,,\n"        # same spot as row above
    "No Coords,,,ok,,,\n"                                   # invalid
    "Zero,0,0,ok,,,\n"                                      # invalid
)


class StopImportTests(APITestCase):
    def setUp(self):
        boss = User.objects.create_user("boss", password="Str0ng!pass9", is_staff=True)
        AdminProfile.objects.create(user=boss, is_super_admin=True)
        Stop.objects.create(name="Hassan Square", latitude="24.902517", longitude="67.072896", address="Square")
        self.client.force_authenticate(boss)

    def upload(self, name, content):
        return self.client.post("/api/stops/import/", {"file": SimpleUploadedFile(name, content.encode())}, format="multipart")

    def test_csv_creates_valid_rows_and_reports_the_rest(self):
        res = self.upload("stops.csv", CSV)
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual([s["name"] for s in res.data["created"]], ["Babul Islam", "Ayesha Manzil"])
        self.assertEqual([s["row"] for s in res.data["skipped"]], [4, 5, 7])
        self.assertIn("Hassan Square", res.data["skipped"][0]["reason"])
        self.assertIn("row 6 of this file", res.data["skipped"][2]["reason"])
        self.assertEqual([s["row"] for s in res.data["invalid"]], [8, 9])
        self.assertEqual(res.data["ignored_columns"], ["landmark_or_hint", "map_link", "status"])

        stop = Stop.objects.get(name="Babul Islam")
        self.assertEqual((stop.address, stop.is_active, stop.location_source), ("N/A", True, "import"))
        self.assertTrue(AdminActivityLog.objects.filter(description__startswith="Imported stops from stops.csv: 2 created").exists())

    def test_json_wrapped_list_and_bad_files(self):
        res = self.upload("s.json", json.dumps({"stops": [{"Name": "KDA", "Latitude": 24.95, "longitude": 67.11}]}))
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.data["created"][0]["name"], "KDA")

        self.assertEqual(self.upload("s.json", "{not json").status_code, 400)
        self.assertEqual(self.upload("s.txt", "name\nX").status_code, 400)

    def test_students_cannot_import(self):
        self.client.force_authenticate(User.objects.create_user("stud", password="Str0ng!pass9"))
        self.assertEqual(self.upload("s.csv", CSV).status_code, 403)
