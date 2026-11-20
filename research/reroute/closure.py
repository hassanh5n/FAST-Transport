"""Road closures: circles matched to road segments by geometry.

A closure is one or more circles and a speed factor: 0 blocks the road, a value between 0 and 1
slows it. A segment is affected when any point sampled along it (both ends and every ``sample_m``
metres between) lies inside a circle, so a long segment that crosses a closure with no map node
inside it is still caught.

The functions take the tables of :func:`reroute.roadnet.build_tables` either as a dictionary or as
any object with the same names as attributes (such as :class:`reroute.graph.Graph`).

Pure ``numpy`` and the standard library; no file access.
"""
from __future__ import annotations

import hashlib
import json
import math
import weakref
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from reroute.roadnet import EARTH_RADIUS_M, haversine_np

GRID_DEG = 0.005                 # bucket size of the segment-midpoint index
_COL_SPAN = 1_000_000            # key = row * _COL_SPAN + (col + _COL_SHIFT)
_COL_SHIFT = 100_000
_M_PER_DEG_LAT = math.pi / 180 * EARTH_RADIUS_M
_INDEX_CACHE_MAX = 4


@dataclass(frozen=True)
class Closure:
    """``circles`` are ``(lat, lng, radius_m)``; ``factor`` 0 is a full block, below 1 a slowed road."""

    id: str
    circles: tuple[tuple[float, float, float], ...]
    factor: float

    def __post_init__(self) -> None:
        if not self.circles:
            raise ValueError(f"closure {self.id}: needs at least one circle")
        if not 0.0 <= self.factor <= 1.0:
            raise ValueError(f"closure {self.id}: factor must be between 0 and 1")
        for circle in self.circles:
            if len(circle) != 3 or not circle[2] > 0:
                raise ValueError(f"closure {self.id}: circles are (lat, lng, radius_m > 0)")

    @property
    def blocks(self) -> bool:
        """True for a full block (factor 0)."""
        return self.factor == 0.0


def _get(tables: Any, name: str) -> np.ndarray:
    """A table array from a dictionary or from an object attribute."""
    if isinstance(tables, Mapping):
        return tables[name]
    return getattr(tables, name)


def closure_key(closures: Sequence[Closure]) -> str:
    """A stable hash of a set of closures, independent of their order; ``"none"`` when empty."""
    if not closures:
        return "none"
    canon = sorted(json.dumps([c.id, [[float(x) for x in circle] for circle in c.circles], float(c.factor)])
                   for c in closures)
    return hashlib.sha256("\n".join(canon).encode()).hexdigest()[:16]


class _SegmentIndex:
    """Segment midpoints bucketed in a plain latitude/longitude grid of ``GRID_DEG`` degrees."""

    def __init__(self, tables: Any) -> None:
        lat1, lng1 = np.asarray(_get(tables, "seg_lat1")), np.asarray(_get(tables, "seg_lng1"))
        lat2, lng2 = np.asarray(_get(tables, "seg_lat2")), np.asarray(_get(tables, "seg_lng2"))
        mid_lat, mid_lng = (lat1 + lat2) / 2, (lng1 + lng2) / 2
        keys = self._key(np.floor(mid_lat / GRID_DEG), np.floor(mid_lng / GRID_DEG))
        self.order = np.argsort(keys, kind="stable")
        self.keys = keys[self.order]
        seg_m = np.asarray(_get(tables, "seg_m"), dtype=np.float64)
        self.max_half_m = float(seg_m.max()) / 2 if len(seg_m) else 0.0

    @staticmethod
    def _key(row, col):
        return np.asarray(row, dtype=np.int64) * _COL_SPAN + (np.asarray(col, dtype=np.int64) + _COL_SHIFT)

    def candidates(self, lat: float, lng: float, radius_m: float) -> np.ndarray:
        """Segments whose midpoint lies in a bucket the circle (widened by half a segment) reaches."""
        reach = radius_m + self.max_half_m
        dlat = reach / _M_PER_DEG_LAT
        dlng = reach / (_M_PER_DEG_LAT * max(math.cos(math.radians(lat)), 1e-6))
        r0, r1 = math.floor((lat - dlat) / GRID_DEG), math.floor((lat + dlat) / GRID_DEG)
        c0, c1 = math.floor((lng - dlng) / GRID_DEG), math.floor((lng + dlng) / GRID_DEG)
        parts = []
        for row in range(r0, r1 + 1):
            lo = np.searchsorted(self.keys, self._key(row, c0), side="left")
            hi = np.searchsorted(self.keys, self._key(row, c1), side="right")
            if hi > lo:
                parts.append(self.order[lo:hi])
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.int64)


_INDEX_CACHE: "OrderedDict[int, tuple[weakref.ref, _SegmentIndex]]" = OrderedDict()


def _index(tables: Any) -> _SegmentIndex:
    """The grid index for ``tables``, built once per segment table (a few recent ones are kept).

    Entries hold only a weak reference to the table, so a memory-mapped file is not kept open.
    """
    lat1 = _get(tables, "seg_lat1")
    entry = _INDEX_CACHE.get(id(lat1))
    if entry is not None and entry[0]() is lat1:
        _INDEX_CACHE.move_to_end(id(lat1))
        return entry[1]
    index = _SegmentIndex(tables)
    _INDEX_CACHE[id(lat1)] = (weakref.ref(lat1), index)
    while len(_INDEX_CACHE) > _INDEX_CACHE_MAX:
        _INDEX_CACHE.popitem(last=False)
    return index


def closed_segments(tables: Any, closure: Closure, sample_m: float = 50.0) -> np.ndarray:
    """Sorted indices of segments with any sampled point inside any circle of ``closure``."""
    if sample_m <= 0:
        raise ValueError("sample_m must be positive")
    index = _index(tables)
    lat1, lng1 = _get(tables, "seg_lat1"), _get(tables, "seg_lng1")
    lat2, lng2 = _get(tables, "seg_lat2"), _get(tables, "seg_lng2")
    seg_m = _get(tables, "seg_m")
    hits = []
    for clat, clng, radius in closure.circles:
        cand = index.candidates(clat, clng, radius)
        if not len(cand):
            continue
        steps = np.maximum(1, np.ceil(np.asarray(seg_m[cand], dtype=np.float64) / sample_m)).astype(np.int64)
        owner = np.repeat(np.arange(len(cand)), steps + 1)          # one row per sample
        first = np.repeat(np.cumsum(steps + 1) - (steps + 1), steps + 1)
        frac = (np.arange(len(owner)) - first) / steps[owner]
        seg = cand[owner]
        plat = lat1[seg] + (lat2[seg] - lat1[seg]) * frac
        plng = lng1[seg] + (lng2[seg] - lng1[seg]) * frac
        inside = haversine_np(plat, plng, clat, clng) <= radius
        hits.append(np.unique(seg[inside]))
    if not hits:
        return np.zeros(0, dtype=np.int64)
    return np.unique(np.concatenate(hits)).astype(np.int64)


def _segment_factors(tables: Any, closures: Sequence[Closure]) -> dict[int, float]:
    """Lowest factor per affected segment over all closures."""
    factors: dict[int, float] = {}
    for closure in closures:
        for s in closed_segments(tables, closure).tolist():
            factors[s] = min(factors.get(s, 1.0), closure.factor)
    return factors


def edge_changes(tables: Any, closures: Sequence[Closure]) -> tuple[np.ndarray, dict[int, float]]:
    """Edges to remove (any segment fully blocked) and extra seconds for slowed edges.

    The extra seconds of an edge are the sum over its slowed segments of ``seg_s x (1/factor - 1)``,
    in the table's own (uncalibrated) seconds. Where closures overlap a segment takes the lowest
    factor. Removed edges get no extra-seconds entry.
    """
    seg_edge, seg_s = _get(tables, "seg_edge"), _get(tables, "seg_s")
    removed: set[int] = set()
    extra: dict[int, float] = {}
    for s, factor in _segment_factors(tables, closures).items():
        e = int(seg_edge[s])
        if factor <= 0.0:
            removed.add(e)
        elif factor < 1.0:
            extra[e] = extra.get(e, 0.0) + float(seg_s[s]) * (1.0 / factor - 1.0)
    for e in removed:
        extra.pop(e, None)
    return np.array(sorted(removed), dtype=np.int64), extra


def osrm_speed_rows(tables: Any, closure: Closure) -> list[tuple[int, int, int]]:
    """``(from map node, to map node, km/h)`` per affected segment, for OSRM's speed file.

    km/h is 0 for a full block, otherwise the segment's own speed times the factor, at least 1.
    The segment's speed is recovered from ``seg_m / seg_s`` (``float32``) and rounded to a whole
    km/h before the factor is applied (every class speed is a whole km/h), so the segments of one
    road get one speed even when the product ends in .5. A pair of map nodes listed twice (parallel
    segments) keeps the lower speed.
    """
    seg_from, seg_to = _get(tables, "seg_from"), _get(tables, "seg_to")
    seg_m, seg_s = _get(tables, "seg_m"), _get(tables, "seg_s")
    rows: dict[tuple[int, int], int] = {}
    for s in closed_segments(tables, closure).tolist():
        if closure.blocks:
            kmh = 0
        else:
            speed = round(float(seg_m[s]) / float(seg_s[s]) * 3.6) if float(seg_s[s]) > 0 else 0
            kmh = max(1, round(speed * closure.factor))
        pair = (int(seg_from[s]), int(seg_to[s]))
        rows[pair] = min(rows.get(pair, kmh), kmh)
    return [(a, b, kmh) for (a, b), kmh in rows.items()]


def closed_points(point_lat, point_lng, closures: Sequence[Closure]) -> np.ndarray:
    """True where a point lies inside a full-block circle: such a point cannot be visited."""
    lat = np.atleast_1d(np.asarray(point_lat, dtype=np.float64))
    lng = np.atleast_1d(np.asarray(point_lng, dtype=np.float64))
    out = np.zeros(lat.shape, dtype=bool)
    for closure in closures:
        if not closure.blocks:
            continue
        for clat, clng, radius in closure.circles:
            out |= haversine_np(lat, lng, clat, clng) <= radius
    return out


def closed_road_points(tables: Any, point_lat, point_lng, closures: Sequence[Closure],
                       tol_m: float = 1.0) -> np.ndarray:
    """True where a point lies on a segment a full block closes and on no open segment (within ``tol_m``).

    Use it on the place where a point meets the road: such a point cannot be visited, because OSRM
    would move it onto another road (work plan Section 5: "if its road segment is closed"). A point
    where an open road also meets, such as a junction at the end of a closed segment, stays open.
    """
    lat = np.atleast_1d(np.asarray(point_lat, dtype=np.float64))
    lng = np.atleast_1d(np.asarray(point_lng, dtype=np.float64))
    out = np.zeros(lat.shape, dtype=bool)
    blocks = [c for c in closures if c.blocks]
    if not blocks or not len(lat):
        return out
    index = _index(tables)
    lat1, lng1 = np.asarray(_get(tables, "seg_lat1")), np.asarray(_get(tables, "seg_lng1"))
    lat2, lng2 = np.asarray(_get(tables, "seg_lat2")), np.asarray(_get(tables, "seg_lng2"))
    closed = np.unique(np.concatenate([closed_segments(tables, c) for c in blocks]))
    for k in range(len(lat)):
        cand = index.candidates(float(lat[k]), float(lng[k]), tol_m)
        if not len(cand):
            continue
        kx = _M_PER_DEG_LAT * math.cos(math.radians(float(lat[k])))
        ax, ay = (lng1[cand] - lng[k]) * kx, (lat1[cand] - lat[k]) * _M_PER_DEG_LAT
        bx, by = (lng2[cand] - lng[k]) * kx, (lat2[cand] - lat[k]) * _M_PER_DEG_LAT
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        t = np.clip(-(ax * dx + ay * dy) / np.where(length2 > 0, length2, 1.0), 0.0, 1.0)
        near = np.hypot(ax + t * dx, ay + t * dy) <= tol_m
        on_closed = np.isin(cand[near], closed)
        out[k] = bool(on_closed.any()) and not bool((~on_closed).any())
    return out
