"""Build the travel-time matrices for the research instance from a local OSRM server.

    python3 research/build_matrix.py              # OSRM at http://localhost:5000
    OSRM_URL=http://host:5000 python3 research/build_matrix.py
    python3 research/build_matrix.py --combined   # one table over all 311 stops (work item A5)

Standard library only; it never touches the website, its settings or its database.
By default writes research/data/matrix_fall2026_v1.json with, per contractor:
  nodes          node 0 = campus, then the contractor's stops in instance order
  durations_s    driving time from row node to column node, free-flow, no traffic
  distances_m    driving distance for the same pairs
  snap_m         how far each point was moved to reach the nearest road
  calls, cells   OSRM requests made and matrix cells requested (the query budget)

With --combined it writes research/data/matrix_fall2026_v1_all.json in the same shape, under the single
key contractors["All"]: campus, then all 311 stops in instance order. It then checks every pair of the
saved per-contractor matrix against the combined table (within 0.1 s); a difference means the map build
is not the one of run N1, and both matrices must be rebuilt as version 2.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

OSRM = os.environ.get("OSRM_URL", "http://localhost:5000").rstrip("/")
SNAP_WARN_M = 200
CHECK_TOLERANCE_S = 0.1
DATA = Path(__file__).resolve().parent / "data"
SAVED_MATRIX = DATA / "matrix_fall2026_v1.json"
COMBINED_MATRIX = DATA / "matrix_fall2026_v1_all.json"


def table(points, osrm: str = OSRM) -> dict:
    """One OSRM table request (durations and distances) over `(lat, lng)` points."""
    path = ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in points)
    url = f"{osrm}/table/v1/driving/{path}?annotations=duration,distance"
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            body = json.load(response)
    except urllib.error.HTTPError as err:
        with err:
            raw = err.read()
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            raise SystemExit(f"OSRM at {osrm} answered HTTP {err.code} with a non-JSON page; "
                             f"check that OSRM_URL points at the car server") from None
    except (urllib.error.URLError, OSError) as err:
        raise SystemExit(f"cannot reach OSRM at {osrm} ({getattr(err, 'reason', err)}); "
                         f"start the untouched car server or set OSRM_URL")
    if body.get("code") != "Ok":
        raise SystemExit(f"OSRM refused the request: {body.get('code')} {body.get('message', '')}")
    return body


def contractor_points(instance: dict, contractor: str) -> tuple[list[str], list[tuple[float, float]]]:
    """Node names and points for one contractor: campus, then its stops in instance order."""
    by_name = {s["name"]: s for s in instance["stops"]}
    names = instance["contractors"][contractor]["stops"]
    campus = instance["campus"]
    return (["CAMPUS"] + list(names),
            [(campus["lat"], campus["lng"])] + [(by_name[n]["lat"], by_name[n]["lng"]) for n in names])


def combined_points(instance: dict) -> tuple[list[str], list[tuple[float, float]]]:
    """Node names and points over every stop: campus, then all stops in instance order."""
    campus = instance["campus"]
    return (["CAMPUS"] + [s["name"] for s in instance["stops"]],
            [(campus["lat"], campus["lng"])] + [(s["lat"], s["lng"]) for s in instance["stops"]])


def matrix_entry(nodes: list[str], body: dict) -> dict:
    """The stored matrix for `nodes` from one OSRM table answer (unreachable pairs stay `None`)."""
    durations, distances = body["durations"], body["distances"]
    snap = [round(w["distance"], 1) for w in body["sources"]]
    unreachable = [(nodes[i], nodes[j]) for i, row in enumerate(durations)
                   for j, v in enumerate(row) if v is None]
    far_snaps = [(nodes[i], d) for i, d in enumerate(snap) if d > SNAP_WARN_M]
    assert all(durations[i][i] == 0 for i in range(len(nodes))), "diagonal must be zero"
    return {
        "nodes": nodes,
        "durations_s": [[None if v is None else round(v, 1) for v in row] for row in durations],
        "distances_m": [[None if v is None else round(v) for v in row] for row in distances],
        "snap_m": snap, "calls": 1, "cells": len(nodes) ** 2,
        "unreachable_pairs": unreachable, "far_snaps": far_snaps,
    }


def compare_with_saved(combined: dict, saved: dict, tolerance_s: float = CHECK_TOLERANCE_S) -> list[tuple]:
    """Pairs of `saved` whose duration differs from `combined` by more than `tolerance_s`, or whose
    reachability differs, as `(from, to, saved_s, combined_s)`. Raises KeyError for a missing node."""
    at = {name: i for i, name in enumerate(combined["nodes"])}
    cols = [at[name] for name in saved["nodes"]]
    diffs = []
    for a, row in zip(saved["nodes"], saved["durations_s"]):
        crow = combined["durations_s"][at[a]]
        for b, j, s in zip(saved["nodes"], cols, row):
            c = crow[j]
            if (s is None) != (c is None) or (s is not None and abs(s - c) > tolerance_s + 1e-9):
                diffs.append((a, b, s, c))
    return diffs


def write_json(path: Path, data: dict) -> None:
    Path(path).write_text(json.dumps(data))


def build(instance: dict, groups: dict[str, tuple[list[str], list]], osrm: str) -> dict:
    """One table call per group, printed and assembled into the matrix file's content."""
    out = {"instance": instance["version"], "osrm_url": osrm,
           "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "units": {"durations": "seconds", "distances": "metres"}, "contractors": {}}
    for cname, (nodes, points) in groups.items():
        entry = matrix_entry(nodes, table(points, osrm))
        out["contractors"][cname] = entry
        print(f"{cname}: {len(nodes)} x {len(nodes)} matrix, 1 call, "
              f"{len(entry['unreachable_pairs'])} unreachable pairs, "
              f"{len(entry['far_snaps'])} points moved more than {SNAP_WARN_M} m")
        for name, d in entry["far_snaps"]:
            print(f"   check on a map: {name} is {d:.0f} m from the nearest road")
    return out


def check_combined(entry: dict, saved_path: Path) -> int:
    """Print the check of the combined table against the saved matrix; return the number of differences."""
    saved = json.loads(saved_path.read_text(encoding="utf-8"))
    total = 0
    for cname, saved_entry in saved["contractors"].items():
        diffs = compare_with_saved(entry, saved_entry)
        total += len(diffs)
        print(f"check {cname}: {len(saved_entry['nodes']) ** 2} pairs, {len(diffs)} differ by more than "
              f"{CHECK_TOLERANCE_S} s")
        for a, b, s, c in diffs[:10]:
            print(f"   {a} -> {b}: saved {s}, combined {c}")
    if total:
        print("the map build differs from run N1: rebuild both matrices as version 2")
    return total


def main(argv: Sequence[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Travel-time matrices for the research instance from OSRM "
                                            "(server from OSRM_URL, default http://localhost:5000).")
    p.add_argument("--combined", action="store_true",
                   help="one table over campus and all 311 stops, under contractors['All']")
    p.add_argument("--out", type=Path, help="output file (default: the matrix file for the chosen mode)")
    p.add_argument("--no-check", action="store_true",
                   help="with --combined, skip the check against the saved per-contractor matrix")
    args = p.parse_args(argv)

    instance = json.loads((DATA / "instance_fall2026_v1.json").read_text(encoding="utf-8"))
    if args.combined:
        groups = {"All": combined_points(instance)}
    else:
        groups = {c: contractor_points(instance, c) for c in instance["contractors"]}
    out = build(instance, groups, OSRM)
    target = args.out or (COMBINED_MATRIX if args.combined else SAVED_MATRIX)
    write_json(target, out)
    print(f"wrote {target}")
    if args.combined and not args.no_check and SAVED_MATRIX.exists():
        if check_combined(out["contractors"]["All"], SAVED_MATRIX):
            sys.exit(1)


if __name__ == "__main__":
    main()
