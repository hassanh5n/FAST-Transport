"""Build the travel-time matrices for the research instance from a local OSRM server.

    python3 research/build_matrix.py            # OSRM at http://localhost:5000
    OSRM_URL=http://host:5000 python3 research/build_matrix.py

Standard library only; it never touches the website, its settings or its database.
Writes research/data/matrix_fall2026_v1.json with, per contractor:
  nodes          node 0 = campus, then the contractor's stops in instance order
  durations_s    driving time from row node to column node, free-flow, no traffic
  distances_m    driving distance for the same pairs
  snap_m         how far each point was moved to reach the nearest road
  calls, cells   OSRM requests made and matrix cells requested (the query budget)
"""
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OSRM = os.environ.get("OSRM_URL", "http://localhost:5000").rstrip("/")
SNAP_WARN_M = 200
DATA = Path(__file__).resolve().parent / "data"


def table(points):
    path = ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in points)
    url = f"{OSRM}/table/v1/driving/{path}?annotations=duration,distance"
    with urllib.request.urlopen(url, timeout=120) as response:
        body = json.load(response)
    if body.get("code") != "Ok":
        raise SystemExit(f"OSRM refused the request: {body.get('code')} {body.get('message', '')}")
    return body


instance = json.loads((DATA / "instance_fall2026_v1.json").read_text())
by_name = {s["name"]: s for s in instance["stops"]}
campus = instance["campus"]

out = {"instance": instance["version"], "osrm_url": OSRM,
       "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
       "units": {"durations": "seconds", "distances": "metres"}, "contractors": {}}

for cname, c in instance["contractors"].items():
    nodes = ["CAMPUS"] + c["stops"]
    points = [(campus["lat"], campus["lng"])] + [(by_name[n]["lat"], by_name[n]["lng"]) for n in c["stops"]]
    body = table(points)
    durations, distances = body["durations"], body["distances"]
    snap = [round(w["distance"], 1) for w in body["sources"]]

    unreachable = [(nodes[i], nodes[j]) for i, row in enumerate(durations)
                   for j, v in enumerate(row) if v is None]
    far_snaps = [(nodes[i], d) for i, d in enumerate(snap) if d > SNAP_WARN_M]
    assert all(durations[i][i] == 0 for i in range(len(nodes))), "diagonal must be zero"

    out["contractors"][cname] = {
        "nodes": nodes,
        "durations_s": [[None if v is None else round(v, 1) for v in row] for row in durations],
        "distances_m": [[None if v is None else round(v) for v in row] for row in distances],
        "snap_m": snap, "calls": 1, "cells": len(nodes) ** 2,
        "unreachable_pairs": unreachable, "far_snaps": far_snaps,
    }
    print(f"{cname}: {len(nodes)} x {len(nodes)} matrix, 1 call, "
          f"{len(unreachable)} unreachable pairs, {len(far_snaps)} points moved more than {SNAP_WARN_M} m")
    for name, d in far_snaps:
        print(f"   check on a map: {name} is {d:.0f} m from the nearest road")

target = DATA / "matrix_fall2026_v1.json"
target.write_text(json.dumps(out))
print(f"wrote {target}")
