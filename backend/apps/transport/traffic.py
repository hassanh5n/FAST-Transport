"""Live traffic incidents for Karachi, fetched once and shared by every user.

One call to OpenWeb Ninja's Google Maps Traffic Alerts API covers the whole city
(zoom 12; zoom 13 is limited to 500 km^2 a call). The result is kept in the cache and
served to everyone; it is refreshed at most once per TRAFFIC_ALERTS_REFRESH_SECONDS,
however many students and drivers are looking. When it is due, one request refreshes
it while the others keep getting the saved copy, and a failed refresh keeps serving
the last good one.

The cache is Django's (in-process unless CACHES says otherwise), so each server
process refreshes on its own: calls per day are processes x 288 at the 5 minute default.
"""
import logging
import time

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

URL = "https://api.openwebninja.com/google-maps-traffic-alerts/traffic-alerts"
# South-west and north-east corners of the area the buses run in.
BOTTOM_LEFT = "24.78,66.93"
TOP_RIGHT = "25.06,67.30"
ZOOM = 12

SNAPSHOT_KEY = "traffic-alerts:snapshot"
LOCK_KEY = "traffic-alerts:refreshing"
KEEP_SECONDS = 6 * 60 * 60  # a saved copy is still worth showing for hours if the API is down
TYPES = {"accident", "construction", "road_closed", "incident"}


class TrafficUnavailable(Exception):
    pass


def _fetch():
    if not settings.OPENWEBNINJA_API_KEY:
        raise TrafficUnavailable("No traffic data key is configured on the server.")
    response = requests.get(
        URL,
        params={"bottom_left": BOTTOM_LEFT, "top_right": TOP_RIGHT, "zoom": ZOOM, "language": "en"},
        headers={"x-api-key": settings.OPENWEBNINJA_API_KEY},
        timeout=15,
    )
    body = response.json()
    if response.status_code != 200 or body.get("status") != "OK":
        message = (body.get("error") or {}).get("message") or f"HTTP {response.status_code}"
        raise TrafficUnavailable(f"The traffic provider refused the request: {message}")
    alerts = []
    for alert in (body.get("data") or {}).get("alerts") or []:
        try:
            latitude, longitude = float(alert["latitude"]), float(alert["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        kind = alert.get("type") if alert.get("type") in TYPES else "incident"
        alerts.append({"type": kind, "latitude": latitude, "longitude": longitude})
    return alerts


def snapshot():
    """{"alerts", "fetched_at", "refresh_seconds", "stale"}; raises TrafficUnavailable only
    when there has never been a successful fetch."""
    refresh = settings.TRAFFIC_ALERTS_REFRESH_SECONDS
    saved = cache.get(SNAPSHOT_KEY)
    due = saved is None or time.time() - saved["fetched_at"] >= refresh
    # Only the request that takes the lock refreshes; it expires on its own if that one dies.
    if due and cache.add(LOCK_KEY, True, timeout=30):
        try:
            saved = {"alerts": _fetch(), "fetched_at": time.time(), "error": None}
            cache.set(SNAPSHOT_KEY, saved, KEEP_SECONDS)
        except (requests.RequestException, ValueError, TrafficUnavailable) as exc:
            logger.warning("Traffic alerts refresh failed: %s", exc)
            if saved is None:
                raise TrafficUnavailable(str(exc)) from exc
            saved = {**saved, "error": str(exc)}
        finally:
            cache.delete(LOCK_KEY)
    if saved is None:
        raise TrafficUnavailable("Traffic data is loading. Try again in a few seconds.")
    return {
        "alerts": saved["alerts"],
        "fetched_at": saved["fetched_at"],
        "refresh_seconds": refresh,
        "stale": time.time() - saved["fetched_at"] >= refresh + 60 or bool(saved.get("error")),
    }
