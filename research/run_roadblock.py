"""The road-block test (work item A2; work plan Section 8.1; offline plan, Task 2).

    python run_roadblock.py                  # needs Docker and the untouched car build

Four checks on one fixed leg, the first leg of Jadoon route R-10 (Hyderi Super Mart KDA to Ziauddin):

1. **Speed 0.** The middle pair of consecutive map nodes of the leg's route is written at 0 km/h in
   both directions, on a fresh copy of the OSRM files; the leg is routed again. `blocks` when the new
   route avoids the pair (either direction) and is slower; `ignored` when the route is unchanged. On
   `ignored` the check is repeated at 1 km/h, and the scenarios must then use 1 km/h.
2. **Snapping.** A route starting at the midpoint of the closed pair, before and after the closure:
   `moved` when OSRM moved the start (`waypoints[0].distance`) more than 20 m further.
3. **Slowed.** The same pair at 5 km/h on a fresh copy: `changes route`, `same route, longer` or
   `no effect`.
4. **Timings.** Repeats of fresh copy, customize with the closed pair, and server start until the
   first `Ok`, each timed, with the customize run's peak memory as OSRM itself logs it
   (`RAM: peak bytes used`).

Writes `results/roadblock/result.json` with `machine`, `osrm_image`, `leg`, `block_kmh` (the speed
that blocks a road, 0 or 1, or null when neither did), `checks` (each `{"question", "answer",
"evidence"}`) and `timings`. The untouched server runs on port 5000 and the customized one on 5002.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np

import osrm_tools
from osrm_tools import OsrmError, speed_csv

RESEARCH = Path(__file__).resolve().parent
OSRM_HOME = Path.home() / "fleetcentric-osrm"
UNTOUCHED_PORT, TEST_PORT = 5000, 5002
UNTOUCHED_NAME, TEST_NAME = "osrm", "osrm-roadblock"
SNAP_MOVED_M = 20.0
SLOWED_KMH = 5
SAME_DURATION_S = 0.05            # durations closer than this count as equal
REPEATS = 5
LEG_CONTRACTOR, LEG_ROUTE = "Jadoon", "R-10"

Point = tuple[float, float]
Pair = tuple[int, int]

_PEAK_RAM = re.compile(r"RAM: peak bytes used:\s*(\d+)")


# --- answer rules (pure) -----------------------------------------------------------------------

def route_nodes(route: dict) -> list[int]:
    """The map node ids of a route requested with `nodes=True`, legs joined without the repeated joint."""
    out: list[int] = []
    for leg in route["legs"]:
        nodes = [int(n) for n in leg["annotation"]["nodes"]]
        out += nodes[1:] if out and nodes and out[-1] == nodes[0] else nodes
    return out


def middle_pair(nodes: Sequence[int]) -> Pair:
    """The middle pair of consecutive node ids (the later one of two middle pairs)."""
    if len(nodes) < 2:
        raise ValueError("a route needs at least two map nodes to have a segment")
    k = (len(nodes) - 1) // 2
    return int(nodes[k]), int(nodes[k + 1])


def uses_pair(nodes: Sequence[int], pair: Pair) -> bool:
    """True when `pair` appears as consecutive nodes of `nodes`, in either direction."""
    a, b = pair
    return any((u, v) in ((a, b), (b, a)) for u, v in zip(nodes, nodes[1:]))


def block_answer(before_nodes: Sequence[int], before_s: float, after_nodes: Sequence[int],
                 after_s: float, pair: Pair) -> str:
    """`blocks`, `ignored` (route unchanged) or `unclear` (changed, but not both avoiding and slower)."""
    if list(after_nodes) == list(before_nodes):
        return "ignored"
    if not uses_pair(after_nodes, pair) and after_s > before_s + SAME_DURATION_S:
        return "blocks"
    return "unclear"


def snap_answer(before_m: float, after_m: float, threshold_m: float = SNAP_MOVED_M) -> str:
    """`moved` when the start was moved more than `threshold_m` further after the closure."""
    return "moved" if after_m - before_m > threshold_m else "not moved"


def slowed_answer(before_nodes: Sequence[int], before_s: float, after_nodes: Sequence[int],
                  after_s: float) -> str:
    """`changes route`, `same route, longer` or `no effect`."""
    if list(after_nodes) != list(before_nodes):
        return "changes route"
    return "same route, longer" if after_s > before_s + SAME_DURATION_S else "no effect"


def peak_ram_bytes(log: str) -> int | None:
    """The `RAM: peak bytes used` figure an OSRM tool logs at its end, or None."""
    found = _PEAK_RAM.findall(log or "")
    return int(found[-1]) if found else None


def segment_midpoint(graph: Any, pair: Pair) -> Point:
    """The midpoint of the road segment between the two map nodes of `pair` (either direction)."""
    a, b = pair
    f, t = np.asarray(graph.seg_from), np.asarray(graph.seg_to)
    hits = np.flatnonzero(((f == a) & (t == b)) | ((f == b) & (t == a)))
    if not len(hits):
        raise ValueError(f"map nodes {a} and {b} are not a segment of the road graph; "
                         f"the graph and the OSRM build come from different maps")
    s = int(hits[0])
    return ((float(graph.seg_lat1[s]) + float(graph.seg_lat2[s])) / 2,
            (float(graph.seg_lng1[s]) + float(graph.seg_lng2[s])) / 2)


def first_leg(instance: dict, contractor: str, code: str) -> tuple[tuple[str, Point], tuple[str, Point]]:
    """`(name, (lat, lng))` of the first two stops of one baseline route."""
    coords = {s["name"]: (s["lat"], s["lng"]) for s in instance["stops"]}
    for r in instance["contractors"][contractor]["baseline_routes"]:
        if r["code"] == code:
            a, b = r["stops"][:2]
            return (a, coords[a]), (b, coords[b])
    raise KeyError(f"no route {contractor} {code} in the instance")


def machine_info() -> dict:
    """What the timings were measured on (no host name)."""
    info: dict[str, Any] = {"system": platform.system(), "release": platform.release(),
                            "machine": platform.machine(), "python": platform.python_version(),
                            "cpus": os.cpu_count()}
    try:
        import psutil
        info["memory_gb"] = round(psutil.virtual_memory().total / 2 ** 30, 1)
    except ImportError:
        info["memory_gb"] = None
    return info


# --- the run --------------------------------------------------------------------------------------

def _url(port: int) -> str:
    return f"http://localhost:{port}"


def _pair_rows(pair: Pair, kmh: int) -> str:
    a, b = pair
    return speed_csv([(a, b, kmh), (b, a, kmh)])


def _closed_route(osrm: Any, car_dir: Path, work_dir: Path, leg: Sequence[Point], pair: Pair,
                  kmh: int) -> dict:
    """Customize a fresh copy with `pair` at `kmh`, (re)start the test server, route the leg there."""
    osrm.fresh_copy(car_dir, work_dir)
    osrm.customize(work_dir, _pair_rows(pair, kmh))
    osrm.start_server(work_dir, port=TEST_PORT, name=TEST_NAME)
    return osrm.route(list(leg), base=_url(TEST_PORT), nodes=True)


def _check(question: str, answer: str, evidence: dict) -> dict:
    return {"question": question, "answer": answer, "evidence": evidence}


def _block_checks(osrm, car_dir, work_dir, leg, pair, before) -> tuple[list[dict], int | None]:
    """Check 1 at 0 km/h and, if OSRM ignored it, again at 1 km/h. Leaves the last closure running."""
    nodes0, s0 = route_nodes(before), float(before["duration"])
    checks: list[dict] = []
    for kmh in (0, 1):
        after = _closed_route(osrm, car_dir, work_dir, leg, pair, kmh)
        nodes1, s1 = route_nodes(after), float(after["duration"])
        answer = block_answer(nodes0, s0, nodes1, s1, pair)
        selects = {"blocks": f"scenarios close roads at {kmh} km/h",
                   "ignored": "repeat at 1 km/h" if kmh == 0 else "neither 0 nor 1 km/h blocks; stop",
                   "unclear": "look at the two routes by hand before building scenarios"}[answer]
        checks.append(_check(
            f"Does a segment speed of {kmh} km/h block the road in OSRM?", answer,
            {"pair": list(pair), "kmh": kmh, "duration_before_s": round(s0, 1),
             "duration_after_s": round(s1, 1), "nodes_before": len(nodes0), "nodes_after": len(nodes1),
             "after_uses_pair": uses_pair(nodes1, pair), "selects": selects}))
        if answer == "blocks":
            return checks, kmh
        if answer != "ignored":
            break
    return checks, None


def _snap_check(osrm, graph, leg, pair, closed_kmh: int) -> dict:
    mid = segment_midpoint(graph, pair)
    before = osrm.route([mid, leg[1]], base=_url(UNTOUCHED_PORT))["waypoints"][0]["distance"]
    evidence: dict[str, Any] = {"start": [round(mid[0], 6), round(mid[1], 6)], "closed_kmh": closed_kmh,
                                "moved_before_m": round(float(before), 1)}
    try:
        after = osrm.route([mid, leg[1]], base=_url(TEST_PORT))["waypoints"][0]["distance"]
    except OsrmError as err:
        evidence["error"] = str(err)
        return _check("Is a point on a closed segment moved to another road?", "no route", evidence)
    evidence["moved_after_m"] = round(float(after), 1)
    evidence["selects"] = "confirms the reachability rule (points inside a full block are unreachable)"
    return _check("Is a point on a closed segment moved to another road?",
                  snap_answer(float(before), float(after)), evidence)


def _slowed_check(osrm, car_dir, work_dir, leg, pair, before) -> dict:
    after = _closed_route(osrm, car_dir, work_dir, leg, pair, SLOWED_KMH)
    nodes0, s0 = route_nodes(before), float(before["duration"])
    nodes1, s1 = route_nodes(after), float(after["duration"])
    answer = slowed_answer(nodes0, s0, nodes1, s1)
    return _check(f"Does a segment slowed to {SLOWED_KMH} km/h change routes?", answer,
                  {"pair": list(pair), "kmh": SLOWED_KMH, "duration_before_s": round(s0, 1),
                   "duration_after_s": round(s1, 1),
                   "selects": "University Road case stays in" if answer != "no effect"
                   else "drop the University Road case"})


def _timings(osrm, car_dir, work_dir, pair, kmh: int, repeats: int) -> dict:
    rows = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        osrm.fresh_copy(car_dir, work_dir)
        copy_s = time.perf_counter() - t0
        customize_s, log = osrm.customize_logged(work_dir, _pair_rows(pair, kmh))
        osrm.stop_server(TEST_NAME)                 # so start_s times the start alone
        t1 = time.perf_counter()
        osrm.start_server(work_dir, port=TEST_PORT, name=TEST_NAME)
        start_s = time.perf_counter() - t1
        peak = peak_ram_bytes(log)
        rows.append({"copy_s": round(copy_s, 2), "customize_s": round(customize_s, 2),
                     "start_s": round(start_s, 2),
                     "peak_ram_mb": None if peak is None else round(peak / 2 ** 20, 1)})
    median = {}
    for key in ("copy_s", "customize_s", "start_s", "peak_ram_mb"):
        values = [r[key] for r in rows if r[key] is not None]
        median[key] = round(statistics.median(values), 2) if values else None
    return {"closed_kmh": kmh, "repeats": rows, "median": median}


def run_test(osrm: Any, graph: Any, leg: Sequence[Point], car_dir: Path, work_dir: Path,
             repeats: int = REPEATS) -> dict:
    """Run the four checks on `leg` (two `(lat, lng)` points) and return the result (no `machine`).

    `osrm` is the `osrm_tools` module or a stand-in with the same functions.
    """
    osrm.start_server(car_dir, port=UNTOUCHED_PORT, name=UNTOUCHED_NAME)
    try:
        before = osrm.route(list(leg), base=_url(UNTOUCHED_PORT), nodes=True)
        pair = middle_pair(route_nodes(before))
        checks, block_kmh = _block_checks(osrm, car_dir, work_dir, leg, pair, before)
        # The speed of the last closure `_block_checks` left on the test server (1 when 0 was ignored).
        closed_kmh = checks[-1]["evidence"]["kmh"]
        checks.append(_snap_check(osrm, graph, leg, pair, closed_kmh))
        checks.append(_slowed_check(osrm, car_dir, work_dir, leg, pair, before))
        timings = _timings(osrm, car_dir, work_dir, pair, closed_kmh, repeats)
        m = timings["median"]
        checks.append(_check(
            "How long do customizing and reloading take?",
            f"customize {m['customize_s']} s, server start {m['start_s']} s (median of {repeats})",
            {"copy_s": m["copy_s"], "peak_ram_mb": m["peak_ram_mb"],
             "selects": "scenario build time: about 106 customizations"}))
    finally:
        osrm.stop_server(TEST_NAME)
        osrm.stop_server(UNTOUCHED_NAME)
    return {"osrm_image": osrm_tools.IMAGE,
            "leg": {"from": [round(leg[0][0], 6), round(leg[0][1], 6)],
                    "to": [round(leg[1][0], 6), round(leg[1][1], 6)], "pair": list(pair)},
            "block_kmh": block_kmh, "checks": checks, "timings": timings}


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="The OSRM road-block test (work item A2).")
    p.add_argument("--car-dir", type=Path, default=OSRM_HOME / "car",
                   help="untouched car build (karachi.osrm*); default %(default)s")
    p.add_argument("--work-dir", type=Path, default=OSRM_HOME / "work",
                   help="scratch folder, emptied for every customization; default %(default)s")
    p.add_argument("--graph", type=Path, default=RESEARCH / "data" / "graph_karachi_v1")
    p.add_argument("--instance", type=Path, default=RESEARCH / "data" / "instance_fall2026_v1.json")
    p.add_argument("--out", type=Path, default=RESEARCH / "results" / "roadblock" / "result.json")
    p.add_argument("--repeats", type=int, default=REPEATS, help="timing repeats (default %(default)s)")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None, osrm: Any = osrm_tools, graph: Any = None) -> dict:
    """Run the test and write the result file. `osrm` and `graph` can be replaced in tests."""
    args = parse_args(argv)
    instance = json.loads(args.instance.read_text(encoding="utf-8"))
    (a_name, a), (b_name, b) = first_leg(instance, LEG_CONTRACTOR, LEG_ROUTE)
    if graph is None:
        from reroute.graph import Graph
        graph = Graph.load(args.graph)
    try:
        result = run_test(osrm, graph, (a, b), args.car_dir, args.work_dir, repeats=args.repeats)
    except (FileNotFoundError, RuntimeError) as err:
        sys.exit(f"run_roadblock: {err}")
    result = {"machine": machine_info(), **result}
    result["leg"] = {"route": f"{LEG_CONTRACTOR} {LEG_ROUTE}", "from_stop": a_name, "to_stop": b_name,
                     **result["leg"]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    for c in result["checks"]:
        print(f"{c['question']} -> {c['answer']}")
    print(f"block speed for the scenarios: {result['block_kmh']} km/h; wrote {args.out}")
    return result


if __name__ == "__main__":
    main()
