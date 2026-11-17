"""The site index carries what the experiment pages read (hub/web/app.js), built with the standard library only."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH / "hub"))
sys.path.insert(0, str(RESEARCH))
import build_site  # noqa: E402
import run_reroute  # noqa: E402


class PassRulesTests(unittest.TestCase):
    def test_no_verdict_means_every_chip_pending(self):
        for kind in ("quality", "limits"):
            chips, thresholds = run_reroute.pass_rules(kind)
            self.assertEqual(len(chips), 3)
            self.assertTrue(all(c["result"] is None for c in chips))
            self.assertNotIn("note", thresholds)
        self.assertEqual(run_reroute.pass_rules("scale"), ([], {"note": "curves only, no pass or fail"}))

    def test_chips_match_the_summary_of_a_finished_pass(self):
        s = run_reroute.build_summary(RESEARCH / "results" / "reroute-quality-quick")
        chips, thresholds = run_reroute.pass_rules("quality", s["verdict"])
        self.assertEqual((chips, thresholds), (s["chips"], s["thresholds"]))
        self.assertEqual([c["result"] for c in chips], ["pass", "pass", "pass"])


class SiteIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as tmp:
            out = build_site.build(Path(tmp) / "site")
            cls.index = json.loads((out / "data" / "index.json").read_text(encoding="utf-8"))
        cls.exp = {e["id"]: e for e in cls.index["experiments"]}

    def test_a_pass_with_no_runs_carries_its_pending_rules(self):
        for exp_id, kind in (("reroute-quality", "quality"), ("reroute-limits", "limits")):
            e = self.exp[exp_id]
            if "summary" in e:
                self.skipTest(f"{exp_id} has runs now")
            self.assertEqual(e["state"], "not started")
            self.assertEqual(e["pending"]["pass"], kind)
            self.assertEqual((e["pending"]["chips"], e["pending"]["thresholds"]), run_reroute.pass_rules(kind))

    def test_non_reroute_experiments_have_no_pending_key(self):
        for e in self.index["experiments"]:
            if e["kind"] != "reroute":
                self.assertNotIn("pending", e)

    def test_summaries_the_pages_read(self):
        q = self.exp["reroute-quality-quick"]["summary"]
        self.assertEqual(q["pass"], "quality")
        self.assertTrue({"cells", "per_route", "thresholds", "judged_share"} <= q.keys())
        self.assertEqual(self.exp["reroute-limits-quick"]["summary"]["pass"], "limits")
        scale = self.exp["reroute-scale"]["summary"]
        self.assertEqual((scale["pass"], len(scale["rows"]), scale["meta"]["only"]), ("scale", 45, "stops"))
        opt = self.exp["optimizer-scale"]["summary"]
        self.assertEqual(len(opt["rows"]), 12)
        self.assertEqual(sum(r["status"] == "skipped" for r in opt["rows"]), 4)
        self.assertTrue(all(r.get("reason") for r in opt["rows"] if r["status"] == "skipped"))

    def test_the_project_phases_name_known_experiments(self):
        for phase in self.index["project"]["phases"]:
            for item in phase["items"]:
                for exp_id in item["experiments"]:
                    self.assertIn(exp_id, self.exp)


def fake_scenarios(path):
    """A tiny scenario file in the frozen format: one closure on a route of stops 0, 1, 2, its early and
    late scenarios, candidate 5, and the tables the map must leave out."""
    head = {"id": "Jadoon-R-1-L2", "kind": "synthetic", "contractor": "Jadoon", "route": "R-1", "leg": 2}
    closure = {**head, "circles": [[24.9, 67.1, 200.0]], "points": [0, 1, 2, 5], "closed_points": [2],
               "pre": [[0, 1], [1, 0]], "post": [[0, None], [None, 0]]}
    scen = [{"id": "Jadoon-R-1-L2-early", "closure": head["id"], "trigger": "early", "position": 0,
             "remaining": [0, 1, 2], "students": {"0": 3, "1": 2, "2": 4}, "candidates": [5], "tags": {}},
            {"id": "Jadoon-R-1-L2-late", "closure": head["id"], "trigger": "late", "position": 1,
             "remaining": [2], "students": {"2": 4}, "candidates": [5], "tags": {}}]
    path.write_text(json.dumps({"version": "reroute-v1", "instance": "fall2026-v1", "closures": [closure],
                                "scenarios": scen}), encoding="utf-8")
    return path


def fake_instance(path):
    stops = [{"name": f"Stop {i}", "lat": 24.9 + i / 100, "lng": 67.0 + i / 100} for i in range(7)]
    path.write_text(json.dumps({"campus": {"name": "Campus", "lat": 24.85, "lng": 67.26}, "stops": stops}),
                    encoding="utf-8")
    return path


class PlanMapDataTests(unittest.TestCase):
    def test_no_scenario_file_publishes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(build_site.reroute_map_data(Path(tmp) / "missing.json", fake_instance(Path(tmp) / "i.json")))

    def test_map_data_from_a_tiny_scenario_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = build_site.reroute_map_data(fake_scenarios(Path(tmp) / "s.json"), fake_instance(Path(tmp) / "i.json"))
        self.assertEqual(sorted(d["scenarios"]), ["Jadoon-R-1-L2-early", "Jadoon-R-1-L2-late"])
        late = d["scenarios"]["Jadoon-R-1-L2-late"]
        self.assertEqual((late["position"], late["remaining"], late["candidates"]), (1, [2], [5]))
        self.assertEqual(late["route_order"], [0, 1, 2])        # from the early scenario: the whole route
        self.assertEqual((late["route"], late["closed_points"], late["circles"]), ("Jadoon-R-1", [2], [[24.9, 67.1, 200.0]]))
        self.assertEqual(sorted(d["points"], key=int), ["-1", "0", "1", "2", "5"])   # only the points used, campus -1
        self.assertEqual(d["points"]["5"], [24.95, 67.05, "Stop 5"])
        self.assertEqual(d["points"]["-1"], [24.85, 67.26, "Campus"])
        self.assertNotIn("pre", json.dumps(d))                  # no tables

    def test_build_publishes_the_map_file_only_when_the_scenario_file_exists(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            scen = fake_scenarios(Path(tmp) / "scenarios.json")
            with mock.patch.object(build_site.run_reroute, "SCENARIOS", scen):
                out = build_site.build(Path(tmp) / "site")
            index = json.loads((out / "data" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["reroute_map"], "data/reroute_map.json")
            pm = json.loads((out / "data" / "reroute_map.json").read_text(encoding="utf-8"))
            self.assertIn("Jadoon-R-1-L2-late", pm["scenarios"])
            with mock.patch.object(build_site.run_reroute, "SCENARIOS", Path(tmp) / "none.json"):
                out = build_site.build(Path(tmp) / "site2")
            index = json.loads((out / "data" / "index.json").read_text(encoding="utf-8"))
            self.assertIsNone(index["reroute_map"])
            self.assertFalse((out / "data" / "reroute_map.json").exists())


class StdlibOnlyTests(unittest.TestCase):
    def test_site_builds_without_numpy_or_scipy(self):
        code = ("import sys; sys.modules['numpy'] = None; sys.modules['scipy'] = None; "
                f"sys.path.insert(0, {str(RESEARCH / 'hub')!r}); sys.path.insert(0, {str(RESEARCH)!r}); "
                "import build_site, tempfile, pathlib; build_site.build(pathlib.Path(tempfile.mkdtemp()) / 'site'); "
                "print('built')")
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("built", r.stdout)


if __name__ == "__main__":
    unittest.main()
