"""Optimizer scaling run: how build time, memory and plan quality grow with stops and buses.

    python research/run_scale.py --quick       # pipeline test: Nadeem, 10 s, both lookups, results/optimizer-scale-quick/
    python research/run_scale.py               # the run: 4 instances x 2 lookups x 300 s, about 40 min, resumable
    python research/run_scale.py --summarize   # print the table of finished runs
    python research/run_scale.py --instances Nadeem-doubled --out-dir results/optimizer-scale-extra

Instances (scale_instances.py): Jadoon (171 stops), Nadeem (143), All (311 stops, both fleets) and
All-doubled (622: every stop and bus twice, each copy 30 s from its original, so it tests model size,
not geography). "<name>-doubled" works for any instance name. All and All-doubled need the combined
matrix data/matrix_fall2026_v1_all.json (offline-builders plan); without it they are recorded as
"skipped" and run on the next start once the file exists.

Lookups (optimize.py: solve): "callback" (Python answers each arc; every recorded result used it) and
"matrix" (tables handed to OR-Tools once). Each run is a fresh process, so peak memory is per run.
The worker is started as `python <path>/research/run_scale.py --worker ...`, not through multiprocessing,
so its command line names the script: the hub's Stop (pkill -f research/run_scale.py) ends it with the
parent, and the hub's busy check (pgrep) sees it.
No resource limits and no pass/fail threshold: this run reports curves. The model is optimize.py's.

Row fields (runs.jsonl): build_s is model construction (solve before SolveWithParameters);
first_plan_s is from entering solve to the first plan; ride_Ns is the best plan's solver cost after
N s of search in approx. student-minutes (cost / 60, which includes the driving tie-breaker and
10**9 per dropped stop), None if no plan yet or N is past the budget, and at N = budget the cost of
the returned plan (OR-Tools may find it a little after the nominal limit); improvements counts new
best plans, the first included; solve_cpu_s is the CPU time of the whole solve call. The number of students does not change the model's size; stops and
buses do.
Research only: no Django, no website, no database.
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from run_query_budget import machine_info  # noqa: E402  (stdlib only at import time)
from scale_instances import combined_instance, contractor_instance, doubled_instance  # noqa: E402

DATA = ROOT / "data"
INSTANCE_FILE = DATA / "instance_fall2026_v1.json"
MATRIX_FILE = DATA / "matrix_fall2026_v1.json"
MATRIX_ALL_FILE = DATA / "matrix_fall2026_v1_all.json"
INSTANCES = ["Jadoon", "Nadeem", "All", "All-doubled"]
QUICK_INSTANCES = ["Nadeem"]
LOOKUPS = ["callback", "matrix"]
BUDGET_S, QUICK_BUDGET_S = 300, 10
CHECKPOINTS_S = [10, 60, 300]       # ride_10s, ride_60s, ride_300s
GAP_S = 30.0                        # doubled instance: a copy is this many seconds from its original
DOUBLED = "-doubled"

# The hub's generic table shows the first 10 scalar fields, so the measured ones come first.
FIRST = ["key", "setup", "status", "stops", "buses", "build_s", "first_plan_s", "peak_mb", "ride_10s", "ride_300s"]


def plan(instances, lookups=LOOKUPS, quick=False):
    """Instance-major job list; keys are unique per output folder and between the quick and full runs."""
    prefix = "scale-quick" if quick else "scale"
    return [{"key": f"{prefix}-{i}-{lk}", "setup": f"{i} {lk}", "instance": i, "lookup": lk, "repeat": 1}
            for i in instances for lk in lookups]


def base_name(name):
    """The instance a name is built from: "All-doubled" -> "All"; a plain name is its own base."""
    while name.endswith(DOUBLED):
        name = name[:-len(DOUBLED)]
    return name


def needs_combined(name):
    return base_name(name) == "All"


def build_instance(name, inst, mat, mat_all=None, gap_s=GAP_S):
    """Instance by name: a contractor, "All", or any of these followed by one or more "-doubled"."""
    if name.endswith(DOUBLED):
        return doubled_instance(build_instance(name[:-len(DOUBLED)], inst, mat, mat_all, gap_s), gap_s)
    if name == "All":
        if mat_all is None:
            raise FileNotFoundError(f"{MATRIX_ALL_FILE.name} is needed for {name}")
        return combined_instance(inst, mat_all)
    if name not in mat["contractors"]:
        raise KeyError(f"unknown instance {name!r}")
    return contractor_instance(inst, mat, name)


def best_by(progress, seconds):
    """Best (lowest) solver cost among plans found within the first `seconds` of search, else None.
    progress lists every plan the search accepts, not only improvements, hence the minimum."""
    costs = [c for t, c in progress if t <= seconds]
    return min(costs) if costs else None


def improvements(progress):
    """How many new best plans the search found, the first plan included ([600, 540, 570, 480] -> 3)."""
    count, best = 0, None
    for _, c in progress:
        if best is None or c < best:
            count, best = count + 1, c
    return count


def to_min(cost):
    return None if cost is None else round(cost / 60)


def checkpoint_fields(progress, budget_s):
    """ride_<N>s for each checkpoint; None past the budget.

    The checkpoint at the budget takes every plan: OR-Tools runs slightly past its nominal limit, and
    ride_<budget>s must be the cost of the plan the run returns. Costs include the solver's 10**9
    penalty per dropped stop (about 16.7 million per stop after / 60), so a huge value means drops."""
    def at(n):
        return to_min(best_by(progress, n if n < budget_s else float("inf")))
    return {f"ride_{n}s": at(n) if n <= budget_s else None for n in CHECKPOINTS_S}


def run_one(job, out_dir, budget_s):
    """One run in a fresh process: build the instance, solve under one lookup, measure, write the run file."""
    from optimize import peak_memory_mb, score, solve      # OR-Tools only in the worker
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inst = json.loads(INSTANCE_FILE.read_text())
    mat = json.loads(MATRIX_FILE.read_text())
    mat_all = json.loads(MATRIX_ALL_FILE.read_text()) if needs_combined(job["instance"]) else None
    I = build_instance(job["instance"], inst, mat, mat_all)
    T, q, caps = I["T"], I["q"], I["capacities"]

    cpu0, wall0 = time.process_time(), time.perf_counter()
    result, progress, times = solve(T, q, caps, budget_s, lookup=job["lookup"], timings=True)
    cpu, wall = time.process_time() - cpu0, time.perf_counter() - wall0
    row = {**job, "status": "ok" if result is not None else "no_plan", "stops": len(T) - 1, "buses": len(caps),
           "build_s": times["build_s"], "first_plan_s": times["first_plan_s"], "peak_mb": peak_memory_mb(),
           **checkpoint_fields(progress, budget_s), "improvements": improvements(progress),
           "solve_cpu_s": round(cpu, 1), "solve_wall_s": round(wall, 1), "budget_s": budget_s,
           "students": sum(q), "started_at": started}
    if result is not None:
        opt = score(result["routes"], T, q)
        row.update({"total_student_ride_min": opt["total_student_ride_min"],
                    "longest_ride_min": opt["longest_ride_min"], "dropped_stops": len(result["dropped"])})
        if "baseline_routes" in I:            # the hub's run pages need the current routes to compare with
            write_run_file(out_dir, job, I, result, progress, opt, row, inst)
    return row


def write_run_file(out_dir, job, I, result, progress, opt, row, inst):
    """Per-run JSON in optimize.py's format, so the hub lists the run under Runs (contractor instances only:
    the combined and doubled instances have no current routes to compare with, and copies have no map point)."""
    from optimize import score
    nodes = I["nodes"]
    opt = {**opt, "dropped_stops": [nodes[i] for i in result["dropped"]]}
    entry = {"baseline": score(I["baseline_routes"], I["T"], I["q"]), "optimized": opt,
             "solve_wall_s": row["solve_wall_s"], "solve_cpu_s": row["solve_cpu_s"], "peak_rss_mb": row["peak_mb"],
             "progress": progress, "routes": [[nodes[i] for i in r] for r in result["routes"] if r],
             "baseline_routes": [[nodes[i] for i in r] for r in I["baseline_routes"]]}
    report = {"run_id": job["key"], "instance": inst["version"], "time_limit_s": row["budget_s"],
              "model": {"deadline": "08:00", "max_ride_min": 90, "stop_time": "60 s + 5 s/student",
                        "objective": "total student ride time, driving time as tie-breaker",
                        "lookup": job["lookup"]},
              "contractors": {I["name"]: entry}}
    (out_dir / "runs" / f"{job['key']}.json").write_text(json.dumps(report, indent=1))


SCRIPT = Path(__file__).resolve()


def worker_command(job, out_dir, budget_s, result_path):
    """argv of the worker process for one job. It names this script by its full path, so
    `pkill -f research/run_scale.py` and `pgrep -af research/...py` (hub/serve.py) match it."""
    return [sys.executable, str(SCRIPT), "--worker", json.dumps(job), "--out-dir", str(out_dir),
            "--budget", str(budget_s), "--result-file", str(result_path)]


def start_worker(job, out_dir, budget_s, result_path):
    """Start the worker for one job; it writes its row (or {"error": ...}) as JSON to result_path."""
    return subprocess.Popen(worker_command(job, out_dir, budget_s, result_path), cwd=str(ROOT))


def run_in_worker(job, out_dir, budget_s):
    """Run one job in a fresh worker process and return its row; a crash becomes a 'failed' row."""
    with tempfile.TemporaryDirectory(prefix="run_scale_") as tmp:
        result_path = Path(tmp) / "row.json"
        proc = start_worker(job, out_dir, budget_s, result_path)
        try:
            code = proc.wait()
        finally:
            if proc.poll() is None:             # interrupted (Ctrl+C): do not leave the solve behind
                proc.kill()
        out = json.loads(result_path.read_text()) if result_path.exists() else None
    if out is not None and "error" not in out:
        return out
    error = out["error"] if out is not None else f"worker exited with code {code} and wrote no result"
    return {**job, "status": "failed", "error": error[:300],
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def worker_main(job, out_dir, budget_s, result_path):
    """Body of `run_scale.py --worker`: run one job and write its row, or the error, to result_path."""
    try:
        out = run_one(job, out_dir, budget_s)
    except Exception as exc:                    # the parent records the failure and keeps going
        out = {"error": repr(exc)}
    result_path.write_text(json.dumps(out))


def order_row(row):
    """FIRST fields first, present (None) even on skipped or failed rows: the hub takes its columns
    from the rows in time order, and skipped rows are written before any run finishes."""
    return {**{k: row.get(k) for k in FIRST}, **{k: v for k, v in row.items() if k not in FIRST}}


def read_rows(out_dir):
    """Latest row per key from runs.jsonl."""
    path, latest = out_dir / "runs.jsonl", {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                latest[r["key"]] = r
    return latest


def append_row(out_dir, row, code_version):
    row = order_row({**row, "code_version": code_version})
    with open(out_dir / "runs.jsonl", "a") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def summarize(out_dir):
    rows = read_rows(out_dir)
    if not rows:
        sys.exit(f"no runs yet in {out_dir}")
    cols = ["setup", "status", "stops", "buses", "build_s", "first_plan_s", "peak_mb",
            "ride_10s", "ride_60s", "ride_300s", "improvements", "solve_cpu_s"]
    print("  ".join(f"{c:>12}" for c in cols))
    for r in sorted(rows.values(), key=lambda r: (r.get("stops") or 0, r["setup"])):
        print("  ".join(f"{'-' if r.get(c) is None else r[c]!s:>12}" for c in cols))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="Nadeem only, 10 s, both lookups, to test the pipeline")
    ap.add_argument("--summarize", action="store_true", help="only print the table of finished runs")
    ap.add_argument("--instances", default=None,
                    help="comma-separated instance names (default: the four of the run, or Nadeem with --quick)")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--code-version", default=None)
    ap.add_argument("--worker", default=None, help=argparse.SUPPRESS)       # internal: one job as JSON
    ap.add_argument("--budget", type=int, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--result-file", type=Path, default=None, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.worker:
        worker_main(json.loads(args.worker), args.out_dir, args.budget, args.result_file)
        return
    out_dir = args.out_dir or ROOT / "results" / ("optimizer-scale-quick" if args.quick else "optimizer-scale")
    if args.summarize:
        summarize(out_dir)
        return
    try:
        import ortools  # noqa: F401
    except ImportError:
        sys.exit("OR-Tools is not installed in this Python. In the hub: Run & publish, Check setup, then Install.")

    instances = args.instances.split(",") if args.instances else (QUICK_INSTANCES if args.quick else INSTANCES)
    mat = json.loads(MATRIX_FILE.read_text())
    unknown = [i for i in instances if not needs_combined(i) and base_name(i) not in mat["contractors"]]
    if unknown:
        sys.exit(f"unknown instances: {', '.join(unknown)}")
    budget = QUICK_BUDGET_S if args.quick else BUDGET_S
    jobs = plan(instances, quick=args.quick)
    (out_dir / "runs").mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "meta.json"
    if not meta_path.exists():
        meta_path.write_text(json.dumps({"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                         "machine": machine_info(), "quick": args.quick, "setup": "unlimited",
                                         "budget_s": budget, "instances": instances, "lookups": LOOKUPS,
                                         "doubled_gap_s": GAP_S, "runs_total": len(jobs),
                                         "code_version": args.code_version}, indent=1))

    done = {k for k, r in read_rows(out_dir).items() if r["status"] == "ok"}
    todo = [j for j in jobs if j["key"] not in done]
    have_all = MATRIX_ALL_FILE.exists()
    runnable = []
    for j in todo:
        if needs_combined(j["instance"]) and not have_all:
            append_row(out_dir, {**j, "status": "skipped", "reason": f"missing data/{MATRIX_ALL_FILE.name}",
                                 "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                       args.code_version)
            print(f"{j['key']}: skipped, data/{MATRIX_ALL_FILE.name} not found")
        else:
            runnable.append(j)
    print(f"{len(done)} runs already done, {len(runnable)} to go, about {len(runnable) * (budget + 5) / 60:.1f} min")

    # one run per fresh process, one at a time, so peak memory is per run
    for i, j in enumerate(runnable, 1):
        row = run_in_worker(j, out_dir, budget)
        row = append_row(out_dir, row, args.code_version)
        print(f"[{i}/{len(runnable)}] {row['key']}: {row['status']}"
              + (f", build {row['build_s']} s, peak {row['peak_mb']} MB, ride at {budget} s "
                 f"{row.get(f'ride_{budget}s')} (approx. student-min)" if row["status"] == "ok" else ""), flush=True)
    summarize(out_dir)


if __name__ == "__main__":
    main()
