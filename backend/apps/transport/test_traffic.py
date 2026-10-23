"""Traffic incidents: one shared provider call per refresh period, whoever asks."""

from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from . import traffic

PROVIDER_OK = {"status": "OK", "data": {"count": 3, "alerts": [
    {"type": "accident", "latitude": 24.9, "longitude": 67.1},
    {"type": "road_closed", "latitude": 24.91, "longitude": 67.08},
    {"type": "something_new", "latitude": "24.85", "longitude": "67.0"},
]}}


def provider(status_code=200, body=PROVIDER_OK):
    return Mock(status_code=status_code, json=Mock(return_value=body))


@override_settings(OPENWEBNINJA_API_KEY="test-key", TRAFFIC_ALERTS_REFRESH_SECONDS=300)
class TrafficAlertsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient()
        self.client.force_authenticate(User.objects.create_user(username="rider", password="pass12345"))

    @patch("apps.transport.traffic.requests.get", return_value=provider())
    def test_many_users_share_one_provider_call(self, mock_get):
        for _ in range(5):
            response = self.client.get("/api/traffic/alerts/")
            self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_get.call_count, 1)
        alerts = response.json()["alerts"]
        self.assertEqual([a["type"] for a in alerts], ["accident", "road_closed", "incident"])  # unknown types become "incident"
        self.assertFalse(response.json()["stale"])

    @patch("apps.transport.traffic.requests.get", return_value=provider())
    def test_refreshes_after_the_period(self, mock_get):
        with patch("apps.transport.traffic.time.time", return_value=1_000_000):
            traffic.snapshot()
        with patch("apps.transport.traffic.time.time", return_value=1_000_000 + 299):
            traffic.snapshot()
        self.assertEqual(mock_get.call_count, 1)
        with patch("apps.transport.traffic.time.time", return_value=1_000_000 + 301):
            traffic.snapshot()
        self.assertEqual(mock_get.call_count, 2)

    def test_a_failed_refresh_keeps_the_last_good_copy(self):
        with patch("apps.transport.traffic.requests.get", return_value=provider()), \
                patch("apps.transport.traffic.time.time", return_value=1_000_000):
            traffic.snapshot()
        refused = provider(403, {"status": "ERROR", "error": {"message": "Quota exceeded", "code": 403}})
        with patch("apps.transport.traffic.requests.get", return_value=refused), \
                patch("apps.transport.traffic.time.time", return_value=1_000_000 + 400):
            data = traffic.snapshot()
        self.assertEqual(len(data["alerts"]), 3)
        self.assertTrue(data["stale"])

    @patch("apps.transport.traffic.requests.get", return_value=provider(403, {"status": "ERROR", "error": {"message": "Quota exceeded"}}))
    def test_no_data_yet_is_a_503(self, _get):
        response = self.client.get("/api/traffic/alerts/")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Quota exceeded", response.json()["detail"])

    def test_needs_sign_in(self):
        self.assertEqual(APIClient().get("/api/traffic/alerts/").status_code, 401)
