"""Road tables from map ways: the full directed segment table and the compressed search graph.

Pure ``numpy`` and the standard library; no file access. ``build_graph.py`` reads the map file
into :class:`Way` objects and saves the arrays returned by :func:`build_tables`.

Two tables come out of one pass:

* **Segments**, one row per direction a vehicle may travel between two adjacent map nodes. OSRM's
  speed file names segments this way, and closures are matched to roads by their geometry.
* **The compressed graph**: chains of pass-through nodes are merged into one edge. A node is
  removed when it has exactly two distinct neighbours, the roads on both sides allow the same
  directions, and it is not in ``keep_ids``. A closed ring with no kept node keeps its lowest-id
  node, so the ring is not lost. Parallel edges between the same two nodes stay separate edges.

Every segment records the compressed edge that contains it (``seg_edge``), and an edge's length
and time are the sums over its segments.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np

EARTH_RADIUS_M = 6_371_008.8

# Car-profile speeds of OSRM, km/h. Other classes are not roads a bus may use.
SPEED_KMH: dict[str, float] = {
    "motorway": 90, "motorway_link": 45, "trunk": 85, "trunk_link": 40,
    "primary": 65, "primary_link": 30, "secondary": 55, "secondary_link": 25,
    "tertiary": 40, "tertiary_link": 20, "unclassified": 25, "residential": 25,
    "living_street": 10, "service": 15,
}

FORWARD_ONLY = frozenset({"yes", "true", "1"})
REVERSE_ONLY = frozenset({"-1", "reverse"})

# Array names and dtypes produced by build_tables, in a fixed order.
TABLE_DTYPES: dict[str, type] = {
    "seg_from": np.int64, "seg_to": np.int64,
    "seg_lat1": np.float64, "seg_lng1": np.float64, "seg_lat2": np.float64, "seg_lng2": np.float64,
    "seg_m": np.float32, "seg_s": np.float32, "seg_edge": np.int32,
    "node_id": np.int64, "node_lat": np.float64, "node_lng": np.float64,
    "edge_u": np.int32, "edge_v": np.int32, "edge_m": np.float32, "edge_s": np.float32,
}
TABLE_KEYS: tuple[str, ...] = tuple(TABLE_DTYPES)


@dataclass(frozen=True)
class Way:
    """A map way: ``nodes`` are ``(map node id, lat, lng)`` in way order."""

    nodes: list[tuple[int, float, float]]
    highway: str
    oneway: str = ""


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres between two points given in degrees."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def haversine_np(lat1, lng1, lat2, lng2) -> np.ndarray:
    """Vectorised :func:`haversine_m` over numpy arrays (broadcasting), in metres."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(np.asarray(lng2) - np.asarray(lng1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.minimum(1.0, np.sqrt(a)))


def _directions(oneway: str) -> tuple[bool, bool]:
    """(forward allowed, reverse allowed) for an OSM ``oneway`` value."""
    value = (oneway or "").strip().lower()
    if value in FORWARD_ONLY:
        return True, False
    if value in REVERSE_ONLY:
        return False, True
    return True, True


def _empty_tables() -> dict[str, np.ndarray]:
    return {k: np.zeros(0, dtype=d) for k, d in TABLE_DTYPES.items()}


def build_tables(ways: Iterable[Way], keep_ids: Iterable[int] = ()) -> dict[str, np.ndarray]:
    """Segment table and compressed graph for ``ways``; see the module docstring for the rules.

    Graph nodes are sorted by map node id. ``keep_ids`` that are not on any kept way are ignored.
    """
    seg_from: list[int] = []
    seg_to: list[int] = []
    seg_s: list[float] = []
    seg_m: list[float] = []
    coords: dict[int, tuple[float, float]] = {}
    for w in ways:
        speed = SPEED_KMH.get(w.highway)
        if speed is None:
            continue
        mps = speed / 3.6
        fwd, rev = _directions(w.oneway)
        for (a, alat, alng), (b, blat, blng) in zip(w.nodes, w.nodes[1:]):
            if a == b:
                continue
            coords.setdefault(a, (alat, alng))
            coords.setdefault(b, (blat, blng))
            metres = haversine_m(alat, alng, blat, blng)
            for ok, f, t in ((fwd, a, b), (rev, b, a)):
                if ok:
                    seg_from.append(f)
                    seg_to.append(t)
                    seg_m.append(metres)
                    seg_s.append(metres / mps)
    if not seg_from:
        return _empty_tables()

    f_ids = np.asarray(seg_from, dtype=np.int64)
    t_ids = np.asarray(seg_to, dtype=np.int64)
    ids, inverse = np.unique(np.concatenate([f_ids, t_ids]), return_inverse=True)
    n_segs = len(f_ids)
    f, t = inverse[:n_segs], inverse[n_segs:]
    seconds = np.asarray(seg_s, dtype=np.float64)
    metres = np.asarray(seg_m, dtype=np.float64)

    kept = _junctions(ids, f, t, set(keep_ids))
    seg_edge, edge_u, edge_v = _compress(f, t, kept, ids)

    edge_m = np.bincount(seg_edge, weights=metres, minlength=len(edge_u))
    edge_s = np.bincount(seg_edge, weights=seconds, minlength=len(edge_u))
    node_index = np.cumsum(kept) - 1                       # dense id -> graph node index
    lat = np.array([coords[int(i)][0] for i in ids])
    lng = np.array([coords[int(i)][1] for i in ids])
    out = {
        "seg_from": f_ids, "seg_to": t_ids,
        "seg_lat1": lat[f], "seg_lng1": lng[f], "seg_lat2": lat[t], "seg_lng2": lng[t],
        "seg_m": metres, "seg_s": seconds, "seg_edge": seg_edge,
        "node_id": ids[kept], "node_lat": lat[kept], "node_lng": lng[kept],
        "edge_u": node_index[edge_u], "edge_v": node_index[edge_v], "edge_m": edge_m, "edge_s": edge_s,
    }
    return {k: np.ascontiguousarray(out[k], dtype=d) for k, d in TABLE_DTYPES.items()}


def _by_node(index: np.ndarray, n: int) -> tuple[np.ndarray, np.ndarray]:
    """CSR-style grouping: (order, start offsets) of segments by ``index``."""
    order = np.argsort(index, kind="stable")
    starts = np.zeros(n + 1, dtype=np.int64)
    np.cumsum(np.bincount(index, minlength=n), out=starts[1:])
    return order, starts


def _junctions(ids: np.ndarray, f: np.ndarray, t: np.ndarray, keep: set[int]) -> np.ndarray:
    """Boolean mask over dense nodes: True where the node stays a graph node (before rings)."""
    n = len(ids)
    out_order, out_start = _by_node(f, n)
    in_order, in_start = _by_node(t, n)
    kept = np.ones(n, dtype=bool)
    # Only nodes with two to four touching segments can be pass-throughs: screen in numpy first.
    touching = np.diff(out_start) + np.diff(in_start)
    for v in np.flatnonzero((touching >= 2) & (touching <= 4)).tolist():
        if int(ids[v]) in keep:
            continue
        outs = t[out_order[out_start[v]:out_start[v + 1]]].tolist()
        ins = f[in_order[in_start[v]:in_start[v + 1]]].tolist()
        nbrs = set(outs) | set(ins)
        if len(nbrs) != 2:
            continue
        a, b = nbrs
        # Same directions on both sides: a->v exactly when v->b, and b->v exactly when v->a,
        # with at most one segment of each so a chain has one way through.
        a_in, b_out, b_in, a_out = ins.count(a), outs.count(b), ins.count(b), outs.count(a)
        if a_in == b_out <= 1 and b_in == a_out <= 1:
            kept[v] = False
    return kept


def _compress(f: np.ndarray, t: np.ndarray, kept: np.ndarray,
              ids: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Walk chains from kept nodes. Returns seg_edge and the dense end nodes of each edge.

    ``kept`` is updated in place when a ring without a kept node gets its lowest-id node.
    """
    n_segs = len(f)
    out_order, out_start = _by_node(f, len(kept))
    out_lists = [out_order[out_start[v]:out_start[v + 1]] for v in range(len(kept))]
    seg_edge = np.full(n_segs, -1, dtype=np.int64)
    edge_u: list[int] = []
    edge_v: list[int] = []

    def next_segment(seg: int) -> int:
        """The one segment leaving the pass-through node ``t[seg]`` towards its other neighbour."""
        v, back = t[seg], f[seg]
        for s in out_lists[v]:
            if t[s] != back:
                return int(s)
        raise AssertionError("a pass-through node has no way onward")   # excluded by _junctions

    def walk(seg: int) -> None:
        e = len(edge_u)
        start = int(f[seg])
        while True:
            seg_edge[seg] = e
            if kept[t[seg]]:
                break
            seg = next_segment(seg)
        edge_u.append(start)
        edge_v.append(int(t[seg]))

    for v in np.flatnonzero(kept).tolist():
        for s in out_lists[v].tolist():
            walk(s)
    # Whatever is left lies on rings made only of pass-through nodes.
    for s0 in np.flatnonzero(seg_edge < 0).tolist():
        if seg_edge[s0] >= 0:
            continue
        ring, seg = [int(f[s0])], s0
        while int(t[seg]) != ring[0]:
            ring.append(int(t[seg]))
            seg = next_segment(seg)
        anchor = min(ring, key=lambda d: ids[d])
        kept[anchor] = True
        for s in out_lists[anchor].tolist():
            if seg_edge[s] < 0:
                walk(s)
    return seg_edge, np.asarray(edge_u, dtype=np.int64), np.asarray(edge_v, dtype=np.int64)
