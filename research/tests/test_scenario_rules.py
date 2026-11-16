"""Tests for `scenario_rules`: closure placement, geometry, candidates, triggers, historical stretches."""
import json
import math
import tempfile
import unittest
from pathlib import Path

from scenario_rules import (apply_closed, candidates, circles_along, closure_legs, haversine_m,
                            load_historical, midpoint, route_students, scenario_id, scenario_tags,
                            stops_with_students, triggers, validate_historical)

RESEARCH = Path(__file__).resolve().parent.parent


class ScenarioRulesTests(unittest.TestCase):
    """The tests written out in the plan, Task 4 Step 1."""

    def test_closure_legs(self):
        self.assertEqual([closure_legs(n) for n in (2, 3, 4, 6, 13)], [[], [1, 2], [2, 3], [2, 4], [5, 9]])

    def test_midpoint_is_by_length(self):
        lat, lng = midpoint([(24.9, 67.0), (24.9, 67.001), (24.9, 67.004)])
        self.assertAlmostEqual(lng, 67.002, places=5)

    def test_circles_along_cover_the_line(self):
        cs = circles_along([(24.9, 67.0), (24.9, 67.003)])          # about 302 m
        self.assertEqual(len(cs), 4)
        self.assertEqual((cs[0][:2], cs[-1][2]), ((24.9, 67.0), 60.0))
        self.assertAlmostEqual(cs[-1][1], 67.003, places=5)

    def test_route_students_counts_only_this_route(self):
        rows = [{"contractor": "Jadoon", "stop": "A", "baseline_route": "R-1"}] * 3 + \
               [{"contractor": "Jadoon", "stop": "A", "baseline_route": "R-2"},
                {"contractor": "Nadeem", "stop": "A", "baseline_route": "R-1"}]
        self.assertEqual(route_students(rows, "Jadoon", "R-1"), {"A": 3})

    def test_candidates(self):
        walk = {(1, 7): 300.0, (2, 9): 900.0, (1, 2): 100.0, (2, 5): 800.0}
        self.assertEqual(candidates([1, 2], walk), [5, 7])

    def test_triggers(self):
        t = triggers([10, 11, 12, 13], leg=2)
        self.assertEqual(t[0], {"trigger": "early", "position": 10, "remaining": [10, 11, 12, 13]})
        self.assertEqual(t[1], {"trigger": "late", "position": 11, "remaining": [12, 13]})

    def test_trigger_on_first_leg(self):
        t = triggers([10, 11, 12], leg=1)
        self.assertEqual(t[1], {"trigger": "late", "position": 10, "remaining": [11, 12]})

    def test_apply_closed(self):
        out = apply_closed([[0, 5, 9], [5, 0, 4], [9, 4, 0]], [False, True, False])
        self.assertEqual(out, [[0, math.inf, 9], [math.inf, 0, math.inf], [9, math.inf, 0]])

    def test_scenario_id(self):
        self.assertEqual(scenario_id("Jadoon", "R-10", 2, "early"), "Jadoon-R-10-L2-early")


class ClosureLegTests(unittest.TestCase):
    def test_three_stop_route_closes_two_different_legs(self):
        # Review focus 2.
        legs = closure_legs(3)
        self.assertEqual(len(set(legs)), 2)
        self.assertTrue(all(1 <= k <= 2 for k in legs))

    def test_legs_are_distinct_and_valid_for_every_route_length(self):
        for n in range(3, 40):
            first, second = closure_legs(n)
            self.assertLess(first, second, n)
            self.assertLessEqual(second, n - 1, n)
            self.assertGreaterEqual(first, 1, n)

    def test_short_routes_have_no_closures(self):
        self.assertEqual([closure_legs(n) for n in (0, 1, 2)], [[], [], []])


class GeometryTests(unittest.TestCase):
    def test_haversine_one_degree_of_latitude(self):
        self.assertAlmostEqual(haversine_m(24.0, 67.0, 25.0, 67.0), 111_195, delta=10)

    def test_midpoint_of_a_single_point_or_a_zero_length_line(self):
        self.assertEqual(midpoint([(24.9, 67.0)]), (24.9, 67.0))
        self.assertEqual(midpoint([(24.9, 67.0), (24.9, 67.0)]), (24.9, 67.0))

    def test_midpoint_needs_a_point(self):
        with self.assertRaises(ValueError):
            midpoint([])

    def test_circles_are_evenly_spaced(self):
        cs = circles_along([(24.9, 67.0), (24.9, 67.001), (24.9, 67.003)], spacing_m=50.0, radius_m=30.0)
        gaps = [haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(cs, cs[1:])]
        self.assertEqual(len(cs), 7)                    # 302 m / 50 m = 6.05 -> 6 gaps
        self.assertTrue(all(abs(g - gaps[0]) < 0.01 for g in gaps))
        self.assertTrue(all(c[2] == 30.0 for c in cs))

    def test_a_short_line_still_gets_both_ends(self):
        cs = circles_along([(24.9, 67.0), (24.9, 67.0002)])          # about 20 m
        self.assertEqual([c[:2] for c in cs], [(24.9, 67.0), (24.9, 67.0002)])


class StudentTests(unittest.TestCase):
    def test_stop_without_students_on_this_route_is_dropped(self):
        # Review focus 4: "B" has students only on another contractor's route.
        rows = [{"contractor": "Jadoon", "stop": "A", "baseline_route": "R-1"},
                {"contractor": "Nadeem", "stop": "B", "baseline_route": "R-1"},
                {"contractor": "Jadoon", "stop": "C", "baseline_route": "R-1"}]
        counts = route_students(rows, "Jadoon", "R-1")
        self.assertEqual(stops_with_students(["A", "B", "C"], counts), ["A", "C"])

    def test_dropped_stop_is_not_a_remaining_stop_or_counted(self):
        kept = stops_with_students(["A", "B", "C", "D"], {"A": 2, "B": 0, "C": 1, "D": 4})
        self.assertEqual(kept, ["A", "C", "D"])
        self.assertEqual(triggers([0, 2, 3], leg=1)[1]["remaining"], [2, 3])


class CandidateTests(unittest.TestCase):
    def test_walk_is_directed_from_the_remaining_stop(self):
        self.assertEqual(candidates([1], {(7, 1): 100.0}), [])

    def test_custom_limit_and_no_remaining(self):
        walk = {(1, 7): 300.0, (1, 8): 450.0}
        self.assertEqual(candidates([1], walk, max_m=400.0), [7])
        self.assertEqual(candidates([], walk), [])

    def test_unreachable_walk_is_never_a_candidate(self):
        self.assertEqual(candidates([1], {(1, 7): math.inf}), [])


class TriggerTests(unittest.TestCase):
    def test_late_trigger_on_the_last_leg_leaves_one_stop(self):
        t = triggers([10, 11, 12], leg=2)
        self.assertEqual(t[1], {"trigger": "late", "position": 11, "remaining": [12]})

    def test_closure_containing_a_stop_keeps_the_scenario_and_marks_the_stop(self):
        # Review focus 3: stop 11 is inside the closure. It stays a remaining stop (its students
        # must be served by walking) and its row and column become unreachable.
        stops = [10, 11, 12]
        t = triggers(stops, leg=1)
        self.assertIn(11, t[0]["remaining"])
        self.assertIn(11, t[1]["remaining"])
        closed = [s == 11 for s in stops] + [False]          # campus last, never closed here
        table = apply_closed([[0, 1, 2, 3], [1, 0, 2, 3], [2, 2, 0, 3], [3, 3, 3, 0]], closed)
        self.assertEqual(table[1], [math.inf, 0, math.inf, math.inf])
        self.assertEqual([row[1] for row in table], [math.inf, 0, math.inf, math.inf])
        self.assertEqual(scenario_tags(t[1]["remaining"], {11}),
                         {"remaining": 2, "closure_contains_stop": True})
        self.assertEqual(scenario_tags([12], {11}), {"remaining": 1, "closure_contains_stop": False})

    def test_bad_leg(self):
        for leg in (0, 3):
            with self.assertRaises(ValueError):
                triggers([10, 11, 12], leg=leg)


class ApplyClosedTests(unittest.TestCase):
    def test_input_is_not_changed(self):
        table = [[0, 5], [5, 0]]
        apply_closed(table, [True, False])
        self.assertEqual(table, [[0, 5], [5, 0]])

    def test_shape_mismatch(self):
        with self.assertRaises(ValueError):
            apply_closed([[0, 5], [5, 0]], [True])


def _stretch(**over):
    entry = {"id": "s1", "name": "Somewhere", "factor": 0.0,
             "from": {"lat": 24.86, "lng": 67.07}, "to": {"lat": 24.87, "lng": 67.09},
             "both_directions": True, "source": "a newspaper"}
    entry.update(over)
    return entry


class HistoricalTests(unittest.TestCase):
    def test_committed_file_has_the_two_stretches(self):
        entries = json.loads((RESEARCH / "data" / "raw" / "historical_closures.json").read_text())
        self.assertEqual([(e["id"], e["factor"]) for e in entries],
                         [("shahrah-e-faisal-2024-02-24", 0.0), ("university-road-ponding", 0.25)])
        validate_historical(entries, require_coordinates=False)

    def test_blank_coordinates_are_refused_with_a_clear_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "h.json"
            path.write_text(json.dumps([_stretch(**{"from": {"lat": None, "lng": None}})]))
            with self.assertRaises(ValueError) as ctx:
                load_historical(path)
        message = str(ctx.exception)
        self.assertIn("s1", message)
        self.assertIn("from.lat", message)
        self.assertIn("OpenStreetMap", message)

    def test_pinned_file_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "h.json"
            path.write_text(json.dumps([_stretch(), _stretch(id="s2", factor=0.25, length_m=1400)]))
            self.assertEqual([e["id"] for e in load_historical(path)], ["s1", "s2"])

    def test_invalid_entries(self):
        bad = [
            [_stretch(), _stretch()],                                   # duplicate id
            [_stretch(factor=1.0)],                                     # factor 1 changes nothing
            [_stretch(factor=-0.1)],
            [_stretch(**{"to": {"lat": 40.0, "lng": 67.0}})],           # not in Karachi
            [{k: v for k, v in _stretch().items() if k != "source"}],   # no source
            {"id": "not a list"},
        ]
        for entries in bad:
            with self.assertRaises(ValueError, msg=entries):
                validate_historical(entries)


if __name__ == "__main__":
    unittest.main()
