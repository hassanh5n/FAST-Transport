"""Build the frozen closure scenarios with true travel times from OSRM (work item A4).

    python build_scenarios.py                       # every route; writes data/scenarios_reroute_v1.json
    python build_scenarios.py --route Jadoon:R-10   # one route, for checking (results/scenarios-check/)
    python build_scenarios.py --resume              # keep the closures already in the output file

Work plan Section 8.2; offline plan, Task 6. Needs Docker, the untouched car build, the road graph,
the walking file and the historical closures with their end points pinned (or `--skip-historical`).

Per route (stops in route order; a stop with no students on this route is dropped from it):

1. The road line of every leg (stop to stop, then last stop to campus) from the untouched server,
   which runs on port 5000 for the whole build.
2. Synthetic closures on the legs of `closure_legs`: a 200 m full-block circle at the `midpoint` of
   the leg's line. The graph's segments in the circle become an OSRM speed file; a fresh copy of the
   untouched files is customized with it and served on port 5002.
3. `pre` and `post` tables over the closure's `points` (the route's stops, then the candidates of
   either trigger) with campus last. `pre` is left as OSRM returned it; in `post` the rows and
   columns of points inside a full-block circle are infinite (`apply_closed`). `null` in the file
   is an unreachable pair, never zero.
4. Leak check: each pair of consecutive open points in route order (campus last) is routed on the
   customized server, and a route with any vertex inside a full-block circle is a leak.
5. Scenarios from `triggers`, candidates from the walking file (800 m), tags from `scenario_tags`.

Historical stretches (`data/raw/historical_closures.json`) become chains of 60 m circles every
100 m along the road line between their end points; each is customized once and applied to every
route whose leg lines enter it, with one closure entry per affected route (`kind` `historical`, no
`leg`, `stretch` naming the stretch) and scenarios from `historical_triggers`. A full block is
written at the block speed chosen by the road-block test (`--block-kmh`, 0 unless that test said
1); a slowed stretch is written at 10 km/h (never faster than the road's own speed) and carried as
its factor (0.25 for University Road).

`load_scenarios` reads the file back with `null` turned into infinity.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import osrm_tools
from osrm_tools import OsrmError, clean_table, speed_csv, to_json_table
from reroute.closure import Closure, closed_points, closed_segments, osrm_speed_rows
from scenario_rules import (apply_closed, block_rows, candidates, circles_along, closure_legs,
                            closure_point_ids, first_crossing_leg, historical_triggers, line_in_circles,
                            load_historical, midpoint, route_students, scenario_id, scenario_tags,
                            slowed_rows, stops_with_students, triggers)

RESEARCH = Path(__file__).resolve().parent
DATA = RESEARCH / "data"
OSRM_HOME = Path.home() / "fleetcentric-osrm"
VERSION = "reroute-v1"
CAMPUS_ID = -1
SYNTHETIC_RADIUS_M = 200.0
HISTORICAL_SPACING_M, HISTORICAL_RADIUS_M = 100.0, 60.0
SLOWED_KMH = 10                  # a slowed historical stretch (University Road) in the speed file
CANDIDATE_WALK_M = 800.0
FASTER_TOLERANCE_S = 0.5         # post below pre by less than this is rounding, not a fault
UNTOUCHED_PORT, CLOSED_PORT = 5000, 5002
UNTOUCHED_NAME, CLOSED_NAME = "osrm", "osrm-scn"

Point = tuple[float, float]


# --- pure helpers --------------------------------------------------------------------------------

@dataclass(frozen=True)
class RouteStops:
    """One baseline route: its stop ids in order (stops without students on it dropped)."""

    contractor: str
    code: str
    stop_ids: list[int]
    students: dict[int, int]
    dropped: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.contractor}-{self.code}"


def route_stops(instance: Mapping, student_rows: Iterable[dict],
                only: tuple[str, str] | None = None) -> list[RouteStops]:
    """Every baseline route of the instance (or only `(contractor, code)`), in instance order."""
    rows = list(student_rows)
    ids = {s["name"]: i for i, s in enumerate(instance["stops"])}
    out = []
    for contractor, c in instance["contractors"].items():
        for r in c["baseline_routes"]:
            if only is not None and (contractor, r["code"]) != only:
                continue
            counts = route_students(rows, contractor, r["code"])
            kept = stops_with_students(r["stops"], counts)
            out.append(RouteStops(contractor, r["code"], [ids[n] for n in kept],
                                  {ids[n]: counts[n] for n in kept},
                                  [n for n in r["stops"] if n not in kept]))
    if only is not None and not out:
        raise KeyError(f"no route {only[0]}:{only[1]} in the instance")
    return out


def line_from(route: Mapping) -> list[Point]:
    """The `(lat, lng)` vertices of an OSRM route's GeoJSON line."""
    return [(float(lat), float(lng)) for lng, lat in route["geometry"]["coordinates"]]


def speed_rows(graph: Any, closure: Closure, block_kmh: int = 0,
               slowed_kmh: int = SLOWED_KMH) -> list[tuple[int, int, int]]:
    """OSRM speed rows for `closure`: a full block at `block_kmh`, a slowed road at `slowed_kmh`
    (never faster than the segment's own speed)."""
    if closure.blocks:
        return block_rows(osrm_speed_rows(graph, closure), block_kmh)
    own = osrm_speed_rows(graph, Closure(closure.id, closure.circles, 1.0))
    return slowed_rows(own, slowed_kmh)


def load_table(values: list[list[float | None]]) -> list[list[float]]:
    """A table read from the scenario file: `null` becomes infinity."""
    return clean_table(values)


def faster_pairs(pre: Sequence[Sequence[float]], post: Sequence[Sequence[float]],
                 tolerance_s: float = FASTER_TOLERANCE_S) -> int:
    """Pairs finite in both tables where `post` is faster than `pre` by more than `tolerance_s`.

    A closure only removes or slows roads, so any such pair points at a snapping difference.
    """
    return sum(1 for rp, rq in zip(pre, post) for p, q in zip(rp, rq)
               if math.isfinite(p) and math.isfinite(q) and q < p - tolerance_s)


def summary(out: Mapping) -> dict:
    """Totals printed at the end of a build."""
    kinds = {c["id"]: c["kind"] for c in out["closures"]}
    contains = {s["closure"] for s in out["scenarios"] if s["tags"]["closure_contains_stop"]}
    return {
        "closures": {k: sum(v == k for v in kinds.values()) for k in ("synthetic", "historical")},
        "scenarios": {k: sum(kinds[s["closure"]] == k for s in out["scenarios"])
                      for k in ("synthetic", "historical")},
        "closures_with_leaks": sum(1 for c in out["closures"] if c["leaks"]),
        "scenarios_closure_contains_stop": sum(s["tags"]["closure_contains_stop"] for s in out["scenarios"]),
        "closures_containing_a_stop": len(contains),
        "faster_pairs": sum(faster_pairs(load_table(c["pre"]), load_table(c["post"])) for c in out["closures"]),
    }


def load_scenarios(path: Path) -> dict:
    """The scenario file with every `pre` and `post` table's `null` turned into infinity."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for c in data["closures"]:
        c["pre"], c["post"] = load_table(c["pre"]), load_table(c["post"])
    return data


def _circle_json(circles: Iterable[tuple[float, float, float]]) -> list[list[float]]:
    return [[round(lat, 6), round(lng, 6), float(r)] for lat, lng, r in circles]


# --- the builder ---------------------------------------------------------------------------------

class ScenarioBuilder:
    """Drives OSRM over every closure. `osrm` is `osrm_tools` or a stand-in with its functions."""

    def __init__(self, osrm: Any, graph: Any, instance: Mapping, student_rows: Iterable[dict],
                 walk: Mapping[tuple[int, int], float], car_dir: Path, work_dir: Path,
                 block_kmh: int = 0, walk_version: str | None = None,
                 log: Callable[[str], None] = print) -> None:
        self.osrm, self.graph, self.walk = osrm, graph, walk
        self.instance, self.student_rows = instance, list(student_rows)
        self.car_dir, self.work_dir = Path(car_dir), Path(work_dir)
        self.block_kmh, self.walk_version, self.log = block_kmh, walk_version, log
        self.coords = [(float(s["lat"]), float(s["lng"])) for s in instance["stops"]]
        self.campus = (float(instance["campus"]["lat"]), float(instance["campus"]["lng"]))
        self.untouched = f"http://localhost:{UNTOUCHED_PORT}"
        self.closed = f"http://localhost:{CLOSED_PORT}"
        self._lines: dict[str, list[list[Point]]] = {}

    def point(self, pid: int) -> Point:
        return self.campus if pid == CAMPUS_ID else self.coords[pid]

    def leg_lines(self, route: RouteStops) -> list[list[Point]]:
        """Road line of every leg on the untouched server; leg n is the last stop to campus."""
        if route.key not in self._lines:
            seq = route.stop_ids + [CAMPUS_ID]
            self._lines[route.key] = [
                line_from(self.osrm.route([self.point(a), self.point(b)], base=self.untouched))
                for a, b in zip(seq, seq[1:])]
        return self._lines[route.key]

    def _customize(self, closure: Closure) -> float:
        """A fresh copy of the untouched files, customized with `closure` and served on CLOSED_PORT."""
        rows = speed_rows(self.graph, closure, self.block_kmh)
        if not rows:
            self.log(f"  warning: {closure.id} touches no road segment of the graph")
        self.osrm.fresh_copy(self.car_dir, self.work_dir)
        seconds = self.osrm.customize(self.work_dir, speed_csv(rows))
        self.osrm.start_server(self.work_dir, port=CLOSED_PORT, name=CLOSED_NAME)
        return seconds

    def _leaks(self, route: RouteStops, closure: Closure, closed_ids: set[int]) -> int:
        """Route each pair of consecutive open points (route order, campus last) on the closed server.

        Closed points are skipped, not used to cut the chain: with stops D, E, F and E, F inside the
        circle, D -> campus is routed. Returns how many of those routes put a vertex in a circle.
        """
        seq = [p for p in route.stop_ids + [CAMPUS_ID] if p not in closed_ids]
        leaks = 0
        for a, b in zip(seq, seq[1:]):
            try:
                answer = self.osrm.route([self.point(a), self.point(b)], base=self.closed)
            except OsrmError as err:
                if err.code != "NoRoute":
                    raise
                continue
            if line_in_circles(line_from(answer), closure.circles):
                leaks += 1
        return leaks

    def _record(self, route: RouteStops, closure: Closure, head: dict, trigger_list: list[dict],
                customize_s: float, scenario_ids: list[str]) -> tuple[dict, list[dict]]:
        """The closure entry and its scenarios, with tables from both servers."""
        cands = [candidates(t["remaining"], self.walk, CANDIDATE_WALK_M) for t in trigger_list]
        points = closure_point_ids(route.stop_ids, cands)
        ids = points + [CAMPUS_ID]
        where = [self.point(p) for p in ids]
        # Closed is judged where each point meets the road before the closure (work plan Section 5), not
        # at its raw coordinate: a stop whose road point is inside a block would otherwise be moved by
        # OSRM onto another road (19 Nov: Race Course, 173 m from its road, in Nadeem-35-L2).
        pre, snapped = self.osrm.table_with_snaps(where, base=self.untouched)
        closed = [bool(v) for v in closed_points([p[0] for p in snapped], [p[1] for p in snapped], [closure])]
        post = apply_closed(self.osrm.table(where, base=self.closed), closed)
        closed_ids = [p for p, c in zip(ids, closed) if c]
        if CAMPUS_ID in closed_ids:
            self.log(f"  warning: {closure.id}: campus is inside the closure, so every scenario of it "
                     f"is infeasible")
        faster = faster_pairs(pre, post)
        if faster:
            self.log(f"  warning: {closure.id}: {faster} pairs faster after the closure than before")
        entry = {**head, "circles": _circle_json(closure.circles), "factor": float(closure.factor),
                 "points": points, "closed_points": closed_ids,
                 "snapped": [[round(lat, 6), round(lng, 6)] for lat, lng in snapped],
                 "pre": to_json_table(pre), "post": to_json_table(post),
                 "segments": int(len(closed_segments(self.graph, closure))),
                 "leaks": self._leaks(route, closure, set(closed_ids)) if closure.blocks else None,
                 "customize_s": round(float(customize_s), 1)}
        scenarios = [{"id": sid, "closure": entry["id"], "trigger": t["trigger"], "position": t["position"],
                      "remaining": list(t["remaining"]),
                      "students": {str(s): route.students[s] for s in t["remaining"]},
                      "candidates": cand, "tags": scenario_tags(t["remaining"], closed_ids)}
                     for sid, t, cand in zip(scenario_ids, trigger_list, cands)]
        self.log(f"  {entry['id']}: {entry['segments']} segments, leaks {entry['leaks']}, "
                 f"closed points {closed_ids}, customize {entry['customize_s']} s")
        return entry, scenarios

    def synthetic(self, route: RouteStops, done: set[str]) -> Iterable[tuple[dict, list[dict]]]:
        """The route's synthetic closures not in `done`, one customization each."""
        legs = closure_legs(len(route.stop_ids))
        if not legs:
            self.log(f"{route.key}: {len(route.stop_ids)} stops with students; no synthetic closure")
        for leg in legs:
            cid = f"{route.key}-L{leg}"
            if cid in done:
                continue
            centre = midpoint(self.leg_lines(route)[leg - 1])
            closure = Closure(cid, ((centre[0], centre[1], SYNTHETIC_RADIUS_M),), 0.0)
            seconds = self._customize(closure)
            head = {"id": cid, "kind": "synthetic", "contractor": route.contractor, "route": route.code,
                    "leg": leg}
            trig = triggers(route.stop_ids, leg)
            yield self._record(route, closure, head, trig, seconds,
                               [scenario_id(route.contractor, route.code, leg, t["trigger"]) for t in trig])

    def historical(self, stretch: Mapping, routes: Sequence[RouteStops],
                   done: set[str]) -> Iterable[tuple[dict, list[dict]]]:
        """One closure entry per route whose path enters the stretch; one customization in all."""
        if stretch.get("both_directions") is False:
            raise ValueError(f"historical closure {stretch['id']}: one-direction stretches are not "
                             f"supported (the circles close every direction)")
        ends = [(stretch[k]["lat"], stretch[k]["lng"]) for k in ("from", "to")]
        line = line_from(self.osrm.route(ends, base=self.untouched))
        closure = Closure(stretch["id"], tuple(circles_along(line, HISTORICAL_SPACING_M, HISTORICAL_RADIUS_M)),
                          float(stretch["factor"]))
        affected = []
        for route in routes:
            cid = f"{stretch['id']}-{route.key}"
            if cid in done or not route.stop_ids:
                continue
            leg = first_crossing_leg(self.leg_lines(route), closure.circles)
            if leg is not None:
                affected.append((route, cid, leg))
        self.log(f"{stretch['id']}: {len(closure.circles)} circles, {len(affected)} routes to build")
        if not affected:
            return
        seconds = self._customize(closure)
        for route, cid, leg in affected:
            head = {"id": cid, "kind": "historical", "stretch": stretch["id"], "contractor": route.contractor,
                    "route": route.code}
            trig = historical_triggers(route.stop_ids, leg)
            yield self._record(route, closure, head, trig, seconds, [f"{cid}-{t['trigger']}" for t in trig])

    def build(self, routes: Sequence[RouteStops], historical: Sequence[Mapping],
              existing: Mapping | None = None,
              on_closure: Callable[[dict], None] | None = None) -> dict:
        """The scenario file's content. Closures in `existing` are kept and not rebuilt;
        `on_closure` is called with the whole content after every new closure."""
        out = {"version": VERSION, "instance": self.instance["version"],
               "graph": getattr(self.graph, "version", None), "walk": self.walk_version,
               "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "osrm_image": osrm_tools.IMAGE, "block_kmh": self.block_kmh,
               "closures": list(existing["closures"]) if existing else [],
               "scenarios": list(existing["scenarios"]) if existing else []}
        done = {c["id"] for c in out["closures"]}

        def add(pair: tuple[dict, list[dict]]) -> None:
            entry, scenarios = pair
            out["closures"].append(entry)
            out["scenarios"].extend(scenarios)
            if on_closure is not None:
                on_closure(out)

        self.osrm.start_server(self.car_dir, port=UNTOUCHED_PORT, name=UNTOUCHED_NAME)
        try:
            for route in routes:
                if route.dropped:
                    self.log(f"{route.key}: dropped stops without students here: {', '.join(route.dropped)}")
                for pair in self.synthetic(route, done):
                    add(pair)
            for stretch in historical:
                for pair in self.historical(stretch, routes, done):
                    add(pair)
        finally:
            self.osrm.stop_server(CLOSED_NAME)
            self.osrm.stop_server(UNTOUCHED_NAME)
        return out


# --- command line ----------------------------------------------------------------------------------

def write_json(path: Path, content: Mapping) -> None:
    """Write `content` to `path` through a temporary file, so a stopped build never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(content), encoding="utf-8")
    os.replace(tmp, path)


def _route_arg(text: str) -> tuple[str, str]:
    contractor, sep, code = text.partition(":")
    if not sep or not contractor or not code:
        raise argparse.ArgumentTypeError("use CONTRACTOR:ROUTE, for example Jadoon:R-10")
    return contractor, code


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build the frozen closure scenarios (work item A4).")
    p.add_argument("--route", type=_route_arg, help="one route only, CONTRACTOR:ROUTE (for checking)")
    p.add_argument("--resume", action="store_true", help="keep the closures already in the output file")
    p.add_argument("--skip-historical", action="store_true", help="build the synthetic closures only")
    p.add_argument("--block-kmh", type=int, choices=(0, 1), default=0,
                   help="speed that blocks a road, from the road-block test (default %(default)s)")
    p.add_argument("--car-dir", type=Path, default=OSRM_HOME / "car")
    p.add_argument("--work-dir", type=Path, default=OSRM_HOME / "work")
    p.add_argument("--graph", type=Path, default=DATA / "graph_karachi_v1")
    p.add_argument("--instance", type=Path, default=DATA / "instance_fall2026_v1.json")
    p.add_argument("--students", type=Path, default=DATA / "students_synthetic_fall2026.csv")
    p.add_argument("--walk", type=Path, default=DATA / "walk_fall2026_v1.json")
    p.add_argument("--historical", type=Path, default=DATA / "raw" / "historical_closures.json")
    p.add_argument("--out", type=Path, help="default data/scenarios_reroute_v1.json, or "
                                            "results/scenarios-check/ with --route")
    return p.parse_args(argv)


def _out_path(args: argparse.Namespace) -> Path:
    if args.out is not None:
        return args.out
    if args.route:
        return RESEARCH / "results" / "scenarios-check" / f"scenarios_{args.route[0]}_{args.route[1]}.json"
    return DATA / "scenarios_reroute_v1.json"


def _existing(path: Path, instance: Mapping, block_kmh: int) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key, want in (("version", VERSION), ("instance", instance["version"]), ("block_kmh", block_kmh)):
        if data.get(key) != want:
            sys.exit(f"build_scenarios: cannot resume {path}: its {key} is {data.get(key)!r}, not {want!r}")
    if any("snapped" not in c for c in data.get("closures", [])):
        sys.exit(f"build_scenarios: cannot resume {path}: it was built before closed points were judged where "
                 f"each point meets the road (20 Nov); build it again without --resume")
    return data


def main(argv: Sequence[str] | None = None, osrm: Any = osrm_tools, graph: Any = None) -> dict:
    """Build (or finish) the scenario file. `osrm` and `graph` can be replaced in tests."""
    args = parse_args(argv)
    out_path = _out_path(args)
    instance = json.loads(args.instance.read_text(encoding="utf-8"))
    with args.students.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    walk_data = json.loads(args.walk.read_text(encoding="utf-8"))
    walk = {(int(a), int(b)): float(m) for a, b, m in walk_data["pairs"]}
    historical: list[dict] = []
    if not args.skip_historical:
        try:
            historical = load_historical(args.historical)
        except ValueError as err:
            sys.exit(f"build_scenarios: {err}\nPass --skip-historical to build the synthetic scenarios only.")
    existing = _existing(out_path, instance, args.block_kmh) if args.resume and out_path.exists() else None
    if graph is None:
        from reroute.graph import Graph
        graph = Graph.load(args.graph)

    builder = ScenarioBuilder(osrm, graph, instance, rows, walk, args.car_dir, args.work_dir,
                              block_kmh=args.block_kmh, walk_version=walk_data.get("version"))
    routes = route_stops(instance, rows, only=args.route)
    try:
        out = builder.build(routes, historical, existing, on_closure=lambda o: write_json(out_path, o))
    except (FileNotFoundError, RuntimeError, ValueError) as err:
        sys.exit(f"build_scenarios: {err}")
    write_json(out_path, out)

    s = summary(out)
    print(f"closures: {s['closures']['synthetic']} synthetic, {s['closures']['historical']} historical; "
          f"scenarios: {s['scenarios']['synthetic']} synthetic, {s['scenarios']['historical']} historical")
    print(f"scenarios whose closure contains a remaining stop: {s['scenarios_closure_contains_stop']}; "
          f"pairs faster after a closure: {s['faster_pairs']}")
    print(f"closures with leaks: {s['closures_with_leaks']}; wrote {out_path}")
    if s["closures_with_leaks"]:
        sys.exit("build_scenarios: some closures leak. Find out why before freezing the file "
                 "(offline plan, Task 6 Step 4).")
    return out


if __name__ == "__main__":
    main()
