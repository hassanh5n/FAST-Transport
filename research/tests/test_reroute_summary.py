"""Tests for ``run_reroute``: verdict rules, summaries, the quality job, the limits worker and parent.

The verdict tests are the experiment-runner plan's (Task 2). The rest cover its Review Focus:
an infeasible scenario, a plan invalid on truth, no judged scenarios, a worker killed for memory,
a route with no corridor file (on the toy road map of the road-graph plan), and which statuses
count as failures (review fixes).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import run_reroute
from run_reroute import limits_verdict, quality_verdict
from tests.test_reroute_cases import TOY_CLOSURE, TOY_SCENARIO, WALK

INF = float("inf")
RESEARCH = Path(__file__).resolve().parents[1]


def q(scenario, arm, gain, r2m=0, route="R1", judged=True, kind="synthetic", limit=400, status="ok", r0=400, r3=0):
    return {"scenario": scenario, "arm": arm, "limit_m": limit, "route": route, "kind": kind, "judged": judged,
            "status": status, "r3_gain_s": gain, "r2_minus_r3_s": r2m, "r0_delay_s": r0, "r3_delay_s": r3}


class QualityVerdictTests(unittest.TestCase):
    def test_gain_is_net_of_the_control(self):
        rows = [q("a", "main", 410), q("a", "control", 10), q("b", "main", 100), q("b", "control", 60)]
        self.assertEqual(quality_verdict(rows)["gain"], "pass")          # median of 400 and 40 is 220
        rows = [q("a", "main", 70), q("a", "control", 60)]
        self.assertEqual(quality_verdict(rows)["gain"], "fail")          # 10 s net

    def test_unjudged_and_historical_rows_are_ignored(self):
        rows = [q("a", "main", 0, judged=False), q("a", "control", 0, judged=False),
                q("h", "main", 0, kind="historical"), q("h", "control", 0, kind="historical")]
        self.assertEqual(quality_verdict(rows)["gain"], None)

    def test_near_oracle_needs_the_share_and_every_route(self):
        ok = [q(f"s{i}", "main", 100, r2m=0) for i in range(9)] + [q("s9", "main", 100, r2m=500)]
        self.assertEqual(quality_verdict(ok)["near_oracle"], "pass")     # 90% within, route median 0
        bad_route = ok + [q("x1", "main", 100, r2m=90, route="R2"), q("x2", "main", 100, r2m=90, route="R2")]
        self.assertEqual(quality_verdict(bad_route)["near_oracle"], "fail")

    def test_violations(self):
        self.assertEqual(quality_verdict([q("a", "main", 1, status="invalid_on_truth")])["no_violations"], "fail")
        self.assertEqual(quality_verdict([q("a", "main", -5, r0=10, r3=15)])["no_violations"], "fail")
        self.assertEqual(quality_verdict([q("a", "main", 5)])["no_violations"], "pass")

    def test_no_judged_scenarios_gives_no_verdict(self):
        rows = [q("a", "main", 0, judged=False), q("a", "control", 0, judged=False)]
        self.assertEqual(quality_verdict(rows), {"gain": None, "near_oracle": None, "no_violations": None})
        self.assertEqual(quality_verdict([]), {"gain": None, "near_oracle": None, "no_violations": None})

    def test_avoidable_unserved_stop_is_a_violation(self):
        self.assertEqual(quality_verdict([dict(q("a", "main", 5), unserved_avoidable=1)])["no_violations"], "fail")

    def test_one_unjudged_route_does_not_change_route_medians(self):
        rows = [q(f"s{i}", "main", 100) for i in range(10)] + [q("x", "main", 100, r2m=900, route="R2", judged=False)]
        self.assertEqual(quality_verdict(rows)["near_oracle"], "pass")


def lim(scenario, rep, first, gap30, mb=100, arm="graph_limited", judged=True, kind="synthetic"):
    return {"scenario": scenario, "repeat": rep, "arm": arm, "judged": judged, "kind": kind, "status": "ok",
            "t_first_s": first, "gap_30s": gap30, "peak_mb": mb, "delay_5s": None if first is None else 0}


class LimitsVerdictTests(unittest.TestCase):
    def test_worst_repeat_decides(self):
        rows = [lim("a", 1, 1, 0), lim("a", 2, 9, 0), lim("a", 3, 1, 0)]
        self.assertEqual(limits_verdict(rows)["first_plan"], "fail")     # one scenario, its worst repeat is 9 s

    def test_pass(self):
        rows = [lim(f"s{i}", r, 2, 10) for i in range(20) for r in (1, 2, 3)]
        self.assertEqual(limits_verdict(rows), {"first_plan": "pass", "at_30": "pass", "memory": "pass"})

    def test_memory_and_other_arms(self):
        self.assertEqual(limits_verdict([lim("a", 1, 2, 10, mb=450)])["memory"], "fail")
        self.assertEqual(limits_verdict([lim("a", 1, 99, 999, arm="truth_limited")])["first_plan"], None)

    def test_no_judged_scenarios_gives_no_verdict(self):
        rows = [lim("a", 1, 2, 10, judged=False), lim("h", 1, 2, 10, kind="historical")]
        self.assertEqual(limits_verdict(rows), {"first_plan": None, "at_30": None, "memory": None})

    def test_killed_or_invalid_repeat_fails_its_scenario(self):
        killed = dict(lim("a", 2, None, None, mb=None), status="killed_memory")
        v = limits_verdict([lim("a", 1, 1, 0), killed])
        self.assertEqual((v["first_plan"], v["at_30"], v["memory"]), ("fail", "fail", "fail"))
        bad = dict(lim("a", 1, 1, None), status="invalid_on_truth")
        self.assertEqual(limits_verdict([bad])["at_30"], "fail")

    def test_first_plan_must_be_valid_on_truth_at_5_s(self):
        graph_only = dict(lim("a", 1, 1, 0), delay_5s=None)       # found at 1 s, but invalid on truth at 5 s
        self.assertEqual(limits_verdict([graph_only])["first_plan"], "fail")

    def test_memory_is_judged_on_every_graph_limited_row(self):
        rows = [lim("a", 1, 1, 0), lim("h", 1, 1, 0, mb=450, kind="historical"), lim("u", 1, 1, 0, judged=False)]
        self.assertEqual(limits_verdict(rows)["memory"], "fail")
        killed_unjudged = dict(lim("u", 1, None, None, mb=None, judged=False), status="killed_memory")
        self.assertEqual(limits_verdict([lim("a", 1, 1, 0), killed_unjudged])["memory"], "fail")


# --- the quality job ----------------------------------------------------------------------------

def rows_by_key(rows):
    return {r["key"]: r for r in rows}


class QualityRowsTests(unittest.TestCase):
    def test_toy_scenario_rows(self):
        rows = rows_by_key(run_reroute.quality_rows(TOY_SCENARIO, TOY_CLOSURE, WALK))
        self.assertEqual(len(rows), 5)
        main = rows["T-L1-late-L400-main"]
        self.assertEqual((main["status"], main["r0_delay_s"], main["r3_delay_s"], main["r3_gain_s"]),
                         ("ok", 400.0, -10.0, 410.0))
        self.assertEqual(rows["T-L1-late-L400-control"]["r3_gain_s"], 10.0)
        self.assertEqual(rows["T-L1-late-L0-main"]["r3_gain_s"], 0.0)
        self.assertTrue(all(r["judged"] for r in rows.values()))       # copied from the main row at 400 m
        self.assertTrue(main["r3_differs_from_r0"] and main["r3_ran"])

    def test_every_stop_unservable_is_infeasible_not_a_crash(self):
        # the bus sits at point 0; stops 1 and 2 are inside the closure and nobody can walk anywhere
        closed = dict(TOY_CLOSURE, closed_points=[1, 2],
                      post=[[0, INF, INF, 650], [INF, 0, INF, INF], [INF, INF, 0, INF], [INF, INF, INF, 0]])
        rows = run_reroute.quality_rows(TOY_SCENARIO, closed, {})
        main = [r for r in rows if r["arm"] != "control"]
        self.assertTrue(all(r["status"] == "infeasible" for r in main))
        self.assertTrue(all(r["unserved"] == 2 for r in main))
        self.assertFalse(any(r["judged"] for r in rows))

    def test_campus_unreachable_is_infeasible(self):
        cut = dict(TOY_CLOSURE, post=[[0, 100, 300, INF], [100, 0, 400, INF], [300, 400, 0, INF], [INF, INF, INF, 0]])
        rows = rows_by_key(run_reroute.quality_rows(TOY_SCENARIO, cut, WALK))
        self.assertEqual(rows["T-L1-late-L400-main"]["status"], "infeasible")
        self.assertEqual(rows["T-L1-late-L400-control"]["status"], "ok")      # the control uses pre
        json.dumps(list(rows.values()), allow_nan=False)                      # no infinity reaches the file


# --- the limits worker and parent ---------------------------------------------------------------

class LimitsWorkerTests(unittest.TestCase):
    def test_truth_arm_on_the_toy_scenario(self):
        row = run_reroute.solve_case(TOY_SCENARIO, TOY_CLOSURE, WALK, "truth_limited", None, cap_s=30)
        self.assertEqual((row["status"], row["delay_30s"], row["r3_ran"]), ("ok", -10.0, True))
        self.assertIn(row["method_30s"], ("R2", "R3"))      # R3 ties R2 here, so the ladder keeps R2's plan
        self.assertLess(row["t_first_s"], 5)
        self.assertIsNotNone(row["t_done_s"])
        self.assertEqual(row["planned_minus_true_s"], 0.0)

    def test_gaps_are_filled_from_the_oracle(self):
        row = run_reroute.solve_case(TOY_SCENARIO, TOY_CLOSURE, WALK, "truth_limited", None, cap_s=30)
        oracle = run_reroute.oracle_info(TOY_SCENARIO, TOY_CLOSURE, WALK)
        self.assertEqual((oracle["oracle_delay_s"], oracle["judged"]), (-10.0, True))
        filled = run_reroute.fill_gaps(row, oracle)
        self.assertEqual((filled["gap_30s"], filled["final_gap_s"], filled["judged"]), (0.0, 0.0, True))

    def test_killed_worker_marks_its_unfinished_scenarios(self):
        job = {"route": "T-T", "arm": "graph_limited", "repeat": 1, "scenarios": ["a", "b", "c"]}
        done = [{"scenario": "a", "status": "ok"}]
        rows = run_reroute.worker_outcome(job, -9, "", done, limited=True)
        self.assertEqual([r["status"] for r in rows], ["ok", "killed_memory", "killed_memory"])
        rows = run_reroute.worker_outcome(job, 1, "Traceback ... MemoryError", [], limited=True)
        self.assertEqual({r["status"] for r in rows}, {"killed_memory"})
        rows = run_reroute.worker_outcome(job, 1, "Traceback ... KeyError", [], limited=True)
        self.assertEqual({r["status"] for r in rows}, {"failed"})
        rows = run_reroute.worker_outcome(job, -9, "", [], limited=False)
        self.assertEqual({r["status"] for r in rows}, {"failed"})

    def test_route_keys_and_jobs(self):
        cases = {"closures": {"T-L1": TOY_CLOSURE}, "scenarios": [TOY_SCENARIO]}
        jobs = run_reroute.limit_jobs(cases, arms=run_reroute.LIMIT_ARMS, repeats=3)
        self.assertEqual(len(jobs), 7)      # 3 repeats of two limited arms, one unlimited run
        self.assertEqual({j["route"] for j in jobs}, {"T-T"})
        self.assertIn("T-L1-late-graph_limited-r3", {k for j in jobs for k in j["keys"]})


class GraphWorkerTests(unittest.TestCase):
    """The graph arm on the road-graph plan's toy map: no corridor file, so the whole graph."""

    def setUp(self):
        from reroute.graph import Graph, clear_row_cache
        from reroute.roadnet import build_tables
        from reroute.tests.toymap import N, TOY
        clear_row_cache()
        self.graph = Graph(build_tables(TOY, keep_ids=[1, 3, 4, 6]))
        # bus position at toy node 4, stops 1 and 2 at toy nodes 1 and 3, campus at toy node 6
        self.coords = {0: N[4], 1: N[1], 2: N[3]}
        self.campus = N[6]
        self.closure = dict(TOY_CLOSURE, circles=[[24.910, 67.000, 30.0]])        # touches no used road

    def test_missing_corridor_falls_back_to_the_city(self):
        with tempfile.TemporaryDirectory() as tmp:
            corridor, area = run_reroute.route_corridor(Path(tmp), "T-T", self.graph.version)
        self.assertEqual((corridor, area), (None, "city"))
        source = run_reroute.GraphSource(self.graph, corridor, area, self.coords, self.campus)
        source.snap([0, 1, 2])
        row = run_reroute.solve_case(TOY_SCENARIO, self.closure, WALK, "graph_limited", source, cap_s=30)
        self.assertEqual((row["status"], row["corridor"], row["widened"]), ("ok", "city", False))
        self.assertGreater(row["searches"], 0)
        self.assertIsNotNone(row["final_delay_s"])

    def test_worker_loads_the_graph_from_disk_and_writes_one_row_per_scenario(self):
        import numpy as np
        from reroute.roadnet import build_tables
        from reroute.tests.toymap import N, TOY
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "graph").mkdir()
            for k, v in build_tables(TOY, keep_ids=[1, 3, 4, 6]).items():
                np.save(d / "graph" / f"{k}.npy", v)
            (d / "graph" / "meta.json").write_text(json.dumps({"version": "toy"}))
            stops = [{"lat": N[7][0], "lng": N[7][1]} for _ in range(23)]
            for base in (0, 10, 20):
                for off, n in ((0, 4), (1, 1), (2, 3)):
                    stops[base + off] = {"lat": N[n][0], "lng": N[n][1]}
            (d / "instance.json").write_text(json.dumps({"stops": stops, "campus": {"lat": N[6][0], "lng": N[6][1]}}))
            content = run_reroute.toy_content()
            for c in content["closures"]:
                c["circles"] = [[24.910, 67.010, 30.0]]
            (d / "scen.json").write_text(json.dumps(content))
            args = run_reroute.parse_args(["worker", "--route", "T-T", "--arm", "graph_limited", "--repeat", "1",
                                           "--out", str(d / "rows.jsonl"), "--scenarios", str(d / "scen.json"),
                                           "--graph", str(d / "graph"), "--corridors", str(d / "none"),
                                           "--instance", str(d / "instance.json")])
            run_reroute._worker_main(args)
            rows = [json.loads(l) for l in (d / "rows.jsonl").read_text().splitlines()]
        self.assertEqual([r["scenario"] for r in rows], ["T-L1-late", "T-L2-late", "T-L3-late"])
        self.assertTrue(all(r["corridor"] == "city" and r["t_first_s"] is not None for r in rows))

    def test_points_inside_a_block_are_closed_on_the_graph(self):
        source = run_reroute.GraphSource(self.graph, None, "city", self.coords, self.campus)
        source.snap([0, 1, 2])
        at_stop_1 = dict(self.closure, circles=[[24.900, 67.000, 30.0]])
        problem, _ = source.problem(TOY_SCENARIO, at_stop_1, WALK, 400)
        self.assertEqual(problem.row(problem.start)[0], INF)


class ImportTests(unittest.TestCase):
    def test_imports_and_summarises_with_the_standard_library_only(self):
        code = ("import sys, json, tempfile, pathlib; sys.modules['numpy'] = None; sys.modules['scipy'] = None; "
                f"sys.path.insert(0, {str(RESEARCH)!r}); import run_reroute; "
                "d = pathlib.Path(tempfile.mkdtemp()); "
                "(d / 'meta.json').write_text(json.dumps({'pass': 'quality', 'runs_total': 5})); "
                "(d / 'runs.jsonl').write_text(json.dumps({'key': 'a-L400-main', 'status': 'ok', 'scenario': 'a', "
                "'arm': 'main', 'limit_m': 400, 'kind': 'synthetic', 'judged': False, 'route': 'R', "
                "'started_at': 'x'}) + '\\n'); "
                "s = run_reroute.build_summary(d); print(s['runs_done'], s['runs_total'])")
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["1", "5"])

    def test_default_output_folders_are_paths(self):
        for command in ("quality", "limits", "scale"):
            args = run_reroute.parse_args([command, "--quick", "--summarize"])
            self.assertEqual(run_reroute._out_dir(args), run_reroute.RESULTS / f"{run_reroute.PASSES[command]}-quick")


class SummaryTests(unittest.TestCase):
    def write(self, d, meta, rows):
        (d / "meta.json").write_text(json.dumps(meta))
        (d / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    def test_no_runs_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(run_reroute.build_summary(Path(tmp)))

    def test_rerun_replaces_the_earlier_row_and_invalid_rows_are_counted(self):
        a = dict(lim("a", 1, 2, 10), key="a-graph_limited-r1", started_at="1", route="R")
        later = dict(a, status="invalid_on_truth", started_at="2")
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.write(d, {"pass": "limits", "runs_total": 1}, [a, later])
            s = run_reroute.build_summary(d)
        self.assertEqual((len(s["rows"]), s["runs_done"], s["runs_failed"]), (1, 1, 1))   # a result, but not ok
        cell = next(c for c in s["cells"] if c["arm"] == "graph_limited")
        self.assertEqual(cell["invalid_on_truth"], 1)
        self.assertEqual(s["verdict"]["at_30"], "fail")
        for key in ("generated_at", "meta", "thresholds", "verdict", "chips", "runs_done", "runs_total",
                    "runs_failed", "remaining_s", "rows", "cells", "per_route"):
            self.assertIn(key, s)

    def test_quality_summary_from_the_toy_rows(self):
        rows = run_reroute.quality_rows(TOY_SCENARIO, TOY_CLOSURE, WALK)
        for r in rows:
            r["started_at"] = "x"
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.write(d, {"pass": "quality", "runs_total": 5}, rows)
            s = run_reroute.build_summary(d)
        self.assertEqual(s["verdict"]["gain"], "pass")                     # 410 - 10 = 400 s net
        self.assertEqual(s["per_route"]["worst_route"], "T-T")
        self.assertEqual(len(s["chips"]), 3)
        self.assertIn("60 s", s["chips"][0]["label"])
        cell = next(c for c in s["cells"] if c["scope"] == "all" and c["arm"] == "main" and c["limit_m"] == 400
                    and c["method"] == "R3")
        self.assertEqual((cell["median_delay_s"], cell["worst_delay_s"], cell["share_differs_from_r0"]),
                         (-10.0, -10.0, 1.0))


class FailureCountingTests(unittest.TestCase):
    """Review fixes: which statuses are failures, and how the limits pass scores graph plans on truth."""

    def test_failed_rows_fail_no_violations_even_with_nothing_judged(self):
        crashed = {"scenario": "x", "arm": "main", "limit_m": 400, "kind": "synthetic", "status": "failed"}
        self.assertEqual(quality_verdict([crashed])["no_violations"], "fail")

    def test_infeasible_and_historical_failures_are_not_violations(self):
        infeasible = dict(q("i", "main", 0, judged=False), status="infeasible")
        hist = dict(q("h", "main", 0, kind="historical", judged=False), status="failed")
        self.assertEqual(quality_verdict([q("a", "main", 5), infeasible, hist])["no_violations"], "pass")

    def test_infeasible_is_not_counted_as_failed(self):
        rows = [dict(lim("a", 1, 1, 0), key="a-r1", started_at="1"),
                dict(lim("b", 1, None, None), key="b-r1", started_at="2", status="infeasible")]
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "meta.json").write_text(json.dumps({"pass": "limits", "runs_total": 2}))
            run_reroute.append_rows(d, rows)
            s = run_reroute.build_summary(d)
        self.assertEqual(s["runs_failed"], 0)
        self.assertTrue(s["verdict"]["complete"])
        cell = next(c for c in s["cells"] if c["arm"] == "graph_limited" and c["scope"] == "all")
        self.assertEqual(cell["infeasible"], 1)

    def test_graph_plan_that_never_reaches_campus_is_invalid_when_truth_can(self):
        class NoCampusGraph:
            area = "city"

            def problem(self, scenario, closure, walk, limit_m):
                from reroute import table_rows
                from reroute_cases import build_problem, sub_table
                table = [[INF if (b == 3) != (a == 3) else t for b, t in enumerate(r)]
                         for a, r in enumerate(sub_table(closure, "post", scenario))]
                tt = type("TT", (), {"widened": False, "searches": 0, "hits": 0, "reused": 0})()
                return build_problem(scenario, closure, walk, limit_m, rows=table_rows(table)), tt

        row = run_reroute.solve_case(TOY_SCENARIO, TOY_CLOSURE, WALK, "graph_limited", NoCampusGraph(), 5.0)
        self.assertEqual(row["status"], "invalid_on_truth")
        self.assertIsNone(row["final_delay_s"])
        json.dumps(row, allow_nan=False)

    def test_truth_arm_on_the_toy_scenario_is_ok_and_matches_the_oracle(self):
        row = run_reroute.solve_case(TOY_SCENARIO, TOY_CLOSURE, WALK, "truth_limited", None, 30.0)
        row = run_reroute.fill_gaps(row, run_reroute.oracle_info(TOY_SCENARIO, TOY_CLOSURE, WALK))
        self.assertEqual((row["status"], row["final_gap_s"]), ("ok", 0.0))

    def test_infeasible_scenario_is_never_judged(self):
        unservable = dict(TOY_CLOSURE, post=[[0, INF, INF, 650], [INF, 0, INF, 590], [INF, INF, 0, 700],
                                             [INF, INF, INF, 0]])
        self.assertFalse(run_reroute.oracle_info(TOY_SCENARIO, unservable, WALK)["judged"])


class RobustnessTests(unittest.TestCase):
    """Review fixes: a torn last line, a scenario the oracle cannot solve, a changed scenario file."""

    def test_torn_last_line_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "runs.jsonl").write_text(json.dumps({"key": "a", "status": "ok"}) + "\n" + '{"key": "b", "sta',
                                          encoding="utf-8")
            self.assertEqual(list(run_reroute.read_latest(d)), ["a"])

    def test_oracle_crash_gives_a_failed_row_not_a_crash(self):
        broken = dict(TOY_CLOSURE, points=[0, 1])                 # stop 2 missing: building the problem raises
        oracle = run_reroute.safe_oracle_info(TOY_SCENARIO, broken, WALK)
        self.assertFalse(oracle["judged"])
        row = run_reroute.fill_gaps({"status": "ok", "delay_30s": 10.0}, oracle)
        self.assertEqual(row["status"], "failed")
        self.assertIn("oracle", row["error"])

    def test_changed_scenario_file_keeps_the_earlier_hash(self):
        import argparse
        args = argparse.Namespace(command="quality", quick=True, code_version=None)
        with tempfile.TemporaryDirectory() as tmp:
            d, scen = Path(tmp), Path(tmp) / "s.json"
            scen.write_text(json.dumps({"version": 1}), encoding="utf-8")
            run_reroute._write_meta(d, args, scen, 5)
            first = json.loads((d / "meta.json").read_text(encoding="utf-8"))["scenarios"]["sha256"]
            scen.write_text(json.dumps({"version": 2}), encoding="utf-8")
            run_reroute._write_meta(d, args, scen, 5)
            info = json.loads((d / "meta.json").read_text(encoding="utf-8"))["scenarios"]
        self.assertEqual((info["earlier_sha256"], info["version"]), ([first], 2))
        self.assertNotEqual(info["sha256"], first)


if __name__ == "__main__":
    unittest.main()


class ScaleNoLimitsTests(unittest.TestCase):
    """--no-limits must not create 'limited' scaling measurements that ran without limits."""

    def test_no_limits_runs_only_the_unlimited_setup(self):
        import argparse
        import tempfile
        from unittest import mock
        import run_reroute
        seen = {}

        def fake_jobs(quick, only, cases, limits_ok):
            seen["limits_ok"] = limits_ok
            return []

        with tempfile.TemporaryDirectory() as tmp:
            args = argparse.Namespace(summarize=False, quick=False, no_limits=True, sudo=False, only="stops",
                                      scenarios=Path(tmp) / "missing.json", walk=None, graph=Path(tmp) / "g",
                                      corridors=Path(tmp) / "c", instance=None, out_dir=Path(tmp), code_version="x", command="scale")
            with mock.patch.object(run_reroute, "scale_jobs", fake_jobs), \
                    mock.patch.object(run_reroute, "summarize", lambda out_dir: None):
                run_reroute.cmd_scale(args)
        self.assertIs(seen["limits_ok"], False)
        self.assertEqual([j["setup"] for j in run_reroute.scale_jobs(False, "stops", None, False)][:1], ["unlimited"])
        self.assertNotIn("limited", {j["setup"] for j in run_reroute.scale_jobs(False, "stops", None, False)})
