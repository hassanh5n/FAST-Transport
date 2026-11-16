"""Tests for the fixes made after the offline-builders review (beyond tests/test_review_offline.py).

Run from `research/`: `python -m unittest tests.test_offline_fixes -v`.
"""
import tempfile
import unittest
from pathlib import Path

import build_scenarios as bs
import osrm_tools
import run_roadblock as rb
from reroute.graph import Graph
from tests.fake_osrm import FakeOsrm, make_osrm_folder
from tests.toy_city import INSTANCE, STUDENT_ROWS, TABLES, WALK, node_at


class FreshCopyGuardTests(unittest.TestCase):
    def test_ancestor_work_folder_is_refused_with_a_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "fleetcentric-osrm"
            car = make_osrm_folder(home / "car")
            with self.assertRaises(ValueError):
                osrm_tools.fresh_copy(car, home)
            self.assertTrue((car / osrm_tools.OSRM_BASENAME).exists())

    def test_sibling_work_folder_with_a_shared_prefix_is_allowed(self):
        # `car-work` starts with `car` but is not inside it; a string-prefix check would refuse it.
        with tempfile.TemporaryDirectory() as tmp:
            car = make_osrm_folder(Path(tmp) / "car")
            osrm_tools.fresh_copy(car, Path(tmp) / "car-work")
            self.assertTrue((Path(tmp) / "car-work" / osrm_tools.OSRM_BASENAME).exists())


class LeakChainTests(unittest.TestCase):
    def test_open_points_are_chained_past_the_closed_ones(self):
        # Nadeem R-2 = D, E, F; the L2 circle holds E and F, so the only open pair is D -> campus.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fake = FakeOsrm(TABLES)
            b = bs.ScenarioBuilder(fake, Graph(TABLES), INSTANCE, STUDENT_ROWS, WALK,
                                   make_osrm_folder(tmp / "car"), tmp / "work", log=lambda s: None)
            routes = bs.route_stops(INSTANCE, STUDENT_ROWS, only=("Nadeem", "R-2"))
            out = b.build(routes, [])
            entry = {c["id"]: c for c in out["closures"]}["Nadeem-R-2-L2"]
            route = routes[0]
            closed = set(entry["closed_points"])
            open_seq = [p for p in route.stop_ids + [bs.CAMPUS_ID] if p not in closed]
            starts = [i for i, c in enumerate(fake.calls) if c[0] == "start" and c[2] == bs.CLOSED_PORT]
            routed = [c for c in fake.calls[starts[-1]:]
                      if c[0] == "route" and c[1] == f"http://localhost:{bs.CLOSED_PORT}"]
            self.assertEqual(len(routed), len(open_seq) - 1)


class RoadblockTimingTests(unittest.TestCase):
    def test_each_timed_start_follows_a_stop_of_the_test_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fake = FakeOsrm(TABLES)
            rb.run_test(fake, Graph(TABLES), (node_at(0, 0), node_at(0, 4)),
                        make_osrm_folder(tmp / "car"), tmp / "work", repeats=2)
            starts = [i for i, c in enumerate(fake.calls) if c[0] == "start" and c[3] == rb.TEST_NAME]
            for i in starts[-2:]:                   # the two timing repeats
                self.assertEqual(fake.calls[i - 1], ("stop", rb.TEST_NAME))


if __name__ == "__main__":
    unittest.main()
