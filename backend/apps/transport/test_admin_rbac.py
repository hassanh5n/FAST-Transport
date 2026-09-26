"""Tests for admin roles/permissions and the activity log."""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from .models import AdminActivityLog, AdminProfile, AdminRole, Bus, Complaint


class AdminRBACTests(APITestCase):
    def setUp(self):
        self.super = User.objects.create_user("boss", password="Str0ng!pass9", is_staff=True)
        AdminProfile.objects.create(user=self.super, is_super_admin=True)
        self.student = User.objects.create_user("stud", password="Str0ng!pass9")
        self.complaint = Complaint.objects.create(submitted_by=self.student, subject="AC broken")

    def login(self, username, password="Str0ng!pass9"):
        res = self.client.post("/api/token/", {"username": username, "password": password}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")

    def make_admin(self, username, role_name=None, custom=None):
        self.login("boss")
        role = AdminRole.objects.get(name=role_name).id if role_name else None
        res = self.client.post("/api/admin-management/admins/", {
            "username": username, "password": "Str0ng!pass9", "email": f"{username}@x.com",
            "role": role, "custom_permissions": custom or {},
        }, format="json")
        self.assertEqual(res.status_code, 201, res.content)
        self.client.credentials()
        return User.objects.get(username=username)

    def test_presets_seeded(self):
        self.assertTrue(AdminRole.objects.filter(name="Complaints Officer", is_system=True).exists())

    def test_super_admin_creates_admin_with_role(self):
        user = self.make_admin("comp", "Complaints Officer")
        self.assertTrue(user.is_staff)
        self.assertEqual(user.admin_profile.created_by, self.super)

    def test_complaints_officer_can_reply_but_not_touch_buses(self):
        self.make_admin("comp", "Complaints Officer")
        self.login("comp")
        self.assertEqual(self.client.get("/api/complaints/").status_code, 200)
        res = self.client.patch(f"/api/complaints/{self.complaint.id}/resolve/", {"admin_response": "Fixed"}, format="json")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.client.get("/api/buses/").status_code, 403)
        self.assertEqual(self.client.post("/api/buses/", {"bus_number": "B1"}, format="json").status_code, 403)
        self.assertEqual(self.client.get("/api/admin-management/admins/").status_code, 403)

    def test_view_only_admin_cannot_reply(self):
        self.make_admin("viewer", custom={"complaints": "view"})
        self.login("viewer")
        self.assertEqual(self.client.get("/api/complaints/").status_code, 200)
        res = self.client.patch(f"/api/complaints/{self.complaint.id}/resolve/", {"admin_response": "x"}, format="json")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["code"], "module_forbidden")

    def test_custom_override_revokes_role_permission(self):
        self.make_admin("comp2", "Complaints Officer", custom={"complaints": "none"})
        self.login("comp2")
        self.assertEqual(self.client.get("/api/complaints/").status_code, 403)

    def test_user_endpoint_returns_permissions(self):
        self.make_admin("comp", "Complaints Officer")
        self.login("comp")
        data = self.client.get("/api/user/").json()
        self.assertFalse(data["is_super_admin"])
        self.assertEqual(data["permissions"]["complaints"], "manage")
        self.assertEqual(data["permissions"]["fleet"], "none")
        self.assertEqual(data["admin_role"], "Complaints Officer")

    def test_students_unaffected(self):
        self.login("stud")
        self.assertEqual(self.client.get("/api/complaints/").status_code, 200)
        self.assertEqual(self.client.get("/api/admin-management/admins/").status_code, 403)

    def test_actions_are_logged_with_diff(self):
        self.make_admin("comp", "Complaints Officer")
        self.login("comp")
        self.client.patch(f"/api/complaints/{self.complaint.id}/resolve/", {"admin_response": "Fixed"}, format="json")
        log = AdminActivityLog.objects.filter(actor__username="comp", action="update", module="complaints").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.changes["status"], {"from": "Pending", "to": "Resolved"})
        self.assertEqual(log.changes["admin_response"]["to"], "Fixed")
        self.assertTrue(AdminActivityLog.objects.filter(actor__username="comp", action="login").exists())

    def test_admin_creation_logged_and_password_masked(self):
        self.make_admin("comp", "Complaints Officer")
        log = AdminActivityLog.objects.filter(actor=self.super, action="create", model_name="User").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.changes["password"]["to"], "••••••")

    def test_student_actions_not_logged(self):
        self.login("stud")
        before = AdminActivityLog.objects.count()
        self.client.post("/api/complaints/", {"subject": "Late bus", "description": "x"}, format="json")
        self.assertEqual(AdminActivityLog.objects.count(), before)

    def test_super_admin_reads_logs_with_filters(self):
        self.login("boss")
        self.client.post("/api/buses/", {"bus_number": "B-7", "capacity": 40}, format="json")
        res = self.client.get("/api/admin-management/activity-logs/?module=fleet")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertGreaterEqual(body["total"], 1)
        self.assertTrue(all(i["module"] == "fleet" for i in body["items"]))

    def test_cannot_demote_last_super_admin_or_self(self):
        self.login("boss")
        res = self.client.patch(f"/api/admin-management/admins/{self.super.id}/", {"is_super_admin": False}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertTrue(User.objects.get(pk=self.super.pk).admin_profile.is_super_admin)

    def test_deactivated_admin_cannot_login(self):
        user = self.make_admin("comp", "Complaints Officer")
        self.login("boss")
        self.client.patch(f"/api/admin-management/admins/{user.id}/", {"is_active": False}, format="json")
        self.client.credentials()
        res = self.client.post("/api/token/", {"username": "comp", "password": "Str0ng!pass9"}, format="json")
        self.assertEqual(res.status_code, 401)

    def test_staff_without_profile_has_no_module_access(self):
        User.objects.create_user("legacy", password="Str0ng!pass9", is_staff=True)
        self.login("legacy")
        self.assertEqual(self.client.get("/api/complaints/").status_code, 403)
        self.assertEqual(self.client.get("/api/routes/").status_code, 200)  # public read
