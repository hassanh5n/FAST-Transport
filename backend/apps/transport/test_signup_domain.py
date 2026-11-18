"""Students sign up with a university (@nu.edu.pk) email; faculty are not restricted yet."""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.transport.models import StudentProfile


@patch("apps.transport.views.auth.send_otp_email")
class SignupEmailDomainTests(TestCase):
    def setUp(self):
        cache.clear()  # signup is rate-limited; keep each test independent
        self.client = APIClient()

    def signup(self, email, username="k230769", roll="23K-0769"):
        return self.client.post("/api/signup/", {
            "username": username, "email": email, "password": "Str0ng-Pass-123",
            "roll_number": roll, "department": "CS", "batch": "23",
        }, format="json")

    def test_university_email_can_sign_up(self, send_otp):
        res = self.signup("k230769@nu.edu.pk")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertTrue(StudentProfile.objects.filter(user__email="k230769@nu.edu.pk").exists())
        send_otp.assert_called_once()

    def test_domain_is_not_case_sensitive(self, send_otp):
        self.assertEqual(self.signup("K230769@NU.EDU.PK").status_code, 201)

    def faculty_signup(self, email, username):
        return self.client.post("/api/signup/", {
            "username": username, "email": email, "password": "Str0ng-Pass-123",
            "user_type": StudentProfile.FACULTY, "department": "CS",
        }, format="json")

    def test_faculty_with_university_email_can_sign_up(self, send_otp):
        self.assertEqual(self.faculty_signup("sara.ahmed@nu.edu.pk", "dr_sara").status_code, 201)

    def test_faculty_with_any_email_can_sign_up_for_now(self, send_otp):
        res = self.faculty_signup("sara.ahmed@gmail.com", "dr_sara")
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(StudentProfile.objects.get(user__username="dr_sara").user_type, StudentProfile.FACULTY)

    def test_student_cannot_skip_the_check_by_omitting_user_type(self, send_otp):
        # user_type defaults to student, so leaving it out is not a way around the rule.
        res = self.client.post("/api/signup/", {
            "username": "k1", "email": "k1@gmail.com", "password": "Str0ng-Pass-123", "roll_number": "23K-0001",
        }, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("email", res.data)

    def test_other_domains_are_refused(self, send_otp):
        for i, email in enumerate((
            "someone@gmail.com",
            "k230769@nu.edu.pk.evil.com",   # domain only starts with ours
            "k230769@evilnu.edu.pk",        # domain only ends with ours
            "k230769@lhr.nu.edu.pk",        # subdomains are not on the list
            "nu.edu.pk@gmail.com",          # our domain in the local part
        )):
            with self.subTest(email=email):
                res = self.signup(email, username=f"user{i}", roll=f"23K-10{i}")
                self.assertEqual(res.status_code, 400)
                self.assertIn("email", res.data)
                self.assertIn("@nu.edu.pk", str(res.data["email"][0]))
        # Refused before anything is created or emailed.
        self.assertFalse(User.objects.exists())
        self.assertFalse(StudentProfile.objects.exists())
        send_otp.assert_not_called()

    @override_settings(SIGNUP_EMAIL_DOMAINS=["nu.edu.pk", "isb.nu.edu.pk"])
    def test_allowed_domains_come_from_settings(self, send_otp):
        self.assertEqual(self.signup("i230001@isb.nu.edu.pk", "i230001", "23I-0001").status_code, 201)
        self.assertEqual(self.signup("x@gmail.com", "x1", "23K-9998").status_code, 400)
