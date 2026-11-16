"""Tests for `run_roadblock`: the answer rules, and the whole test run against the fake OSRM."""
import json
import tempfile
import unittest
from pathlib import Path

import run_roadblock as rb
from reroute.graph import Graph
from tests.fake_osrm import FakeOsrm, make_osrm_folder
from tests.toy_city import TABLES, node_at, node_id


class AnswerRuleTests(unittest.TestCase):
    def test_middle_pair(self):
        self.assertEqual(rb.middle_pair([1, 2, 3, 4, 5]), (3, 4))       # pairs 12 23 34 45 -> index 2
        self.assertEqual(rb.middle_pair([7, 8]), (7, 8))
        with self.assertRaises(ValueError):
            rb.middle_pair([7])

    def test_uses_pair_in_either_direction(self):
        self.assertTrue(rb.uses_pair([1, 2, 3], (2, 3)))
        self.assertTrue(rb.uses_pair([1, 3, 2], (2, 3)))
        self.assertFalse(rb.uses_pair([2, 1, 3], (2, 3)))                # both nodes, not adjacent

    def test_block_answer(self):
        pair = (2, 3)
        self.assertEqual(rb.block_answer([1, 2, 3, 4], 100, [1, 5, 6, 4], 140, pair), "blocks")
        self.assertEqual(rb.block_answer([1, 2, 3, 4], 100, [1, 2, 3, 4], 100, pair), "ignored")
        # Changed but still through the pair, or avoiding it without getting slower: not clear-cut.
        self.assertEqual(rb.block_answer([1, 2, 3, 4], 100, [1, 2, 3, 7, 4], 150, pair), "unclear")
        self.assertEqual(rb.block_answer([1, 2, 3, 4], 100, [1, 5, 4], 100, pair), "unclear")

    def test_snap_answer_needs_more_than_20_m(self):
        self.assertEqual(rb.snap_answer(3.0, 23.5), "moved")
        self.assertEqual(rb.snap_answer(3.0, 23.0), "not moved")

    def test_slowed_answer(self):
        self.assertEqual(rb.slowed_answer([1, 2, 3], 100, [1, 4, 3], 120), "changes route")
        self.assertEqual(rb.slowed_answer([1, 2, 3], 100, [1, 2, 3], 160), "same route, longer")
        self.assertEqual(rb.slowed_answer([1, 2, 3], 100, [1, 2, 3], 100.04), "no effect")

    def test_peak_ram_from_the_osrm_log(self):
        log = "[info] Customize\n[info] RAM: peak bytes used: 734003200\n"
        self.assertEqual(rb.peak_ram_bytes(log), 734003200)
        self.assertIsNone(rb.peak_ram_bytes("[info] finished"))

    def test_route_nodes_joins_legs_without_repeating_the_joint(self):
        route = {"legs": [{"annotation": {"nodes": [1, 2, 3]}}, {"annotation": {"nodes": [3, 4]}}]}
        self.assertEqual(rb.route_nodes(route), [1, 2, 3, 4])

    def test_segment_midpoint_from_the_graph(self):
        g = Graph(TABLES)
        lat, lng = rb.segment_midpoint(g, (node_id(0, 2), node_id(0, 3)))
        self.assertAlmostEqual(lat, 24.900)
        self.assertAlmostEqual(lng, 67.00625)
        with self.assertRaises(ValueError):
            rb.segment_midpoint(g, (node_id(0, 2), node_id(4, 4)))


class RunTests(unittest.TestCase):
    """The whole test on the toy grid: the leg runs along row 0 from (0,0) to (0,4)."""

    LEG = (node_at(0, 0), node_at(0, 4))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.car = make_osrm_folder(root / "car")
        self.work = root / "work"
        self.graph = Graph(TABLES)

    def tearDown(self):
        self.tmp.cleanup()

    def run_with(self, fake):
        return rb.run_test(fake, self.graph, self.LEG, self.car, self.work, repeats=3)

    def test_speed_zero_blocks_on_a_working_osrm(self):
        fake = FakeOsrm(TABLES)
        result = self.run_with(fake)
        answers = [c["answer"] for c in result["checks"]]
        self.assertEqual(answers[0], "blocks")
        self.assertEqual(result["block_kmh"], 0)
        self.assertEqual(result["leg"]["pair"], [node_id(0, 2), node_id(0, 3)])
        # The fake snaps to nodes, both ends of the closed pair keep other open roads.
        self.assertEqual(answers[1], "not moved")
        self.assertEqual(answers[2], "changes route")
        self.assertEqual(len(result["checks"]), 4)
        self.assertIn("median of 3", result["checks"][3]["answer"])

    def test_timings_and_memory(self):
        fake = FakeOsrm(TABLES, customize_s=2.5)
        t = self.run_with(fake)["timings"]
        self.assertEqual(len(t["repeats"]), 3)
        self.assertEqual({r["customize_s"] for r in t["repeats"]}, {2.5})
        self.assertEqual({r["peak_ram_mb"] for r in t["repeats"]}, {round(123_456_789 / 2 ** 20, 1)})
        self.assertEqual(t["median"]["customize_s"], 2.5)
        for r in t["repeats"]:
            self.assertGreaterEqual(r["copy_s"], 0)
            self.assertGreaterEqual(r["start_s"], 0)

    def test_every_customization_starts_from_a_fresh_copy(self):
        fake = FakeOsrm(TABLES)
        self.run_with(fake)
        # block, slowed and three timing repeats: five customizations, each alone in its copy.
        self.assertEqual(len(fake.customizations), 5)
        self.assertEqual((self.work / "updates.csv").read_text(), fake.customizations[-1])
        self.assertFalse((self.car / "updates.csv").exists())

    def test_servers_are_stopped_at_the_end(self):
        fake = FakeOsrm(TABLES)
        self.run_with(fake)
        self.assertEqual(fake.names, {})

    def test_an_ignored_block_is_retried_at_1_kmh(self):
        fake = FakeOsrm(TABLES, ignore_block=True)
        result = self.run_with(fake)
        first, extra = result["checks"][0], result["checks"][1]
        self.assertEqual(first["answer"], "ignored")
        self.assertIn("1 km/h", extra["question"])
        self.assertEqual(extra["answer"], "blocks")
        self.assertEqual(result["block_kmh"], 1)
        self.assertEqual(len(result["checks"]), 5)
        # The timing runs then close the pair at 1 km/h.
        self.assertTrue(fake.customizations[-1].strip().endswith(",1"))

    def test_main_writes_result_json(self):
        fake = FakeOsrm(TABLES)
        out = Path(self.tmp.name) / "roadblock" / "result.json"
        instance = {"stops": [{"name": "Hyderi Super Mart KDA", "lat": self.LEG[0][0], "lng": self.LEG[0][1]},
                              {"name": "Ziauddin", "lat": self.LEG[1][0], "lng": self.LEG[1][1]}],
                    "contractors": {"Jadoon": {"baseline_routes": [
                        {"code": "R-10", "stops": ["Hyderi Super Mart KDA", "Ziauddin", "Elsewhere"]}]}}}
        inst = Path(self.tmp.name) / "instance.json"
        inst.write_text(json.dumps(instance))
        rb.main(["--car-dir", str(self.car), "--work-dir", str(self.work), "--instance", str(inst),
                 "--out", str(out), "--repeats", "2"], osrm=fake, graph=self.graph)
        data = json.loads(out.read_text())
        self.assertEqual(set(data) >= {"machine", "osrm_image", "checks", "timings"}, True)
        self.assertEqual(data["osrm_image"], "ghcr.io/project-osrm/osrm-backend:v5.27.1")
        for check in data["checks"]:
            self.assertEqual(set(check), {"question", "answer", "evidence"})

    def test_first_leg_of_a_route(self):
        instance = {"stops": [{"name": "P", "lat": 1.0, "lng": 2.0}, {"name": "Q", "lat": 3.0, "lng": 4.0}],
                    "contractors": {"Jadoon": {"baseline_routes": [{"code": "R-10", "stops": ["P", "Q"]}]}}}
        self.assertEqual(rb.first_leg(instance, "Jadoon", "R-10"), (("P", (1.0, 2.0)), ("Q", (3.0, 4.0))))


if __name__ == "__main__":
    unittest.main()
