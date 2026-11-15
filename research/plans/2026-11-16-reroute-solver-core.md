# Rerouting Solver Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `research/reroute/`, a pure-Python package that takes one bus's rerouting problem and returns a valid plan from a ladder of three methods (R0 patched route, R2 greedy, R3 exact), with a resumable solve and the JSON request and proposal formats.

**Architecture:** One `Problem` object holds the stops, candidate points, walking distances and a function that returns travel-time rows on request. One `evaluate` function scores any plan and is the only place the timing rules live; every method builds a visit order and boarding choices and calls it. A `Ladder` runs R0, then R2, then R3 in slices, and can be saved and restored between slices.

**Tech Stack:** Python 3.10+, standard library, `numpy` (R3 only). Tests use `unittest`; no new test dependency.

**Spec:** `research/plans/2026-11-15-rerouting-plan.md` (version 2), Sections 5, 6.3 and work item C2. This plan covers work item C2 only. Work item B1 (`build_graph.py`) needs its own plan, and C1 is a logbook entry.

## Global Constraints

- No import of Django, of anything under `backend/`, or of any other file in `research/`. No file or network access inside `research/reroute/`.
- Stop time: 60 s per visited point plus 5 s per student boarding there.
- Walkers start 60 s after the decision and walk at 1.2 m/s. The bus does not leave a point before the walkers boarding there have arrived.
- Walking limit per stop, default 400 m, maximum 800 m. A must-serve stop boards only at itself.
- Objective: earliest arrival at campus; among plans the solver holds with equal arrival, least total walking (students x metres).
- A point whose travel time from the bus is infinite cannot be visited. A stop with no reachable boarding point in range is reported `unserved`, never dropped silently.
- Committed points are always visited.
- R3 runs only when remaining stops plus committed points number 16 or fewer.
- Stops and points are identified by integer ids, never by name.
- All times inside the package are seconds after the decision time, as floats.
- Commit messages start with `Research:` and carry no co-author line.
- Tests run from `research/` with: `python -m unittest discover -s reroute/tests -t . -v`

## Review Focus

Inputs the spec implies but does not spell out. Each has a test in the task named.

1. **No remaining stops** (bus already past its last stop): every method returns an empty visit list and arrival equal to the direct time to campus. Task 2.
2. **Campus unreachable from the bus**: no method raises; the plan's arrival is infinite and the proposal status is `failed` with reason `campus unreachable`. Tasks 2 and 6.
3. **Travel times that break the triangle inequality** (estimated tables can): R3 still returns a valid plan, and the ladder's best plan never arrives later than R0. Tasks 4 and 5.
4. **A stop with zero students**: still needs a boarding point, adds no boarding time, adds no walking. Task 1.
5. **Duplicate ids, or a remaining stop missing from the points list**: `Problem` raises `ValueError` naming the id. Task 1.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `research/reroute/__init__.py` | Re-exports the public names |
| `research/reroute/model.py` | `StopNeed`, `Params`, `Problem`, `Plan`, `InvalidPlan`, `table_rows`, `evaluate`, `make_plan` |
| `research/reroute/ladder.py` | `servable`, `solve_r0`, `solve_r2`, `solve_r3`, `lower_bound`, `Ladder` |
| `research/reroute/wire.py` | `parse_request`, `to_proposal`, `failed_proposal`, `RequestError` |
| `research/reroute/tests/__init__.py` | empty |
| `research/reroute/tests/helpers.py` | `tiny_problem()`, `random_problem(seed, n_stops, n_extra)`, `brute_force(problem)` |
| `research/reroute/tests/test_model.py`, `test_r0.py`, `test_r2.py`, `test_r3.py`, `test_ladder.py`, `test_wire.py` | one per task |
| `research/requirements.txt` | add `numpy` |
| `research/README.md` | add the package to the layout table and the test command |

**Node indexing, used by every task.** A problem with P points has P + 2 nodes: indices `0..P-1` are the points in the order given, `P` is the bus position (`problem.start`), `P + 1` is campus (`problem.campus`). A travel-time row is a sequence of P + 2 floats; `math.inf` means unreachable.

**The tiny problem, used in several tests.** Points `[1, 2]`. Stops: id 1 with 4 students; id 2 with 2 students. Walking: only `(2, 1)`, 240 m, so stop 2 can walk to point 1 but stop 1 cannot walk to point 2. (With both directions allowed, visiting only point 2 would arrive at 890 and the expected values below would not be the best plans.) Travel times in seconds, by node index (0 = point 1, 1 = point 2, 2 = start, 3 = campus):

```python
INF = float("inf")
TINY = [
    [0,   200, INF, 590],   # from point 1
    [200, 0,   INF, 500],   # from point 2
    [100, 300, 0,   650],   # from start
    [INF, INF, INF, 0],     # from campus
]
```

Expected values, worked from the rules:
- Visit `[1, 2]`, each stop at itself: arrive 100, leave 100 + 60 + 20 = 180; arrive 380, leave 380 + 60 + 10 = 450; campus **950**; walking **0**.
- Visit `[1]`, stop 2 walks to point 1: walkers ready at 60 + 240 / 1.2 = 260; bus arrives 100 and waits; leaves 260 + 60 + 30 = 350; campus **940**; walking 2 x 240 = **480**.
- Visit `[2, 1]`, each at itself: arrive 300, leave 370; arrive 570, leave 650; campus **1240**.

---

### Task 1: Model and the scoring function

**Files:**
- Create: `research/reroute/__init__.py`, `research/reroute/model.py`, `research/reroute/tests/__init__.py`, `research/reroute/tests/helpers.py`
- Test: `research/reroute/tests/test_model.py`
- Modify: `research/README.md` (layout table row for `reroute/`, and the test command under a new heading "Rerouting solver tests")

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `StopNeed(id: int, students: int, walk_limit_m: float = 400.0, must_serve: bool = False)`, frozen dataclass.
  - `Params(stop_base_s: float = 60.0, stop_per_student_s: float = 5.0, walk_speed_mps: float = 1.2, walk_lag_s: float = 60.0)`, frozen dataclass.
  - `Problem(stops: Sequence[StopNeed], points: Sequence[int], rows: Callable[[list[int]], dict[int, Sequence[float]]], walk: Mapping[tuple[int, int], float], committed: Iterable[int] = (), params: Params = Params())`. `stops` are in published order. Attributes: `stops`, `points` (tuple), `committed` (frozenset), `params`, `index` (point id to node index), `start` (= P), `campus` (= P + 1), `rows_requested` (int, distinct rows fetched so far).
  - `Problem.row(node: int) -> Sequence[float]`: fetches through `rows` once per node and caches. `Problem.fetch(nodes: list[int]) -> None`: fetches all uncached nodes in one call to `rows`.
  - `Problem.walk_m(stop_id: int, point_id: int) -> float | None`: `0.0` when the ids are equal; the metres from `walk` when present; `None` otherwise.
  - `Problem.can_board(stop: StopNeed, point_id: int) -> bool`: true when the ids are equal, or when the stop is not must-serve and `walk_m` is not `None` and at most `stop.walk_limit_m`.
  - `Problem.ready_s(stop_id: int, point_id: int) -> float`: `0.0` when equal, otherwise `walk_lag_s + walk_m / walk_speed_mps`.
  - `table_rows(matrix: Sequence[Sequence[float]]) -> Callable`: wraps a full (P + 2) x (P + 2) table as a `rows` function.
  - `Plan(method: str, visit: tuple[int, ...], board_at: dict[int, int], unserved: tuple[int, ...], arrival_s: float, walk_m: float)`, frozen dataclass. `Plan.key -> tuple[float, float]` is `(arrival_s, walk_m)`.
  - `InvalidPlan(ValueError)`.
  - `evaluate(problem: Problem, visit: Sequence[int], board_at: Mapping[int, int], unserved: Sequence[int] = ()) -> tuple[float, float]`: returns `(arrival_s, walk_m)`. Raises `InvalidPlan` when: a point repeats in `visit`; a stop is neither in `board_at` nor in `unserved`; a stop's boarding point is not in `visit` or `can_board` is false; a committed point is not in `visit`. Unreachable legs give an infinite arrival and do not raise.
  - `make_plan(problem, method: str, visit, board_at, unserved=()) -> Plan`: calls `evaluate` and builds the `Plan`.
  - In `helpers.py`: `tiny_problem(**overrides) -> Problem` built from the table and values above; accepts `walk`, `stops`, `committed`, `matrix` overrides.

- [ ] **Step 1: Write the failing tests**

```python
import math, unittest
from reroute.model import (StopNeed, Problem, InvalidPlan, evaluate, make_plan, table_rows)
from reroute.tests.helpers import tiny_problem, TINY

class EvaluateTests(unittest.TestCase):
    def test_visit_both_stops(self):
        self.assertEqual(evaluate(tiny_problem(), [1, 2], {1: 1, 2: 2}), (950.0, 0.0))

    def test_bus_waits_for_walkers(self):
        self.assertEqual(evaluate(tiny_problem(), [1], {1: 1, 2: 1}), (940.0, 480.0))

    def test_order_matters(self):
        self.assertEqual(evaluate(tiny_problem(), [2, 1], {1: 1, 2: 2})[0], 1240.0)

    def test_no_wait_when_bus_is_later_than_walkers(self):
        p = tiny_problem(walk={(2, 1): 30.0})          # ready at 60 + 25 = 85, bus arrives 100
        self.assertEqual(evaluate(p, [1], {1: 1, 2: 1}), (100 + 60 + 30 + 590.0, 60.0))

    def test_zero_student_stop_costs_no_boarding_time_or_walking(self):
        p = tiny_problem(stops=[StopNeed(1, 4), StopNeed(2, 0)])
        self.assertEqual(evaluate(p, [1], {1: 1, 2: 1}), (260 + 60 + 20 + 590.0, 0.0))

    def test_walk_beyond_limit_is_invalid(self):
        p = tiny_problem(stops=[StopNeed(1, 4), StopNeed(2, 2, walk_limit_m=200)])
        with self.assertRaises(InvalidPlan):
            evaluate(p, [1], {1: 1, 2: 1})

    def test_must_serve_cannot_walk(self):
        p = tiny_problem(stops=[StopNeed(1, 4), StopNeed(2, 2, must_serve=True)])
        with self.assertRaises(InvalidPlan):
            evaluate(p, [1], {1: 1, 2: 1})

    def test_missing_stop_is_invalid_unless_listed_unserved(self):
        with self.assertRaises(InvalidPlan):
            evaluate(tiny_problem(), [1], {1: 1})
        self.assertEqual(evaluate(tiny_problem(), [1], {1: 1}, unserved=[2])[0], 100 + 60 + 20 + 590.0)

    def test_committed_point_must_be_visited(self):
        with self.assertRaises(InvalidPlan):
            evaluate(tiny_problem(committed=[2]), [1], {1: 1, 2: 1})

    def test_repeated_point_is_invalid(self):
        with self.assertRaises(InvalidPlan):
            evaluate(tiny_problem(), [1, 2, 1], {1: 1, 2: 2})

    def test_unreachable_leg_gives_infinite_arrival(self):
        m = [row[:] for row in TINY]; m[2][0] = math.inf
        self.assertEqual(evaluate(tiny_problem(matrix=m), [1, 2], {1: 1, 2: 2})[0], math.inf)

class ProblemTests(unittest.TestCase):
    def test_rows_are_fetched_once_and_counted(self):
        p = tiny_problem()
        p.row(p.start); p.row(p.start); p.fetch([p.start, 0])
        self.assertEqual(p.rows_requested, 2)

    def test_duplicate_point_id_raises_naming_the_id(self):
        with self.assertRaisesRegex(ValueError, "7"):
            Problem([StopNeed(7, 1)], [7, 7], table_rows(TINY), {})

    def test_stop_missing_from_points_raises_naming_the_id(self):
        with self.assertRaisesRegex(ValueError, "9"):
            Problem([StopNeed(9, 1)], [1, 2], table_rows(TINY), {})

    def test_make_plan_key(self):
        plan = make_plan(tiny_problem(), "R0", [1, 2], {1: 1, 2: 2})
        self.assertEqual((plan.method, plan.key), ("R0", (950.0, 0.0)))
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run from `research/`: `python -m unittest discover -s reroute/tests -t . -v`
Expected: errors, `No module named 'reroute'`.

- [ ] **Step 3: Implement `model.py` and `helpers.tiny_problem`**

`evaluate` walks the visit list once. At each point: arrival is the previous departure plus the row entry; the wait target is the largest `ready_s` among stops boarding there; departure is `max(arrival, wait target) + stop_base_s + stop_per_student_s x students boarding`. The first leg uses `problem.row(problem.start)`. With an empty visit list the arrival is the start row's campus entry.

- [ ] **Step 4: Run the tests and confirm they pass**

Same command. Expected: 15 tests, OK.

- [ ] **Step 5: Add the README lines and commit**

```bash
git add research/reroute research/README.md
git commit -m "Research: rerouting solver model and scoring function"
```

---

### Task 2: Servable stops and R0, the patched published route

**Files:**
- Create: `research/reroute/ladder.py`
- Test: `research/reroute/tests/test_r0.py`

**Interfaces:**
- Consumes: everything Task 1 produces.
- Produces:
  - `servable(problem) -> tuple[list[StopNeed], list[int]]`: the stops that have at least one reachable point they can board at, and the ids of those that have none. A point is reachable when the start row's entry for it is finite.
  - `insert_cheapest(problem, order: list[int], point_id: int) -> list[int]`: a new order with the point inserted where it adds the least driving time, counting the legs from the start and to campus. Ties go to the earliest position.
  - `solve_r0(problem) -> Plan`, method `"R0"`. Visits every servable stop that is itself reachable, in published order. A servable stop whose own point is unreachable boards at the reachable point in range with the least walking (ties: lowest id); if that point is not already visited it is inserted with `insert_cheapest`. Committed points not already visited are inserted with `insert_cheapest`, in ascending id order. Unservable stops go in `unserved`.

- [ ] **Step 1: Write the failing tests**

```python
import math, unittest
from reroute.ladder import servable, solve_r0, insert_cheapest
from reroute.model import StopNeed
from reroute.tests.helpers import tiny_problem, TINY

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
```

- [ ] **Step 2: Run and confirm failure** (`cannot import name 'solve_r0'`).

- [ ] **Step 3: Implement `servable`, `insert_cheapest`, `solve_r0` in `ladder.py`.** `solve_r0` builds its result with `make_plan`.

- [ ] **Step 4: Run and confirm all tests pass.**

- [ ] **Step 5: Commit**

```bash
git add research/reroute
git commit -m "Research: rerouting R0, the patched published route"
```

---

### Task 3: R2, the greedy method

**Files:**
- Modify: `research/reroute/ladder.py`
- Test: `research/reroute/tests/test_r2.py`
- Modify: `research/reroute/tests/helpers.py` (add `random_problem`)

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces:
  - `solve_r2(problem) -> Plan`, method `"R2"`.
  - In `helpers.py`: `random_problem(seed: int, n_stops: int, n_extra: int, limit_m: float = 400.0) -> Problem`. Uses `random.Random(seed)`. Places `n_stops + n_extra` points, the start and campus uniformly in a 2000 m x 2000 m square. Point ids are `1..n_stops + n_extra`; the first `n_stops` are the remaining stops in id order, each with 1 to 9 students. Travel time between two nodes is their straight-line distance in metres divided by 10, so the table satisfies the triangle inequality. `walk[(stop, point)]` is the straight-line distance in metres for every pair within 800 m.

**Algorithm, fixed here because the tests do not determine it:**

1. Start with the committed points, inserted with `insert_cheapest` in ascending id order. Every servable stop is unassigned.
2. While any stop is unassigned: for each reachable point not yet visited, its gain is the students of unassigned stops that can board there, and its cost is the driving time added by `insert_cheapest` plus `stop_base_s`. Take the point with the largest gain divided by cost (ties: lowest id); skip points with zero gain. Insert it and assign those stops to it. Count a stop with zero students as one student in the gain so it is not ignored.
3. Removal pass: for each visited point that is not committed, in visit order, try removing it and reassigning each of its stops to the visited point in range with the least walking. If every stop can be reassigned and the plan's `key` is lower, keep the removal. Repeat the pass until one full pass changes nothing.
4. Reassign every stop to the visited point in range with the least walking, then keep that assignment only if it does not make `key` worse.
5. If `solve_r0(problem).arrival_s` is lower than the result's `arrival_s`, return R0's visit order and boarding choices under method `"R2"`.

- [ ] **Step 1: Write the failing tests**

```python
import unittest
from reroute.ladder import solve_r0, solve_r2
from reroute.model import StopNeed, evaluate
from reroute.tests.helpers import tiny_problem, random_problem

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
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `random_problem` and `solve_r2` as specified above.**
- [ ] **Step 4: Run and confirm all tests pass.**
- [ ] **Step 5: Commit** with message `Research: rerouting R2, the greedy method`.

---

### Task 4: R3, the exact method, and the lower bound

**Files:**
- Modify: `research/reroute/ladder.py`, `research/requirements.txt` (add a line `numpy`)
- Test: `research/reroute/tests/test_r3.py`
- Modify: `research/reroute/tests/helpers.py` (add `brute_force`)

**Interfaces:**
- Consumes: Tasks 1 to 3.
- Produces:
  - `MAX_EXACT_BITS = 16`.
  - `R3State`: a class holding the search tables, with `next_mask: int`, `done: bool`, `to_json() -> dict` and `R3State.from_json(d: dict) -> R3State`. The dictionary holds only JSON types; arrays are stored as base64 strings of their bytes with their shape and dtype.
  - `r3_start(problem) -> R3State`. Raises `ValueError("too many stops for the exact method")` when servable stops plus committed points exceed `MAX_EXACT_BITS`. Fetches every row with one `problem.fetch` call.
  - `r3_advance(problem, state: R3State, max_masks: int | None = None, deadline: float | None = None) -> R3State`: processes masks in increasing order from `state.next_mask`, stopping after `max_masks` masks or when `time.perf_counter()` passes `deadline`, whichever comes first. Returns the same state object, updated.
  - `r3_plan(problem, state: R3State) -> Plan`, method `"R3"`. Requires `state.done`.
  - `solve_r3(problem) -> Plan`: `r3_start`, `r3_advance` to the end, `r3_plan`.
  - `lower_bound(problem) -> float`: start-to-campus time, plus `stop_base_s` x `ceil(servable stops / largest number of servable stops any one reachable point can board)`, plus `stop_per_student_s` x students at servable stops. Returns the start-to-campus time when there are no servable stops.
  - In `helpers.py`: `brute_force(problem) -> float`: the smallest arrival over every subset of reachable points, every order of that subset, and every choice of boarding point for every stop, using `evaluate`; `InvalidPlan` results are skipped. Stops that are unservable are passed as `unserved`.

**Algorithm, fixed here because the tests do not determine it:**

- **Bits.** One bit per servable stop, then one bit per committed point. A committed point's bit can be set only at that point; it has zero students and is ready at time zero.
- **State.** `value[mask, v]` is the earliest time the bus can leave point `v` having boarded exactly the stops in `mask`. Parent pointers `(previous mask, previous point)` are kept for rebuilding the plan.
- **Per mask**, with numpy: `arrive[v] = min over u of (value[mask, u] + drive[u, v])`; for the empty mask `arrive` is the start row. Then for each point `v` with a finite `arrive[v]`: list the bits not in `mask` that can board at `v`, sorted by ready time; for each non-empty prefix `S` of that list, `leave = max(arrive[v], ready of the last bit in S) + stop_base_s + stop_per_student_s x students in S`, and update `value[mask | S, v]` if `leave` is lower. Only prefixes are tried: adding a stop that is already ready never delays the bus, so a larger set at the same leaving time is never worse.
- **Finish.** The answer is the smallest `value[full, v] + drive[v, campus]`. With no bits, the plan is the empty visit list.
- **Rebuild.** Follow the parent pointers. The search does not track visited points, so a point can appear twice in the path. Merge every repeat into its last occurrence (all its stops board at the later visit), then call `make_plan`. On a table that satisfies the triangle inequality the merged plan arrives no later than the search's value.
- **Guard.** If the rebuilt plan arrives later than `solve_r2(problem)`, return R2's visit order and boarding choices under method `"R3"`. This can only happen on tables that break the triangle inequality.
- The walking tie-break applies only between entries with equal `leave` time. The method guarantees the earliest arrival; it does not guarantee the least walking among all plans with that arrival.

- [ ] **Step 1: Write the failing tests**

```python
import json, math, unittest
from reroute.ladder import (solve_r0, solve_r2, solve_r3, r3_start, r3_advance, r3_plan,
                            R3State, lower_bound, MAX_EXACT_BITS)
from reroute.model import StopNeed, evaluate
from reroute.tests.helpers import tiny_problem, random_problem, brute_force

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
```

The third test rebuilds a `Problem` with changed stops; `Problem` must therefore keep its constructor arguments as `_rows` and `_walk`. Add those two attributes in `model.py` in this task.

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `brute_force`, then R3 and `lower_bound` as specified above.**
- [ ] **Step 4: Run and confirm all tests pass.** The whole suite must finish in under 90 s on a laptop; if `brute_force` is slower, restrict each stop's boarding choices to visited points it can board at before enumerating.
- [ ] **Step 5: Record one timing in the commit message.** Run this from `research/` and note the number:

```bash
python -c "import time; from reroute.tests.helpers import random_problem; from reroute.ladder import solve_r3; p=random_problem(1,13,17); t=time.process_time(); solve_r3(p); print(round(time.process_time()-t,2),'CPU-s for 13 stops, 30 points')"
```

No pass or fail: the decision-time experiment judges this under limits. If it is above 2 CPU-seconds, say so in the commit message so the next task owner knows the per-point loop needs vectorising across masks.

- [ ] **Step 6: Commit** with message `Research: rerouting R3, the exact method (N CPU-s for 13 stops, 30 points)`.

---

### Task 5: The ladder

**Files:**
- Modify: `research/reroute/ladder.py`, `research/reroute/__init__.py`
- Test: `research/reroute/tests/test_ladder.py`

**Interfaces:**
- Consumes: Tasks 1 to 4.
- Produces:
  - `Ladder(problem)`. Attributes: `best: Plan | None`, `done: bool`, `stage: str` (one of `"R0"`, `"R2"`, `"R3"`, `"done"`; the next thing to run), `bound: float | None` (set to `lower_bound(problem)` when R3 is skipped for size, else `None`).
  - `Ladder.step(max_masks: int | None = None, deadline: float | None = None) -> Plan`: runs the next piece of work and returns `best`. First call runs R0 in full. Second runs R2 in full. Later calls advance R3 by a slice; when R3 finishes, or is skipped because the problem is too large, `done` becomes true. `best` is replaced only by a plan with a lower `key`, and never by one with more unserved stops.
  - `Ladder.run(deadline: float | None = None) -> Plan`: calls `step` until `done` or the deadline passes. Always completes R0 even if the deadline has already passed.
  - `Ladder.to_json() -> dict` and `Ladder.from_json(problem, d: dict) -> Ladder`: JSON types only; includes the stage, the best plan and the R3 state when one exists.
  - `reroute/__init__.py` re-exports: `StopNeed`, `Params`, `Problem`, `Plan`, `InvalidPlan`, `table_rows`, `evaluate`, `Ladder`, `solve_r0`, `solve_r2`, `solve_r3`, `lower_bound`.

- [ ] **Step 1: Write the failing tests**

```python
import json, time, unittest
from reroute import Ladder, solve_r0, solve_r3
from reroute.ladder import MAX_EXACT_BITS
from reroute.tests.helpers import tiny_problem, random_problem

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
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `Ladder`.**
- [ ] **Step 4: Run and confirm all tests pass.**
- [ ] **Step 5: Commit** with message `Research: rerouting ladder with a resumable solve`.

---

### Task 6: Request and proposal formats

**Files:**
- Create: `research/reroute/wire.py`
- Modify: `research/reroute/__init__.py` (re-export `parse_request`, `to_proposal`, `failed_proposal`, `RequestError`)
- Test: `research/reroute/tests/test_wire.py`

**Interfaces:**
- Consumes: Tasks 1 to 5.
- Produces:
  - `SCHEMA = 1`.
  - `RequestError(ValueError)`.
  - `parse_request(request: dict, rows: Callable, walk: Mapping[tuple[int, int], float]) -> Problem`. The request has the shape in Section 6.3 of the spec. Points are the `remaining` stops in order followed by `candidates` not already among them; ids are `stop_id`. Raises `RequestError` with the field name in the message when: `schema` is not 1; a required field (`schema`, `now`, `remaining`, `candidates`, `closures`, `campus`, `position`) is missing; a `stop_id` repeats within `remaining`; `students` is negative; `walk_limit_m` is outside 0 to 800; a `committed` id is in neither list; `now` has no UTC offset. `must_serve` defaults to false and `walk_limit_m` to 400. `closures` and coordinates are checked for presence only: turning them into travel times is the caller's job, through `rows`.
  - `to_proposal(request: dict, plan: Plan, compute_s: float, baseline_arrival_s: float | None = None, revision: int = 1, state: dict | None = None) -> dict`. Keys: `schema`, `status`, `reason`, `revision`, `method`, `visit`, `stops`, `arrival`, `delay_s`, `students_walking`, `compute_s`, `state`.
    - `stops` has one entry per remaining stop, in request order: `{"stop_id", "action", "board_at", "walk_m"}` with `action` one of `"keep"` (boards at itself), `"walk"`, `"unserved"`. `board_at` is `None` and `walk_m` is 0 for `unserved`; `walk_m` is the metres one student walks, rounded to a whole number.
    - `status` is `"failed"` with reason `"campus unreachable"` when the arrival is infinite; `"no_change"` with reason `"published order is already best"` when `visit` equals the remaining stop ids in order and no stop walks or is unserved; otherwise `"reroute"` with reason `None`.
    - `arrival` is `now` plus `arrival_s` rounded to a whole second, as an ISO 8601 string with the same offset as `now`; `None` when failed.
    - `delay_s` is `round(arrival_s - baseline_arrival_s)`, or `None` when no baseline is given or the status is failed.
    - `students_walking` is the students at stops with action `"walk"`.
  - `failed_proposal(reason: str, revision: int = 1) -> dict`: the same keys, `status` `"failed"`, empty `visit` and `stops`, the rest `None` or 0.

- [ ] **Step 1: Write the failing tests**

```python
import json, math, unittest
from reroute import Ladder, parse_request, to_proposal, failed_proposal, RequestError, table_rows
from reroute.tests.helpers import TINY

def request(**changes):
    r = {"schema": 1, "graph": "karachi_v1",
         "trip": {"assignment_id": 41, "service_date": "2026-12-01", "direction": "morning"},
         "now": "2026-12-01T07:05:00+05:00", "deadline_s": 5,
         "position": {"lat": 24.91, "lng": 67.08},
         "remaining": [{"stop_id": 1, "route_stop_id": 901, "name": "A", "lat": 24.92, "lng": 67.09, "students": 4},
                       {"stop_id": 2, "route_stop_id": 902, "name": "B", "lat": 24.93, "lng": 67.10, "students": 2}],
         "candidates": [], "committed": [],
         "closures": [{"id": "incident-55", "circle": {"lat": 24.9, "lng": 67.09, "radius_m": 200}, "factor": 0.0}],
         "campus": {"lat": 24.856899, "lng": 67.264684}, "based_on": None}
    r.update(changes); return r

WALK = {(2, 1): 240.0}

class WireTests(unittest.TestCase):
    def solve(self, req, matrix=TINY):
        problem = parse_request(req, table_rows(matrix), WALK)
        return to_proposal(req, Ladder(problem).run(), compute_s=0.01, baseline_arrival_s=900.0)

    def test_reroute_proposal(self):
        out = self.solve(request())
        self.assertEqual((out["status"], out["visit"], out["delay_s"], out["students_walking"]),
                         ("reroute", [1], 40, 2))
        self.assertEqual(out["arrival"], "2026-12-01T07:20:40+05:00")
        self.assertEqual(out["stops"], [{"stop_id": 1, "action": "keep", "board_at": 1, "walk_m": 0},
                                        {"stop_id": 2, "action": "walk", "board_at": 1, "walk_m": 240}])
        json.dumps(out)

    def test_no_change_when_every_stop_must_be_served(self):
        req = request()
        for s in req["remaining"]:
            s["must_serve"] = True
        out = self.solve(req)
        self.assertEqual((out["status"], out["reason"], out["visit"]),
                         ("no_change", "published order is already best", [1, 2]))

    def test_campus_unreachable_is_failed(self):
        m = [row[:] for row in TINY]
        for i in range(3):
            m[i][3] = math.inf
        out = self.solve(request(), m)
        self.assertEqual((out["status"], out["reason"], out["arrival"], out["delay_s"]),
                         ("failed", "campus unreachable", None, None))

    def test_bad_requests_name_the_field(self):
        bad = {"schema": request(schema=2), "now": request(now="2026-12-01T07:05:00"),
               "committed": request(committed=[99])}
        r = request(); r["remaining"][1]["stop_id"] = 1; bad["stop_id"] = r
        r = request(); r["remaining"][0]["students"] = -1; bad["students"] = r
        r = request(); r["remaining"][0]["walk_limit_m"] = 900; bad["walk_limit_m"] = r
        r = request(); del r["closures"]; bad["closures"] = r
        for field, req in bad.items():
            with self.assertRaisesRegex(RequestError, field):
                parse_request(req, table_rows(TINY), WALK)

    def test_failed_proposal_shape(self):
        out = failed_proposal("no travel times")
        self.assertEqual((out["status"], out["reason"], out["visit"], out["stops"]),
                         ("failed", "no travel times", [], []))
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `wire.py`.**
- [ ] **Step 4: Run the whole suite and confirm it passes.**
- [ ] **Step 5: Commit** with message `Research: rerouting request and proposal formats`.

---

## After this plan

- The road graph (`build_graph.py`, `graph.py`, `closure.py`) and the experiment runner (`run_reroute.py`) have their own plans. Both use only what `reroute/__init__.py` exports.
- Vectorising R3's per-point loop across masks is a follow-up if Task 4's timing is above 2 CPU-seconds.
