"""Build the FleetCentric research instance (Fall 2026) with synthetic students.

    python research/build_instance.py

Reads research/data/raw/ and writes research/data/:
  instance_fall2026_v1.json   stops, campus, buses, current routes, students per stop
  students_synthetic_fall2026.csv   one row per synthetic student (no real person)

Rules (agreed 3 Nov 2026):
- Stop locations in the route plan are trusted as they are. Stops with no
  location at all are placed midway between their located neighbours on the route.
- Stops with the same name (case and spaces ignored) or within 25 m are one stop,
  the first one seen wins, as in backend/apps/transport/stop_import.py.
- A stop may be served by both contractors. Each contractor plans its own routes
  with its own buses.
- Bus data is synthetic. Jadoon runs 27 routes with 26 buses, so one bus is added.

Synthetic students, fixed seed so every run gives the same file:
- Each current route gets one bus, larger buses on routes with more stops.
- The bus is filled to a load factor drawn from U(0.65, 0.90).
- Those students are spread over the route's stops with log-normal weights
  (sigma 0.6), at least one student per stop.
The current routes are therefore feasible by construction, and the optimizer
must serve exactly the same students, so the comparison is fair.
"""
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path

import h3

SEED = 2026
LOAD_FACTOR = (0.65, 0.90)
STOP_WEIGHT_SIGMA = 0.6
MERGE_RADIUS_M = 25
EXTRA_BUSES = [{"bus_number": "JDN-126", "capacity": 45, "contractor": "Jadoon"}]

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data"


def norm(name):
    return " ".join(str(name).lower().split())


def dist_m(a, b):
    rad = math.pi / 180
    x = (b[1] - a[1]) * rad * math.cos((a[0] + b[0]) * rad / 2)
    y = (b[0] - a[0]) * rad
    return 6371000 * math.hypot(x, y)


plan = json.loads((RAW / "fast_karachi_fall2026.json").read_text())
campus = plan["campus"]

# 1. Locations: as given. The 11 stops with none are placed from their route
# neighbours, which is what their hints describe ("between X and Y", "just before X"):
# - between two located stops: spaced evenly between them;
# - at the start of a route: STEP_M apart before the first located stop,
#   continuing the route's direction backwards;
# - at the end of a route: STEP_M apart after the last located stop, continuing forwards.
# They are marked "interpolated". Replace them with real points when known.
STEP_M = 300
coords = {n: (v["lat"], v["lng"]) for n, v in plan["stops"].items() if v.get("lat") is not None}
source = {n: plan["stops"][n]["status"] for n in coords}


def step_from(p, q, metres):
    """The point `metres` beyond p, on the line from q through p."""
    d = dist_m(q, p) or 1.0
    return (p[0] + (p[0] - q[0]) * metres / d, p[1] + (p[1] - q[1]) * metres / d)


for route in plan["routes"]:
    names = [s["name"].strip() for s in route["stops"]]
    located = [coords[m] for m in names if m in coords]
    i = 0
    while i < len(names):
        if names[i] in coords:
            i += 1
            continue
        j = i
        while j < len(names) and names[j] not in coords:
            j += 1
        gap = names[i:j]
        before = [coords[m] for m in names[:i] if m in coords]
        after = [coords[m] for m in names[j:] if m in coords]
        for k, n in enumerate(gap, 1):
            if before and after:
                a, b, t = before[-1], after[0], k / (len(gap) + 1)
                coords[n] = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            elif after:  # start of route: count back from the first located stop
                coords[n] = step_from(after[0], after[1], STEP_M * (len(gap) + 1 - k))
            else:  # end of route
                coords[n] = step_from(before[-1], before[-2], STEP_M * k)
            source[n] = "interpolated"
        i = j

# 2. One stop per place: same normalised name or within 25 m, first seen wins.
canonical, kept = {}, []
for route in plan["routes"]:
    for s in route["stops"]:
        n = s["name"].strip()
        if n in canonical:
            continue
        # A guessed position never merges with anything; only real names and locations do.
        close = lambda k: "interpolated" not in (source[k], source[n]) and dist_m(coords[k], coords[n]) <= MERGE_RADIUS_M
        match = next((k for k in kept if norm(k) == norm(n) or close(k)), None)
        canonical[n] = match or n
        if match is None:
            kept.append(n)

# 3. Buses: given list plus the extra, assigned to routes by size.
buses = defaultdict(list)
with open(RAW / "buses_fall2026.csv") as f:
    for b in csv.DictReader(f):
        if b["is_active"].strip().lower() == "true":
            buses[b["contractor"]].append({"bus_number": b["bus_number"], "capacity": int(b["capacity"])})
for b in EXTRA_BUSES:
    buses[b["contractor"]].append({"bus_number": b["bus_number"], "capacity": b["capacity"]})

rng = random.Random(SEED)
contractors = {}
students = []
demand = defaultdict(lambda: defaultdict(int))  # stop -> contractor -> students
for cname in sorted(buses):
    routes = [r for r in plan["routes"] if r["operator"] == cname]
    fleet = sorted(buses[cname], key=lambda b: (-b["capacity"], b["bus_number"]))
    by_size = sorted(routes, key=lambda r: (-len(r["stops"]), r["code"]))
    assert len(fleet) >= len(routes), f"{cname}: {len(routes)} routes, {len(fleet)} buses"
    baseline = []
    for route, bus in zip(by_size, fleet):
        order = list(dict.fromkeys(canonical[s["name"].strip()] for s in route["stops"]))
        riders = round(bus["capacity"] * rng.uniform(*LOAD_FACTOR))
        weights = [rng.lognormvariate(0, STOP_WEIGHT_SIGMA) for _ in order]
        counts = [1] * len(order)
        for _ in range(riders - len(order)):
            counts[rng.choices(range(len(order)), weights)[0]] += 1
        for stop, k in zip(order, counts):
            demand[stop][cname] += k
            for _ in range(k):
                students.append({"contractor": cname, "stop": stop,
                                 "baseline_route": route["code"], "baseline_bus": bus["bus_number"]})
        baseline.append({"code": route["code"], "bus": bus["bus_number"], "capacity": bus["capacity"],
                         "students": riders, "stops": order})
    contractors[cname] = {
        "buses": sorted(fleet, key=lambda b: b["bus_number"]),
        "baseline_routes": sorted(baseline, key=lambda r: r["code"]),
        "stops": sorted({s for r in baseline for s in r["stops"]}),
    }

stops = []
for n in sorted(kept):
    lat, lng = coords[n]
    stops.append({"name": n, "lat": lat, "lng": lng, "location": source[n],
                  "also_named": sorted(a for a, c in canonical.items() if c == n and a != n),
                  "h3_r9": h3.latlng_to_cell(lat, lng, 9), "h3_r10": h3.latlng_to_cell(lat, lng, 10),
                  "students": dict(sorted(demand[n].items()))})

instance = {
    "version": "fall2026-v1",
    "frozen": True,
    "built_by": "research/build_instance.py",
    "students_are_synthetic": True,
    "seed": SEED,
    "campus": {**campus, "h3_r9": h3.latlng_to_cell(campus["lat"], campus["lng"], 9)},
    "arrival_deadline": "08:00",
    "contractors": contractors,
    "stops": stops,
}
(OUT / "instance_fall2026_v1.json").write_text(json.dumps(instance, indent=1))
with open(OUT / "students_synthetic_fall2026.csv", "w", newline="") as f:
    w = csv.DictWriter(f, ["student_id", "contractor", "stop", "baseline_route", "baseline_bus"])
    w.writeheader()
    for i, s in enumerate(students, 1):
        w.writerow({"student_id": f"SYN-{i:04d}", **s})

# Self-checks: every student is at a known stop, no current route is over capacity.
names = {s["name"] for s in stops}
assert all(s["stop"] in names for s in students)
for c in contractors.values():
    for r in c["baseline_routes"]:
        assert r["students"] <= r["capacity"] and len(r["stops"]) <= r["students"]
print(f"{len(stops)} stops ({sum(s['location'] == 'interpolated' for s in stops)} interpolated), "
      f"{len(students)} students, merged: {sorted(a for a, c in canonical.items() if a != c)}")
for cname, c in contractors.items():
    seats = sum(b["capacity"] for b in c["buses"])
    riders = sum(r["students"] for r in c["baseline_routes"])
    print(f"{cname}: {len(c['stops'])} stops, {len(c['baseline_routes'])} routes, "
          f"{len(c['buses'])} buses, {seats} seats, {riders} students")
