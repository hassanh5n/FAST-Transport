"""Query-budget experiment: how few real travel-time lookups still give good routes?

    python3 research/run_query.py --check      # confirm the free-tier limits apply
    python3 research/run_query.py --quick      # pipeline test, about 2 minutes
    python3 research/run_query.py              # full experiment, about 2.7 hours
    python3 research/run_query.py --summarize  # rebuild summary only

Design (fixed in LOGBOOK.md before any run):
- The optimizer plans on real travel times only from each stop to its K nearest stops (by straight line)
  and to campus; every other pair is estimated as a + b x straight-line distance, fitted on the real ones.
- K = 5, 10, 20, 40, and full (every pair real). Plans are always scored on the full real matrix.
- Free-tier limits (512 MB, no swap, 0.1 CPU), 300 s search, 3 repeats, per contractor: 30 runs.
- Uses the same limits, runner and records as run_budget.py. Already finished runs are skipped.
"""
import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import run_budget as rb

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "query"
KS = [5, 10, 20, 40, 0]                      # 0 = full real matrix
BUDGET_S, REPEATS = 300, 3
# Fixed before the runs (LOGBOOK 2026-11-09). Do not change after results exist.
GAP_THRESHOLD_PCT = 2.0                       # vs the full-matrix plan, same setup and budget


def k_label(k):
    return "full" if k == 0 else f"k{k}"


def plan(contractors, ks, repeats, budget):
    jobs = [dict(contractor=c, setup="limited", budget_s=budget, repeat=r, k=k)
            for r in range(1, repeats + 1) for k in ks for c in contractors]
    for j in jobs:
        j["key"] = f"{j['contractor']}-{k_label(j['k'])}-t{j['budget_s']}-r{j['repeat']}"
    return jobs


def optimize_cmd(job, out_dir, python, use_sudo):
    cmd = [python, str(rb.OPTIMIZE), "--contractor", job["contractor"], "--time-limit", str(job["budget_s"]),
           "--k", str(job["k"]), "--out-dir", str(out_dir / "runs"), "--run-id", job["key"], "--no-html"]
    return rb.limit_prefix(use_sudo) + cmd


rb.optimize_cmd = optimize_cmd                # run_budget.run_one builds its command through this


def summarize(out_dir):
    rows = [json.loads(l) for l in (out_dir / "runs.jsonl").read_text().splitlines() if l.strip()]
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "threshold_gap_pct": GAP_THRESHOLD_PCT, "budget_s": BUDGET_S, "contractors": {}}
    for c in sorted({r["contractor"] for r in rows}):
        cells = []
        for k in KS:
            rs = [r for r in rows if r["contractor"] == c and r["k"] == k]
            ok = [r for r in rs if r["status"] == "ok"]
            if not rs:
                continue
            info = {}
            for r in ok:
                f = out_dir / "runs" / f"{r['key']}.json"
                info = json.loads(f.read_text())["contractors"][c].get("matrix", {})
            med = lambda key: statistics.median(r[key] for r in ok) if ok else None
            cells.append({"k": k_label(k), "runs": len(rs), "ok": len(ok),
                          "not_ok": [r["status"] for r in rs if r["status"] != "ok"],
                          "queried_cells": info.get("queried_cells"), "query_share": info.get("query_share"),
                          "estimate_median_abs_error_pct": info.get("estimate_median_abs_error_pct"),
                          "ride_min": med("total_student_ride_min"), "longest_ride_min": med("longest_ride_min"),
                          "stops_over_90_min": max((r["stops_over_90_min"] for r in ok), default=None),
                          "peak_mb": max((r["peak_mb"] for r in ok), default=None)})
        full = next((x for x in cells if x["k"] == "full" and x["ride_min"]), None)
        for x in cells:
            x["gap_pct"] = round(100 * (x["ride_min"] - full["ride_min"]) / full["ride_min"], 2) \
                if full and x["ride_min"] else None
        passing = [x for x in cells if x["k"] != "full" and x["gap_pct"] is not None
                   and x["gap_pct"] <= GAP_THRESHOLD_PCT and x["ok"] == x["runs"]]
        smallest = min(passing, key=lambda x: x["queried_cells"]) if passing else None
        summary["contractors"][c] = {"cells": cells, "smallest_passing_k": smallest and smallest["k"],
                                     "queries_saved_pct": smallest and round(100 * (1 - smallest["query_share"]), 1)}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    for c, s in summary["contractors"].items():
        print(f"\n{c}: smallest K within {GAP_THRESHOLD_PCT}% of full = {s['smallest_passing_k']} "
              f"(saves {s['queries_saved_pct']}% of lookups)")
        print(f"  {'K':>5} {'lookups':>8} {'share':>6} {'est.err':>7} {'ride':>7} {'gap':>6} {'longest':>7} ok")
        for x in s["cells"]:
            print(f"  {x['k']:>5} {x['queried_cells'] or '-':>8} {x['query_share'] or '-':>6} "
                  f"{x['estimate_median_abs_error_pct'] if x['estimate_median_abs_error_pct'] is not None else '-':>7} "
                  f"{x['ride_min'] or '-':>7} {x['gap_pct'] if x['gap_pct'] is not None else '-':>6} "
                  f"{x['longest_ride_min'] or '-':>7} {x['ok']}/{x['runs']}")
    print(f"\nwrote {out_dir / 'summary.json'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--quick", action="store_true", help="one 10 s run per K and contractor")
    ap.add_argument("--summarize", action="store_true")
    ap.add_argument("--sudo", action="store_true")
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()

    out = OUT.with_name("query-quick") if args.quick else OUT
    if args.check:
        print(json.dumps(rb.check_limits(args.sudo), indent=1))
        return
    if args.summarize:
        summarize(out)
        return
    limits = rb.check_limits(args.sudo)
    if not limits["ok"]:
        sys.exit(f"Limits did not apply, nothing run: {json.dumps(limits)}")
    (out / "runs").mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(exist_ok=True)
    meta = {"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "machine": rb.machine_info(args.python), "limits": limits, "ks": KS,
            "budget_s": 10 if args.quick else BUDGET_S, "repeats": 1 if args.quick else REPEATS}
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    jobs = plan(sorted(rb.CONTRACTORS), KS, meta["repeats"], meta["budget_s"])
    done = set()
    if (out / "runs.jsonl").exists():
        done = {json.loads(l)["key"] for l in (out / "runs.jsonl").read_text().splitlines()
                if l.strip() and json.loads(l)["status"] == "ok"}
    todo = [j for j in jobs if j["key"] not in done]
    print(f"{len(jobs)} runs planned, {len(done)} already done, {len(todo)} to go")
    for n, job in enumerate(todo, 1):
        print(f"[{n}/{len(todo)}] {job['key']} ...", end=" ", flush=True)
        row = rb.run_one(job, out, args.python, args.sudo)
        with open(out / "runs.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")
        print(f"{row['status']} in {row['wall_s']} s" +
              (f" · {row['total_student_ride_min']} student-min, peak {row['peak_mb']} MB"
               if row["status"] == "ok" else ""))
    summarize(out)


if __name__ == "__main__":
    main()
