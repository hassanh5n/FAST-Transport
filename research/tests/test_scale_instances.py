"""Tests for scale_instances.py: the optimizer instances of growing size (optimizer-scaling, Task 2)."""
import copy
import json
import unittest
from pathlib import Path

from scale_instances import combined_instance, contractor_instance, doubled_instance

BASE = {"name": "b", "T": [[0, 10, 20], [11, 0, 5], [21, 6, 0]], "q": [0, 4, 7], "capacities": [30]}
DATA = Path(__file__).resolve().parent.parent / "data"


class ScaleInstanceTests(unittest.TestCase):
    def test_doubled_shape(self):
        d = doubled_instance(BASE)
        self.assertEqual((len(d["T"]), d["q"], d["capacities"]), (5, [0, 4, 7, 4, 7], [30, 30]))

    def test_copy_sits_beside_its_original(self):
        T = doubled_instance(BASE)["T"]
        self.assertEqual((T[1][3], T[3][1], T[3][3]), (30.0, 30.0, 0))      # stop 1 and its copy
        self.assertEqual((T[3][0], T[0][3], T[3][2], T[3][4]), (11, 10, 5, 5))   # copy behaves like stop 1

    def test_combined_sums_students_and_fleets(self):
        inst = {"stops": [{"name": "A", "students": {"J": 2, "N": 3}}, {"name": "B", "students": {"J": 1}}],
                "contractors": {"J": {"buses": [{"capacity": 30}]}, "N": {"buses": [{"capacity": 40}, {"capacity": 45}]}}}
        mat_all = {"contractors": {"All": {"nodes": ["CAMPUS", "A", "B"], "durations_s": [[0, 1, 2], [1, 0, 3], [2, 3, 0]]}}}
        c = combined_instance(inst, mat_all)
        self.assertEqual((c["q"], sorted(c["capacities"])), ([0, 5, 1], [30, 40, 45]))


class MoreScaleInstanceTests(unittest.TestCase):
    def test_doubled_leaves_the_base_unchanged(self):
        before = copy.deepcopy(BASE)
        doubled_instance(BASE, gap_s=12.5)
        self.assertEqual(BASE, before)

    def test_doubled_gap_and_name(self):
        d = doubled_instance(BASE, gap_s=12.5)
        self.assertEqual((d["T"][2][4], d["T"][4][2], d["name"]), (12.5, 12.5, "b-doubled"))
        self.assertEqual(d["T"][0], [0, 10, 20, 10, 20])                   # campus row: copies as originals
        self.assertEqual([row[0] for row in d["T"]], [0, 11, 21, 11, 21])  # and back to campus

    def test_doubled_names_copies_when_nodes_are_known(self):
        d = doubled_instance({**BASE, "nodes": ["CAMPUS", "A", "B"]})
        self.assertEqual(d["nodes"], ["CAMPUS", "A", "B", "A (copy)", "B (copy)"])

    def test_contractor_instance_matches_optimize_main(self):
        """Same T, q and capacities as optimize.py: main builds for the saved Nadeem data."""
        inst = json.loads((DATA / "instance_fall2026_v1.json").read_text())
        mat = json.loads((DATA / "matrix_fall2026_v1.json").read_text())
        c = contractor_instance(inst, mat, "Nadeem")
        m = mat["contractors"]["Nadeem"]
        by_name = {s["name"]: s for s in inst["stops"]}
        self.assertIs(c["T"], m["durations_s"])
        self.assertEqual(c["q"], [0] + [by_name[n]["students"].get("Nadeem", 0) for n in m["nodes"][1:]])
        self.assertEqual(c["capacities"], [b["capacity"] for b in inst["contractors"]["Nadeem"]["buses"]])
        self.assertEqual((c["name"], len(c["T"]) - 1), ("Nadeem", 143))
        self.assertEqual(len(c["baseline_routes"]), len(inst["contractors"]["Nadeem"]["baseline_routes"]))

    def test_doubled_can_be_built_from_a_contractor_instance(self):
        inst = json.loads((DATA / "instance_fall2026_v1.json").read_text())
        mat = json.loads((DATA / "matrix_fall2026_v1.json").read_text())
        base = contractor_instance(inst, mat, "Nadeem")
        d = doubled_instance(base)
        self.assertEqual(len(d["T"]) - 1, 2 * 143)
        self.assertEqual(sum(d["q"]), 2 * sum(base["q"]))
        self.assertEqual(len(d["capacities"]), 2 * len(base["capacities"]))

    def test_combined_needs_every_stop_in_the_matrix(self):
        inst = {"stops": [{"name": "A", "students": {"J": 2}}], "contractors": {"J": {"buses": [{"capacity": 30}]}}}
        mat_all = {"contractors": {"All": {"nodes": ["CAMPUS", "Z"], "durations_s": [[0, 1], [1, 0]]}}}
        with self.assertRaises(KeyError):
            combined_instance(inst, mat_all)


class RunScaleHelperTests(unittest.TestCase):
    """The pure parts of run_scale.py (Task 3)."""

    def test_best_by_takes_the_minimum_not_the_last_plan(self):
        from run_scale import best_by
        progress = [(0.1, 600), (0.5, 540), (2.0, 570), (11.0, 480)]   # the search accepts worse plans too
        self.assertEqual((best_by(progress, 10), best_by(progress, 60), best_by(progress, 0.05)), (540, 480, None))

    def test_improvements_counts_new_bests_only(self):
        from run_scale import improvements
        self.assertEqual(improvements([(0, 600), (1, 540), (2, 570), (3, 540), (4, 480)]), 3)
        self.assertEqual(improvements([]), 0)

    def test_checkpoints_past_the_budget_are_empty(self):
        from run_scale import checkpoint_fields
        f = checkpoint_fields([(1.0, 6000), (9.0, 5940)], 10)
        self.assertEqual(f, {"ride_10s": 99, "ride_60s": None, "ride_300s": None})

    def test_plan_keys(self):
        from run_scale import INSTANCES, plan
        full, quick = plan(INSTANCES), plan(["Nadeem"], quick=True)
        self.assertEqual(len(full), 8)
        self.assertEqual(len({j["key"] for j in full}), 8)
        self.assertEqual([j["key"] for j in quick], ["scale-quick-Nadeem-callback", "scale-quick-Nadeem-matrix"])
        self.assertTrue(all(j["repeat"] == 1 for j in full))          # the hub's Runs list reads it

    def test_skipped_rows_keep_the_column_order(self):
        from run_scale import FIRST, order_row
        row = order_row({"key": "k", "instance": "All", "status": "skipped", "setup": "All matrix", "reason": "x"})
        self.assertEqual(list(row)[:len(FIRST)], FIRST)
        self.assertIsNone(row["build_s"])

    def test_build_instance_by_name(self):
        from run_scale import base_name, build_instance, needs_combined
        inst = json.loads((DATA / "instance_fall2026_v1.json").read_text())
        mat = json.loads((DATA / "matrix_fall2026_v1.json").read_text())
        self.assertEqual(len(build_instance("Jadoon", inst, mat)["T"]) - 1, 171)
        self.assertEqual(len(build_instance("Nadeem-doubled", inst, mat)["T"]) - 1, 286)
        self.assertEqual((base_name("All-doubled"), needs_combined("All-doubled"), needs_combined("Nadeem")),
                         ("All", True, False))
        with self.assertRaises(FileNotFoundError):
            build_instance("All-doubled", inst, mat, None)
        with self.assertRaises(KeyError):
            build_instance("Nobody", inst, mat)


class OutputDirTests(unittest.TestCase):
    def test_relative_out_dir_is_made_absolute_from_the_callers_directory(self):
        import os, tempfile
        from run_scale import output_dir
        here = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                got = output_dir(Path("research/results/x"))
            finally:
                os.chdir(here)
            self.assertTrue(got.is_absolute())
            self.assertEqual(got, (Path(tmp) / "research/results/x").resolve())

    def test_default_out_dir(self):
        from run_scale import ROOT, output_dir
        self.assertEqual(output_dir(None), (ROOT / "results" / "optimizer-scale").resolve())
        self.assertEqual(output_dir(None, quick=True).name, "optimizer-scale-quick")


if __name__ == "__main__":
    unittest.main()
