"""Timings and memory of the road graph under the free-tier limits (work item B4, gate G1).

    python research/measure_graph.py                 # no limits (recorded as "limits": "none")
    python research/measure_graph.py --no-limits     # the same, stated explicitly
    python research/measure_graph.py --limited       # Linux (WSL) only: inside a systemd scope with
                                                     # MemoryMax=512M, MemorySwapMax=0, CPUQuota=10%

Each mode runs the measurement in a fresh child process (inside the limits for ``--limited``) and
merges its figures into ``results/graph-timing/timing.json`` under the mode's name. Measured on the
longest current route, 5 repeats each: graph load time; resident memory after importing numpy and
scipy only, after the load and at the peak; CPU-seconds and wall seconds for 1 row, for the 14 rows
R0 needs and for 31 rows, on the route's corridor and on the whole city. Every repeat starts with
an empty row cache.

Gate G1 (work plan): on the corridor, under the limits, 14 rows in at most 5 s of wall time and 31
rows in at most 30 s, judged on the worst repeat. Only a ``--limited`` run whose limits were read
back from the kernel can pass or fail it; on Windows or macOS ``--limited`` refuses to run, because
the limits come from systemd and could not be claimed.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

RESEARCH = Path(__file__).resolve().parent
DEFAULT_GRAPH = RESEARCH / "data" / "graph_karachi_v1"
DEFAULT_CORRIDORS = RESEARCH / "data" / "corridors_fall2026_v1"
DEFAULT_INSTANCE = RESEARCH / "data" / "instance_fall2026_v1.json"
DEFAULT_OUT = RESEARCH / "results" / "graph-timing"
SIZES = (1, 14, 31)
REPEATS = 5
GATE_G1 = {14: 5.0, 31: 30.0}          # rows -> most wall seconds allowed, corridor, limited


# ---------------------------------------------------------------- memory, portable

def rss_mb() -> float:
    """Resident memory of this process in MB."""
    import psutil
    return psutil.Process().memory_info().rss / 2 ** 20


def peak_rss_mb() -> float:
    """Peak resident memory of this process in MB (``resource`` on Unix, the peak working set on Windows)."""
    if sys.platform.startswith("win"):
        import psutil
        return psutil.Process().memory_info().peak_wset / 2 ** 20
    import resource                     # Unix only; never imported at module level
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 2 ** 20 if sys.platform == "darwin" else peak / 1024


# ---------------------------------------------------------------- the measurement (child process)

def longest_route(instance: Mapping) -> tuple[str, list[str]]:
    """Key (``contractor-code``) and stop names of the current route with the most stops."""
    best = max(((c, r) for c, d in sorted(instance["contractors"].items()) for r in d["baseline_routes"]),
               key=lambda cr: (len(cr[1]["stops"]), cr[0], cr[1]["code"]))
    return f"{best[0]}-{best[1]['code']}", list(best[1]["stops"])


def pick_sources(graph, corridor, route_nodes: Sequence[int], instance_nodes: Sequence[int],
                 count: int, seed: int = 0) -> list[int]:
    """``count`` distinct source nodes inside the corridor: the route's own points first, then other
    stops that fall inside the corridor, then random corridor nodes (seeded)."""
    import numpy as np
    inside = set(corridor.nodes.tolist()) if corridor is not None else set(range(graph.n_nodes))
    out = list(dict.fromkeys(int(n) for n in route_nodes if int(n) in inside))
    out += [n for n in dict.fromkeys(int(x) for x in instance_nodes) if n in inside and n not in out]
    pool = np.asarray(sorted(inside - set(out)), dtype=np.int64)
    rng = np.random.default_rng(seed)
    extra = rng.permutation(pool)[:max(0, count - len(out))].tolist() if len(pool) else []
    return (out + [int(x) for x in extra])[:count]


def time_rows(graph, corridor, sources: Sequence[int], repeats: int) -> dict:
    """CPU and wall seconds of one ``rows`` call for ``sources``, each repeat with an empty cache."""
    from reroute.graph import TravelTimes, clear_row_cache
    wall, cpu = [], []
    for _ in range(repeats):
        clear_row_cache()
        tt = TravelTimes(graph, corridor)
        w0, c0 = time.perf_counter(), time.process_time()
        tt.rows(list(sources))
        wall.append(round(time.perf_counter() - w0, 4))
        cpu.append(round(time.process_time() - c0, 4))
    clear_row_cache()
    return {"rows": len(sources), "wall_s": wall, "cpu_s": cpu, "wall_median_s": statistics.median(wall),
            "wall_worst_s": max(wall), "cpu_median_s": statistics.median(cpu)}


def measure(graph_dir: Path, corridors_dir: Path, instance: Mapping, repeats: int = REPEATS) -> dict:
    """Run every measurement in this process and return the figures (call in a fresh process)."""
    start_rss = rss_mb()
    import numpy  # noqa: F401  (measured: memory after numpy and scipy only)
    import scipy.sparse.csgraph  # noqa: F401
    import scipy.spatial  # noqa: F401
    libs_rss = rss_mb()

    from reroute.graph import Graph, graph_info, load_corridor
    loads = []
    graph = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        graph = Graph.load(graph_dir)
        loads.append(round(time.perf_counter() - t0, 4))
    load_rss = rss_mb()

    key, stop_names = longest_route(instance)
    corridor = load_corridor(corridors_dir, key, graph.version)
    stops = {s["name"]: s for s in instance["stops"]}
    campus = instance["campus"]
    route_nodes = [graph.nearest_node(stops[n]["lat"], stops[n]["lng"])[0] for n in stop_names]
    route_nodes.append(graph.nearest_node(campus["lat"], campus["lng"])[0])
    other = [graph.nearest_node(s["lat"], s["lng"])[0] for s in instance["stops"] if s["name"] not in stop_names]

    areas = {"corridor": corridor, "city": None} if corridor is not None else {"city": None}
    timings: dict[str, dict] = {}
    for area, c in areas.items():
        sources = pick_sources(graph, c, route_nodes, other, max(SIZES))
        timings[area] = {str(k): time_rows(graph, c, sources[:k], repeats) for k in SIZES if k <= len(sources)}
    return {"graph": graph_info(graph), "route": key, "route_stops": len(stop_names),
            "corridor_nodes": int(len(corridor.nodes)) if corridor is not None else None,
            "repeats": repeats, "load_s": loads, "load_median_s": statistics.median(loads),
            "rss_mb": {"start": round(start_rss, 1), "after_numpy_scipy": round(libs_rss, 1),
                       "after_load": round(load_rss, 1), "peak": round(peak_rss_mb(), 1)},
            "timings": timings}


# ---------------------------------------------------------------- parent: modes, limits, file

def gate_g1(limited: Mapping | None) -> dict:
    """Gate G1 verdict from a limited run's corridor timings (worst repeat); ``not run`` without one."""
    if not limited or "corridor" not in limited.get("timings", {}):
        return {"verdict": "not run", "rule": {f"{k} rows": f"<= {v:g} s" for k, v in GATE_G1.items()}}
    t = limited["timings"]["corridor"]
    checks = {f"{k} rows": {"worst_wall_s": t[str(k)]["wall_worst_s"], "limit_s": v,
                            "pass": t[str(k)]["wall_worst_s"] <= v}
              for k, v in GATE_G1.items() if str(k) in t}
    ok = len(checks) == len(GATE_G1) and all(c["pass"] for c in checks.values())
    return {"verdict": "pass" if ok else "fail", "checks": checks}


def run_child(cmd_prefix: Sequence[str], args) -> dict:
    """Run :func:`measure` in a fresh Python process (under ``cmd_prefix``) and read its figures."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "child.json"
        cmd = [*cmd_prefix, sys.executable, str(Path(__file__).resolve()), "--child", str(out),
               "--graph", str(args.graph), "--corridors", str(args.corridors), "--instance", str(args.instance),
               "--repeats", str(args.repeats)]
        r = subprocess.run(cmd, cwd=str(RESEARCH), capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"measurement failed (exit {r.returncode}): {(r.stderr or r.stdout)[-800:]}")
        return json.loads(out.read_text())


def machine() -> dict:
    return {"host": platform.node(), "system": platform.system(), "release": platform.release(),
            "python": platform.python_version(), "cpus": os.cpu_count()}


def write_result(out_dir: Path, mode: str, figures: Mapping) -> dict:
    """Merge one mode's figures into ``timing.json`` and recompute the gate verdict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "timing.json"
    data = json.loads(path.read_text()) if path.exists() else {"runs": {}}
    data["runs"][mode] = dict(figures)
    data["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    data["gate_g1"] = gate_g1(data["runs"].get("limited"))
    path.write_text(json.dumps(data, indent=1))
    return data


def print_figures(mode: str, f: Mapping) -> None:
    print(f"[{mode}] limits: {json.dumps(f['limits'])}")
    print(f"[{mode}] graph {f['graph']['version']}: {f['graph']['nodes']:,} nodes; route {f['route']} "
          f"({f['route_stops']} stops, corridor {f['corridor_nodes']} nodes)")
    m = f["rss_mb"]
    print(f"[{mode}] load {f['load_median_s']} s; RSS MB: numpy+scipy {m['after_numpy_scipy']}, "
          f"after load {m['after_load']}, peak {m['peak']}")
    for area, sizes in f["timings"].items():
        for k, t in sizes.items():
            print(f"[{mode}] {area:<8} {k:>2} rows: wall median {t['wall_median_s']} s, worst {t['wall_worst_s']} s, "
                  f"CPU median {t['cpu_median_s']} s")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--limited", action="store_true", help="run inside the free-tier limits (Linux, systemd)")
    mode.add_argument("--no-limits", action="store_true", help="run with no limits; recorded as limits: none")
    mode.add_argument("--child", type=Path, help=argparse.SUPPRESS)
    ap.add_argument("--sudo", action="store_true", help="use 'sudo systemd-run --scope' for --limited")
    ap.add_argument("--repeats", type=int, default=REPEATS)
    ap.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    ap.add_argument("--corridors", type=Path, default=DEFAULT_CORRIDORS)
    ap.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    instance = json.loads(args.instance.read_text())

    if args.child:
        args.child.write_text(json.dumps(measure(args.graph, args.corridors, instance, args.repeats)))
        return 0
    if args.limited and not sys.platform.startswith("linux"):
        print("--limited needs Linux (WSL) with systemd: the limits come from systemd cgroups and "
              "cannot be applied or claimed here. Use --no-limits for an unlimited run.", file=sys.stderr)
        return 2
    if not (args.graph / "meta.json").exists():
        print(f"no graph at {args.graph}: run build_graph.py first", file=sys.stderr)
        return 2

    if args.limited:
        import run_budget
        check = run_budget.check_limits(args.sudo)
        if not check["ok"]:
            print(f"limits were not applied: {check.get('error', check.get('found'))}", file=sys.stderr)
            return 2
        figures = run_child(run_budget.limit_prefix(args.sudo), args)
        figures["limits"] = check
        name = "limited"
    else:
        figures = run_child([], args)
        figures["limits"] = "none"
        name = "unlimited"
    figures["machine"] = machine()
    data = write_result(args.out, name, figures)
    print_figures(name, figures)
    print(f"gate G1: {data['gate_g1']['verdict']}")
    print(f"wrote {args.out / 'timing.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
