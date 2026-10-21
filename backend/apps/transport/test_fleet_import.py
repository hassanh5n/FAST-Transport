"""Tests for bulk bus and driver CSV import."""
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from .models import AdminActivityLog, AdminProfile, Bus, Contractor, Driver

BUS_CSV = (
    "bus_number,capacity,model,tracker_token,contractor,colour\n"
    "JDN-101,50,Hino 2020,TRK101,Jadoon,white\n"   # created
    ",,,,,\n"                                       # blank row: dropped
    "abc 123,30,,,Jadoon,\n"                        # same number as DB bus ABC-123
    "NDM-201,40,,TRK-OLD,Nadeem,\n"                 # same tracker token as DB bus
    "jdn101,30,,,Jadoon,\n"                         # same number as row 2
    "NDM-202,45,Isuzu,,nadeem,\n"                   # created (contractor case ignored)
    "NDM-203,abc,,,Nadeem,\n"                       # invalid capacity
    "NDM-204,40,,,Unknown Co,\n"                    # invalid contractor
    ",40,,,Nadeem,\n"                               # invalid: no bus number
)

DRIVER_CSV = (
    "name,cnic,license_no,phone,address,contractor,username\n"
    "Imran Ali,4210112345671,LIC-9001,0300 1112223,Gulshan,Jadoon,imran\n"   # created
    "Copy Of Hassan,42101-7168848-9,X1,,,Nadeem,\n"                         # same CNIC as DB driver
    "Copy Of Rizwan,4210199999991,lic 2468,,,Jadoon,\n"                     # same license as DB driver
    "Imran Again,42101-1234567-1,NEW-1,,,Jadoon,\n"                         # same CNIC as row 2
    "Bilal Khan,42201-7654321-3,LIC-9002,,,Nadeem,\n"                       # created
    "Short Cnic,12345,LIC-9003,,,Nadeem,\n"                                 # invalid CNIC
    ",4210155555551,LIC-9004,,,Nadeem,\n"                                   # invalid: no name
)


class FleetImportTests(APITestCase):
    def setUp(self):
        boss = User.objects.create_user("boss", password="Str0ng!pass9", is_staff=True)
        AdminProfile.objects.create(user=boss, is_super_admin=True)
        # Migration 0024 seeds both contractors.
        self.jadoon, _ = Contractor.objects.get_or_create(name="Jadoon")
        self.nadeem, _ = Contractor.objects.get_or_create(name="Nadeem")
        Bus.objects.create(bus_number="ABC-123", capacity=30, contractor=self.jadoon)
        Bus.objects.create(bus_number="OLD-1", capacity=30, tracker_token="trk-old")
        Driver.objects.create(name="Hassan", cnic="42101-7168848-9", license_no="234567")
        Driver.objects.create(name="Rizwan", cnic="67658954", license_no="LIC2468")
        self.client.force_authenticate(boss)

    def upload(self, url, content, name="file.csv"):
        return self.client.post(url, {"file": SimpleUploadedFile(name, content.encode())}, format="multipart")

    def test_bus_import_creates_valid_rows_and_reports_the_rest(self):
        res = self.upload("/api/buses/import/", BUS_CSV)
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual([b["name"] for b in res.data["created"]], ["JDN-101", "NDM-202"])
        self.assertEqual([s["row"] for s in res.data["skipped"]], [4, 5, 6])
        self.assertIn("ABC-123", res.data["skipped"][0]["reason"])
        self.assertIn("tracker token", res.data["skipped"][1]["reason"])
        self.assertIn("row 2 of this file", res.data["skipped"][2]["reason"])
        self.assertEqual([s["row"] for s in res.data["invalid"]], [8, 9, 10])
        self.assertEqual(res.data["ignored_columns"], ["colour"])
        self.assertEqual(Bus.objects.get(bus_number="NDM-202").contractor, self.nadeem)
        self.assertTrue(AdminActivityLog.objects.filter(module="fleet", model_name="bus").exists())

    def test_driver_import_checks_cnic_and_license_duplicates(self):
        res = self.upload("/api/drivers/import/", DRIVER_CSV)
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual([d["name"] for d in res.data["created"]], ["Imran Ali", "Bilal Khan"])
        self.assertEqual([s["row"] for s in res.data["skipped"]], [3, 4, 5])
        self.assertIn("CNIC", res.data["skipped"][0]["reason"])
        self.assertIn("license", res.data["skipped"][1]["reason"])
        self.assertIn("row 2 of this file", res.data["skipped"][2]["reason"])
        self.assertEqual([s["row"] for s in res.data["invalid"]], [7, 8])
        self.assertEqual(res.data["ignored_columns"], ["username"])
        imran = Driver.objects.get(name="Imran Ali")
        self.assertEqual(imran.cnic, "42101-1234567-1")
        self.assertEqual(imran.contractor, self.jadoon)
        self.assertIsNone(imran.user)  # logins are never created from a file

    def test_rejects_non_csv_and_needs_admin(self):
        res = self.upload("/api/buses/import/", BUS_CSV, name="buses.json")
        self.assertEqual(res.status_code, 400)
        self.client.force_authenticate(User.objects.create_user("student", password="Str0ng!pass9"))
        res = self.upload("/api/drivers/import/", DRIVER_CSV)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(Driver.objects.count(), 2)
