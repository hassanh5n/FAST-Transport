"""Reviewer tests for the road-graph module: each one demonstrates a defect found in review.

Run from ``research/``: ``python -m unittest reroute.tests.test_review_graph -v``.
"""
import math
import unittest

import numpy as np

from reroute.closure import Closure, osrm_speed_rows
from reroute.graph import Corridor, Graph, TravelTimes, clear_row_cache, corridor_for, shortest_path_nodes
from reroute.roadnet import Way, build_tables
from reroute.tests.toymap import TOY


def node(g, map_id):
    return int(np.where(g.node_id == map_id)[0][0])


class CorridorIdentityTests(unittest.TestCase):
    def setUp(self):
        clear_row_cache()

    def tearDown(self):
        clear_row_cache()

    def test_two_corridors_with_the_same_key_do_not_share_cached_rows(self):
        # The row cache is keyed on the corridor's key only, and rows are stored at corridor length.
        # A second corridor with the same key but other nodes gets the first one's row back.
        g = Graph(build_tables(TOY))
        path = shortest_path_nodes(g, node(g, 1), node(g, 6))
        narrow = corridor_for(g, "r", path, buffer_m=50)          # nodes 1, 3, 6
        wide = corridor_for(g, "r", path, buffer_m=150)           # nodes 1, 3, 4, 6
        TravelTimes(g, narrow).rows([node(g, 1)])
        row = TravelTimes(g, wide).rows([node(g, 1)])[node(g, 1)]
        self.assertAlmostEqual(float(row[node(g, 4)]), 43.5, delta=0.5)

    def test_corridor_with_unsorted_nodes_gives_the_same_rows(self):
        # Corridor(key, nodes, edges) is public, and nothing says nodes must be sorted; _local uses
        # searchsorted on them, so an unsorted corridor silently answers inf everywhere.
        g = Graph(build_tables(TOY))
        path = shortest_path_nodes(g, node(g, 1), node(g, 6))
        good = corridor_for(g, "s", path, buffer_m=150)
        shuffled = Corridor("u", good.nodes[::-1].copy(), good.edges)
        want = TravelTimes(g, good).rows([node(g, 1)])[node(g, 1)]
        got = TravelTimes(g, shuffled).rows([node(g, 1)])[node(g, 1)]
        np.testing.assert_allclose(got, want)


class OsrmSpeedRowsTests(unittest.TestCase):
    def test_one_slowed_road_gets_one_speed(self):
        # The speed is recovered from float32 seg_m / seg_s, so 25 km/h x 0.5 = 12.5 lands on
        # 12 for some segments and 13 for others of the same residential road.
        rng = np.random.default_rng(1)
        lng = 67.0 + np.cumsum(rng.uniform(0.0001, 0.0009, 60))
        t = build_tables([Way([(i + 1, 24.9, float(x)) for i, x in enumerate(lng)], "residential")])
        mid = float((lng[0] + lng[-1]) / 2)
        rows = osrm_speed_rows(t, Closure("c", ((24.9, mid, 5000.0),), 0.5))
        self.assertEqual(len(rows), len(t["seg_from"]))
        self.assertEqual(len({kmh for _, _, kmh in rows}), 1, sorted({kmh for _, _, kmh in rows}))


if __name__ == "__main__":
    unittest.main()
