"""Pure rules for building the closure scenarios (work plan Section 8.2, offline plan Task 4).

Nothing here talks to OSRM or reads the road graph; `build_scenarios.py` combines these rules with
OSRM answers. Points are `(lat, lng)` in degrees, distances in metres, times in seconds.

Leg numbering: in a route with stops s1..sn, leg k joins stop k and stop k + 1 (1-based).
Stop ids are positions in the `stops` list of the instance file.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Iterable, Mapping, Sequence

EARTH_RADIUS_M = 6_371_008.8
# Rough box around Karachi, used to catch swapped or mistyped coordinates.
KARACHI_BOX = {"lat": (24.6, 25.4), "lng": (66.6, 67.6)}

Point = tuple[float, float]


# --- placement -----------------------------------------------------------------------------------

def closure_legs(n_stops: int) -> list[int]:
    """The two legs to close on a route of `n_stops` stops: ceil(n/3) and ceil(2n/3), capped at n-1.

    Routes with fewer than 3 stops get no closure.
    """
    if n_stops < 3:
        return []
    return [math.ceil(n_stops / 3), min(math.ceil(2 * n_stops / 3), n_stops - 1)]


def scenario_id(contractor: str, route_code: str, leg: int, trigger: str) -> str:
    """For example `Jadoon-R-10-L2-early`."""
    return f"{contractor}-{route_code}-L{leg}-{trigger}"


def triggers(stop_ids: Sequence[int], leg: int) -> list[dict]:
    """The two bus positions for a closure on leg `leg` of a route with stops `stop_ids`.

    Early: the bus is at the first stop, which is still to be served. Late: the bus has just served
    the stop before the closure (stop `leg`), and the stops after it remain. For `leg` 1 the late
    trigger therefore starts at the first stop with the rest remaining.
    """
    if not 1 <= leg <= len(stop_ids) - 1:
        raise ValueError(f"leg {leg} is not between two of the {len(stop_ids)} stops")
    stops = list(stop_ids)
    return [{"trigger": "early", "position": stops[0], "remaining": stops},
            {"trigger": "late", "position": stops[leg - 1], "remaining": stops[leg:]}]


def scenario_tags(remaining: Sequence[int], closed_stop_ids: Iterable[int]) -> dict:
    """Tags kept with a scenario: how many stops remain and whether the closure contains one of them.

    A scenario whose closure contains a remaining stop is kept; that stop must be served by walking.
    """
    closed = set(closed_stop_ids)
    return {"remaining": len(remaining), "closure_contains_stop": any(s in closed for s in remaining)}


# --- students and candidates -----------------------------------------------------------------------

def route_students(csv_rows: Iterable[dict], contractor: str, route_code: str) -> dict[str, int]:
    """Students per stop name on one route, from rows of `students_synthetic_fall2026.csv`."""
    counts = Counter(r["stop"] for r in csv_rows
                     if r["contractor"] == contractor and r["baseline_route"] == route_code)
    return dict(counts)


def stops_with_students(stop_names: Sequence[str], students: Mapping[str, int]) -> list[str]:
    """The route's stops, in order, without those that have no students on this route.

    A stop shared with another route or contractor but empty here is not a stop of this route.
    """
    return [name for name in stop_names if students.get(name, 0) > 0]


def candidates(remaining: Sequence[int], walk: Mapping[tuple[int, int], float],
               max_m: float = 800.0) -> list[int]:
    """Other stop ids within `max_m` walk of any remaining stop, ascending.

    `walk` is directed, `(from, to) -> metres`, read from the remaining stop to the candidate.
    """
    rest = set(remaining)
    found = {b for (a, b), m in walk.items() if a in rest and b not in rest and m <= max_m}
    return sorted(found)


# --- tables ------------------------------------------------------------------------------------------

def apply_closed(table: list[list[float]], closed: Sequence[bool]) -> list[list[float]]:
    """A copy of `table` with the rows and columns of closed points infinite, diagonal kept.

    This is the reachability rule: a point inside a full block cannot be visited, whatever OSRM
    answers after snapping it to another road.
    """
    n = len(closed)
    if len(table) != n or any(len(row) != n for row in table):
        raise ValueError(f"table is not {n} x {n}")
    return [[v if i == j or not (closed[i] or closed[j]) else math.inf for j, v in enumerate(row)]
            for i, row in enumerate(table)]


# --- geometry ------------------------------------------------------------------------------------------

def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _lengths(line: Sequence[Point]) -> list[float]:
    return [haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(line, line[1:])]


def _point_at(line: Sequence[Point], lengths: Sequence[float], distance: float) -> Point:
    """The point `distance` metres along `line`, interpolated linearly inside a segment."""
    for (a, b), length in zip(zip(line, line[1:]), lengths):
        if distance <= length and length > 0:
            t = distance / length
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        distance -= length
    return tuple(line[-1])


def midpoint(line: Sequence[Point]) -> Point:
    """The point halfway along a polyline of `(lat, lng)`, by length."""
    if not line:
        raise ValueError("a line needs at least one point")
    lengths = _lengths(line)
    total = sum(lengths)
    if total == 0:
        return tuple(line[0])
    return _point_at(line, lengths, total / 2)


def circles_along(line: Sequence[Point], spacing_m: float = 100.0,
                  radius_m: float = 60.0) -> list[tuple[float, float, float]]:
    """`max(2, round(length / spacing_m) + 1)` circles `(lat, lng, radius_m)` evenly spaced by length
    from the first point of `line` to the last (both ends exactly)."""
    if len(line) < 2:
        raise ValueError("a line needs at least two points")
    lengths = _lengths(line)
    total = sum(lengths)
    n = max(2, round(total / spacing_m) + 1)
    centres = [tuple(line[0])] + [_point_at(line, lengths, total * i / (n - 1)) for i in range(1, n - 1)] \
        + [tuple(line[-1])]
    return [(lat, lng, float(radius_m)) for lat, lng in centres]


# --- closures on routes ------------------------------------------------------------------------------

Circle = tuple[float, float, float]


def line_in_circles(line: Sequence[Point], circles: Sequence[Circle]) -> bool:
    """True when any vertex of `line` lies inside (or on) any circle `(lat, lng, radius_m)`.

    This is the leak test: a route on the customized server must keep every vertex out of a full
    block. It is also how a historical stretch is found on a route's path.
    """
    return any(haversine_m(lat, lng, clat, clng) <= radius
               for lat, lng in line for clat, clng, radius in circles)


def first_crossing_leg(leg_lines: Sequence[Sequence[Point]], circles: Sequence[Circle]) -> int | None:
    """The first leg (1-based) whose road line enters a circle, or None if the path never does.

    `leg_lines[k - 1]` is the line of leg k; for a route of n stops, leg n is the last stop to campus.
    """
    for k, line in enumerate(leg_lines, start=1):
        if line_in_circles(line, circles):
            return k
    return None


def historical_triggers(stop_ids: Sequence[int], leg: int) -> list[dict]:
    """Bus positions for a historical stretch first met on leg `leg` (leg n = last stop to campus).

    Early: at the first stop, every stop remaining. Late: at the last stop before the stretch (stop
    `leg`), the stops after it remaining. A stretch met on the way to campus leaves no stop for the
    late trigger, which is then left out: with nothing left to serve, every method drives the same.
    """
    stops = list(stop_ids)
    if not 1 <= leg <= len(stops):
        raise ValueError(f"leg {leg} is not a leg of a route with {len(stops)} stops")
    out = [{"trigger": "early", "position": stops[0], "remaining": stops}]
    if stops[leg:]:
        out.append({"trigger": "late", "position": stops[leg - 1], "remaining": stops[leg:]})
    return out


def closure_point_ids(stop_ids: Sequence[int], candidate_lists: Iterable[Sequence[int]]) -> list[int]:
    """The points a closure's tables cover: the route's stops in order, then every candidate of any
    trigger that is not a stop of the route, ascending."""
    stops = list(stop_ids)
    extra = sorted({c for cands in candidate_lists for c in cands} - set(stops))
    return stops + extra


def block_rows(rows: Iterable[tuple[int, int, int]], block_kmh: int = 0) -> list[tuple[int, int, int]]:
    """Speed rows with every 0 km/h (a full block) written as `block_kmh`.

    The road-block test (offline plan, Task 2) decides the value: 0 if OSRM 5.27.1 blocks a road
    at speed 0, otherwise 1.
    """
    if block_kmh < 0:
        raise ValueError("block_kmh must not be negative")
    return [(a, b, block_kmh if kmh == 0 else kmh) for a, b, kmh in rows]


def slowed_rows(own_rows: Iterable[tuple[int, int, int]], kmh: int) -> list[tuple[int, int, int]]:
    """Speed rows for a slowed stretch: `kmh` on every segment, but never faster than the segment's
    own speed (`own_rows` are the segments at their own speed)."""
    if kmh < 1:
        raise ValueError("a slowed road needs at least 1 km/h")
    return [(a, b, min(own, kmh)) for a, b, own in own_rows]


# --- historical closures --------------------------------------------------------------------------------

def validate_historical(entries: object, require_coordinates: bool = True) -> list[dict]:
    """Check the historical-closure list of `data/raw/historical_closures.json` and return it.

    Each entry needs an id, a name, a factor in [0, 1), two end points `from` and `to`, and a source.
    With `require_coordinates` (the default), blank coordinates are refused: they must be pinned on
    OpenStreetMap by a person, never guessed. Raises ValueError naming the entry and the field.
    """
    if not isinstance(entries, list):
        raise ValueError("historical closures must be a JSON list")
    seen: set[str] = set()
    for e in entries:
        cid = e.get("id") if isinstance(e, dict) else None
        if not cid or cid in seen:
            raise ValueError(f"historical closure id missing or repeated: {cid!r}")
        seen.add(cid)
        for key in ("name", "source"):
            if not e.get(key):
                raise ValueError(f"historical closure {cid!r}: '{key}' is missing")
        factor = e.get("factor")
        if not isinstance(factor, (int, float)) or not 0 <= factor < 1:
            raise ValueError(f"historical closure {cid!r}: factor must be at least 0 and below 1, got {factor!r}")
        for end in ("from", "to"):
            point = e.get(end)
            if not isinstance(point, dict):
                raise ValueError(f"historical closure {cid!r}: '{end}' end point is missing")
            for axis in ("lat", "lng"):
                value = point.get(axis)
                if value is None:
                    if require_coordinates:
                        raise ValueError(
                            f"historical closure {cid!r}: {end}.{axis} is blank. Pin both end points "
                            f"on OpenStreetMap, on the carriageway itself, and write them into the file "
                            f"by hand (offline plan, Task 5); they must not be guessed.")
                    continue
                low, high = KARACHI_BOX[axis]
                if not isinstance(value, (int, float)) or not low <= value <= high:
                    raise ValueError(f"historical closure {cid!r}: {end}.{axis} = {value!r} is not in Karachi")
    return entries


def load_historical(path: Path) -> list[dict]:
    """Read and validate the historical closures; blank coordinates are refused."""
    return validate_historical(json.loads(Path(path).read_text(encoding="utf-8")))
