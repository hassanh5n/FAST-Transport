"""Robustness checks for the optimization results: traffic and student seed.

    python research/run_robustness.py traffic --quick            # pipeline test, results/traffic-check-quick/
    python research/run_robustness.py traffic --workers 2        # 18 runs, about 10 min on 2 cores, resumable
    python research/run_robustness.py seed --workers 2           # 8 runs, about 5 min on 2 cores, resumable
    python research/run_robustness.py traffic --summarize        # rebuild the summary from finished runs

Both checks answer a caveat on runs B1 and Q1 with re-runs on the saved data (no OSRM, no limits):

traffic  The matrix holds free-flow times. Every travel time is multiplied by 1.0 (control), 1.3 and 1.5;
         stop times are unchanged. Each run plans on the scaled matrix and is scored on the same scaled
         matrix, next to the current routes scored the same way. The control run's plan (made on free-flow
         times) is also re-scored at 1.3 and 1.5, to show what a plan made without traffic does in traffic.
seed     Students are synthetic (seed 2026). Seed 2026 is the frozen dataset, the control. For seeds 2027,
         2028 and 2029 the students are redrawn the same way build_instance.py draws them (each current
         route's bus filled to 65 to 90 percent, spread over its stops with log-normal weights, at least one
         per stop). Routes, stops, buses and the matrix do not change. The frozen dataset is not rewritten.

Search: 60 s unlimited per run (run B1: 60 s unlimited = 600 s at 0.1 CPU in plan quality).
Pass/fail thresholds are fixed here and in LOGBOOK.md (2026-11-10) before any run. Do not change after results exist.
Research only: no Django, no website, no database.
"""
import argparse
import json
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from run_query_budget import CONTRACTORS, load, machine_info  # noqa: E402  (stdlib only at import time)

BUDGET_S = 60
FACTORS = [1.0, 1.3, 1.5]          # traffic: multiplier on every travel time
TRAFFIC_REPEATS = 3
FROZEN_SEED = 2026                 # the dataset's own seed: control, students read from the frozen file
NEW_SEEDS = [2027, 2028, 2029]
LOAD_FACTOR = (0.65, 0.90)         # same as build_instance.py
STOP_WEIGHT_SIGMA = 0.6            # same as build_instance.py

# Fixed before the runs (LOGBOOK 2026-11-10). Do not change after results exist. Judged on the worst run.
JUDGED_FACTOR = 1.5                # traffic thresholds are judged at the heaviest traffic
MIN_IMPROVEMENT_PCT = 15.0         # optimized plan at least 15% below the current routes, same times and students
# Feasibility: no dropped stop and no student over 90 min in any judged run.

CHECKS = {"traffic": "traffic-check", "seed": "seed-check"}


def scaled(T, factor):
    return [[int(round(x * factor)) for x in row] for row in T]


def redraw_students(d, contractor, seed):
    """Students per node for another seed: the build_instance.py draw, over the frozen current routes."""
    rng = random.Random(f"{seed}-{contractor}")
    pos = {n: i for i, n in enumerate(d["nodes"])}
    q = [0] * len(d["nodes"])
    for route in d["inst"]["contractors"][contractor]["baseline_routes"]:
        order = route["stops"]
        riders = round(route["capacity"] * rng.uniform(*LOAD_FACTOR))
        weights = [rng.lognormvariate(0, STOP_WEIGHT_SIGMA) for _ in order]
        counts = [1] * len(order)
        for _ in range(riders - len(order)):
            counts[rng.choices(range(len(order)), weights)[0]] += 1
        for stop, k in zip(order, counts):
            q[pos[stop]] += k
    return q


def plan(check, quick=False):
    """Repeat-major: after one pass every setting has a first result."""
    jobs = []
    if check == "traffic":
        factors, repeats = ([1.0, JUDGED_FACTOR], 1) if quick else (FACTORS, TRAFFIC_REPEATS)
        for rep in range(1, repeats + 1):
            for c in CONTRACTORS:
                for f in factors:
                    jobs.append({"key": f"{c}-x{f}-r{rep}", "check": check, "contractor": c, "factor": f,
                                 "seed": FROZEN_SEED, "repeat": rep, "setup": f"traffic x{f}"})
    else:
        for s in ([FROZEN_SEED, NEW_SEEDS[0]] if quick else [FROZEN_SEED] + NEW_SEEDS):
            for c in CONTRACTORS:
                jobs.append({"key": f"{c}-seed{s}", "check": check, "contractor": c, "factor": 1.0,
                             "seed": s, "repeat": 1, "setup": f"seed {s}" + (" (frozen)" if s == FROZEN_SEED else "")})
    return jobs


def improvement(opt, base):
    return round((base - opt) / base * 100, 2) if base else None


def run_one(job, out_dir, budget_s):
    from optimize import score, solve      # imported here so --summarize works without OR-Tools
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    d = load(job["contractor"])
    q = d["q"] if job["seed"] == FROZEN_SEED else redraw_students(d, job["contractor"], job["seed"])
    T = scaled(d["T"], job["factor"])

    cpu0, wall0 = time.process_time(), time.perf_counter()
    result, progress = solve(T, q, d["caps"], budget_s)
    cpu, wall = time.process_time() - cpu0, time.perf_counter() - wall0
    baseline = score(d["baseline_routes"], T, q)
    row = {**job, "started_at": started, "budget_s": budget_s, "students": sum(q),
           "solve_wall_s": round(wall, 1), "solve_cpu_s": round(cpu, 1),
           "baseline_total_student_ride_min": baseline["total_student_ride_min"],
           "baseline_longest_ride_min": baseline["longest_ride_min"],
           "baseline_stops_over_90_min": baseline["stops_over_90_min"]}
    report = {"run_id": job["key"], "instance": d["inst"]["version"], "time_limit_s": budget_s,
              "model": {"deadline": "08:00", "max_ride_min": 90, "stop_time": "60 s + 5 s/student",
                        "objective": "total student ride time, driving time as tie-breaker",
                        "matrix": f"travel times x{job['factor']}; students seed {job['seed']}"},
              "contractors": {}}
    entry = {"baseline": baseline, "solve_wall_s": row["solve_wall_s"], "solve_cpu_s": row["solve_cpu_s"],
             "peak_rss_mb": None, "progress": progress, "baseline_routes": d["baseline_names"]}
    if result is None:
        row["status"] = "no_plan"
        entry["optimized"] = None
    else:
        opt = score(result["routes"], T, q)
        row.update({"status": "ok", "total_student_ride_min": opt["total_student_ride_min"],
                    "improvement_pct": improvement(opt["total_student_ride_min"], baseline["total_student_ride_min"]),
                    "longest_ride_min": opt["longest_ride_min"], "stops_over_90_min": opt["stops_over_90_min"],
                    "buses_used": opt["buses_used"], "dropped_stops": len(result["dropped"])})
        if job["check"] == "traffic" and job["factor"] == 1.0:
            # what the free-flow plan does when the roads are slower than it assumed
            for f in FACTORS[1:]:
                Tf = scaled(d["T"], f)
                s, b = score(result["routes"], Tf, q), score(d["baseline_routes"], Tf, q)
                row[f"freeflow_plan_x{f}"] = {"total_student_ride_min": s["total_student_ride_min"],
                                              "longest_ride_min": s["longest_ride_min"],
                                              "stops_over_90_min": s["stops_over_90_min"],
                                              "improvement_pct": improvement(s["total_student_ride_min"],
                                                                             b["total_student_ride_min"])}
        opt["dropped_stops"] = [d["nodes"][i] for i in result["dropped"]]
        entry["optimized"] = opt
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
    check, quick = meta.get("check") or rows[0].get("check", "traffic"), bool(meta.get("quick"))
    full = plan(check, quick)
    ok = [r for r in rows if r["status"] == "ok"]

    def judged(r):
        return r["factor"] == JUDGED_FACTOR if check == "traffic" else r["seed"] != FROZEN_SEED

    cells = []
    for c in CONTRACTORS:
        for setup in dict.fromkeys(j["setup"] for j in full if j["contractor"] == c):
            good = [r for r in ok if r["contractor"] == c and r["setup"] == setup]
            if not good:
                continue
            imps = [r["improvement_pct"] for r in good]
            cells.append({"contractor": c, "setup": setup, "runs": len(good), "judged": judged(good[0]),
                          "current_routes_ride_min": good[0]["baseline_total_student_ride_min"],
                          "current_routes_over_90": good[0]["baseline_stops_over_90_min"],
                          "ride_min": round(statistics.median(r["total_student_ride_min"] for r in good)),
                          "improvement_pct": round(statistics.median(imps), 2), "worst_improvement_pct": min(imps),
                          "longest_ride_min": max(r["longest_ride_min"] for r in good),
                          "runs_over_90": sum(r["stops_over_90_min"] > 0 for r in good),
                          "runs_with_dropped_stops": sum(r["dropped_stops"] > 0 for r in good)})
    j_all = [r for r in rows if judged(r)]
    j_ok = [r for r in j_all if r["status"] == "ok"]
    imp = None if not j_ok else ("pass" if min(r["improvement_pct"] for r in j_ok) >= MIN_IMPROVEMENT_PCT else "fail")
    feas = None if not j_all else ("pass" if all(r["status"] == "ok" and r["stops_over_90_min"] == 0
                                                 and r["dropped_stops"] == 0 for r in j_all) else "fail")
    ok_keys = {r["key"] for r in ok}
    budget = meta.get("budget_s", BUDGET_S)
    what = f"x{JUDGED_FACTOR} traffic" if check == "traffic" else "new seeds"
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "meta": meta, "check": check,
            "thresholds": {"judged": what, "min_improvement_pct": MIN_IMPROVEMENT_PCT,
                           "feasibility": "no dropped stop and no student over 90 min", "rule": "worst run"},
            "cells": cells,
            "verdict": {"improvement": imp, "feasibility": feas,
                        "complete": len(ok_keys) >= len(full) and len(ok) == len(rows)},
            "chips": [{"label": f"At least {MIN_IMPROVEMENT_PCT:g}% better than current routes ({what})", "result": imp},
                      {"label": f"Nobody over 90 min, no stop dropped ({what})", "result": feas}],
            "runs_done": len(ok_keys), "runs_total": len(full), "runs_failed": len(rows) - len(ok_keys),
            "remaining_s": round(sum(budget + 5 for j in full if j["key"] not in ok_keys) / max(1, meta.get("workers", 1))),
            "rows": sorted(rows, key=lambda r: r.get("started_at", ""))}


def summarize(out_dir):
    s = build_summary(out_dir)
    if s is None:
        sys.exit(f"no runs yet in {out_dir}")
    (out_dir / "summary.json").write_text(json.dumps(s, indent=1))
    v, t = s["verdict"], s["thresholds"]
    print(f"{s['check']} check, judged on {t['judged']}, {t['rule']}: improvement >= {t['min_improvement_pct']}%: "
          f"{v['improvement']} | {t['feasibility']}: {v['feasibility']} | complete: {v['complete']}")
    print(f"  {'contractor':10} {'setup':20} {'runs':>4} {'current':>8} {'optimized':>9} {'better %':>8} {'worst %':>8} "
          f"{'longest':>7} {'>90':>3} {'dropped':>7}")
    for x in s["cells"]:
        print(f"  {x['contractor']:10} {x['setup']:20} {x['runs']:>4} {x['current_routes_ride_min']:>8} {x['ride_min']:>9} "
              f"{x['improvement_pct']:>8} {x['worst_improvement_pct']:>8} {x['longest_ride_min']:>7} "
              f"{x['runs_over_90']:>3} {x['runs_with_dropped_stops']:>7}")
    print(f"\nwrote {out_dir / 'summary.json'}")


# ---------------------------------------------------------------- main

FIRST = ["key", "setup", "status", "students", "baseline_total_student_ride_min", "total_student_ride_min",
         "improvement_pct", "longest_ride_min", "stops_over_90_min", "dropped_stops"]


def order_row(row):
    """The hub's table shows the first 10 fields, so put the ones that matter first."""
    return {**{k: row[k] for k in FIRST if k in row}, **{k: v for k, v in row.items() if k not in FIRST}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("check", choices=sorted(CHECKS))
    ap.add_argument("--quick", action="store_true", help="two settings, 5 s, 1 repeat, to test the pipeline")
    ap.add_argument("--summarize", action="store_true")
    ap.add_argument("--workers", type=int, default=1, help="runs in parallel (one solver thread each; keep <= physical cores)")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--code-version", default=None)
    args = ap.parse_args()
    out_dir = args.out_dir or ROOT / "results" / (CHECKS[args.check] + ("-quick" if args.quick else ""))
    if args.summarize:
        summarize(out_dir)
        return
    try:
        import ortools  # noqa: F401
    except ImportError:
        sys.exit("OR-Tools is not installed in this Python. In the hub: Run & publish, Check setup, then Install.")
    budget = 5 if args.quick else BUDGET_S
    (out_dir / "runs").mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "meta.json"
    if not meta_path.exists():
        meta_path.write_text(json.dumps({"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                         "machine": machine_info(), "check": args.check, "quick": args.quick,
                                         "setup": "unlimited", "budget_s": budget, "workers": args.workers,
                                         "factors": FACTORS, "seeds": [FROZEN_SEED] + NEW_SEEDS,
                                         "code_version": args.code_version}, indent=1))
    runs_path = out_dir / "runs.jsonl"
    latest = {}
    if runs_path.exists():
        for l in runs_path.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                latest[r["key"]] = r["status"]
    done = {k for k, s in latest.items() if s == "ok"}
    jobs = [j for j in plan(args.check, args.quick) if j["key"] not in done]
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
                  + (f", {row['total_student_ride_min']} student-min, {row['improvement_pct']}% better than current routes"
                     if row["status"] == "ok" else ""), flush=True)
    summarize(out_dir)


if __name__ == "__main__":
    main()
