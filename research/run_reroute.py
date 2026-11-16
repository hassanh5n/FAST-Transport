"""Rerouting experiments: quality pass, limits pass and scaling runs (work plan Sections 8.3 to 8.5).

    python research/run_reroute.py make-toy                      # writes data/scenarios_toy.json
    python research/run_reroute.py quality --quick               # toy file, results/reroute-quality-quick/
    python research/run_reroute.py quality --workers 2           # frozen scenarios, results/reroute-quality/
    python research/run_reroute.py limits --quick --no-limits    # toy file, no systemd: a dry run
    python research/run_reroute.py limits                        # Linux (WSL) with systemd, results/reroute-limits/
    python research/run_reroute.py scale --quick                 # stops at 4 and 8, slices on the toy file
    python research/run_reroute.py scale [--only stops|graph|buses|slices]
    python research/run_reroute.py quality --summarize           # rebuild summary.json from finished runs

quality  Every scenario x walking limits 0, 400 and 800 m x R0, R2 and R3 on true times, no time limit,
         plus two arms at 400 m: the no-closure control (same solve on the unblocked table) and
         must-serve (25% of remaining stops, fixed draw). One job per scenario, five rows.
limits   Every scenario at 400 m inside the free-tier limits (512 MB, no swap, 0.1 CPU; systemd, as in
         run B1). One worker process per route, arm and repeat loads the road graph once and handles
         that route's scenarios in turn. Arms: graph_limited (plan on the graph, 30 s cap, limited),
         graph_unlimited (plan on the graph, no cap, no limits) and truth_limited (plan on true times,
         30 s cap, limited). Every plan is scored on true times against the oracle (R3 on true times).
         Without systemd the pass refuses to run unless --no-limits is given; every row then records
         limits "none", so the numbers say nothing about the free tier.
scale    Curves, no verdicts: stops on one bus (synthetic problems), road-graph rows (corridor and
         city), buses hit by one closure sharing the row cache, and solving in slices.

--quick reads data/scenarios_toy.json only and writes to a "-quick" folder. The quick limits pass runs
only the truth_limited arm (the toy file has no road graph); the quick scaling run measures `stops`
at 4 and 8 stops without limits and `slices` on the toy file.

Each finished run is one JSON line in <dir>/runs.jsonl ("key", "status", "started_at"); finished runs
are skipped on the next start (a "failed" or "skipped" row is retried) and a rerun of a key replaces
the earlier row in summaries. Statuses "ok" and "infeasible" (no plan is possible on true times) are
counted results; every other status is a failure. Thresholds are copied from LOGBOOK.md (2026-11-16) and are not changed
after results exist.

Only the standard library is imported at module level: the hub's page builder imports this file
where numpy, scipy and the reroute package may be missing. Research only: no Django, no database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"
SCENARIOS = DATA / "scenarios_reroute_v1.json"
TOY = DATA / "scenarios_toy.json"
WALK = DATA / "walk_fall2026_v1.json"
GRAPH = DATA / "graph_karachi_v1"
CORRIDORS = DATA / "corridors_fall2026_v1"
INSTANCE = DATA / "instance_fall2026_v1.json"

# Fixed before any result (LOGBOOK 2026-11-16). Do not change after results exist.
GAIN_MIN_S = 60              # median closure-specific gain of R3 over R0 at 400 m, net of the control
NEAR_ORACLE_S = 60           # R2 (quality) or the plan held at 30 s (limits) within this of the oracle
NEAR_ORACLE_SHARE = 0.90     # ... in at least this share of judged scenarios (and on every route's median)
FIRST_PLAN_S = 5             # a valid plan within 5 s ...
FIRST_PLAN_SHARE = 0.95      # ... in at least 95% of judged scenarios
AT_30_SHARE = 0.90           # at 30 s within NEAR_ORACLE_S of the oracle in at least 90%
MEMORY_MB = 400              # peak memory including the graph

LIMITS_M = (0, 400, 800)
JUDGED_LIMIT_M = 400
JUDGED_MIN_REMAINING = 2
JUDGED_MIN_R0_DELAY_S = 60
LIMIT_ARMS = ("graph_limited", "graph_unlimited", "truth_limited")
LIMITED_ARMS = ("graph_limited", "truth_limited")
REPEATS = 3
CAP_S = 30.0                 # the limited arms stop the ladder after 30 s
SLICE_MASKS = 256            # R3 masks per ladder step
CHECKS_S = (1, 5, 30)
RETRY = frozenset({"failed", "skipped"})      # statuses rerun on the next start
RESULT_STATUSES = frozenset({"ok", "infeasible"})  # statuses that are counted results; every other one is a failure
SEF_STRETCH = "shahrah-e-faisal-2024-02-24"
PASSES = {"quality": "reroute-quality", "limits": "reroute-limits", "scale": "reroute-scale"}

SCALE_STOPS = (4, 8, 12, 16, 20)
SCALE_CANDIDATES = (1, 2, 4)
SCALE_SEEDS = (1, 2, 3)
SCALE_POINTS = (10, 30, 60)
SCALE_BUSES = (1, 5, 10, 20)
SCALE_SLICE_SCENARIOS = 3


# ================================================================ small helpers (stdlib only)

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _num(x: Any, digits: int = 1) -> Any:
    """A JSON-safe number: infinity and NaN become ``None``, floats are rounded."""
    if isinstance(x, float):
        return round(x, digits) if math.isfinite(x) else None
    return x


def read_jsonl(path: Path) -> list[dict]:
    """The rows of a JSON-lines file; a line that does not parse (torn by a kill mid-write) is skipped."""
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def read_latest(out_dir: Path) -> dict[str, dict]:
    """The latest row of every key in ``runs.jsonl`` (a rerun replaces the earlier row)."""
    return {row["key"]: row for row in read_jsonl(Path(out_dir) / "runs.jsonl") if "key" in row}


def finished(latest: Mapping[str, dict]) -> set[str]:
    """Keys whose latest row is a result (not a crash or a skip), so they are not run again."""
    return {k for k, r in latest.items() if r.get("status") not in RETRY}


def append_rows(out_dir: Path, rows: Iterable[dict]) -> None:
    with open(Path(out_dir) / "runs.jsonl", "a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, allow_nan=False) + "\n")


def peak_mb() -> float | None:
    """This process's peak resident memory in MB (Linux: ru_maxrss; Windows: peak working set)."""
    try:
        import resource                                   # Linux and macOS only
        kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(kb / 1024 / (1024 if sys.platform == "darwin" else 1), 1)
    except ImportError:
        pass
    try:
        import psutil
        info = psutil.Process().memory_info()
        return round(getattr(info, "peak_wset", info.rss) / 2**20, 1)
    except ImportError:
        return None


def rss_mb() -> float | None:
    """This process's current resident memory in MB, or ``None`` without psutil or /proc."""
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / 2**20, 1)
    except ImportError:
        pass
    try:
        pages = int(Path("/proc/self/statm").read_text().split()[1])
        return round(pages * os.sysconf("SC_PAGE_SIZE") / 2**20, 1)
    except (OSError, ValueError, AttributeError):
        return None


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def machine_info() -> dict:
    info = {"host": platform.node(), "system": platform.system(), "kernel": platform.release(),
            "python": platform.python_version(), "cpus": os.cpu_count()}
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text()
        info["cpu"] = next(l.split(":", 1)[1].strip() for l in cpuinfo.splitlines() if l.startswith("model name"))
        mem_kb = next(int(l.split()[1]) for l in Path("/proc/meminfo").read_text().splitlines()
                      if l.startswith("MemTotal"))
        info["ram_gb"] = round(mem_kb / 1024 / 1024, 1)
    except (OSError, StopIteration):
        info["cpu"] = platform.processor() or None
    for name in ("numpy", "scipy"):
        try:
            info[name] = __import__(name).__version__
        except ImportError:
            info[name] = "missing"
    return info


def code_version(given: str | None) -> str | None:
    """The version the hub passes, else the git commit of research/ (``-dirty`` with edits)."""
    if given not in (None, "", "{code_version}"):
        return given
    import run_budget                                     # stdlib only at import time
    return run_budget.git_version()


def _median(vals: Sequence[float]) -> float | None:
    vals = [v for v in vals if v is not None]
    return _num(float(statistics.median(vals))) if vals else None


def _pct(vals: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile (q in 0..100) of the values that are not ``None``."""
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    return _num(float(vals[min(len(vals) - 1, max(0, math.ceil(q / 100 * len(vals)) - 1))]))


def _max(vals: Iterable[float | None]) -> float | None:
    vals = [v for v in vals if v is not None]
    return _num(float(max(vals))) if vals else None


def _share(flags: Sequence[bool]) -> float | None:
    return round(sum(flags) / len(flags), 3) if flags else None


def _verdict(ok: bool | None) -> str | None:
    return None if ok is None else ("pass" if ok else "fail")


# ================================================================ the scenario file

def walk_from_pairs(pairs: Iterable[Sequence]) -> dict[tuple[int, int], float]:
    """Directed walking metres from ``[from_id, to_id, metres]`` triples."""
    return {(int(a), int(b)): float(m) for a, b, m in pairs}


def load_cases(path: Path, walk_path: Path | None = None) -> dict:
    """The scenario file with tables as floats (``null`` = infinity), closures by id and the walk.

    The toy file carries its walking pairs under ``"walk"``; the frozen file names a walk version
    and the pairs are read from ``walk_path``.
    """
    from build_scenarios import load_scenarios
    data = load_scenarios(path)
    if isinstance(data.get("walk"), list):
        walk = walk_from_pairs(data["walk"])
    else:
        from build_walk import load_walk
        walk = load_walk(walk_path or WALK)
    return {"data": data, "closures": {c["id"]: c for c in data["closures"]},
            "scenarios": sorted(data["scenarios"], key=lambda s: s["id"]), "walk": walk}


def route_key(closure: Mapping) -> str:
    """The route a closure belongs to, as corridor files name it: ``<contractor>-<route code>``."""
    return f"{closure['contractor']}-{closure['route']}"


def _scenario_head(scenario: Mapping, closure: Mapping) -> dict:
    return {"scenario": scenario["id"], "route": route_key(closure), "contractor": closure["contractor"],
            "kind": closure["kind"], "trigger": scenario["trigger"]}


# ================================================================ make-toy

def toy_content() -> dict:
    """Three hand-checkable scenarios (experiment-runner plan, Task 1 and 3).

    ``T-L1-late`` is the plan's toy; ``T-L2-late`` has the same tables on other ids with no walking
    pair, so no stop can walk; ``T-L3-late`` closes stop 22 (its ``post`` row and column infinite).
    Before the closure the published order arrives at 950 s; after it at 1,350 s; letting the second
    stop walk 240 m to the first arrives at 940 s.
    """
    from osrm_tools import to_json_table
    inf = math.inf
    pre = [[0, 100, 300, 650], [100, 0, 200, 590], [300, 200, 0, 500], [inf, inf, inf, 0]]
    post = [[0, 100, 300, 650], [100, 0, 400, 590], [300, 400, 0, 700], [inf, inf, inf, 0]]
    closed_post = [[0, 100, inf, 650], [100, 0, inf, 590], [inf, inf, 0, inf], [inf, inf, inf, 0]]

    def closure(cid: str, leg: int, base: int, post_table, closed: list[int]) -> dict:
        return {"id": cid, "kind": "synthetic", "contractor": "T", "route": "T", "leg": leg, "factor": 0.0,
                "circles": [[24.9, 67.0, 200.0]], "points": [base, base + 1, base + 2], "closed_points": closed,
                "pre": to_json_table(pre), "post": to_json_table(post_table), "segments": 0, "leaks": 0,
                "customize_s": 0.0}

    def scenario(cid: str, base: int, closed: bool) -> dict:
        return {"id": f"{cid}-late", "closure": cid, "trigger": "late", "position": base,
                "remaining": [base + 1, base + 2], "students": {str(base + 1): 4, str(base + 2): 2},
                "candidates": [], "tags": {"remaining": 2, "closure_contains_stop": closed}}

    return {"version": "reroute-toy", "instance": None, "graph": None, "built_at": None,
            "note": "Hand-made toy scenarios for --quick runs; written by run_reroute.py make-toy.",
            "closures": [closure("T-L1", 1, 0, post, []), closure("T-L2", 2, 10, post, []),
                         closure("T-L3", 3, 20, closed_post, [22])],
            "scenarios": [scenario("T-L1", 0, False), scenario("T-L2", 10, False), scenario("T-L3", 20, True)],
            "walk": [[2, 1, 240.0], [22, 21, 240.0]]}


def make_toy(path: Path = TOY) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(toy_content(), indent=1), encoding="utf-8")
    return path


# ================================================================ quality pass

def _solve_all(problem) -> dict:
    """R0, R2 and the ladder's best (R3 when the problem is small enough), each solved in full."""
    from reroute import Ladder, solve_r0, solve_r2
    ladder = Ladder(problem)
    best = ladder.run()
    return {"R0": solve_r0(problem), "R2": solve_r2(problem), "R3": best,
            "r3_ran": ladder.bound is None, "bound": ladder.bound}


def _feasible(plan, n_stops: int) -> bool:
    return math.isfinite(plan.arrival_s) and not (n_stops and len(plan.unserved) == n_stops)


def truth_feasible(scenario: dict, closure: dict, walk: Mapping, limit_m: float = JUDGED_LIMIT_M) -> bool:
    """Whether the scenario can be planned at all on true times (Review Focus 1).

    False when the published route has no finite arrival, or when the patched route on the ``post``
    table never reaches campus or serves no stop. R0 serves every stop that has a reachable boarding
    point, so this is the quality pass's rule for ``infeasible`` applied to the true table.
    """
    from reroute import solve_r0
    from reroute_cases import baseline_arrival, build_problem
    if not math.isfinite(baseline_arrival(scenario, closure, walk)):
        return False
    problem = build_problem(scenario, closure, walk, limit_m)
    return _feasible(solve_r0(problem), len(problem.stops))


def quality_rows(scenario: dict, closure: dict, walk: Mapping) -> list[dict]:
    """The five rows of one scenario: ``main`` at 0, 400 and 800 m, ``control`` and ``must_serve`` at 400 m.

    A row whose plans never reach campus or serve no stop at all is ``infeasible``; a plan the
    scoring table makes invalid gives ``invalid_on_truth``. ``judged`` comes from the main row at
    400 m and is copied to the others.
    """
    from reroute_cases import baseline_arrival, build_problem, must_serve_draw, score_on_truth
    head = _scenario_head(scenario, closure)
    tags = scenario.get("tags", {})
    baseline = baseline_arrival(scenario, closure, walk)
    drawn = must_serve_draw(scenario)
    settings = [(lim, "main") for lim in LIMITS_M] + [(JUDGED_LIMIT_M, "control"), (JUDGED_LIMIT_M, "must_serve")]
    rows = []
    for limit, arm in settings:
        which = "pre" if arm == "control" else "post"
        must = drawn if arm == "must_serve" else ()
        problem = build_problem(scenario, closure, walk, limit, which=which, must_serve=must)
        plans = _solve_all(problem)
        row = {"key": f"{scenario['id']}-L{limit}-{arm}", "setup": f"{arm} {limit} m", "status": "ok", **head,
               "limit_m": limit, "arm": arm, "remaining": len(scenario["remaining"]),
               "must_serve": list(must), "closure_contains_stop": bool(tags.get("closure_contains_stop")),
               "r3_ran": plans["r3_ran"]}
        n = len(problem.stops)
        if not math.isfinite(baseline) or not all(_feasible(plans[m], n) for m in ("R0", "R3")):
            row.update(status="infeasible", unserved=len(plans["R3"].unserved))
            rows.append(row)
            continue
        scores = {m: score_on_truth(scenario, closure, walk, limit, plans[m], must, which) for m in ("R0", "R2", "R3")}
        bad = [m for m, s in scores.items() if s["status"] != "ok"]
        if bad:
            row.update(status="invalid_on_truth", invalid_methods=bad,
                       error=scores[bad[0]].get("error"), unserved=len(plans["R3"].unserved))
            rows.append(row)
            continue
        r0, r2, r3 = scores["R0"], scores["R2"], scores["R3"]
        p0, p3 = plans["R0"], plans["R3"]
        row.update({
            "r0_delay_s": _num(r0["delay_s"]), "r2_delay_s": _num(r2["delay_s"]), "r3_delay_s": _num(r3["delay_s"]),
            "r3_gain_s": _num(r0["arrival_s"] - r3["arrival_s"]),
            "r3_walkers": r3["walkers"], "r3_walk_m_per_walker": _num(r3["walk_m_per_walker"]),
            "r2_minus_r3_s": _num(r2["delay_s"] - r3["delay_s"]),
            "unserved": r3["unserved"], "unserved_avoidable": max(s["unserved_avoidable"] for s in scores.values()),
            "r3_differs_from_r0": (p3.visit, p3.board_at) != (p0.visit, p0.board_at),
            "r0_walkers": r0["walkers"], "r2_walkers": r2["walkers"],
            "r0_walk_m_per_walker": _num(r0["walk_m_per_walker"]),
            "r2_walk_m_per_walker": _num(r2["walk_m_per_walker"]),
            "r3_method": p3.method, "baseline_arrival_s": _num(baseline)})
        if not plans["r3_ran"]:
            bound = plans["bound"]
            row["lower_bound_s"] = _num(bound - baseline) if bound is not None else None
            row["r2_gap_to_bound_s"] = _num(r2["arrival_s"] - bound) if bound is not None else None
        rows.append(row)
    main = next(r for r in rows if r["arm"] == "main" and r["limit_m"] == JUDGED_LIMIT_M)
    judged = (main["status"] == "ok" and main["remaining"] >= JUDGED_MIN_REMAINING
              and main["r0_delay_s"] is not None and main["r0_delay_s"] >= JUDGED_MIN_R0_DELAY_S)
    for r in rows:
        r["judged"] = judged
    return rows


def _quality_job(scenario: dict, closure: dict, walk: dict) -> list[dict]:
    """One scenario's rows; a crash gives five ``failed`` rows. Top level, so a process pool can run it."""
    started = now()
    try:
        rows = quality_rows(scenario, closure, walk)
    except Exception as exc:                              # keep going; the rows record the failure
        settings = [(lim, "main") for lim in LIMITS_M] + [(JUDGED_LIMIT_M, "control"), (JUDGED_LIMIT_M, "must_serve")]
        rows = [{"key": f"{scenario['id']}-L{lim}-{arm}", "setup": f"{arm} {lim} m", "status": "failed",
                 **_scenario_head(scenario, closure), "limit_m": lim, "arm": arm,
                 "error": repr(exc)[:300]} for lim, arm in settings]
    for r in rows:
        r["started_at"] = started
    return rows


def quality_keys(scenario: Mapping) -> list[str]:
    return ([f"{scenario['id']}-L{lim}-main" for lim in LIMITS_M]
            + [f"{scenario['id']}-L{JUDGED_LIMIT_M}-control", f"{scenario['id']}-L{JUDGED_LIMIT_M}-must_serve"])


def case_walk(scenario: Mapping, walk: Mapping) -> dict:
    """Only the walking pairs this scenario can use (keeps what is sent to worker processes small)."""
    points = list(scenario["remaining"]) + list(scenario["candidates"])
    return {(s, p): walk[(s, p)] for s in scenario["remaining"] for p in points if (s, p) in walk}


# ================================================================ limits pass

def oracle_info(scenario: dict, closure: dict, walk: Mapping) -> dict:
    """The oracle (the ladder to the end on true times at 400 m), R0's delay and whether the scenario is judged."""
    from reroute import Ladder, solve_r0
    from reroute_cases import build_problem, score_on_truth
    problem = build_problem(scenario, closure, walk, JUDGED_LIMIT_M)
    oracle = score_on_truth(scenario, closure, walk, JUDGED_LIMIT_M, Ladder(problem).run())
    r0 = score_on_truth(scenario, closure, walk, JUDGED_LIMIT_M, solve_r0(problem))
    r0_delay = r0["delay_s"] if r0["status"] == "ok" else None
    return {"oracle_delay_s": oracle["delay_s"] if oracle["status"] == "ok" else None, "r0_delay_s": r0_delay,
            "judged": (len(scenario["remaining"]) >= JUDGED_MIN_REMAINING and r0_delay is not None
                       and r0_delay >= JUDGED_MIN_R0_DELAY_S and truth_feasible(scenario, closure, walk))}


def safe_oracle_info(scenario: dict, closure: dict, walk: Mapping) -> dict:
    """:func:`oracle_info`, or an unjudged record carrying the error when the scenario cannot be solved."""
    try:
        return oracle_info(scenario, closure, walk)
    except Exception as exc:                              # one malformed scenario must not stop the pass
        return {"oracle_delay_s": None, "r0_delay_s": None, "judged": False, "error": repr(exc)[:300]}


def route_corridor(corridor_dir: Path | None, key: str, graph_version: str | None):
    """The route's saved corridor and its label, or ``(None, "city")`` when it has no corridor file."""
    from reroute.graph import load_corridor
    corridor = load_corridor(corridor_dir, key, graph_version) if corridor_dir is not None else None
    return (corridor, key) if corridor is not None else (None, "city")


class GraphSource:
    """Plans on the road graph: points snapped once, then one ``TravelTimes`` per scenario's closure.

    ``coords`` maps point ids to ``(lat, lng)``; ``area`` is the corridor label recorded in rows
    (``"city"`` when the route has no corridor file and the whole graph is searched).
    """

    def __init__(self, graph, corridor, area: str, coords: Mapping[int, tuple[float, float]],
                 campus: tuple[float, float], reuse=None) -> None:
        self.graph, self.corridor, self.area, self.reuse = graph, corridor, area, reuse
        self.coords = {int(k): (float(v[0]), float(v[1])) for k, v in coords.items()}
        self.campus = (float(campus[0]), float(campus[1]))
        self.node: dict[int, int] = {}
        self.campus_node = graph.nearest_node(*self.campus)[0]

    @classmethod
    def load(cls, graph, corridor_dir: Path | None, route: str, instance_path: Path) -> GraphSource:
        instance = json.loads(Path(instance_path).read_text(encoding="utf-8"))
        coords = {i: (s["lat"], s["lng"]) for i, s in enumerate(instance["stops"])}
        campus = (instance["campus"]["lat"], instance["campus"]["lng"])
        corridor, area = route_corridor(corridor_dir, route, graph.version)
        reuse = None
        if corridor is not None:
            from reroute.graph import load_reuse
            reuse = load_reuse(corridor_dir, route)
        return cls(graph, corridor, area, coords, campus, reuse)

    def snap(self, point_ids: Iterable[int]) -> None:
        """Snap points to their nearest graph node, once, before any closure (work plan Section 5)."""
        for pid in point_ids:
            if int(pid) not in self.node:
                self.node[int(pid)] = self.graph.nearest_node(*self.coords[int(pid)])[0]

    def problem(self, scenario: dict, closure: dict, walk: Mapping, limit_m: float):
        """The scenario's problem with rows from the graph under its closure, and the ``TravelTimes``."""
        from reroute.closure import Closure, closed_points
        from reroute.graph import TravelTimes, problem_rows
        from reroute_cases import build_problem, case_points
        cl = Closure(closure["id"], tuple(tuple(float(x) for x in c) for c in closure["circles"]),
                     float(closure["factor"]))
        pts = case_points(scenario)
        self.snap(pts + [scenario["position"]])
        closed = [bool(c) for c in closed_points([self.coords[p][0] for p in pts],
                                                 [self.coords[p][1] for p in pts], [cl])]
        tt = TravelTimes(self.graph, self.corridor, [cl], reuse=self.reuse)
        nodes = [self.node[p] for p in pts]
        start = self.node[int(scenario["position"])]
        open_targets = [n for n, c in zip(nodes, closed) if not c] + [self.campus_node]
        tt.ensure([start], open_targets)              # widens to the city if the corridor cannot reach them
        rows = problem_rows(tt, nodes, start, self.campus_node, closed)
        return build_problem(scenario, closure, walk, limit_m, rows=rows), tt


def solve_case(scenario: dict, closure: dict, walk: Mapping, arm: str, source: GraphSource | None,
               cap_s: float | None) -> dict:
    """Plan one scenario as the limits pass does and score what was held at 1, 5 and 30 s on truth.

    The clock starts before the problem is built, so applying the closure to the graph is inside the
    measured time. The ladder steps by ``SLICE_MASKS`` R3 masks until done or ``cap_s`` (``None``:
    no cap). ``source`` is ``None`` for the truth arm.

    Status: ``infeasible`` when no plan is possible on true times (:func:`truth_feasible`);
    ``invalid_on_truth`` when the final plan breaks a rule on true times, never reaches campus, or
    leaves unserved a stop that truth can serve (work plan Section 5: an unserved stop is a failure);
    ``ok`` otherwise. A held plan that leaves such a stop unserved gets no delay at its checkpoint, so
    abandoning students never shows as a gain over the oracle.
    """
    from reroute import Ladder
    from reroute_cases import build_problem, checkpoints, score_on_truth
    t0 = time.perf_counter()
    tt = None
    if source is None:
        problem = build_problem(scenario, closure, walk, JUDGED_LIMIT_M)
    else:
        problem, tt = source.problem(scenario, closure, walk, JUDGED_LIMIT_M)
    ladder = Ladder(problem)
    deadline = None if cap_s is None else t0 + cap_s
    timeline = []
    while not ladder.done:
        if deadline is not None and timeline and time.perf_counter() >= deadline:
            break
        plan = ladder.step(max_masks=SLICE_MASKS, deadline=deadline)
        timeline.append((time.perf_counter() - t0, plan))
    elapsed = time.perf_counter() - t0
    row = {**_scenario_head(scenario, closure), "status": "ok", "arm": arm,
           "corridor": None if source is None else source.area,
           "widened": None if tt is None else tt.widened,
           "t_done_s": _num(elapsed, 3) if ladder.done else None,
           "rows_requested": problem.rows_requested,
           "searches": None if tt is None else tt.searches, "cache_hits": None if tt is None else tt.hits,
           "rows_reused": None if tt is None else tt.reused, "r3_ran": ladder.bound is None}
    first = next((t for t, p in timeline if p is not None and math.isfinite(p.arrival_s)), None)
    row["t_first_s"] = _num(first, 3)
    final = timeline[-1][1] if timeline else None
    row["final_method"] = None if final is None else final.method
    for t in CHECKS_S:
        row[f"method_{t}s"] = row[f"delay_{t}s"] = None
    row["final_delay_s"] = row["planned_minus_true_s"] = None
    row["peak_mb"] = peak_mb()
    if not truth_feasible(scenario, closure, walk):
        row["status"] = "infeasible"
        return row

    def scored(plan) -> dict | None:
        """The plan's score on truth, or ``None`` when it is invalid there or abandons a servable stop."""
        if plan is None:
            return None
        s = score_on_truth(scenario, closure, walk, JUDGED_LIMIT_M, plan)
        return s if s["status"] == "ok" and not s["unserved_avoidable"] else None

    held = checkpoints(timeline, CHECKS_S)
    for t in CHECKS_S:
        plan, score = held[t], scored(held[t])
        row[f"method_{t}s"] = None if plan is None else plan.method
        row[f"delay_{t}s"] = _num(score["delay_s"]) if score else None
    score = None if final is None else score_on_truth(scenario, closure, walk, JUDGED_LIMIT_M, final)
    if first is None or score is None:
        row.update(status="invalid_on_truth", error="no plan reached campus on the planning table")
    elif score["status"] != "ok":
        row.update(status=score["status"], error=score.get("error"))
    elif score["unserved_avoidable"]:
        row.update(status="invalid_on_truth", unserved_avoidable=score["unserved_avoidable"],
                   error=f"leaves {score['unserved_avoidable']} stop(s) unserved that truth can serve")
    else:
        row["final_delay_s"] = _num(score["delay_s"])
        row["planned_minus_true_s"] = _num(final.arrival_s - score["arrival_s"])
    return row


def fill_gaps(row: dict, oracle: Mapping) -> dict:
    """Add the oracle's delay, ``judged`` and every gap (a delay on truth minus the oracle's)."""
    o = oracle.get("oracle_delay_s")
    out = dict(row, oracle_delay_s=_num(o), judged=bool(oracle.get("judged")))
    if oracle.get("error") and out.get("status") == "ok":
        out.update(status="failed", error=f"oracle: {oracle['error']}")
    for t in CHECKS_S:
        d = row.get(f"delay_{t}s")
        out[f"gap_{t}s"] = _num(d - o) if d is not None and o is not None else None
    d = row.get("final_delay_s")
    out["final_gap_s"] = _num(d - o) if d is not None and o is not None else None
    return out


def limit_jobs(cases: Mapping, arms: Sequence[str] = LIMIT_ARMS, repeats: int = REPEATS) -> list[dict]:
    """One worker job per route, arm and repeat (repeat-major); graph_unlimited runs once (no timing)."""
    by_route: dict[str, list[str]] = {}
    for s in cases["scenarios"]:
        by_route.setdefault(route_key(cases["closures"][s["closure"]]), []).append(s["id"])
    jobs = []
    for rep in range(1, repeats + 1):
        for arm in arms:
            if arm == "graph_unlimited" and rep > 1:
                continue
            for route, ids in by_route.items():
                jobs.append({"route": route, "arm": arm, "repeat": rep, "scenarios": sorted(ids),
                             "keys": [f"{sid}-{arm}-r{rep}" for sid in sorted(ids)]})
    return jobs


def worker_outcome(job: Mapping, returncode: int, log_text: str, rows: Sequence[dict], limited: bool) -> list[dict]:
    """One row per scenario of the job: the worker's own rows, and for scenarios it did not finish
    ``killed_memory`` (killed under the limits, or ``MemoryError``) or ``failed``.

    Rows the worker finished before it was killed are kept: they are complete measurements.
    """
    got = {r["scenario"]: r for r in rows}
    killed = returncode != 0 and ("MemoryError" in log_text or (limited and returncode in (-9, 137)))
    status = "killed_memory" if killed else "failed"
    out = []
    for sid in job["scenarios"]:
        if sid in got:
            out.append(got[sid])
        else:
            out.append({"scenario": sid, "status": status, "returncode": returncode,
                        "error": log_text.strip()[-300:] or None})
    return out


def _worker_main(args: argparse.Namespace) -> None:
    """Internal: one route, arm and repeat. Loads the graph once, then each scenario in turn."""
    cases = load_cases(args.scenarios, args.walk)
    mine = [s for s in cases["scenarios"] if route_key(cases["closures"][s["closure"]]) == args.route]
    source = None
    if args.arm != "truth_limited":
        if args.toy:
            sys.exit("the toy file has no road graph: only the truth_limited arm can run on it")
        from reroute.graph import Graph
        graph = Graph.load(args.graph)
        source = GraphSource.load(graph, args.corridors, args.route, args.instance)
        for s in mine:
            source.snap(list(s["remaining"]) + list(s["candidates"]) + [s["position"]])
    cap = None if args.arm == "graph_unlimited" else CAP_S
    with open(args.out, "a", encoding="utf-8") as fh:
        for s in mine:
            row = solve_case(s, cases["closures"][s["closure"]], cases["walk"], args.arm, source, cap)
            fh.write(json.dumps(row, allow_nan=False) + "\n")
            fh.flush()
    print(f"peak_mb {peak_mb()}")


# ================================================================ scaling runs

def synthetic_problem(n_stops: int, per_stop: int, seed: int, limit_m: float = 400.0):
    """Stops uniform in a 2 km square, ``per_stop`` extra boarding points within 600 m of each stop,
    straight-line driving at 10 m/s, walking = straight-line metres up to 800 m (as in the solver tests)."""
    from reroute import Problem, StopNeed, table_rows
    rng = random.Random(f"reroute-scale-{n_stops}-{per_stop}-{seed}")
    stops_xy = [(rng.uniform(0, 2000), rng.uniform(0, 2000)) for _ in range(n_stops)]
    extra_xy = []
    for x, y in stops_xy:
        for _ in range(per_stop):
            r, a = rng.uniform(100, 600), rng.uniform(0, 2 * math.pi)
            extra_xy.append((x + r * math.cos(a), y + r * math.sin(a)))
    xy = stops_xy + extra_xy + [(rng.uniform(0, 2000), rng.uniform(0, 2000)), (rng.uniform(4000, 6000), 1000.0)]
    matrix = [[math.dist(a, b) / 10.0 for b in xy] for a in xy]
    n_points = len(stops_xy) + len(extra_xy)
    walk = {(s + 1, p + 1): math.dist(xy[s], xy[p]) for s in range(n_stops) for p in range(n_points)
            if s != p and math.dist(xy[s], xy[p]) <= 800.0}
    stops = [StopNeed(i + 1, rng.randint(1, 9), walk_limit_m=limit_m) for i in range(n_stops)]
    return Problem(stops, list(range(1, n_points + 1)), table_rows(matrix), walk)


def measure_stops(n_stops: int, per_stop: int, seed: int, cap_s: float | None) -> dict:
    """CPU-seconds and peak memory of R2 and of R3 on one synthetic problem (R3 skipped above 16 stops)."""
    from reroute import solve_r2
    from reroute.ladder import MAX_EXACT_BITS, lower_bound, r3_advance, r3_plan, r3_start, servable
    problem = synthetic_problem(n_stops, per_stop, seed)
    base = peak_mb()
    c0, w0 = time.process_time(), time.perf_counter()
    r2 = solve_r2(problem)
    out = {"points": len(problem.points), "r2_cpu_s": _num(time.process_time() - c0, 3),
           "r2_wall_s": _num(time.perf_counter() - w0, 3), "r2_peak_mb": peak_mb(), "base_mb": base,
           "r2_arrival_s": _num(r2.arrival_s)}
    bits = len(servable(problem)[0]) + len(problem.committed)
    if bits > MAX_EXACT_BITS:
        bound = lower_bound(problem)
        out.update(r3_ran=False, r3_done=False, lower_bound_s=_num(bound),
                   r2_gap_to_bound_s=_num(r2.arrival_s - bound))
        return out
    c0, w0 = time.process_time(), time.perf_counter()
    state = r3_start(problem)
    r3_advance(problem, state, deadline=None if cap_s is None else w0 + cap_s)
    out.update(r3_ran=True, r3_done=state.done, r3_cpu_s=_num(time.process_time() - c0, 3),
               r3_wall_s=_num(time.perf_counter() - w0, 3), r3_peak_mb=peak_mb())
    if state.done:
        r3 = r3_plan(problem, state, fallback=r2)
        out.update(r3_arrival_s=_num(r3.arrival_s), r2_minus_r3_s=_num(r2.arrival_s - r3.arrival_s))
    return out


def _longest_route(instance: Mapping) -> tuple[str, list[int]]:
    """The current route with the most stops: its key and its stop ids in order."""
    ids = {s["name"]: i for i, s in enumerate(instance["stops"])}
    best = max(((f"{c}-{r['code']}", [ids[n] for n in r["stops"]])
                for c, d in instance["contractors"].items() for r in d["baseline_routes"]),
               key=lambda kv: len(kv[1]))
    return best


def graph_points(instance: Mapping, route_stops: Sequence[int], count: int) -> list[int]:
    """``count`` stop ids: the route's stops first, then the other stops nearest to any of them."""
    from scenario_rules import haversine_m
    stops = instance["stops"]
    chosen = list(dict.fromkeys(route_stops))[:count]
    if len(chosen) < count:
        rest = [i for i in range(len(stops)) if i not in set(chosen)]
        rest.sort(key=lambda i: min(haversine_m(stops[i]["lat"], stops[i]["lng"], stops[j]["lat"], stops[j]["lng"])
                                    for j in route_stops))
        chosen += rest[:count - len(chosen)]
    return chosen


def measure_graph(area: str, count: int, graph_dir: Path, corridor_dir: Path, instance_path: Path) -> dict:
    """Rows for ``count`` points on the longest route's corridor (or the city), with the arrays memory-mapped."""
    from reroute.graph import Graph, TravelTimes, clear_row_cache, load_corridor
    instance = json.loads(Path(instance_path).read_text(encoding="utf-8"))
    key, route = _longest_route(instance)
    graph = Graph.load(graph_dir, mmap=True)
    corridor = load_corridor(corridor_dir, key, graph.version) if area == "corridor" else None
    if area == "corridor" and corridor is None:
        return {"status": "skipped", "error": f"no corridor file for {key}", "route": key}
    pts = graph_points(instance, route, count)
    nodes = [graph.nearest_node(instance["stops"][i]["lat"], instance["stops"][i]["lng"])[0] for i in pts]
    clear_row_cache()
    base = rss_mb()
    tt = TravelTimes(graph, corridor)
    c0, w0 = time.process_time(), time.perf_counter()
    tt.rows(nodes)
    cpu = time.process_time() - c0
    return {"route": key, "points": len(pts), "searches": tt.searches, "cpu_s": _num(cpu, 3),
            "cpu_per_row_s": _num(cpu / max(1, tt.searches), 4), "wall_s": _num(time.perf_counter() - w0, 3),
            "rss_before_mb": base, "rss_mb": rss_mb(), "peak_mb": peak_mb(),
            "graph_nodes": graph.n_nodes, "area_nodes": None if corridor is None else int(len(corridor.nodes))}


def measure_buses(n_buses: int, cases: Mapping, graph_dir: Path, instance_path: Path) -> dict:
    """Shahrah-e-Faisal hits ``n_buses`` buses at once; one process plans for all of them on the
    whole graph, sharing the row cache, stepping each bus's ladder in turn."""
    from reroute import Ladder
    from reroute.graph import Graph, clear_row_cache
    sef = sorted((s for s in cases["scenarios"] if cases["closures"][s["closure"]].get("stretch") == SEF_STRETCH),
                 key=lambda s: s["id"])
    if not sef:
        return {"status": "skipped", "error": f"no scenario of {SEF_STRETCH} in the scenario file"}
    picked = [sef[i % len(sef)] for i in range(n_buses)]
    graph = Graph.load(graph_dir, mmap=True)
    source = GraphSource.load(graph, None, "city", instance_path)
    for s in picked:
        source.snap(list(s["remaining"]) + list(s["candidates"]) + [s["position"]])
    clear_row_cache()
    t0 = time.perf_counter()
    ladders, tts = [], []
    for s in picked:
        problem, tt = source.problem(s, cases["closures"][s["closure"]], cases["walk"], JUDGED_LIMIT_M)
        ladders.append(Ladder(problem))
        tts.append(tt)
    t_valid = None
    while not all(lad.done for lad in ladders):
        for lad in ladders:
            if not lad.done:
                lad.step(max_masks=SLICE_MASKS)
        if t_valid is None and all(lad.best is not None and math.isfinite(lad.best.arrival_s) for lad in ladders):
            t_valid = time.perf_counter() - t0
    searches, hits = sum(t.searches for t in tts), sum(t.hits for t in tts)
    return {"buses": n_buses, "distinct_scenarios": len({s["id"] for s in picked}),
            "repeated": len(sef) < n_buses, "t_all_valid_s": _num(t_valid, 3),
            "t_all_final_s": _num(time.perf_counter() - t0, 3), "searches": searches, "cache_hits": hits,
            "cache_hit_share": round(hits / (hits + searches), 3) if hits + searches else None,
            "peak_mb": peak_mb()}


def measure_slices(scenario: dict, closure: dict, walk: Mapping) -> dict:
    """The ladder stepped by ``SLICE_MASKS`` masks: the plan after each slice and the saved state's size."""
    from reroute import Ladder
    from reroute_cases import build_problem, score_on_truth
    problem = build_problem(scenario, closure, walk, JUDGED_LIMIT_M)
    ladder = Ladder(problem)
    slices = []
    c0 = time.process_time()
    while not ladder.done:
        stage = ladder.stage
        plan = ladder.step(max_masks=SLICE_MASKS)
        score = score_on_truth(scenario, closure, walk, JUDGED_LIMIT_M, plan)
        slices.append({"stage": stage, "method": plan.method, "delay_s": _num(score["delay_s"]),
                       "cpu_s": _num(time.process_time() - c0, 3),
                       "state_bytes": len(json.dumps(ladder.to_json(), allow_nan=False))})
    return {"points": len(problem.points), "remaining": len(problem.stops), "n_slices": len(slices),
            "max_state_bytes": max(s["state_bytes"] for s in slices),
            "final_delay_s": slices[-1]["delay_s"], "slices": slices}


def scale_jobs(quick: bool, only: str | None, cases: Mapping | None, limits_ok: bool) -> list[dict]:
    """Every measurement of the scaling runs; ``limits_ok`` adds the limited setups."""
    setups = ["unlimited"] + (["limited"] if limits_ok else [])
    jobs: list[dict] = []
    if only in (None, "stops"):
        sizes, per, seeds = ((4, 8), (1,), (1,)) if quick else (SCALE_STOPS, SCALE_CANDIDATES, SCALE_SEEDS)
        for setup in (["unlimited"] if quick else setups):
            for n in sizes:
                for c in per:
                    for seed in seeds:
                        jobs.append({"part": "stops", "setup": setup, "n_stops": n, "per_stop": c, "seed": seed,
                                     "key": f"stops-n{n}-c{c}-s{seed}-{setup}"})
    if not quick and only in (None, "graph"):
        for setup in setups:
            for area in ("corridor", "city"):
                for p in SCALE_POINTS:
                    jobs.append({"part": "graph", "setup": setup, "area": area, "count": p,
                                 "key": f"graph-{area}-p{p}-{setup}"})
    if not quick and only in (None, "buses"):
        for b in SCALE_BUSES:
            jobs.append({"part": "buses", "setup": "limited" if limits_ok else "unlimited", "buses": b,
                         "key": f"buses-b{b}"})
    if only in (None, "slices") and cases is not None:
        info = {s["id"]: safe_oracle_info(s, cases["closures"][s["closure"]], cases["walk"])
                for s in cases["scenarios"]}
        judged = [s for s in cases["scenarios"] if info[s["id"]]["judged"]]
        judged.sort(key=lambda s: (-(len(s["remaining"]) + len(s["candidates"])), s["id"]))
        for s in judged[:SCALE_SLICE_SCENARIOS]:
            jobs.append({"part": "slices", "setup": "unlimited", "scenario": s["id"], "key": f"slices-{s['id']}"})
    return jobs


def _scale_job_main(args: argparse.Namespace) -> None:
    """Internal: one scaling measurement in a fresh process (so its peak memory is its own)."""
    job = json.loads(args.job)
    cap = CAP_S if job["setup"] == "limited" else None
    if job["part"] == "stops":
        res = measure_stops(job["n_stops"], job["per_stop"], job["seed"], cap)
    elif job["part"] == "graph":
        res = measure_graph(job["area"], job["count"], args.graph, args.corridors, args.instance)
    else:
        cases = load_cases(args.scenarios, args.walk)
        if job["part"] == "buses":
            res = measure_buses(job["buses"], cases, args.graph, args.instance)
        else:
            s = next(x for x in cases["scenarios"] if x["id"] == job["scenario"])
            res = measure_slices(s, cases["closures"][s["closure"]], cases["walk"])
    Path(args.out).write_text(json.dumps(res, allow_nan=False), encoding="utf-8")


# ================================================================ verdicts and summaries

def _judged_synthetic(rows: Iterable[dict]) -> list[dict]:
    return [r for r in rows if r.get("judged") and r.get("kind") == "synthetic"]


def quality_verdict(rows: Sequence[dict]) -> dict:
    """Thresholds 1 to 3 of the logbook (2026-11-16), on judged synthetic scenarios; ``None`` when none."""
    js = _judged_synthetic(rows)

    def at_400(arm: str) -> dict[str, dict]:
        return {r["scenario"]: r for r in js
                if r["arm"] == arm and r["limit_m"] == JUDGED_LIMIT_M and r["status"] == "ok"}
    main, control = at_400("main"), at_400("control")
    nets = [main[s]["r3_gain_s"] - control[s]["r3_gain_s"] for s in main
            if s in control and main[s].get("r3_gain_s") is not None and control[s].get("r3_gain_s") is not None]
    gain = None if not nets else statistics.median(nets) >= GAIN_MIN_S

    close = [r for r in main.values() if r.get("r2_minus_r3_s") is not None]
    near = None
    if close:
        share = sum(r["r2_minus_r3_s"] <= NEAR_ORACLE_S for r in close) / len(close)
        routes: dict[str, list[float]] = {}
        for r in close:
            routes.setdefault(r["route"], []).append(r["r2_minus_r3_s"])
        near = share >= NEAR_ORACLE_SHARE and all(statistics.median(v) <= NEAR_ORACLE_S for v in routes.values())

    # A failed, crashed or invalid row never reaches the judged set (it has no ``judged`` key, or its
    # main row is not ok), so failures are looked for over every synthetic row.
    failures = any(r.get("status") not in RESULT_STATUSES for r in rows if r.get("kind") == "synthetic")
    viol = None
    if js or failures:
        viol = (not failures and all(r["status"] == "ok" for r in js)
                and not any(r.get("unserved_avoidable") for r in js)
                and not any(r["arm"] == "main" and r.get("r3_delay_s") is not None
                            and r.get("r0_delay_s") is not None and r["r3_delay_s"] > r["r0_delay_s"] + 1e-6
                            for r in js))
    return {"gain": _verdict(gain), "near_oracle": _verdict(near), "no_violations": _verdict(viol)}


def limits_verdict(rows: Sequence[dict]) -> dict:
    """Thresholds 4 to 6 on graph_limited rows of judged synthetic scenarios, each scenario's worst repeat.

    A repeat that did not finish (killed, failed, invalid on truth) counts as missing the threshold.
    "A valid plan within 5 s" means valid on true times: the plan held at 5 s must have a delay on the
    truth (``delay_5s`` is set), not only a finite arrival on the graph it was planned on.
    Memory is a property of the worker process, so threshold 6 is judged on every graph_limited row
    (any scenario, judged or not, synthetic or historical), as soon as there is a judged scenario.
    """
    g = [r for r in _judged_synthetic(rows) if r.get("arm") == "graph_limited"]
    if not g:
        return {"first_plan": None, "at_30": None, "memory": None}
    worst_first: dict[str, float] = {}
    worst_gap: dict[str, float] = {}
    for r in g:
        ok = r.get("status") == "ok"
        valid_at_5 = r.get("delay_5s") is not None
        first = r.get("t_first_s") if ok and valid_at_5 and r.get("t_first_s") is not None else math.inf
        gap = r.get("gap_30s") if ok and r.get("gap_30s") is not None else math.inf
        worst_first[r["scenario"]] = max(worst_first.get(r["scenario"], -math.inf), first)
        worst_gap[r["scenario"]] = max(worst_gap.get(r["scenario"], -math.inf), gap)
    first_ok = sum(v <= FIRST_PLAN_S for v in worst_first.values()) / len(worst_first)
    gap_ok = sum(v <= NEAR_ORACLE_S for v in worst_gap.values()) / len(worst_gap)
    every = [r for r in rows if r.get("arm") == "graph_limited"]
    peaks = [r["peak_mb"] for r in every if r.get("peak_mb") is not None]
    killed = any(r.get("status") == "killed_memory" for r in every)
    return {"first_plan": _verdict(first_ok >= FIRST_PLAN_SHARE), "at_30": _verdict(gap_ok >= AT_30_SHARE),
            "memory": _verdict(not killed and max(peaks, default=0) < MEMORY_MB)}


def _quality_cells(rows: Sequence[dict]) -> list[dict]:
    cells = []
    for scope in ("all", "judged"):
        for kind in ("synthetic", "historical"):
            for arm, limits in (("main", LIMITS_M), ("control", (JUDGED_LIMIT_M,)), ("must_serve", (JUDGED_LIMIT_M,))):
                for limit in limits:
                    rs = [r for r in rows if r.get("kind") == kind and r.get("arm") == arm
                          and r.get("limit_m") == limit and (scope == "all" or r.get("judged"))]
                    ok = [r for r in rs if r.get("status") == "ok"]
                    if not rs:
                        continue
                    for m in ("R0", "R2", "R3"):
                        k = m.lower()
                        delays = [r.get(f"{k}_delay_s") for r in ok]
                        cells.append({
                            "scope": scope, "kind": kind, "arm": arm, "limit_m": limit, "method": m,
                            "scenarios": len(rs), "ok": len(ok),
                            "infeasible": sum(r.get("status") == "infeasible" for r in rs),
                            "median_delay_s": _median(delays), "p90_delay_s": _pct(delays, 90),
                            "worst_delay_s": _max(delays),
                            "median_walkers": _median([r.get(f"{k}_walkers") for r in ok]),
                            "median_walk_m_per_walker": _median([r.get(f"{k}_walk_m_per_walker") for r in ok]),
                            "share_differs_from_r0": (_share([bool(r.get("r3_differs_from_r0")) for r in ok])
                                                      if m == "R3" else None)})
    return cells


def _quality_per_route(rows: Sequence[dict]) -> dict:
    js = _judged_synthetic(rows)
    control = {r["scenario"]: r for r in js if r["arm"] == "control" and r["status"] == "ok"}
    routes: dict[str, list[dict]] = {}
    for r in js:
        if r["arm"] == "main" and r["limit_m"] == JUDGED_LIMIT_M and r["status"] == "ok":
            routes.setdefault(r["route"], []).append(r)
    out = []
    for route, rs in sorted(routes.items()):
        r2m = [r.get("r2_minus_r3_s") for r in rs]
        nets = [r["r3_gain_s"] - control[r["scenario"]]["r3_gain_s"] for r in rs
                if r["scenario"] in control and r.get("r3_gain_s") is not None
                and control[r["scenario"]].get("r3_gain_s") is not None]
        out.append({"route": route, "scenarios": len(rs), "median_r2_minus_r3_s": _median(r2m),
                    "worst_r2_minus_r3_s": _max(r2m), "median_net_gain_s": _median(nets),
                    "worst_net_gain_s": _num(float(min(nets))) if nets else None,
                    "median_r3_delay_s": _median([r.get("r3_delay_s") for r in rs]),
                    "worst_r3_delay_s": _max([r.get("r3_delay_s") for r in rs])})
    worst = max(out, key=lambda x: (x["median_r2_minus_r3_s"] or 0, x["worst_r2_minus_r3_s"] or 0), default=None)
    return {"routes": out, "worst_route": worst["route"] if worst else None,
            "worst_by": "median R2 minus R3 delay at 400 m"}


def _limits_cells(rows: Sequence[dict]) -> list[dict]:
    cells = []
    for scope in ("all", "judged"):
        for kind in ("synthetic", "historical"):
            for arm in LIMIT_ARMS:
                rs = [r for r in rows if r.get("kind") == kind and r.get("arm") == arm
                      and (scope == "all" or r.get("judged"))]
                if not rs:
                    continue
                ok = [r for r in rs if r.get("status") == "ok"]
                firsts = [r.get("t_first_s") for r in ok]
                cells.append({
                    "scope": scope, "kind": kind, "arm": arm, "runs": len(rs), "ok": len(ok),
                    "killed_memory": sum(r.get("status") == "killed_memory" for r in rs),
                    "infeasible": sum(r.get("status") == "infeasible" for r in rs),
                    "invalid_on_truth": sum(r.get("status") == "invalid_on_truth" for r in rs),
                    "median_t_first_s": _median(firsts), "worst_t_first_s": _max(firsts),
                    "share_first_within_5s": _share([f is not None and f <= FIRST_PLAN_S for f in firsts]),
                    **{f"median_gap_{t}s": _median([r.get(f"gap_{t}s") for r in ok]) for t in CHECKS_S},
                    **{f"worst_gap_{t}s": _max([r.get(f"gap_{t}s") for r in ok]) for t in CHECKS_S},
                    "median_final_gap_s": _median([r.get("final_gap_s") for r in ok]),
                    "median_planned_minus_true_s": _median([r.get("planned_minus_true_s") for r in ok]),
                    "peak_mb": _max([r.get("peak_mb") for r in rs]),
                    "widened": sum(bool(r.get("widened")) for r in rs),
                    "city_fallback": sum(r.get("corridor") == "city" for r in rs)})
    return cells


def _limits_per_route(rows: Sequence[dict]) -> dict:
    g = [r for r in _judged_synthetic(rows) if r.get("arm") == "graph_limited"]
    routes: dict[str, list[dict]] = {}
    for r in g:
        routes.setdefault(r.get("route", "?"), []).append(r)
    out = []
    for route, rs in sorted(routes.items()):
        ok = [r for r in rs if r.get("status") == "ok"]
        out.append({"route": route, "runs": len(rs), "ok": len(ok),
                    "median_t_first_s": _median([r.get("t_first_s") for r in ok]),
                    "worst_t_first_s": _max([r.get("t_first_s") for r in ok]),
                    "median_gap_30s": _median([r.get("gap_30s") for r in ok]),
                    "worst_gap_30s": _max([r.get("gap_30s") for r in ok])})
    worst = max(out, key=lambda x: (x["ok"] < x["runs"], x["worst_gap_30s"] or 0), default=None)
    return {"routes": out, "worst_route": worst["route"] if worst else None,
            "worst_by": "unfinished runs, then worst gap at 30 s"}


def _scale_cells(rows: Sequence[dict]) -> list[dict]:
    cells = []
    stops = [r for r in rows if r.get("part") == "stops" and r.get("status") == "ok"]
    for setup in ("unlimited", "limited"):
        for n in sorted({r["n_stops"] for r in stops}):
            for c in sorted({r["per_stop"] for r in stops}):
                rs = [r for r in stops if r["setup"] == setup and r["n_stops"] == n and r["per_stop"] == c]
                if rs:
                    cells.append({"part": "stops", "setup": setup, "n_stops": n, "per_stop": c, "runs": len(rs),
                                  "median_r2_cpu_s": _median([r.get("r2_cpu_s") for r in rs]),
                                  "median_r3_cpu_s": _median([r.get("r3_cpu_s") for r in rs]),
                                  "worst_r3_wall_s": _max([r.get("r3_wall_s") for r in rs]),
                                  "r3_done": sum(bool(r.get("r3_done")) for r in rs),
                                  "peak_mb": _max([r.get("r3_peak_mb") or r.get("r2_peak_mb") for r in rs])})
    for setup in ("unlimited", "limited"):
        rs = [r for r in stops if r["setup"] == setup]
        if not rs:
            continue
        for budget in (FIRST_PLAN_S, CAP_S):
            # limited rows: wall time at 0.1 CPU; unlimited rows: CPU-seconds x 10 as the 0.1 CPU estimate
            def solved(r: dict) -> bool:
                if not r.get("r3_done"):
                    return False
                t = r.get("r3_wall_s") if setup == "limited" else (r.get("r3_cpu_s") or 0) * 10
                return t is not None and t <= budget
            sizes = sorted({r["n_stops"] for r in rs})
            ok_sizes = [n for n in sizes if all(solved(r) for r in rs if r["n_stops"] == n)]
            cells.append({"part": "stops", "setup": setup, "largest_solved_within_s": budget,
                          "n_stops": max(ok_sizes, default=None),
                          "basis": "wall time" if setup == "limited" else "CPU-seconds x 10"})
    for part in ("graph", "buses", "slices"):
        for r in rows:
            if r.get("part") == part and r.get("status") == "ok":
                cells.append({k: v for k, v in r.items() if k not in ("slices", "started_at", "code_version")})
    return cells


def build_summary(out_dir: Path) -> dict | None:
    """The hub summary of one pass's folder (``meta.json["pass"]`` says which), or ``None`` without runs."""
    out_dir = Path(out_dir)
    latest = read_latest(out_dir)
    if not latest:
        return None
    meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8")) if (out_dir / "meta.json").exists() else {}
    rows = sorted(latest.values(), key=lambda r: r.get("started_at", ""))
    kind = meta.get("pass") or ("limits" if any("repeat" in r for r in rows) else "quality")
    done = finished(latest)
    total = meta.get("runs_total") or len(rows)
    left = max(0, total - len(done))
    failed = sum(1 for r in rows if r.get("status") not in RESULT_STATUSES)      # infeasible is a counted result
    if kind == "quality":
        verdict = quality_verdict(rows)
        chips = [
            {"label": f"Walking gains at least {GAIN_MIN_S} s net of the no-closure control (400 m, median)",
             "result": verdict["gain"]},
            {"label": f"Greedy within {NEAR_ORACLE_S} s of the exact plan in {NEAR_ORACLE_SHARE:.0%} of scenarios "
                      f"and on every route's median (400 m)", "result": verdict["near_oracle"]},
            {"label": "No failed run, no avoidable unserved stop, exact never later than the patched route",
             "result": verdict["no_violations"]}]
        cells, per_route, per_run_s = _quality_cells(rows), _quality_per_route(rows), 2.0
        thresholds = {"gain_min_s": GAIN_MIN_S, "near_oracle_s": NEAR_ORACLE_S,
                      "near_oracle_share": NEAR_ORACLE_SHARE, "judged_limit_m": JUDGED_LIMIT_M}
    elif kind == "limits":
        verdict = limits_verdict(rows)
        chips = [
            {"label": f"A valid plan within {FIRST_PLAN_S} s in {FIRST_PLAN_SHARE:.0%} of scenarios (graph, limited, "
                      f"worst repeat)", "result": verdict["first_plan"]},
            {"label": f"At 30 s within {NEAR_ORACLE_S} s of the oracle in {AT_30_SHARE:.0%} of scenarios "
                      f"(graph, limited, worst repeat)", "result": verdict["at_30"]},
            {"label": f"Peak memory under {MEMORY_MB} MB including the graph, none killed",
             "result": verdict["memory"]}]
        cells, per_route, per_run_s = _limits_cells(rows), _limits_per_route(rows), 15.0
        thresholds = {"first_plan_s": FIRST_PLAN_S, "first_plan_share": FIRST_PLAN_SHARE,
                      "near_oracle_s": NEAR_ORACLE_S, "at_30_share": AT_30_SHARE, "memory_mb": MEMORY_MB}
    else:
        verdict, chips, thresholds = {}, [], {"note": "curves only, no pass or fail"}
        cells, per_route, per_run_s = _scale_cells(rows), {}, 20.0
    if verdict:
        verdict["complete"] = len(done) >= total and failed == 0
    judged_main = [r for r in rows if r.get("arm") in ("main", "graph_limited")]
    return {"generated_at": now(), "meta": meta, "pass": kind, "thresholds": thresholds, "verdict": verdict,
            "chips": chips, "runs_done": len(done), "runs_total": total, "runs_failed": failed,
            "remaining_s": round(left * per_run_s), "rows": rows, "cells": cells, "per_route": per_route,
            "judged_share": _share([bool(r.get("judged")) for r in judged_main]) if judged_main else None}


def summarize(out_dir: Path) -> dict:
    s = build_summary(out_dir)
    if s is None:
        sys.exit(f"no runs yet in {out_dir}")
    (Path(out_dir) / "summary.json").write_text(json.dumps(s, indent=1, allow_nan=False), encoding="utf-8")
    print(f"{s['pass']}: {s['runs_done']}/{s['runs_total']} runs done, {s['runs_failed']} failed")
    for chip in s["chips"]:
        print(f"  {chip['result'] or 'no verdict'}: {chip['label']}")
    print(f"wrote {Path(out_dir) / 'summary.json'}")
    return s


# ================================================================ command line

def _out_dir(args: argparse.Namespace) -> Path:
    return args.out_dir or RESULTS / (PASSES[args.command] + ("-quick" if args.quick else ""))


def _write_meta(out_dir: Path, args: argparse.Namespace, scen_path: Path | None, runs_total: int, **extra) -> None:
    """Write meta.json on the first start; later starts update ``runs_total`` and the scenario file's hash.

    When the scenario file changed between starts, the earlier hashes are kept in
    ``scenarios["earlier_sha256"]``, so a folder mixing rows from two files says so.
    """
    path = out_dir / "meta.json"
    meta = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "started_at": now(), "machine": machine_info(), "pass": args.command, "quick": args.quick,
        "code_version": args.code_version,
        "scenarios": None if scen_path is None else {"file": scen_path.name,
                                                     "sha256": sha256(scen_path)}, **extra}
    if scen_path is not None and meta.get("scenarios"):
        info = meta["scenarios"]
        digest = sha256(scen_path)
        if info.get("sha256") != digest:
            info.setdefault("earlier_sha256", []).append(info.get("sha256"))
            info["sha256"] = digest
        info["version"] = json.loads(scen_path.read_text(encoding="utf-8")).get("version")
    meta["runs_total"] = runs_total
    path.write_text(json.dumps(meta, indent=1), encoding="utf-8")


def _scenario_path(args: argparse.Namespace) -> Path:
    if args.quick:
        if not TOY.exists():
            sys.exit(f"{TOY} is missing: run 'python research/run_reroute.py make-toy' first")
        return TOY
    path = args.scenarios or SCENARIOS
    if not path.exists():
        sys.exit(f"{path} is missing: build it with build_scenarios.py (needs OSRM), or use --quick")
    return path


def _limits_or_exit(args: argparse.Namespace) -> tuple[str, dict | None]:
    """``("systemd", check)`` when the limits apply, ``("none", None)`` with --no-limits; else exit."""
    if args.no_limits:
        print("--no-limits: nothing is limited; every row records limits 'none'")
        return "none", None
    if not sys.platform.startswith("linux"):
        sys.exit("The limits come from systemd cgroups (Linux or WSL). This machine cannot apply them, so "
                 "the pass refuses to claim them. Use --no-limits for a dry run with limits 'none'.")
    import run_budget
    check = run_budget.check_limits(args.sudo)
    print("limits:", json.dumps(check.get("found")), "OK" if check["ok"] else "NOT APPLIED")
    if not check["ok"]:
        sys.exit("Limits were not applied. Try --sudo, or see 'Limits without Docker' in research/README.md. "
                 f"{check.get('error', '')}")
    return "systemd", check


def cmd_quality(args: argparse.Namespace) -> None:
    out_dir = _out_dir(args)
    if args.summarize:
        summarize(out_dir)
        return
    scen_path = _scenario_path(args)
    cases = load_cases(scen_path, args.walk)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_meta(out_dir, args, scen_path, 5 * len(cases["scenarios"]), limits_m=list(LIMITS_M),
                workers=args.workers)
    done = finished(read_latest(out_dir))
    todo = [s for s in cases["scenarios"] if not set(quality_keys(s)) <= done]
    print(f"{len(cases['scenarios']) - len(todo)} scenarios already done, {len(todo)} to go")
    jobs = [(s, cases["closures"][s["closure"]], case_walk(s, cases["walk"])) for s in todo]

    def record(i: int, rows: list[dict]) -> None:
        for r in rows:
            r["code_version"] = args.code_version
        append_rows(out_dir, [r for r in rows if r["key"] not in done])
        main = next((r for r in rows if r["arm"] == "main" and r["limit_m"] == JUDGED_LIMIT_M), rows[0])
        print(f"[{i}/{len(jobs)}] {main['scenario']}: {main['status']}"
              + (f", R0 {main['r0_delay_s']} s, R3 {main['r3_delay_s']} s at 400 m"
                 if main["status"] == "ok" else ""), flush=True)

    if args.workers > 1 and len(jobs) > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(_quality_job, *j) for j in jobs]
            for i, f in enumerate(futures, 1):
                record(i, f.result())
    else:
        for i, j in enumerate(jobs, 1):
            record(i, _quality_job(*j))
    summarize(out_dir)


def cmd_limits(args: argparse.Namespace) -> None:
    out_dir = _out_dir(args)
    if args.summarize:
        summarize(out_dir)
        return
    scen_path = _scenario_path(args)
    limits, check = _limits_or_exit(args)
    cases = load_cases(scen_path, args.walk)
    arms = ("truth_limited",) if args.quick else LIMIT_ARMS
    jobs = limit_jobs(cases, arms, 1 if args.quick else REPEATS)
    for sub in ("logs", "work"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    _write_meta(out_dir, args, scen_path, sum(len(j["keys"]) for j in jobs), limits=limits,
                limits_check=check, arms=list(arms), repeats=1 if args.quick else REPEATS, cap_s=CAP_S,
                slice_masks=SLICE_MASKS, use_sudo=args.sudo)
    done = finished(read_latest(out_dir))
    todo = [j for j in jobs if not set(j["keys"]) <= done]
    print(f"{len(jobs) - len(todo)} worker jobs already done, {len(todo)} to go")
    by_id = {s["id"]: s for s in cases["scenarios"]}
    oracles: dict[str, dict] = {}
    for i, job in enumerate(todo, 1):
        name = f"{job['route']}-{job['arm']}-r{job['repeat']}"
        rows_path, log_path = out_dir / "work" / f"{name}.jsonl", out_dir / "logs" / f"{name}.log"
        rows_path.unlink(missing_ok=True)
        limited = job["arm"] in LIMITED_ARMS and limits == "systemd"
        cmd = [sys.executable, str(Path(__file__).resolve()), "worker", "--route", job["route"], "--arm", job["arm"],
               "--repeat", str(job["repeat"]), "--out", str(rows_path), "--scenarios", str(scen_path),
               "--graph", str(args.graph), "--corridors", str(args.corridors), "--instance", str(args.instance)]
        if args.walk:
            cmd += ["--walk", str(args.walk)]
        if args.quick:
            cmd.append("--toy")
        if limited:
            import run_budget
            cmd = run_budget.limit_prefix(args.sudo) + cmd
        started = now()
        timeout = None if job["arm"] == "graph_unlimited" else 300 + 2 * CAP_S * len(job["scenarios"])
        with open(log_path, "w", encoding="utf-8") as log:
            try:
                rc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                rc = -1
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        got = read_jsonl(rows_path)
        if job["arm"] != "truth_limited" and rc != 0 and not Path(args.graph).exists():
            rows = [{"scenario": sid, "status": "skipped", "error": f"no road graph at {args.graph}"}
                    for sid in job["scenarios"]]
        else:
            rows = worker_outcome(job, rc, log_text, got, limited)
        out = []
        for r in rows:
            s = by_id[r["scenario"]]
            closure = cases["closures"][s["closure"]]
            if s["id"] not in oracles:
                oracles[s["id"]] = safe_oracle_info(s, closure, cases["walk"])
            key = f"{s['id']}-{job['arm']}-r{job['repeat']}"
            full = {"key": key, "setup": f"{job['arm']} r{job['repeat']}", "status": r["status"],
                    **_scenario_head(s, closure), "arm": job["arm"], "repeat": job["repeat"],
                    **{k: v for k, v in r.items() if k not in ("status",)},
                    "limits": "none" if job["arm"] == "graph_unlimited" else limits,
                    "started_at": started, "code_version": args.code_version}
            full = fill_gaps(full, oracles[s["id"]])
            if key not in done:
                out.append(full)
        append_rows(out_dir, out)
        states = sorted({r["status"] for r in out}) or ["already done"]
        print(f"[{i}/{len(todo)}] {name}: {len(out)} rows, {', '.join(states)} (worker exit {rc})", flush=True)
    summarize(out_dir)


def cmd_scale(args: argparse.Namespace) -> None:
    out_dir = _out_dir(args)
    if args.summarize:
        summarize(out_dir)
        return
    if args.quick:
        limits, check = "none", None
    else:
        limits, check = _limits_or_exit(args)
    scen_path = TOY if args.quick else (args.scenarios or SCENARIOS)
    if args.quick and not TOY.exists():
        sys.exit(f"{TOY} is missing: run 'python research/run_reroute.py make-toy' first")
    cases = load_cases(scen_path, args.walk) if scen_path.exists() else None
    if cases is None:
        print(f"{scen_path} is missing: the slices and buses parts are skipped")
    jobs = scale_jobs(args.quick, args.only, cases, limits_ok=not args.quick)
    (out_dir / "work").mkdir(parents=True, exist_ok=True)
    _write_meta(out_dir, args, scen_path if scen_path.exists() else None, len(jobs), limits=limits,
                limits_check=check, only=args.only, cap_s=CAP_S, slice_masks=SLICE_MASKS)
    done = finished(read_latest(out_dir))
    todo = [j for j in jobs if j["key"] not in done]
    print(f"{len(jobs) - len(todo)} measurements already done, {len(todo)} to go")
    for i, job in enumerate(todo, 1):
        res_path = out_dir / "work" / f"{job['key']}.json"
        res_path.unlink(missing_ok=True)
        cmd = [sys.executable, str(Path(__file__).resolve()), "scale-job", "--job", json.dumps(job),
               "--out", str(res_path), "--scenarios", str(scen_path), "--graph", str(args.graph),
               "--corridors", str(args.corridors), "--instance", str(args.instance)]
        if args.walk:
            cmd += ["--walk", str(args.walk)]
        limited = job["setup"] == "limited" and limits == "systemd"
        if limited:
            import run_budget
            cmd = run_budget.limit_prefix(args.sudo) + cmd
        started = now()
        needs_graph = job["part"] in ("graph", "buses")
        if needs_graph and not Path(args.graph).exists():
            res, rc = {"status": "skipped", "error": f"no road graph at {args.graph}"}, 0
        elif job["part"] == "buses" and cases is None:
            res, rc = {"status": "skipped", "error": f"no scenario file at {scen_path}"}, 0
        else:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=None if job["setup"] == "unlimited" else 900)
            rc = r.returncode
            if rc == 0 and res_path.exists():
                res = json.loads(res_path.read_text(encoding="utf-8"))
            else:
                killed = "MemoryError" in r.stderr or (limited and rc in (-9, 137))
                res = {"status": "killed_memory" if killed else "failed", "error": (r.stderr or r.stdout)[-300:]}
        row = {"key": job["key"], "setup": job["setup"], "status": res.pop("status", "ok"),
               **{k: v for k, v in job.items() if k not in ("key", "setup")}, **res,
               "limits": limits if job["setup"] == "limited" else "none",
               "started_at": started, "code_version": args.code_version}
        append_rows(out_dir, [row])
        print(f"[{i}/{len(todo)}] {job['key']}: {row['status']}", flush=True)
    summarize(out_dir)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("make-toy", help="write data/scenarios_toy.json")

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--quick", action="store_true", help="toy file only, written to a '-quick' folder")
        p.add_argument("--summarize", action="store_true", help="only rebuild summary.json")
        p.add_argument("--code-version", default=None, help="git commit of the code (the hub passes it)")
        p.add_argument("--out-dir", type=Path, default=None)
        p.add_argument("--scenarios", type=Path, default=None, help=f"default {SCENARIOS.relative_to(ROOT)}")
        p.add_argument("--walk", type=Path, default=None, help=f"default {WALK.relative_to(ROOT)}")
        p.add_argument("--graph", type=Path, default=GRAPH)
        p.add_argument("--corridors", type=Path, default=CORRIDORS)
        p.add_argument("--instance", type=Path, default=INSTANCE)

    q = sub.add_parser("quality", help="R0, R2, R3 on true times at 0, 400, 800 m, plus control and must-serve")
    common(q)
    q.add_argument("--workers", type=int, default=1, help="scenarios solved in parallel")
    for name, text in (("limits", "decision time under 512 MB and 0.1 CPU"), ("scale", "scaling curves")):
        p = sub.add_parser(name, help=text)
        common(p)
        p.add_argument("--sudo", action="store_true", help="use 'sudo systemd-run --scope' for the limits")
        p.add_argument("--no-limits", action="store_true",
                       help="run without systemd limits (a dry run); every row records limits 'none'")
        if name == "scale":
            p.add_argument("--only", choices=("stops", "graph", "buses", "slices"), default=None)

    w = sub.add_parser("worker", help="internal: one route, arm and repeat of the limits pass")
    w.add_argument("--route", required=True)
    w.add_argument("--arm", required=True, choices=LIMIT_ARMS)
    w.add_argument("--repeat", type=int, required=True)
    w.add_argument("--out", type=Path, required=True)
    w.add_argument("--toy", action="store_true", help="read data/scenarios_toy.json")
    w.add_argument("--scenarios", type=Path, default=SCENARIOS)
    w.add_argument("--walk", type=Path, default=None)
    w.add_argument("--graph", type=Path, default=GRAPH)
    w.add_argument("--corridors", type=Path, default=CORRIDORS)
    w.add_argument("--instance", type=Path, default=INSTANCE)

    j = sub.add_parser("scale-job", help="internal: one scaling measurement")
    j.add_argument("--job", required=True)
    j.add_argument("--out", type=Path, required=True)
    j.add_argument("--scenarios", type=Path, default=SCENARIOS)
    j.add_argument("--walk", type=Path, default=None)
    j.add_argument("--graph", type=Path, default=GRAPH)
    j.add_argument("--corridors", type=Path, default=CORRIDORS)
    j.add_argument("--instance", type=Path, default=INSTANCE)
    args = ap.parse_args(argv)
    if args.command == "worker" and args.toy:
        args.scenarios = TOY
    if hasattr(args, "code_version") and not getattr(args, "summarize", False):
        args.code_version = code_version(args.code_version)
    return args


def main(argv: Sequence[str] | None = None) -> None:
    sys.path.insert(0, str(ROOT))
    args = parse_args(argv)
    if args.command == "make-toy":
        print(f"wrote {make_toy()}")
    elif args.command == "quality":
        cmd_quality(args)
    elif args.command == "limits":
        cmd_limits(args)
    elif args.command == "scale":
        cmd_scale(args)
    elif args.command == "worker":
        _worker_main(args)
    else:
        _scale_job_main(args)


if __name__ == "__main__":
    main()
