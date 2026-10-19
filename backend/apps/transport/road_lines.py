"""
Builds road-following lines in the background, so no admin has to press a button.

Any change that drops a route's saved line (stops moved, reordered, a plan
activated) calls schedule_road_line_build(). One worker thread then walks every
published route still missing a line, one request a second as the free routing
server asks. Map pages keep drawing those routes stop to stop until it lands.
"""

import logging
import threading
import time

from django.db import close_old_connections, transaction

logger = logging.getLogger(__name__)

REQUEST_GAP_SECONDS = 1   # the free routing server allows about one request a second
RETRY_COOLDOWN_SECONDS = 300  # after a pass with failures, map loads wait this long before retrying

_lock = threading.Lock()
_state = {"running": False, "again": False, "failed_at": 0.0}


def _route_coordinates(route):
    from .models import RouteStop

    rows = (
        RouteStop.objects.filter(route=route, stop__is_active=True)
        .order_by("stop_order").values_list("stop__longitude", "stop__latitude")
    )
    return [[float(lng), float(lat)] for lng, lat in rows if not (float(lng) == 0 and float(lat) == 0)]


def build_missing_road_lines():
    """Save a road line for every published route without one. Returns (built, failed)."""
    from .models import Route
    from .views.maps import _display_route_geometry

    built = failed = 0
    for route in Route.objects.filter(is_active=True, status="published").order_by("id"):
        coordinates = _route_coordinates(route)
        if len(coordinates) < 2 or _display_route_geometry(route, coordinates)[1] == "stored":
            continue
        _, source = _display_route_geometry(route, coordinates, fetch=True)
        if source == "stored":
            built += 1
        else:
            failed += 1
        time.sleep(REQUEST_GAP_SECONDS)
    return built, failed


def _worker():
    try:
        while True:
            close_old_connections()
            try:
                built, failed = build_missing_road_lines()
                logger.info("Road lines: %s built, %s failed", built, failed)
                _state["failed_at"] = time.monotonic() if failed else 0.0
            except Exception:  # a crash here must not take down the request that scheduled it
                logger.exception("Road line build failed")
                _state["failed_at"] = time.monotonic()
            with _lock:
                if not _state["again"]:
                    _state["running"] = False
                    return
                _state["again"] = False  # something changed mid-pass: walk the routes once more
    finally:
        close_old_connections()


def _start():
    with _lock:
        if _state["running"]:
            _state["again"] = True
            return
        _state["running"] = True
        _state["again"] = False
    threading.Thread(target=_worker, name="road-line-builder", daemon=True).start()


def schedule_road_line_build(respect_cooldown=False):
    """Start (or re-queue) the background build once the current transaction commits.

    respect_cooldown=True is for page loads: after a pass where the routing server
    failed, they do not retry it on every request.
    """
    if respect_cooldown and _state["failed_at"] and time.monotonic() - _state["failed_at"] < RETRY_COOLDOWN_SECONDS:
        return
    transaction.on_commit(_start)
