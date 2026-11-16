"""Task 2: servable stops and R0, the patched published route."""
import math
import unittest

from reroute.ladder import insert_cheapest, servable, solve_r0
from reroute.model import StopNeed, evaluate
from reroute.tests.helpers import TINY, random_problem, tiny_problem


def blocked(point_index):
    """TINY with one point unreachable from everywhere and to everywhere."""
    m = [row[:] for row in TINY]
    for i in range(4):
        if i != point_index:
            m[i][point_index] = math.inf
            m[point_index][i] = math.inf
    return m


class R0Tests(unittest.TestCase):
    def test_no_closure_returns_published_order(self):
        plan = solve_r0(tiny_problem())
        self.assertEqual((plan.visit, plan.board_at, plan.unserved, plan.arrival_s),
                         ((1, 2), {1: 1, 2: 2}, (), 950.0))

    def test_stop_on_closed_road_walks_to_the_other_stop(self):
        plan = solve_r0(tiny_problem(matrix=blocked(1)))        # point 2 unreachable
        self.assertEqual((plan.visit, plan.board_at, plan.unserved), ((1,), {1: 1, 2: 1}, ()))
        self.assertEqual(plan.arrival_s, 940.0)

    def test_stop_on_closed_road_out_of_range_is_unserved(self):
        p = tiny_problem(matrix=blocked(1), stops=[StopNeed(1, 4), StopNeed(2, 2, walk_limit_m=100)])
        plan = solve_r0(p)
        self.assertEqual((plan.visit, plan.unserved), ((1,), (2,)))

    def test_must_serve_stop_on_closed_road_is_unserved(self):
        p = tiny_problem(matrix=blocked(1), stops=[StopNeed(1, 4), StopNeed(2, 2, must_serve=True)])
        self.assertEqual(solve_r0(p).unserved, (2,))

    def test_no_remaining_stops(self):
        p = tiny_problem(stops=[])
        plan = solve_r0(p)
        self.assertEqual((plan.visit, plan.arrival_s), ((), 650.0))

    def test_campus_unreachable_does_not_raise(self):
        m = [row[:] for row in TINY]
        for i in range(3):
            m[i][3] = math.inf
        self.assertEqual(solve_r0(tiny_problem(matrix=m)).arrival_s, math.inf)

    def test_insert_cheapest_position(self):
        # start->2->1->campus = 300+200+590 = 1090; start->1->2->campus = 100+200+500 = 800
        self.assertEqual(insert_cheapest(tiny_problem(), [1], 2), [1, 2])

    def test_only_needed_rows_are_fetched(self):
        p = tiny_problem()
        solve_r0(p)
        self.assertLessEqual(p.rows_requested, 3)       # start, point 1, point 2

    # Extra checks beyond the plan's list.

    def test_servable_splits_stops(self):
        p = tiny_problem(matrix=blocked(1), stops=[StopNeed(1, 4), StopNeed(2, 2, walk_limit_m=100)])
        stops, unservable = servable(p)
        self.assertEqual(([s.id for s in stops], unservable), ([1], [2]))

    def test_committed_point_is_inserted(self):
        p = tiny_problem(stops=[StopNeed(1, 4)], committed=[2])
        self.assertEqual(solve_r0(p).visit, (1, 2))

    def test_walk_target_off_the_route_is_inserted(self):
        # Point 1 is unreachable; stop 1 walks to point 2, which is not a remaining stop.
        p = tiny_problem(matrix=blocked(0), stops=[StopNeed(1, 4)], walk={(1, 2): 100.0})
        plan = solve_r0(p)
        self.assertEqual((plan.visit, plan.board_at), ((2,), {1: 2}))

    def test_insert_cheapest_ties_go_to_the_earliest_position(self):
        m = [[0, 10, 10, 10, 10], [10, 0, 10, 10, 10], [10, 10, 0, 10, 10],
             [10, 10, 10, 0, 10], [math.inf] * 4 + [0]]
        from reroute.model import Problem, table_rows
        p = Problem([], [1, 2, 3], table_rows(m), {})
        self.assertEqual(insert_cheapest(p, [1, 2], 3), [3, 1, 2])

    def test_unreachable_campus_from_the_end_is_repaired_by_insertion(self):
        # Point 2 cannot reach campus directly but point 1 can: the insertion that fixes the
        # broken last leg wins over any finite saving.
        m = [row[:] for row in TINY]
        m[1][3] = math.inf
        p = tiny_problem(matrix=m)
        self.assertEqual(insert_cheapest(p, [2], 1), [2, 1])

    def test_valid_on_random_problems(self):
        for seed in range(20):
            p = random_problem(seed, 2 + seed % 9, seed % 4)
            plan = solve_r0(p)
            self.assertEqual(evaluate(p, plan.visit, plan.board_at, plan.unserved), plan.key)


if __name__ == "__main__":
    unittest.main()
