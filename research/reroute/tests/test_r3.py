"""Task 4: R3, the exact method, and the lower bound."""
import json
import math
import unittest

from reroute.ladder import (MAX_EXACT_BITS, R3State, lower_bound, r3_advance, r3_plan, r3_start,
                            solve_r0, solve_r2, solve_r3)
from reroute.model import Problem, StopNeed, evaluate, table_rows
from reroute.tests.helpers import TINY, brute_force, random_problem, tiny_problem


class R3Tests(unittest.TestCase):
    def test_tiny_problem(self):
        plan = solve_r3(tiny_problem())
        self.assertEqual((plan.method, plan.visit, plan.arrival_s), ("R3", (1,), 940.0))

    def test_matches_brute_force_on_small_problems(self):
        for seed in range(24):
            p = random_problem(seed, n_stops=1 + seed % 4, n_extra=seed % 3)
            self.assertAlmostEqual(solve_r3(p).arrival_s, brute_force(p), places=6, msg=seed)

    def test_matches_brute_force_with_must_serve_and_committed(self):
        for seed in range(12):
            base = random_problem(seed, n_stops=4, n_extra=2)
            stops = [StopNeed(s.id, s.students, s.walk_limit_m, must_serve=(s.id == 1)) for s in base.stops]
            p = type(base)(stops, base.points, base._rows, base._walk, committed=[5])   # point 5 is an extra point
            plan = solve_r3(p)
            self.assertAlmostEqual(plan.arrival_s, brute_force(p), places=6, msg=seed)
            self.assertIn(1, plan.visit); self.assertIn(5, plan.visit)

    def test_never_later_than_r2_and_always_valid(self):
        for seed in range(30):
            p = random_problem(seed, n_stops=3 + seed % 9, n_extra=seed % 5)
            r2, r3 = solve_r2(p), solve_r3(p)
            self.assertLessEqual(r3.arrival_s, r2.arrival_s + 1e-9, seed)
            self.assertEqual(evaluate(p, r3.visit, r3.board_at, r3.unserved), r3.key, seed)

    def test_no_point_is_visited_twice(self):
        for seed in range(30):
            visit = solve_r3(random_problem(seed, 6, 3)).visit
            self.assertEqual(len(visit), len(set(visit)), seed)

    def test_non_metric_table_still_gives_a_valid_plan_no_later_than_r2(self):
        for seed in range(10):
            p = random_problem(seed, 5, 2)
            rows = {n: [t * (1.7 if (n + i + seed) % 3 == 0 else 1.0) for i, t in enumerate(p.row(n))]
                    for n in range(len(p.points) + 2)}
            q = type(p)(p.stops, p.points, lambda nodes: {n: rows[n] for n in nodes}, p._walk)
            r3 = solve_r3(q)
            self.assertLessEqual(r3.arrival_s, solve_r2(q).arrival_s + 1e-9, seed)
            evaluate(q, r3.visit, r3.board_at, r3.unserved)

    def test_too_many_stops_raises(self):
        with self.assertRaisesRegex(ValueError, "too many stops"):
            r3_start(random_problem(0, MAX_EXACT_BITS + 1, 0))

    def test_sliced_and_resumed_equals_uninterrupted(self):
        p = random_problem(5, 9, 3)
        whole = solve_r3(p)
        state = r3_start(p)
        while not state.done:
            state = r3_advance(p, state, max_masks=37)
            state = R3State.from_json(json.loads(json.dumps(state.to_json())))
        part = r3_plan(p, state)
        self.assertEqual((part.visit, part.board_at, part.arrival_s), (whole.visit, whole.board_at, whole.arrival_s))

    def test_lower_bound_is_below_the_exact_answer(self):
        for seed in range(20):
            p = random_problem(seed, 6, 2)
            self.assertLessEqual(lower_bound(p), solve_r3(p).arrival_s + 1e-9, seed)

    def test_no_remaining_stops(self):
        self.assertEqual(solve_r3(tiny_problem(stops=[])).arrival_s, 650.0)

    # Extra checks: Review Focus items 2, 3 and 4, slicing by deadline, and state contents.

    def test_campus_unreachable_does_not_raise(self):
        m = [row[:] for row in TINY]
        for i in range(3):
            m[i][3] = math.inf
        self.assertEqual(solve_r3(tiny_problem(matrix=m)).arrival_s, math.inf)

    def test_non_metric_table_is_never_later_than_r0(self):
        for seed in range(10):
            p = random_problem(seed, 6, 3)
            rows = {n: [t * (0.4 if (n * 7 + i + seed) % 5 == 0 else 1.0) for i, t in enumerate(p.row(n))]
                    for n in range(len(p.points) + 2)}
            q = type(p)(p.stops, p.points, lambda nodes: {n: rows[n] for n in nodes}, p._walk)
            r3 = solve_r3(q)
            self.assertLessEqual(r3.arrival_s, solve_r0(q).arrival_s + 1e-9, seed)
            self.assertEqual(evaluate(q, r3.visit, r3.board_at, r3.unserved), r3.key, seed)

    def test_guard_returns_r2_when_the_merged_plan_is_later(self):
        # Non-metric: start->A->B is far quicker than start->B. The search's best path is
        # A{1} B{2} A{3} -> campus (635 s); merging the repeat of A gives [B, A] (2155 s), which R2's
        # [A, B] (1305 s) beats, so R3 must return R2's plan.
        inf = math.inf
        matrix = [[0, 10, inf, inf, 10],        # from A (point 1)
                  [10, 0, inf, inf, 600],       # from B (point 2)
                  [inf, inf, 0, inf, inf],      # from C (point 3), cut off by the closure
                  [10, 2000, inf, 0, 1000],     # from start
                  [inf, inf, inf, inf, 0]]      # from campus
        p = Problem([StopNeed(1, 1), StopNeed(2, 1), StopNeed(3, 1, walk_limit_m=800)], [1, 2, 3],
                    table_rows(matrix), {(3, 1): 600.0})
        state = r3_advance(p, r3_start(p))
        full = (1 << state.n_bits) - 1
        self.assertAlmostEqual(min(state.value[full] + [10, 600]), 635.0)
        plan = r3_plan(p, state)
        r2 = solve_r2(p)
        self.assertEqual((plan.method, plan.visit, plan.arrival_s), ("R3", r2.visit, r2.arrival_s))
        self.assertEqual((plan.visit, plan.arrival_s), ((1, 2), 1305.0))
        self.assertEqual(evaluate(p, plan.visit, plan.board_at, plan.unserved), plan.key)

    def test_zero_student_stop_is_boarded(self):
        p = tiny_problem(stops=[StopNeed(1, 4), StopNeed(2, 0)])
        plan = solve_r3(p)
        self.assertEqual((set(plan.board_at), plan.unserved), ({1, 2}, ()))
        self.assertAlmostEqual(plan.arrival_s, brute_force(p))

    def test_unservable_stop_is_reported(self):
        m = [row[:] for row in TINY]
        for i in range(4):
            if i != 1:
                m[i][1] = m[1][i] = math.inf
        p = tiny_problem(matrix=m, stops=[StopNeed(1, 4), StopNeed(2, 2, walk_limit_m=100)])
        self.assertEqual(solve_r3(p).unserved, (2,))

    def test_expired_deadline_processes_nothing(self):
        import time
        p = random_problem(2, 5, 1)
        state = r3_advance(p, r3_start(p), deadline=time.perf_counter() - 1)
        self.assertEqual((state.next_mask, state.done), (0, False))

    def test_plan_requires_a_finished_state(self):
        p = random_problem(2, 5, 1)
        with self.assertRaises(ValueError):
            r3_plan(p, r3_start(p))

    def test_state_from_another_problem_is_rejected(self):
        state = r3_start(random_problem(2, 5, 1))
        with self.assertRaises(ValueError):
            r3_advance(random_problem(2, 6, 1), R3State.from_json(state.to_json()))

    def test_rows_fetched_with_one_call(self):
        calls = []
        base = random_problem(3, 6, 2)

        def rows(nodes):
            calls.append(list(nodes))
            return base._rows(nodes)
        p = Problem(base.stops, base.points, rows, base._walk)
        r3_start(p)
        self.assertEqual(len(calls), 2)          # the start row (reachability), then all others

    def test_lower_bound_without_servable_stops_is_the_direct_time(self):
        self.assertEqual(lower_bound(tiny_problem(stops=[])), 650.0)

    def test_matches_brute_force_with_stop_walking_to_an_extra_point(self):
        inf = math.inf
        matrix = [[0, 50, inf, 400],      # from point 1
                  [50, 0, inf, 100],      # from point 2
                  [300, 20, 0, 500],      # from start
                  [inf, inf, inf, 0]]     # from campus
        p = Problem([StopNeed(1, 3)], [1, 2], table_rows(matrix), {(1, 2): 50.0})
        plan = solve_r3(p)
        # Walkers ready at 60 + 50 / 1.2; bus waits at point 2, boards 3 students, then 100 s.
        self.assertEqual((plan.visit, plan.board_at), ((2,), {1: 2}))
        self.assertAlmostEqual(plan.arrival_s, 60 + 50 / 1.2 + 60 + 15 + 100)
        self.assertAlmostEqual(plan.arrival_s, brute_force(p))



class RepairTests(unittest.TestCase):
    """The search allows revisits and is only a lower bound; the repair phase makes R3 exact."""

    # (seed, n_stops, n_extra, walk limit) where the search's best path revisits a point and
    # merging the repeat loses time, so the repair runs.
    REPAIRED = [(125, 3, 2, 400.0), (133, 3, 1, 400.0), (138, 4, 0, 400.0)]

    def test_matches_brute_force_on_a_wider_scan(self):
        for limit in (400.0, 800.0):
            for seed in range(120, 200):
                n_stops, n_extra = 2 + seed % 4, seed % 3
                p = random_problem(seed, n_stops, n_extra, limit)
                self.assertAlmostEqual(solve_r3(p).arrival_s,
                                       brute_force(random_problem(seed, n_stops, n_extra, limit)),
                                       places=6, msg=(seed, limit))

    def test_repair_runs_and_reaches_the_optimum(self):
        for seed, n_stops, n_extra, limit in self.REPAIRED:
            p = random_problem(seed, n_stops, n_extra, limit)
            state = r3_advance(p, r3_start(p))
            self.assertIsNotNone(state.repair, seed)
            plan = r3_plan(p, state)
            self.assertEqual(plan.method, "R3")
            self.assertEqual(len(plan.visit), len(set(plan.visit)), seed)
            self.assertEqual(evaluate(p, plan.visit, plan.board_at, plan.unserved), plan.key)
            self.assertAlmostEqual(plan.arrival_s, brute_force(p), places=6, msg=seed)

    def test_certified_search_skips_the_repair(self):
        p = tiny_problem(stops=[StopNeed(1, 4)])               # one stop: no revisit possible
        self.assertIsNone(r3_advance(p, r3_start(p)).repair)

    def test_tiny_problem_needs_the_repair(self):
        # The search boards stop 1 at point 1 (leave 180 s), then "revisits" point 1 at no driving
        # cost and boards stop 2's walkers when ready at 260 s: 920 s. Merged into one visit, the
        # 20 s of boarding lands after the wait: 940 s, which is the true optimum.
        p = tiny_problem()
        state = r3_advance(p, r3_start(p))
        self.assertIsNotNone(state.repair)
        self.assertEqual(r3_plan(p, state).arrival_s, 940.0)

    def test_repair_sliced_and_resumed_equals_uninterrupted(self):
        p = random_problem(39, 8, 4, 800.0)
        whole = solve_r3(p)
        state, saw_repair = r3_start(p), False
        while not state.done:
            state = r3_advance(p, state, max_masks=97)
            saw_repair |= state.repair is not None
            state = R3State.from_json(json.loads(json.dumps(state.to_json())))
        self.assertTrue(saw_repair)
        part = r3_plan(p, state)
        self.assertEqual((part.visit, part.board_at, part.arrival_s),
                         (whole.visit, whole.board_at, whole.arrival_s))

    def test_repair_honours_an_expired_deadline(self):
        import time
        p = random_problem(125, 3, 2)
        state = r3_start(p)
        r3_advance(p, state, max_masks=1 << state.n_bits)
        self.assertIsNotNone(state.repair)
        before = state.repair.next_mask
        r3_advance(p, state, deadline=time.perf_counter() - 1)
        self.assertEqual((state.repair.next_mask, state.done), (before, False))

    def test_group_prefix_sums_match_a_direct_sum(self):
        import numpy as np
        from reroute.ladder import _context, _group_prefix_sums
        p = random_problem(4, 7, 3, 800.0)
        state = r3_start(p)
        ctx = _context(p, state)
        for mask in (0, 5, 0b1010101):
            free = (ctx.pair_bit & mask) == 0
            got = _group_prefix_sums(ctx, free)
            for i in range(len(ctx.pair_k)):
                want = (ctx.pair_vals[ctx.pair_first[i]:i + 1]
                        * free[ctx.pair_first[i]:i + 1, None]).sum(axis=0)
                np.testing.assert_allclose(got[i], want, rtol=1e-12, atol=1e-9)


if __name__ == "__main__":
    unittest.main()
