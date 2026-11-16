"""Tests for optimize.py: the two ways of handing travel times to OR-Tools ("callback" and "matrix").

The plan's tests (optimizer-scaling, Task 1 Step 2 and Task 3 Step 1) come first; the rest cover the
plan's Review Focus: travel times that are not whole numbers, more buses than stops, and a stop no
bus can reach within 90 minutes.
"""
import unittest

from optimize import peak_memory_mb, score, solve, transit_tables

# campus is node 0; four stops; times in seconds, deliberately not symmetric and with decimals
T = [[0, 900.4, 800.2, 700.9, 600.1],
     [900.4, 0, 120.7, 400.3, 500.5],
     [800.2, 130.2, 0, 150.8, 450.6],
     [700.9, 410.1, 160.4, 0, 140.2],
     [600.1, 520.3, 460.9, 150.6, 0]]
Q = [0, 5, 3, 8, 2]


class LookupTests(unittest.TestCase):
    def both(self, caps, T=T, q=Q, limit=3):
        a, _ = solve(T, q, caps, limit, lookup="callback")
        b, _ = solve(T, q, caps, limit, lookup="matrix")
        return a, b

    def test_same_plan_quality_on_a_small_instance(self):
        a, b = self.both([10, 10])
        self.assertEqual(score(a["routes"], T, Q)["total_student_ride_min"],
                         score(b["routes"], T, Q)["total_student_ride_min"])
        self.assertEqual((a["dropped"], b["dropped"]), ([], []))

    def test_capacity_is_respected_with_the_matrix(self):
        _, b = self.both([8, 8, 8])
        for route in b["routes"]:
            self.assertLessEqual(sum(Q[i] for i in route), 8)

    def test_more_buses_than_stops(self):
        _, b = self.both([20] * 6)
        self.assertEqual(sorted(i for r in b["routes"] for i in r), [1, 2, 3, 4])

    def test_unreachable_stop_is_dropped_under_both(self):
        far = [row[:] for row in T]
        for i in range(5):
            far[4][i] = far[i][4] = 6000.0 if i != 4 else 0          # 100 minutes from everything
        a, b = self.both([10, 10], T=far)
        self.assertEqual((a["dropped"], b["dropped"]), ([4], [4]))

    def test_unknown_lookup_raises(self):
        with self.assertRaises(ValueError):
            solve(T, Q, [10], 1, lookup="other")


class ReviewFocusTests(unittest.TestCase):
    """Extra tests for the plan's Review Focus items."""

    def test_tables_truncate_decimals_like_the_callback(self):
        drive, timed, demand = transit_tables(T, Q)
        dummy = len(T)
        self.assertEqual((len(drive), len(drive[0])), (dummy + 1, dummy + 1))
        self.assertEqual(drive[1][2], 120)                  # int(120.7): truncated, not rounded to 121
        self.assertEqual(drive[2][1], 130)                  # int(130.2)
        self.assertEqual(timed[1][2], 120 + 60 + 5 * 5)     # plus the stop time of the stop being left
        self.assertEqual(timed[0][1], 900)                  # leaving campus adds no stop time
        self.assertEqual(drive[dummy], [0] * (dummy + 1))   # from the dummy start: free
        self.assertEqual(timed[dummy], [0] * (dummy + 1))
        self.assertEqual([row[dummy] for row in drive[:dummy]], [10 ** 7] * dummy)
        self.assertEqual(demand, [0, 5, 3, 8, 2, 0])        # campus and dummy carry no students

    def test_both_lookups_reach_the_same_solver_cost_with_decimal_times(self):
        """Same model under both lookups: the solver's own objective (which includes the truncated
        driving seconds) reaches the same best value. Rounding instead of truncating would shift it.
        progress logs every solution the search accepts, not only improvements, so take the minimum."""
        _, pa = solve(T, Q, [10, 10], 2, lookup="callback")
        _, pb = solve(T, Q, [10, 10], 2, lookup="matrix")
        self.assertEqual(min(c for _, c in pa), min(c for _, c in pb))

    def test_spare_buses_stay_empty_under_both(self):
        a, b = LookupTests.both(self, [20] * 6)
        for result in (a, b):
            self.assertEqual(len(result["routes"]), 6)
            self.assertGreaterEqual(sum(1 for r in result["routes"] if not r), 2)   # at most 4 stops, 6 buses
            self.assertEqual(result["dropped"], [])

    def test_unreachable_stop_with_a_single_bus(self):
        far = [row[:] for row in T]
        for i in range(5):
            if i != 2:
                far[2][i] = far[i][2] = 5500.0                # stop 2 is over 90 min from everything
        a, b = LookupTests.both(self, [30], T=far)
        self.assertEqual((a["dropped"], b["dropped"]), ([2], [2]))
        self.assertEqual(sorted(i for r in b["routes"] for i in r), [1, 3, 4])


class TimingsTests(unittest.TestCase):
    def test_default_return_has_two_values(self):
        out = solve(T, Q, [10, 10], 1)
        self.assertEqual(len(out), 2)

    def test_timings_adds_build_seconds(self):
        for lookup in ("callback", "matrix"):
            result, progress, timings = solve(T, Q, [10, 10], 1, lookup=lookup, timings=True)
            self.assertIsNotNone(result)
            self.assertTrue(progress)
            self.assertGreaterEqual(timings["build_s"], 0.0)
            self.assertLess(timings["build_s"], 5.0)


class PeakMemoryTests(unittest.TestCase):
    def test_peak_memory_is_a_positive_number_or_unknown(self):
        mb = peak_memory_mb()
        if mb is not None:
            self.assertGreater(mb, 0)


if __name__ == "__main__":
    unittest.main()
