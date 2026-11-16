"""Build the compact road graph of Karachi from the map file OSRM was built from (work item B1).

    python research/build_graph.py PATH/karachi.osm.pbf
    python research/build_graph.py PATH/map.osm --out data/graph_test --instance data/instance_fall2026_v1.json

Reads the map with ``pyosmium`` (``.osm.pbf`` or ``.osm`` XML), keeps the ways a bus may use, snaps
campus and every stop of the instance to the nearest map node on a kept way and keeps those nodes
in the graph, then writes ``data/graph_karachi_v1/``: one ``.npy`` file per array of
``reroute.roadnet.build_tables`` (separate files, so they can be memory-mapped) and ``meta.json``:

    {"version": "karachi_v1", "source_sha256": ..., "built_at": ..., "nodes": N, "edges": E,
     "segments": S, "speed_factor": 1.0, "keep_points": 312, "far_snaps": [[name, metres], ...]}

Prints the counts and every point snapped more than 200 m from a road. Research only: no Django,
no database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

from reroute.roadnet import EARTH_RADIUS_M, SPEED_KMH, TABLE_KEYS, Way, build_tables, haversine_m

RESEARCH = Path(__file__).resolve().parent
DEFAULT_INSTANCE = RESEARCH / "data" / "instance_fall2026_v1.json"
DEFAULT_OUT = RESEARCH / "data" / "graph_karachi_v1"
VERSION = "karachi_v1"
FAR_SNAP_M = 200.0
NO_ACCESS = frozenset({"no", "private"})
ONEWAY_BY_DEFAULT = frozenset({"motorway", "motorway_link"})


def way_rules(tags: Mapping[str, str]) -> tuple[str, str] | None:
    """``(highway, oneway)`` for a way a bus may use, or ``None`` for a way to skip.

    Skips classes not in ``SPEED_KMH``, ``area=yes``, ``access`` of ``no`` or ``private`` and
    ``motor_vehicle=no``. A roundabout, motorway or motorway link is one-way unless it carries its
    own ``oneway`` tag.
    """
    highway = tags.get("highway", "")
    if highway not in SPEED_KMH:
        return None
    if tags.get("area") == "yes" or tags.get("access") in NO_ACCESS or tags.get("motor_vehicle") == "no":
        return None
    oneway = tags.get("oneway")
    if oneway is None:
        oneway = "yes" if tags.get("junction") == "roundabout" or highway in ONEWAY_BY_DEFAULT else ""
    return highway, oneway


def split_valid(nodes: Sequence[tuple[int, float, float] | None]) -> list[list[tuple[int, float, float]]]:
    """Runs of consecutive nodes with a known location (``None`` marks a node missing from the extract)."""
    runs: list[list[tuple[int, float, float]]] = [[]]
    for n in nodes:
        if n is None:
            runs.append([])
        else:
            runs[-1].append(n)
    return [r for r in runs if len(r) >= 2]


def read_ways(pbf_path: str | Path) -> list[Way]:
    """The ways of the map file a bus may use, with node locations (needs ``pyosmium``)."""
    import osmium                      # offline build only; nothing else in research needs it

    ways: list[Way] = []

    class Handler(osmium.SimpleHandler):
        def way(self, w) -> None:
            rules = way_rules({t.k: t.v for t in w.tags})
            if rules is None:
                return
            nodes = [(n.ref, n.location.lat, n.location.lon) if n.location.valid() else None for n in w.nodes]
            for run in split_valid(nodes):
                ways.append(Way(run, *rules))

    Handler().apply_file(str(pbf_path), locations=True)
    return ways


def nearest_way_nodes(ways: Iterable[Way], points: Sequence[tuple[float, float]]) -> list[tuple[int, float]]:
    """For each ``(lat, lng)`` point, the nearest map node on any of ``ways`` and its distance in metres."""
    from scipy.spatial import cKDTree

    coords: dict[int, tuple[float, float]] = {}
    for w in ways:
        for nid, lat, lng in w.nodes:
            coords.setdefault(nid, (lat, lng))
    if not coords:
        raise ValueError("no road nodes to snap to")
    ids = np.fromiter(coords, dtype=np.int64)
    latlng = np.array(list(coords.values()), dtype=np.float64)
    lat0 = math.radians(float(np.mean([p[0] for p in points]))) if points else 0.0

    def xy(lat, lng):
        return np.column_stack([np.radians(lng) * math.cos(lat0) * EARTH_RADIUS_M, np.radians(lat) * EARTH_RADIUS_M])

    tree = cKDTree(xy(latlng[:, 0], latlng[:, 1]))
    out = []
    for lat, lng in points:
        _, i = tree.query(xy(np.array([lat]), np.array([lng]))[0])
        out.append((int(ids[i]), haversine_m(lat, lng, latlng[i, 0], latlng[i, 1])))
    return out


def instance_points(instance: Mapping) -> list[tuple[str, float, float]]:
    """``(name, lat, lng)`` of campus and every stop of the instance."""
    campus = instance["campus"]
    return [(campus["name"], campus["lat"], campus["lng"])] + [(s["name"], s["lat"], s["lng"])
                                                                for s in instance["stops"]]


def sha256_file(path: str | Path) -> str:
    """SHA-256 of a file, read in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_graph(tables: Mapping[str, np.ndarray], out_dir: str | Path, meta: Mapping) -> None:
    """Write one ``.npy`` per table array and ``meta.json`` (counts filled in from the tables)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for k in TABLE_KEYS:
        np.save(out_dir / f"{k}.npy", tables[k])
    full = {**meta, "nodes": int(len(tables["node_id"])), "edges": int(len(tables["edge_u"])),
            "segments": int(len(tables["seg_from"]))}
    (out_dir / "meta.json").write_text(json.dumps(full, indent=1))


def build(map_path: str | Path, instance: Mapping, out_dir: str | Path, version: str = VERSION) -> dict:
    """Read the map, build and write the graph; returns the metadata written."""
    ways = read_ways(map_path)
    points = instance_points(instance)
    snaps = nearest_way_nodes(ways, [(lat, lng) for _, lat, lng in points])
    tables = build_tables(ways, keep_ids={nid for nid, _ in snaps})
    far = [[name, round(metres, 1)] for (name, _, _), (_, metres) in zip(points, snaps) if metres > FAR_SNAP_M]
    meta = {"version": version, "source_sha256": sha256_file(map_path),
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "speed_factor": 1.0, "keep_points": len(points), "far_snaps": far}
    write_graph(tables, out_dir, meta)
    return json.loads((Path(out_dir) / "meta.json").read_text())


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("map", type=Path, help="the .osm.pbf (or .osm) map file OSRM was built from")
    ap.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--version", default=VERSION, help="graph version written to meta.json")
    args = ap.parse_args(argv)
    if not args.map.exists():
        print(f"map file not found: {args.map}", file=sys.stderr)
        return 2
    instance = json.loads(args.instance.read_text())
    meta = build(args.map, instance, args.out, args.version)
    print(f"graph {meta['version']}: {meta['nodes']:,} nodes, {meta['edges']:,} edges, "
          f"{meta['segments']:,} segments, {meta['keep_points']} points kept as nodes")
    print(f"source sha256 {meta['source_sha256']}")
    if meta["far_snaps"]:
        print(f"points snapped more than {FAR_SNAP_M:.0f} m from a road:")
        for name, metres in meta["far_snaps"]:
            print(f"  {name}: {metres} m")
    else:
        print(f"no point snapped more than {FAR_SNAP_M:.0f} m from a road")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
