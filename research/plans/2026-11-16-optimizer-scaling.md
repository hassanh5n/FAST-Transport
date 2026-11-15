# Optimizer Scaling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the route optimizer hand travel times to OR-Tools as a matrix, and measure how its build time, memory and plan quality grow as the number of stops and buses grows.

**Architecture:** `optimize.py: solve` gains a `lookup` argument: `"callback"` (today's behaviour, the default, so results B1, Q1, T1 and S1 stay reproducible) or `"matrix"`. A new script, `run_scale.py`, builds four instances of growing size and runs both lookups on each.

**Tech Stack:** Python 3.10+, OR-Tools 9.15.6755 (in the WSL research environment). Tests use `unittest`.

**Spec:** `research/plans/2026-11-15-rerouting-plan.md` (version 2), Section 8.6 and work item S3. This plan has 6 hours in the schedule; the doubled instance is second in the work plan's cut order.

## Global Constraints

- The default behaviour of `optimize.py` does not change. Every existing result was produced with `lookup="callback"`.
- The model is unchanged: 08:00 arrival, 90-minute ride limit, 60 s plus 5 s per student stop time, capacity, total student ride time as the objective.
- This run has no pass or fail threshold; it reports curves. It still gets a logbook entry before it runs, stating what is measured.
- Tests need OR-Tools, so they run in WSL: `~/fc-research-venv/bin/python -m unittest discover -s research/tests -t research -v`
- Commit messages start with `Research:` and carry no co-author line.

## Review Focus

1. **A travel time that is not a whole number** (the saved matrix has one decimal): both lookups truncate the same way, so they see the same model. Task 1.
2. **An instance with more buses than stops**: builds and solves; spare buses stay empty. Task 1.
3. **A stop no bus can reach within 90 minutes**: reported in `dropped`, as today, under both lookups. Task 1.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `research/optimize.py` | `solve(T, q, capacities, time_limit, lookup="callback")` |
| `research/scale_instances.py` | Pure: build the four instances from the saved files |
| `research/run_scale.py` | Run both lookups on each instance; write `results/optimizer-scale/` |
| `research/tests/test_optimize_lookup.py`, `research/tests/test_scale_instances.py` | Tests |

---

### Task 1: Matrix lookup in the optimizer

**Files:**
- Modify: `research/optimize.py` (`solve`, around lines 95 to 153)
- Test: `research/tests/test_optimize_lookup.py`

**Interfaces:**
- Produces: `solve(T, q, capacities, time_limit, lookup: str = "callback") -> tuple[dict | None, list]`. With `lookup="matrix"` the two transit callbacks (`drive` and `transit`) and the demand callback are replaced by `routing.RegisterTransitMatrix(...)` and `routing.RegisterUnaryTransitVector(...)`, built once from `T`, `q` and the same rules: zero from the dummy start node, `10 ** 7` to the dummy node, `int(T[a][b])` otherwise; the time matrix adds the stop time of the node being left unless it is campus or the dummy. Any other value of `lookup` raises `ValueError`.

- [ ] **Step 1: Confirm the OR-Tools calls exist in 9.15.** In WSL:

```bash
~/fc-research-venv/bin/python -c "from ortools.constraint_solver import pywrapcp as p; print(hasattr(p.RoutingModel,'RegisterTransitMatrix'), hasattr(p.RoutingModel,'RegisterUnaryTransitVector'))"
```

Expected: `True True`. Then read the docstring of `RegisterTransitMatrix` (`help(p.RoutingModel.RegisterTransitMatrix)`) to learn whether the matrix is indexed by node or by routing index. The model has one extra start index per bus, so the two are not the same. The tests in Step 2 fail loudly if the wrong one is assumed.

- [ ] **Step 2: Write the failing tests**

```python
import unittest
from optimize import solve, score

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
```

A four-stop instance is solved to its best plan well inside 3 s under either lookup, so equal scores are a fair test that both lookups describe the same model.

- [ ] **Step 3: Run and confirm failure** (`solve() got an unexpected keyword argument 'lookup'`).
- [ ] **Step 4: Implement the `lookup` argument.**
- [ ] **Step 5: Run and confirm the tests pass.**
- [ ] **Step 6: Check nothing changed for existing results.** Run this once on the commit before the change and once after, on the same machine with nothing else running:

```bash
~/fc-research-venv/bin/python research/optimize.py --time-limit 60 --contractor Nadeem --no-html --out-dir /tmp/check
```

Expected: the same `optimized ... student-min` line both times. Runs B1 and Q1 recorded 29,898 for this setting on two laptops; a third machine may land elsewhere, which is why the comparison is before against after, not against that figure. A difference between the two means the default path was altered.

- [ ] **Step 7: Commit** with message `Research: optimizer can hand travel times to the solver as a matrix`.

---

### Task 2: Instances of growing size

**Files:**
- Create: `research/scale_instances.py`
- Test: `research/tests/test_scale_instances.py`

**Interfaces:**
- Produces:
  - `contractor_instance(inst: dict, mat: dict, contractor: str) -> dict`: `{"name", "T", "q", "capacities"}` exactly as `optimize.py: main` builds them today (node 0 is campus).
  - `combined_instance(inst: dict, mat_all: dict) -> dict`: all 311 stops in one problem; `q` is each stop's students summed over contractors; `capacities` are both fleets' buses. `mat_all` is `matrix_fall2026_v1_all.json`.
  - `doubled_instance(base: dict, gap_s: float = 30.0) -> dict`: every stop appears twice. A copy is `gap_s` seconds from its original in both directions and has the original's times to and from every other node; a copy carries the same students; every bus appears twice. Node 0 stays campus.

- [ ] **Step 1: Write the failing tests**

```python
import unittest
from scale_instances import doubled_instance, combined_instance

BASE = {"name": "b", "T": [[0, 10, 20], [11, 0, 5], [21, 6, 0]], "q": [0, 4, 7], "capacities": [30]}

class ScaleInstanceTests(unittest.TestCase):
    def test_doubled_shape(self):
        d = doubled_instance(BASE)
        self.assertEqual((len(d["T"]), d["q"], d["capacities"]), (5, [0, 4, 7, 4, 7], [30, 30]))

    def test_copy_sits_beside_its_original(self):
        T = doubled_instance(BASE)["T"]
        self.assertEqual((T[1][3], T[3][1], T[3][3]), (30.0, 30.0, 0))      # stop 1 and its copy
        self.assertEqual((T[3][0], T[0][3], T[3][2], T[3][4]), (11, 10, 5, 5))   # copy behaves like stop 1

    def test_combined_sums_students_and_fleets(self):
        inst = {"stops": [{"name": "A", "students": {"J": 2, "N": 3}}, {"name": "B", "students": {"J": 1}}],
                "contractors": {"J": {"buses": [{"capacity": 30}]}, "N": {"buses": [{"capacity": 40}, {"capacity": 45}]}}}
        mat_all = {"contractors": {"All": {"nodes": ["CAMPUS", "A", "B"], "durations_s": [[0, 1, 2], [1, 0, 3], [2, 3, 0]]}}}
        c = combined_instance(inst, mat_all)
        self.assertEqual((c["q"], sorted(c["capacities"])), ([0, 5, 1], [30, 40, 45]))
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `scale_instances.py`.**
- [ ] **Step 4: Run and confirm the tests pass.**
- [ ] **Step 5: Commit** with message `Research: optimizer instances of growing size`.

---

### Task 3: The scaling run

**Files:**
- Create: `research/run_scale.py`
- Modify: `research/hub/experiments.json` (one entry, `"kind": "scale"`, which gets the hub's generic table), `research/README.md`

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces `results/optimizer-scale/`: `meta.json`, `runs.jsonl` and per-run JSON in the hub's format. One run per instance and lookup: instances `Jadoon` (171 stops), `Nadeem` (143), `All` (311), `All-doubled` (622); lookups `callback` and `matrix`; 300 s each, no limits: 8 runs, 40 minutes. Row fields: `key, setup, status, instance, stops, buses, lookup, build_s, first_plan_s, peak_mb, ride_10s, ride_60s, ride_300s, improvements, solve_cpu_s, started_at, code_version`. `build_s` is the time to construct the model: the part of `solve` before `SolveWithParameters`, which `solve` returns as a third value only when called with `timings=True`. `first_plan_s` is the time from entering `solve` to the first plan.
- `ride_Ns` is the best plan's cost at N seconds, read from the `progress` list `solve` already returns.
- Each run is a fresh process, so peak memory is per run. Resumable; `--quick` runs `Nadeem` only for 10 s under both lookups into `results/optimizer-scale-quick/`.

- [ ] **Step 1: Add `timings=False` to `solve`** (returns `(result, progress)` as today when false, `(result, progress, {"build_s": ...})` when true) and a test that the default return still has two values.
- [ ] **Step 2: Write `run_scale.py`,** following `run_robustness.py` for resuming and row writing.
- [ ] **Step 3: Run the quick test.** Expected: 2 rows, both `ok`, with `ride_10s` values within a few percent of each other.
- [ ] **Step 4: Write the logbook "planned" entry** (what is measured, no threshold, that the doubled instance copies stops 30 s apart and so tests model size, not geography) and push it.
- [ ] **Step 5: Run it from the hub.** `All` and `All-doubled` need `data/matrix_fall2026_v1_all.json` from the offline-builders plan; without it the script runs the two contractor instances and records the other two as `skipped`.
- [ ] **Step 6: Commit and write the logbook result entry the same day.** Report: build time and memory against stops; plan cost against CPU-seconds for each size; callback against matrix. State that the number of students does not change the model's size, only stops and buses do.
