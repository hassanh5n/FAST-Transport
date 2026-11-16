"""Tests for ``reroute.closure``: closures matched to road segments by geometry."""
import unittest

import numpy as np

from reroute.closure import (Closure, closed_points, closed_segments, closure_key, edge_changes,
                             osrm_speed_rows)
from reroute.roadnet import Way, build_tables
from reroute.tests.toymap import TOY

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


class ExtraClosureTests(unittest.TestCase):
    """Review focus 2 and edge cases beyond the plan's tests."""

    def test_closure_touching_no_road_changes_no_edge(self):
        far = Closure("far", ((25.5, 67.5, 200.0),), 0.0)
        removed, extra = edge_changes(T, [far])
        self.assertEqual((len(removed), extra), (0, {}))
        self.assertEqual(osrm_speed_rows(T, far), [])

    def test_no_closures_change_nothing(self):
        removed, extra = edge_changes(T, [])
        self.assertEqual((len(removed), extra), (0, {}))
        self.assertEqual(closed_points(np.array([24.9]), np.array([67.001]), []).tolist(), [False])

    def test_several_circles_in_one_closure(self):
        two = Closure("two", ((24.900, 67.001, 30.0), (24.910, 67.005, 50.0)), 0.0)
        self.assertEqual(seg_pairs(closed_segments(T, two)),
                         [(1, 2), (2, 1), (2, 3), (3, 2), (7, 8), (8, 7)])

    def test_coarser_sampling_misses_the_middle_of_a_long_segment(self):
        mid = Closure("c2", ((24.910, 67.005, 50.0),), 0.0)
        self.assertEqual(len(closed_segments(T, mid, sample_m=400.0)), 0)

    def test_works_on_an_object_with_attributes(self):
        class Tables:
            pass
        obj = Tables()
        for k, v in T.items():
            setattr(obj, k, v)
        self.assertEqual(seg_pairs(closed_segments(obj, AT_NODE_2)), [(1, 2), (2, 1), (2, 3), (3, 2)])

    def test_empty_tables(self):
        empty = build_tables([])
        self.assertEqual(len(closed_segments(empty, AT_NODE_2)), 0)
        self.assertEqual(osrm_speed_rows(empty, AT_NODE_2), [])

    def test_key_changes_with_factor_and_is_stable_for_empty(self):
        self.assertNotEqual(closure_key([AT_NODE_2]), closure_key([Closure("c1", AT_NODE_2.circles, 0.5)]))
        self.assertEqual(closure_key([]), closure_key(()))

    def test_invalid_closures_are_rejected(self):
        with self.assertRaises(ValueError):
            Closure("bad", ((24.9, 67.0, 30.0),), 1.5)
        with self.assertRaises(ValueError):
            Closure("bad", ((24.9, 67.0, -1.0),), 0.0)
        with self.assertRaises(ValueError):
            Closure("bad", (), 0.0)

    def test_slow_speed_never_below_one(self):
        slowed = osrm_speed_rows(T, Closure("crawl", ((24.900, 67.001, 30.0),), 0.01))
        self.assertEqual({kmh for _, _, kmh in slowed}, {1})

    def test_far_apart_grid_cells_are_found(self):
        # A segment longer than the grid cell, crossing many cells, closed far from its midpoint.
        long_way = [Way([(1, 24.9, 67.0), (2, 24.9, 67.05)], "primary")]
        t = build_tables(long_way)
        near_end = Closure("end", ((24.9, 67.049, 60.0),), 0.0)
        self.assertEqual(len(closed_segments(t, near_end)), 2)


if __name__ == "__main__":
    unittest.main()
