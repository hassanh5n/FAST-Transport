"""Calibrate the road graph's speed factor against the saved OSRM matrix M1 (work item B2).

    python research/calibrate_graph.py               # one factor for every road
    python research/calibrate_graph.py --per-class   # one factor per road class, then one overall
    python research/calibrate_graph.py --dry-run     # print the figures, write nothing

For both contractors, graph times on the whole city graph are computed between every pair of the
matrix's nodes (one search per node). The factor is the 60th percentile of OSRM time over graph
time across all pairs the graph can reach, so that the scaled graph runs slightly slow rather than
fast. Printed: the factor, the median absolute error, the median signed error (graph minus OSRM,
relative to OSRM) and the share of pairs the graph finds unreachable.

Rule, fixed before the test: median absolute error at most 15% and median signed error not
negative. On a pass or a fail the factor is written to ``meta.json`` with the figures; if the
single factor fails, try ``--per-class``; if that fails too, follow the work plan's Section 11.

``--per-class`` groups segments by their profile speed (the road classes of ``SPEED_KMH``; classes
with the same speed share a group), fits one non-negative factor per group by least squares on
relative error along each pair's path, rewrites ``edge_s.npy`` (the uncalibrated times are kept
once in ``edge_s_profile.npy``) and then fits the overall factor on top.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from reroute.graph import Graph, TravelTimes, clear_row_cache
from reroute.roadnet import TABLE_KEYS

RESEARCH = Path(__file__).resolve().parent
DEFAULT_GRAPH = RESEARCH / "data" / "graph_karachi_v1"
DEFAULT_INSTANCE = RESEARCH / "data" / "instance_fall2026_v1.json"
DEFAULT_MATRIX = RESEARCH / "data" / "matrix_fall2026_v1.json"
PERCENTILE = 60
MAX_ABS_ERROR_PCT = 15.0
MIN_SIGNED_ERROR_PCT = 0.0
BATCH = 16                         # sources per search call, so few full-city rows are held at once


def matrix_points(instance: Mapping, names: Sequence[str]) -> list[tuple[float, float]]:
    """``(lat, lng)`` of each matrix node name; ``CAMPUS`` is the instance's campus."""
    stops = {s["name"]: (s["lat"], s["lng"]) for s in instance["stops"]}
    campus = instance["campus"]
    return [(campus["lat"], campus["lng"]) if n == "CAMPUS" else stops[n] for n in names]


def graph_table(graph: Graph, nodes: Sequence[int]) -> np.ndarray:
    """Seconds between every pair of graph ``nodes`` on the whole graph, no closures."""
    nodes = [int(n) for n in nodes]
    tt = TravelTimes(graph, None)
    out = np.full((len(nodes), len(nodes)), np.inf)
    cols = np.asarray(nodes)
    for start in range(0, len(nodes), BATCH):
        batch = nodes[start:start + BATCH]
        rows = tt.rows(batch)
        for i, s in enumerate(batch, start):
            out[i] = rows[s][cols]
        clear_row_cache()
    return out


def _pairs(osrm: np.ndarray) -> np.ndarray:
    """Mask of pairs to compare: off the diagonal with a positive, finite OSRM time."""
    osrm = np.asarray(osrm, dtype=np.float64)
    mask = np.isfinite(osrm) & (osrm > 0)
    np.fill_diagonal(mask, False)
    return mask


def fit_factor(osrm: np.ndarray, graph_s: np.ndarray, percentile: float = PERCENTILE) -> float:
    """The ``percentile`` of OSRM time / graph time over pairs with a finite, positive graph time."""
    mask = _pairs(osrm) & np.isfinite(graph_s) & (graph_s > 0)
    if not mask.any():
        raise ValueError("no pair has both an OSRM and a graph time")
    return float(np.percentile(np.asarray(osrm)[mask] / np.asarray(graph_s)[mask], percentile))


def errors(osrm: np.ndarray, graph_s: np.ndarray, factor: float) -> dict:
    """Median absolute and signed error (%) of ``graph_s x factor`` against OSRM, and unreachable share.

    Pairs whose two stops snap to one graph node (graph time 0) are left out of the errors, as in
    :func:`fit_factor`; they still count as reachable.
    """
    pairs = _pairs(osrm)
    reach = pairs & np.isfinite(graph_s)
    timed = reach & (np.asarray(graph_s) > 0)
    rel = (np.asarray(graph_s)[timed] * factor - np.asarray(osrm)[timed]) / np.asarray(osrm)[timed]
    return {"pairs": int(pairs.sum()),
            "median_abs_error_pct": round(float(np.median(np.abs(rel))) * 100, 2) if rel.size else None,
            "median_signed_error_pct": round(float(np.median(rel)) * 100, 2) if rel.size else None,
            "unreachable_share": round(1 - reach.sum() / pairs.sum(), 4) if pairs.any() else None}


def passes(err: Mapping) -> bool:
    """The calibration rule: median |error| <= 15% and median signed error >= 0."""
    a, s = err.get("median_abs_error_pct"), err.get("median_signed_error_pct")
    return a is not None and s is not None and a <= MAX_ABS_ERROR_PCT and s >= MIN_SIGNED_ERROR_PCT


def speed_groups(graph: Graph) -> tuple[np.ndarray, list[int]]:
    """Group index per segment by its profile speed (km/h, rounded), and the speeds of the groups."""
    seg_s = np.asarray(graph.seg_s, dtype=np.float64)
    kmh = np.rint(np.asarray(graph.seg_m, dtype=np.float64) / np.where(seg_s > 0, seg_s, 1.0) * 3.6).astype(np.int64)
    speeds, group = np.unique(kmh, return_inverse=True)
    return group, speeds.tolist()


def edge_group_seconds(graph: Graph, group: np.ndarray, n_groups: int) -> np.ndarray:
    """Profile seconds of each edge split by speed group: an ``edges x groups`` array."""
    out = np.zeros((graph.n_edges, n_groups))
    np.add.at(out, (np.asarray(graph.seg_edge), group), np.asarray(graph.seg_s, dtype=np.float64))
    return out


def fit_class_factors(graph: Graph, nodes_by_set: Sequence[Sequence[int]],
                      osrm_by_set: Sequence[np.ndarray]) -> tuple[np.ndarray, list[int]]:
    """One factor per speed group: non-negative least squares on relative error along each path.

    Paths are those of the graph as it is (with its current edge times).
    """
    from scipy.optimize import nnls

    group, speeds = speed_groups(graph)
    per_edge = edge_group_seconds(graph, group, len(speeds))
    a_rows, b = [], []
    tt = TravelTimes(graph, None)
    for nodes, osrm in zip(nodes_by_set, osrm_by_set):
        mask = _pairs(osrm)
        for i, s in enumerate(nodes):
            for j, edges in enumerate(tt.path_edges(int(s), [int(t) for t in nodes])):
                if mask[i, j] and len(edges):
                    a_rows.append(per_edge[edges].sum(axis=0) / osrm[i, j])
                    b.append(1.0)
    if not a_rows:
        raise ValueError("no reachable pair to fit class factors on")
    a = np.asarray(a_rows)
    used = a.sum(axis=0) > 0
    factors = np.ones(len(speeds))
    factors[used] = nnls(a[:, used], np.asarray(b))[0]
    factors[used & (factors <= 0)] = 1.0        # a group with no weight keeps its profile speed
    return factors, speeds


def apply_class_factors(graph: Graph, factors: np.ndarray) -> np.ndarray:
    """New ``edge_s`` (float32): each edge's profile seconds per group times the group's factor."""
    group, speeds = speed_groups(graph)
    return (edge_group_seconds(graph, group, len(speeds)) @ np.asarray(factors)).astype(np.float32)


def calibrate(graph: Graph, instance: Mapping, matrix: Mapping) -> tuple[float, dict, list, list]:
    """Fit the overall factor for ``graph`` as it is; returns factor, errors, node sets and OSRM tables."""
    node_sets, osrm_sets, graph_sets = [], [], []
    for data in matrix["contractors"].values():
        points = matrix_points(instance, data["nodes"])
        nodes = [graph.nearest_node(lat, lng)[0] for lat, lng in points]
        osrm = np.array([[np.inf if v is None else float(v) for v in row] for row in data["durations_s"]])
        node_sets.append(nodes)
        osrm_sets.append(osrm)
        graph_sets.append(graph_table(graph, nodes))
    osrm_all = _block_diag(osrm_sets)
    graph_all = _block_diag(graph_sets)
    factor = fit_factor(osrm_all, graph_all)
    return factor, errors(osrm_all, graph_all, factor), node_sets, osrm_sets


def _block_diag(tables: Sequence[np.ndarray]) -> np.ndarray:
    """Tables on the diagonal of one matrix, ``nan`` elsewhere (so the off-blocks are never compared)."""
    n = sum(len(t) for t in tables)
    out = np.full((n, n), np.nan)
    i = 0
    for t in tables:
        out[i:i + len(t), i:i + len(t)] = t
        i += len(t)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    ap.add_argument("--instance", type=Path, default=DEFAULT_INSTANCE)
    ap.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    ap.add_argument("--per-class", action="store_true", help="fit one factor per road class first")
    ap.add_argument("--dry-run", action="store_true", help="print the figures, change no file")
    args = ap.parse_args(argv)
    if not (args.graph / "meta.json").exists():
        print(f"no graph at {args.graph}: run build_graph.py first", file=sys.stderr)
        return 2
    instance = json.loads(args.instance.read_text())
    matrix = json.loads(args.matrix.read_text())
    meta_path = args.graph / "meta.json"
    meta = json.loads(meta_path.read_text())
    loaded = Graph.load(args.graph, mmap=False)         # not mapped: edge_s.npy may be rewritten
    graph = Graph({k: getattr(loaded, k) for k in TABLE_KEYS}, version=loaded.version)   # factor 1
    class_info = None
    if args.per_class:
        _, _, node_sets, osrm_sets = calibrate(graph, instance, matrix)
        factors, speeds = fit_class_factors(graph, node_sets, osrm_sets)
        new_edge_s = apply_class_factors(graph, factors)
        class_info = {f"{kmh} km/h": round(float(f), 4) for kmh, f in zip(speeds, factors)}
        print("class factors:", ", ".join(f"{k} x{v}" for k, v in class_info.items()))
        graph = Graph({k: (new_edge_s if k == "edge_s" else getattr(graph, k)) for k in TABLE_KEYS},
                      version=graph.version)
        if not args.dry_run:
            profile = args.graph / "edge_s_profile.npy"
            if not profile.exists():
                shutil.copyfile(args.graph / "edge_s.npy", profile)
            np.save(args.graph / "edge_s.npy", new_edge_s)
    factor, err, _, _ = calibrate(graph, instance, matrix)
    ok = passes(err)
    print(f"speed factor {factor:.4f} ({PERCENTILE}th percentile of OSRM / graph)")
    print(f"median absolute error {err['median_abs_error_pct']}% (rule: at most {MAX_ABS_ERROR_PCT:g}%)")
    print(f"median signed error {err['median_signed_error_pct']}% (rule: not negative)")
    print(f"unreachable pairs {err['unreachable_share']:.2%} of {err['pairs']:,}")
    print("PASS" if ok else "FAIL: " + ("try --per-class" if not args.per_class else "see the work plan, Section 11"))
    if not args.dry_run:
        meta["speed_factor"] = round(factor, 6)
        meta["calibration"] = {"matrix": matrix.get("instance"), "matrix_built_at": matrix.get("built_at"),
                               "percentile": PERCENTILE, **err, "pass": ok, "per_class": class_info,
                               "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        meta_path.write_text(json.dumps(meta, indent=1))
        print(f"wrote {meta_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
