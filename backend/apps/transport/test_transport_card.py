from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.transport.models import Semester, StudentProfile


class TransportCardDownloadTests(TestCase):
    def test_faculty_without_roll_number_gets_a_pdf(self):
        user = User.objects.create_user("fac", "fac@nu.edu.pk", "x", first_name="Aiman", last_name="Khan")
        StudentProfile.objects.create(user=user, user_type=StudentProfile.FACULTY, department="CS")
        Semester.objects.create(name="Fall 2026", is_active=True)
        client = APIClient()
        client.force_authenticate(user)
        res = client.get("/api/download-transport-card/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/pdf")
        self.assertTrue(b"".join(res.streaming_content if res.streaming else [res.content]).startswith(b"%PDF"))
