"""Build the research site: one set of pages for everything in research/.

    python research/hub/build_site.py                 # writes research/hub/_site/
    python research/hub/build_site.py --out _site     # used by the GitHub Pages workflow

The same pages are served by the local hub (serve.py, with run buttons) and published
read-only to GitHub Pages. Standard library only. Reads research/ files; writes only to --out.
"""
import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HUB = Path(__file__).resolve().parent
RESEARCH = HUB.parent
WEB = HUB / "web"
sys.path.insert(0, str(RESEARCH))
import run_budget  # noqa: E402  (stdlib only at import time)

EXPERIMENTS = [
    {
        "id": "time-budget",
        "title": "Time-budget experiment",
        "dir": "results/budget",
        "args": [],
        "main": True,
        "question": "On a free-tier server (512 MB, no swap, 0.1 CPU), how close does the optimizer get to the "
                    "best known plan, and how fast?",
        "design": "Each contractor solved at 10, 60, 300 and 600 s, 3 repeats, limited and unlimited, plus one "
                  "30-minute unlimited reference. 50 runs, about 4.5 hours. Limits applied with systemd cgroups in WSL.",
    },
    {
        "id": "time-budget-quick",
        "title": "Pipeline test",
        "dir": "results/budget-quick",
        "args": ["--quick"],
        "main": False,
        "question": "Does the whole experiment pipeline work? 5 s runs, about 1 minute. Not a reported result.",
        "design": "One 5 s run per contractor and setup, plus a 10 s reference.",
    },
]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def logbook_entries(text):
    out = []
    for line in text.splitlines():
        m = re.match(r"^##\s+(\d{4}-\d{2}-\d{2})?:?\s*(.*)$", line)
        if m and not line.startswith("###"):
            out.append({"date": m.group(1), "title": m.group(2).strip()})
    return out


def run_summary(run_id, report, source, row=None):
    contractors = {}
    for c, e in report["contractors"].items():
        b, o = e["baseline"], e.get("optimized") or {}
        delta = None
        if o.get("total_student_ride_min") is not None:
            delta = round((o["total_student_ride_min"] - b["total_student_ride_min"]) / b["total_student_ride_min"] * 100, 1)
        contractors[c] = {"current_ride_min": b["total_student_ride_min"], "ride_min": o.get("total_student_ride_min"),
                          "vs_current_pct": delta, "buses": o.get("buses_used"), "longest_min": o.get("longest_ride_min"),
                          "dropped": len(o.get("dropped_stops", [])), "wall_s": e.get("solve_wall_s"),
                          "cpu_s": e.get("solve_cpu_s"), "peak_mb": e.get("peak_rss_mb")}
    s = {"id": run_id, "source": source, "time_limit_s": report.get("time_limit_s"),
         "contractors": contractors, "file": f"data/runs/{run_id}.json"}
    if row:
        s.update({"setup": row["setup"], "repeat": row["repeat"], "started_at": row.get("started_at"),
                  "peak_mb": row.get("peak_mb")})
    else:
        m = re.match(r"opt-(\d{8})-(\d{6})", run_id)
        if m:
            d, t = m.groups()
            s["started_at"] = f"{d[:4]}-{d[4:6]}-{d[6:]}T{t[:2]}:{t[2:4]}:{t[4:]}+00:00"
        s["setup"] = "development"
    return s


def build(out, git_info=None):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    (out / "data" / "runs").mkdir(parents=True)
    (out / "docs").mkdir()
    (out / "files").mkdir()
    for f in WEB.iterdir():
        shutil.copy2(f, out / f.name)
    (out / ".nojekyll").write_text("")

    inst = read_json(RESEARCH / "data" / "instance_fall2026_v1.json")
    stops = [[s["name"], s["lat"], s["lng"], s["students"], s.get("location")] for s in inst["stops"]]
    contractors = {}
    for c, d in inst["contractors"].items():
        routes = d["baseline_routes"]
        contractors[c] = {"stops": len(d["stops"]) if "stops" in d else sum(1 for s in inst["stops"] if c in s["students"]),
                          "routes": len(routes), "buses": len(d["buses"]),
                          "seats": sum(b["capacity"] for b in d["buses"]),
                          "students": sum(s["students"].get(c, 0) for s in inst["stops"]),
                          "current_routes": routes}
    dataset = {"version": inst["version"], "synthetic": inst.get("students_are_synthetic", True),
               "campus": inst["campus"], "arrival": inst.get("arrival_deadline"), "stops": stops,
               "contractors": contractors}

    runs = []
    for f in sorted((RESEARCH / "results").glob("opt-*.json")):
        report = read_json(f)
        runs.append(run_summary(f.stem, report, "development"))
        shutil.copy2(f, out / "data" / "runs" / f.name)

    experiments = []
    for exp in EXPERIMENTS:
        d = RESEARCH / exp["dir"]
        summary = run_budget.build_summary(d) if (d / "runs.jsonl").exists() else None
        rows = {r["key"]: r for r in (summary or {}).get("rows", [])}
        for f in sorted((d / "runs").glob("*.json")) if (d / "runs").exists() else []:
            report = read_json(f)
            runs.append(run_summary(f.stem, report, exp["id"], rows.get(f.stem)))
            shutil.copy2(f, out / "data" / "runs" / f.name)
        info = {k: exp[k] for k in ("id", "title", "main", "question", "design")}
        if summary is None:
            info["state"] = "not started"
        else:
            info["state"] = "complete" if summary["runs_done"] >= summary["runs_total"] else "partial"
            info["summary"] = summary
        experiments.append(info)

    docs = [{"id": "logbook", "title": "Logbook", "group": "Records", "file": "docs/LOGBOOK.md"},
            {"id": "readme", "title": "How to run (README)", "group": "Records", "file": "docs/README.md"}]
    shutil.copy2(RESEARCH / "LOGBOOK.md", out / "docs" / "LOGBOOK.md")
    shutil.copy2(RESEARCH / "README.md", out / "docs" / "README.md")
    for i, f in enumerate(sorted((RESEARCH / "literature").glob("*.md"))):
        name = f"literature-{i + 1}.md"
        shutil.copy2(f, out / "docs" / name)
        first = next((l.lstrip("# ").strip() for l in f.read_text(encoding="utf-8").splitlines() if l.startswith("#")), f.stem)
        docs.append({"id": f"lit-{i + 1}", "title": first, "group": "Literature", "file": f"docs/{name}"})
    files = []
    for f in sorted(RESEARCH.glob("*.pdf")):
        shutil.copy2(f, out / "files" / f.name)
        files.append({"title": f.stem.replace("_", " "), "file": f"files/{f.name}"})

    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git": git_info or {},
        "project": read_json(HUB / "project.json"),
        "thresholds": {"gap_budget_s": run_budget.GAP_BUDGET_S, "gap_threshold_pct": run_budget.GAP_THRESHOLD_PCT,
                       "memory_threshold_mb": run_budget.MEMORY_THRESHOLD_MB},
        "dataset": dataset,
        "experiments": experiments,
        "runs": sorted(runs, key=lambda r: r.get("started_at") or "", reverse=True),
        "logbook": logbook_entries((RESEARCH / "LOGBOOK.md").read_text(encoding="utf-8")),
        "docs": docs,
        "files": files,
    }
    (out / "data" / "index.json").write_text(json.dumps(index), encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=HUB / "_site")
    ap.add_argument("--commit", default=None, help="commit id shown on the page")
    args = ap.parse_args()
    out = build(args.out, {"commit": args.commit} if args.commit else None)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
