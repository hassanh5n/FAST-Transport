"""One search corridor per current route, and its pre-closure table (work item B3; Tasks 5 and 8).

    python research/build_corridors.py
    python research/build_corridors.py --graph data/graph_karachi_v1 --out data/corridors_fall2026_v1 --no-reuse

For each current route of ``data/instance_fall2026_v1.json`` (both contractors), the path is the
fastest path on the whole graph from the first stop through each stop in order to campus, and the
corridor is every graph node within ``--buffer`` metres (1,500 by default) of that path. Writes to
``data/corridors_fall2026_v1/``:

- ``<contractor>-<route code>.nodes.npy`` and ``.edges.npy``: the corridor (graph node and edge indices);
- unless ``--no-reuse``: ``<key>.pre.npy`` (no-closure seconds between every pair of the route's
  stops and campus), ``<key>.paths.npy`` and ``<key>.paths_index.npy`` (the graph edges of each
  pair's path) and ``<key>.reuse.json`` (the points and the graph they were built on);
- ``index.json``: per route its key, node and edge counts, and the stops whose own node falls
  outside the corridor (expected: none) or that no path reaches.

Run it again after calibration: the pre-closure tables are tied to the graph's speed factor.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from reroute.graph import Corridor, Graph, corridor_for, reuse_table, shortest_path_nodes

RESEARCH = Path(__file__).resolve().parent
DEFAULT_GRAPH = RESEARCH / "data" / "graph_karachi_v1"
DEFAULT_INSTANCE = RESEARCH / "data" / "instance_fall2026_v1.json"
DEFAULT_OUT = RESEARCH / "data" / "corridors_fall2026_v1"
BUFFER_M = 1500.0


def route_key(contractor: str, code: str) -> str:
    """File key of a route's corridor, e.g. ``Jadoon-R-10``."""
    return f"{contractor}-{code}"


def route_path(graph: Graph, nodes: Sequence[int]) -> tuple[list[int], list[int]]:
    """Fastest path through ``nodes`` in order, and the indices of legs with no path.

    An unreachable leg is skipped: the path continues from the leg's end node.
    """
    path: list[int] = [int(nodes[0])] if len(nodes) else []
    broken: list[int] = []
    for i, (a, b) in enumerate(zip(nodes, nodes[1:])):
        leg = shortest_path_nodes(graph, int(a), int(b))
        if not leg:
            broken.append(i)
            leg = [int(a), int(b)]
        path.extend(leg[1:])
    return path, broken


def build_route(graph: Graph, key: str, stop_nodes: Sequence[int], campus_node: int,
                buffer_m: float = BUFFER_M) -> tuple[Corridor, dict]:
    """The route's corridor and its index entry (without the stop names)."""
    points = [int(n) for n in stop_nodes] + [int(campus_node)]
    path, broken = route_path(graph, points)
    corridor = corridor_for(graph, key, path, buffer_m=buffer_m)
    inside = set(corridor.nodes.tolist())
    entry = {"key": key, "nodes": int(len(corridor.nodes)), "edges": int(len(corridor.edges)),
             "path_nodes": len(path), "point_nodes": points,
             "outside": [i for i, n in enumerate(points[:-1]) if n not in inside],
             "unreachable_legs": broken}
    return corridor, entry


def save_corridor(corridor: Corridor, out_dir: Path) -> None:
    """Write ``<key>.nodes.npy`` and ``<key>.edges.npy``."""
    np.save(out_dir / f"{corridor.key}.nodes.npy", corridor.nodes.astype(np.int64))
    np.save(out_dir / f"{corridor.key}.edges.npy", corridor.edges.astype(np.int64))


def build_all(graph: Graph, instance: Mapping, out_dir: Path, buffer_m: float = BUFFER_M,
              reuse: bool = True) -> dict:
    """Corridors (and reuse tables) for every current route; returns the index written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stops = {s["name"]: s for s in instance["stops"]}
    campus = instance["campus"]
    campus_node, _ = graph.nearest_node(campus["lat"], campus["lng"])
    node_of: dict[str, int] = {}
    routes = []
    for contractor, data in sorted(instance["contractors"].items()):
        for route in data["baseline_routes"]:
            for name in route["stops"]:
                if name not in node_of:
                    node_of[name] = graph.nearest_node(stops[name]["lat"], stops[name]["lng"])[0]
            key = route_key(contractor, route["code"])
            corridor, entry = build_route(graph, key, [node_of[n] for n in route["stops"]], campus_node, buffer_m)
            save_corridor(corridor, out_dir)
            if reuse:
                reuse_table(graph, corridor, entry["point_nodes"], key=key).save(out_dir)
            entry["contractor"], entry["code"] = contractor, route["code"]
            entry["stops"] = list(route["stops"])
            entry["stops_outside"] = [route["stops"][i] for i in entry.pop("outside")]
            entry["unreachable_legs"] = [[(route["stops"] + ["CAMPUS"])[i], (route["stops"] + ["CAMPUS"])[i + 1]]
                                         for i in entry["unreachable_legs"]]
            routes.append(entry)
    index = {"graph_version": graph.version, "speed_factor": graph.speed_factor, "graph_nodes": graph.n_nodes,
             "buffer_m": buffer_m, "reuse": reuse,
             "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "routes": routes}
    (out_dir / "index.json").write_text(json.dumps(index, indent=1))
    return index


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    ap.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--buffer", type=float, default=BUFFER_M, help="corridor buffer in metres")
    ap.add_argument("--no-reuse", action="store_true", help="skip the pre-closure tables of Task 8")
    args = ap.parse_args(argv)
    if not (args.graph / "meta.json").exists():
        print(f"no graph at {args.graph}: run build_graph.py first", file=sys.stderr)
        return 2
    graph = Graph.load(args.graph)
    index = build_all(graph, json.loads(args.instance.read_text()), args.out, args.buffer, not args.no_reuse)
    routes = index["routes"]
    print(f"{'route':<20} {'nodes':>8} {'edges':>8}  stops outside / unreachable legs")
    for r in routes:
        notes = ", ".join(r["stops_outside"] + [" -> ".join(leg) for leg in r["unreachable_legs"]])
        print(f"{r['key']:<20} {r['nodes']:>8,} {r['edges']:>8,}  {notes or '-'}")
    if routes:
        sizes = sorted(r["nodes"] for r in routes)
        print(f"{len(routes)} corridors; nodes smallest {sizes[0]:,}, median {statistics.median(sizes):,.0f}, "
              f"largest {sizes[-1]:,} (whole graph {graph.n_nodes:,})")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
