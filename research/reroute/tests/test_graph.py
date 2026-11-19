"""Tests for ``reroute.graph``: searches, corridors, closures, the row cache and reuse of rows."""
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from reroute.closure import Closure
from reroute.graph import (Corridor, Graph, ReuseTable, TravelTimes, affected_sources, clear_row_cache,
                           corridor_for, load_corridor, load_reuse, problem_rows, reuse_table,
                           shortest_path_nodes)
from reroute.roadnet import TABLE_KEYS, Way, build_tables
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

    # A point on a one-way dead end (node 6: no way back to the city) snaps to the main road network,
    # as OSRM does, so legs to and from it have a path.
    def test_nearest_node_keeps_to_the_main_road_network(self):
        g = graph()
        idx, metres = g.nearest_node(24.902, 67.002)            # exactly on node 6
        self.assertEqual(int(g.node_id[idx]), 3)
        self.assertAlmostEqual(metres, 222.4, delta=1.0)
        # Node 2 is a pass-through and not kept here; 5 and 6 are the one-way stub, 7 and 8 an island.
        self.assertEqual(sorted(int(g.node_id[i]) for i in np.flatnonzero(g.main_nodes)), [1, 3, 4])

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


class ReviewFocusTests(unittest.TestCase):
    """Extra tests for the plan's review-focus items and other edge cases."""

    def setUp(self):
        clear_row_cache()

    # Review focus 1: a point far from any road.
    def test_nearest_node_reports_the_distance_of_a_far_point(self):
        g = graph()
        idx, metres = g.nearest_node(24.950, 67.002)          # about 5 km north of the toy roads
        self.assertGreater(metres, 4000)
        self.assertIn(int(g.node_id[idx]), (1, 2, 3, 4))       # the main network, not the 7-8 island

    # Review focus 2: a closure that touches no road.
    def test_closure_touching_no_road_leaves_searches_unchanged(self):
        g = graph()
        open_row = TravelTimes(g, None).rows([node(g, 1)])[node(g, 1)]
        far = TravelTimes(g, None, [Closure("far", ((25.5, 67.5, 200.0),), 0.0)])
        np.testing.assert_array_equal(far.rows([node(g, 1)])[node(g, 1)], open_row)
        self.assertEqual(len(far.removed), 0)

    # Review focus 3: source or target outside the corridor.
    def test_source_outside_corridor_is_an_infinite_row(self):
        g = graph(); c = corridor_for(g, "r", shortest_path_nodes(g, node(g, 1), node(g, 6)), buffer_m=50)
        tt = TravelTimes(g, c)
        row = tt.rows([node(g, 4)])[node(g, 4)]
        self.assertEqual(len(row), g.n_nodes)
        self.assertTrue(np.all(np.isinf(row)))
        self.assertEqual(tt.searches, 0)

    # Review focus 4: a closure that cuts the corridor in two.
    def test_closure_cutting_the_corridor_widens_to_the_city(self):
        # A detour from 4 to 6 around the east, through junction 40 about 1.7 km from the corridor.
        tables = build_tables(TOY + [
            Way([(4, 24.900, 67.003), (40, 24.900, 67.020), (41, 24.902, 67.020), (6, 24.902, 67.002)], "primary"),
            Way([(40, 24.900, 67.020), (42, 24.890, 67.020)], "residential")], keep_ids=[4])
        g = Graph(tables)
        path = shortest_path_nodes(g, node(g, 4), node(g, 6))
        c = corridor_for(g, "r", path, buffer_m=150)
        self.assertNotIn(40, g.node_id[c.nodes].tolist())
        cut = Closure("cut", ((24.900, 67.0025, 20.0),), 0.0)          # between nodes 3 and 4
        tt = TravelTimes(g, c, [cut])
        rows = tt.ensure([node(g, 4)], [node(g, 6)])
        self.assertTrue(tt.widened)
        self.assertTrue(math.isfinite(float(rows[node(g, 4)][node(g, 6)])))
        self.assertIsNone(tt.corridor)

    def test_ensure_does_not_widen_when_everything_is_reachable(self):
        g = graph(); c = corridor_for(g, "r", shortest_path_nodes(g, node(g, 1), node(g, 6)), buffer_m=50)
        tt = TravelTimes(g, c)
        rows = tt.ensure([node(g, 1)], [node(g, 6)])
        self.assertFalse(tt.widened)
        self.assertAlmostEqual(float(rows[node(g, 1)][node(g, 6)]), 41.3, delta=0.4)

    def test_ensure_widens_only_once(self):
        g = graph(); c = corridor_for(g, "r", shortest_path_nodes(g, node(g, 1), node(g, 6)), buffer_m=50)
        tt = TravelTimes(g, c)
        tt.ensure([node(g, 6)], [node(g, 1)])                 # unreachable everywhere (one-way)
        searches = tt.searches
        tt.ensure([node(g, 6)], [node(g, 1)])
        self.assertTrue(tt.widened)
        self.assertEqual(tt.searches, searches)               # the second call is served from the cache

    def test_rows_are_float32_graph_length_and_read_only(self):
        g = graph(); c = corridor_for(g, "r", shortest_path_nodes(g, node(g, 1), node(g, 6)), buffer_m=50)
        row = TravelTimes(g, c).rows([node(g, 1)])[node(g, 1)]
        self.assertEqual((row.dtype, len(row)), (np.float32, g.n_nodes))
        import reroute.graph as G
        cached = next(iter(G.ROW_CACHE.values()))
        self.assertEqual(len(cached), len(c.nodes))           # stored at corridor length
        with self.assertRaises(ValueError):
            cached[0] = 1.0

    def test_one_search_call_for_many_sources(self):
        g = graph(); tt = TravelTimes(g, None)
        out = tt.rows([node(g, 1), node(g, 3), node(g, 1)])
        self.assertEqual(set(out), {node(g, 1), node(g, 3)})
        self.assertEqual(tt.searches, 2)

    def test_parallel_edges_keep_the_faster(self):
        # Two roads join 1 and 3: residential through 2 (29.0 s) and primary through 5 (about 16.6 s).
        # Node 1 is kept, else it would be a pass-through of the loop 3-2-1-5-3.
        tables = build_tables([TOY[0], Way([(1, 24.900, 67.000), (5, 24.901, 67.001), (3, 24.900, 67.002)],
                                           "primary"), TOY[2]], keep_ids=[1])
        g = Graph(tables)
        self.assertEqual(int(np.sum((g.edge_u == node(g, 1)) & (g.edge_v == node(g, 3)))), 2)
        t = float(TravelTimes(g, None).rows([node(g, 1)])[node(g, 1)][node(g, 3)])
        self.assertAlmostEqual(t, 16.6, delta=0.3)          # 2 x 150 m at 65 km/h, not the 29 s street

    def test_shortest_path_unreachable_and_trivial(self):
        g = graph()
        self.assertEqual(shortest_path_nodes(g, node(g, 6), node(g, 1)), [])
        self.assertEqual(shortest_path_nodes(g, node(g, 3), node(g, 3)), [node(g, 3)])

    def test_corridor_edges_have_both_ends_inside(self):
        g = graph(); c = corridor_for(g, "r", shortest_path_nodes(g, node(g, 1), node(g, 6)), buffer_m=50)
        inside = set(c.nodes.tolist())
        for e in c.edges.tolist():
            self.assertIn(int(g.edge_u[e]), inside)
            self.assertIn(int(g.edge_v[e]), inside)

    def test_problem_rows_closed_point_row_is_infinite(self):
        g = graph(keep=[2]); tt = TravelTimes(g, None)
        rows = problem_rows(tt, [node(g, 2), node(g, 3)], start_node=node(g, 1), campus_node=node(g, 6),
                            closed=[False, True])
        self.assertTrue(all(math.isinf(x) for x in rows([1])[1]))
        with self.assertRaises(ValueError):
            problem_rows(tt, [node(g, 2)], node(g, 1), node(g, 6), closed=[False, True])

    def test_problem_from_problem_rows_solves_with_the_ladder(self):
        from reroute import Ladder, Problem, StopNeed
        g = graph(keep=[2]); tt = TravelTimes(g, None)
        rows = problem_rows(tt, [node(g, 2), node(g, 3)], start_node=node(g, 1), campus_node=node(g, 6))
        problem = Problem([StopNeed(1, 2), StopNeed(2, 3)], [1, 2], rows, walk={})
        plan = Ladder(problem).run()
        self.assertEqual(plan.visit, (1, 2))
        self.assertEqual(plan.unserved, ())
        # 14.5 drive + 60 + 2 x 5 stop, 14.5 drive + 60 + 3 x 5 stop, 12.3 to campus.
        self.assertAlmostEqual(plan.arrival_s, 186.3, delta=0.6)

    def test_ladder_on_a_closed_point_leaves_its_stop_unserved(self):
        from reroute import Ladder, Problem, StopNeed
        g = graph(keep=[2]); tt = TravelTimes(g, None, [AT_NODE_2])
        rows = problem_rows(tt, [node(g, 2), node(g, 4)], start_node=node(g, 3), campus_node=node(g, 6),
                            closed=[True, False])
        problem = Problem([StopNeed(1, 2), StopNeed(2, 3)], [1, 2], rows, walk={})
        plan = Ladder(problem).run()
        self.assertEqual(plan.unserved, (1,))
        self.assertTrue(math.isfinite(plan.arrival_s))


class LoadTests(unittest.TestCase):
    def setUp(self):
        clear_row_cache()

    def test_load_reads_memory_mapped_arrays_and_meta(self):
        tables = build_tables(TOY)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            for k in TABLE_KEYS:
                np.save(Path(tmp) / f"{k}.npy", tables[k])
            (Path(tmp) / "meta.json").write_text(json.dumps({"version": "toy_v9", "speed_factor": 2.0}))
            g = Graph.load(tmp)
            self.assertIsInstance(g.edge_s, np.memmap)
            self.assertEqual((g.version, g.speed_factor, g.n_nodes), ("toy_v9", 2.0, 6))
            t = float(TravelTimes(g, None).rows([node(g, 1)])[node(g, 1)][node(g, 6)])
            self.assertAlmostEqual(t, 82.6, delta=0.8)
            self.assertNotIsInstance(Graph.load(tmp, mmap=False).edge_s, np.memmap)
            del g

    def test_load_corridor_returns_none_without_a_file(self):
        g = graph(); c = corridor_for(g, "Jadoon-R-1", shortest_path_nodes(g, node(g, 1), node(g, 6)), buffer_m=50)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            self.assertIsNone(load_corridor(tmp, "Jadoon-R-1"))
            np.save(Path(tmp) / "Jadoon-R-1.nodes.npy", c.nodes)
            np.save(Path(tmp) / "Jadoon-R-1.edges.npy", c.edges)
            back = load_corridor(tmp, "Jadoon-R-1")
            self.assertIsInstance(back, Corridor)
            self.assertEqual((back.key, back.nodes.tolist(), back.edges.tolist()),
                             ("Jadoon-R-1", c.nodes.tolist(), c.edges.tolist()))


class ReuseTests(unittest.TestCase):
    """Task 8: rows of points whose stored paths avoid the closure are served from the stored table."""

    def setUp(self):
        clear_row_cache()

    def _setup(self):
        g = graph()
        c = corridor_for(g, "r", shortest_path_nodes(g, node(g, 1), node(g, 6)), buffer_m=500)
        points = [node(g, 4), node(g, 3), node(g, 6)]      # the route's points, campus last
        return g, c, points, reuse_table(g, c, points)

    def test_unaffected_row_is_reused_and_affected_row_is_searched(self):
        g, c, points, table = self._setup()
        targets = points
        tt = TravelTimes(g, c, [AT_NODE_2], reuse=table)
        got = tt.rows([node(g, 4), node(g, 1)], targets=targets)
        self.assertEqual((tt.reused, tt.searches), (1, 1))
        clear_row_cache()
        plain = TravelTimes(g, c, [AT_NODE_2]).rows([node(g, 4), node(g, 1)])
        for s in (node(g, 4), node(g, 1)):
            np.testing.assert_allclose(got[s][targets], plain[s][targets])

    def test_point_whose_path_crosses_the_closure_is_searched(self):
        g = graph()
        c = corridor_for(g, "r", shortest_path_nodes(g, node(g, 1), node(g, 6)), buffer_m=500)
        points = [node(g, 1), node(g, 4), node(g, 6)]
        table = reuse_table(g, c, points)
        tt = TravelTimes(g, c, [AT_NODE_2], reuse=table)
        got = tt.rows(points, targets=points)
        # Node 1's paths and node 4's path to node 1 cross the closure; campus has no outgoing path.
        self.assertEqual((tt.reused, tt.searches), (1, 2))
        self.assertEqual(float(got[node(g, 4)][node(g, 1)]), math.inf)

    def test_affected_sources(self):
        g, c, points, table = self._setup()
        k = len(points)
        self.assertEqual(len(table.paths_index), k * k + 1)
        removed_36 = [e for e in range(g.n_edges)
                      if (int(g.node_id[g.edge_u[e]]), int(g.node_id[g.edge_v[e]])) == (3, 6)]
        self.assertEqual(affected_sources(table.paths, table.paths_index, removed_36, []), {0, 1})
        self.assertEqual(affected_sources(table.paths, table.paths_index, [], []), set())
        self.assertEqual(affected_sources(table.paths, table.paths_index, [], removed_36), {0, 1})

    def test_slowed_edge_on_a_stored_path_is_not_reused(self):
        g, c, points, table = self._setup()
        slow = Closure("slow", ((24.900, 67.0025, 20.0),), 0.5)     # between nodes 3 and 4
        tt = TravelTimes(g, c, [slow], reuse=table)
        got = tt.rows([node(g, 4)], targets=points)
        self.assertEqual((tt.reused, tt.searches), (0, 1))
        clear_row_cache()
        plain = TravelTimes(g, c, [slow]).rows([node(g, 4)])
        np.testing.assert_allclose(got[node(g, 4)][points], plain[node(g, 4)][points])

    def test_no_reuse_without_targets_or_for_targets_off_the_table(self):
        g, c, points, table = self._setup()
        tt = TravelTimes(g, c, [AT_NODE_2], reuse=table)
        tt.rows([node(g, 4)])
        self.assertEqual(tt.reused, 0)
        clear_row_cache()
        tt.rows([node(g, 4)], targets=[node(g, 1)])
        self.assertEqual(tt.reused, 0)

    def test_reuse_switches_off_after_widening(self):
        g, c, points, table = self._setup()
        tt = TravelTimes(g, c, [AT_NODE_2], reuse=table)
        tt.ensure([node(g, 6)], [node(g, 1)])                 # unreachable: widens
        tt.rows([node(g, 4)], targets=points)
        self.assertEqual(tt.reused, 0)

    def test_problem_rows_use_reuse(self):
        g, c, points, table = self._setup()
        tt = TravelTimes(g, c, [AT_NODE_2], reuse=table)
        rows = problem_rows(tt, [node(g, 4)], start_node=node(g, 3), campus_node=node(g, 6))
        out = rows([0, 1])
        self.assertEqual(tt.reused, 2)
        self.assertAlmostEqual(out[0][2], 26.8, delta=0.4)    # node 4 to campus

    def test_reuse_table_mismatch_is_rejected(self):
        g, c, points, table = self._setup()
        other = Graph(build_tables(TOY), speed_factor=2.0)
        with self.assertRaises(ValueError):
            TravelTimes(other, c, reuse=table)

    def test_reuse_table_round_trip(self):
        g, c, points, table = self._setup()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            self.assertIsNone(load_reuse(tmp, "r"))
            table.save(tmp)
            back = load_reuse(tmp, "r")
            self.assertIsInstance(back, ReuseTable)
            np.testing.assert_array_equal(back.pre, table.pre)
            np.testing.assert_array_equal(back.paths, table.paths)
            self.assertEqual(back.point_nodes.tolist(), table.point_nodes.tolist())
            self.assertEqual((back.graph_version, back.speed_factor), (g.version, g.speed_factor))


if __name__ == "__main__":
    unittest.main()


def _grid_ways(seed: int, size: int = 7):
    """A random street grid: random road classes, some one-way streets, about 110 m blocks."""
    import random
    rng = random.Random(seed)
    classes = ["residential", "primary", "secondary", "tertiary", "service"]
    nid = lambda r, c: 1000 + r * size + c
    at = lambda r, c: (nid(r, c), 24.90 + r * 0.001, 67.00 + c * 0.001)
    ways = []
    for r in range(size):
        for c in range(size - 1):
            ways.append(Way([at(r, c), at(r, c + 1)], rng.choice(classes), rng.choice(["", "", "yes", "-1"])))
    for c in range(size):
        for r in range(size - 1):
            ways.append(Way([at(r, c), at(r + 1, c)], rng.choice(classes), rng.choice(["", "", "yes"])))
    return ways


def _reference_seconds(tables, closures, source_id):
    """Plain Dijkstra over the uncompressed segments, closures applied segment by segment."""
    import heapq
    from reroute.closure import closed_segments
    factor = {}
    for c in closures:
        for s in closed_segments(tables, c).tolist():
            factor[s] = min(factor.get(s, 1.0), c.factor)
    adj = {}
    for s, (f, t, sec) in enumerate(zip(tables["seg_from"].tolist(), tables["seg_to"].tolist(),
                                        tables["seg_s"].tolist())):
        k = factor.get(s, 1.0)
        if k > 0:
            adj.setdefault(f, []).append((t, sec / k))
    best, heap = {source_id: 0.0}, [(0.0, source_id)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > best.get(u, math.inf):
            continue
        for v, w in adj.get(u, []):
            if d + w < best.get(v, math.inf):
                best[v] = d + w
                heapq.heappush(heap, (d + w, v))
    return best


class RandomGridTests(unittest.TestCase):
    """Compression, closures and reuse checked against a plain search on random street grids."""

    def setUp(self):
        clear_row_cache()

    def test_rows_match_a_search_over_uncompressed_segments(self):
        import random
        for seed in range(6):
            rng = random.Random(seed)
            tables = build_tables(_grid_ways(seed))
            g = Graph(tables)
            closures = [Closure(f"c{i}", ((24.90 + rng.uniform(0, 0.006), 67.00 + rng.uniform(0, 0.006),
                                           rng.uniform(20, 120)),), rng.choice([0.0, 0.3, 0.6]))
                        for i in range(rng.randint(0, 3))]
            tt = TravelTimes(g, None, closures)
            for source in rng.sample(range(g.n_nodes), 4):
                ref = _reference_seconds(tables, closures, int(g.node_id[source]))
                row = tt.rows([source])[source]
                for target in range(g.n_nodes):
                    want = ref.get(int(g.node_id[target]), math.inf)
                    got = float(row[target])
                    if math.isinf(want):
                        self.assertTrue(math.isinf(got), (seed, source, target))
                    else:
                        self.assertAlmostEqual(got, want, delta=max(0.01, want * 1e-5), msg=(seed, source, target))

    def test_reused_rows_equal_searched_rows(self):
        import random
        for seed in range(6):
            rng = random.Random(100 + seed)
            g = Graph(build_tables(_grid_ways(seed)))
            points = rng.sample(range(g.n_nodes), 6)
            c = corridor_for(g, "grid", points, buffer_m=5000)
            table = reuse_table(g, c, points)
            closures = [Closure("c", ((24.90 + rng.uniform(0, 0.006), 67.00 + rng.uniform(0, 0.006), 60.0),),
                                rng.choice([0.0, 0.5]))]
            with_reuse = TravelTimes(g, c, closures, reuse=table)
            got = with_reuse.rows(points, targets=points)
            clear_row_cache()
            plain = TravelTimes(g, c, closures).rows(points)
            for s in points:
                np.testing.assert_allclose(got[s][points], plain[s][points], rtol=1e-6)
            self.assertEqual(with_reuse.reused + with_reuse.searches, len(set(points)))


class FixTests(unittest.TestCase):
    """Fixes after review: corridor identity, cache bytes, corridor version check."""

    def setUp(self):
        clear_row_cache()

    def tearDown(self):
        clear_row_cache()

    def test_corridor_sorts_its_arrays_and_ident_tells_node_sets_apart(self):
        g = graph(); path = shortest_path_nodes(g, node(g, 1), node(g, 6))
        narrow, wide = corridor_for(g, "r", path, buffer_m=50), corridor_for(g, "r", path, buffer_m=150)
        self.assertNotEqual(narrow.ident, wide.ident)
        same = Corridor("r", wide.nodes[::-1].copy(), wide.edges[::-1].copy())
        self.assertEqual(same.ident, wide.ident)
        self.assertEqual(same.nodes.tolist(), sorted(wide.nodes.tolist()))

    def test_reuse_table_of_another_corridor_with_the_same_key_is_not_used(self):
        g = graph(); path = shortest_path_nodes(g, node(g, 1), node(g, 6))
        built_on, other = corridor_for(g, "r", path, buffer_m=500), corridor_for(g, "r", path, buffer_m=50)
        points = [node(g, 3), node(g, 6)]
        tt = TravelTimes(g, other, reuse=reuse_table(g, built_on, points))
        tt.rows(points, targets=points)
        self.assertEqual((tt.reused, tt.searches), (0, 2))

    def test_cache_is_bounded_in_bytes(self):
        import reroute.graph as G
        old, G.ROW_CACHE_MAX_BYTES = G.ROW_CACHE_MAX_BYTES, 0
        try:
            g = graph(); tt = TravelTimes(g, None)
            for map_id in (1, 3, 4):
                tt.rows([node(g, map_id)])
            self.assertEqual(len(G.ROW_CACHE), 1)              # the newest row is always kept
            tt.rows([node(g, 4)])
            self.assertEqual((tt.searches, tt.hits), (3, 1))
            clear_row_cache()
            self.assertEqual(G._cache_bytes, 0)
        finally:
            G.ROW_CACHE_MAX_BYTES = old

    def test_load_corridor_rejects_another_graph_version(self):
        g = graph(); c = corridor_for(g, "r", shortest_path_nodes(g, node(g, 1), node(g, 6)), buffer_m=50)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            np.save(Path(tmp) / "r.nodes.npy", c.nodes)
            np.save(Path(tmp) / "r.edges.npy", c.edges)
            (Path(tmp) / "index.json").write_text(json.dumps({"graph_version": "old"}))
            self.assertIsNotNone(load_corridor(tmp, "r"))
            self.assertIsNotNone(load_corridor(tmp, "r", "old"))
            with self.assertRaises(ValueError):
                load_corridor(tmp, "r", "new")


class ModuleRuleTests(unittest.TestCase):
    def test_graph_and_closure_import_only_numpy_scipy_and_the_standard_library(self):
        import ast
        import sys as _sys
        allowed = set(_sys.stdlib_module_names) | {"numpy", "scipy", "reroute", "__future__"}
        for name in ("graph.py", "closure.py", "roadnet.py"):
            tree = ast.parse((Path(__file__).resolve().parents[1] / name).read_text())
            for node_ in ast.walk(tree):
                if isinstance(node_, ast.Import):
                    roots = [a.name.split(".")[0] for a in node_.names]
                elif isinstance(node_, ast.ImportFrom):
                    roots = [(node_.module or "").split(".")[0]]
                else:
                    continue
                for root in roots:
                    self.assertIn(root, allowed, f"{name} imports {root}")

    def test_problem_rows_reuse_with_a_start_off_the_table(self):
        clear_row_cache()
        g = graph(keep=[2])
        c = corridor_for(g, "r", shortest_path_nodes(g, node(g, 1), node(g, 6)), buffer_m=500)
        table = reuse_table(g, c, [node(g, 4), node(g, 3), node(g, 6)])
        tt = TravelTimes(g, c, [AT_NODE_2], reuse=table)
        rows = problem_rows(tt, [node(g, 4), node(g, 3)], start_node=node(g, 2), campus_node=node(g, 6))
        out = rows([0, 1, 2])                                  # two points reused, the start searched
        self.assertEqual((tt.reused, tt.searches), (2, 1))
        self.assertAlmostEqual(out[0][3], 26.8, delta=0.4)    # point 0 (node 4) to campus
        self.assertEqual(out[0][2], math.inf)                 # column of the start: not on the table
        self.assertEqual(out[2][0], math.inf)                 # node 2 is cut off by the closure
