"""Time-budget experiment: how much route quality do free-tier limits cost?

    python research/run_budget.py --check        # confirm the limits really apply, then stop
    python research/run_budget.py --quick        # pipeline test (about 3 min), written to results/budget-quick/
    python research/run_budget.py                # full experiment (about 4.5 h), resumable
    python research/run_budget.py --summarize    # rebuild the summary from finished runs

Runs research/optimize.py once per (contractor, setup, search budget, repeat):
- limited:   systemd cgroup scope with MemoryMax=512M, MemorySwapMax=0, CPUQuota=10%
             (0.1 CPU and 512 MB, as on Render's free tier; same kernel limits Docker would set)
- unlimited: the same command with no limits
plus one 30-minute unlimited reference run per contractor. Each finished run is one line in
runs.jsonl and is skipped on the next start, so stopping the script loses only the run in progress.

Pass/fail thresholds are fixed here and in LOGBOOK.md before any run (2026-11-04).
Linux (WSL) only, because the limits come from systemd. Research only: no Django, no website, no database.
"""
import argparse
import json
import os
import platform
import signal
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OPTIMIZE = ROOT / "optimize.py"
CONTRACTORS = ["Jadoon", "Nadeem"]
BUDGETS = [10, 60, 300, 600]
REPEATS = 3
REFERENCE_S = 1800

LIMITS = {"MemoryMax": "512M", "MemorySwapMax": "0", "CPUQuota": "10%"}
EXPECTED = {"memory.max": "536870912", "memory.swap.max": "0", "cpu.max": "10000 100000"}

# Fixed before the runs (LOGBOOK 2026-11-04). Do not change after results exist.
GAP_BUDGET_S = 60
GAP_THRESHOLD_PCT = 5.0
MEMORY_THRESHOLD_MB = 400


def limit_prefix(use_sudo):
    props = [a for k, v in LIMITS.items() for a in ("-p", f"{k}={v}")]
    if use_sudo:
        user = os.environ.get("SUDO_USER") or os.environ.get("USER") or os.getlogin()
        return ["sudo", "systemd-run", "--scope", "--quiet", *props, "sudo", "-u", user, "--"]
    return ["systemd-run", "--user", "--scope", "--quiet", *props]


def check_limits(use_sudo):
    """Start a scope with the limits and read back what the kernel actually applied."""
    probe = ("p=$(cut -d: -f3 /proc/self/cgroup | tail -n1); "
             "for f in memory.max memory.swap.max cpu.max; do "
             "printf '%s=' $f; cat /sys/fs/cgroup$p/$f 2>/dev/null || echo missing; done")
    try:
        r = subprocess.run(limit_prefix(use_sudo) + ["sh", "-c", probe], capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return {"ok": False, "error": "systemd-run not found: enable systemd in WSL (see README)"}
    found = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    found = {k: v.strip() for k, v in found.items()}
    ok = r.returncode == 0 and all(found.get(k) == v for k, v in EXPECTED.items())
    res = {"ok": ok, "expected": EXPECTED, "found": found}
    if r.returncode != 0:
        res["error"] = (r.stderr or r.stdout).strip()[-500:]
    return res


def plan(contractors, budgets, repeats, reference_s):
    """Repeat-major order: after one pass every cell has a first result."""
    jobs = [dict(contractor=c, setup=s, budget_s=b, repeat=rep)
            for rep in range(1, repeats + 1) for b in budgets for c in contractors
            for s in ("limited", "unlimited")]
    jobs += [dict(contractor=c, setup="reference", budget_s=reference_s, repeat=1) for c in contractors]
    for j in jobs:
        j["key"] = f"{j['contractor']}-{j['setup']}-t{j['budget_s']}-r{j['repeat']}"
    return jobs


def optimize_cmd(job, out_dir, python, use_sudo):
    cmd = [python, str(OPTIMIZE), "--contractor", job["contractor"], "--time-limit", str(job["budget_s"]),
           "--out-dir", str(out_dir / "runs"), "--run-id", job["key"], "--no-html"]
    return limit_prefix(use_sudo) + cmd if job["setup"] == "limited" else cmd


def run_one(job, out_dir, python, use_sudo):
    cmd = optimize_cmd(job, out_dir, python, use_sudo)
    grace = max(180, job["budget_s"] // 2)       # loading and model building are slow at 0.1 CPU
    log_path = out_dir / "logs" / f"{job['key']}.log"
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0, timed_out = time.perf_counter(), False
    with open(log_path, "w") as log:
        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        while True:
            pid, status, ru = os.wait4(p.pid, os.WNOHANG)
            if pid:
                break
            if time.perf_counter() - t0 > job["budget_s"] + grace:
                timed_out = True
                if use_sudo and job["setup"] == "limited":
                    subprocess.run(["sudo", "kill", "-9", f"-{p.pid}"])
                else:
                    os.killpg(p.pid, signal.SIGKILL)
                pid, status, ru = os.wait4(p.pid, 0)
                break
            time.sleep(0.5)
    p.returncode = rc = os.waitstatus_to_exitcode(status)
    wall = time.perf_counter() - t0

    row = {**job, "started_at": started, "returncode": rc, "wall_s": round(wall, 1),
           "child_cpu_s": round(ru.ru_utime + ru.ru_stime, 1), "child_peak_mb": round(ru.ru_maxrss / 1024),
           "log": str(log_path.relative_to(out_dir))}
    result_path = out_dir / "runs" / f"{job['key']}.json"
    log_text = log_path.read_text(errors="replace")
    if timed_out:
        row["status"] = "timeout"
    elif rc != 0:
        if "MemoryError" in log_text or (rc == -9 and job["setup"] == "limited"):
            row["status"] = "killed_memory"
        else:
            row["status"] = "failed"
    elif not result_path.exists():
        row["status"] = "failed"
    else:
        entry = json.loads(result_path.read_text())["contractors"][job["contractor"]]
        opt = entry.get("optimized")
        row["baseline_total_student_ride_min"] = entry["baseline"]["total_student_ride_min"]
        row["solve_wall_s"], row["solve_cpu_s"] = entry["solve_wall_s"], entry["solve_cpu_s"]
        row["peak_mb"] = max(entry["peak_rss_mb"], row["child_peak_mb"])
        if opt is None:
            row["status"] = "no_plan"
        else:
            row["status"] = "ok"
            row.update({k: opt[k] for k in ("total_student_ride_min", "longest_ride_min", "buses_used",
                                            "stops_over_90_min", "bus_driving_min")})
            row["dropped_stops"] = len(opt["dropped_stops"])
            prog = entry["progress"]
            # launch to first valid plan = loading/model time + solver time to first solution
            row["first_plan_s"] = round(wall - entry["solve_wall_s"] + prog[0][0], 1) if prog else None
    return row


def machine_info(python):
    info = {"host": platform.node(), "kernel": platform.release(), "python": platform.python_version(),
            "cpus": os.cpu_count()}
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text()
        info["cpu"] = next(l.split(":", 1)[1].strip() for l in cpuinfo.splitlines() if l.startswith("model name"))
        mem_kb = next(int(l.split()[1]) for l in Path("/proc/meminfo").read_text().splitlines() if l.startswith("MemTotal"))
        info["ram_gb"] = round(mem_kb / 1024 / 1024, 1)
    except (OSError, StopIteration):
        pass
    r = subprocess.run([python, "-c", "import ortools; print(ortools.__version__)"], capture_output=True, text=True)
    info["ortools"] = r.stdout.strip() or "unknown"
    return info


# ---------------------------------------------------------------- summary

def summarize(out_dir):
    summary = build_summary(out_dir)
    if summary is None:
        sys.exit(f"no runs yet in {out_dir}")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    (out_dir / "summary.html").write_text(HTML.replace("__DATA__", json.dumps(summary)))
    v = summary["verdict"]
    print(f"gap at {GAP_BUDGET_S} s (limited, <= {GAP_THRESHOLD_PCT}%): {v['gap']} | "
          f"memory (< {MEMORY_THRESHOLD_MB} MB, none killed): {v['memory']} | complete: {v['complete']}")
    print(f"wrote {out_dir / 'summary.json'} and summary.html")


def build_summary(out_dir):
    """Summary dict of the runs in out_dir, or None if there are none. Also used by the research hub."""
    path = out_dir / "runs.jsonl"
    if not path.exists():
        return None
    latest = {}
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            latest[r["key"]] = r                       # a rerun of a key replaces the earlier row
    rows = list(latest.values())
    meta_path = out_dir / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

    summary = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "meta": meta,
               "thresholds": {"gap_budget_s": GAP_BUDGET_S, "gap_threshold_pct": GAP_THRESHOLD_PCT,
                              "memory_threshold_mb": MEMORY_THRESHOLD_MB},
               "contractors": {}, "verdict": {}}
    gap_pass, mem_peaks, killed = [], [], 0
    for c in sorted({r["contractor"] for r in rows}):
        mine = [r for r in rows if r["contractor"] == c]
        ok = [r for r in mine if r["status"] == "ok"]
        if not ok:
            summary["contractors"][c] = {"cells": [], "note": "no successful runs"}
            continue
        ref = next((r for r in ok if r["setup"] == "reference"), None)
        best = min(r["total_student_ride_min"] for r in ok)
        cells = []
        for setup in ("limited", "unlimited"):
            for b in sorted({r["budget_s"] for r in mine if r["setup"] == setup}):
                rs = [r for r in mine if r["setup"] == setup and r["budget_s"] == b]
                good = [r for r in rs if r["status"] == "ok"]

                def med(k):
                    vals = [r[k] for r in good if r.get(k) is not None]
                    return round(statistics.median(vals), 1) if vals else None
                ride = med("total_student_ride_min")
                cell = {"setup": setup, "budget_s": b, "runs": len(rs), "ok": len(good),
                        "not_ok": sorted(r["status"] for r in rs if r["status"] != "ok"),
                        "ride_min": ride, "gap_pct": round((ride - best) / best * 100, 2) if ride is not None else None,
                        "wall_s": med("wall_s"), "cpu_s": med("solve_cpu_s"), "first_plan_s": med("first_plan_s"),
                        "peak_mb": max((r["peak_mb"] for r in good), default=None)}
                cells.append(cell)
                if setup == "limited":
                    mem_peaks += [r["peak_mb"] for r in good]
                    killed += sum(r["status"] == "killed_memory" for r in rs)
                    if b == GAP_BUDGET_S and cell["gap_pct"] is not None:
                        gap_pass.append(cell["gap_pct"] <= GAP_THRESHOLD_PCT)
        baseline = ok[0]["baseline_total_student_ride_min"]
        summary["contractors"][c] = {
            "best_known_ride_min": best, "reference_ride_min": ref["total_student_ride_min"] if ref else None,
            "best_from": next(r["key"] for r in ok if r["total_student_ride_min"] == best),
            "current_routes_ride_min": baseline,
            "current_routes_gap_pct": round((baseline - best) / best * 100, 2), "cells": cells}

    summary["verdict"] = {
        "gap": None if not gap_pass else ("pass" if all(gap_pass) else "fail"),
        "memory": None if not mem_peaks and not killed else
        ("pass" if not killed and max(mem_peaks, default=0) < MEMORY_THRESHOLD_MB else "fail"),
        "limited_peak_mb": max(mem_peaks, default=None), "limited_killed": killed,
        "complete": all(r["status"] == "ok" for r in rows) and len(rows) == len(
            plan(sorted({r["contractor"] for r in rows}), meta.get("budgets_s", BUDGETS),
                 meta.get("repeats", REPEATS), meta.get("reference_s", REFERENCE_S))),
    }
    summary["runs_done"] = len(rows)
    summary["runs_total"] = len(plan(CONTRACTORS, meta.get("budgets_s", BUDGETS), meta.get("repeats", REPEATS),
                                     meta.get("reference_s", REFERENCE_S)))
    summary["rows"] = sorted(rows, key=lambda r: r.get("started_at", ""))
    return summary


HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Time-budget experiment</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1f2937;--muted:#6b7280;--line:#e5e7eb;--good:#047857;--bad:#b91c1c;--lim:#2563eb;--unl:#9333ea}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
header{background:#111827;color:#fff;padding:18px 24px}header h1{margin:0;font-size:20px;font-weight:600}
header p{margin:4px 0 0;color:#cbd5e1;font-size:13px}main{max-width:1100px;margin:0 auto;padding:20px 16px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:16px}
.card,.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.panel{margin-bottom:16px;overflow-x:auto}.panel h2{font-size:15px;margin:0 0 10px}
.k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}.v{font-size:22px;font-weight:600;margin-top:4px}
.pass{color:var(--good)}.fail{color:var(--bad)}table{width:100%;border-collapse:collapse}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}
th{color:var(--muted);font-weight:500;font-size:12px;text-transform:uppercase}.note{color:var(--muted);font-size:12px;margin-top:8px}
svg text{font:12px system-ui,sans-serif;fill:var(--muted)}
</style></head><body>
<header><h1>Time-budget experiment</h1><p id="sub"></p></header><main>
<div class="cards" id="cards"></div><div id="per"></div>
<div class="panel"><h2>Machine</h2><div id="meta"></div></div>
</main><script>
const S=__DATA__,T=S.thresholds,V=S.verdict;
const m=S.meta||{},mc=m.machine||{};
document.getElementById('sub').textContent=`Generated ${S.generated_at} · limited = 512 MB, no swap, 0.1 CPU (systemd cgroups) · synthetic students, free-flow travel times`;
const vcard=(k,v,d)=>`<div class="card"><div class="k">${k}</div><div class="v ${v||''}">${v??'not yet'}</div><div class="note">${d}</div></div>`;
document.getElementById('cards').innerHTML=vcard(`Gap at ${T.gap_budget_s} s, limited`,V.gap,`within ${T.gap_threshold_pct}% of best known, every contractor`)+
 vcard('Memory, limited',V.memory,`peak ${V.limited_peak_mb??'-'} MB (limit ${T.memory_threshold_mb} MB), ${V.limited_killed} killed`)+
 `<div class="card"><div class="k">Experiment</div><div class="v">${V.complete?'complete':'partial'}</div><div class="note">verdicts are final only when complete</div></div>`;
let html='';
for(const [c,d] of Object.entries(S.contractors)){
 if(!d.cells.length){html+=`<div class="panel"><h2>${c}</h2>${d.note}</div>`;continue}
 html+=`<div class="panel"><h2>${c}</h2><svg id="ch-${c}" viewBox="0 0 900 300" width="100%"></svg>
 <div class="note">Gap = median total student ride time over repeats, relative to the best plan found by any run (${d.best_known_ride_min.toLocaleString()} student-min, from ${d.best_from}). Current hand-made routes: ${d.current_routes_ride_min.toLocaleString()} student-min, ${d.current_routes_gap_pct}% above best. Dashed red line: ${T.gap_threshold_pct}% threshold.</div>
 <table><tr><th>Setup</th><th>Budget</th><th>Runs ok</th><th>Ride (student-min)</th><th>Gap</th><th>First plan</th><th>Wall</th><th>Solver CPU</th><th>Peak MB</th><th>Not ok</th></tr>`+
 d.cells.map(x=>`<tr><td>${x.setup}</td><td>${x.budget_s} s</td><td>${x.ok}/${x.runs}</td><td>${x.ride_min?.toLocaleString()??'-'}</td><td>${x.gap_pct??'-'}${x.gap_pct!=null?'%':''}</td><td>${x.first_plan_s??'-'} s</td><td>${x.wall_s??'-'} s</td><td>${x.cpu_s??'-'} s</td><td>${x.peak_mb??'-'}</td><td>${x.not_ok.join(', ')}</td></tr>`).join('')+`</table></div>`}
document.getElementById('per').innerHTML=html;
for(const [c,d] of Object.entries(S.contractors)){
 if(!d.cells.length)continue;const svg=document.getElementById('ch-'+c);
 const W=900,H=300,l=60,r=110,t=20,b=40,bud=[...new Set(d.cells.map(x=>x.budget_s))].sort((a,b)=>a-b);
 const gaps=d.cells.map(x=>x.gap_pct).filter(x=>x!=null),y1=Math.max(T.gap_threshold_pct*1.4,...gaps,1);
 const X=s=>l+(W-l-r)*(bud.length<2?.5:Math.log(s/bud[0])/Math.log(bud[bud.length-1]/bud[0])),Y=g=>t+(H-t-b)*(1-g/y1);
 let g='';for(let i=0;i<=4;i++){const v=y1*i/4;g+=`<line x1="${l}" x2="${W-r}" y1="${Y(v)}" y2="${Y(v)}" stroke="#eef0f3"/><text x="${l-8}" y="${Y(v)+4}" text-anchor="end">${v.toFixed(1)}%</text>`}
 bud.forEach(s=>g+=`<text x="${X(s)}" y="${H-b+18}" text-anchor="middle">${s} s</text>`);
 g+=`<line x1="${l}" x2="${W-r}" y1="${Y(T.gap_threshold_pct)}" y2="${Y(T.gap_threshold_pct)}" stroke="#b91c1c" stroke-dasharray="5 5"/>`;
 for(const [setup,col] of [['limited','var(--lim)'],['unlimited','var(--unl)']]){
  const pts=d.cells.filter(x=>x.setup===setup&&x.gap_pct!=null).map(x=>[X(x.budget_s),Y(x.gap_pct)]);if(!pts.length)continue;
  g+=`<polyline points="${pts.map(p=>p.join(',')).join(' ')}" fill="none" stroke="${col}" stroke-width="2.5"/>`+pts.map(p=>`<circle cx="${p[0]}" cy="${p[1]}" r="4" fill="${col}"/>`).join('');
  const last=pts[pts.length-1];g+=`<text x="${last[0]+10}" y="${last[1]+4}" style="fill:${col}">${setup}</text>`}
 svg.innerHTML=g+`<text x="${l}" y="12">Gap to best known plan (lower is better)</text><text x="${W-r}" y="${H-4}" text-anchor="end">search budget (log scale)</text>`}
const rowsM=[['Host',mc.host],['CPU',mc.cpu],['Cores',mc.cpus],['RAM (GB)',mc.ram_gb],['Kernel',mc.kernel],['Python',mc.python],['OR-Tools',mc.ortools],['Limits applied',m.limits?JSON.stringify(m.limits.found):'-'],['Started',m.started_at]];
document.getElementById('meta').innerHTML='<table>'+rowsM.map(([k,v])=>`<tr><td>${k}</td><td style="text-align:left">${v??'-'}</td></tr>`).join('')+'</table>';
</script></body></html>"""


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="only check that the limits apply")
    ap.add_argument("--quick", action="store_true", help="one 5 s run per cell and a 10 s reference, to test the pipeline")
    ap.add_argument("--summarize", action="store_true", help="only rebuild summary.json and summary.html")
    ap.add_argument("--sudo", action="store_true", help="use 'sudo systemd-run --scope' if the --user scope cannot set limits")
    ap.add_argument("--contractor", action="append", choices=CONTRACTORS, help="limit to one contractor (repeatable)")
    ap.add_argument("--python", default=sys.executable, help="Python that has OR-Tools (default: this one)")
    ap.add_argument("--out-dir", type=Path, default=None)
    args = ap.parse_args()
    out_dir = args.out_dir or ROOT / "results" / ("budget-quick" if args.quick else "budget")

    if args.summarize:
        summarize(out_dir)
        return
    if not sys.platform.startswith("linux"):
        sys.exit("run_budget.py needs Linux (WSL): the limits come from systemd cgroups. See research/README.md.")

    check = check_limits(args.sudo)
    print("limits:", json.dumps(check.get("found")), "OK" if check["ok"] else "NOT APPLIED")
    if not check["ok"]:
        print(check.get("error", ""), file=sys.stderr)
        sys.exit("Limits were not applied, so the limited runs would mean nothing. "
                 "Try --sudo, or see 'Limits without Docker' in research/README.md.")
    if args.check:
        return

    contractors = args.contractor or CONTRACTORS
    budgets, repeats, reference_s = ([5], 1, 10) if args.quick else (BUDGETS, REPEATS, REFERENCE_S)
    for sub in ("runs", "logs"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "meta.json"
    if not meta_path.exists():
        meta_path.write_text(json.dumps({
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "machine": machine_info(args.python), "limits": check, "budgets_s": budgets, "repeats": repeats,
            "reference_s": reference_s, "use_sudo": args.sudo}, indent=1))

    runs_path = out_dir / "runs.jsonl"
    done = set()
    if runs_path.exists():
        done = {json.loads(l)["key"] for l in runs_path.read_text().splitlines() if l.strip()}
    jobs = [j for j in plan(contractors, budgets, repeats, reference_s) if j["key"] not in done]
    total_s = sum(j["budget_s"] for j in jobs)
    print(f"{len(done)} runs already done, {len(jobs)} to go, about {total_s / 3600:.1f} h of search time")

    for i, job in enumerate(jobs, 1):
        print(f"[{i}/{len(jobs)}] {job['key']} ...", end=" ", flush=True)
        row = run_one(job, out_dir, args.python, args.sudo)
        with open(runs_path, "a") as fh:
            fh.write(json.dumps(row) + "\n")
        detail = (f"{row['total_student_ride_min']} student-min, peak {row['peak_mb']} MB"
                  if row["status"] == "ok" else f"see {row['log']}")
        print(f"{row['status']} in {row['wall_s']} s · {detail}")
    summarize(out_dir)


if __name__ == "__main__":
    main()
