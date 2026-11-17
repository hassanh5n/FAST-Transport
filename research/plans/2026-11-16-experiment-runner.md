# Experiment Runner Implementation Plan (quality pass, limits pass, scaling runs, hub)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One script, `run_reroute.py`, that runs the three rerouting experiments from the frozen scenario file, judges them against thresholds fixed in the logbook, and shows up in the research hub.

**Architecture:** Pure functions turn a scenario into a solver `Problem`, score a plan on the true travel times, and build summaries; they are unit-tested on a hand-made toy scenario file. Three sub-commands (`quality`, `limits`, `scale`) drive them. The limits pass starts one worker process per route inside the same systemd limits as run B1; the worker loads the road graph once and handles that route's scenarios in turn, which is the "graph already loaded" condition.

**Tech Stack:** Python 3.10+ standard library, `numpy`, `scipy`, the `reroute` package; systemd in WSL for the limits. No OSRM and no Docker.

**Spec:** `research/plans/2026-11-15-rerouting-plan.md` (version 2), Sections 8.3 to 8.5 and work item C3. Reads the scenario file defined in `research/plans/2026-11-16-offline-builders.md`; uses `Ladder`, `evaluate` and `Problem` from the solver-core plan and `Graph`, `TravelTimes`, `problem_rows` from the road-graph plan.

## Global Constraints

- `numpy`, `scipy` and `reroute` are imported inside functions, never at the top of `run_reroute.py`. The hub's page builder imports every runner, and the GitHub Pages job has only the standard library.
- Thresholds are module constants copied from the logbook entry. They are not changed after results exist.
- Each finished run is one JSON line in `<dir>/runs.jsonl` with at least `key`, `status`, `started_at`; finished runs are skipped on restart; a rerun of a key replaces the earlier row in summaries.
- `--quick` reads `data/scenarios_toy.json` only and writes to a `-quick` folder. It never touches the frozen scenarios.
- **Judged set:** scenarios with at least 2 remaining stops whose patched route loses at least 60 s.
- Synthetic and historical scenarios are never pooled in a threshold; thresholds are judged on synthetic scenarios, historical ones are reported beside them.
- Walking limits run: 0, 400 and 800 m. Must-serve arm: 25% of remaining stops, rounded up, at least one, drawn with `random.Random(f"2026-{scenario id}")`.
- Proposed thresholds (final values come from the logbook entry):
  - `GAIN_MIN_S = 60`: median closure-specific gain of the best plan over the patched route at 400 m.
  - `NEAR_ORACLE_S = 60`, `NEAR_ORACLE_SHARE = 0.90`: the greedy plan's delay is within 60 s of the best plan's in at least 90% of judged scenarios, and on every route's median.
  - `FIRST_PLAN_S = 5`, `FIRST_PLAN_SHARE = 0.95`; `AT_30_SHARE = 0.90` (within `NEAR_ORACLE_S` of the best plan's delay at 30 s); `MEMORY_MB = 400`.
- Commit messages start with `Research:` and carry no co-author line.

## Review Focus

1. **A scenario whose every stop is unservable or whose campus is unreachable**: the row is written with status `infeasible` and counted, the run does not crash. Task 1.
2. **A plan made on the graph that the true times make invalid** (a point truly unreachable): scored as a failure with status `invalid_on_truth`, counted in the summary. Task 1.
3. **No judged scenarios at all**: verdicts are `None`, not a division by zero. Task 2.
4. **The worker is killed for memory**: the parent records `killed_memory` for that route's scenarios and carries on. Task 4.
5. **A route with no corridor file**: the worker falls back to the whole graph and records `corridor: "city"`. Task 4.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `research/run_reroute.py` | Sub-commands, constants, summaries |
| `research/reroute_cases.py` | Pure: scenario to `Problem`, scoring on truth, must-serve draw, timeline checkpoints |
| `research/data/scenarios_toy.json` | Three hand-checkable scenarios, built by `python run_reroute.py make-toy` |
| `research/tests/test_reroute_cases.py`, `research/tests/test_reroute_summary.py` | Unit tests |
| `research/hub/experiments.json`, `research/hub/build_site.py`, `research/hub/project.json` | Hub entries, summary dispatch, plan text |

---

### Task 1: From a scenario to a problem, and scoring on true times

**Files:**
- Create: `research/reroute_cases.py`
- Test: `research/tests/test_reroute_cases.py`

**Interfaces:**
- Consumes: the scenario file shape; `Problem`, `StopNeed`, `table_rows`, `evaluate`, `InvalidPlan`, `Plan`.
- Produces:
  - `case_points(scenario: dict) -> list[int]`: `remaining` followed by `candidates`.
  - `sub_table(closure: dict, which: str, scenario: dict) -> list[list[float]]`: the (P + 2) square table for this scenario cut from the closure's `pre` or `post` table: the scenario's points in order, then the bus position, then campus.
  - `build_problem(scenario, closure, walk, limit_m: float, which: str = "post", must_serve: Sequence[int] = (), rows=None) -> Problem`: stops are the remaining stops in order with their students and `limit_m`; `rows` defaults to `table_rows(sub_table(...))`.
  - `baseline_arrival(scenario, closure, walk) -> float`: arrival of the published order, every remaining stop visited, on the `pre` table.
  - `score_on_truth(scenario, closure, walk, limit_m, plan: Plan, must_serve=()) -> dict`: replays the plan's visit order and boarding choices on the `post` table. Returns `{"status": "ok", "arrival_s", "delay_s", "walkers", "walk_m_per_walker", "unserved"}`; status `invalid_on_truth` when `evaluate` raises or the arrival is infinite.
  - `must_serve_draw(scenario: dict) -> list[int]`.
  - `checkpoints(timeline: Sequence[tuple[float, Plan]], at: Sequence[float] = (1, 5, 30)) -> dict[float, Plan | None]`: the last plan whose elapsed time is at or before each checkpoint.

- [ ] **Step 1: Write the toy scenario in the test file** (also the source for `make-toy` in Task 3):

```python
INF = float("inf")
# points: stops 1 and 2 of one route; campus last. Same numbers as the solver plan's tiny problem.
TOY_CLOSURE = {"id": "T-L1", "kind": "synthetic", "contractor": "T", "route": "T", "leg": 1, "factor": 0.0,
               "circles": [[24.9, 67.0, 200.0]], "points": [0, 1, 2], "closed_points": [],
               "pre":  [[0, 100, 300, 650], [100, 0, 200, 590], [300, 200, 0, 500], [INF, INF, INF, 0]],
               "post": [[0, 100, 300, 650], [100, 0, 400, 590], [300, 400, 0, 700], [INF, INF, INF, 0]]}
TOY_SCENARIO = {"id": "T-L1-late", "closure": "T-L1", "trigger": "late", "position": 0, "remaining": [1, 2],
                "students": {"1": 4, "2": 2}, "candidates": [], "tags": {"remaining": 2, "closure_contains_stop": False}}
WALK = {(2, 1): 240.0}
```

Stop 0 is where the bus is; stops 1 and 2 remain. Before the closure the published order arrives at 100 + 80 + 200 + 70 + 500 = **950**. After it, the published order arrives at 100 + 80 + 400 + 70 + 700 = **1350**, a delay of **400**. Letting stop 2 walk to stop 1 arrives at 260 + 90 + 590 = **940**, a delay of **-10**.

- [ ] **Step 2: Write the failing tests**

```python
import unittest
from reroute import Ladder, solve_r0
from reroute_cases import (case_points, sub_table, build_problem, baseline_arrival, score_on_truth, must_serve_draw, checkpoints)

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
```

The control test shows the point of the control arm: with no closure at all, letting stop 2 walk still gains 10 s. With the closure it gains 410 s. The closure-specific gain is 400 s.

- [ ] **Step 3: Run and confirm failure.**
- [ ] **Step 4: Implement `reroute_cases.py`.**
- [ ] **Step 5: Run and confirm the tests pass.**
- [ ] **Step 6: Commit** with message `Research: scenario cases and scoring on true times`.

---

### Task 2: Summaries and verdicts

**Files:**
- Create: `research/run_reroute.py` (constants and `build_summary` only in this task)
- Test: `research/tests/test_reroute_summary.py`

**Interfaces:**
- Produces:
  - Constants: the thresholds in Global Constraints; `LIMITS_M = (0, 400, 800)`; `JUDGED_MIN_REMAINING = 2`; `JUDGED_MIN_R0_DELAY_S = 60`.
  - Row shape of the quality pass, one row per scenario, limit and arm (`main`, `control`, `must_serve`); key `{scenario}-L{limit}-{arm}`:
    `key, setup, status, scenario, route, contractor, kind, trigger, limit_m, arm, remaining, r0_delay_s, r2_delay_s, r3_delay_s, r3_gain_s, r3_walkers, r3_walk_m_per_walker, r2_minus_r3_s, unserved, judged, closure_contains_stop, r3_differs_from_r0, started_at, code_version`. `r3_gain_s` is the patched route's arrival minus the best plan's, on the table that arm uses. `judged` is computed from the `main` row at 400 m and copied to the scenario's other rows.
  - Row shape of the limits pass, one row per scenario, arm (`graph_limited`, `graph_unlimited`, `truth_limited`) and repeat; key `{scenario}-{arm}-r{repeat}`:
    `key, setup, status, scenario, route, kind, arm, repeat, t_first_s, t_done_s, method_1s, method_5s, method_30s, gap_1s, gap_5s, gap_30s, final_gap_s, planned_minus_true_s, rows_requested, searches, corridor, widened, peak_mb, judged, started_at, code_version`. `gap_Ns` is the delay on true times of the plan held at N seconds minus the oracle's delay.
  - `build_summary(out_dir: Path) -> dict | None`: the same keys every hub summary has (`generated_at`, `meta`, `thresholds`, `verdict`, `chips`, `runs_done`, `runs_total`, `runs_failed`, `remaining_s`, `rows`) plus `cells` and `per_route`. It reads `meta.json["pass"]` to know which pass it is summarising.
  - `quality_verdict(rows) -> dict` with keys `gain`, `near_oracle`, `no_violations`, each `"pass"`, `"fail"` or `None`:
    - `gain`: over judged synthetic scenarios, the median of (`main` `r3_gain_s` at 400 m minus `control` `r3_gain_s` at 400 m) is at least `GAIN_MIN_S`.
    - `near_oracle`: over judged synthetic `main` rows at 400 m, the share with `r2_minus_r3_s` at most `NEAR_ORACLE_S` is at least `NEAR_ORACLE_SHARE`, and every route's median is at most `NEAR_ORACLE_S`.
    - `no_violations`: no row has status other than `ok`, and no `main` row has `r3_delay_s` greater than `r0_delay_s`.
  - `limits_verdict(rows) -> dict` with keys `first_plan`, `at_30`, `memory`, judged on `graph_limited` rows of judged synthetic scenarios, taking each scenario's worst repeat.

- [ ] **Step 1: Write the failing tests**

```python
import unittest
from run_reroute import quality_verdict, limits_verdict

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

def lim(scenario, rep, first, gap30, mb=100, arm="graph_limited", judged=True, kind="synthetic"):
    return {"scenario": scenario, "repeat": rep, "arm": arm, "judged": judged, "kind": kind, "status": "ok",
            "t_first_s": first, "gap_30s": gap30, "peak_mb": mb}

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
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement the constants, the two verdict functions and `build_summary`.** `chips` are built from the verdicts with labels that state the rule, for example `Walking gains at least 60 s net of the no-closure control (400 m)`. `cells` hold, per kind, limit and method: median, 90th percentile and worst delay, students walking, and the share of scenarios where the best plan differs from the patched route. `per_route` holds each route's median and worst values and names the worst route.
- [ ] **Step 4: Run and confirm the tests pass.**
- [ ] **Step 5: Commit** with message `Research: rerouting summaries and verdict rules`.

---

### Task 3: Quality pass and the toy file

**Files:**
- Modify: `research/run_reroute.py`
- Create: `research/data/scenarios_toy.json`

**Interfaces:**
- Consumes: Tasks 1 and 2; `load_scenarios`, `load_walk`.
- Produces:
  - `python research/run_reroute.py make-toy`: writes `data/scenarios_toy.json` from the toy closure and scenario of Task 1 plus two variants (one with an empty walking table, so no stop can walk; one with stop 2 listed in `closed_points` and its `post` row and column infinite), with a matching toy walking table inside the file under `"walk"`.
  - `python research/run_reroute.py quality [--quick] [--workers N] [--code-version V] [--summarize]`: output in `results/reroute-quality/` or `results/reroute-quality-quick/`. `meta.json` records `pass: "quality"`, machine, scenario file version and SHA-256, `runs_total`.
  - One job per scenario; a job writes the rows for every limit and arm (3 `main`, 1 `control` at 400 m, 1 `must_serve` at 400 m). R0, R2 and R3 are each solved in full with no time limit, on the table the arm uses, and each plan is scored with `score_on_truth` (the `control` arm scores on `pre`).

- [ ] **Step 1: Implement `make-toy` and the `quality` sub-command**, following `run_robustness.py` for resuming, `ProcessPoolExecutor`, row writing and `machine_info`.
- [ ] **Step 2: Run the quick test:** `python research/run_reroute.py quality --quick`.

Expected: 3 scenarios, 15 rows, all `ok`; for `T-L1-late` the `main` row at 400 m has `r0_delay_s` 400, `r3_delay_s` -10, `r3_gain_s` 410, and the `control` row has `r3_gain_s` 10. For the variant with an empty walking table, every row has `r3_gain_s` 0.

- [ ] **Step 3: Commit** with message `Research: rerouting quality pass`.

---

### Task 4: Limits pass

**Files:**
- Modify: `research/run_reroute.py`

**Interfaces:**
- Consumes: Tasks 1 to 3; `run_budget.limit_prefix`, `run_budget.check_limits`; `Graph.load`, corridors, `TravelTimes`, `problem_rows`, `Closure`, `closed_points`.
- Produces:
  - `python research/run_reroute.py limits [--quick] [--sudo] [--code-version V] [--summarize]`: output in `results/reroute-limits/`.
  - `python research/run_reroute.py worker --route KEY --arm ARM --repeat N --out FILE [--toy]`: internal. Loads the graph once (not for `truth_limited`), then for each of that route's scenarios: builds the problem, runs the ladder with `step(max_masks=256)` until done or 30 s, recording `(elapsed, plan)` after every step, and writes one row. Prints its own peak memory at the end.
  - The parent starts one worker per route, arm and repeat: `graph_limited` and `truth_limited` inside the systemd scope, `graph_unlimited` outside it with no 30 s cap. It computes each scenario's oracle itself (R3 on the `post` table, no limit) and fills in the gap columns.
  - With `--quick` (toy file, no road graph) only the `truth_limited` arm runs.
  - A worker killed by the memory limit gives every scenario of that route status `killed_memory`.

- [ ] **Step 1: Implement the worker and the parent.** The elapsed time for a scenario starts when the worker begins building that scenario's problem, so applying the closure to the graph is inside the measured time; loading the graph is not.
- [ ] **Step 2: Check the limits apply:** `python research/run_budget.py --check` prints `OK`.
- [ ] **Step 3: Run the quick test:** `python research/run_reroute.py limits --quick`.

Expected: 3 rows, arm `truth_limited`, all `ok`, `t_first_s` well under 5, `final_gap_s` 0 for each.

- [ ] **Step 4: Commit** with message `Research: rerouting limits pass under free-tier limits`.

---

### Task 5: Scaling runs

**Files:**
- Modify: `research/run_reroute.py`

**Interfaces:**
- Produces `python research/run_reroute.py scale [--quick] [--only NAME]`, output in `results/reroute-scale/`, one row per measurement, no verdicts. Four parts:
  - `stops`: synthetic problems (points placed at random in a square, straight-line travel times, as in the solver tests) with 4, 8, 12, 16 and 20 remaining stops and 1, 2 and 4 candidates per stop; 3 seeds each; limited and unlimited. Records CPU-seconds and peak memory for R2 and for R3, whether R3 ran, and the lower bound when it did not.
  - `graph`: on the longest route, rows for 10, 30 and 60 points on its corridor and on the whole city; limited and unlimited. Records CPU-seconds per row, searches, and resident memory with the arrays memory-mapped.
  - `buses`: the Shahrah-e-Faisal closure with 1, 5, 10 and 20 buses in one limited process sharing the row cache. Buses are that closure's scenarios taken in id order; if there are fewer than needed they are repeated and the row says so. Records seconds until every bus has a valid plan, seconds until every bus has its final plan, distinct searches, and cache hits.
  - `slices`: on the three largest judged scenarios, plan quality after each slice of 256 masks, and the size in bytes of `Ladder.to_json()` serialised.

- [ ] **Step 1: Implement the four parts.** The work plan asks for longer routes "made by joining real ones"; that needs travel times between stops of different routes, which the scenario tables do not hold, so `stops` uses synthetic problems. Say so in the logbook entry for this run.
- [ ] **Step 2: Run the quick test:** `python research/run_reroute.py scale --quick` runs `stops` at 4 and 8 stops and `slices` on the toy file. Expected: rows for both sizes with `r3_ran` true.
- [ ] **Step 3: Commit** with message `Research: rerouting scaling runs`.

---

### Task 6: Hub entries

**Files:**
- Modify: `research/hub/experiments.json`, `research/hub/build_site.py`, `research/hub/project.json`, `research/requirements.txt`, `research/README.md`

**Interfaces:**
- Consumes: `run_reroute.build_summary`.

- [ ] **Step 1: Add five entries to `experiments.json`,** all with `"kind": "reroute"`:

| id | dir | args | main |
| --- | --- | --- | --- |
| `reroute-quality` | `results/reroute-quality` | `quality --workers 2 --code-version {code_version}` | true |
| `reroute-limits` | `results/reroute-limits` | `limits --code-version {code_version}` | true |
| `reroute-scale` | `results/reroute-scale` | `scale --code-version {code_version}` | true |
| `reroute-quality-quick` | `results/reroute-quality-quick` | `quality --quick --code-version {code_version}` | false |
| `reroute-limits-quick` | `results/reroute-limits-quick` | `limits --quick --code-version {code_version}` | false |

Each needs `title`, `question`, `design` and `runs_total`, written from the work plan's Sections 8.3 to 8.5. `runs_total` for the main entries is filled in once the scenario file exists.

- [ ] **Step 2: In `build_site.py`** import `run_reroute` beside the other runners and add the branch `elif exp.get("kind") == "reroute": summary = run_reroute.build_summary(d)`.
- [ ] **Step 3: Check the page still builds with only the standard library.** Run in an environment without `numpy`:

```bash
python -S -c "import sys; sys.modules['numpy']=None; sys.modules['scipy']=None; sys.path.insert(0,'research/hub'); sys.path.insert(0,'research'); import build_site, tempfile, pathlib; build_site.build(pathlib.Path(tempfile.mkdtemp())/'site'); print('built')"
```

Expected: `built`. An `ImportError` means a top-level import of `numpy`, `scipy` or `reroute` slipped into `run_reroute.py`.

- [ ] **Step 4: Update `project.json`:** Rerouting status `in progress`; its `experiments` list the three main ids; `planned_experiments` and `next_steps` rewritten to match the work plan.
- [ ] **Step 5: Add `numpy`, `scipy` to `requirements.txt` if not already there, and a "Rerouting experiments" section to the README** with the five commands.
- [ ] **Step 6: Start the hub and run both quick tests from the Run & publish tab** on the machine that will run the experiments. Expected: both finish, appear under Experiments with pass or fail badges, and the run rows carry a code version, not `unknown`.
- [ ] **Step 7: Commit** with message `Research: rerouting experiments in the hub`.

---

### Task 7: The real runs

Only after the logbook entry with the rules is pushed (see the logbook plan) and the scenario file is frozen.

- [ ] **Step 1: Quality pass** from the hub. About 210 scenarios, seconds each.
- [ ] **Step 2: Limits pass** from the hub, on the same machine, plugged in, nothing else running.
- [ ] **Step 3: Scaling runs** from the hub.
- [ ] **Step 4: Publish each from the hub and write its logbook result entry the same day,** in the form of the T1 and S1 entries: when, machine, code version, tables, verdict against each rule, observations, caveats.
