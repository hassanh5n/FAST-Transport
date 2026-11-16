"""Tests for `build_matrix`: per-contractor and combined node lists, the matrix entry, the check
against the saved matrix, and the command line. OSRM is never contacted."""
import json
import math
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import build_matrix
from build_matrix import combined_points, compare_with_saved, contractor_points, matrix_entry

RESEARCH = Path(__file__).resolve().parent.parent

INSTANCE = {"version": "toy-v1", "campus": {"lat": 24.85, "lng": 67.26},
            "stops": [{"name": "A", "lat": 24.9, "lng": 67.0}, {"name": "B", "lat": 24.91, "lng": 67.01},
                      {"name": "C", "lat": 24.92, "lng": 67.02}],
            "contractors": {"J": {"stops": ["A", "C"]}, "N": {"stops": ["B"]}}}


def fake_body(n, missing=()):
    durations = [[0 if i == j else 10.0 * (i + 1) + j + 0.04 for j in range(n)] for i in range(n)]
    for i, j in missing:
        durations[i][j] = None
    return {"code": "Ok", "durations": durations,
            "distances": [[0 if i == j else 100.4 * (i + j) for j in range(n)] for i in range(n)],
            "sources": [{"distance": 5.0 + 100 * i} for i in range(n)]}


class NodeTests(unittest.TestCase):
    def test_contractor_points_start_at_campus(self):
        nodes, points = contractor_points(INSTANCE, "J")
        self.assertEqual(nodes, ["CAMPUS", "A", "C"])
        self.assertEqual(points, [(24.85, 67.26), (24.9, 67.0), (24.92, 67.02)])

    def test_combined_points_cover_every_stop_in_instance_order(self):
        nodes, points = combined_points(INSTANCE)
        self.assertEqual(nodes, ["CAMPUS", "A", "B", "C"])
        self.assertEqual(points[2], (24.91, 67.01))

    def test_real_instance_gives_312_nodes(self):
        instance = json.loads((RESEARCH / "data" / "instance_fall2026_v1.json").read_text())
        nodes, points = combined_points(instance)
        self.assertEqual((len(nodes), len(points), nodes[0]), (312, 312, "CAMPUS"))


class EntryTests(unittest.TestCase):
    def test_entry_shape_matches_the_saved_file(self):
        entry = matrix_entry(["CAMPUS", "A", "B"], fake_body(3, missing=[(1, 2)]))
        self.assertEqual(entry["durations_s"][1], [20.0, 0, None])
        self.assertEqual(entry["distances_m"][0], [0, 100, 201])
        self.assertEqual((entry["calls"], entry["cells"]), (1, 9))
        self.assertEqual(entry["unreachable_pairs"], [("A", "B")])
        self.assertEqual(entry["far_snaps"], [("B", 205.0)])
        saved = json.loads((RESEARCH / "data" / "matrix_fall2026_v1.json").read_text())["contractors"]["Jadoon"]
        self.assertEqual(set(entry), set(saved))

    def test_nonzero_diagonal_is_refused(self):
        body = fake_body(2)
        body["durations"][1][1] = 3.0
        with self.assertRaises(AssertionError):
            matrix_entry(["CAMPUS", "A"], body)


class CompareTests(unittest.TestCase):
    SAVED = {"nodes": ["CAMPUS", "A", "C"], "durations_s": [[0, 10.0, 20.0], [11.0, 0, None], [21.0, 5.0, 0]]}

    def combined(self, a_to_c=None, c_to_a=5.0):
        # Combined nodes CAMPUS, A, B, C.
        return {"nodes": ["CAMPUS", "A", "B", "C"],
                "durations_s": [[0, 10.0, 99.0, 20.0], [11.05, 0, 99.0, a_to_c],
                                [99.0, 99.0, 0, 99.0], [21.0, c_to_a, 99.0, 0]]}

    def test_equal_within_a_tenth_of_a_second(self):
        self.assertEqual(compare_with_saved(self.combined(), self.SAVED), [])

    def test_reports_differences_and_reachability_changes(self):
        diffs = compare_with_saved(self.combined(a_to_c=30.0, c_to_a=5.2), self.SAVED)
        self.assertEqual(diffs, [("A", "C", None, 30.0), ("C", "A", 5.0, 5.2)])

    def test_node_missing_from_the_combined_table(self):
        with self.assertRaises(KeyError):
            compare_with_saved({"nodes": ["CAMPUS"], "durations_s": [[0]]}, self.SAVED)


class CommandTests(unittest.TestCase):
    def test_help_works_without_a_server(self):
        out = subprocess.run([sys.executable, "build_matrix.py", "--help"], cwd=RESEARCH,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("--combined", out.stdout)

    def test_unreachable_server_fails_clearly(self):
        out = subprocess.run([sys.executable, "build_matrix.py", "--combined", "--out", "unused.json"],
                             cwd=RESEARCH, capture_output=True, text=True, timeout=60,
                             env={**__import__("os").environ, "OSRM_URL": "http://127.0.0.1:9"})
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("cannot reach OSRM", out.stderr)
        self.assertNotIn("Traceback", out.stderr)
        self.assertFalse((RESEARCH / "unused.json").exists())

    def test_combined_run_writes_one_all_table(self):
        written = {}

        def fake_table(points, osrm):
            return fake_body(len(points))

        with mock.patch.object(build_matrix, "table", side_effect=fake_table), \
                mock.patch.object(build_matrix, "write_json", side_effect=lambda p, d: written.update({p: d})), \
                mock.patch("builtins.print"):
            build_matrix.main(["--combined", "--out", "x.json", "--no-check"])
        (path, data), = written.items()
        self.assertEqual(path, Path("x.json"))
        self.assertEqual(list(data["contractors"]), ["All"])
        self.assertEqual(len(data["contractors"]["All"]["nodes"]), 312)
        self.assertTrue(math.isfinite(data["contractors"]["All"]["durations_s"][1][2]))

    def test_default_run_writes_both_contractors_to_the_saved_name(self):
        written = {}
        with mock.patch.object(build_matrix, "table", side_effect=lambda p, o: fake_body(len(p))), \
                mock.patch.object(build_matrix, "write_json", side_effect=lambda p, d: written.update({p: d})), \
                mock.patch("builtins.print"):
            build_matrix.main([])
        (path, data), = written.items()
        self.assertEqual(path, build_matrix.DATA / "matrix_fall2026_v1.json")
        self.assertEqual(list(data["contractors"]), ["Jadoon", "Nadeem"])


if __name__ == "__main__":
    unittest.main()
