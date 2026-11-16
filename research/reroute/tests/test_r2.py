"""Task 3: R2, the greedy method."""
import math
import unittest

from reroute.ladder import solve_r0, solve_r2
from reroute.model import StopNeed, evaluate
from reroute.tests.helpers import TINY, random_problem, tiny_problem


class R2Tests(unittest.TestCase):
    def test_tiny_problem_lets_stop_2_walk(self):
        plan = solve_r2(tiny_problem())
        self.assertEqual((plan.method, plan.visit, plan.arrival_s), ("R2", (1,), 940.0))

    def test_zero_walk_limit_visits_every_stop(self):
        p = tiny_problem(stops=[StopNeed(1, 4, walk_limit_m=0), StopNeed(2, 2, walk_limit_m=0)])
        self.assertEqual(sorted(solve_r2(p).visit), [1, 2])

    def test_must_serve_stop_is_visited(self):
        p = tiny_problem(stops=[StopNeed(1, 4), StopNeed(2, 2, must_serve=True)])
        self.assertIn(2, solve_r2(p).visit)

    def test_committed_point_is_visited(self):
        self.assertIn(2, solve_r2(tiny_problem(committed=[2])).visit)

    def test_never_later_than_r0_and_always_valid(self):
        for seed in range(40):
            p = random_problem(seed, n_stops=2 + seed % 9, n_extra=seed % 4)
            r0, r2 = solve_r0(p), solve_r2(p)
            self.assertLessEqual(r2.arrival_s, r0.arrival_s, seed)
            self.assertEqual(evaluate(p, r2.visit, r2.board_at, r2.unserved), r2.key, seed)

    def test_same_input_gives_same_plan(self):
        a, b = solve_r2(random_problem(3, 8, 3)), solve_r2(random_problem(3, 8, 3))
        self.assertEqual((a.visit, a.board_at), (b.visit, b.board_at))

    # Extra checks: Review Focus items 1, 2 and 4, and a stop only a committed point serves.

    def test_no_remaining_stops(self):
        plan = solve_r2(tiny_problem(stops=[]))
        self.assertEqual((plan.visit, plan.arrival_s), ((), 650.0))

    def test_campus_unreachable_does_not_raise(self):
        m = [row[:] for row in TINY]
        for i in range(3):
            m[i][3] = math.inf
        self.assertEqual(solve_r2(tiny_problem(matrix=m)).arrival_s, math.inf)

    def test_zero_student_stop_still_gets_a_boarding_point(self):
        p = tiny_problem(stops=[StopNeed(1, 4), StopNeed(2, 0)])
        plan = solve_r2(p)
        self.assertEqual(set(plan.board_at), {1, 2})
        self.assertEqual(plan.unserved, ())

    def test_stop_only_a_committed_point_can_serve_is_assigned(self):
        # Stop 2 is must-serve and its point is committed: no unvisited point can take it.
        p = tiny_problem(stops=[StopNeed(1, 4), StopNeed(2, 2, must_serve=True)], committed=[2])
        plan = solve_r2(p)
        self.assertEqual(plan.board_at[2], 2)
        self.assertEqual(evaluate(p, plan.visit, plan.board_at, plan.unserved), plan.key)


if __name__ == "__main__":
    unittest.main()
