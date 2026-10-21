"""
The main-road line a bus actually drives, and where each rider boards it.

A Karachi shuttle keeps to the main road. A rider whose stop is pinned inside a
street walks out to the main road and is picked up there; the bus does not turn
in, U-turn or lap a roundabout to reach the pin. So the line is not routed
through every stop:

1. Only the first stop and the campus are waypoints ("anchors") at first.
2. The router drives between the anchors on main roads (secondary and up).
3. Each stop is matched to the point of the line closest to it, its boarding
   point. A stop farther than MAP_STOP_WALK_M from the line is not served yet:
   the farthest such stop becomes an anchor and the line is routed again.
4. An anchor the line still passes too far from may use the next smaller road
   class (tertiary, then unclassified, then residential), so the bus turns in for
   that stop only, and only as far as it must.

After every pass, loops are cut: where the line comes back to a point it already
passed (a U-turn on a divided road, a lap of a roundabout, an out-and-back into a
side road) the excursion is removed, as long as no stop ends up farther from the
line than it was allowed to be.

This is a greedy heuristic for the shortest covering path problem (Current,
Pirkul & Rolland 1994): the cheapest path from the first stop to campus that
passes within walking distance of every stop.

The public router (valhalla1.openstreetmap.de) takes at most 10 locations per
request and about one request a second. Longer anchor lists are routed in
overlapping chunks and joined.
"""

import logging
import math
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

ROUTE_LINE_VERSION = 2          # bump to make every saved line rebuild
ROAD_CLASSES = ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential")
SNAP_RADIUS_M = 50              # either carriageway of a divided road counts
LOOP_TOLERANCE_M = 30           # the line "comes back" when it passes this close to itself
LOOP_MIN_LENGTH_M = 120         # shorter wiggles are junction geometry, not detours
MAX_PASSES = 10                 # routing passes per route (each pass is 1+ requests)
CHUNK_GAP_SECONDS = 1           # the free router allows about one request a second
EARTH_RADIUS_M = 6371000


def _setting(name, default):
    return getattr(settings, name, default)


def road_class_ladder():
    """MAP_MAIN_ROAD_CLASS and every smaller class, biggest first."""
    main = _setting("MAP_MAIN_ROAD_CLASS", "secondary")
    return ROAD_CLASSES[ROAD_CLASSES.index(main):] if main in ROAD_CLASSES else ROAD_CLASSES[3:]


# ── Geometry helpers (lng, lat in degrees; metres via a local flat projection) ──

def haversine_m(a, b):
    (lng1, lat1), (lng2, lat2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def _flat(point, origin):
    """Metres east/north of origin. Accurate to well under 1% across a city."""
    kx = math.cos(math.radians(origin[1])) * math.pi / 180 * EARTH_RADIUS_M
    ky = math.pi / 180 * EARTH_RADIUS_M
    return (point[0] - origin[0]) * kx, (point[1] - origin[1]) * ky


def project(line, point):
    """Closest point of `line` to `point`: (distance_m, chainage_m, [lng, lat], segment, t)."""
    best = (float("inf"), 0.0, list(line[0]), 0, 0.0)
    chainage = 0.0
    for index in range(1, len(line)):
        a, b = line[index - 1], line[index]
        ax, ay = _flat(a, point)
        bx, by = _flat(b, point)
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        t = 0.0 if not length_sq else max(0.0, min(1.0, -(ax * dx + ay * dy) / length_sq))
        qx, qy = ax + t * dx, ay + t * dy
        distance = math.hypot(qx, qy)
        length = math.sqrt(length_sq)
        if distance < best[0]:
            best = (
                distance, chainage + t * length,
                [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])], index, t,
            )
        chainage += length
    return best


def _walks(line, points):
    return [project(line, point)[0] for point in points]


def line_length_m(line):
    return sum(haversine_m(a, b) for a, b in zip(line, line[1:]))


# ── Router ──

def _decode_polyline6(encoded):
    """[[lng, lat], ...] from a Valhalla shape (Google polyline, 6 decimals)."""
    coordinates, index, values = [], 0, [0, 0]
    while index < len(encoded):
        for axis in (0, 1):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            values[axis] += ~(result >> 1) if result & 1 else result >> 1
        coordinates.append([round(values[1] / 1e6, 6), round(values[0] / 1e6, 6)])
    return coordinates


def _route_chunk(points, road_classes, timeout):
    """One router request. [(shape, seconds, metres)] per leg, or None."""
    last = len(points) - 1
    body = {
        "locations": [
            {
                "lon": lng, "lat": lat,
                # break_through: a stop the bus passes without a U-turn at it
                "type": "break" if index in (0, last) else "break_through",
                "radius": SNAP_RADIUS_M,
                "search_filter": {"min_road_class": road_class},
            }
            for index, ((lng, lat), road_class) in enumerate(zip(points, road_classes))
        ],
        "costing": "bus",
        "costing_options": {"bus": {"use_living_streets": 0}},
        "directions_type": "none",
    }
    try:
        for attempt in range(2):
            response = requests.post(f"{settings.MAP_ROUTING_URL}/route", json=body, timeout=timeout)
            if response.status_code != 429 or attempt:
                break
            time.sleep(2)
        response.raise_for_status()
        legs = response.json()["trip"]["legs"]
        result = [
            (_decode_polyline6(leg["shape"]), float(leg["summary"]["time"]), float(leg["summary"]["length"]) * 1000)
            for leg in legs
        ]
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        reply = getattr(getattr(exc, "response", None), "text", "")
        logger.warning("Routing failed (%s points): %r %s", len(points), exc, reply[:300])
        return None
    if len(result) != last:
        return None
    return result


def route_through(points, road_classes=None, timeout=15):
    """Drive through `points` in order: (line, segment_seconds, legs) or None.

    `segment_seconds[i]` is the drive time from line[i-1] to line[i] (0 for i=0);
    `legs` is [(seconds, metres)] per point-to-point leg. More points than the
    router accepts are sent in chunks that share their end point.
    """
    if len(points) < 2:
        return None
    road_classes = list(road_classes or [road_class_ladder()[0]] * len(points))
    per_request = max(2, int(_setting("MAP_ROUTING_MAX_LOCATIONS", 10)))
    line, seconds, legs = [], [], []
    start = 0
    while start < len(points) - 1:
        end = min(start + per_request, len(points))
        if start:
            time.sleep(CHUNK_GAP_SECONDS)
        chunk = _route_chunk(points[start:end], road_classes[start:end], timeout)
        if chunk is None:
            return None
        for shape, leg_seconds, leg_metres in chunk:
            if not line:
                line.append(shape[0])
                seconds.append(0.0)
            pieces = shape[1:]
            # spread the leg's time over its shape by distance
            previous = line[-1]
            lengths = []
            for point in pieces:
                lengths.append(haversine_m(previous, point))
                previous = point
            total = sum(lengths) or 1.0
            seconds.extend(leg_seconds * length / total for length in lengths)
            line.extend(pieces)
            legs.append((leg_seconds, leg_metres))
        start = end - 1
    if len(line) < 2:
        return None
    return line, seconds, legs


# ── Loop removal ──

def _cell(point, size_deg):
    return int(point[0] // size_deg), int(point[1] // size_deg)


def _find_loop(line, start_from=0):
    """First (i, j) where the line returns within LOOP_TOLERANCE_M of line[i] after
    more than LOOP_MIN_LENGTH_M of driving. j is the last such return."""
    size_deg = LOOP_TOLERANCE_M / 111000
    cells = {}
    for index, point in enumerate(line):
        cells.setdefault(_cell(point, size_deg), []).append(index)
    chainage = [0.0]
    for a, b in zip(line, line[1:]):
        chainage.append(chainage[-1] + haversine_m(a, b))
    for i in range(start_from, len(line)):
        cx, cy = _cell(line[i], size_deg)
        latest = -1
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in cells.get((cx + dx, cy + dy), ()):
                    if (j > latest and chainage[j] - chainage[i] > LOOP_MIN_LENGTH_M
                            and haversine_m(line[i], line[j]) <= LOOP_TOLERANCE_M):
                        latest = j
        if latest > i:
            return i, latest
    return None


def cut_loops(line, seconds, stop_points, walk_limit_m):
    """Remove loops from the line unless that strands a stop.

    A stop may end up at most max(walk_limit_m, its distance before) from the line.
    Returns (line, seconds, metres_removed).
    """
    nearest = [project(line, point) for point in stop_points]
    allowed = [max(walk_limit_m, found[0]) + 1 for found in nearest]
    removed = 0.0
    start_from = 0
    for _ in range(200):  # each cut shortens the line; this is only a safety net
        found = _find_loop(line, start_from)
        if not found:
            break
        i, j = found
        candidate = line[:i + 1] + line[j + 1:]
        # Only a stop whose closest point is inside the cut part can end up farther away.
        affected = [k for k, near in enumerate(nearest) if i < near[3] <= j + 1]
        if len(candidate) >= 2 and all(project(candidate, stop_points[k])[0] <= allowed[k] for k in affected):
            removed += line_length_m(line[i:j + 1])
            seconds = seconds[:i + 1] + seconds[j + 1:]
            line = candidate
            nearest = [project(line, point) for point in stop_points]
            start_from = max(0, i - 1)
        else:
            start_from = i + 1  # this loop serves a stop: keep it, look further on
    return line, seconds, removed


# ── The corridor ──

def build_corridor(stop_points, walk_m=None, timeout=15):
    """The line for stops in this order (first stop ... campus), or None.

    Returns {
        "line": [[lng, lat], ...],
        "stops": [{"at": [lng, lat], "walk_m": int, "s": seconds from the first boarding point,
                   "km": distance along the line}],
        "anchors": [stop index, ...],     # stops the line was routed through
        "turn_ins": [stop index, ...],    # anchors that needed a road smaller than secondary
        "removed_m": metres of loops cut,
    }
    """
    walk_m = float(walk_m or _setting("MAP_STOP_WALK_M", 500))
    points = [(float(lng), float(lat)) for lng, lat in stop_points]
    if len(points) < 2:
        return None
    count = len(points)
    ladder = road_class_ladder()
    top = len(ladder) - 1
    level = [0] * count
    anchors = [0, count - 1]
    best = None
    for _ in range(MAX_PASSES):
        trip = route_through([points[i] for i in anchors], [ladder[level[i]] for i in anchors], timeout)
        if trip is None:
            # No way through with these snaps (e.g. a stop with no main road near
            # it at all): let every anchor reach one road class lower, then retry.
            if all(level[i] >= top for i in anchors):
                break
            for i in anchors:
                level[i] = min(level[i] + 1, top)
            continue
        line, seconds, _ = trip
        line, seconds, removed = cut_loops(line, seconds, points, walk_m)
        walks = _walks(line, points)
        best = (line, seconds, list(anchors), list(level), removed)

        far_anchors = [i for i in anchors if walks[i] > walk_m and level[i] < top]
        if far_anchors:
            for i in far_anchors:
                level[i] += 1
            continue
        uncovered = [(walks[i], i) for i in range(count) if i not in anchors and walks[i] > walk_m]
        if not uncovered:
            break
        anchors = sorted(anchors + [max(uncovered)[1]])
    if best is None:
        return None

    line, seconds, anchors, level, removed = best
    elapsed = [0.0]
    for value in seconds[1:]:
        elapsed.append(elapsed[-1] + value)
    chainage = [0.0]
    for a, b in zip(line, line[1:]):
        chainage.append(chainage[-1] + haversine_m(a, b))

    stops = []
    for point in points:
        distance, along, at, segment, t = project(line, point)
        at_seconds = elapsed[segment - 1] + t * (elapsed[segment] - elapsed[segment - 1])
        stops.append({"at": at, "walk_m": distance, "s": at_seconds, "km": along / 1000})
    first = stops[0]["s"]
    for stop in stops:
        stop["s"] = round(stop["s"] - first)
        stop["walk_m"] = round(stop["walk_m"])
        stop["km"] = round(stop["km"], 2)
        stop["at"] = [round(stop["at"][0], 6), round(stop["at"][1], 6)]
    return {
        "line": line,
        "stops": stops,
        "anchors": anchors,
        "turn_ins": [i for i in anchors if level[i] > 0],
        "removed_m": round(removed),
        "length_m": round(chainage[-1]),
    }
