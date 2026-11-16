"""Task 6: the request and proposal formats."""
import json
import math
import unittest

from reroute import Ladder, RequestError, failed_proposal, parse_request, table_rows, to_proposal
from reroute.model import Plan
from reroute.tests.helpers import TINY


def request(**changes):
    r = {"schema": 1, "graph": "karachi_v1",
         "trip": {"assignment_id": 41, "service_date": "2026-12-01", "direction": "morning"},
         "now": "2026-12-01T07:05:00+05:00", "deadline_s": 5,
         "position": {"lat": 24.91, "lng": 67.08},
         "remaining": [{"stop_id": 1, "route_stop_id": 901, "name": "A", "lat": 24.92, "lng": 67.09, "students": 4},
                       {"stop_id": 2, "route_stop_id": 902, "name": "B", "lat": 24.93, "lng": 67.10, "students": 2}],
         "candidates": [], "committed": [],
         "closures": [{"id": "incident-55", "circle": {"lat": 24.9, "lng": 67.09, "radius_m": 200}, "factor": 0.0}],
         "campus": {"lat": 24.856899, "lng": 67.264684}, "based_on": None}
    r.update(changes); return r


WALK = {(2, 1): 240.0}


class WireTests(unittest.TestCase):
    def solve(self, req, matrix=TINY):
        problem = parse_request(req, table_rows(matrix), WALK)
        return to_proposal(req, Ladder(problem).run(), compute_s=0.01, baseline_arrival_s=900.0)

    def test_reroute_proposal(self):
        out = self.solve(request())
        self.assertEqual((out["status"], out["visit"], out["delay_s"], out["students_walking"]),
                         ("reroute", [1], 40, 2))
        self.assertEqual(out["arrival"], "2026-12-01T07:20:40+05:00")
        self.assertEqual(out["stops"], [{"stop_id": 1, "action": "keep", "board_at": 1, "walk_m": 0},
                                        {"stop_id": 2, "action": "walk", "board_at": 1, "walk_m": 240}])
        json.dumps(out)

    def test_no_change_when_every_stop_must_be_served(self):
        req = request()
        for s in req["remaining"]:
            s["must_serve"] = True
        out = self.solve(req)
        self.assertEqual((out["status"], out["reason"], out["visit"]),
                         ("no_change", "published order is already best", [1, 2]))

    def test_campus_unreachable_is_failed(self):
        m = [row[:] for row in TINY]
        for i in range(3):
            m[i][3] = math.inf
        out = self.solve(request(), m)
        self.assertEqual((out["status"], out["reason"], out["arrival"], out["delay_s"]),
                         ("failed", "campus unreachable", None, None))

    def test_bad_requests_name_the_field(self):
        bad = {"schema": request(schema=2), "now": request(now="2026-12-01T07:05:00"),
               "committed": request(committed=[99])}
        r = request(); r["remaining"][1]["stop_id"] = 1; bad["stop_id"] = r
        r = request(); r["remaining"][0]["students"] = -1; bad["students"] = r
        r = request(); r["remaining"][0]["walk_limit_m"] = 900; bad["walk_limit_m"] = r
        r = request(); del r["closures"]; bad["closures"] = r
        for field, req in bad.items():
            with self.assertRaisesRegex(RequestError, field):
                parse_request(req, table_rows(TINY), WALK)

    def test_failed_proposal_shape(self):
        out = failed_proposal("no travel times")
        self.assertEqual((out["status"], out["reason"], out["visit"], out["stops"]),
                         ("failed", "no travel times", [], []))

    # Extra checks beyond the plan's list.

    def test_every_required_field_is_named_when_missing(self):
        for field in ("schema", "now", "remaining", "candidates", "closures", "campus", "position"):
            r = request(); del r[field]
            with self.assertRaisesRegex(RequestError, field):
                parse_request(r, table_rows(TINY), WALK)

    def test_defaults_and_candidates(self):
        matrix = [[0, 200, 50, math.inf, 590], [200, 0, 50, math.inf, 500], [50, 50, 0, math.inf, 600],
                  [100, 300, 80, 0, 650], [math.inf] * 4 + [0]]
        req = request(candidates=[{"stop_id": 77, "name": "NIPA", "lat": 24.91, "lng": 67.1},
                                  {"stop_id": 2, "name": "B again", "lat": 24.93, "lng": 67.1}],
                      committed=[77])
        p = parse_request(req, table_rows(matrix), WALK)
        self.assertEqual((p.points, sorted(p.committed)), ((1, 2, 77), [77]))
        self.assertEqual([(s.walk_limit_m, s.must_serve) for s in p.stops], [(400.0, False)] * 2)
        out = to_proposal(req, Ladder(p).run(), compute_s=0.2)
        self.assertIn(77, out["visit"])
        self.assertEqual((out["status"], out["delay_s"]), ("reroute", None))

    def test_unserved_stop_in_proposal(self):
        m = [row[:] for row in TINY]
        for i in range(4):
            if i != 1:
                m[i][1] = m[1][i] = math.inf
        req = request()
        req["remaining"][1]["walk_limit_m"] = 100
        out = self.solve(req, m)
        self.assertEqual(out["stops"][1], {"stop_id": 2, "action": "unserved", "board_at": None, "walk_m": 0})
        self.assertEqual((out["status"], out["students_walking"]), ("reroute", 0))

    def test_revision_state_and_negative_delay(self):
        problem = parse_request(request(), table_rows(TINY), WALK)
        lad = Ladder(problem)
        state = lad.to_json()
        out = to_proposal(request(), lad.run(), compute_s=1.5, baseline_arrival_s=950.0,
                          revision=3, state=state)
        self.assertEqual((out["revision"], out["state"], out["delay_s"], out["compute_s"]),
                         (3, state, -10, 1.5))
        self.assertEqual(set(out), set(failed_proposal("x")))

    def test_bad_entries_are_request_errors(self):
        cases = {"now": request(now="tomorrow"), "remaining": request(remaining={"stop_id": 1}),
                 "position": request(position={"lat": 1}), "must_serve": None}
        r = request(); r["remaining"][0]["must_serve"] = "yes"; cases["must_serve"] = r
        for field, req in cases.items():
            with self.assertRaisesRegex(RequestError, field):
                parse_request(req, table_rows(TINY), WALK)

    def test_walking_stop_without_distance_is_rejected(self):
        plan = Plan("R2", (1,), {1: 1, 2: 1}, (), 940.0, 480.0)     # no per-stop metres
        with self.assertRaises(ValueError):
            to_proposal(request(), plan, compute_s=0.0)


if __name__ == "__main__":
    unittest.main()
