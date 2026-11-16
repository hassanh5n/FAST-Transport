"""Tests for ``reroute_cases``: a scenario turned into a solver problem, and plans scored on true times.

The toy closure and scenario are the hand-checkable ones of the experiment-runner plan (Task 1);
``run_reroute.py make-toy`` writes the same numbers to ``data/scenarios_toy.json``.
"""
import unittest

from reroute import Ladder, solve_r0
from reroute_cases import (baseline_arrival, build_problem, case_points, checkpoints, must_serve_draw,
                           score_on_truth, sub_table)

INF = float("inf")
# points: stops 1 and 2 of one route; campus last. Same numbers as the solver plan's tiny problem.
TOY_CLOSURE = {"id": "T-L1", "kind": "synthetic", "contractor": "T", "route": "T", "leg": 1, "factor": 0.0,
               "circles": [[24.9, 67.0, 200.0]], "points": [0, 1, 2], "closed_points": [],
               "pre":  [[0, 100, 300, 650], [100, 0, 200, 590], [300, 200, 0, 500], [INF, INF, INF, 0]],
               "post": [[0, 100, 300, 650], [100, 0, 400, 590], [300, 400, 0, 700], [INF, INF, INF, 0]]}
TOY_SCENARIO = {"id": "T-L1-late", "closure": "T-L1", "trigger": "late", "position": 0, "remaining": [1, 2],
                "students": {"1": 4, "2": 2}, "candidates": [], "tags": {"remaining": 2, "closure_contains_stop": False}}
WALK = {(2, 1): 240.0}


class CaseTests(unittest.TestCase):
    def test_sub_table_orders_points_then_position_then_campus(self):
        t = sub_table(TOY_CLOSURE, "post", TOY_SCENARIO)
        self.assertEqual(t[2], [100, 300, 0, 650])            # from the bus position
        self.assertEqual(t[0][1], 400)                         # stop 1 to stop 2 after the closure

    def test_baseline_and_patched_route(self):
        self.assertEqual(baseline_arrival(TOY_SCENARIO, TOY_CLOSURE, WALK), 950.0)
        p = build_problem(TOY_SCENARIO, TOY_CLOSURE, WALK, 400)
        self.assertEqual(solve_r0(p).arrival_s, 1350.0)

    def test_best_plan_scored_on_truth(self):
        p = build_problem(TOY_SCENARIO, TOY_CLOSURE, WALK, 400)
        s = score_on_truth(TOY_SCENARIO, TOY_CLOSURE, WALK, 400, Ladder(p).run())
        self.assertEqual((s["status"], s["delay_s"], s["walkers"], s["walk_m_per_walker"]), ("ok", -10.0, 2, 240.0))

    def test_zero_limit_keeps_every_stop(self):
        p = build_problem(TOY_SCENARIO, TOY_CLOSURE, WALK, 0)
        self.assertEqual(Ladder(p).run().arrival_s, 1350.0)

    def test_control_uses_the_unblocked_table(self):
        p = build_problem(TOY_SCENARIO, TOY_CLOSURE, WALK, 400, which="pre")
        self.assertEqual((solve_r0(p).arrival_s, Ladder(p).run().arrival_s), (950.0, 940.0))

    def test_plan_that_truth_makes_unreachable_is_a_counted_failure(self):
        blocked = dict(TOY_CLOSURE, post=[[0, INF, 300, 650], [INF, 0, INF, INF], [300, INF, 0, 700], [INF, INF, INF, 0]])
        plan = Ladder(build_problem(TOY_SCENARIO, TOY_CLOSURE, WALK, 400)).run()      # planned on the old table
        self.assertEqual(score_on_truth(TOY_SCENARIO, blocked, WALK, 400, plan)["status"], "invalid_on_truth")

    def test_must_serve_draw_is_fixed_and_at_least_one(self):
        self.assertEqual(len(must_serve_draw(TOY_SCENARIO)), 1)
        self.assertEqual(must_serve_draw(TOY_SCENARIO), must_serve_draw(TOY_SCENARIO))

    def test_checkpoints(self):
        a, b = object(), object()
        self.assertEqual(checkpoints([(0.4, a), (7.0, b)]), {1: a, 5: a, 30: b})
        self.assertEqual(checkpoints([(2.0, a)])[1], None)


class CaseExtraTests(unittest.TestCase):
    """Edge cases beyond the plan's tests."""

    def test_case_points_are_remaining_then_candidates(self):
        self.assertEqual(case_points(dict(TOY_SCENARIO, candidates=[7, 9])), [1, 2, 7, 9])

    def test_must_serve_draw_is_a_quarter_rounded_up(self):
        eight = dict(TOY_SCENARIO, id="X-early", remaining=list(range(10, 18)))
        drawn = must_serve_draw(eight)
        self.assertEqual(len(drawn), 2)
        self.assertTrue(set(drawn) <= set(eight["remaining"]))
        self.assertEqual(must_serve_draw(dict(TOY_SCENARIO, remaining=[])), [])

    def test_must_serve_stop_is_visited(self):
        p = build_problem(TOY_SCENARIO, TOY_CLOSURE, WALK, 400, must_serve=[2])
        plan = Ladder(p).run()
        self.assertIn(2, plan.visit)
        self.assertEqual(score_on_truth(TOY_SCENARIO, TOY_CLOSURE, WALK, 400, plan, must_serve=[2])["delay_s"], 400.0)

    def test_score_on_the_unblocked_table(self):
        p = build_problem(TOY_SCENARIO, TOY_CLOSURE, WALK, 400, which="pre")
        s = score_on_truth(TOY_SCENARIO, TOY_CLOSURE, WALK, 400, Ladder(p).run(), which="pre")
        self.assertEqual((s["status"], s["arrival_s"], s["delay_s"]), ("ok", 940.0, -10.0))

    def test_nobody_walking_has_no_metres_per_walker(self):
        p = build_problem(TOY_SCENARIO, TOY_CLOSURE, WALK, 0)
        s = score_on_truth(TOY_SCENARIO, TOY_CLOSURE, WALK, 0, solve_r0(p))
        self.assertEqual((s["walkers"], s["walk_m_per_walker"], s["unserved"]), (0, None, 0))

    def test_plan_breaking_a_rule_on_truth_is_invalid(self):
        # planned at 400 m (stop 2 walks 240 m), scored at a 100 m limit: the walk is not allowed
        plan = Ladder(build_problem(TOY_SCENARIO, TOY_CLOSURE, WALK, 400)).run()
        self.assertEqual(score_on_truth(TOY_SCENARIO, TOY_CLOSURE, WALK, 100, plan)["status"], "invalid_on_truth")

    def test_campus_unreachable_scores_invalid(self):
        cut = dict(TOY_CLOSURE, post=[[0, 100, 300, INF], [100, 0, 400, INF], [300, 400, 0, INF], [INF, INF, INF, 0]])
        plan = solve_r0(build_problem(TOY_SCENARIO, cut, WALK, 400))
        self.assertEqual(plan.arrival_s, INF)
        self.assertEqual(score_on_truth(TOY_SCENARIO, cut, WALK, 400, plan)["status"], "invalid_on_truth")

    def test_unserved_stop_is_counted(self):
        closed = dict(TOY_CLOSURE, closed_points=[2],
                      post=[[0, 100, INF, 650], [100, 0, INF, 590], [INF, INF, 0, INF], [INF, INF, INF, 0]])
        plan = solve_r0(build_problem(TOY_SCENARIO, closed, WALK, 0))
        s = score_on_truth(TOY_SCENARIO, closed, WALK, 0, plan)
        self.assertEqual((s["status"], s["unserved"], s["unserved_avoidable"]), ("ok", 1, 0))

    def test_unserved_where_truth_has_a_boarding_point_is_flagged(self):
        from reroute.model import make_plan
        p = build_problem(TOY_SCENARIO, TOY_CLOSURE, WALK, 400)
        lazy = make_plan(p, "R2", [1], {1: 1}, unserved=[2])     # stop 2 could walk to 1 but is dropped
        s = score_on_truth(TOY_SCENARIO, TOY_CLOSURE, WALK, 400, lazy)
        self.assertEqual((s["unserved"], s["unserved_avoidable"]), (1, 1))

    def test_walk_is_cut_to_the_case(self):
        p = build_problem(TOY_SCENARIO, TOY_CLOSURE, {(2, 1): 240.0, (5, 6): 10.0, (2, 9): -1.0}, 400)
        self.assertEqual(p.walk_m(2, 1), 240.0)            # pairs outside the case are dropped, not validated


if __name__ == "__main__":
    unittest.main()
