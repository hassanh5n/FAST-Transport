"""Tests for the pure parts of `build_walk`: pair filtering, statistics, the file and its loader."""
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from build_walk import (build_output, detour_factor, load_walk, route_stop_ids, share_same_route,
                        walk_pairs)

RESEARCH = Path(__file__).resolve().parent.parent

# Three stops on one street, about 100 m apart, and one far away.
POINTS = [(24.9, 67.0), (24.9, 67.001), (24.9, 67.002), (24.95, 67.05)]
STRAIGHT_01 = 100.9
DIST = [[0, 130, 260, 9000],
        [125, 0, 140, None],
        [250, 135, 0, 9000],
        [9000, None, 9000, 0]]


class WalkPairTests(unittest.TestCase):
    def test_keeps_close_pairs_in_whole_metres(self):
        pairs = walk_pairs(DIST, POINTS)
        self.assertEqual(pairs, [[0, 1, 130], [0, 2, 260], [1, 0, 125], [1, 2, 140],
                                 [2, 0, 250], [2, 1, 135]])

    def test_walk_limit_and_straight_line_limit(self):
        self.assertEqual(walk_pairs(DIST, POINTS, max_walk_m=200), [[0, 1, 130], [1, 0, 125],
                                                                    [1, 2, 140], [2, 1, 135]])
        # A pair beyond the straight-line limit is not kept even if the walk is short.
        self.assertEqual(walk_pairs(DIST, POINTS, max_straight_m=150), [[0, 1, 130], [1, 0, 125],
                                                                        [1, 2, 140], [2, 1, 135]])

    def test_unreachable_pairs_are_dropped_not_zero(self):
        dist = [[0, None], [None, 0]]
        self.assertEqual(walk_pairs(dist, POINTS[:2]), [])

    def test_shape_mismatch(self):
        with self.assertRaises(ValueError):
            walk_pairs(DIST, POINTS[:3])


class StatisticTests(unittest.TestCase):
    def test_detour_factor_is_the_median_ratio(self):
        f = detour_factor(DIST, POINTS)
        ratios = sorted([130 / STRAIGHT_01, 260 / (2 * STRAIGHT_01), 125 / STRAIGHT_01,
                         140 / STRAIGHT_01, 250 / (2 * STRAIGHT_01), 135 / STRAIGHT_01])
        self.assertAlmostEqual(f, (ratios[2] + ratios[3]) / 2, places=2)

    def test_detour_factor_without_pairs(self):
        self.assertIsNone(detour_factor([[0]], POINTS[:1]))

    def test_share_same_route(self):
        walk = {(0, 1): 300.0, (1, 0): 300.0, (2, 3): 700.0}
        routes = [[0, 1, 2], [2, 3]]
        # Visits: 0, 1, 2 on the first route; 2, 3 on the second. 5 visits.
        self.assertEqual(share_same_route(routes, walk, 400), 2 / 5)
        self.assertEqual(share_same_route(routes, walk, 800), 3 / 5)
        # Stop 2 walks to 3 only on the second route; on the first route 3 is not a neighbour.

    def test_share_of_no_visits(self):
        self.assertEqual(share_same_route([], {}, 400), 0.0)


class FileTests(unittest.TestCase):
    INSTANCE = {"version": "toy-v1",
                "stops": [{"name": n, "lat": p[0], "lng": p[1]} for n, p in zip("ABCD", POINTS)],
                "contractors": {"J": {"baseline_routes": [{"code": "R-1", "stops": ["A", "B", "C"]}]},
                                "N": {"baseline_routes": [{"code": "R-1", "stops": ["D", "C"]}]}}}

    def test_route_stop_ids_use_instance_positions(self):
        self.assertEqual(route_stop_ids(self.INSTANCE), [[0, 1, 2], [3, 2]])

    def test_output_round_trips_through_load_walk(self):
        out = build_output(self.INSTANCE, DIST, built_at="2026-11-16T00:00:00+00:00")
        self.assertEqual((out["version"], out["instance"], out["profile"], out["max_m"]),
                         ("walk-fall2026-v1", "toy-v1", "foot", 1000))
        self.assertEqual(set(out["stats"]), {"detour_factor", "share_same_route_400", "share_same_route_800"})
        self.assertEqual(out["stats"]["share_same_route_400"], 0.6)   # A, B, C of R-1; D and C apart
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "walk.json"
            path.write_text(json.dumps(out))
            walk = load_walk(path)
        self.assertEqual(walk[(0, 1)], 130.0)
        self.assertNotIn((0, 3), walk)
        self.assertTrue(all(isinstance(k, tuple) and v < math.inf for k, v in walk.items()))


class CommandTests(unittest.TestCase):
    def test_help_works_without_a_server(self):
        out = subprocess.run([sys.executable, "build_walk.py", "--help"], cwd=RESEARCH,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("--foot-dir", out.stdout)

    def test_missing_foot_build_fails_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run([sys.executable, "build_walk.py", "--foot-dir", tmp,
                                  "--out", str(Path(tmp) / "w.json")],
                                 cwd=RESEARCH, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("karachi.osrm", out.stderr)
        self.assertNotIn("Traceback", out.stderr)


if __name__ == "__main__":
    unittest.main()
