"""Tests for `build_scenarios`, end to end on the toy city with the fake OSRM (no Docker).

The toy city (`tests/toy_city.py`) has two routes: Jadoon R-1 (A, B, C, long legs) and Nadeem R-2
(D, X, E, F, where X has no R-2 students). Stop Y sits on a street joined to nothing.
"""
import copy
import csv
import json
import math
import tempfile
import unittest
from pathlib import Path

import build_scenarios as bs
from reroute.closure import Closure
from reroute.graph import Graph
from reroute.roadnet import haversine_m
from tests.fake_osrm import FakeOsrm, make_osrm_folder
from tests.toy_city import (CAMPUS, ID, INSTANCE, STUDENT_ROWS, TABLES, WALK, node_at, node_id,
                            stop_point)

A, B, C, D, X, E, F, Y = (ID[n] for n in "ABCDXEFY")

# A full block along column 4 from B to C, and University-Road-like slowing along row 3 from D to X.
HISTORICAL = [
    {"id": "col4-block", "name": "Column 4, B to C", "factor": 0.0, "both_directions": True,
     "from": {"lat": stop_point("B")[0], "lng": stop_point("B")[1]},
     "to": {"lat": stop_point("C")[0], "lng": stop_point("C")[1]}, "source": "toy"},
    {"id": "row3-slow", "name": "Row 3, D to X", "factor": 0.25, "both_directions": True,
     "from": {"lat": stop_point("D")[0], "lng": stop_point("D")[1]},
     "to": {"lat": stop_point("X")[0], "lng": stop_point("X")[1]}, "source": "toy"},
]


def builder(tmp: Path, fake: FakeOsrm, block_kmh: int = 0) -> bs.ScenarioBuilder:
    car = make_osrm_folder(tmp / "car")
    return bs.ScenarioBuilder(fake, Graph(TABLES), INSTANCE, STUDENT_ROWS, WALK, car, tmp / "work",
                              block_kmh=block_kmh)


def by_id(items):
    return {x["id"]: x for x in items}


class RouteStopsTests(unittest.TestCase):
    def test_stops_without_students_on_this_route_are_dropped(self):
        routes = {(r.contractor, r.code): r for r in bs.route_stops(INSTANCE, STUDENT_ROWS)}
        r2 = routes[("Nadeem", "R-2")]
        self.assertEqual(r2.stop_ids, [D, E, F])
        self.assertEqual(r2.dropped, ["X"])
        self.assertEqual(r2.students, {D: 2, E: 1, F: 5})
        self.assertEqual(routes[("Jadoon", "R-1")].stop_ids, [A, B, C])

    def test_only_one_route(self):
        routes = bs.route_stops(INSTANCE, STUDENT_ROWS, only=("Nadeem", "R-2"))
        self.assertEqual([(r.contractor, r.code) for r in routes], [("Nadeem", "R-2")])
        with self.assertRaises(KeyError):
            bs.route_stops(INSTANCE, STUDENT_ROWS, only=("Nadeem", "R-404"))


class SpeedRowTests(unittest.TestCase):
    G = Graph(TABLES)

    def test_full_block_rows_use_the_block_speed(self):
        c = Closure("c", ((*node_at(0, 2), 30.0),), 0.0)
        self.assertEqual({kmh for _, _, kmh in bs.speed_rows(self.G, c)}, {0})
        self.assertEqual({kmh for _, _, kmh in bs.speed_rows(self.G, c, block_kmh=1)}, {1})

    def test_slowed_rows_are_10_kmh_at_most(self):
        c = Closure("c", ((*node_at(0, 2), 30.0),), 0.25)
        rows = bs.speed_rows(self.G, c)
        self.assertEqual(len(rows), 6)                       # three two-way segments touch the node
        self.assertEqual({kmh for _, _, kmh in rows}, {10})


class TableCheckTests(unittest.TestCase):
    def test_faster_pairs_ignores_infinity_and_small_noise(self):
        inf = math.inf
        pre = [[0, 100, inf], [100, 0, 50]]
        post = [[0, 99.8, 10], [90, 0, inf]]
        self.assertEqual(bs.faster_pairs(pre, post), 1)          # only 100 -> 90

    def test_line_from_route_swaps_to_lat_lng(self):
        route = {"geometry": {"coordinates": [[67.1, 24.9], [67.2, 24.8]]}}
        self.assertEqual(bs.line_from(route), [(24.9, 67.1), (24.8, 67.2)])


class BuildTests(unittest.TestCase):
    """One build of the whole toy city, synthetic and historical."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.fake = FakeOsrm(TABLES)
        b = builder(Path(cls.tmp.name), cls.fake)
        cls.out = b.build(bs.route_stops(INSTANCE, STUDENT_ROWS), HISTORICAL)
        cls.closures = by_id(cls.out["closures"])
        cls.scenarios = by_id(cls.out["scenarios"])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def closure(self, cid):
        return self.closures[cid]

    def test_counts(self):
        synthetic = [c for c in self.out["closures"] if c["kind"] == "synthetic"]
        self.assertEqual(sorted(c["id"] for c in synthetic),
                         ["Jadoon-R-1-L1", "Jadoon-R-1-L2", "Nadeem-R-2-L1", "Nadeem-R-2-L2"])
        self.assertEqual(sum(s["closure"] in {c["id"] for c in synthetic} for s in self.out["scenarios"]), 8)
        # One customization per synthetic closure and one per historical stretch.
        self.assertEqual(len(self.fake.customizations), 6)

    def test_no_leaks(self):
        for c in self.out["closures"]:
            if c["factor"] == 0.0:
                self.assertEqual(c["leaks"], 0, c["id"])

    def test_three_stop_route_closes_two_different_legs(self):
        l1, l2 = self.closure("Jadoon-R-1-L1"), self.closure("Jadoon-R-1-L2")
        self.assertEqual((l1["leg"], l2["leg"]), (1, 2))
        self.assertNotEqual(l1["circles"], l2["circles"])
        # Each circle sits halfway along its own leg: node (0,2) between A and B, (1,4) between B and C.
        self.assertLess(haversine_m(*l1["circles"][0][:2], *node_at(0, 2)), 1.0)
        self.assertLess(haversine_m(*l2["circles"][0][:2], *node_at(1, 4)), 1.0)
        self.assertEqual(l1["circles"][0][2], 200.0)

    def test_tables_are_points_then_campus(self):
        c = self.closure("Jadoon-R-1-L1")
        self.assertEqual(c["points"], [A, B, C, Y])
        for t in (c["pre"], c["post"]):
            self.assertEqual(len(t), 5)
            self.assertTrue(all(len(row) == 5 for row in t))
        self.assertEqual(self.closure("Nadeem-R-2-L1")["points"], [D, E, F, X])

    def test_unreachable_pairs_are_null(self):
        pre = self.closure("Jadoon-R-1-L1")["pre"]
        y = 3
        self.assertEqual(pre[y][y], 0)
        self.assertTrue(all(pre[y][j] is None for j in range(5) if j != y))
        self.assertTrue(all(pre[i][y] is None for i in range(5) if i != y))
        self.assertIsNotNone(pre[0][1])

    def test_points_inside_a_full_block_are_infinite(self):
        c = self.closure("Nadeem-R-2-L2")
        self.assertEqual(c["closed_points"], [E, F])
        e, f = c["points"].index(E), c["points"].index(F)
        for k in (e, f):
            self.assertEqual(c["post"][k][k], 0)
            self.assertTrue(all(c["post"][k][j] is None for j in range(len(c["post"])) if j != k))
            self.assertTrue(all(c["post"][i][k] is None for i in range(len(c["post"])) if i != k))
        # The pre table is left as OSRM returned it.
        self.assertIsNotNone(c["pre"][e][f])

    def test_a_closed_candidate_is_marked_but_not_tagged(self):
        c = self.closure("Nadeem-R-2-L1")
        self.assertEqual(c["closed_points"], [X])
        for trig in ("early", "late"):
            self.assertFalse(self.scenarios[f"Nadeem-R-2-L1-{trig}"]["tags"]["closure_contains_stop"])

    def test_closure_containing_a_stop_is_kept_and_tagged(self):
        early, late = self.scenarios["Nadeem-R-2-L2-early"], self.scenarios["Nadeem-R-2-L2-late"]
        self.assertEqual((late["position"], late["remaining"]), (E, [F]))
        self.assertEqual(early["remaining"], [D, E, F])
        self.assertTrue(early["tags"]["closure_contains_stop"])
        self.assertTrue(late["tags"]["closure_contains_stop"])
        self.assertEqual(late["tags"]["remaining"], 1)
        for trig in ("early", "late"):
            self.assertFalse(self.scenarios[f"Jadoon-R-1-L1-{trig}"]["tags"]["closure_contains_stop"])

    def test_a_stop_without_students_here_is_never_remaining(self):
        r2 = [s for s in self.out["scenarios"] if "Nadeem-R-2" in s["closure"]]
        self.assertTrue(r2)
        for s in r2:
            self.assertNotIn(X, s["remaining"])
            self.assertNotEqual(s["position"], X)
        # It may still be a walking candidate.
        self.assertIn(X, self.scenarios["Nadeem-R-2-L1-early"]["candidates"])

    def test_scenario_fields(self):
        s = self.scenarios["Jadoon-R-1-L1-early"]
        self.assertEqual(s["closure"], "Jadoon-R-1-L1")
        self.assertEqual(s["position"], A)
        self.assertEqual(s["students"], {str(A): 3, str(B): 2, str(C): 4})
        self.assertEqual(s["candidates"], [Y])
        late = self.scenarios["Jadoon-R-1-L1-late"]
        self.assertEqual((late["position"], late["remaining"], late["candidates"]), (A, [B, C], []))
        self.assertEqual(late["students"], {str(B): 2, str(C): 4})

    def test_post_is_never_faster_and_the_closure_slows_something(self):
        for cid in ("Jadoon-R-1-L1", "Jadoon-R-1-L2", "Nadeem-R-2-L1"):
            c = self.closure(cid)
            pre, post = bs.load_table(c["pre"]), bs.load_table(c["post"])
            self.assertEqual(bs.faster_pairs(pre, post), 0, cid)
            self.assertTrue(any(q > p for rp, rq in zip(pre, post) for p, q in zip(rp, rq)
                                if math.isfinite(p) and math.isfinite(q)), cid)

    def test_every_closure_starts_from_the_untouched_copy(self):
        # Leg 2's server must not still carry leg 1's closure: A to B is free-flow again.
        l2 = self.closure("Jadoon-R-1-L2")
        self.assertEqual(l2["post"][0][1], l2["pre"][0][1])

    def test_closure_bookkeeping(self):
        c = self.closure("Jadoon-R-1-L1")
        self.assertEqual((c["kind"], c["contractor"], c["route"], c["factor"]), ("synthetic", "Jadoon", "R-1", 0.0))
        self.assertGreater(c["segments"], 0)
        self.assertEqual(c["customize_s"], 1.5)

    def test_header(self):
        self.assertEqual(self.out["version"], "reroute-v1")
        self.assertEqual(self.out["instance"], "toy-v1")
        self.assertEqual(self.out["block_kmh"], 0)
        self.assertEqual(self.out["osrm_image"], "ghcr.io/project-osrm/osrm-backend:v5.27.1")

    def test_historical_block_applies_to_routes_whose_path_crosses_it(self):
        hist = [c for c in self.out["closures"] if c["kind"] == "historical"]
        self.assertEqual(sorted(c["id"] for c in hist), ["col4-block-Jadoon-R-1", "row3-slow-Nadeem-R-2"])
        c = self.closure("col4-block-Jadoon-R-1")
        self.assertNotIn("leg", c)
        self.assertEqual(c["stretch"], "col4-block")
        self.assertEqual(len(c["circles"]), 5)                   # about 444 m: round(4.44) + 1
        self.assertEqual({r for _, _, r in c["circles"]}, {60.0})
        self.assertEqual(c["closed_points"], [B, C])
        self.assertEqual(c["leaks"], 0)
        # First met on leg 1 (A to B ends inside it): early at A, late at A with B and C remaining.
        late = self.scenarios["col4-block-Jadoon-R-1-late"]
        self.assertEqual((late["position"], late["remaining"]), (A, [B, C]))
        self.assertIn("col4-block-Jadoon-R-1-early", self.scenarios)

    def test_historical_slowed_stretch(self):
        c = self.closure("row3-slow-Nadeem-R-2")
        self.assertEqual(c["factor"], 0.25)
        self.assertEqual(c["closed_points"], [])
        self.assertIsNone(c["leaks"])
        pre, post = bs.load_table(c["pre"]), bs.load_table(c["post"])
        self.assertGreater(post[0][1], pre[0][1])                # D to E is slower
        self.assertTrue(all(math.isfinite(v) for row in post for v in row))   # slowed, never closed


class LeakTests(unittest.TestCase):
    def test_an_osrm_that_ignores_the_block_shows_leaks(self):
        with tempfile.TemporaryDirectory() as tmp:
            b = builder(Path(tmp), FakeOsrm(TABLES, ignore_block=True))
            out = b.build(bs.route_stops(INSTANCE, STUDENT_ROWS, only=("Jadoon", "R-1")), [])
        leaks = {c["id"]: c["leaks"] for c in out["closures"]}
        self.assertGreaterEqual(leaks["Jadoon-R-1-L1"], 1)       # A to B drives straight through
        self.assertEqual(bs.summary(out)["closures_with_leaks"], 2 if leaks["Jadoon-R-1-L2"] else 1)


class LoadTests(unittest.TestCase):
    def test_null_reads_back_as_infinity(self):
        data = {"version": "reroute-v1", "closures": [{"id": "c", "pre": [[0, None], [3.5, 0]],
                                                       "post": [[0, None], [None, 0]]}], "scenarios": []}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text(json.dumps(data))
            loaded = bs.load_scenarios(path)
        self.assertEqual(loaded["closures"][0]["pre"], [[0, math.inf], [3.5, 0]])
        self.assertEqual(loaded["closures"][0]["post"], [[0, math.inf], [math.inf, 0]])


class MainTests(unittest.TestCase):
    """The command line: input files, `--route`, `--resume`, and blank historical coordinates."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.car = make_osrm_folder(root / "car")
        self.work = root / "work"
        self.instance = root / "instance.json"
        self.instance.write_text(json.dumps(INSTANCE))
        self.students = root / "students.csv"
        with self.students.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["contractor", "stop", "baseline_route"])
            w.writeheader()
            w.writerows(STUDENT_ROWS)
        self.walk = root / "walk.json"
        self.walk.write_text(json.dumps({"version": "walk-toy", "pairs": [[a, b, m] for (a, b), m in WALK.items()]}))
        self.hist = root / "hist.json"
        self.hist.write_text(json.dumps(HISTORICAL))
        self.out = root / "scenarios.json"

    def tearDown(self):
        self.tmp.cleanup()

    def argv(self, *extra):
        return ["--car-dir", str(self.car), "--work-dir", str(self.work), "--instance", str(self.instance),
                "--students", str(self.students), "--walk", str(self.walk), "--historical", str(self.hist),
                "--out", str(self.out), *extra]

    def test_full_run_then_resume_does_nothing_new(self):
        fake = FakeOsrm(TABLES)
        bs.main(self.argv(), osrm=fake, graph=Graph(TABLES))
        first = json.loads(self.out.read_text())
        self.assertEqual(first["walk"], "walk-toy")
        self.assertEqual(len(first["closures"]), 6)
        n = len(fake.customizations)
        bs.main(self.argv("--resume"), osrm=fake, graph=Graph(TABLES))
        self.assertEqual(len(fake.customizations), n)
        second = json.loads(self.out.read_text())
        self.assertEqual([c["id"] for c in second["closures"]], [c["id"] for c in first["closures"]])
        self.assertEqual(second["scenarios"], first["scenarios"])

    def test_resume_finishes_a_partial_file(self):
        fake = FakeOsrm(TABLES)
        bs.main(self.argv("--skip-historical"), osrm=fake, graph=Graph(TABLES))
        partial = json.loads(self.out.read_text())
        partial["closures"] = [c for c in partial["closures"] if c["id"] != "Nadeem-R-2-L2"]
        partial["scenarios"] = [s for s in partial["scenarios"] if s["closure"] != "Nadeem-R-2-L2"]
        self.out.write_text(json.dumps(partial))
        fake2 = FakeOsrm(TABLES)
        bs.main(self.argv("--skip-historical", "--resume"), osrm=fake2, graph=Graph(TABLES))
        self.assertEqual(len(fake2.customizations), 1)
        done = json.loads(self.out.read_text())
        self.assertEqual(len(done["closures"]), 4)
        self.assertEqual(len(done["scenarios"]), 8)

    def test_resume_refuses_a_file_built_with_another_block_speed(self):
        fake = FakeOsrm(TABLES)
        bs.main(self.argv("--skip-historical"), osrm=fake, graph=Graph(TABLES))
        with self.assertRaises(SystemExit):
            bs.main(self.argv("--skip-historical", "--resume", "--block-kmh", "1"), osrm=fake, graph=Graph(TABLES))

    def test_one_route(self):
        fake = FakeOsrm(TABLES)
        bs.main(self.argv("--route", "Jadoon:R-1", "--skip-historical"), osrm=fake, graph=Graph(TABLES))
        data = json.loads(self.out.read_text())
        self.assertEqual({c["route"] for c in data["closures"]}, {"R-1"})
        self.assertEqual(len(data["scenarios"]), 4)

    def test_blank_historical_coordinates_stop_the_build(self):
        blank = copy.deepcopy(HISTORICAL)
        blank[0]["from"] = {"lat": None, "lng": None}
        self.hist.write_text(json.dumps(blank))
        with self.assertRaises(SystemExit) as ctx:
            bs.main(self.argv(), osrm=FakeOsrm(TABLES), graph=Graph(TABLES))
        self.assertIn("--skip-historical", str(ctx.exception))

    def test_servers_are_stopped(self):
        fake = FakeOsrm(TABLES)
        bs.main(self.argv("--skip-historical"), osrm=fake, graph=Graph(TABLES))
        self.assertEqual(fake.names, {})


if __name__ == "__main__":
    unittest.main()
