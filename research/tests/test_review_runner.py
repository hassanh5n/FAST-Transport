"""Reviewer tests for the experiment runner (``run_reroute.py``, ``reroute_cases.py``).

Each test demonstrates a defect found in review against plans/2026-11-16-experiment-runner.md,
plans/2026-11-15-rerouting-plan.md (version 2, Sections 5 and 8.3 to 8.4) and the logbook rules of
2026-11-16. They fail on the code as reviewed.
"""
import json
import tempfile
import unittest
from pathlib import Path

import run_reroute
from reroute_cases import build_problem
from run_reroute import quality_verdict
from tests.test_reroute_cases import TOY_CLOSURE, TOY_SCENARIO, WALK

INF = float("inf")

# Every remaining stop unreachable on truth, campus reachable: no stop can be served.
ALL_UNSERVABLE = dict(TOY_CLOSURE, post=[[0, INF, INF, 650], [INF, 0, INF, 590], [INF, INF, 0, 700],
                                         [INF, INF, INF, 0]])
# Campus unreachable on truth.
NO_CAMPUS = dict(TOY_CLOSURE, post=[[0, 100, 300, INF], [100, 0, 400, INF], [300, 400, 0, INF],
                                    [INF, INF, INF, 0]])


class _FakeTT:
    widened, searches, hits, reused = False, 0, 0, 0


class _GraphSaysStop2IsClosed:
    """A graph source whose times close stop 2 although truth (TOY_CLOSURE post) reaches it."""

    area = "city"

    def problem(self, scenario, closure, walk, limit_m):
        from reroute_cases import sub_table
        graph_table = sub_table(closure, "post", scenario)       # nodes: stop 1, stop 2, position, campus
        graph_table = [[INF if (a == 1) != (b == 1) else t for b, t in enumerate(row)]
                       for a, row in enumerate(graph_table)]
        rows = run_reroute_table_rows(graph_table)
        return build_problem(scenario, closure, walk, limit_m, rows=rows), _FakeTT()


def run_reroute_table_rows(matrix):
    from reroute import table_rows
    return table_rows(matrix)


class NoViolationsTests(unittest.TestCase):
    def test_a_crashed_scenario_is_a_violation(self):
        """Plan Task 2: no_violations fails when any row has a status other than ok. Failed rows from
        _quality_job carry no 'judged' key (and any non-ok main row gets judged False), so they never
        reach the check and the verdict reads 'pass'."""
        good = run_reroute.quality_rows(TOY_SCENARIO, TOY_CLOSURE, WALK)
        broken_closure = dict(TOY_CLOSURE, id="T-bad", points=[0, 1])      # stop 2 missing: build_problem raises
        broken = run_reroute._quality_job(dict(TOY_SCENARIO, id="T-bad-late", closure="T-bad"),
                                          broken_closure, WALK)
        self.assertTrue(all(r["status"] == "failed" for r in broken))
        self.assertNotEqual(quality_verdict(good + broken)["no_violations"], "pass")


class LimitsScoringTests(unittest.TestCase):
    def test_graph_plan_that_abandons_a_truly_servable_stop_is_not_ok(self):
        """Work plan Section 5: a stop left unserved counts as a failure; logbook rule 3: no stop is
        unserved where a boarding point exists. A plan made on the graph that drops stop 2 (the graph
        wrongly closes it) is scored 'ok' on truth with a negative gap to the oracle, so it helps the
        at_30 verdict instead of failing it."""
        no_walk = {}
        row = run_reroute.solve_case(TOY_SCENARIO, TOY_CLOSURE, no_walk, "graph_limited",
                                     _GraphSaysStop2IsClosed(), 30.0)
        row = run_reroute.fill_gaps(row, run_reroute.oracle_info(TOY_SCENARIO, TOY_CLOSURE, no_walk))
        self.assertNotEqual(row["status"], "ok")
        self.assertIsNone(row["final_gap_s"])             # no "better than the oracle" gap for abandoning students
        self.assertIsNone(row["gap_30s"])

    def test_every_stop_unservable_is_infeasible_in_the_limits_pass(self):
        """Review Focus 1: a scenario whose every stop is unservable is written as 'infeasible' (as the
        quality pass does). The limits pass writes it 'ok' with a delay of -300 s (serving nobody)."""
        row = run_reroute.solve_case(TOY_SCENARIO, ALL_UNSERVABLE, WALK, "truth_limited", None, 30.0)
        self.assertEqual(row["status"], "infeasible")

    def test_campus_unreachable_is_infeasible_in_the_limits_pass(self):
        """Review Focus 1: campus unreachable gives 'infeasible'; the limits pass writes 'no_plan'."""
        row = run_reroute.solve_case(TOY_SCENARIO, NO_CAMPUS, WALK, "truth_limited", None, 30.0)
        self.assertEqual(row["status"], "infeasible")


class CompleteTests(unittest.TestCase):
    def test_finished_run_with_an_infeasible_scenario_is_complete(self):
        """Review Focus 1: an infeasible row is a result that is counted, not a failure. build_summary
        counts it in runs_failed and so verdict.complete stays False forever: the hub shows every
        verdict as 'so far' on a finished run."""
        rows = (run_reroute.quality_rows(TOY_SCENARIO, TOY_CLOSURE, WALK)
                + run_reroute.quality_rows(dict(TOY_SCENARIO, id="T-L9-late"), dict(ALL_UNSERVABLE, id="T-L9"), WALK))
        self.assertIn("infeasible", {r["status"] for r in rows})
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for r in rows:
                r["started_at"] = "2026-11-17T00:00:00+00:00"
            (d / "meta.json").write_text(json.dumps({"pass": "quality", "runs_total": len(rows)}), encoding="utf-8")
            run_reroute.append_rows(d, rows)
            s = run_reroute.build_summary(d)
        self.assertEqual(s["runs_done"], s["runs_total"])
        self.assertTrue(s["verdict"]["complete"])


if __name__ == "__main__":
    unittest.main()
