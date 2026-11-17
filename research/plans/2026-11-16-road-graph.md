# Road Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a compact road graph of Karachi from the map file OSRM was built from, and the code that applies closures to it and answers travel-time rows inside 512 MB and 0.1 CPU.

**Architecture:** An offline script turns the map file into arrays: a full table of directed road segments (needed to name segments to OSRM and to match closures by geometry) and a compressed graph for searching. At run time `graph.py` loads the arrays memory-mapped, searches only a per-route corridor, and caches rows. `closure.py` turns circles into closed or slowed segments, graph edges and OSRM speed-file rows.

**Tech Stack:** Python 3.10+, `numpy`, `scipy.sparse.csgraph`; `pyosmium` for the offline build only. Tests use `unittest` and a hand-made toy map, so they need neither `pyosmium` nor the map file.

**Spec:** `research/plans/2026-11-15-rerouting-plan.md` (version 2), Section 6.2 and work items B1 to B4. Uses the `Problem` interface from `research/plans/2026-11-16-reroute-solver-core.md`.

## Global Constraints

- `research/reroute/graph.py` and `closure.py` import only `numpy`, `scipy` and the standard library. No file access except `Graph.load`.
- Arrays are stored as separate `.npy` files, never `.npz`: `.npz` cannot be memory-mapped.
- Closed roads are removed from the edge list before a search. Never represent a closure as a zero weight.
- Closures are matched to roads by geometry: a segment is affected if any point sampled every 50 m along it lies inside the closure.
- Calibration rule, fixed before the test: median absolute error against the saved OSRM matrix at most 15%, median signed error not negative.
- Speeds by road class, km/h, from OSRM's car profile: motorway 90, motorway_link 45, trunk 85, trunk_link 40, primary 65, primary_link 30, secondary 55, secondary_link 25, tertiary 40, tertiary_link 20, unclassified 25, residential 25, living_street 10, service 15. Other classes are not roads a bus may use.
- Tests run from `research/` with: `python -m unittest discover -s reroute/tests -t . -v`
- Commit messages start with `Research:` and carry no co-author line.

## Review Focus

1. **A point far from any road** (a stop pin in a park): `nearest_node` returns the distance, and the builder prints every point snapped more than 200 m. Task 2.
2. **A closure that touches no road**: zero closed segments, searches unchanged, no error. Task 3.
3. **Source or target outside the corridor**: the row entry is infinite, not an exception. Task 4.
4. **A closure that cuts the corridor in two**: `TravelTimes` retries once on the whole graph and sets `widened`. Task 4.
5. **A ring road with no junction** (every node passes through): compression keeps one node, so the ring is not lost. Task 1.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `research/build_graph.py` | Offline: read the map file, build tables, write `data/graph_karachi_v1/` |
| `research/reroute/roadnet.py` | `Way`, `SPEED_KMH`, `build_tables(ways, keep_ids)`: pure, tested |
| `research/reroute/graph.py` | `Graph`, `Corridor`, `corridor_for`, `shortest_path_nodes`, `TravelTimes`, `problem_rows` |
| `research/reroute/closure.py` | `Closure`, `closed_segments`, `edge_changes`, `osrm_speed_rows`, `closed_points`, `closure_key` |
| `research/build_corridors.py` | Offline: one corridor per current route, written to `data/corridors_fall2026_v1/` |
| `research/calibrate_graph.py` | Offline: fit the speed factor against matrix M1, print the errors |
| `research/measure_graph.py` | Timings and memory under the free-tier limits (gate G1) |
| `research/reroute/tests/toymap.py` | The toy map below |
| `research/reroute/tests/test_roadnet.py`, `test_closure.py`, `test_graph.py` | Tests |

**The toy map.** Coordinates in degrees; at this latitude 0.001 of longitude is about 100.8 m and 0.001 of latitude about 111.2 m.

```python
from reroute.roadnet import Way
N = {1: (24.900, 67.000), 2: (24.900, 67.001), 3: (24.900, 67.002), 4: (24.900, 67.003),
     5: (24.901, 67.002), 6: (24.902, 67.002), 7: (24.910, 67.000), 8: (24.910, 67.010)}
def way(ids, highway, oneway=""):
    return Way([(i, *N[i]) for i in ids], highway, oneway)
TOY = [way([1, 2, 3, 4], "residential"),          # two-way street, node 2 is a pass-through
       way([3, 5, 6], "primary", "yes"),          # one-way, node 5 is a pass-through
       way([7, 8], "residential")]                # one long segment, about 1 km
```

Expected, worked from the speeds: segment 1 to 2 is about 100.8 m and 14.5 s; the compressed edge 1 to 3 about 201.6 m and 29.0 s; edge 3 to 6 about 222.4 m and 12.3 s; so node 1 to node 6 takes about 41.3 s and node 6 to node 1 is unreachable.

---

### Task 1: Tables from ways

**Files:**
- Create: `research/reroute/roadnet.py`, `research/reroute/tests/toymap.py`
- Test: `research/reroute/tests/test_roadnet.py`

**Interfaces:**
- Produces:
  - `Way(nodes: list[tuple[int, float, float]], highway: str, oneway: str = "")`: nodes are `(map node id, lat, lng)` in way order.
  - `SPEED_KMH: dict[str, float]` with the values in Global Constraints.
  - `haversine_m(lat1, lng1, lat2, lng2) -> float`.
  - `build_tables(ways: Iterable[Way], keep_ids: Iterable[int] = ()) -> dict[str, np.ndarray]` with keys:
    - Segments, one row per direction a vehicle may travel: `seg_from`, `seg_to` (int64 map node ids), `seg_lat1`, `seg_lng1`, `seg_lat2`, `seg_lng2` (float64), `seg_m`, `seg_s` (float32), `seg_edge` (int32, the compressed edge that contains the segment).
    - Graph nodes: `node_id` (int64), `node_lat`, `node_lng` (float64).
    - Compressed edges: `edge_u`, `edge_v` (int32 indices into the node arrays), `edge_m`, `edge_s` (float32).
  - Rules: ways whose `highway` is not in `SPEED_KMH` are skipped. `oneway` of `yes`, `true` or `1` allows only way order; `-1` or `reverse` only the reverse; anything else both. A node is removed by compression when it has exactly two distinct neighbours, the roads on both sides allow the same directions, and its id is not in `keep_ids`. A closed ring with no kept node keeps its lowest-id node. Parallel edges between the same two nodes are kept as separate edges.

- [ ] **Step 1: Write the failing tests**

```python
import unittest, numpy as np
from reroute.roadnet import build_tables, Way, haversine_m
from reroute.tests.toymap import TOY, N, way

def pairs(t, a, b):
    ids = t["node_id"]
    return sorted((int(ids[u]), int(ids[v])) for u, v in zip(t[a], t[b]))

class BuildTablesTests(unittest.TestCase):
    def test_segments_follow_direction_rules(self):
        t = build_tables(TOY)
        segs = sorted(zip(t["seg_from"].tolist(), t["seg_to"].tolist()))
        self.assertEqual(segs, [(1, 2), (2, 1), (2, 3), (3, 2), (3, 4), (3, 5), (4, 3), (5, 6), (7, 8), (8, 7)])

    def test_pass_through_nodes_are_compressed_away(self):
        t = build_tables(TOY)
        self.assertEqual(sorted(t["node_id"].tolist()), [1, 3, 4, 6, 7, 8])
        self.assertEqual(pairs(t, "edge_u", "edge_v"), [(1, 3), (3, 1), (3, 4), (3, 6), (4, 3), (7, 8), (8, 7)])

    def test_kept_ids_survive_compression(self):
        t = build_tables(TOY, keep_ids=[2])
        self.assertIn(2, t["node_id"].tolist())
        self.assertIn((1, 2), pairs(t, "edge_u", "edge_v"))

    def test_lengths_and_times(self):
        t = build_tables(TOY)
        e = {p: i for i, p in enumerate(zip(t["node_id"][t["edge_u"]].tolist(), t["node_id"][t["edge_v"]].tolist()))}
        self.assertAlmostEqual(float(t["edge_m"][e[(1, 3)]]), 201.6, delta=1.0)
        self.assertAlmostEqual(float(t["edge_s"][e[(1, 3)]]), 29.0, delta=0.2)
        self.assertAlmostEqual(float(t["edge_s"][e[(3, 6)]]), 12.3, delta=0.2)

    def test_every_segment_points_at_its_edge(self):
        t = build_tables(TOY)
        for f, to, e in zip(t["seg_from"].tolist(), t["seg_to"].tolist(), t["seg_edge"].tolist()):
            if (f, to) in ((1, 2), (2, 3)):
                self.assertEqual((int(t["node_id"][t["edge_u"][e]]), int(t["node_id"][t["edge_v"][e]])), (1, 3))
        self.assertAlmostEqual(float(t["seg_s"].sum()), float(t["edge_s"].sum()), delta=0.01)

    def test_unknown_road_class_is_skipped(self):
        self.assertEqual(len(build_tables([way([1, 2], "footway")])["seg_from"]), 0)

    def test_reverse_oneway(self):
        t = build_tables([way([1, 2], "residential", "-1")])
        self.assertEqual(list(zip(t["seg_from"].tolist(), t["seg_to"].tolist())), [(2, 1)])

    def test_ring_without_a_junction_keeps_one_node(self):
        ring = [Way([(1, 24.9, 67.0), (2, 24.9, 67.001), (3, 24.901, 67.001), (1, 24.9, 67.0)], "residential")]
        t = build_tables(ring)
        self.assertEqual(t["node_id"].tolist(), [1])
        self.assertEqual(len(t["edge_u"]), 2)            # the ring, once in each direction
```

- [ ] **Step 2: Run and confirm failure** (`No module named 'reroute.roadnet'`).
- [ ] **Step 3: Implement `roadnet.py` and `toymap.py`.**
- [ ] **Step 4: Run and confirm the tests pass.**
- [ ] **Step 5: Commit** with message `Research: road tables from map ways`.

---

### Task 2: The offline build script

**Files:**
- Create: `research/build_graph.py`
- Modify: `research/requirements.txt` (add `scipy` and `pyosmium`), `research/README.md` (layout table and a "Build the road graph" section with the command)

**Interfaces:**
- Consumes: `build_tables` from Task 1.
- Produces: `research/data/graph_karachi_v1/` holding one `.npy` file per key of `build_tables`, plus `meta.json`: `{"version": "karachi_v1", "source_sha256": ..., "built_at": ..., "nodes": N, "edges": E, "segments": S, "speed_factor": 1.0, "keep_points": 312, "far_snaps": [[name, metres], ...]}`.
- Command: `python research/build_graph.py PATH/karachi.osm.pbf`.

- [ ] **Step 1: Write `read_ways(pbf_path) -> list[Way]`** with `osmium.SimpleHandler` and `apply_file(pbf_path, locations=True)`. Keep ways with a `highway` tag in `SPEED_KMH`; skip ways tagged `area=yes`, `access` of `no` or `private`, or `motor_vehicle=no`. A way tagged `junction=roundabout`, or of class `motorway` or `motorway_link`, is one-way unless it carries its own `oneway` tag.
- [ ] **Step 2: Write `main`.** Read `data/instance_fall2026_v1.json`; for campus and every stop find the nearest map node on a kept way and pass those node ids as `keep_ids`, so every stop is a graph node. Write the arrays and `meta.json`. Print node, edge and segment counts and every point snapped more than 200 m.
- [ ] **Step 3: Run on the real map file** (on the machine that has it).

Expected: the node count is of the same order as OSRM's 409,528 from run N1 (the compression rules differ, so not equal); no stop is listed more than 250 m from a road except Boat Basin (224 m in run M1). If the counts differ by more than a factor of three, stop and check the way filter.

- [ ] **Step 4: Commit the script and the arrays** with message `Research: road graph karachi_v1 built from the N1 map file`. Put the SHA-256 and the counts in the logbook.

---

### Task 3: Closures

**Files:**
- Create: `research/reroute/closure.py`
- Test: `research/reroute/tests/test_closure.py`

**Interfaces:**
- Consumes: the table dictionary of Task 1 (`Graph` in Task 4 exposes the same arrays as attributes; these functions take anything with those names as attributes or keys through a small accessor).
- Produces:
  - `Closure(id: str, circles: tuple[tuple[float, float, float], ...], factor: float)`: circles are `(lat, lng, radius_m)`; `factor` 0 is a full block, between 0 and 1 a slowed road.
  - `closure_key(closures: Sequence[Closure]) -> str`: a stable hash, independent of order.
  - `closed_segments(tables, closure: Closure, sample_m: float = 50.0) -> np.ndarray`: indices of segments with any sampled point (both ends and every `sample_m` between) inside any circle.
  - `edge_changes(tables, closures: Sequence[Closure]) -> tuple[np.ndarray, dict[int, float]]`: the indices of edges to remove (any segment fully blocked) and, for the others, extra seconds per edge: the sum over slowed segments of `seg_s x (1 / factor - 1)`. Where closures overlap, a segment takes the lowest factor.
  - `osrm_speed_rows(tables, closure: Closure) -> list[tuple[int, int, int]]`: `(seg_from, seg_to, km/h)` per affected segment; km/h is 0 for a full block, otherwise the segment's own speed times the factor, at least 1.
  - `closed_points(point_lat, point_lng, closures) -> np.ndarray` of bool: true where a point lies inside a full-block circle. This is the reachability rule: such a point cannot be visited in either travel-time source.

- [ ] **Step 1: Write the failing tests**

```python
import unittest, numpy as np
from reroute.roadnet import build_tables
from reroute.closure import (Closure, closed_segments, edge_changes, osrm_speed_rows, closed_points, closure_key)
from reroute.tests.toymap import TOY, N

T = build_tables(TOY)
def seg_pairs(idx):
    return sorted((int(T["seg_from"][i]), int(T["seg_to"][i])) for i in idx)
AT_NODE_2 = Closure("c1", ((24.900, 67.001, 30.0),), 0.0)

class ClosureTests(unittest.TestCase):
    def test_circle_at_a_node_closes_the_segments_that_touch_it(self):
        self.assertEqual(seg_pairs(closed_segments(T, AT_NODE_2)), [(1, 2), (2, 1), (2, 3), (3, 2)])

    def test_long_segment_with_no_node_inside_is_still_closed(self):
        mid = Closure("c2", ((24.910, 67.005, 50.0),), 0.0)
        self.assertEqual(seg_pairs(closed_segments(T, mid)), [(7, 8), (8, 7)])

    def test_closure_touching_no_road_closes_nothing(self):
        self.assertEqual(len(closed_segments(T, Closure("c3", ((25.5, 67.5, 200.0),), 0.0))), 0)

    def test_full_block_removes_edges(self):
        removed, extra = edge_changes(T, [AT_NODE_2])
        ends = sorted((int(T["node_id"][T["edge_u"][e]]), int(T["node_id"][T["edge_v"][e]])) for e in removed)
        self.assertEqual((ends, extra), ([(1, 3), (3, 1)], {}))

    def test_slowed_road_adds_time(self):
        removed, extra = edge_changes(T, [Closure("c4", ((24.900, 67.001, 30.0),), 0.5)])
        self.assertEqual(len(removed), 0)
        self.assertEqual(len(extra), 2)
        for seconds in extra.values():
            self.assertAlmostEqual(seconds, 29.0, delta=0.2)      # the edge takes twice as long

    def test_overlapping_closures_take_the_lowest_factor(self):
        removed, _ = edge_changes(T, [Closure("a", ((24.900, 67.001, 30.0),), 0.5), AT_NODE_2])
        self.assertEqual(len(removed), 2)

    def test_osrm_rows(self):
        self.assertEqual(sorted(osrm_speed_rows(T, AT_NODE_2)), [(1, 2, 0), (2, 1, 0), (2, 3, 0), (3, 2, 0)])
        slowed = osrm_speed_rows(T, Closure("c4", ((24.900, 67.001, 30.0),), 0.4))
        self.assertEqual({kmh for _, _, kmh in slowed}, {10})         # residential 25 km/h x 0.4

    def test_closed_points(self):
        lat, lng = np.array([24.900, 24.900]), np.array([67.001, 67.003])
        self.assertEqual(closed_points(lat, lng, [AT_NODE_2]).tolist(), [True, False])
        self.assertEqual(closed_points(lat, lng, [Closure("s", ((24.900, 67.001, 30.0),), 0.5)]).tolist(), [False, False])

    def test_key_ignores_order(self):
        a, b = AT_NODE_2, Closure("c2", ((24.910, 67.005, 50.0),), 0.0)
        self.assertEqual(closure_key([a, b]), closure_key([b, a]))
        self.assertNotEqual(closure_key([a]), closure_key([b]))
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `closure.py`.** To find candidate segments quickly, bucket segment midpoints in a plain latitude and longitude grid of 0.005 degrees and test only buckets a circle can reach, widened by the longest segment's half-length. (The work plan mentions H3 cells as the index; a plain grid does the same job with no extra dependency.)
- [ ] **Step 4: Run and confirm the tests pass.**
- [ ] **Step 5: Commit** with message `Research: closures matched to roads by geometry`.

---

### Task 4: Graph, corridors and travel-time rows

**Files:**
- Create: `research/reroute/graph.py`
- Test: `research/reroute/tests/test_graph.py`

**Interfaces:**
- Consumes: Tasks 1 and 3; `Problem` and its `rows` contract from the solver-core plan (a function `rows(nodes: list[int]) -> dict[int, Sequence[float]]` over P + 2 problem nodes, start at P, campus at P + 1).
- Produces:
  - `Graph(tables: dict, version: str = "toy", speed_factor: float = 1.0)`; `Graph.load(directory: str | Path, mmap: bool = True) -> Graph` reads the `.npy` files with `mmap_mode="r"` and `speed_factor` and `version` from `meta.json`. Attributes: every table array by name, `n_nodes`, `n_edges`, `version`. `Graph.edge_seconds` is `edge_s x speed_factor`.
  - `Graph.nearest_node(lat: float, lng: float) -> tuple[int, float]`: graph node index and distance in metres.
  - `Corridor(key: str, nodes: np.ndarray, edges: np.ndarray)`: graph node indices and graph edge indices with both ends in `nodes`.
  - `shortest_path_nodes(graph: Graph, a: int, b: int) -> list[int]`: node indices from `a` to `b` on the whole graph, empty when unreachable.
  - `corridor_for(graph: Graph, key: str, path_nodes: Sequence[int], buffer_m: float = 1500.0) -> Corridor`: every node within `buffer_m` of any node in `path_nodes`.
  - `TravelTimes(graph: Graph, corridor: Corridor | None, closures: Sequence[Closure] = ())`. `corridor=None` searches the whole graph.
    - `rows(sources: Sequence[int]) -> dict[int, np.ndarray]`: for each source graph node, seconds to every graph node (`inf` when unreachable or outside the corridor). One call to `scipy.sparse.csgraph.dijkstra` for the sources not already cached.
    - `searches: int`, `hits: int`: sources searched and sources served from the cache.
    - `widened: bool`: set when a requested target was unreachable inside the corridor and the search was repeated on the whole graph.
    - `ensure(sources, targets)`: runs the searches and, if any requested target is unreachable from any source inside the corridor, repeats once on the whole graph and sets `widened`.
  - `ROW_CACHE` at module level, keyed `(graph.version, corridor key or "city", closure_key, source node)`, shared by every `TravelTimes`. `clear_row_cache()` empties it. It holds at most `ROW_CACHE_MAX = 256` rows and drops the least recently used. Rows are stored at corridor length (`float32`) and expanded to graph length only when returned: a row over the whole city is about 1.6 MB, so an unbounded cache of full-length rows would fill 512 MB after a few hundred searches.
  - `problem_rows(tt: TravelTimes, point_nodes: Sequence[int], start_node: int, campus_node: int, closed: Sequence[bool] = ()) -> Callable`: the `rows` function for a `Problem` whose points sit at `point_nodes`. Entries to or from a point flagged in `closed` are infinite.

- [ ] **Step 1: Write the failing tests**

```python
import math, unittest, numpy as np
from reroute.roadnet import build_tables
from reroute.graph import (Graph, corridor_for, shortest_path_nodes, TravelTimes, problem_rows, clear_row_cache)
from reroute.closure import Closure
from reroute.tests.toymap import TOY

def graph(keep=()):
    return Graph(build_tables(TOY, keep_ids=keep))
def node(g, map_id):
    return int(np.where(g.node_id == map_id)[0][0])
AT_NODE_2 = Closure("c1", ((24.900, 67.001, 30.0),), 0.0)

class GraphTests(unittest.TestCase):
    def setUp(self):
        clear_row_cache()

    def test_one_way_is_respected(self):
        g = graph(); tt = TravelTimes(g, None)
        self.assertAlmostEqual(float(tt.rows([node(g, 1)])[node(g, 1)][node(g, 6)]), 41.3, delta=0.4)
        self.assertEqual(float(tt.rows([node(g, 6)])[node(g, 6)][node(g, 1)]), math.inf)

    def test_blocked_road_is_avoided(self):
        g = graph(); tt = TravelTimes(g, None, [AT_NODE_2])
        self.assertEqual(float(tt.rows([node(g, 1)])[node(g, 1)][node(g, 6)]), math.inf)
        self.assertAlmostEqual(float(tt.rows([node(g, 4)])[node(g, 4)][node(g, 6)]), 26.8, delta=0.4)

    def test_slowed_road_costs_more(self):
        g = graph(); tt = TravelTimes(g, None, [Closure("s", ((24.900, 67.001, 30.0),), 0.5)])
        self.assertAlmostEqual(float(tt.rows([node(g, 1)])[node(g, 1)][node(g, 6)]), 70.3, delta=0.6)

    def test_speed_factor_scales_every_time(self):
        g = Graph(build_tables(TOY), speed_factor=2.0)
        self.assertAlmostEqual(float(TravelTimes(g, None).rows([node(g, 1)])[node(g, 1)][node(g, 6)]), 82.6, delta=0.8)

    def test_nearest_node(self):
        g = graph(keep=[2])
        idx, metres = g.nearest_node(24.9001, 67.001)
        self.assertEqual(int(g.node_id[idx]), 2)
        self.assertAlmostEqual(metres, 11.1, delta=1.0)

    def test_corridor_keeps_only_nearby_nodes(self):
        g = graph(); path = shortest_path_nodes(g, node(g, 1), node(g, 6))
        self.assertEqual([int(g.node_id[i]) for i in path], [1, 3, 6])
        near = corridor_for(g, "r", path, buffer_m=50)
        self.assertNotIn(4, g.node_id[near.nodes].tolist())
        self.assertIn(4, g.node_id[corridor_for(g, "r", path, buffer_m=150).nodes].tolist())

    def test_target_outside_corridor_is_infinite_not_an_error(self):
        g = graph(); c = corridor_for(g, "r", shortest_path_nodes(g, node(g, 1), node(g, 6)), buffer_m=50)
        self.assertEqual(float(TravelTimes(g, c).rows([node(g, 1)])[node(g, 1)][node(g, 4)]), math.inf)

    def test_ensure_widens_once_when_the_corridor_is_cut(self):
        g = graph(); c = corridor_for(g, "r", shortest_path_nodes(g, node(g, 1), node(g, 6)), buffer_m=50)
        tt = TravelTimes(g, c)
        tt.ensure([node(g, 1)], [node(g, 4)])
        self.assertTrue(tt.widened)
        self.assertAlmostEqual(float(tt.rows([node(g, 1)])[node(g, 1)][node(g, 4)]), 43.5, delta=0.5)

    def test_rows_are_cached_and_shared_between_instances(self):
        g = graph(); a = TravelTimes(g, None); a.rows([node(g, 1)]); a.rows([node(g, 1)])
        self.assertEqual((a.searches, a.hits), (1, 1))
        b = TravelTimes(g, None); b.rows([node(g, 1)])
        self.assertEqual((b.searches, b.hits), (0, 1))
        c = TravelTimes(g, None, [AT_NODE_2]); c.rows([node(g, 1)])
        self.assertEqual(c.searches, 1)                       # a different closure is a different cache entry

    def test_cache_is_bounded(self):
        import reroute.graph as G
        old, G.ROW_CACHE_MAX = G.ROW_CACHE_MAX, 2
        try:
            g = graph(); tt = TravelTimes(g, None)
            for map_id in (1, 3, 4, 6):
                tt.rows([node(g, map_id)])
            self.assertLessEqual(len(G.ROW_CACHE), 2)
            tt.rows([node(g, 1)])                             # dropped earlier, so searched again
            self.assertEqual(tt.searches, 5)
        finally:
            G.ROW_CACHE_MAX = old

    def test_problem_rows_match_the_solver_contract(self):
        g = graph(keep=[2]); tt = TravelTimes(g, None)
        rows = problem_rows(tt, [node(g, 2), node(g, 3)], start_node=node(g, 1), campus_node=node(g, 6), closed=[False, True])
        out = rows([2, 0])                                   # problem node 2 is the start, 0 is the first point
        self.assertEqual(len(out[2]), 4)
        self.assertAlmostEqual(out[2][0], 14.5, delta=0.3)   # start to the first point
        self.assertEqual(out[2][1], math.inf)                # the second point is closed
        self.assertAlmostEqual(out[2][3], 41.3, delta=0.4)   # start to campus
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `graph.py`.** Build one `scipy.sparse.csr_matrix` per `TravelTimes` from the corridor's edges, minus the removed edges, with `edge_seconds` plus any extra seconds. Where two edges join the same pair of nodes, keep the smaller time (a sparse matrix would otherwise add them). Rows are stored as `float32`.
- [ ] **Step 4: Run and confirm the tests pass.**
- [ ] **Step 5: Commit** with message `Research: road graph search with corridors, closures and a shared row cache`.

---

### Task 5: Corridors for the current routes

**Files:**
- Create: `research/build_corridors.py`
- Modify: `research/README.md` (command)

**Interfaces:**
- Consumes: `Graph.load`, `shortest_path_nodes`, `corridor_for`.
- Produces: `research/data/corridors_fall2026_v1/<contractor>-<route code>.nodes.npy` and `.edges.npy` for each of the 52 current routes, and `index.json` listing each route's key, node count, edge count and the stops whose own node falls outside the corridor (expected: none).
- Also produces, in `research/reroute/graph.py`: `load_corridor(directory: str | Path, key: str) -> Corridor | None`, which returns `None` when the route has no corridor file. The experiment runner uses it.
- Command: `python research/build_corridors.py`.

- [ ] **Step 1: Write the script and `load_corridor`.** For each current route in `data/instance_fall2026_v1.json`: the path is the shortest path from the first stop through each stop in order to campus; the corridor is `corridor_for(graph, key, path, buffer_m=1500)`.
- [ ] **Step 2: Run it** and check the printed table: every route has a corridor, and node counts are far below the whole graph's.
- [ ] **Step 3: Commit** with message `Research: one search corridor per current route`. Record the smallest, median and largest corridor size in the logbook.

---

### Task 6: Calibration against the saved OSRM matrix

**Files:**
- Create: `research/calibrate_graph.py`

**Interfaces:**
- Consumes: `Graph.load`, `TravelTimes`, `data/matrix_fall2026_v1.json`.
- Produces: an updated `speed_factor` in `data/graph_karachi_v1/meta.json`, and printed error figures. `--per-class` fits one factor per road class instead and rewrites `edge_s.npy`.
- Command: `python research/calibrate_graph.py`.

- [ ] **Step 1: Write the script.** For both contractors, compute graph times on the whole city graph between every pair of matrix nodes (one search per node). The factor is the **60th percentile** of OSRM time divided by graph time over all pairs with a finite graph time, so that the scaled graph runs slightly slow, not fast. Print: the factor; median absolute error; median signed error; the share of pairs the graph finds unreachable.
- [ ] **Step 2: Run it and apply the rule.** Pass: median absolute error at most 15% and median signed error not negative. If it fails, run with `--per-class` and check again. If it still fails, stop and follow the fallback in the work plan's Section 11.
- [ ] **Step 3: Commit** with message `Research: graph speed factor calibrated against matrix M1`. Put the three figures and the pass or fail in the logbook.

---

### Task 7: Timings and memory under the free-tier limits

**Files:**
- Create: `research/measure_graph.py`

**Interfaces:**
- Consumes: `run_budget.limit_prefix` and `run_budget.check_limits` (the same limits as run B1), `Graph.load`, corridors, `TravelTimes`.
- Produces: `research/results/graph-timing/timing.json` and printed lines. Sub-commands: `python research/measure_graph.py` (unlimited) and `--limited` (re-runs itself inside the systemd scope).
- Measured, 5 repeats each, on the longest route (13 stops): load time; resident memory after load, after importing `numpy` and `scipy` only, and at the peak; CPU-seconds and wall seconds for 1 row, for the 14 rows R0 needs, and for 31 rows; all on the route's corridor and on the whole city.

- [ ] **Step 1: Write the script.**
- [ ] **Step 2: Run both modes in WSL** (the limits need systemd).
- [ ] **Step 3: Apply the gate G1 rule from the work plan:** on the corridor, under the limits, 14 rows in at most 5 s of wall time and 31 rows in at most 30 s. Record pass or fail.
- [ ] **Step 4: Commit the script and the results** with message `Research: graph timings under free-tier limits`, and put the table in the logbook.

---

### Task 8 (first in the cut order): Reuse of pre-closure rows

Do this only if gate G1 passes with time to spare, or if it fails and the work plan's fallback makes reuse required.

**Files:**
- Modify: `research/reroute/graph.py`, `research/build_corridors.py`
- Test: `research/reroute/tests/test_graph.py`

**Interfaces:**
- Produces:
  - `build_corridors.py` also writes, per route, `<key>.pre.npy` (seconds between every pair of the route's points and campus, no closure) and `<key>.paths.npy` plus `<key>.paths_index.npy` (for every ordered pair, the graph edges on its shortest path).
  - `affected_sources(paths, paths_index, removed_edges, slowed_edges) -> set[int]`: the points with at least one pair whose stored path uses a removed or slowed edge.
  - `TravelTimes.rows` serves an unaffected point's row from the stored table and counts it in a new `reused: int`.

- [ ] **Step 1: Write the failing test:** on the toy map with the closure at node 2, the row from node 4 is reused (its paths avoid the closure) and the row from node 1 is searched; both equal a search with reuse switched off.
- [ ] **Step 2: Implement.** This is sound because a closure only increases travel times: a stored shortest path that uses no affected edge is still the shortest.
- [ ] **Step 3: Run the tests, then commit** with message `Research: reuse of pre-closure rows`.

If this task is cut, write that in the logbook: the 10 November entry lists reuse as part of the rerouting design.
