"""Reviewer's tests for the solver core: each test here pins a defect found in review (R3 not
exact when its search revisits a point, NaN travel times accepted, ``schema: true`` accepted)."""
import math
import unittest

from reroute import Ladder, RequestError, parse_request, table_rows
from reroute.ladder import _context, r3_advance, r3_start, solve_r2, solve_r3
from reroute.model import Problem, StopNeed
from reroute.tests.helpers import TINY, brute_force, random_problem, tiny_problem

# (seed, n_stops, n_extra) of metric random problems (walk limit 400 m) where R3 is not exact.
NOT_EXACT = [(125, 3, 2), (133, 3, 1), (138, 4, 0)]


class R3ExactnessTests(unittest.TestCase):
    def test_r3_matches_brute_force_on_more_small_metric_problems(self):
        """Spec: R3 is the exact method ('best plan in the model', the oracle)."""
        for seed, n_stops, n_extra in NOT_EXACT:
            p = random_problem(seed, n_stops, n_extra)
            self.assertAlmostEqual(solve_r3(p).arrival_s, brute_force(p), places=6,
                                   msg=(seed, n_stops, n_extra))

    def test_search_value_is_a_lower_bound_and_repair_reaches_the_optimum(self):
        """The search allows revisits, so its value is only a lower bound: here the optimum
        (brute force) is later than it, and R3 must still return the optimum."""
        p = random_problem(125, 3, 2)
        state = r3_start(p)
        r3_advance(p, state)
        ctx = _context(p, state)
        full = (1 << state.n_bits) - 1
        search_value = float((state.value[full] + ctx.campus).min())
        self.assertIsNotNone(state.repair)                 # the merged plan was not certified
        optimum = brute_force(random_problem(125, 3, 2))
        self.assertLess(search_value, optimum - 1.0)
        self.assertAlmostEqual(solve_r3(p).arrival_s, optimum, places=6)

    def test_ladder_final_plan_is_the_exact_optimum(self):
        p = random_problem(133, 3, 1)
        self.assertAlmostEqual(Ladder(p).run().arrival_s,
                               brute_force(random_problem(133, 3, 1)), places=6)


class NanTravelTimeTests(unittest.TestCase):
    def test_nan_in_a_row_is_rejected(self):
        m = [row[:] for row in TINY]
        m[1][3] = math.nan                                    # point 2 -> campus
        p = tiny_problem(matrix=m)
        with self.assertRaisesRegex(ValueError, "1"):
            p.row(1)

    def test_nan_start_entry_does_not_silently_make_a_stop_unserved(self):
        m = [row[:] for row in TINY]
        m[2][0] = math.nan                                    # start -> point 1
        p = tiny_problem(matrix=m)
        with self.assertRaises(ValueError):
            Ladder(p).run()


class WireReviewTests(unittest.TestCase):
    def test_schema_true_is_rejected(self):
        req = {"schema": True, "now": "2026-12-01T07:05:00+05:00",
               "position": {"lat": 24.91, "lng": 67.08},
               "remaining": [{"stop_id": 1, "students": 4}, {"stop_id": 2, "students": 2}],
               "candidates": [], "closures": [], "campus": {"lat": 24.85, "lng": 67.26}}
        with self.assertRaisesRegex(RequestError, "schema"):
            parse_request(req, table_rows(TINY), {(2, 1): 240.0})


def _blocked(point_index):
    """TINY with one point unreachable from everywhere and to everywhere."""
    m = [row[:] for row in TINY]
    for i in range(4):
        if i != point_index:
            m[i][point_index] = math.inf
            m[point_index][i] = math.inf
    return m


class UnreachableCommittedPointTests(unittest.TestCase):
    """Second review round. A committed point that is unreachable, with no servable stop, leaves
    R3 with bits but no useful point (K = 0); the search then reduces an empty numpy row."""

    def problem(self):
        return tiny_problem(stops=[], committed=[2], matrix=_blocked(1))

    def test_solve_r3_does_not_crash_with_no_useful_point(self):
        plan = solve_r3(self.problem())
        self.assertEqual(plan.arrival_s, math.inf)

    def test_ladder_run_does_not_crash_with_no_useful_point(self):
        plan = Ladder(self.problem()).run()
        self.assertEqual(plan.arrival_s, math.inf)


class WireCommittedTypeTests(unittest.TestCase):
    """Second review round. ``committed`` must be a list of stop ids; a falsy non-list value
    (``{}``, ``0``, ``""``, ``False``) is swallowed by ``request.get("committed") or []``."""

    def test_non_list_committed_is_rejected(self):
        for bad in ({}, 0, "", False):
            req = {"schema": 1, "now": "2026-12-01T07:05:00+05:00",
                   "position": {"lat": 24.91, "lng": 67.08},
                   "remaining": [{"stop_id": 1, "students": 4}, {"stop_id": 2, "students": 2}],
                   "candidates": [], "closures": [], "campus": {"lat": 24.85, "lng": 67.26},
                   "committed": bad}
            with self.subTest(committed=bad):
                with self.assertRaisesRegex(RequestError, "committed"):
                    parse_request(req, table_rows(TINY), {(2, 1): 240.0})

    def test_missing_or_null_committed_means_none(self):
        """The fix must keep the documented default: no key, or null, is no commitments."""
        base = {"schema": 1, "now": "2026-12-01T07:05:00+05:00",
                "position": {"lat": 24.91, "lng": 67.08},
                "remaining": [{"stop_id": 1, "students": 4}, {"stop_id": 2, "students": 2}],
                "candidates": [], "closures": [], "campus": {"lat": 24.85, "lng": 67.26}}
        for req in (base, {**base, "committed": None}):
            with self.subTest(committed=req.get("committed", "<missing>")):
                problem = parse_request(req, table_rows(TINY), {(2, 1): 240.0})
                self.assertEqual(list(problem.committed), [])


class LadderRunsR2OnceTests(unittest.TestCase):
    """Second review round: when the repair starts inside the ladder, its bound comes from the
    ladder's best plan, so R2 is not run a second time."""

    def test_repair_inside_the_ladder_does_not_rerun_r2(self):
        from unittest import mock
        from reroute import ladder as ladder_module
        p = random_problem(125, 3, 2)                # the search misses here: the repair runs
        real = ladder_module.solve_r2
        with mock.patch.object(ladder_module, "solve_r2", side_effect=real) as spy:
            plan = Ladder(p).run()
        self.assertEqual(spy.call_count, 1)
        self.assertAlmostEqual(plan.arrival_s, brute_force(p), places=6)


class ZeroWalkLimitOrderTests(unittest.TestCase):
    """Spec C2: no closure and a zero walking limit return the published order, not just the
    same set of stops. On TINY the published order 1, 2 (800 s) beats 2, 1 (1090 s)."""

    def test_every_rung_keeps_the_published_order(self):
        p = tiny_problem(stops=[StopNeed(1, 4, walk_limit_m=0), StopNeed(2, 2, walk_limit_m=0)])
        for name, plan in (("r2", solve_r2(p)), ("r3", solve_r3(p)), ("ladder", Ladder(p).run())):
            with self.subTest(rung=name):
                self.assertEqual(list(plan.visit), [1, 2])


if __name__ == "__main__":
    unittest.main()
