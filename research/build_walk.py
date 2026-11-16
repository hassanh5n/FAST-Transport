"""Walking distances between stops from OSRM's foot profile (work item A3; offline plan, Task 3).

    python build_walk.py                     # starts the foot server from ~/fleetcentric-osrm/foot
    python build_walk.py --no-start          # use a foot server already running on --port

Needs Docker and the foot build of the map (see the plan, Task 3 Step 1). Makes one table call for
all 311 stops with `annotations=distance` and writes `data/walk_fall2026_v1.json`:

    {"version": "walk-fall2026-v1", "instance": "fall2026-v1", "profile": "foot", "built_at": ...,
     "max_m": 1000, "pairs": [[from_id, to_id, metres], ...],
     "stats": {"detour_factor": ..., "share_same_route_400": ..., "share_same_route_800": ...}}

Pairs are directed; ids are positions in the instance's `stops` list; only pairs within 1,200 m in a
straight line and 1,000 m of walking are kept. `load_walk` reads the file back for the runner.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

import osrm_tools
from scenario_rules import haversine_m

RESEARCH = Path(__file__).resolve().parent
DATA = RESEARCH / "data"
VERSION = "walk-fall2026-v1"
MAX_WALK_M = 1000
MAX_STRAIGHT_M = 1200
DETOUR_WITHIN_M = 800
SHARE_LIMITS_M = (400, 800)
CONTAINER = "osrm-foot"

Point = tuple[float, float]


def _straight(points: Sequence[Point], i: int, j: int) -> float:
    return haversine_m(points[i][0], points[i][1], points[j][0], points[j][1])


def _check_shape(dist: Sequence[Sequence[float | None]], points: Sequence[Point]) -> None:
    n = len(points)
    if len(dist) != n or any(len(row) != n for row in dist):
        raise ValueError(f"distance table is not {n} x {n}")


def _finite(v: float | None) -> bool:
    return v is not None and math.isfinite(v)


def walk_pairs(dist: Sequence[Sequence[float | None]], points: Sequence[Point],
               max_straight_m: float = MAX_STRAIGHT_M, max_walk_m: float = MAX_WALK_M) -> list[list[int]]:
    """Directed `[from, to, whole metres]` for pairs within both limits; unreachable pairs dropped."""
    _check_shape(dist, points)
    return [[i, j, round(v)] for i, row in enumerate(dist) for j, v in enumerate(row)
            if i != j and _finite(v) and v <= max_walk_m and _straight(points, i, j) <= max_straight_m]


def detour_factor(dist: Sequence[Sequence[float | None]], points: Sequence[Point],
                  within_m: float = DETOUR_WITHIN_M) -> float | None:
    """Median of walk metres over straight-line metres, for pairs within `within_m` straight line."""
    _check_shape(dist, points)
    ratios = []
    for i, row in enumerate(dist):
        for j, v in enumerate(row):
            straight = _straight(points, i, j) if i != j else 0.0
            if straight > 0 and straight <= within_m and _finite(v):
                ratios.append(v / straight)
    return statistics.median(ratios) if ratios else None


def share_same_route(routes: Sequence[Sequence[int]], walk: Mapping[tuple[int, int], float],
                     limit_m: float) -> float:
    """Share of stop visits on `routes` that have another stop of the same route within `limit_m` walk."""
    visits = [(stop, route) for route in routes for stop in route]
    if not visits:
        return 0.0
    near = sum(any(o != s and walk.get((s, o), math.inf) <= limit_m for o in route) for s, route in visits)
    return near / len(visits)


def route_stop_ids(instance: dict) -> list[list[int]]:
    """Stop ids of every baseline route of every contractor, in route order."""
    ids = {s["name"]: i for i, s in enumerate(instance["stops"])}
    return [[ids[name] for name in r["stops"]]
            for c in instance["contractors"].values() for r in c["baseline_routes"]]


def instance_points(instance: dict) -> list[Point]:
    return [(s["lat"], s["lng"]) for s in instance["stops"]]


def build_output(instance: dict, dist: Sequence[Sequence[float | None]], built_at: str) -> dict:
    """The walk file's content from the foot distance table over all stops in instance order."""
    points = instance_points(instance)
    pairs = walk_pairs(dist, points)
    walk = {(a, b): float(m) for a, b, m in pairs}
    routes = route_stop_ids(instance)
    factor = detour_factor(dist, points)
    stats = {"detour_factor": None if factor is None else round(factor, 3)}
    for limit in SHARE_LIMITS_M:
        stats[f"share_same_route_{limit}"] = round(share_same_route(routes, walk, limit), 3)
    return {"version": VERSION, "instance": instance["version"], "profile": "foot", "built_at": built_at,
            "max_m": MAX_WALK_M, "pairs": pairs, "stats": stats}


def load_walk(path: Path) -> dict[tuple[int, int], float]:
    """Directed walking metres `(from_id, to_id) -> metres` from a walk file. Absent pairs are beyond
    the file's `max_m` (or unreachable on foot)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {(int(a), int(b)): float(m) for a, b, m in data["pairs"]}


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Walking distances between stops from OSRM's foot profile.")
    p.add_argument("--foot-dir", type=Path, default=Path.home() / "fleetcentric-osrm" / "foot",
                   help="folder with the foot build (karachi.osrm*); default %(default)s")
    p.add_argument("--port", type=int, default=5001, help="port of the foot server (default %(default)s)")
    p.add_argument("--no-start", action="store_true",
                   help="do not start or stop a container; use a foot server already on --port")
    p.add_argument("--instance", type=Path, default=DATA / "instance_fall2026_v1.json")
    p.add_argument("--out", type=Path, default=DATA / "walk_fall2026_v1.json")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    instance = json.loads(args.instance.read_text(encoding="utf-8"))
    base = f"http://localhost:{args.port}"
    try:
        if not args.no_start:
            osrm_tools.start_server(args.foot_dir, port=args.port, name=CONTAINER)
        try:
            dist = osrm_tools.table(instance_points(instance), base=base, profile="foot",
                                    annotations="distance")
        finally:
            if not args.no_start:
                osrm_tools.stop_server(CONTAINER)
    except (FileNotFoundError, RuntimeError) as err:
        sys.exit(f"build_walk: {err}")
    out = build_output(instance, dist, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    args.out.write_text(json.dumps(out), encoding="utf-8")
    s = out["stats"]
    print(f"{len(out['pairs'])} directed pairs within {MAX_WALK_M} m walk; detour factor "
          f"{s['detour_factor']}; same-route neighbour within 400 m {s['share_same_route_400']:.1%}, "
          f"within 800 m {s['share_same_route_800']:.1%}")
    if s["detour_factor"] is not None and s["detour_factor"] < 1.0:
        print("warning: detour factor below 1.0 means distances and durations were mixed up")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
