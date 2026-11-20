# Research progress tracker

Last updated: **20 November 2026**. Deadline for the rerouting work: **Sunday 6 December 2026**.

**How to use this file.** Tick a box when the task's "done when" in its plan is met and the work is
committed. Add the date and initials after the tick. Update the "Last updated" line. Record every cut
and every change of plan in the last two sections. The logbook stays the source of truth for results;
this file only tracks work.

Status words: **done**, **in progress**, **not started**, **blocked** (say on what), **cut**.

A task whose code is done but whose "done when" needs a real run on the Karachi map or OSRM is marked
**code done; run blocked (needs Docker laptop and map file)**. Nothing has been measured on the map or
on OSRM yet. Section 7 lists those runs in order.

## 1. Summary

| Part | Status |
| --- | --- |
| Optimization: experiments | done (B1, Q1, T1, S1 all passed and are logged) |
| Optimization: chapter | draft committed; references, figures and the Nadeem bus-count point still open |
| Optimization: scaling run | done: run OS1 complete, 12 of 12 runs. Jadoon, Nadeem and their doubled instances on the Windows laptop (17 Nov, `results/optimizer-scale/`); All and All-doubled in WSL on 19 Nov (code `975760c`, `results/optimizer-scale-wsl/`); the two machines' rows are not pooled |
| Rerouting: planning | done (work plan version 2 approved; six implementation plans written) |
| Rerouting: code | done: solver, road graph, offline builders, runner and optimizer scaling, with unit tests (221 in `reroute/tests`, 237 in `tests`, all passing); commits `54a55f2` and `7299036`; R2 improvement rounds added after RS1's first run (`723f4c8`) |
| Rerouting: data (graph, walking distances, scenarios) | in progress: on 19 Nov, in WSL on the N1 laptop: map file and OSRM checked (A1), graph built (L2), road-block test (L3), calibration, corridors and G1 timings (L5), walking distances (L4); gate G1 met. Historical closures pinned, combined matrix built, scenarios frozen (L6, 20 Nov). Next: the quality pass |
| Rerouting: experiments | quality pass done 20 Nov (L8): R2 matches R3 (pass), no violations (pass), walking gains a median 0 s net of the no-closure control (fail; a valid result, work plan Section 11). RS1 "stops" without limits done 17 Nov. Limits pass done 20 Nov (L9): valid plan within 5 s in 94.9% (fail by one scenario), within 60 s of the oracle at 30 s in 92.3% (pass), peak 209 MB (pass). RS1 complete 20 Nov (L10, `results/reroute-scale-wsl/`): R2 within 4.4 s at 20 stops, R3 within 30 s up to 12 stops, 20 buses at once peak 426 MB. All rerouting experiments done |
| Rerouting: chapter | draft committed (`9132c3d`) from the plans and rules; updated 17 Nov (not yet committed) with the R2 change and the RS1 "stops" results; OS1 is in the optimization chapter (Section 7.6). Other results marked pending until each run is logged |
| Website integration | design only (work plan Section 12); nothing to build before 6 December. `reroute.wire` is the request and proposal contract |

## 2. Done

### Optimization (FYP-1, part 1)

- [x] Frozen dataset `fall2026-v1` (run D1, 3 Nov)
- [x] Karachi OSRM build and travel-time matrices (runs N1, M1, 3 Nov)
- [x] Optimizer `optimize.py` (3 Nov)
- [x] Research hub and shared page (4 Nov)
- [x] Time-budget experiment B1: pass (logged 9 Nov)
- [x] Query-budget experiment Q1: pass (logged 9 Nov)
- [x] Traffic check T1 and seed check S1: pass (run 10 Nov, logged 15 Nov)
- [x] Hub plan updated for the finished checks (15 Nov)
- [x] Optimization chapter draft, `report/optimization_chapter.md` (committed 15 Nov, `fa8e027`)

### Rerouting (FYP-1, part 2): planning

- [x] Research question confirmed by the supervisor (10 Nov)
- [x] Work plan version 2, reviewed by four reviewers and approved (15 Nov): `2026-11-15-rerouting-plan.md`
- [x] Implementation plans written (16 Nov):
  - `2026-11-16-reroute-solver-core.md`
  - `2026-11-16-road-graph.md`
  - `2026-11-16-offline-builders.md`
  - `2026-11-16-experiment-runner.md`
  - `2026-11-16-optimizer-scaling.md`
  - `2026-11-16-logbook-and-chapter.md`

### Rerouting (FYP-1, part 2): code (17 Nov)

Each module was checked by an independent reviewer; every bug found was first shown by a failing test,
then fixed.

- [x] Solver core, Tasks 1 to 6: `reroute/model.py`, `ladder.py`, `wire.py` (17 Nov, `54a55f2`)
- [x] Road graph code, Tasks 1 to 8: `reroute/roadnet.py`, `closure.py`, `graph.py`; `build_graph.py`,
  `build_corridors.py`, `calibrate_graph.py`, `measure_graph.py` (17 Nov, `54a55f2`). `build_graph.py` was
  tested through pyosmium on a hand-written `.osm` file, not on the Karachi map
- [x] Offline builders code, Tasks 1 to 7: `osrm_tools.py`, `run_roadblock.py`, `build_walk.py`,
  `scenario_rules.py`, `data/raw/historical_closures.json` (coordinates null), `build_scenarios.py`,
  `build_matrix.py --combined` (17 Nov, `54a55f2`). Tested against a fake OSRM, not a real one
- [x] Experiment runner code, Tasks 1 to 6: `reroute_cases.py`, `run_reroute.py`, `data/scenarios_toy.json`,
  hub entries and their `-quick` variants, `build_site.py` summary branch (17 Nov, `54a55f2`, `7299036`).
  The quick tests of Tasks 3 to 6 pass without limits (logged 17 Nov; rerun on `c1a9f8a`)
- [x] R2 improved after RS1's first run: reorder, remove, nearest point, add and swap rounds until nothing
  changes, with tests that no single move improves the final plan (17 Nov, `723f4c8`; Section 5)
- [x] Optimizer scaling code, Tasks 1 to 3: `optimize.py` `lookup="callback"|"matrix"` and `timings=True`,
  portable peak memory, `scale_instances.py`, `run_scale.py`, hub entry `optimizer-scale` (17 Nov, `54a55f2`)
- [x] Logbook entry planning OS1 and RS1 "stops" (17 Nov, `c4c13f5`, committed, not pushed); limits verdict
  rules (17 Nov, `7299036`); entry on the rules settled during the build, with the README, hub plan, this
  tracker and the rerouting chapter draft (17 Nov, `9132c3d`)

### Rerouting and optimizer: first results (17 Nov, lead's Windows laptop, no limits)

- [x] Quick pipeline tests: quality, limits without limits, rerouting scale and `run_scale.py --quick`, all ok
  (code `7299036`, logged in `c1a9f8a`; rerun on code `c1a9f8a`, logged in `e59d26f`)
- [x] Run OS1, contractor part: Jadoon, Nadeem, Jadoon-doubled, Nadeem-doubled x callback and matrix, 300 s
  each, 8 of 12 runs (code `7299036`, logged 17 Nov in `c1a9f8a`, `results/optimizer-scale/`). The callback lookup stays the
  default. Left: All and All-doubled on the Docker laptop (Section 7, item 9)
- [x] Run RS1 part "stops" without limits, first run with the greedy-only R2 (code `7299036`, logged 17 Nov in `c1a9f8a`,
  `results/reroute-scale-r2-insertion/`). It showed R2 far from R3, which led to the R2 change
- [x] Run RS1 part "stops" without limits, rerun with the improved R2 (code `c1a9f8a`, logged 17 Nov in `e59d26f`,
  `results/reroute-scale/`). Left: the limited "stops" rows and the graph, buses and slices parts in WSL
  (Section 7, item 12)

## 3. Left to do

Tracks: **A** = the person with the Docker laptop, **B** = road graph, **C** = rules, solver, runner.
Names are not assigned yet.

### Day one (Mon 16 Nov)

- [ ] Assign tracks A, B, C to people, and name the Docker laptop
- [x] Commit this `plans/` folder (16 Nov, `e84e06a`)
- [x] Add the hub warning when git is missing, so no run is recorded with code version `unknown`: the hub
  now refuses to start a run (17 Nov)
- [x] Remove `run_query.py` and the `--k` option in `optimize.py` (17 Nov)
- [x] Correct "the optimizer is not built yet" in the root `CLAUDE.md` (17 Nov)

### Week 1, 16 to 22 Nov. Gate G1 on Sun 22 Nov

| Done | Track | Task | Plan and task | Due |
| --- | --- | --- | --- | --- |
| [ ] written and committed (`50ab71b`); push pending | C | Logbook entry L1 (problem, rules, thresholds) pushed | logbook-and-chapter, L1 | Tue 17 |
| [x] (19 Nov) | A | Map file from run N1 found, SHA-256 logged; Docker runs OSRM | work plan A1 | Tue 17 |
| [x] (19 Nov) | A | OSRM helper (the hand check in Step 5) | offline-builders, Task 1 | Tue 17 |
| [x] (17 Nov) | B | Road tables from map ways | road-graph, Task 1 | Tue 17 |
| [ ] built and logged (19 Nov; rebuilt with the snapping rule, Section 5); commit pending | B | Graph built from the map file and committed | road-graph, Task 2 | Wed 18 |
| [x] (17 Nov) | C | Solver model and scoring | solver-core, Task 1 | Wed 18 |
| [x] (17 Nov) | C | R0 | solver-core, Task 2 | Wed 18 |
| [ ] run and logged (19 Nov); commit pending | A | Road-block test run and logged (L3) | offline-builders, Task 2 | Fri 20 |
| [x] (17 Nov) | B | Closures matched by geometry | road-graph, Task 3 | Thu 19 |
| [x] (17 Nov) | C | R2 | solver-core, Task 3 | Thu 19 |
| [x] (17 Nov) | B | Graph search, corridors, row cache | road-graph, Task 4 | Fri 20 |
| [ ] built and logged (19 Nov, L5); commit pending | B | Corridors for the 52 routes | road-graph, Task 5 | Fri 20 |
| [x] (19 Nov, L5): factor 1.2493, 8.05% | B | Calibration against matrix M1, logged | road-graph, Task 6 | Fri 20 |
| [x] (17 Nov) | C | R3 and the lower bound | solver-core, Task 4 | Sat 21 |
| [x] (19 Nov, L4): detour 1.38; 17.2% / 48.0% within 400 / 800 m | A | Walking distances built and logged (L4) | offline-builders, Task 3 | Sun 22 |
| [x] (17 Nov) | A | Scenario placement rules | offline-builders, Task 4 | Sun 22 |
| [x] (19 Nov): checked by Hassan; 4,863 m and 3,142 m | A | Historical closure end points pinned on the map | offline-builders, Task 5 | Sun 22 |
| [x] (19 Nov, L5): limited, 14 rows 1.21 s, 31 rows 2.30 s | B | Timings under limits, logged (L5) | road-graph, Task 7 | Sun 22 |
| [x] (17 Nov) | C | Ladder with resumable solve | solver-core, Task 5 | Sun 22 |
| [ ] drafted (`9132c3d`), R2 change added 17 Nov (not yet committed); not yet reviewed | C | Chapter sections 1, 2, 3, 7 | logbook-and-chapter | Sun 22 |

**Gate G1 (Sun 22 Nov).** All five must be true, or follow the work plan's Section 11:

- [x] Road-block answers logged (19 Nov): speed 0 blocks; a point on a closed road is not moved (OSRM
  reports no route); customize 6.7 s, server start 1.8 s
- [x] Walking file built (19 Nov, L4): 700 pairs, detour factor 1.38; committed with the L4 entry
- [x] Graph calibration passes (19 Nov): median absolute error 8.05%, signed +3.05%
- [x] On the corridor under limits (19 Nov): 14 rows in 1.21 s, 31 rows in 2.30 s (worst repeat)
- [x] R3 matches brute force in the tests (17 Nov): exact on 800 of 800 random problems

### Week 2, 23 to 29 Nov. Scenarios frozen Thu 26; quick tests pass Fri 27

| Done | Track | Task | Plan and task | Due |
| --- | --- | --- | --- | --- |
| [x] (17 Nov) | C | Request and proposal formats | solver-core, Task 6 | Mon 23 |
| [x] (19 Nov): Jadoon R-10 checked by eye | A | Scenario build, one route checked by eye | offline-builders, Task 6 steps 1 to 2 | Tue 24 |
| [x] (17 Nov) | C | Scenario cases and scoring on true times | experiment-runner, Task 1 | Tue 24 |
| [x] (17 Nov) | C | Summaries and verdict rules | experiment-runner, Task 2 | Wed 25 |
| [x] (20 Nov, L6): 135 closures, 247 scenarios, 0 leaks | A | Full scenario build; no leaks; file frozen and logged (L6) | offline-builders, Task 6 steps 3 to 5 | Thu 26 |
| [x] (19 Nov): 0 of 50,320 pairs differ from M1 | A | Combined 311-stop matrix | offline-builders, Task 7 | Thu 26 |
| [x] (17 Nov, `c1a9f8a`): `quality --quick` 15 of 15 rows ok, toy verdicts pass | C | Quality pass and toy file | experiment-runner, Task 3 | Thu 26 |
| [ ] code done; quick test passes without limits (17 Nov, `c1a9f8a`); `run_budget.py --check` and the limited quick test need WSL with systemd | C | Limits pass | experiment-runner, Task 4 | Fri 27 |
| [ ] code done; quick tests pass on the lead's laptop (17 Nov); still to do from the hub on the run machine, and the limited quick test needs WSL with systemd | C | Hub entries; both quick tests pass from the hub on the run machine | experiment-runner, Task 6 | Fri 27 |
| [x] (17 Nov) | B | Reuse of pre-closure rows (first in the cut order) | road-graph, Task 8 | Fri 27 |
| [x] (17 Nov) | B | Optimizer matrix lookup | optimizer-scaling, Task 1 | Fri 27 |
| [x] (20 Nov, L8): thresholds 2 and 3 pass, threshold 1 fails (median net gain 0 s) | all | Quality pass run and logged the same day (L8) | experiment-runner, Task 7 | Sun 29 |
| [ ] section 6 drafted (`9132c3d`; R2 and RS1 timings updated 17 Nov, not yet committed); sections 4 and 5 drafted with results pending entries L2 to L6 | all | Chapter sections 4, 5, 6 | logbook-and-chapter | Sun 29 |

### Week 3, 30 Nov to 6 Dec. Run freeze Wed 2; draft Fri 4; done Sun 6

| Done | Track | Task | Plan and task | Due |
| --- | --- | --- | --- | --- |
| [x] (17 Nov): `scale --quick` 4 of 4 ok; part "stops" run without limits | C | Scaling runs coded | experiment-runner, Task 5 | Mon 30 |
| [ ] code done, entry L7 committed (`c4c13f5`, committed minutes before OS1 started) and quick test ok (17 Nov, 2 of 2); the plan asks for L7 pushed before the run, but it was only committed: push pending | B | Optimizer instances and scaling script; entry L7 pushed | optimizer-scaling, Tasks 2 to 3 | Mon 30 |
| [x] (20 Nov, L9): thresholds 5 and 6 pass; threshold 4 fails by one scenario (74 of 78) | all | Limits pass run and logged the same day (L9) | experiment-runner, Task 7 | Tue 1 |
| [x] (20 Nov): OS1 complete (L7 of 19 Nov, All and All-doubled); RS1 complete (L10, all parts in WSL) | all | Rerouting and optimizer scaling runs, logged the same day (L10) | experiment-runner Task 7; optimizer-scaling Task 3 | Wed 2 |
| [ ] | all | **Run freeze**: no new runs after Wed 2 Dec | - | Wed 2 |
| [ ] | all | Chapter sections 8, 9, 10; references checked | logbook-and-chapter | Fri 4 |
| [ ] | all | Internal review of the chapter by a second person | logbook-and-chapter | Fri 4 |
| [ ] | all | Hub plan (`hub/project.json`) and this tracker brought up to date; everything published | - | Sun 6 |

### Still open from the optimization chapter

- [ ] References re-opened and checked (two were cited from memory: the guided local search and granular tabu search papers)
- [ ] Three figures exported from the hub and embedded
- [ ] Decide whether to run Nadeem held to 25 buses (the optimized plans use 26)
- [x] (20 Nov) Decide whether the proposal needs a formal revision: no, the team is not following the proposal closely

## 4. Decisions needed

| Decision | Needed by | Status |
| --- | --- | --- |
| Who is on tracks A, B and C; which laptop has Docker | Mon 16 Nov | open |
| Thresholds, walking speed and start lag in entry L1 | Tue 17 Nov | taken (17 Nov): the proposed values. Walkers start 60 s after the decision at 1.2 m/s; gain at least 60 s; R2 within 60 s of R3 in at least 90%; a valid plan within 5 s in at least 95%; within 60 s of the oracle at 30 s in at least 90%; memory under 400 MB |
| Proposal revision: rerouting is listed there as out of scope | before the chapter is submitted | taken (20 Nov): no revision; the team is not following the proposal closely |
| Limits on automatic reroutes on the website (work plan Section 12.2) | before any website build | open |
| R3 is two-phase, not the plan's single search (Section 5) | before the quality pass | taken by the lead (17 Nov); team to confirm |
| Meaning of "infeasible": R0 on true post-closure times never reaches campus or serves no stop, or the baseline is unreachable. `ok` and `infeasible` are counted results; every other status is a failure | before the quality pass | taken by the lead (17 Nov); team to confirm |
| Threshold 4 ("valid plan within 5 s") means the plan held at 5 s is valid on true times; a graph plan that leaves a truly servable stop unserved is `invalid_on_truth` | before the limits pass | taken by the lead (17 Nov, `7299036`); team to confirm |
| Threshold 6 (memory) is judged on every `graph_limited` row, since memory is per process | before the limits pass | taken by the lead (17 Nov, `7299036`); team to confirm |
| Quality pass: the worst route is the one with the largest median R2 minus R3; an unserved stop with a boarding point in range is a violation of rule 3 | before the quality pass | taken by the lead (17 Nov); team to confirm |
| Doubled contractor instances stand in for All and All-doubled until the combined matrix exists | before OS1 is logged | taken by the lead (17 Nov, `c4c13f5`); team to confirm |
| Whether the OS1 rows from the lead's laptop (no WSL, Windows peak memory) are reported beside the All rows from the Docker laptop, or the contractor instances are rerun there | before L10 | taken (17 Nov, logbook rules entry, `9132c3d`): rows from the two machines are never pooled. Runs on the Docker laptop write to their own folders with `--out-dir` (`results/optimizer-scale-wsl/`, `results/reroute-scale-wsl/`), and each result entry names its machine |
| R2 improves its greedy plan in rounds (reorder, remove, nearest point, add, swap); the L1 description of R2 is extended, thresholds unchanged | before the quality pass | taken by the lead (17 Nov, `723f4c8`), after RS1's first run and before any quality run; team to confirm |
| A proposal with status `failed` must not be acted on (it may still carry a plan for information); a committed point that becomes unreachable reports "campus unreachable" for now | before any website build | taken by the lead (17 Nov); team to confirm |

## 5. Changes made while writing the implementation plans

These differ from the wording of the work plan. Each is stated in the plan that makes it.

| Change | Where | Why |
| --- | --- | --- |
| A plain latitude and longitude grid indexes road segments; H3 is not used at run time | road-graph, Task 3 | Same job, one dependency fewer for the website |
| No single reverse search from campus | road-graph, Task 4 | Every row the solver asks for already includes the time to campus |
| A corridor that is cut falls back to the whole city graph once, not to a wider corridor | road-graph, Task 4 | Simpler; how often it happens is recorded |
| A point is unreachable when it lies inside a full-block circle | road-graph Task 3; offline-builders | One rule both travel-time sources can apply identically |
| The graph's speed factor is the 60th percentile of OSRM time over graph time | road-graph, Task 6 | So the graph runs slightly slow, never fast |
| "Stops per bus" scaling uses synthetic problems, not joined real routes | experiment-runner, Task 5 | Scenario tables hold no times between stops of different routes |
| The doubled optimizer instance copies each stop 30 s from its original | optimizer-scaling, Task 2 | Tests model size without needing new travel times |
| Historical closure end points are left for a person to pin on the map | offline-builders, Task 5 | Coordinates must not be guessed |
| The exact method guarantees the earliest arrival, not the least walking | solver-core, Task 4; work plan Section 13 | The bus can wait for walkers, so one pass cannot guarantee both |

### Changes made during implementation (17 Nov)

| Change | Where | Why |
| --- | --- | --- |
| R3 is two-phase. Phase 1 is a vectorised search over (mask, last point) that allows repeats; repeats are merged. If the merged plan misses the search value, phase 2 runs an exact label search over (mask, last point, visited points) with dominance and lower-bound pruning. Both phases are resumable (state in `R3State` JSON) | `reroute/ladder.py`; solver-core, Task 4 | The plan's single search was not exact on 34 of 800 random problems; the two-phase method matches brute force on 800 of 800. On the lead's laptop R3 takes about 7 CPU-s at 16 stops and 30 points; with 800 m limits the repair can take 16 to 32 CPU-s at 15 stops |
| R3 is not vectorised per layer (the wording of work plan item C2) | `reroute/ladder.py` | The ladder returns R0 and R2 at once, so the website always has a plan while R3 runs |
| `Plan` gained `stop_walk_m` and `to_json`/`from_json`; `r3_plan` and `r3_advance` take optional `fallback` and `upper_bound` | `reroute/model.py`, `ladder.py` | Needed to save and resume the solve and to seed it with R2 |
| Row cache holds at most 256 rows and at most 128 MiB | `reroute/graph.py` | City-wide rows are about 1.6 MB each, so a row count alone does not bound memory |
| A corridor's identity is its key plus a hash of its nodes and edges; `load_corridor` checks the graph version | `reroute/graph.py` | A cached row must never be used with a different corridor or graph |
| "Infeasible" defined: R0 on true post-closure times never reaches campus or serves no stop, or the baseline is unreachable. `ok` and `infeasible` are counted results; every other status is a failure | `run_reroute.py` | A closure that leaves no plan is a result, not a crash |
| A graph plan that leaves a truly servable stop unserved is `invalid_on_truth`; threshold 4 needs the plan held at 5 s to be valid on true times | `run_reroute.py` (`7299036`) | A plan that only looks valid on the graph must not count |
| Memory (threshold 6) is judged on every `graph_limited` row | `run_reroute.py` (`7299036`) | Memory is per process, so every limited worker counts |
| The `graph_unlimited` arm runs once per scenario, not three times | `run_reroute.py`, limits pass | It is deterministic and its timing is not judged |
| A worker killed for memory keeps the rows it finished; its unfinished scenarios get `killed_memory` | `run_reroute.py`, limits pass | A memory kill is a result and must show in the rows |
| No `limited` scaling rows are written without systemd limits | `run_reroute.py`, scale (`7299036`) | A row named limited must have run under the limits |
| Quality pass: the worst route is the one with the largest median R2 minus R3; an unserved stop with a boarding point in range is a rule 3 violation | `run_reroute.py`, quality pass | The plan did not define "worst route" or say how rule 3 is checked |
| `circles_along` keeps the plan's n = max(2, round(L/100) + 1) | `scenario_rules.py` | Gaps occur only on stretches of 121 to 149 m and 241 to 249 m; real stretches are kilometres long |
| The leak check counts route vertices inside circles only | `scenario_rules.py` | Limitation: a long straight segment could cross a circle unseen |
| A historical stretch met on the last-stop-to-campus leg gets only the early trigger; a campus inside a closure is warned | `build_scenarios.py` | There is no later stop to trigger at |
| `run_roadblock.py` answers 0 or 1 km/h as the block speed; `build_scenarios.py --block-kmh` follows it | `run_roadblock.py`, `build_scenarios.py` | The road-block test decides the speed, as the plan intends |
| The doubled contractor instances (Jadoon-doubled, Nadeem-doubled) stand in for All and All-doubled until the combined matrix exists | `run_scale.py`, OS1 (`c4c13f5`) | The combined matrix needs OSRM, which this machine cannot run |
| `build_s` is not comparable between lookups; `ride_Ns` at N = budget includes the plan found right at the limit | `run_scale.py` | The callback lookup computes arc costs lazily, inside the search |
| Points snap only to the main road network (the largest strongly connected part), at build time and in `Graph.nearest_node` (19 Nov) | `build_graph.py`, `reroute/graph.py` | Hyperstar and FTC had snapped onto a one-way parking aisle and a service-road piece with no way back, so two corridor legs had no path; OSRM avoids such pieces |
| A point is closed when the place OSRM meets the road (pre-closure snap) is inside a full block or on a segment the block closes (and on no open one), not by its raw coordinate; the graph arm takes `closed_points` from the scenario file (20 Nov) | `build_scenarios.py`, `osrm_tools.py`, `run_reroute.py` | 7 stops lay with their coordinate and road point on different sides of a circle; Race Course was silently re-snapped by OSRM, giving times faster than before the closure |
| The hub's `optimizer-scale` entry runs the four contractor instances only (8 runs); a new entry `optimizer-scale-wsl` shows All and All-doubled (20 Nov) | `hub/experiments.json` | Pressing Run on the old entry would have written All and All-doubled into the Windows laptop's folder, pooling the two machines' rows |
| The hub's `reroute-scale` entry runs the Windows laptop's part only (stops, no limits, 45 rows); a new entry `reroute-scale-wsl` shows the 109 WSL rows (20 Nov) | `hub/experiments.json` | As for the optimizer: pressing Run on the old entry would have written WSL rows into the Windows folder |
| Unreachable pairs (`None`) become 10**7 s arcs | `optimize.py` | The stop is dropped instead of crashing the solver |
| Quick result folders are published like the other `-quick` folders; per-job `work/` and `logs/` folders are gitignored | `research/results/`, `research/.gitignore` | Pipeline tests stay visible; intermediates stay out of git |
| The hub refuses to start a run when git cannot give the code version | `research/hub/serve.py` | No run is recorded with code version `unknown` |
| OS1 and RS1 "stops" ran from the command line, not from the hub as optimizer-scaling Task 3 Step 5 and experiment-runner Task 7 Step 3 say; each run's `meta.json` still records the code version | `run_scale.py`, `run_reroute.py` | The hub's Run buttons start the scripts in WSL, which the lead's laptop cannot start |
| Runs on the Docker laptop write to their own folders with `--out-dir`: `results/optimizer-scale-wsl/` and `results/reroute-scale-wsl/` | `run_scale.py`, `run_reroute.py`; logbook rules entry (`9132c3d`) | Rows from the Windows laptop (no limits, Windows peak working set) are never pooled with WSL rows |

### Changes made after the first results (17 Nov)

| Change | Where | Why |
| --- | --- | --- |
| R2 keeps its greedy construction and fallback to R0, then improves the plan in rounds until nothing changes: reorder (move one point or reverse a segment), remove points, move stops to their nearest visited point, then add the one point, or failing that swap the one pair, that lowers the arrival most. Tests check that no single one of these moves improves the final plan. The L1 description of R2 ("greedy, then try removals") is extended; the thresholds do not change | `reroute/ladder.py` (`723f4c8`); logbook entry of 17 Nov | RS1's first run (`results/reroute-scale-r2-insertion/`) put the greedy-only R2 a median 68 to 285 s behind R3 (the table's group medians; the entry's text says 70), against the 60 s threshold 2 asks for. The rerun (`results/reroute-scale/`) has R2 within 60 s of R3 on 30 of 36 synthetic problems, largest gap 108 s, at most 0.5 CPU-s. Threshold 2 is still judged only in the quality pass |

## 6. Cuts taken

None yet. The doubled contractor instances stand in for All and All-doubled in the optimizer scaling run
only until the combined matrix exists. That is not a cut: All and All-doubled still run on the Docker
laptop (Section 7). The order is in the work plan, Section 10:

1. Reuse of pre-closure rows
2. The doubled optimizer instance
3. The 800 m walking limit
4. The must-serve arm
5. The paused-solving scaling row
6. One closure per route in place of two

When a cut is taken: write it here with the date, and write logbook entry L11.

## 7. Blocked on this machine

The lead's laptop has no Docker, no OSRM, no Karachi `.osm.pbf` and cannot start WSL (virtualization is
off). **Update 19 Nov:** the N1 laptop runs WSL with Docker and systemd; items 1, 2, 3, 4 and 5 are done there (LOGBOOK, 2026-11-19, three entries); gate G1 is met. Items 6 to 9 done 19 and 20 Nov (historical closures, scenarios, combined matrix, OS1 All). Everything below needs the Docker laptop and the N1 map file; items 4, 11 and 12 also need WSL
with systemd. Results from that machine go to their own folders (`results/optimizer-scale-wsl/`,
`results/reroute-scale-wsl/`) and are never pooled with the Windows laptop's rows. Run in this order, from the repository root unless stated. Log each
result the same day.

1. **A1: map file and OSRM.** Find the map file from run N1 (the plans call it `karachi.osm.pbf` and expect
   it in `~/fleetcentric-osrm/`), log its SHA-256 (`sha256sum karachi.osm.pbf`),
   keep the untouched car build in `~/fleetcentric-osrm/car/`, then check the OSRM helper by hand from
   `research/`:
   `python -c "import osrm_tools as o, pathlib as p; h=p.Path.home()/'fleetcentric-osrm'; o.fresh_copy(h/'car', h/'work'); print(o.customize(h/'work', '')); o.start_server(h/'work'); print(o.table([(24.8607,67.0298),(24.8569,67.2647)])); o.stop_server()"`
2. **Road graph (L2).** `python research/build_graph.py ~/fleetcentric-osrm/karachi.osm.pbf`, then commit
   `data/graph_karachi_v1` and log the counts.
3. **Road-block test (L3).** `python research/run_roadblock.py`. Its answer (0 or 1 km/h) is the
   `--block-kmh` for item 7.
4. **Corridors, calibration and timings (L5).** `python research/build_corridors.py`;
   `python research/calibrate_graph.py` (again with `--per-class` if it fails); then in WSL, as road-graph
   Task 7 says, both modes: `python research/measure_graph.py --no-limits` and
   `python research/measure_graph.py --limited` (add `--sudo` if needed). This answers two G1 items.
5. **Walking distances (L4).** Build the foot profile in `~/fleetcentric-osrm/foot/` (the three `docker run`
   commands in offline-builders, Task 3, Step 1), then `python research/build_walk.py`.
6. **Historical closures.** A person pins the end points in `data/raw/historical_closures.json`, checks each
   stretch against the unblocked OSRM server on a map, and records `length_m`.
7. **Scenarios (L6).** `python research/build_scenarios.py --route Jadoon:R-10 --block-kmh <0 or 1>` and
   check by eye; then `python research/build_scenarios.py --block-kmh <0 or 1>` (`--resume` after a
   stop). Freeze the file and set `runs_total` for the main reroute hub entries.
8. **Combined matrix.** With the untouched car server on port 5000:
   `python research/build_matrix.py --combined` (set `OSRM_URL` if the server is elsewhere). It checks the
   Jadoon and Nadeem pairs against `matrix_fall2026_v1.json` unless `--no-check` is given.
9. **Optimizer All and All-doubled (OS1, L10).**
   `python research/run_scale.py --instances All,All-doubled --out-dir research/results/optimizer-scale-wsl`.
   Use the command, not the `optimizer-scale` hub entry: the hub writes to `results/optimizer-scale/`, which
   holds the Windows laptop's rows, and the two machines' rows are never pooled.
10. **Quality pass (L8).** `python research/run_reroute.py quality --workers 2`, or `reroute-quality` in the hub.
11. **Limits pass (L9).** In WSL, plugged in, nothing else running: `python research/run_budget.py --check`
    must print `OK`; then `python research/run_reroute.py limits` (add `--sudo` if needed), or
    `reroute-limits` in the hub. The limited quick test (`python research/run_reroute.py limits --quick`)
    also belongs here.
12. **Rerouting scaling, remaining parts (L10).** In WSL, each with `--out-dir research/results/reroute-scale-wsl`:
    `python research/run_reroute.py scale --only graph`, `--only buses`, `--only slices`, and `--only stops`
    for the limited rows. The unlimited "stops" rows from the lead's laptop are done and logged
    (`results/reroute-scale/`, 17 Nov) and are not pooled with these.
