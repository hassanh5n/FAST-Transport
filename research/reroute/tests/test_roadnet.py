"""Tests for ``reroute.roadnet``: segment and compressed-edge tables built from map ways."""
import unittest

import numpy as np

from reroute.roadnet import SPEED_KMH, Way, build_tables, haversine_m
from reroute.tests.toymap import N, TOY, way


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


class ExtraRoadnetTests(unittest.TestCase):
    """Edge cases beyond the plan's tests."""

    def test_haversine_matches_the_worked_distances(self):
        self.assertAlmostEqual(haversine_m(*N[1], *N[2]), 100.8, delta=0.3)
        self.assertAlmostEqual(haversine_m(*N[3], *N[5]), 111.2, delta=0.3)

    def test_speeds_are_the_plan_values(self):
        self.assertEqual(SPEED_KMH["motorway"], 90)
        self.assertEqual(SPEED_KMH["service"], 15)
        self.assertEqual(len(SPEED_KMH), 14)

    def test_oneway_spellings(self):
        for flag in ("yes", "true", "1"):
            t = build_tables([way([1, 2], "residential", flag)])
            self.assertEqual(list(zip(t["seg_from"].tolist(), t["seg_to"].tolist())), [(1, 2)])
        t = build_tables([way([1, 2], "residential", "reverse")])
        self.assertEqual(list(zip(t["seg_from"].tolist(), t["seg_to"].tolist())), [(2, 1)])
        t = build_tables([way([1, 2], "residential", "no")])
        self.assertEqual(len(t["seg_from"]), 2)

    def test_empty_input_gives_empty_typed_tables(self):
        t = build_tables([])
        self.assertEqual(len(t["node_id"]), 0)
        self.assertEqual(t["edge_u"].dtype, np.int32)
        self.assertEqual(t["seg_from"].dtype, np.int64)
        self.assertEqual(t["seg_s"].dtype, np.float32)

    def test_direction_change_keeps_the_node(self):
        # A one-way street meets a two-way street at node 2: node 2 must stay a graph node.
        t = build_tables([way([1, 2], "residential", "yes"), way([2, 3], "residential")])
        self.assertIn(2, t["node_id"].tolist())

    def test_two_ways_joining_end_to_end_are_merged(self):
        t = build_tables([way([1, 2], "residential"), way([2, 3], "primary")])
        self.assertEqual(sorted(t["node_id"].tolist()), [1, 3])
        e = pairs(t, "edge_u", "edge_v")
        self.assertEqual(e, [(1, 3), (3, 1)])

    def test_parallel_ways_stay_separate_edges(self):
        # Spurs to nodes 7 and 4 make nodes 1 and 3 junctions; two roads join them.
        t = build_tables([way([1, 2, 3], "residential"), way([1, 5, 3], "primary"),
                          way([7, 1], "residential"), way([3, 4], "residential")])
        self.assertEqual(pairs(t, "edge_u", "edge_v"),
                         [(1, 3), (1, 3), (1, 7), (3, 1), (3, 1), (3, 4), (4, 3), (7, 1)])

    def test_ring_with_a_kept_node_uses_that_node(self):
        ring = [Way([(1, 24.9, 67.0), (2, 24.9, 67.001), (3, 24.901, 67.001), (1, 24.9, 67.0)], "residential")]
        t = build_tables(ring, keep_ids=[3])
        self.assertEqual(t["node_id"].tolist(), [3])

    def test_repeated_node_in_a_way_makes_no_zero_segment(self):
        t = build_tables([Way([(1, *N[1]), (1, *N[1]), (2, *N[2])], "residential")])
        self.assertEqual(sorted(zip(t["seg_from"].tolist(), t["seg_to"].tolist())), [(1, 2), (2, 1)])


if __name__ == "__main__":
    unittest.main()
