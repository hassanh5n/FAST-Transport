"""Task 5: the ladder, with a resumable solve."""
import json
import math
import time
import unittest

from reroute import Ladder, solve_r0, solve_r3
from reroute.ladder import MAX_EXACT_BITS
from reroute.tests.helpers import TINY, random_problem, tiny_problem


class LadderTests(unittest.TestCase):
    def test_first_step_is_r0_and_is_always_valid(self):
        lad = Ladder(tiny_problem())
        plan = lad.step()
        self.assertEqual((plan.method, plan.arrival_s, lad.stage, lad.done), ("R0", 950.0, "R2", False))

    def test_best_never_gets_worse(self):
        for seed in range(15):
            lad, last = Ladder(random_problem(seed, 8, 3)), None
            while not lad.done:
                plan = lad.step(max_masks=50)
                if last is not None:
                    self.assertLessEqual(plan.key, last.key, seed)
                last = plan
            self.assertAlmostEqual(last.arrival_s, solve_r3(random_problem(seed, 8, 3)).arrival_s, places=6)

    def test_run_with_expired_deadline_still_returns_r0(self):
        lad = Ladder(random_problem(1, 10, 4))
        plan = lad.run(deadline=time.perf_counter() - 1)
        self.assertEqual(plan.arrival_s, solve_r0(random_problem(1, 10, 4)).arrival_s)

    def test_saved_and_restored_gives_the_same_final_plan(self):
        p = random_problem(7, 9, 3)
        whole = Ladder(p).run()
        lad = Ladder(p)
        while not lad.done:
            lad.step(max_masks=41)
            lad = Ladder.from_json(p, json.loads(json.dumps(lad.to_json())))
        self.assertEqual((lad.best.visit, lad.best.board_at, lad.best.key), (whole.visit, whole.board_at, whole.key))

    def test_large_problem_skips_r3_and_reports_a_bound(self):
        lad = Ladder(random_problem(2, MAX_EXACT_BITS + 2, 2))
        plan = lad.run()
        self.assertTrue(lad.done)
        self.assertIn(plan.method, ("R0", "R2"))       # R0 stays when R2 does not beat it
        self.assertLessEqual(lad.bound, plan.arrival_s)

    def test_rows_are_requested_lazily(self):
        p = random_problem(4, 8, 6)
        lad = Ladder(p); lad.step()
        self.assertLessEqual(p.rows_requested, 9)        # start plus the 8 remaining stops

    # Extra checks: Review Focus items 1 to 3, and restoring into a fresh Problem object.

    def test_no_remaining_stops(self):
        plan = Ladder(tiny_problem(stops=[])).run()
        self.assertEqual((plan.visit, plan.arrival_s), ((), 650.0))

    def test_campus_unreachable_does_not_raise(self):
        m = [row[:] for row in TINY]
        for i in range(3):
            m[i][3] = math.inf
        lad = Ladder(tiny_problem(matrix=m))
        self.assertEqual(lad.run().arrival_s, math.inf)
        self.assertTrue(lad.done)
        json.dumps(lad.to_json(), allow_nan=False)

    def test_non_metric_table_never_later_than_r0(self):
        for seed in range(8):
            p = random_problem(seed, 7, 2)
            rows = {n: [t * (1.9 if (n + 2 * i + seed) % 4 == 0 else 1.0) for i, t in enumerate(p.row(n))]
                    for n in range(len(p.points) + 2)}
            q = type(p)(p.stops, p.points, lambda nodes: {n: rows[n] for n in nodes}, p._walk)
            self.assertLessEqual(Ladder(q).run().arrival_s, solve_r0(q).arrival_s, seed)

    def test_restore_into_a_fresh_problem_object(self):
        lad = Ladder(random_problem(3, 7, 2))
        for _ in range(3):
            lad.step(max_masks=20)
        saved = json.dumps(lad.to_json(), allow_nan=False)
        fresh = random_problem(3, 7, 2)
        resumed = Ladder.from_json(fresh, json.loads(saved)).run()
        self.assertEqual(resumed.key, Ladder(random_problem(3, 7, 2)).run().key)

    def test_large_problem_bound_survives_save(self):
        lad = Ladder(random_problem(2, MAX_EXACT_BITS + 2, 2))
        lad.run()
        back = Ladder.from_json(lad.problem, json.loads(json.dumps(lad.to_json())))
        self.assertEqual((back.done, back.bound, back.best), (True, lad.bound, lad.best))


if __name__ == "__main__":
    unittest.main()
