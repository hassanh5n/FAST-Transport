"""Brute-force and enumeration guards on login, signup OTP and password reset."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.transport.models import OTPVerification
from apps.transport.otp import MAX_ATTEMPTS, generate_otp
from apps.transport.throttles import AuthRateThrottle


class SecurityTestBase(TestCase):
    def setUp(self):
        cache.clear()  # throttle counters live in the cache
        self.client = APIClient()

    def make_otp(self, user, code="123456"):
        return OTPVerification.objects.create(user=user, otp=code, expires_at=timezone.now() + timedelta(minutes=10))


class OtpGenerationTests(TestCase):
    def test_codes_are_six_digits_and_vary(self):
        codes = {generate_otp() for _ in range(50)}
        self.assertTrue(all(len(c) == 6 and c.isdigit() for c in codes))
        self.assertGreater(len(codes), 40)


class OtpAttemptLimitTests(SecurityTestBase):
    def test_signup_code_dies_after_max_wrong_guesses(self):
        user = User.objects.create_user("pending", "p@nu.edu.pk", "x", is_active=False)
        self.make_otp(user)
        for _ in range(MAX_ATTEMPTS):
            self.assertEqual(self.client.post("/api/verify-otp/", {"email": "p@nu.edu.pk", "otp": "000000"}).status_code, 400)
        res = self.client.post("/api/verify-otp/", {"email": "p@nu.edu.pk", "otp": "123456"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Too many", res.data["detail"])
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_right_code_within_limit_still_works(self):
        user = User.objects.create_user("pending2", "p2@nu.edu.pk", "x", is_active=False)
        self.make_otp(user)
        self.client.post("/api/verify-otp/", {"email": "p2@nu.edu.pk", "otp": "000000"})
        self.assertEqual(self.client.post("/api/verify-otp/", {"email": "p2@nu.edu.pk", "otp": "123456"}).status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_reset_code_dies_after_max_wrong_guesses(self):
        user = User.objects.create_user("active", "a@nu.edu.pk", "OldPass!2026")
        self.make_otp(user)
        body = {"email": "a@nu.edu.pk", "new_password": "N3w-Secure-Pass!"}
        for _ in range(MAX_ATTEMPTS):
            self.client.post("/api/reset-password/", {**body, "otp": "000000"})
        self.assertEqual(self.client.post("/api/reset-password/", {**body, "otp": "123456"}).status_code, 400)
        user.refresh_from_db()
        self.assertTrue(user.check_password("OldPass!2026"))


class EnumerationTests(SecurityTestBase):
    def test_forgot_password_answers_the_same_for_unknown_email(self):
        User.objects.create_user("real", "real@nu.edu.pk", "x")
        known = self.client.post("/api/forgot-password/", {"email": "real@nu.edu.pk"})
        unknown = self.client.post("/api/forgot-password/", {"email": "nobody@nu.edu.pk"})
        self.assertEqual((known.status_code, known.data), (unknown.status_code, unknown.data))

    def test_reset_password_answers_the_same_for_unknown_email(self):
        user = User.objects.create_user("real2", "real2@nu.edu.pk", "x")
        self.make_otp(user)
        body = {"otp": "000000", "new_password": "N3w-Secure-Pass!"}
        wrong_code = self.client.post("/api/reset-password/", {**body, "email": "real2@nu.edu.pk"})
        cache.clear()
        unknown = self.client.post("/api/reset-password/", {**body, "email": "nobody@nu.edu.pk"})
        self.assertEqual(wrong_code.status_code, unknown.status_code)

    def test_reset_rejects_weak_password(self):
        user = User.objects.create_user("real3", "real3@nu.edu.pk", "x")
        self.make_otp(user)
        res = self.client.post("/api/reset-password/", {"email": "real3@nu.edu.pk", "otp": "123456", "new_password": "12345678"})
        self.assertEqual(res.status_code, 400)


class LoginThrottleTests(SecurityTestBase):
    def test_login_is_rate_limited(self):
        with mock.patch.object(AuthRateThrottle, "THROTTLE_RATES", {"auth": "3/min"}):
            codes = [self.client.post("/api/token/", {"username": "x", "password": "y"}).status_code for _ in range(4)]
        self.assertEqual(codes[-1], 429)
        self.assertNotIn(429, codes[:3])
