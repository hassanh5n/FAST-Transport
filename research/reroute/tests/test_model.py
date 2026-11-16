"""Task 1: the problem model and the scoring function."""
import math
import unittest

from reroute.model import (InvalidPlan, Plan, Problem, StopNeed, evaluate, make_plan,
                           table_rows)
from reroute.tests.helpers import TINY, tiny_problem


class EvaluateTests(unittest.TestCase):
    def test_visit_both_stops(self):
        self.assertEqual(evaluate(tiny_problem(), [1, 2], {1: 1, 2: 2}), (950.0, 0.0))

    def test_bus_waits_for_walkers(self):
        self.assertEqual(evaluate(tiny_problem(), [1], {1: 1, 2: 1}), (940.0, 480.0))

    def test_order_matters(self):
        self.assertEqual(evaluate(tiny_problem(), [2, 1], {1: 1, 2: 2})[0], 1240.0)

    def test_no_wait_when_bus_is_later_than_walkers(self):
        p = tiny_problem(walk={(2, 1): 30.0})          # ready at 60 + 25 = 85, bus arrives 100
        self.assertEqual(evaluate(p, [1], {1: 1, 2: 1}), (100 + 60 + 30 + 590.0, 60.0))

    def test_zero_student_stop_costs_no_boarding_time_or_walking(self):
        p = tiny_problem(stops=[StopNeed(1, 4), StopNeed(2, 0)])
        self.assertEqual(evaluate(p, [1], {1: 1, 2: 1}), (260 + 60 + 20 + 590.0, 0.0))

    def test_walk_beyond_limit_is_invalid(self):
        p = tiny_problem(stops=[StopNeed(1, 4), StopNeed(2, 2, walk_limit_m=200)])
        with self.assertRaises(InvalidPlan):
            evaluate(p, [1], {1: 1, 2: 1})

    def test_must_serve_cannot_walk(self):
        p = tiny_problem(stops=[StopNeed(1, 4), StopNeed(2, 2, must_serve=True)])
        with self.assertRaises(InvalidPlan):
            evaluate(p, [1], {1: 1, 2: 1})

    def test_missing_stop_is_invalid_unless_listed_unserved(self):
        with self.assertRaises(InvalidPlan):
            evaluate(tiny_problem(), [1], {1: 1})
        self.assertEqual(evaluate(tiny_problem(), [1], {1: 1}, unserved=[2])[0], 100 + 60 + 20 + 590.0)

    def test_committed_point_must_be_visited(self):
        with self.assertRaises(InvalidPlan):
            evaluate(tiny_problem(committed=[2]), [1], {1: 1, 2: 1})

    def test_repeated_point_is_invalid(self):
        with self.assertRaises(InvalidPlan):
            evaluate(tiny_problem(), [1, 2, 1], {1: 1, 2: 2})

    def test_unreachable_leg_gives_infinite_arrival(self):
        m = [row[:] for row in TINY]; m[2][0] = math.inf
        self.assertEqual(evaluate(tiny_problem(matrix=m), [1, 2], {1: 1, 2: 2})[0], math.inf)

    # Extra checks beyond the plan's list.

    def test_empty_visit_drives_straight_to_campus(self):
        self.assertEqual(evaluate(tiny_problem(stops=[]), [], {}), (650.0, 0.0))

    def test_stop_both_boarded_and_unserved_is_invalid(self):
        with self.assertRaises(InvalidPlan):
            evaluate(tiny_problem(), [1], {1: 1, 2: 1}, unserved=[2])

    def test_unknown_ids_are_invalid(self):
        with self.assertRaises(InvalidPlan):
            evaluate(tiny_problem(), [1, 5], {1: 1, 2: 1})
        with self.assertRaises(InvalidPlan):
            evaluate(tiny_problem(), [1], {1: 1, 2: 1, 8: 1})
        with self.assertRaises(InvalidPlan):
            evaluate(tiny_problem(), [1], {1: 1, 2: 1}, unserved=[8])


class ProblemTests(unittest.TestCase):
    def test_rows_are_fetched_once_and_counted(self):
        p = tiny_problem()
        p.row(p.start); p.row(p.start); p.fetch([p.start, 0])
        self.assertEqual(p.rows_requested, 2)

    def test_duplicate_point_id_raises_naming_the_id(self):
        with self.assertRaisesRegex(ValueError, "7"):
            Problem([StopNeed(7, 1)], [7, 7], table_rows(TINY), {})

    def test_stop_missing_from_points_raises_naming_the_id(self):
        with self.assertRaisesRegex(ValueError, "9"):
            Problem([StopNeed(9, 1)], [1, 2], table_rows(TINY), {})

    def test_make_plan_key(self):
        plan = make_plan(tiny_problem(), "R0", [1, 2], {1: 1, 2: 2})
        self.assertEqual((plan.method, plan.key), ("R0", (950.0, 0.0)))

    # Extra checks beyond the plan's list.

    def test_duplicate_stop_id_raises_naming_the_id(self):
        with self.assertRaisesRegex(ValueError, "1"):
            Problem([StopNeed(1, 1), StopNeed(1, 2)], [1, 2], table_rows(TINY), {})

    def test_committed_id_not_a_point_raises(self):
        with self.assertRaisesRegex(ValueError, "42"):
            Problem([StopNeed(1, 1)], [1, 2], table_rows(TINY), {}, committed=[42])

    def test_bad_students_or_walk_limit_raise(self):
        with self.assertRaisesRegex(ValueError, "students"):
            Problem([StopNeed(1, -1)], [1, 2], table_rows(TINY), {})
        with self.assertRaisesRegex(ValueError, "walk_limit_m"):
            Problem([StopNeed(1, 1, walk_limit_m=801)], [1, 2], table_rows(TINY), {})

    def test_nan_or_negative_travel_time_raises_naming_the_node(self):
        for bad in (math.nan, -1.0):
            m = [row[:] for row in TINY]
            m[1][3] = bad
            with self.assertRaisesRegex(ValueError, "node 1"):
                tiny_problem(matrix=m).row(1)

    def test_nan_or_negative_walk_raises(self):
        for bad in (math.nan, -5.0):
            with self.assertRaisesRegex(ValueError, "walk"):
                tiny_problem(walk={(2, 1): bad})

    def test_short_row_raises(self):
        p = Problem([StopNeed(1, 1)], [1, 2], lambda nodes: {n: [0.0] for n in nodes}, {})
        with self.assertRaisesRegex(ValueError, "4"):
            p.row(p.start)

    def test_walk_and_boarding_rules(self):
        p = tiny_problem()
        s1, s2 = p.stops
        self.assertEqual((p.walk_m(1, 1), p.walk_m(2, 1), p.walk_m(1, 2)), (0.0, 240.0, None))
        self.assertEqual((p.can_board(s2, 1), p.can_board(s1, 2)), (True, False))
        self.assertEqual((p.ready_s(1, 1), p.ready_s(2, 1)), (0.0, 260.0))
        self.assertEqual((p.start, p.campus, p.index), (2, 3, {1: 0, 2: 1}))

    def test_plan_json_round_trip_keeps_infinite_arrival(self):
        plan = Plan("R0", (1,), {1: 1, 2: 1}, (), math.inf, 480.0, {2: 240.0})
        self.assertEqual(Plan.from_json(plan.to_json()), plan)
        self.assertIsNone(plan.to_json()["arrival_s"])


if __name__ == "__main__":
    unittest.main()
