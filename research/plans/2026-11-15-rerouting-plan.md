# Rerouting component: work plan (version 2)

Written 15 November 2026. Target: research finished and written up by **Sunday 6 December 2026** (3 weeks).

Version 2 replaces the 4-week draft after four independent reviews (research methods, algorithms and
performance, backend scalability, schedule). Section 13 lists what changed and what was not adopted.

This is a plan, not a logbook entry. Nothing here is a fixed pass/fail rule until it is copied into
`LOGBOOK.md` and pushed before the first run, as the 10 November rule requires.

## 1. Decisions this plan rests on

| Decision | Source |
| --- | --- |
| Question: "When a road is blocked, which road and which stops (keep, skip, or let students walk to a nearby point) give the lowest student delay, within the same limits?" | Supervisor, logbook 10 Nov |
| Scope: morning runs to campus, one bus rerouted at a time | Logbook 10 Nov |
| Baselines: published route patched with a detour; exact solve with no time limit | Logbook 10 Nov |
| Scores: delay against the oracle, students asked to walk, extra walking distance per affected student; judged on the worst case as well as the median | Logbook 10 Nov |
| Scenarios on or near shuttle routes, including the 24 Feb 2024 Shahrah-e-Faisal closure and University Road ponding | Logbook 10 Nov |
| After a block, reuse travel times that cannot have changed and err high on estimates (from run Q1) | Logbook 10 Nov |
| Deadline: 3 weeks | You, 15 Nov |
| Hosting: free only | You, 15 Nov |
| On the website a reroute is applied automatically and admins are informed | You, 15 Nov |
| Both components must be efficient and must scale with more users | You, 15 Nov |

Everything else is my proposal.

## 2. Capacity, stated plainly

The schedule reviewer estimated the 4-week draft at about 225 hours against 90 to 120 hours that three
part-time people have in three weeks. Version 2 is about **130 hours**:

| Track | Work | Hours |
| --- | --- | --- |
| A, the person with the Docker laptop | prerequisites, road-block test, walking distances, scenario build, combined matrix | 35 |
| B | road graph: build, calibrate, corridors, closures, shared row cache, measurements under limits | 36 |
| C | logbook rules, solver, experiment runner and hub entries | 33 |
| Shared | runs and same-day logbook entries 10, chapter 12, optimizer scaling 6 | 28 |

That is about 43 hours a week, roughly 3 hours per person per weekday, with no slack beyond the cut
order in Section 10. If the team has less than that, apply cuts 1 and 2 of Section 10 on day one
instead of waiting for a gate to slip.

## 3. What "done" means on 6 December

1. The road-block facts for OSRM logged.
2. A frozen scenario file with true post-closure travel times, so every later run needs no OSRM.
3. One quality table: patched route, greedy plan and best plan; delay, students walking, metres walked.
4. One decision-time table under 512 MB and 0.1 CPU.
5. Scalability curves for the rerouting solver, the road graph, several buses hit by one closure, and
   the optimizer.
6. A rerouting chapter draft.
7. The solver's request and proposal formats fixed (Section 6.3), shaped for the website.

Not in the 3 weeks: any website change, evening runs, context-dependent walking limits, boarding points
other than known stops, real incident data.

## 4. What the data and the reviews say

- **Walking to another stop is a real option.** 30% of stop visits have a same-route stop within 400 m
  in a straight line and 65% within 800 m. Real walking distances will lower these.
- **The data's problems are small, but "exact is cheap" is only true if the solver is written for it.**
  Routes have 3 to 13 stops. The exact solver's work grows as 2^(stops) x (candidates)^2: about 7 million
  steps for 13 stops and 30 candidates, which a reviewer estimates at 30 to 100 s in plain Python at
  0.1 CPU. It must be vectorised, and it stops being practical near 20 stops. (Estimates, not measured.)
- **Travel times after the closure are the cost that decides everything.** The patched route alone
  needs up to 14 fresh rows of travel times. On the whole city graph that is an estimated 8 to 14 s at
  0.1 CPU, which misses a 5-second target. Searching only a corridor around each route is therefore
  part of the core design, not an optional extra.
- **Skipping a stop saves 60 s of stop time with or without a closure.** Any claim about walking after
  a block has to be measured net of that.

## 5. Problem definition

To be pushed to the logbook on Tuesday 17 November (work item C1), before scenarios exist.

**Given**: the bus position and time; the remaining stops with students, a walking limit and a
must-serve flag each; candidate boarding points (the remaining stops plus other known stops within
800 m walk); walking distances; one or more closures; points the bus is already committed to visit.

**Decide**: which candidates to visit, in what order, and at which visited point each stop's students
board. The boarding point is a decision, not "the nearest visited point". A reviewer showed that the
nearest-point rule makes the exact method incorrect, because a later visit can pull walkers away from
an earlier one.

**Constraints**

- Every remaining stop boards at one visited point within its walking limit. A must-serve stop boards
  at itself. Committed points are visited.
- The bus does not leave a point before its walkers can arrive. Walkers start one minute after the
  decision at 1.2 m/s.
- Stop time: 60 s per visited point plus 5 s per student boarding.
- **Reachability.** Every point is snapped to the road once, before the closure. If its road segment is
  closed, the point cannot be visited, in both travel-time sources. Its students must walk; if no
  candidate is in range the stop is reported `unserved` and counted as a failure.

**Objective**: earliest arrival at campus; among plans with the same arrival, least total walking. This
is a strict two-level order with no tolerance window, so the best plan is never beaten on arrival time.

**Methods**

| Label | Method | Role |
| --- | --- | --- |
| R0 | Published order, every remaining stop visited, detour around the closure | Baseline |
| R2 | Greedy: add the candidate that boards the most students per second of detour, then try removing each visited point | Fast method |
| R3 | Exact: dynamic programming over (set of boarded stops, last point), value = earliest departure | Best plan in the model |

R1 of the first draft (accept the fastest path if it happens to cover every stop) is dropped. It cannot
be defined on saved travel-time tables and adds little.

R3 on true times with no time limit is called the **oracle**. It is the best plan in this model: known
stops as boarding points, stop-to-stop walking, OSRM times, the closures given. It is not a bound on
what any reroute could achieve.

**Scores**: delay (arrival minus the published route's arrival with no closure, from the same position)
for every method and as a difference from the oracle; students walking; metres per walking student;
stops skipped; longest ride of students on board; decision time and peak memory.

**Scoring a plan made on other travel times.** The visit order and boarding choices are replayed on the
true times. If the bus reaches a point before its walkers, it waits. If the plan uses a point that is
truly unreachable, the run is a failure and is counted.

## 6. What gets built

### 6.1 Layout

```
research/
  reroute/                    solver core: no Django, no file access
    model.py                  request and proposal shapes, validation, versions
    ladder.py                 R0, R2, R3; resumable state
    graph.py                  road graph: load, corridor, apply closures, travel-time rows, row cache
    closure.py                circle or polygon -> road segments (by geometry) -> graph edges / OSRM speed file
  build_graph.py              map file -> compressed road graph + full segment table (offline, once)
  build_walk.py               OSRM foot profile -> walking distances between stops (offline, once)
  build_scenarios.py          closure scenarios + true blocked travel times from OSRM (offline, once)
  run_roadblock.py            road-block test
  run_reroute.py              one runner: quality pass, limits pass, scaling runs
  data/graph_karachi_v1/      arrays as .npy files
  data/walk_fall2026_v1.json
  data/scenarios_reroute_v1.json
  data/scenarios_toy.json     hand-made, for pipeline tests only
```

`run_reroute.py` follows the hub contract and keeps its `numpy` and `scipy` imports inside functions.
`hub/build_site.py` imports every runner when it builds the shared page, so a top-level import of a
package the page builder does not have would break publishing. `research/requirements.txt` and the
hub's setup check gain `numpy`, `scipy` and `pyosmium`.

### 6.2 The road graph (track B)

- **Built from the same map file as OSRM**, offline, with `pyosmium`.
- **Two tables.** A compressed graph (chains of nodes with no junction merged into one edge) for
  searching, and the full list of map segments with their node ids and geometry. The full list is
  needed because OSRM's speed file names segments by adjacent map node ids, and because closures are
  matched to roads by geometry.
- **Closures are matched by geometry, not by H3 cell of a node.** Each segment is sampled every 50 m; a
  segment is closed if any sample falls in the closure. H3 cells are used as an index to find nearby
  segments quickly. Matching by node cell alone misses long segments that cross a closure without a
  node inside it.
- **A corridor per route**, computed offline: the nodes within a buffer of the route's current path to
  campus. Searches run on that subgraph (an estimated 30,000 to 60,000 nodes, not the whole city) and
  widen once if no path exists.
- **Closing a road writes an infinite weight** on a private copy of the weight array, one copy per set
  of closures, never per bus. (A zero in a sparse matrix means "no edge" in some routines and "free
  edge" in others; infinity is unambiguous.)
- **Rows are computed in a fixed order and cached**: one reverse search from campus gives every
  point-to-campus time; then one row per bus position; then rows on demand. The cache is keyed by
  (graph version, closure set, source node) and is shared by every bus affected by the same closure.
- **Reuse of pre-closure rows.** Per route, the pre-closure table and the roads each pair's path uses
  are stored offline. After a closure, only pairs whose path touches a closed segment are recomputed.
  This is the Q1 finding carried into rerouting. It is the first item in the cut order; if cut, the
  logbook must say so, because the 10 November entry lists it as part of the design.
- **Calibration**: one speed factor fitted against the saved OSRM matrix M1. Rule, fixed before the
  test: median absolute error at most 15%, and the median error not negative (the graph must not run
  fast). If it fails, fit one factor per road class (4 hours); if it still fails, see Section 11.

### 6.3 The interface the website will also use

Changed from the first draft on the backend reviewer's advice, so the later build does not force a
rewrite.

Request:

```json
{
  "schema": 1, "graph": "karachi_v1",
  "trip": {"assignment_id": 41, "service_date": "2026-12-01", "direction": "morning"},
  "now": "2026-12-01T07:05:00+05:00", "deadline_s": 5,
  "position": {"lat": 24.91, "lng": 67.08},
  "remaining": [{"stop_id": 118, "route_stop_id": 902, "name": "Gulshan Chowrangi",
                 "lat": 24.92, "lng": 67.09, "students": 6, "walk_limit_m": 400, "must_serve": false}],
  "candidates": [{"stop_id": 77, "name": "NIPA", "lat": 24.91, "lng": 67.10}],
  "committed": [77],
  "closures": [{"id": "incident-55", "circle": {"lat": 24.9, "lng": 67.09, "radius_m": 200}, "factor": 0.0}],
  "campus": {"lat": 24.856899, "lng": 67.264684},
  "based_on": null
}
```

Proposal:

```json
{
  "schema": 1, "status": "reroute", "reason": null, "revision": 1, "method": "R2",
  "visit": [77, 131],
  "stops": [{"stop_id": 118, "action": "walk", "board_at": 77, "walk_m": 310}],
  "arrival": "2026-12-01T08:07:30+05:00", "delay_s": 450, "students_walking": 6,
  "compute_s": 1.8, "state": "..."
}
```

- `status` is `reroute`, `no_change` (with a reason, such as "saves under the minimum") or `failed`.
- `committed` lists points students have already been told to walk to. A later revision must still
  visit them.
- `state` lets a caller stop the solver after any step and continue it later from saved data.
- Stops are identified by ids, never by name: stop names are not unique in the website's database.
- Travel times come from one function the caller passes in, which answers for a batch of source points
  at once. The experiments pass saved tables; the website passes the cached graph rows.

## 7. Work items

### Track A: everything that needs Docker (35 h)

| Item | Work | Hours | Done when |
| --- | --- | --- | --- |
| A1 | Find the map file from run N1, log its SHA-256; confirm Docker runs the OSRM image. Keep an untouched copy of the OSRM files | 3 | Hash in the logbook, Tue 17 Nov |
| A2 | Road-block test (Section 8.1): speed 0, a slowed segment, customize and reload time | 8 | Results in the logbook, Fri 20 Nov |
| A3 | OSRM foot profile build; `build_walk.py`; log the walking detour factor and the share of stops with a neighbour within 400 and 800 m walk | 6 | Walk file committed, Sun 22 Nov |
| A4 | `build_scenarios.py` and the scenario build (Section 8.2) | 16 | Scenario file committed, Thu 26 Nov |
| A5 | One OSRM table call for all 311 stops together, for the optimizer scaling run | 2 | Combined matrix committed |

For A4, every scenario's customization starts from the untouched copy of the OSRM files.
Customizing rewrites segment data, so closures would otherwise pile up. After each one, a check asks
OSRM for routes through the closure and confirms none passes; leaks and over-blocks are logged.

### Track B: road graph (36 h)

| Item | Work | Hours | Done when |
| --- | --- | --- | --- |
| B1 | `build_graph.py`: compressed graph, full segment table, `.npy` files | 14 | Graph committed, Wed 18 Nov |
| B2 | Calibration against M1 | 4 | Error logged, Fri 20 Nov |
| B3 | `closure.py` first (closure to road segments and OSRM speed file, which the scenario build needs), then `graph.py`: corridors, closures, rows, cache, reuse; toy-graph tests | 12 | Closure matching ready Mon 23 Nov; all tests pass Thu 26 Nov |
| B4 | Measurements under limits for gate G1 and Section 8.5 | 6 | Logged |

### Track C: rules, solver, runner (33 h)

| Item | Work | Hours | Done when |
| --- | --- | --- | --- |
| C1 | Logbook entry: Section 5, scenario rules, **all thresholds**, the gate G1 rules, and a note that `backend/apps/transport/corridor.py` already holds a greedy covering path for drawing route lines | 5 | Pushed Tue 17 Nov |
| C2 | `model.py`, `ladder.py`, test-first. R3 vectorised per layer; checked against brute force over orders **and** boarding choices for up to 7 stops | 16 | Tests pass, Sun 22 Nov |
| C3 | `run_reroute.py`, hub entries, summary builder, `--quick` on the toy file only | 12 | `--quick` passes from the hub on the run machine, Fri 27 Nov |

Tests for C2: no closure and a zero walking limit return the published order; a must-serve stop is
always visited; committed points are always visited; a stop with no boarding point is reported, never
dropped; on the same times R3 arrives no later than R2, and R2 no later than R0; a stopped and resumed
solve returns the same plan as an uninterrupted one.

For more than 16 remaining stops R3 is not run. The runner then reports a lower bound (direct time to
campus, plus 60 s for the fewest points that can board everyone, plus 5 s per student) and the gap of
R2 to it.

### Shared (28 h)

| Item | Work | Hours |
| --- | --- | --- |
| S1 | Runs, reruns and logbook result entries written the same day | 10 |
| S2 | Rerouting chapter. The method sections are written in week 1 from the C1 entry | 12 |
| S3 | Optimizer scaling (Section 8.6) | 6 |

Housekeeping to do on Monday: commit the pending logbook entry, hub plan, optimization chapter and this
plan; add the hub warning for missing git; remove `run_query.py` and the `--k` option.

## 8. Experiments

All thresholds are proposals until the C1 entry is pushed. They are fixed **before the scenario file
exists**, so nobody has seen any delay when they are set. This is stricter than the first draft, where
thresholds waited for the baseline delays.

### 8.1 Road-block test (A2)

| Question | Selects |
| --- | --- |
| Does a segment speed of 0 block a road in OSRM 5.27.1? (The current source code maps speed 0 to an impassable segment; not checked on this version.) | If not, use 1 km/h |
| Does a point on a closed segment get moved to another road silently? | Confirms the reachability rule of Section 5 |
| Does a slowed segment change routes? | Whether the University Road case stays in |
| How long do customizing and reloading take? | Scenario build time |

The Valhalla and "OSRM inside 512 MB" probes of the first draft are dropped. They stay in the chapter as
untested free options. Valhalla's route service accepts per-request exclusions according to its
documentation; whether its table service does, and the public server's limits, are unverified.

**Gate G1, Sunday 22 November. Rules fixed in the C1 entry:**

- Graph calibration passes the rule in Section 6.2.
- On the corridor graph under 512 MB and 0.1 CPU, the rows R0 needs for a 13-stop route take at most
  5 s of wall time, and the full table for 30 points at most 30 s.

If either fails, see Section 11.

### 8.2 Scenarios (A4)

- **Where.** For each of the 52 routes, two closures, each a 200 m circle centred on the road path at
  the middle of a leg **between two stops**: the leg after the first third of the stops and the leg
  after the second third. Placing closures by driving time, as in the first draft, would have put many
  after the last stop, where every method gives the same answer.
- **When.** Two bus positions per closure: before the first stop, and at the last stop before the
  closure. Both share one OSRM customization.
- **Historical.** Shahrah-e-Faisal between Karsaz and FTC as a full block; University Road between
  Hasan Square and NIPA slowed to 10 km/h. Each applies to every route whose path crosses it. These are
  reported separately, never pooled with the synthetic ones.
- **Counts.** 104 synthetic closures, 208 scenarios, about 106 customizations.
- **Tags.** Remaining stops; closure contains a stop; R0 delay; whether the oracle differs from R0.
- **Judged set.** Thresholds are judged on scenarios with at least two remaining stops where R0 loses
  at least one minute. The share outside this set is reported.
- "Near" routes: a 200 m circle also closes side roads beside the route. Closures on roads no route
  uses are not included; this is a narrowing of the logbook's "on or near" and will be stated there.

Scenarios from one route are not independent of each other, and routes share trunk roads. Results are
therefore also reported per route, with the worst route named.

### 8.3 Quality pass (one run of `run_reroute.py`)

- **Design.** Every scenario x walking limits 0, 400 and 800 m x methods R0, R2, R3, on true times, no
  time limit. Plus two arms at 400 m:
  - **No-closure control.** The same solve on unblocked times. Skipping a stop saves stop time even on
    a normal day; the control measures that, and the closure-specific gain is blocked minus unblocked.
  - **Must-serve.** 25% of stops (rounded up, at least one) marked must-serve by a fixed draw. Reported
    as a table, not judged.
- **Proposed thresholds, on the judged set.**
  1. Closure-specific gain of the best plan at 400 m over R0: median at least 1 minute.
  2. R2 within 60 s of the oracle's delay in at least 90% of scenarios, and on every route's median.
  3. In no run does a student walk beyond the limit, go unserved where a boarding point exists, or the
     best plan arrive later than R0.

### 8.4 Limits pass: decision time under 512 MB and 0.1 CPU

- **Design.** Every scenario at 400 m, graph already loaded, 3 repeats, limited. The solver plans on the
  road graph and is scored on true times. Two more arms separate the two possible causes of a gap to
  the oracle:
  - R3 on the graph with no limit: shows what the graph's errors cost.
  - R3 on true times under the limits: shows what the time limit costs.
- **Reported.** Seconds to a valid plan; method reached and delay against the oracle at 1, 5 and 30 s;
  peak memory; rows computed and rows reused.
- **Proposed thresholds, judged set, worst repeat.** (1) A valid plan within 5 s in at least 95% of
  scenarios; (2) at 30 s, within 60 s of the oracle's delay in at least 90%; (3) peak memory under
  400 MB including the graph.

### 8.5 Scaling runs for rerouting (no pass or fail; curves)

| What grows | Varied | Recorded |
| --- | --- | --- |
| Stops on one bus | 4 to 20 remaining stops (longer routes made by joining real ones), 1 to 4 candidates per stop | CPU-seconds and memory for R2 and R3; largest problem solved in 5 s and in 30 s at 0.1 CPU |
| Road graph | Corridor, whole city; 10, 30, 60 points | CPU-seconds per row; rows recomputed against rows needed without reuse; peak memory; memory with the arrays opened memory-mapped from `.npy` |
| Buses hit at once | The Shahrah-e-Faisal closure with 1, 5, 10, 20 buses | Seconds until every bus has a valid plan and until every bus has its final plan; distinct searches; share of rows served from the cache |
| Paused solving | A solve cut into slices of 0.5 to 1 s | Plan quality after each slice; size of the saved state |

The third row is the one that matters most for the website: a closed trunk road in the morning affects
many buses at once, and the shared row cache is what keeps the cost from multiplying by the number of
buses.

### 8.6 Scaling run for the optimizer (S3)

- **Change to the optimizer, as a new version.** Travel times are handed to OR-Tools as a matrix; today
  every lookup calls back into Python. Results B1, Q1, T1 and S1 keep the version they were run under.
- **Run.** The two contractors as they are (171 and 143 stops), all 311 stops together (matrix from
  A5), and the 311-stop set doubled by copying stops with a small random shift, with travel times for
  the copies from the road graph and buses in proportion. 300 s each, no limits.
- **Recorded.** Model build time, peak memory, and plan quality against CPU-seconds, old lookup against
  matrix lookup.
- Note for the chapter: the number of students does not change the size of the problem. Stops and
  buses do.

Warm-starting from the current routes and re-planning after a few students change are not in the
3 weeks. They are listed in Section 12.

## 9. Schedule

| Week | Dates | Track A | Track B | Track C and shared | Gate |
| --- | --- | --- | --- | --- | --- |
| 1 | 16 to 22 Nov | A1, A2, A3 | B1, B2, first B4 timings | C1 pushed Tue; C2; chapter method sections | **G1, Sun 22:** road-block facts logged; walk file committed; graph error logged; one search timed under limits; R3 matches brute force |
| 2 | 23 to 29 Nov | A4, A5 | B3 | C3; quality pass run on the weekend | **Thu 26:** scenarios frozen. **Fri 27:** `--quick` passes from the hub on the run machine |
| 3 | 30 Nov to 6 Dec | reruns | B4, scaling runs | limits pass, scaling runs, S3; result entries the same day; chapter | **Wed 2:** run freeze. **Fri 4:** full draft for internal review. **Sun 6:** done |

The three tracks start on Monday and do not wait for each other until Thursday 26 November, when the
scenario build needs the segment table from B1 and the walk file from A3.

## 10. Cut order

Least damaging first. Each cut is recorded in the logbook when it is taken.

1. Reuse of pre-closure rows (Section 6.2). Costs the Q1 carry-over; the corridor and the shared cache
   stay.
2. The doubled-stops optimizer run (keep the 311-stop run).
3. The 800 m walking limit (keep 0 and 400 m).
4. The must-serve arm.
5. The paused-solving row of Section 8.5.
6. One closure per route in place of two, if the scenario file is not committed by Thursday 26 November.

Not to be cut: pushing rules before runs, the frozen scenario file, R0 and the oracle, the no-closure
control, the two decomposition arms of the limits pass, and the several-buses scaling run.

## 11. Risks, with dates

| By | Must be true | If not |
| --- | --- | --- |
| Tue 17 Nov | Docker runs OSRM on a named laptop; the N1 map file is found and its hash logged | Rebuild from the dated Geofabrik extract and log the matrix as a new version on Wed 18. By Thu 19, install Docker in WSL on a second laptop |
| Tue 17 Nov | `pyosmium`, `numpy`, `scipy` install on every run machine (one machine runs Python 3.14) | Build the graph once on the Docker laptop and commit the arrays |
| Fri 20 Nov | Graph calibration passes, and one search is timed under limits | Per-class speed factors (4 h). If still failing: the limits pass plans on saved pre-closure times, reports solver-only time, and the travel-time source becomes a stated limitation |
| Sun 22 Nov | Gate G1 timing rule passes on the corridor graph | Candidates limited to the route's own stops; reuse of pre-closure rows becomes required instead of first to cut |
| Thu 26 Nov | Scenario file committed | Cut 6 |
| Fri 27 Nov | Rules pushed; the run machine has git and every package; `--quick` passes there | Run only on the machine that passed. Run Q1 lost a full start to a missing package and recorded code version `unknown` |
| Wed 2 Dec | All runs closed | Report what is complete; no new runs |

Other risks: most closures may have a nearly free detour (reported as the share outside the judged
set); walking may rarely help on real walking distances (a valid result, reported as such).

## 12. Using both components on the website

Nothing here is built in the 3 weeks. The backend review checked the first draft of this section
against the code and found several claims wrong; this version is corrected.

### 12.1 What exists and what does not

| Need | State of the code |
| --- | --- |
| Bus position | Phone trips post a fix every 15 s to `driver_location`, stored as `BusLocationPing`. Buses on hardware trackers go through `driver_tracker`, which stores nothing |
| Stops still to serve | **Not on the server.** The phone keeps the reached stops in its own storage and sends `remaining` only so the server can compute arrival times, which then discards it. Direction is chosen on the phone by the clock |
| A reported closure | `Incident` has closure types, a point, a radius and admin approval. `expires_at` is never set on approval, nothing fires on expiry, and status can also be changed by a plain update that bypasses `approve` |
| Traffic alerts | Not usable as a trigger as they are: bare points with no id or extent, fetched only when someone asks, cached per process |
| Students per stop | Available from seat allocations; needs one grouped query per trip, stored with the trip |
| Telling students | `Notification` exists. Email mirroring fires only on single creates, each email in its own thread; the free email tier is 300 a day and also carries login codes |
| Background work | `road_lines.py` runs a thread per process. It is safe only because its work can be rebuilt from the database at any time |
| Proposed route sets | `RoutePlan` and `route_plans.py`. Parsing caps a plan at 200 routes |

### 12.2 Rerouting: the design that scales

- **A trip record on the server.** New table, one row per assignment, service date and direction, holding
  the reached stops and student counts per stop. The phone already sends what is needed.
- **A reroute job row, not a thread.** One row per (trip, closure set), unique, claimed with a row lock.
  Each ping advances the solve by a bounded slice (the resumable `state` of Section 6.3) and returns
  the best plan so far. Several workers or instances then cannot duplicate or lose work, and a solve
  never holds the shared tenth of a CPU for more than a slice.
- **One closure, many buses.** Travel-time rows are cached per (graph version, closure set, source) and
  shared by every affected bus. With the default in-process cache this sharing is per worker; a
  database-backed cache table shares it across workers.
- **Graph in memory.** Arrays stored as `.npy` and opened memory-mapped, so workers share the read-only
  parts. The weight array is copied once per closure set. `numpy` and `scipy` become backend
  dependencies; their memory cost is measured in Section 8.5.
- **Students are told only after the driver has the plan.** The driver's ping acknowledges a reroute id
  and revision; only then are students notified. A failed ping is currently dropped by the phone, so
  without this rule students could walk to a point the driver never learns about.
- **Cancel and expiry create a new revision** that still visits every committed boarding point. They
  never "restore the published order", which would strand students already walking.
- **Automatic application, admins informed** (your decision), under limits to agree before building: a
  minimum saving over the patched route, the walking limit, must-serve stops, no walking reroutes on
  evening trips, and only for fixes from an authenticated driver. The plain ping endpoint accepts
  unauthenticated posts and must not be able to trigger a reroute.
- **Notifications in bulk and in-app only**, delivered through the poll students' maps already make.
  Twenty buses of forty students would exhaust the daily email allowance at once.
- **Two existing features need to know about reroutes**: the off-route alert measures distance to the
  route's own stops and would fire on every reroute; and arrival times for a bus off its saved line
  call the public routing server on every ping.

### 12.3 Optimization: the design that scales

- **Output** as an inactive `RoutePlan`; preview and activation are the existing screens, so nothing is
  published without an admin.
- **Where it runs.** The free web service has no scheduled jobs and its tenth of a CPU is shared with
  every request. A scheduled GitHub Actions job that exports the instance, runs the optimizer and
  uploads the plan through the API is the free option. The 0.1-CPU figures of run B1 then describe
  what the web service could do, not what the job does.
- **Before it can scale**: the 200-route cap on a plan; activation moves students with a per-student
  nearest-stop scan inside one locked transaction, run twice, against a 120 s request limit; and
  activation re-derives each student's stop instead of using the optimizer's.
- **Later work on the optimizer itself**: starting from the current plan, re-planning only the routes a
  change touches, limiting each stop to its nearest neighbours (which Q1 supports), and splitting a
  large city into areas.

### 12.4 Order of building, after the research

1. Trip record and student counts per stop.
2. Solver core and graph copied in unchanged, with their tests.
3. Shadow mode: reroutes computed and stored for real incidents, shown to no one.
4. Admin view, then driver delivery with acknowledgement, then student notifications.
5. Optimizer job writing route plans; activation fixes.

## 13. Review record

Four reviewers read the first draft. Adopted:

- **Research methods.** No-closure control; closures placed between stops; a judged set; the oracle
  redefined without a tolerance window and renamed "best plan in the model"; two arms to separate graph
  error from the time limit; a check that OSRM really blocks each closure; thresholds fixed before
  scenarios exist; pipeline tests on a toy file; results per route; must-serve reduced to a table.
- **Algorithms.** Boarding point as a decision; vectorised exact solver with a size cap and a lower
  bound; corridor search and row cache as core; reachability rule for points on closed roads; closure
  matching by geometry; untouched OSRM copy per scenario; infinite weights; matrix lookups in the
  optimizer.
- **Backend.** Section 12 corrected against the code; interface changes in Section 6.3; job row in
  place of a thread; acknowledgement before notifying students; `.npy` in place of `.npz`.
- **Schedule.** Three tracks by who has Docker; one merged runner; scenario build halved; chapter
  started in week 1; same-day result entries; dated risks.

Not adopted, with reasons:

- *Cut the website section to one page.* Kept longer: website use and scaling are stated requirements.
- *A two-pass solver for "least walking within 30 s of the earliest".* The objective was simplified to
  a strict order. The exact method guarantees the earliest arrival; because the bus can wait for
  walkers, it does not guarantee the least walking among all plans with that arrival, only among the
  ones it compares. The chapter must say so.
- *Warm start and incremental re-planning of the optimizer now.* Moved to later work; 6 hours is all
  the optimizer gets in this plan.
- *Latency of other requests while a solve runs.* Not measured; the sliced solve bounds it by design.

Unverified claims the plan depends on: every timing and memory figure in Section 4 is a reviewer's
estimate; OSRM's speed-0 behaviour is confirmed in current source code but not on version 5.27.1.

## 14. Open questions for the team and supervisor

1. Who is on track A (the Docker laptop), B and C.
2. The thresholds of Sections 8.3 and 8.4, the walking speed and the one-minute start lag. Needed by
   Tuesday 17 November.
3. Whether the proposal needs a formal revision, since it lists rerouting as out of scope.
4. The limits on automatic reroutes in Section 12.2. Needed before any build, not for the research.

## 15. First five working days

| Day | Track A | Track B | Track C |
| --- | --- | --- | --- |
| Mon 16 | Commit pending work. Find the map file; Docker check | Start `build_graph.py` | Draft the rules entry; assign tracks |
| Tue 17 | Map hash logged. Road-block test: speed 0, closed-segment snapping | Compressed graph and segment table | **Rules entry pushed.** First solver tests |
| Wed 18 | Road-block test: slowed segment, timings | Graph committed. Calibration | `model.py`; R0 |
| Thu 19 | Foot profile build | Corridor per route; first search timings under limits | R2 |
| Fri 20 | Road-block results logged. `build_walk.py` | Calibration logged. Timings logged | R3, vectorised; brute-force check started |
