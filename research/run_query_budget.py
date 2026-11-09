"""Query-budget experiment: how few real travel-time queries still give good routes?

    python research/run_query_budget.py --quick        # pipeline test (about 2 min), results/query-budget-quick/
    python research/run_query_budget.py --workers 2    # full experiment (72 runs, about 40 min on 2 cores), resumable
    python research/run_query_budget.py --summarize    # rebuild the summary from finished runs

A real deployment pays per travel-time query (OSRM on a small server, or a hosted matrix API).
This experiment uses the full OSRM matrix (run M1) as ground truth and simulates a smaller query budget:
- queried cells: each stop's leg to campus, plus its K nearest stops by straight-line distance
  (K = 0, 3, 5, 10, 20, 40); these cells keep their real OSRM time;
- every other cell is estimated, by one of two estimators fitted only on the queried cells:
    crowfly  real time ~ a + b * straight-line distance (least squares)
    graph    shortest path through the queried cells (Dijkstra); crowfly where no path exists
- control: the full matrix (estimator "exact").
The optimizer (optimize.py: solve) plans on the estimated matrix; the plan is then scored on the real
matrix (optimize.py: score). So the score is what students would actually ride.

Pass/fail thresholds are fixed here and in LOGBOOK.md (2026-11-09) before any run. Do not change after results exist.
Research only: no Django, no website, no database.
"""
import argparse
import heapq
import json
import math
import os
import platform
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"
CONTRACTORS = ["Jadoon", "Nadeem"]
KS = [0, 3, 5, 10, 20, 40]
ESTIMATORS = ["crowfly", "graph"]
REPEATS = 3
BUDGET_S = 60                # unlimited search; run B1: 60 s unlimited = 600 s at 0.1 CPU in plan quality

# Fixed before the runs (LOGBOOK 2026-11-09). Do not change after results exist.
PRIMARY_ESTIMATOR, PRIMARY_K = "graph", 10
GAP_THRESHOLD_PCT = 3.0      # median real student-min within 3% of the full-matrix control, both contractors
FEASIBLE_FROM_K = 10         # every run with K >= 10: no student over 90 min on real times


def haversine(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def load(contractor):
    inst = json.loads((DATA / "instance_fall2026_v1.json").read_text())
    mat = json.loads((DATA / "matrix_fall2026_v1.json").read_text())
    by_name = {s["name"]: s for s in inst["stops"]}
    m = mat["contractors"][contractor]
    nodes, T = m["nodes"], m["durations_s"]
    coords = [(inst["campus"]["lat"], inst["campus"]["lng"])] + [(by_name[n]["lat"], by_name[n]["lng"]) for n in nodes[1:]]
    q = [0] + [by_name[n]["students"].get(contractor, 0) for n in nodes[1:]]
    c = inst["contractors"][contractor]
    pos = {n: i for i, n in enumerate(nodes)}
    return {"inst": inst, "nodes": nodes, "T": T, "coords": coords, "q": q,
            "caps": [b["capacity"] for b in c["buses"]],
            "baseline_routes": [[pos[s] for s in r["stops"]] for r in c["baseline_routes"]],
            "baseline_names": [r["stops"] for r in c["baseline_routes"]]}


def queried_cells(D, k):
    """Directed cells (i, j) that are 'queried': i -> campus, and i -> its k nearest stops. None = all."""
    n = len(D)
    if k is None:
        return {(i, j) for i in range(1, n) for j in range(n) if i != j}
    cells = set()
    for i in range(1, n):
        cells.add((i, 0))
        near = sorted((D[i][j], j) for j in range(1, n) if j != i)[:k]
        cells.update((i, j) for _, j in near)
    return cells


def fit_crowfly(T, D, cells):
    xs = [D[i][j] for i, j in cells]
    ys = [T[i][j] for i, j in cells]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx else 0.0
    return my - b * mx, b


def estimate(T, D, cells, estimator):
    """Matrix the optimizer sees: real times on queried cells, estimates elsewhere."""
    n = len(T)
    if estimator == "exact":
        return [row[:] for row in T], {"a": None, "b": None, "graph_fallback_cells": 0}
    a, b = fit_crowfly(T, D, cells)
    E = [[0 if i == j else max(1.0, a + b * D[i][j]) for j in range(n)] for i in range(n)]
    fallback = 0
    if estimator == "graph":
        adj = [[] for _ in range(n)]
        for i, j in cells:
            if j != 0:                       # campus is a sink: no path continues through it
                adj[i].append((j, T[i][j]))
        for s in range(1, n):
            dist = [math.inf] * n
            dist[s] = 0
            heap = [(0, s)]
            while heap:
                d, u = heapq.heappop(heap)
                if d > dist[u]:
                    continue
                for v, w in adj[u]:
                    if d + w < dist[v]:
                        dist[v] = d + w
                        heapq.heappush(heap, (dist[v], v))
            for j in range(1, n):
                if j != s:
                    if dist[j] < math.inf:
                        E[s][j] = dist[j]
                    else:
                        fallback += 1
    for i, j in cells:
        E[i][j] = T[i][j]
    return [[int(round(x)) for x in row] for row in E], {"a": round(a, 1), "b": round(b, 5), "graph_fallback_cells": fallback}


def plan(contractors, ks, estimators, repeats):
    """Repeat-major: after one pass every cell has a first result."""
    configs = [("exact", None)] + [(e, k) for k in ks for e in estimators if not (e == "graph" and k == 0)]
    jobs = []
    for rep in range(1, repeats + 1):
        for c in contractors:
            for e, k in configs:
                kk = "full" if k is None else f"K{k}"
                jobs.append({"key": f"{c}-{e}-{kk}-r{rep}", "contractor": c, "estimator": e,
                             "k": k, "repeat": rep, "setup": f"{e} {kk}"})
    return jobs


def run_one(job, out_dir, budget_s):
    from optimize import score, solve      # imported here so --summarize works without OR-Tools
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    d = load(job["contractor"])
    T, q, n = d["T"], d["q"], len(d["T"])
    D = [[haversine(d["coords"][i], d["coords"][j]) for j in range(n)] for i in range(n)]
    cells = queried_cells(D, job["k"])
    E, fit = estimate(T, D, cells, job["estimator"])
    unq = [(i, j) for i in range(1, n) for j in range(1, n) if i != j and (i, j) not in cells]
    errs = [(E[i][j] - T[i][j]) / T[i][j] * 100 for i, j in unq if T[i][j] > 0]

    cpu0, wall0 = time.process_time(), time.perf_counter()
    result, progress = solve(E, q, d["caps"], budget_s)
    cpu, wall = time.process_time() - cpu0, time.perf_counter() - wall0
    row = {**job, "started_at": started, "budget_s": budget_s,
           "cells_queried": len(cells), "cells_pct": round(len(cells) / (n - 1) / (n - 1) * 100, 1),
           "est_abs_err_pct": round(statistics.median(abs(e) for e in errs), 1) if errs else 0.0,
           "est_bias_pct": round(statistics.median(errs), 1) if errs else 0.0,
           **fit, "solve_wall_s": round(wall, 1), "solve_cpu_s": round(cpu, 1)}
    baseline = score(d["baseline_routes"], T, q)
    report = {"run_id": job["key"], "instance": d["inst"]["version"], "time_limit_s": budget_s,
              "model": {"deadline": "08:00", "max_ride_min": 90, "stop_time": "60 s + 5 s/student",
                        "objective": "total student ride time, driving time as tie-breaker",
                        "matrix": f"{job['estimator']}, K={job['k'] if job['k'] is not None else 'full'}; scored on real times"},
              "contractors": {}}
    entry = {"baseline": baseline, "solve_wall_s": row["solve_wall_s"], "solve_cpu_s": row["solve_cpu_s"],
             "peak_rss_mb": None, "progress": progress, "baseline_routes": d["baseline_names"]}
    if result is None:
        row["status"] = "no_plan"
        entry["optimized"] = None
    else:
        real, planned = score(result["routes"], T, q), score(result["routes"], E, q)
        legs = [(a, b) for r in result["routes"] if r for a, b in zip(r, r[1:])]
        row.update({"status": "ok", "total_student_ride_min": real["total_student_ride_min"],
                    "planned_ride_min": planned["total_student_ride_min"],
                    "longest_ride_min": real["longest_ride_min"], "stops_over_90_min": real["stops_over_90_min"],
                    "planned_stops_over_90_min": planned["stops_over_90_min"],
                    "buses_used": real["buses_used"], "dropped_stops": len(result["dropped"]),
                    "legs_real_pct": round(sum((a, b) in cells for a, b in legs) / len(legs) * 100, 1) if legs else None,
                    "baseline_total_student_ride_min": baseline["total_student_ride_min"]})
        real["dropped_stops"] = [d["nodes"][i] for i in result["dropped"]]
        entry["optimized"] = real
        entry["routes"] = [[d["nodes"][i] for i in r] for r in result["routes"] if r]
    report["contractors"][job["contractor"]] = entry
    (out_dir / "runs" / f"{job['key']}.json").write_text(json.dumps(report, indent=1))
    return row


# ---------------------------------------------------------------- summary

def build_summary(out_dir):
    path = out_dir / "runs.jsonl"
    if not path.exists():
        return None
    latest = {}
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            latest[r["key"]] = r
    rows = list(latest.values())
    meta = json.loads((out_dir / "meta.json").read_text()) if (out_dir / "meta.json").exists() else {}
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "meta": meta,
               "thresholds": {"primary": f"{PRIMARY_ESTIMATOR} K={PRIMARY_K}", "gap_threshold_pct": GAP_THRESHOLD_PCT,
                              "feasible_from_k": FEASIBLE_FROM_K},
               "contractors": {}}
    gap_ok, feas_ok = [], []
    for c in sorted({r["contractor"] for r in rows}):
        mine = [r for r in rows if r["contractor"] == c]
        ok = [r for r in mine if r["status"] == "ok"]
        if not ok:
            summary["contractors"][c] = {"control_ride_min": None, "current_routes_ride_min": None,
                                         "smallest_k_within_threshold": {}, "cells": [], "note": "no successful runs"}
            continue
        ctrl = [r["total_student_ride_min"] for r in ok if r["estimator"] == "exact"]
        control = statistics.median(ctrl) if ctrl else None
        cells = []
        for setup in sorted({r["setup"] for r in mine}, key=lambda s: (s.split()[0] != "exact", s.split()[0],
                                                                        int(s.split()[1][1:]) if s.split()[1] != "full" else 10 ** 6)):
            rs = [r for r in mine if r["setup"] == setup]
            good = [r for r in rs if r["status"] == "ok"]

            def med(key):
                vals = [r[key] for r in good if r.get(key) is not None]
                return round(statistics.median(vals), 1) if vals else None
            ride = med("total_student_ride_min")
            gaps = [round((r["total_student_ride_min"] - control) / control * 100, 2) for r in good] if control else []
            cell = {"setup": setup, "estimator": rs[0]["estimator"], "k": rs[0]["k"], "runs": len(rs), "ok": len(good),
                    "cells_queried": rs[0].get("cells_queried"), "cells_pct": rs[0].get("cells_pct"),
                    "est_abs_err_pct": rs[0].get("est_abs_err_pct"), "est_bias_pct": rs[0].get("est_bias_pct"),
                    "ride_min": ride, "gap_pct": round((ride - control) / control * 100, 2) if ride and control else None,
                    "gap_range": [min(gaps), max(gaps)] if gaps else None,
                    "planned_ride_min": med("planned_ride_min"), "longest_ride_min": max((r["longest_ride_min"] for r in good), default=None),
                    "runs_over_90": sum(r["stops_over_90_min"] > 0 for r in good), "legs_real_pct": med("legs_real_pct")}
            cells.append(cell)
            if cell["estimator"] == PRIMARY_ESTIMATOR and cell["k"] == PRIMARY_K and cell["gap_pct"] is not None:
                gap_ok.append(cell["gap_pct"] <= GAP_THRESHOLD_PCT)
            if cell["k"] is not None and cell["k"] >= FEASIBLE_FROM_K and good:
                feas_ok.append(cell["runs_over_90"] == 0)
        smallest = {}
        for e in ESTIMATORS:
            hits = [x["k"] for x in cells if x["estimator"] == e and x["gap_pct"] is not None and x["gap_pct"] <= GAP_THRESHOLD_PCT]
            smallest[e] = min(hits) if hits else None
        summary["contractors"][c] = {"control_ride_min": control, "current_routes_ride_min": ok[0]["baseline_total_student_ride_min"] if ok else None,
                                     "smallest_k_within_threshold": smallest, "cells": cells}
    full = plan(CONTRACTORS, meta.get("ks", KS), ESTIMATORS, meta.get("repeats", REPEATS))
    complete = len(rows) >= len(full) and all(r["status"] == "ok" for r in rows)
    summary["verdict"] = {"gap": None if not gap_ok else ("pass" if all(gap_ok) else "fail"),
                          "feasibility": None if not feas_ok else ("pass" if all(feas_ok) else "fail"),
                          "complete": complete}
    ok_keys = {r["key"] for r in rows if r["status"] == "ok"}
    summary["runs_done"], summary["runs_total"] = len(ok_keys), len(full)
    summary["runs_failed"] = len(rows) - len(ok_keys)
    summary["remaining_s"] = round(sum(meta.get("budget_s", BUDGET_S) + 5 for j in full if j["key"] not in ok_keys))
    summary["rows"] = sorted(rows, key=lambda r: r.get("started_at", ""))
    return summary


def summarize(out_dir):
    s = build_summary(out_dir)
    if s is None:
        sys.exit(f"no runs yet in {out_dir}")
    (out_dir / "summary.json").write_text(json.dumps(s, indent=1))
    v = s["verdict"]
    print(f"gap ({s['thresholds']['primary']}, <= {GAP_THRESHOLD_PCT}% of full matrix): {v['gap']} | "
          f"feasibility (K >= {FEASIBLE_FROM_K}, nobody over 90 min): {v['feasibility']} | complete: {v['complete']}")
    for c, d in s["contractors"].items():
        print(f"\n{c}: full-matrix control {d['control_ride_min']} student-min; smallest K within threshold {d['smallest_k_within_threshold']}")
        print(f"  {'setup':14} {'cells':>6} {'%':>5} {'est err':>7} {'bias':>6} {'real':>7} {'gap':>6} {'range':>13} {'planned':>7} {'longest':>7} {'>90':>3} {'real legs':>9}")
        for x in d["cells"]:
            x = {k: ("-" if v is None else v) for k, v in x.items()}
            rng = f"{x['gap_range'][0]}..{x['gap_range'][1]}" if x["gap_range"] != "-" else "-"
            print(f"  {x['setup']:14} {x['cells_queried']:>6} {x['cells_pct']:>5} {x['est_abs_err_pct']:>7} {x['est_bias_pct']:>6} "
                  f"{x['ride_min']:>7} {x['gap_pct']:>6} {rng:>13} {x['planned_ride_min']:>7} {x['longest_ride_min']:>7} {x['runs_over_90']:>3} {x['legs_real_pct']:>9}")
    print(f"\nwrote {out_dir / 'summary.json'}")


# ---------------------------------------------------------------- main

FIRST = ["key", "setup", "status", "cells_queried", "cells_pct", "total_student_ride_min", "longest_ride_min",
         "stops_over_90_min", "est_abs_err_pct", "legs_real_pct"]


def order_row(row):
    """The hub's generic table shows the first 10 fields, so put the ones that matter first."""
    return {**{k: row[k] for k in FIRST if k in row}, **{k: v for k, v in row.items() if k not in FIRST}}


def machine_info():
    info = {"host": platform.node(), "kernel": platform.release(), "python": platform.python_version(), "cpus": os.cpu_count()}
    try:
        info["cpu"] = next(l.split(":", 1)[1].strip() for l in Path("/proc/cpuinfo").read_text().splitlines() if l.startswith("model name"))
    except (OSError, StopIteration):
        pass
    try:
        import ortools
        info["ortools"] = ortools.__version__
    except ImportError:
        info["ortools"] = "missing"
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="K=10 and full only, 5 s, 1 repeat, to test the pipeline")
    ap.add_argument("--summarize", action="store_true")
    ap.add_argument("--workers", type=int, default=1, help="runs in parallel (one solver thread each; keep <= physical cores)")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--code-version", default=None)
    args = ap.parse_args()
    out_dir = args.out_dir or ROOT / "results" / ("query-budget-quick" if args.quick else "query-budget")
    if args.summarize:
        summarize(out_dir)
        return
    try:
        import ortools  # noqa: F401
    except ImportError:
        sys.exit("OR-Tools is not installed in this Python. In the hub: Run & publish, Check setup, then Install.")
    ks, repeats, budget = ([10], 1, 5) if args.quick else (KS, REPEATS, BUDGET_S)
    (out_dir / "runs").mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "meta.json"
    old_meta = json.loads(meta_path.read_text()) if meta_path.exists() else None
    if old_meta is None or old_meta.get("machine", {}).get("ortools") == "missing":
        meta_path.write_text(json.dumps({"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                         "machine": machine_info(), "setup": "unlimited", "budget_s": budget, "ks": ks,
                                         "estimators": ESTIMATORS, "repeats": repeats, "workers": args.workers,
                                         "code_version": args.code_version}, indent=1))
    runs_path = out_dir / "runs.jsonl"
    latest = {}
    if runs_path.exists():
        for l in runs_path.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                latest[r["key"]] = r["status"]
    done = {k for k, s in latest.items() if s == "ok"}
    jobs = [j for j in plan(CONTRACTORS, ks, ESTIMATORS, repeats) if j["key"] not in done]
    print(f"{len(done)} runs already done, {len(jobs)} to go, about {len(jobs) * budget / args.workers / 60:.0f} min")
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, j, out_dir, budget): j for j in jobs}
        for i, (f, j) in enumerate(futures.items(), 1):
            try:
                row = f.result()
            except Exception as exc:                  # keep going; the row records the failure
                row = {**j, "status": "failed", "error": repr(exc)[:300],
                       "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            row["code_version"] = args.code_version
            row = order_row(row)
            with open(runs_path, "a") as fh:
                fh.write(json.dumps(row) + "\n")
            print(f"[{i}/{len(jobs)}] {row['key']}: {row['status']}"
                  + (f", {row['total_student_ride_min']} real student-min, {row['cells_queried']} cells" if row["status"] == "ok" else ""),
                  flush=True)
    summarize(out_dir)


if __name__ == "__main__":
    main()
