# Research progress tracker

Last updated: **17 November 2026**. Deadline for the rerouting work: **Sunday 6 December 2026**.

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
| Optimization: scaling run | in progress: code done; planned entry committed (`c4c13f5`); run OS1 on Jadoon, Nadeem and their doubled instances is running on the lead's laptop, results pending; All and All-doubled blocked (need the combined matrix, so OSRM) |
| Rerouting: planning | done (work plan version 2 approved; six implementation plans written) |
| Rerouting: code | done: solver, road graph, offline builders, runner and optimizer scaling, with unit tests (217 in `reroute/tests`, 235 in `tests`, all passing); commits `54a55f2` and `7299036` |
| Rerouting: data (graph, walking distances, scenarios) | blocked: needs the Docker laptop and the N1 map file (Section 7) |
| Rerouting: experiments | quick pipeline tests are running and RS1 "stops" without limits is running or queued on the lead's laptop, results pending; quality, limits and the rest of scaling blocked on the data |
| Rerouting: chapter | not started |
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
  The quick tests of Tasks 3 to 6 are running, results pending (Section 3, Week 2)
- [x] Optimizer scaling code, Tasks 1 to 3: `optimize.py` `lookup="callback"|"matrix"` and `timings=True`,
  portable peak memory, `scale_instances.py`, `run_scale.py`, hub entry `optimizer-scale` (17 Nov, `54a55f2`)
- [x] Logbook entry planning OS1 and RS1 "stops" (17 Nov, `c4c13f5`, committed, not pushed); limits verdict
  rules (17 Nov, `7299036`)

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
| [ ] blocked (needs Docker laptop and map file) | A | Map file from run N1 found, SHA-256 logged; Docker runs OSRM | work plan A1 | Tue 17 |
| [ ] code done; run blocked (needs Docker laptop and map file) | A | OSRM helper (the hand check in Step 5) | offline-builders, Task 1 | Tue 17 |
| [x] (17 Nov) | B | Road tables from map ways | road-graph, Task 1 | Tue 17 |
| [ ] code done; run blocked (needs Docker laptop and map file) | B | Graph built from the map file and committed | road-graph, Task 2 | Wed 18 |
| [x] (17 Nov) | C | Solver model and scoring | solver-core, Task 1 | Wed 18 |
| [x] (17 Nov) | C | R0 | solver-core, Task 2 | Wed 18 |
| [ ] code done; run blocked (needs Docker laptop and map file) | A | Road-block test run and logged (L3) | offline-builders, Task 2 | Fri 20 |
| [x] (17 Nov) | B | Closures matched by geometry | road-graph, Task 3 | Thu 19 |
| [x] (17 Nov) | C | R2 | solver-core, Task 3 | Thu 19 |
| [x] (17 Nov) | B | Graph search, corridors, row cache | road-graph, Task 4 | Fri 20 |
| [ ] code done; run blocked (needs Docker laptop and map file) | B | Corridors for the 52 routes | road-graph, Task 5 | Fri 20 |
| [ ] code done; run blocked (needs Docker laptop and map file) | B | Calibration against matrix M1, logged | road-graph, Task 6 | Fri 20 |
| [x] (17 Nov) | C | R3 and the lower bound | solver-core, Task 4 | Sat 21 |
| [ ] code done; run blocked (needs Docker laptop and map file) | A | Walking distances built and logged (L4) | offline-builders, Task 3 | Sun 22 |
| [x] (17 Nov) | A | Scenario placement rules | offline-builders, Task 4 | Sun 22 |
| [ ] blocked (needs a person, the map and the unblocked OSRM server); file committed with null coordinates | A | Historical closure end points pinned on the map | offline-builders, Task 5 | Sun 22 |
| [ ] code done; run blocked (needs Docker laptop and map file; the limited mode also needs WSL with systemd) | B | Timings under limits, logged (L5) | road-graph, Task 7 | Sun 22 |
| [x] (17 Nov) | C | Ladder with resumable solve | solver-core, Task 5 | Sun 22 |
| [ ] not started | C | Chapter sections 1, 2, 3, 7 | logbook-and-chapter | Sun 22 |

**Gate G1 (Sun 22 Nov).** All five must be true, or follow the work plan's Section 11:

- [ ] Road-block answers logged (does speed 0 block; does a closed point get moved; timings). Open:
  `run_roadblock.py` is written but needs OSRM and the map
- [ ] Walking file committed. Open: `build_walk.py` is written but needs the foot build of OSRM
- [ ] Graph calibration passes: median absolute error at most 15%, not running fast. Open: needs the
  graph built from the map file
- [ ] On the corridor under limits: 14 rows in at most 5 s, 31 rows in at most 30 s. Open: needs the
  graph and corridors, and WSL with systemd for the limits (the lead's laptop cannot start WSL)
- [x] R3 matches brute force in the tests (17 Nov): exact on 800 of 800 random problems

### Week 2, 23 to 29 Nov. Scenarios frozen Thu 26; quick tests pass Fri 27

| Done | Track | Task | Plan and task | Due |
| --- | --- | --- | --- | --- |
| [x] (17 Nov) | C | Request and proposal formats | solver-core, Task 6 | Mon 23 |
| [ ] code done; run blocked (needs Docker laptop and map file) | A | Scenario build, one route checked by eye | offline-builders, Task 6 steps 1 to 2 | Tue 24 |
| [x] (17 Nov) | C | Scenario cases and scoring on true times | experiment-runner, Task 1 | Tue 24 |
| [x] (17 Nov) | C | Summaries and verdict rules | experiment-runner, Task 2 | Wed 25 |
| [ ] code done; run blocked (needs Docker laptop and map file) | A | Full scenario build; no leaks; file frozen and logged (L6) | offline-builders, Task 6 steps 3 to 5 | Thu 26 |
| [ ] code done; run blocked (needs Docker laptop and map file) | A | Combined 311-stop matrix | offline-builders, Task 7 | Thu 26 |
| [ ] code done; quick test running, result pending | C | Quality pass and toy file | experiment-runner, Task 3 | Thu 26 |
| [ ] code done; quick test running without limits, result pending; `run_budget.py --check` needs WSL with systemd | C | Limits pass | experiment-runner, Task 4 | Fri 27 |
| [ ] code done; quick tests running, results pending; the limited quick test needs WSL with systemd | C | Hub entries; both quick tests pass from the hub on the run machine | experiment-runner, Task 6 | Fri 27 |
| [x] (17 Nov) | B | Reuse of pre-closure rows (first in the cut order) | road-graph, Task 8 | Fri 27 |
| [x] (17 Nov) | B | Optimizer matrix lookup | optimizer-scaling, Task 1 | Fri 27 |
| [ ] blocked (needs the frozen scenario file) | all | Quality pass run and logged the same day (L8) | experiment-runner, Task 7 | Sun 29 |
| [ ] not started | all | Chapter sections 4, 5, 6 | logbook-and-chapter | Sun 29 |

### Week 3, 30 Nov to 6 Dec. Run freeze Wed 2; draft Fri 4; done Sun 6

| Done | Track | Task | Plan and task | Due |
| --- | --- | --- | --- | --- |
| [ ] code done; quick test running, result pending | C | Scaling runs coded | experiment-runner, Task 5 | Mon 30 |
| [ ] code done and entry L7 committed (`c4c13f5`); push pending; quick test (`run_scale.py --quick`) running, result pending | B | Optimizer instances and scaling script; entry L7 pushed | optimizer-scaling, Tasks 2 to 3 | Mon 30 |
| [ ] blocked (needs the frozen scenario file and WSL with systemd) | all | Limits pass run and logged the same day (L9) | experiment-runner, Task 7 | Tue 1 |
| [ ] in progress: OS1 contractor part running and RS1 "stops" without limits running or queued, results pending; the rest blocked (Section 7) | all | Rerouting and optimizer scaling runs, logged the same day (L10) | experiment-runner Task 7; optimizer-scaling Task 3 | Wed 2 |
| [ ] | all | **Run freeze**: no new runs after Wed 2 Dec | - | Wed 2 |
| [ ] | all | Chapter sections 8, 9, 10; references checked | logbook-and-chapter | Fri 4 |
| [ ] | all | Internal review of the chapter by a second person | logbook-and-chapter | Fri 4 |
| [ ] | all | Hub plan (`hub/project.json`) and this tracker brought up to date; everything published | - | Sun 6 |

### Still open from the optimization chapter

- [ ] References re-opened and checked (two were cited from memory: the guided local search and granular tabu search papers)
- [ ] Three figures exported from the hub and embedded
- [ ] Decide whether to run Nadeem held to 25 buses (the optimized plans use 26)
- [ ] Decide whether the proposal needs a formal revision

## 4. Decisions needed

| Decision | Needed by | Status |
| --- | --- | --- |
| Who is on tracks A, B and C; which laptop has Docker | Mon 16 Nov | open |
| Thresholds, walking speed and start lag in entry L1 | Tue 17 Nov | taken (17 Nov): the proposed values. Walkers start 60 s after the decision at 1.2 m/s; gain at least 60 s; R2 within 60 s of R3 in at least 90%; a valid plan within 5 s in at least 95%; within 60 s of the oracle at 30 s in at least 90%; memory under 400 MB |
| Proposal revision: rerouting is listed there as out of scope | before the chapter is submitted | open |
| Limits on automatic reroutes on the website (work plan Section 12.2) | before any website build | open |
| R3 is two-phase, not the plan's single search (Section 5) | before the quality pass | taken by the lead (17 Nov); team to confirm |
| Meaning of "infeasible": R0 on true post-closure times never reaches campus or serves no stop, or the baseline is unreachable. `ok` and `infeasible` are counted results; every other status is a failure | before the quality pass | taken by the lead (17 Nov); team to confirm |
| Threshold 4 ("valid plan within 5 s") means the plan held at 5 s is valid on true times; a graph plan that leaves a truly servable stop unserved is `invalid_on_truth` | before the limits pass | taken by the lead (17 Nov, `7299036`); team to confirm |
| Threshold 6 (memory) is judged on every `graph_limited` row, since memory is per process | before the limits pass | taken by the lead (17 Nov, `7299036`); team to confirm |
| Quality pass: the worst route is the one with the largest median R2 minus R3; an unserved stop with a boarding point in range is a violation of rule 3 | before the quality pass | taken by the lead (17 Nov); team to confirm |
| Doubled contractor instances stand in for All and All-doubled until the combined matrix exists | before OS1 is logged | taken by the lead (17 Nov, `c4c13f5`); team to confirm |
| Whether the OS1 rows from the lead's laptop (no WSL, Windows peak memory) are reported beside the All rows from the Docker laptop, or the contractor instances are rerun there | before L10 | open |
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
| Unreachable pairs (`None`) become 10**7 s arcs | `optimize.py` | The stop is dropped instead of crashing the solver |
| Quick result folders are published like the other `-quick` folders; per-job `work/` and `logs/` folders are gitignored | `research/results/`, `research/.gitignore` | Pipeline tests stay visible; intermediates stay out of git |
| The hub refuses to start a run when git cannot give the code version | `research/hub/serve.py` | No run is recorded with code version `unknown` |

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
off). Everything below needs the Docker laptop and the N1 map file; items 4, 11 and 12 also need WSL
with systemd. Run in this order, from the repository root unless stated. Log each
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
9. **Optimizer All and All-doubled (OS1, L10).** `python research/run_scale.py --instances All,All-doubled`,
   or the `optimizer-scale` entry in the hub, which runs the skipped instances once the matrix exists.
10. **Quality pass (L8).** `python research/run_reroute.py quality --workers 2`, or `reroute-quality` in the hub.
11. **Limits pass (L9).** In WSL, plugged in, nothing else running: `python research/run_budget.py --check`
    must print `OK`; then `python research/run_reroute.py limits` (add `--sudo` if needed), or
    `reroute-limits` in the hub. The limited quick test (`python research/run_reroute.py limits --quick`)
    also belongs here.
12. **Rerouting scaling, remaining parts (L10).** In WSL: `python research/run_reroute.py scale --only graph`,
    `--only buses`, `--only slices`, and `--only stops` for the limited rows (the unlimited "stops" rows are
    running or queued on the lead's laptop now).
