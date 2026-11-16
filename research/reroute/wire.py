"""The request and proposal formats (Section 6.3 of the rerouting plan).

:func:`parse_request` checks a request and turns it into a :class:`~reroute.model.Problem`;
:func:`to_proposal` turns a plan into the proposal the caller sends back. Travel times and walking
distances are the caller's job: closures and coordinates are only checked for presence here.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Mapping

from reroute.model import MAX_WALK_LIMIT_M, Plan, Problem, RowsFn, StopNeed

SCHEMA = 1
REQUIRED = ("schema", "now", "remaining", "candidates", "closures", "campus", "position")
PROPOSAL_KEYS = ("schema", "status", "reason", "revision", "method", "visit", "stops", "arrival",
                 "delay_s", "students_walking", "compute_s", "state")


class RequestError(ValueError):
    """A request that cannot be solved; the message names the offending field."""


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _parse_now(text: Any) -> datetime:
    if not isinstance(text, str):
        raise RequestError("now must be an ISO 8601 string")
    try:
        now = datetime.fromisoformat(text)
    except ValueError:
        raise RequestError(f"now is not an ISO 8601 time: {text!r}") from None
    if now.utcoffset() is None:
        raise RequestError(f"now has no UTC offset: {text!r}")
    return now


def _check_place(request: dict, field: str) -> None:
    place = request[field]
    if not isinstance(place, dict) or "lat" not in place or "lng" not in place:
        raise RequestError(f"{field} needs lat and lng")


def _parse_stop(i: int, entry: Any) -> StopNeed:
    where = f"remaining[{i}]"
    if not isinstance(entry, dict):
        raise RequestError(f"{where} must be an object")
    sid = entry.get("stop_id")
    if not _is_int(sid):
        raise RequestError(f"{where}.stop_id must be an integer")
    students = entry.get("students")
    if not _is_int(students) or students < 0:
        raise RequestError(f"{where}.students must be a whole number, 0 or more")
    limit = entry.get("walk_limit_m", 400)
    if not _is_number(limit) or not 0 <= limit <= MAX_WALK_LIMIT_M:
        raise RequestError(f"{where}.walk_limit_m must be between 0 and {MAX_WALK_LIMIT_M:g}")
    must_serve = entry.get("must_serve", False)
    if not isinstance(must_serve, bool):
        raise RequestError(f"{where}.must_serve must be true or false")
    return StopNeed(sid, students, float(limit), must_serve)


def parse_request(request: dict, rows: RowsFn, walk: Mapping[tuple[int, int], float]) -> Problem:
    """Check a request and build its :class:`Problem`.

    Points are the remaining stops in order, then the candidates not already among them; ids are
    ``stop_id``. ``rows`` gives travel-time rows on that node indexing (see ``reroute.model``) and
    ``walk`` the walking metres between stops and points. Raises :class:`RequestError` naming the
    field at fault.
    """
    if not isinstance(request, dict):
        raise RequestError("request must be a JSON object")
    for field in REQUIRED:
        if field not in request:
            raise RequestError(f"missing field: {field}")
    if not _is_int(request["schema"]) or request["schema"] != SCHEMA:
        raise RequestError(f"schema must be {SCHEMA}, got {request['schema']!r}")
    _parse_now(request["now"])
    _check_place(request, "position")
    _check_place(request, "campus")
    if not isinstance(request["closures"], list):
        raise RequestError("closures must be a list")

    if not isinstance(request["remaining"], list):
        raise RequestError("remaining must be a list")
    stops: list[StopNeed] = []
    seen: set[int] = set()
    for i, entry in enumerate(request["remaining"]):
        stop = _parse_stop(i, entry)
        if stop.id in seen:
            raise RequestError(f"remaining[{i}].stop_id {stop.id} repeats")
        seen.add(stop.id)
        stops.append(stop)

    if not isinstance(request["candidates"], list):
        raise RequestError("candidates must be a list")
    points = [s.id for s in stops]
    for i, entry in enumerate(request["candidates"]):
        if not isinstance(entry, dict) or not _is_int(entry.get("stop_id")):
            raise RequestError(f"candidates[{i}].stop_id must be an integer")
        if entry["stop_id"] not in seen:
            seen.add(entry["stop_id"])
            points.append(entry["stop_id"])

    committed = request.get("committed")
    if committed is None:                             # a missing key or null means no promises
        committed = []
    if not isinstance(committed, list) or not all(_is_int(c) for c in committed):
        raise RequestError("committed must be a list of stop ids")
    for cid in committed:
        if cid not in seen:
            raise RequestError(f"committed id {cid} is in neither remaining nor candidates")
    return Problem(stops, points, rows, walk, committed)


def _proposal(status: str, reason: str | None, revision: int, method: str | None, visit: list,
              stops: list, arrival: str | None, delay_s: int | None, students_walking: int,
              compute_s: float | None, state: dict | None) -> dict:
    return {"schema": SCHEMA, "status": status, "reason": reason, "revision": revision,
            "method": method, "visit": visit, "stops": stops, "arrival": arrival,
            "delay_s": delay_s, "students_walking": students_walking, "compute_s": compute_s,
            "state": state}


def to_proposal(request: dict, plan: Plan, compute_s: float,
                baseline_arrival_s: float | None = None, revision: int = 1,
                state: dict | None = None) -> dict:
    """The proposal for ``plan``, solved from ``request``.

    ``stops`` has one entry per remaining stop in request order, with action ``"keep"``,
    ``"walk"`` or ``"unserved"`` and the metres one student walks. Status is ``"failed"`` when
    campus cannot be reached (``arrival`` and ``delay_s`` are then ``None``), ``"no_change"`` when
    the plan is the published order with nobody walking, and ``"reroute"`` otherwise.
    """
    now = _parse_now(request["now"])
    unserved = set(plan.unserved)
    entries: list[dict] = []
    students_walking = 0
    changed = False
    for stop in request["remaining"]:
        sid = stop["stop_id"]
        if sid in unserved:
            entries.append({"stop_id": sid, "action": "unserved", "board_at": None, "walk_m": 0})
            changed = True
            continue
        if sid not in plan.board_at:
            raise ValueError(f"the plan has no boarding point for stop {sid}")
        at = plan.board_at[sid]
        if at == sid:
            entries.append({"stop_id": sid, "action": "keep", "board_at": at, "walk_m": 0})
            continue
        if sid not in plan.stop_walk_m:
            raise ValueError(f"the plan has no walking distance for stop {sid}")
        entries.append({"stop_id": sid, "action": "walk", "board_at": at,
                        "walk_m": round(plan.stop_walk_m[sid])})
        students_walking += stop["students"]
        changed = True

    visit = list(plan.visit)
    if not math.isfinite(plan.arrival_s):
        return _proposal("failed", "campus unreachable", revision, plan.method, visit, entries,
                         None, None, students_walking, compute_s, state)
    if not changed and visit == [s["stop_id"] for s in request["remaining"]]:
        status, reason = "no_change", "published order is already best"
    else:
        status, reason = "reroute", None
    arrival = (now + timedelta(seconds=round(plan.arrival_s))).isoformat()
    delay = None
    if baseline_arrival_s is not None and math.isfinite(baseline_arrival_s):
        delay = round(plan.arrival_s - baseline_arrival_s)
    return _proposal(status, reason, revision, plan.method, visit, entries, arrival, delay,
                     students_walking, compute_s, state)


def failed_proposal(reason: str, revision: int = 1) -> dict:
    """A ``"failed"`` proposal for when no plan could be made at all."""
    return _proposal("failed", reason, revision, None, [], [], None, None, 0, None, None)
