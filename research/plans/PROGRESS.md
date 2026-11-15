# Research progress tracker

Last updated: **16 November 2026**. Deadline for the rerouting work: **Sunday 6 December 2026**.

**How to use this file.** Tick a box when the task's "done when" in its plan is met and the work is
committed. Add the date and initials after the tick. Update the "Last updated" line. Record every cut
and every change of plan in the last two sections. The logbook stays the source of truth for results;
this file only tracks work.

Status words: **done**, **in progress**, **not started**, **blocked** (say on what), **cut**.

## 1. Summary

| Part | Status |
| --- | --- |
| Optimization: experiments | done (B1, Q1, T1, S1 all passed and are logged) |
| Optimization: chapter | draft committed; references, figures and the Nadeem bus-count point still open |
| Optimization: scaling run | not started |
| Rerouting: planning | done (work plan version 2 approved; six implementation plans written) |
| Rerouting: code | not started |
| Rerouting: data (graph, walking distances, scenarios) | not started |
| Rerouting: experiments | not started |
| Rerouting: chapter | not started |
| Website integration | design only (work plan Section 12); nothing to build before 6 December |

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

## 3. Left to do

Tracks: **A** = the person with the Docker laptop, **B** = road graph, **C** = rules, solver, runner.
Names are not assigned yet.

### Day one (Mon 16 Nov)

- [ ] Assign tracks A, B, C to people, and name the Docker laptop
- [ ] Commit this `plans/` folder (it is untracked)
- [ ] Add the hub warning when git is missing, so no run is recorded with code version `unknown`
- [ ] Remove `run_query.py` and the `--k` option in `optimize.py` (a design that was never run)
- [ ] Correct "the optimizer is not built yet" in the root `CLAUDE.md`

### Week 1, 16 to 22 Nov. Gate G1 on Sun 22 Nov

| Done | Track | Task | Plan and task | Due |
| --- | --- | --- | --- | --- |
| [ ] | C | Logbook entry L1 (problem, rules, thresholds) pushed | logbook-and-chapter, L1 | Tue 17 |
| [ ] | A | Map file from run N1 found, SHA-256 logged; Docker runs OSRM | work plan A1 | Tue 17 |
| [ ] | A | OSRM helper | offline-builders, Task 1 | Tue 17 |
| [ ] | B | Road tables from map ways | road-graph, Task 1 | Tue 17 |
| [ ] | B | Graph built from the map file and committed | road-graph, Task 2 | Wed 18 |
| [ ] | C | Solver model and scoring | solver-core, Task 1 | Wed 18 |
| [ ] | C | R0 | solver-core, Task 2 | Wed 18 |
| [ ] | A | Road-block test run and logged (L3) | offline-builders, Task 2 | Fri 20 |
| [ ] | B | Closures matched by geometry | road-graph, Task 3 | Thu 19 |
| [ ] | C | R2 | solver-core, Task 3 | Thu 19 |
| [ ] | B | Graph search, corridors, row cache | road-graph, Task 4 | Fri 20 |
| [ ] | B | Corridors for the 52 routes | road-graph, Task 5 | Fri 20 |
| [ ] | B | Calibration against matrix M1, logged | road-graph, Task 6 | Fri 20 |
| [ ] | C | R3 and the lower bound | solver-core, Task 4 | Sat 21 |
| [ ] | A | Walking distances built and logged (L4) | offline-builders, Task 3 | Sun 22 |
| [ ] | A | Scenario placement rules | offline-builders, Task 4 | Sun 22 |
| [ ] | A | Historical closure end points pinned on the map | offline-builders, Task 5 | Sun 22 |
| [ ] | B | Timings under limits, logged (L5) | road-graph, Task 7 | Sun 22 |
| [ ] | C | Ladder with resumable solve | solver-core, Task 5 | Sun 22 |
| [ ] | C | Chapter sections 1, 2, 3, 7 | logbook-and-chapter | Sun 22 |

**Gate G1 (Sun 22 Nov).** All five must be true, or follow the work plan's Section 11:

- [ ] Road-block answers logged (does speed 0 block; does a closed point get moved; timings)
- [ ] Walking file committed
- [ ] Graph calibration passes: median absolute error at most 15%, not running fast
- [ ] On the corridor under limits: 14 rows in at most 5 s, 31 rows in at most 30 s
- [ ] R3 matches brute force in the tests

### Week 2, 23 to 29 Nov. Scenarios frozen Thu 26; quick tests pass Fri 27

| Done | Track | Task | Plan and task | Due |
| --- | --- | --- | --- | --- |
| [ ] | C | Request and proposal formats | solver-core, Task 6 | Mon 23 |
| [ ] | A | Scenario build, one route checked by eye | offline-builders, Task 6 steps 1 to 2 | Tue 24 |
| [ ] | C | Scenario cases and scoring on true times | experiment-runner, Task 1 | Tue 24 |
| [ ] | C | Summaries and verdict rules | experiment-runner, Task 2 | Wed 25 |
| [ ] | A | Full scenario build; no leaks; file frozen and logged (L6) | offline-builders, Task 6 steps 3 to 5 | Thu 26 |
| [ ] | A | Combined 311-stop matrix | offline-builders, Task 7 | Thu 26 |
| [ ] | C | Quality pass and toy file | experiment-runner, Task 3 | Thu 26 |
| [ ] | C | Limits pass | experiment-runner, Task 4 | Fri 27 |
| [ ] | C | Hub entries; both quick tests pass from the hub on the run machine | experiment-runner, Task 6 | Fri 27 |
| [ ] | B | Reuse of pre-closure rows (first in the cut order) | road-graph, Task 8 | Fri 27 |
| [ ] | B | Optimizer matrix lookup | optimizer-scaling, Task 1 | Fri 27 |
| [ ] | all | Quality pass run and logged the same day (L8) | experiment-runner, Task 7 | Sun 29 |
| [ ] | all | Chapter sections 4, 5, 6 | logbook-and-chapter | Sun 29 |

### Week 3, 30 Nov to 6 Dec. Run freeze Wed 2; draft Fri 4; done Sun 6

| Done | Track | Task | Plan and task | Due |
| --- | --- | --- | --- | --- |
| [ ] | C | Scaling runs coded | experiment-runner, Task 5 | Mon 30 |
| [ ] | B | Optimizer instances and scaling script; entry L7 pushed | optimizer-scaling, Tasks 2 to 3 | Mon 30 |
| [ ] | all | Limits pass run and logged the same day (L9) | experiment-runner, Task 7 | Tue 1 |
| [ ] | all | Rerouting and optimizer scaling runs, logged the same day (L10) | experiment-runner Task 7; optimizer-scaling Task 3 | Wed 2 |
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
| Thresholds, walking speed and start lag in entry L1 | Tue 17 Nov | open (proposed values are in the draft) |
| Proposal revision: rerouting is listed there as out of scope | before the chapter is submitted | open |
| Limits on automatic reroutes on the website (work plan Section 12.2) | before any website build | open |

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

## 6. Cuts taken

None yet. The order is in the work plan, Section 10:

1. Reuse of pre-closure rows
2. The doubled optimizer instance
3. The 800 m walking limit
4. The must-serve arm
5. The paused-solving scaling row
6. One closure per route in place of two

When a cut is taken: write it here with the date, and write logbook entry L11.
