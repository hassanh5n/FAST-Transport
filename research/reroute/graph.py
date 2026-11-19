"""The road graph at run time: loading, corridors, closures and travel-time rows.

``Graph`` holds the arrays of :func:`reroute.roadnet.build_tables` (memory-mapped when loaded from
disk). ``TravelTimes`` answers travel-time rows with ``scipy.sparse.csgraph.dijkstra`` on a CSR
matrix of one route's corridor (or of the whole city), with closed roads removed from the edge list
and slowed roads given extra seconds. Rows are cached in one module-level, least-recently-used
cache shared by every ``TravelTimes``, keyed by graph (its version plus a per-load serial),
corridor (its key plus a hash of its nodes and edges, so two corridors that share a key never share
rows), closure set and source, holding at most ``ROW_CACHE_MAX`` rows at corridor length and at most ``ROW_CACHE_MAX_BYTES`` in
all (rows searched city-wide are graph length).

Reuse of pre-closure rows: per route, the no-closure times between the route's points and the
graph edges of each pair's shortest path are stored offline (:class:`ReuseTable`). A closure only
makes travel slower, so a stored shortest path that uses no removed or slowed edge is still the
shortest, and that point's row is served from the table instead of searched.

Imports only ``numpy``, ``scipy`` and the standard library. The only file access is in
:meth:`Graph.load`, :func:`load_corridor`, :func:`load_reuse` and :meth:`ReuseTable.save`.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

from reroute.closure import Closure, closure_key, edge_changes
from reroute.roadnet import EARTH_RADIUS_M, TABLE_KEYS, haversine_np

ROW_CACHE_MAX = 256
ROW_CACHE_MAX_BYTES = 128 * 2**20  # city rows are graph length (~1.6 MB), so rows alone are no bound
ROW_CACHE: "OrderedDict[tuple[str, str, str, int], np.ndarray]" = OrderedDict()
MIN_EDGE_S = 1e-3                 # a zero weight would be ambiguous in a sparse matrix
CITY = "city"
_GRAPH_SERIAL = itertools.count(1)


_cache_bytes = 0


def clear_row_cache() -> None:
    """Empty the shared row cache."""
    global _cache_bytes
    ROW_CACHE.clear()
    _cache_bytes = 0


def _cache_put(key: tuple[str, str, str, int], row: np.ndarray) -> None:
    """Store ``row``, then drop least recently used rows past ``ROW_CACHE_MAX`` or ``ROW_CACHE_MAX_BYTES``."""
    global _cache_bytes
    row.flags.writeable = False
    old = ROW_CACHE.pop(key, None)
    if old is not None:
        _cache_bytes -= old.nbytes
    ROW_CACHE[key] = row
    _cache_bytes += row.nbytes
    while len(ROW_CACHE) > 1 and (len(ROW_CACHE) > ROW_CACHE_MAX or _cache_bytes > ROW_CACHE_MAX_BYTES):
        _cache_bytes -= ROW_CACHE.popitem(last=False)[1].nbytes


def _csr(n: int, u: np.ndarray, v: np.ndarray, w: np.ndarray,
         ids: np.ndarray) -> tuple[csr_matrix, np.ndarray, np.ndarray]:
    """CSR matrix over ``n`` nodes keeping the fastest of parallel edges and no self-loops.

    Also returns the sorted pair keys ``u * n + v`` and the edge id (from ``ids``) chosen for each.
    """
    keep = u != v
    u, v, w, ids = u[keep], v[keep], np.maximum(w[keep], MIN_EDGE_S), ids[keep]
    order = np.lexsort((w, v, u))
    u, v, w, ids = u[order], v[order], w[order], ids[order]
    first = np.ones(len(u), dtype=bool)
    first[1:] = (u[1:] != u[:-1]) | (v[1:] != v[:-1])
    u, v, w, ids = u[first], v[first], w[first], ids[first]
    matrix = csr_matrix((w, (u, v)), shape=(n, n))
    return matrix, u.astype(np.int64) * n + v, ids


class Graph:
    """The road tables as attributes, plus ``n_nodes``, ``n_edges``, ``version``, ``speed_factor``."""

    def __init__(self, tables: Mapping[str, np.ndarray], version: str = "toy", speed_factor: float = 1.0) -> None:
        missing = [k for k in TABLE_KEYS if k not in tables]
        if missing:
            raise ValueError(f"road tables are missing {missing}")
        for k in TABLE_KEYS:
            setattr(self, k, tables[k])
        self.version = str(version)
        self.speed_factor = float(speed_factor)
        # Row-cache identity: the version plus a serial, so two graphs that share a version name
        # (toy graphs, a graph recalibrated in place) never serve each other's rows.
        self.cache_id = f"{self.version}#{next(_GRAPH_SERIAL)}"
        self.n_nodes = len(self.node_id)
        self.n_edges = len(self.edge_u)
        self._edge_seconds: np.ndarray | None = None
        self._profile_edge_s: np.ndarray | None = None
        self._city: tuple[csr_matrix, np.ndarray, np.ndarray] | None = None
        self._main_nodes: np.ndarray | None = None

    @classmethod
    def load(cls, directory: str | Path, mmap: bool = True) -> Graph:
        """Read the ``.npy`` arrays (memory-mapped by default) and ``meta.json`` of a built graph."""
        directory = Path(directory)
        meta = json.loads((directory / "meta.json").read_text())
        mode = "r" if mmap else None
        tables = {k: np.load(directory / f"{k}.npy", mmap_mode=mode) for k in TABLE_KEYS}
        return cls(tables, version=meta.get("version", directory.name),
                   speed_factor=meta.get("speed_factor", 1.0))

    @property
    def edge_seconds(self) -> np.ndarray:
        """Calibrated edge times: ``edge_s x speed_factor`` (float64)."""
        if self._edge_seconds is None:
            self._edge_seconds = np.asarray(self.edge_s, dtype=np.float64) * self.speed_factor
        return self._edge_seconds

    @property
    def profile_edge_s(self) -> np.ndarray:
        """Edge times from the segments' profile speeds, before any calibration (float64)."""
        if self._profile_edge_s is None:
            self._profile_edge_s = np.bincount(np.asarray(self.seg_edge), weights=np.asarray(self.seg_s),
                                               minlength=self.n_edges)
        return self._profile_edge_s

    def city_matrix(self) -> tuple[csr_matrix, np.ndarray, np.ndarray]:
        """The whole-city search matrix with no closures, its pair keys and chosen edges (cached)."""
        if self._city is None:
            self._city = _csr(self.n_nodes, np.asarray(self.edge_u, dtype=np.int64),
                              np.asarray(self.edge_v, dtype=np.int64), self.edge_seconds,
                              np.arange(self.n_edges, dtype=np.int64))
        return self._city

    @property
    def main_nodes(self) -> np.ndarray:
        """Boolean mask of the nodes in the largest strongly connected part of the graph (cached).

        From any of these nodes a vehicle can reach every other one and come back. Islands and
        one-way traps (a parking aisle with no way back out) lie outside it.
        """
        if self._main_nodes is None:
            if self.n_nodes == 0:
                self._main_nodes = np.zeros(0, dtype=bool)
            else:
                u, v = np.asarray(self.edge_u, dtype=np.int64), np.asarray(self.edge_v, dtype=np.int64)
                adj = csr_matrix((np.ones(len(u), dtype=np.int8), (u, v)), shape=(self.n_nodes, self.n_nodes))
                _, label = connected_components(adj, directed=True, connection="strong")
                self._main_nodes = label == int(np.argmax(np.bincount(label)))
        return self._main_nodes

    def nearest_node(self, lat: float, lng: float) -> tuple[int, float]:
        """Node index of the main road network (:attr:`main_nodes`) nearest to the point, and its
        distance in metres. Like OSRM, a point is never snapped onto an island or a one-way trap,
        where every leg to or from it would have no path.
        """
        if self.n_nodes == 0:
            raise ValueError("the graph has no nodes")
        d = haversine_np(np.asarray(self.node_lat), np.asarray(self.node_lng), lat, lng)
        d = np.where(self.main_nodes, d, np.inf)
        i = int(np.argmin(d))
        return i, float(d[i])


@dataclass(frozen=True)
class Corridor:
    """Graph node indices and the graph edges with both ends among them.

    Both arrays are stored sorted and without repeats, whatever order they are given in.
    ``ident`` is the key plus a hash of the two arrays: it names this exact node and edge set, so
    the row cache and reuse tables can tell apart two corridors built under the same key.
    """

    key: str
    nodes: np.ndarray
    edges: np.ndarray
    ident: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        nodes = np.unique(np.asarray(self.nodes, dtype=np.int64))
        edges = np.unique(np.asarray(self.edges, dtype=np.int64))
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(self, "edges", edges)
        digest = hashlib.sha256(nodes.tobytes() + b"|" + edges.tobytes()).hexdigest()[:16]
        object.__setattr__(self, "ident", f"{self.key}@{digest}")


def _path_from(pred: np.ndarray, a: int, b: int) -> list[int]:
    """Node sequence from ``a`` to ``b`` out of a predecessor row; empty when unreachable."""
    if a == b:
        return [a]
    if pred[b] < 0:
        return []
    path = [b]
    while path[-1] != a:
        path.append(int(pred[path[-1]]))
    return path[::-1]


def shortest_path_nodes(graph: Graph, a: int, b: int) -> list[int]:
    """Node indices of the fastest path from ``a`` to ``b`` on the whole graph; empty if none."""
    matrix = graph.city_matrix()[0]
    _, pred = dijkstra(matrix, directed=True, indices=int(a), return_predecessors=True)
    return _path_from(pred, int(a), int(b))


def corridor_for(graph: Graph, key: str, path_nodes: Sequence[int], buffer_m: float = 1500.0) -> Corridor:
    """Every graph node within ``buffer_m`` of any node in ``path_nodes``, and their edges."""
    path = np.unique(np.asarray(list(path_nodes), dtype=np.int64))
    if not len(path):
        return Corridor(key, np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64))
    lat, lng = np.asarray(graph.node_lat), np.asarray(graph.node_lng)
    lat0 = math.radians(float(lat[path].mean()))

    def xy(la, ln):
        return np.column_stack([np.radians(ln) * math.cos(lat0) * EARTH_RADIUS_M, np.radians(la) * EARTH_RADIUS_M])

    dist, _ = cKDTree(xy(lat[path], lng[path])).query(xy(lat, lng), k=1, distance_upper_bound=buffer_m)
    inside = np.isfinite(dist) & (dist <= buffer_m)
    inside[path] = True
    nodes = np.flatnonzero(inside).astype(np.int64)
    edges = np.flatnonzero(inside[np.asarray(graph.edge_u)] & inside[np.asarray(graph.edge_v)]).astype(np.int64)
    return Corridor(key, nodes, edges)


def load_corridor(directory: str | Path, key: str, graph_version: str | None = None) -> Corridor | None:
    """The corridor saved by ``build_corridors.py`` for ``key``, or ``None`` when it has none.

    When ``graph_version`` is given and the folder's ``index.json`` names another graph version,
    raises ``ValueError``: node indices of an older build mean nothing on a rebuilt graph.
    """
    directory = Path(directory)
    index_path = directory / "index.json"
    if graph_version is not None and index_path.exists():
        built_for = json.loads(index_path.read_text(encoding="utf-8")).get("graph_version")
        if built_for != graph_version:
            raise ValueError(f"corridors in {directory} were built for graph {built_for}, not {graph_version}")
    nodes_path, edges_path = directory / f"{key}.nodes.npy", directory / f"{key}.edges.npy"
    if not nodes_path.exists() or not edges_path.exists():
        return None
    return Corridor(key, np.load(nodes_path), np.load(edges_path))


@dataclass(frozen=True)
class ReuseTable:
    """No-closure times between one route's points, and the graph edges of each pair's path.

    ``pre[i, j]`` is seconds from point ``i`` to point ``j``; the edges of that pair's path are
    ``paths[paths_index[i * K + j]:paths_index[i * K + j + 1]]`` for ``K`` points. The table is valid
    only for the graph version, speed factor and corridor it was built on; ``corridor_key`` is that
    corridor's :attr:`Corridor.ident` (or ``"city"``), so a corridor rebuilt with other nodes under
    the same key does not match.
    """

    key: str
    corridor_key: str
    graph_version: str
    speed_factor: float
    point_nodes: np.ndarray
    pre: np.ndarray
    paths: np.ndarray
    paths_index: np.ndarray

    def save(self, directory: str | Path) -> None:
        """Write ``<key>.pre.npy``, ``.paths.npy``, ``.paths_index.npy`` and ``<key>.reuse.json``."""
        directory = Path(directory)
        np.save(directory / f"{self.key}.pre.npy", self.pre)
        np.save(directory / f"{self.key}.paths.npy", self.paths)
        np.save(directory / f"{self.key}.paths_index.npy", self.paths_index)
        (directory / f"{self.key}.reuse.json").write_text(json.dumps({
            "corridor_key": self.corridor_key, "graph_version": self.graph_version,
            "speed_factor": self.speed_factor, "point_nodes": self.point_nodes.tolist()}))


def load_reuse(directory: str | Path, key: str) -> ReuseTable | None:
    """The reuse table saved for ``key``, or ``None`` when there is none."""
    directory = Path(directory)
    meta_path = directory / f"{key}.reuse.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    return ReuseTable(key, meta["corridor_key"], meta["graph_version"], float(meta["speed_factor"]),
                      np.asarray(meta["point_nodes"], dtype=np.int64),
                      np.load(directory / f"{key}.pre.npy"), np.load(directory / f"{key}.paths.npy"),
                      np.load(directory / f"{key}.paths_index.npy"))


def affected_sources(paths: np.ndarray, paths_index: np.ndarray, removed_edges: Sequence[int],
                     slowed_edges: Sequence[int]) -> set[int]:
    """Points (positions in the table) with at least one pair whose stored path uses a changed edge."""
    k = int(round(math.sqrt(len(paths_index) - 1)))
    changed = np.union1d(np.asarray(list(removed_edges), dtype=np.int64),
                         np.asarray(list(slowed_edges), dtype=np.int64))
    if not len(changed) or not len(paths):
        return set()
    bad = np.concatenate([[0], np.cumsum(np.isin(paths, changed))])
    index = np.asarray(paths_index, dtype=np.int64)
    per_pair = (bad[index[1:]] - bad[index[:-1]]).reshape(k, k)
    return set(np.flatnonzero(per_pair.sum(axis=1) > 0).tolist())


class TravelTimes:
    """Travel-time rows on a corridor (``None`` = the whole city) under a set of closures.

    ``searches`` counts sources searched, ``hits`` sources served from the shared cache and
    ``reused`` sources served from the pre-closure ``reuse`` table. ``widened`` is set when
    :meth:`ensure` found a requested target unreachable inside the corridor and moved the search to
    the whole graph.
    """

    def __init__(self, graph: Graph, corridor: Corridor | None, closures: Sequence[Closure] = (),
                 reuse: ReuseTable | None = None) -> None:
        self.graph = graph
        self.corridor = corridor
        self.closures = tuple(closures)
        self.closure_key = closure_key(self.closures)
        self.removed, self.extra = edge_changes(graph, self.closures)
        self.searches = 0
        self.hits = 0
        self.reused = 0
        self.widened = False
        self._matrix: tuple[csr_matrix, np.ndarray, np.ndarray] | None = None
        self.reuse = reuse
        self._affected: set[int] | None = None
        if reuse is not None and (reuse.graph_version != graph.version
                                  or not math.isclose(reuse.speed_factor, graph.speed_factor)):
            raise ValueError(f"reuse table {reuse.key} was built for graph {reuse.graph_version} at speed "
                             f"factor {reuse.speed_factor}, not {graph.version} at {graph.speed_factor}")

    @property
    def area_key(self) -> str:
        """The corridor key, or ``"city"`` for the whole graph."""
        return self.corridor.key if self.corridor is not None else CITY

    @property
    def area_id(self) -> str:
        """The corridor's :attr:`Corridor.ident`, or ``"city"``: what cache and reuse entries match on."""
        return self.corridor.ident if self.corridor is not None else CITY

    def _local(self, nodes: np.ndarray) -> np.ndarray:
        """Corridor positions of graph nodes; -1 for nodes outside the corridor."""
        nodes = np.asarray(nodes, dtype=np.int64)
        if self.corridor is None:
            return nodes
        cn = self.corridor.nodes
        if not len(cn):
            return np.full(len(nodes), -1, dtype=np.int64)
        pos = np.minimum(np.searchsorted(cn, nodes), len(cn) - 1)
        return np.where(cn[pos] == nodes, pos, -1)

    def _search_matrix(self) -> tuple[csr_matrix, np.ndarray, np.ndarray]:
        """CSR matrix of the corridor's edges minus removed ones, slowed edges made slower."""
        if self._matrix is None:
            g = self.graph
            if self.corridor is None and not len(self.removed) and not self.extra:
                self._matrix = g.city_matrix()
                return self._matrix
            edges = (np.arange(g.n_edges, dtype=np.int64) if self.corridor is None
                     else self.corridor.edges)
            if len(self.removed):
                edges = edges[~np.isin(edges, self.removed)]
            w = g.edge_seconds[edges].copy()
            if self.extra:
                slowed = np.fromiter(self.extra, dtype=np.int64)
                add = np.fromiter(self.extra.values(), dtype=np.float64)
                # Extra seconds are in profile time; scale them as the edge was calibrated.
                profile = g.profile_edge_s[slowed]
                ratio = np.where(profile > 0, g.edge_seconds[slowed] / np.where(profile > 0, profile, 1.0),
                                 g.speed_factor)
                pos = np.minimum(np.searchsorted(edges, slowed), max(len(edges) - 1, 0))
                hit = (edges[pos] == slowed) if len(edges) else np.zeros(len(slowed), dtype=bool)
                np.add.at(w, pos[hit], (add * ratio)[hit])
            u = self._local(np.asarray(g.edge_u)[edges])
            v = self._local(np.asarray(g.edge_v)[edges])
            n = g.n_nodes if self.corridor is None else len(self.corridor.nodes)
            self._matrix = _csr(n, u, v, w, edges)
        return self._matrix

    def _expand(self, row: np.ndarray) -> np.ndarray:
        if self.corridor is None:
            return row
        full = np.full(self.graph.n_nodes, np.inf, dtype=np.float32)
        full[self.corridor.nodes] = row
        return full

    def _reusable(self, targets: Sequence[int] | None) -> dict[int, int]:
        """Graph node -> table position for sources that may be served from the reuse table."""
        table = self.reuse
        if table is None or targets is None or self.widened or table.corridor_key != self.area_id:
            return {}
        points = table.point_nodes.tolist()
        if not set(int(t) for t in targets) <= set(points):
            return {}
        if self._affected is None:
            self._affected = affected_sources(table.paths, table.paths_index, self.removed.tolist(),
                                              list(self.extra))
        positions: dict[int, list[int]] = {}
        for i, nd in enumerate(points):
            positions.setdefault(int(nd), []).append(i)
        return {nd: pos[0] for nd, pos in positions.items() if not set(pos) & self._affected}

    def rows(self, sources: Sequence[int], targets: Sequence[int] | None = None) -> dict[int, np.ndarray]:
        """Seconds from each source graph node to every graph node (``inf`` when unreachable).

        Rows are ``float32`` arrays of graph length and must not be modified. Sources not in the
        cache are searched with one ``dijkstra`` call. When ``targets`` is given, a source whose row
        can be served from the reuse table is served from it; such a row is correct only at the
        reuse table's points (``inf`` elsewhere), so callers read it only at ``targets``.
        """
        out: dict[int, np.ndarray] = {}
        missing: list[int] = []
        reusable = self._reusable(targets)
        for s in dict.fromkeys(int(x) for x in sources):
            key = (self.graph.cache_id, self.area_id, self.closure_key, s)
            cached = ROW_CACHE.get(key)
            if cached is not None:
                ROW_CACHE.move_to_end(key)
                self.hits += 1
                out[s] = self._expand(cached)
            elif s in reusable:
                row = np.full(self.graph.n_nodes, np.inf, dtype=np.float32)
                row[self.reuse.point_nodes] = self.reuse.pre[reusable[s]]
                row.flags.writeable = False
                self.reused += 1
                out[s] = row
            else:
                missing.append(s)
        if not missing:
            return out
        local = self._local(np.asarray(missing, dtype=np.int64))
        inside = local >= 0
        for s in np.asarray(missing)[~inside].tolist():
            out[int(s)] = np.full(self.graph.n_nodes, np.inf, dtype=np.float32)
        if inside.any():
            dist = dijkstra(self._search_matrix()[0], directed=True, indices=local[inside])
            dist = np.atleast_2d(dist).astype(np.float32)
            for s, row in zip(np.asarray(missing)[inside].tolist(), dist):
                row = row.copy()              # own memory: an evicted row frees its share
                self.searches += 1
                _cache_put((self.graph.cache_id, self.area_id, self.closure_key, int(s)), row)
                out[int(s)] = self._expand(row)
        return out

    def ensure(self, sources: Sequence[int], targets: Sequence[int]) -> dict[int, np.ndarray]:
        """Rows for ``sources``; if a target is unreachable inside the corridor, retry once city-wide.

        Pass only targets that should be reachable (not points closed by a full block), or the
        search widens for nothing.
        """
        got = self.rows(sources, targets)
        if self.corridor is None:
            return got
        t = np.asarray(list(targets), dtype=np.int64)
        if all(np.isfinite(got[int(s)][t]).all() for s in sources):
            return got
        self.corridor = None
        self._matrix = None
        self.widened = True
        return self.rows(sources, targets)

    def path_edges(self, source: int, targets: Sequence[int]) -> list[np.ndarray]:
        """Graph edges on the fastest path from ``source`` to each target (empty if unreachable)."""
        matrix, pair_keys, pair_edges = self._search_matrix()
        n = matrix.shape[0]
        targets_local = self._local(np.asarray(list(targets), dtype=np.int64))
        src = int(self._local(np.asarray([source]))[0])
        if src < 0:
            return [np.zeros(0, dtype=np.int64) for _ in targets_local]
        _, pred = dijkstra(matrix, directed=True, indices=src, return_predecessors=True)
        out = []
        for t in targets_local.tolist():
            nodes = _path_from(pred, src, t) if t >= 0 else []
            if len(nodes) < 2:
                out.append(np.zeros(0, dtype=np.int64))
                continue
            keys = np.asarray(nodes[:-1], dtype=np.int64) * n + np.asarray(nodes[1:], dtype=np.int64)
            out.append(pair_edges[np.searchsorted(pair_keys, keys)])
        return out


def reuse_table(graph: Graph, corridor: Corridor | None, point_nodes: Sequence[int],
                key: str | None = None) -> ReuseTable:
    """Build the pre-closure table of one route's points (route stops, then campus) on ``corridor``."""
    tt = TravelTimes(graph, corridor)
    points = np.asarray(list(point_nodes), dtype=np.int64)
    k = len(points)
    pre = np.full((k, k), np.inf, dtype=np.float32)
    rows = tt.rows(points.tolist())
    paths: list[np.ndarray] = []
    index = [0]
    for i, s in enumerate(points.tolist()):
        pre[i] = rows[s][points]
        for edges in tt.path_edges(s, points.tolist()):
            paths.append(edges.astype(np.int32))
            index.append(index[-1] + len(edges))
    key = key if key is not None else tt.area_key
    flat = np.concatenate(paths) if paths else np.zeros(0, dtype=np.int32)
    return ReuseTable(key, tt.area_id, graph.version, graph.speed_factor, points, pre,
                      flat.astype(np.int32), np.asarray(index, dtype=np.int64))


def problem_rows(tt: TravelTimes, point_nodes: Sequence[int], start_node: int, campus_node: int,
                 closed: Sequence[bool] = ()) -> Callable[[list[int]], dict[int, np.ndarray]]:
    """The ``rows`` function of a :class:`reroute.model.Problem` whose points sit at ``point_nodes``.

    Problem node ``i < P`` is point ``i``; ``P`` is the start and ``P + 1`` campus. Entries to or
    from a point flagged in ``closed`` are infinite.

    The start is left out of the targets passed to :meth:`TravelTimes.rows`, so a row reused from
    a route's pre-closure table (which holds the route's points and campus, not the bus position)
    can serve a point; the start column of such a row is ``inf``. The solver never drives back to
    the start, so it never reads that column.
    """
    p = len(point_nodes)
    if len(closed) > p:
        raise ValueError(f"closed has {len(closed)} flags for {p} points")
    mapping = np.asarray(list(point_nodes) + [start_node, campus_node], dtype=np.int64)
    shut = np.zeros(p + 2, dtype=bool)
    shut[:len(closed)] = np.asarray(list(closed), dtype=bool)
    targets = mapping.tolist()
    not_start = targets[:p] + targets[p + 1:]

    def rows(nodes: list[int]) -> dict[int, np.ndarray]:
        got = tt.rows([targets[n] for n in nodes], targets=not_start)
        out = {}
        for n in nodes:
            row = got[targets[n]][mapping].astype(np.float64)
            row[shut] = np.inf
            if shut[n]:
                row[:] = np.inf
            out[n] = row
        return out

    return rows


def graph_info(graph: Graph) -> dict[str, Any]:
    """Counts and settings of a graph, for printed reports and result files."""
    return {"version": graph.version, "speed_factor": graph.speed_factor, "nodes": graph.n_nodes,
            "edges": graph.n_edges, "segments": len(graph.seg_from)}
