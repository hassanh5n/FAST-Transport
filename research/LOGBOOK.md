# Research logbook

Source of truth for the research paper and report. Every decision, run and number goes
here, dated, in the order it happened. Never rewrite an old entry: add a new dated entry
that corrects it.

**Scope.** FYP-1: route optimization and rerouting. FYP-2: incident context and travel-time prediction.
**Isolation.** All research lives in `research/`. Nothing here changes the website, its backend, settings or database.

---

## 2026-10-21: Research questions set

- Earlier proposal's research component dropped.
- Questions kept: optimization (all-stop routes from a travel-time matrix under free-tier
  CPU and query limits, compared with hand-made routes) and rerouting (road choice plus
  keep, skip or merge stops when a road is blocked).
- Memory is not the research question: a 280-stop matrix is about 0.3 MB. The limits that
  bind on free hosting are CPU time and the number of travel-time queries.
- No GPS trackers on buses, so FYP-1 uses no bus GPS data.

## 2026-11-03: Dataset decisions

- Inputs: Fall 2026 route plan (52 routes), stop list, bus list (synthetic).
- Stop locations used as given. 11 stops had none; placed from route neighbours
  (evenly between located neighbours; 300 m steps at a route's start or end), marked `interpolated`.
- Same name or within 25 m = one stop (rule from `stop_import.py`). Merged:
  Ayesha Manzil into Ayesha Manzil More, Model Colony into Model More, Qazimabad into Kazimabad.
- Contractors plan only their own routes with their own buses; a stop may be served by both
  (Check Post 5, Kala Board, Kazimabad).
- Jadoon has 27 routes and 26 buses; added JDN-126 (45 seats). Larger buses assigned to routes with more stops.
- Students are synthetic (no access to real data): each route's bus filled to U(0.65, 0.90)
  of capacity, spread over its stops with log-normal weights (sigma 0.6), minimum 1 per stop, seed 2026.
  Current routes are feasible by construction; the optimizer must serve the same students.
- Drivers file excluded (no effect on routes; contains CNICs).

### Run D1: build dataset (`build_instance.py`, version fall2026-v1)

| Item | Jadoon | Nadeem | Total |
| --- | --- | --- | --- |
| Stops | 171 | 143 | 311 unique (3 shared) |
| Current routes | 27 | 25 | 52 |
| Buses | 27 | 26 (1 spare) | 53 |
| Seats | 1,220 | 1,195 | 2,415 |
| Students (synthetic) | 906 | 900 | 1,806 |

- Students per stop: min 1, median 5, max 19. Route load factor: min 0.66, mean 0.78, max 0.90.
- Rebuild is identical (checked by file hash on two machines).

## 2026-11-03: Road network (OSRM)

- Map: Geofabrik Pakistan extract, file dated 2026-11-02, cut to box 66.90,24.70,67.45,25.15.
- OSRM v5.27.1, car profile, MLD pipeline (chosen so a blocked road can be re-customized without a full rebuild).
- Run in Docker inside WSL on a team laptop.

### Run N1: build road network

| Step | Result |
| --- | --- |
| Graph | 409,528 nodes, 582,290 edges (compressed); 550,297 nodes in edge-based graph |
| Partition | 6.5 s, peak 214 MB RAM |
| Customize | 4.5 s, peak 291 MB RAM |

- Customize is the step rerouting repeats per blocked road; 4.5 s on a laptop is the starting reference.
- Warnings about unreachable boundary nodes come from dead-end fragments at the cut edge; no stop affected.

### Run M1: travel-time matrices (`build_matrix.py`)

| Item | Jadoon | Nadeem |
| --- | --- | --- |
| Size (campus + stops) | 172 x 172 | 144 x 144 |
| OSRM calls | 1 | 1 |
| Unreachable pairs | 0 | 0 |
| Largest snap to road | 80 m | 224 m (Boat Basin, kept) |
| Free-flow time to campus, min / median / max | 13 / 28 / 40 min | 9 / 27 / 39 min |
| Median asymmetry A to B vs B to A | 8% | 7% |

- Times are free-flow (no traffic). Real morning times will be higher.
- Asymmetry confirms one-way roads matter: the optimizer must use the full directed matrix.
- Query budget so far: 2 calls, 50,320 cells.

## Open decisions

- Maximum ride time per student (proposed 90 min).
- Objective: total student ride time (proposed) vs fewest buses first.
- Stop time per stop (proposed 60 s + 5 s per student).

## 2026-11-03: Optimizer model fixed

- Decisions: longest ride 90 min per student; objective = total student ride time
  (driving time as a small tie-breaker). Stop time 60 s + 5 s per student. All buses arrive at campus at 08:00.
- Solver: OR-Tools 9.15 routing, first solution PATH_CHEAPEST_ARC, then GUIDED_LOCAL_SEARCH.
  Each contractor solved separately with its own buses; all stops mandatory (a stop is dropped only if no plan can serve it).
- Current routes are scored with the same function on the same matrix (`optimize.py: score`).

### Run O0: smoke test (`opt-20261103-160652-t20`)

Development check, not a reported result: 20 s limit, unthrottled cloud machine (not the team laptop, not resource-limited).

| | Jadoon current | Jadoon optimized | Nadeem current | Nadeem optimized |
| --- | --- | --- | --- | --- |
| Buses used | 27 | 27 | 25 | 26 |
| Total student ride (min) | 40,201 | 31,562 (-21.5%) | 37,280 | 29,951 (-19.7%) |
| Longest ride (min) | 78.7 | 56.1 | 65.6 | 64.0 |
| Stops dropped | - | 0 | - | 0 |
| Peak memory | | 57 MB | | 64 MB |

- Every stop visited exactly once; no bus over capacity.
- Nadeem's plan uses its spare bus: the objective rewards shorter rides, so it uses every bus available. Note for the report.
- Caveat: free-flow times and synthetic students; numbers show the method works, not real savings.

### Run O1: 60 s development run (`opt-20261103-162833-t60`)

Logged 2026-11-04 from the result file; machine not recorded, not resource-limited. Development check, not a reported result.

| | Jadoon | Nadeem |
| --- | --- | --- |
| Total student ride, optimized (min) | 31,492 (-21.7% vs current) | 29,807 (-20.0% vs current) |
| Change vs 20 s run (O0) | -0.2% | -0.5% |
| Solve wall / CPU | 58.5 s / 61.2 s | 57.0 s / 59.7 s |
| Peak memory | 57 MB | 64 MB |
| First valid plan | 0.07 s | 0.10 s |

- Tripling the search time improved the plan by under 1%: the search flattens early on an unlimited machine.
  The time-budget experiment tests whether that still holds at 0.1 CPU.

## 2026-11-04: Time-budget experiment planned (fixed before any run)

- Question: on a free-tier server (512 MB RAM, no swap, 0.1 CPU, as on Render's free tier),
  how close does the optimizer get to the best known plan, and how fast?
- Design (`run_budget.py`): per contractor, search budgets 10, 60, 300, 600 s; 3 repeats each;
  setups limited and unlimited; plus one 1,800 s unlimited reference. 50 runs, about 4.2 h of search time.
  Median over repeats reported. Gap measured against the best plan found by any run (normally the reference).
- Limits applied with systemd cgroups v2 (`systemd-run --scope`, MemoryMax=512M, MemorySwapMax=0,
  CPUQuota=10%) inside WSL, not Docker: same kernel mechanism Docker uses. Each run first checks that the
  kernel applied the limits (`--check`) and records what it found. A run over 512 MB is killed and counted as a failure.
- Each run is a fresh process, so peak memory is per run.
- **Thresholds, fixed now:** (1) limited setup within 5% of the best known plan at 60 s, for both contractors;
  (2) peak memory under 400 MB in every limited run, none killed.
- Also recorded: time from launch to first valid plan, wall and CPU time, machine details (`meta.json`).
- Caveats carried over: free-flow travel times, synthetic students.

## 2026-11-09: Time-budget experiment results

### Run B1: time-budget experiment (`run_budget.py`, `results/budget/`)

- Ran 2026-11-04 17:08 to 2026-11-06 14:16 UTC, with pauses (resumed through the hub). 50 of 50 runs finished, all `ok`.
- Machine: DESKTOP-VIQC8PE, Intel i7-3770 (8 threads), 3.8 GB RAM, WSL2 kernel 6.18.54.1, Python 3.14.4, OR-Tools 9.15.6755.
- Limits read back from the kernel before the runs: `memory.max=536870912`, `memory.swap.max=0`, `cpu.max=10000 100000`.
- Code: rows from the hub carry commit `2c763de`; the earliest rows have no commit recorded (started before the hub passed it).
- Gap = median total student ride time over 3 repeats, compared with the best plan any run found. The best plan for both
  contractors came from the 30-minute reference run: Jadoon 31,447 student-min, Nadeem 29,639.

**Gap to best known plan, median (range over 3 repeats)**

| Budget | Jadoon limited | Nadeem limited | Jadoon unlimited | Nadeem unlimited |
| --- | --- | --- | --- | --- |
| 10 s | 21.0% (12.6 to 21.0) | 19.2% (11.7 to 23.8) | 2.2% (0.8 to 2.3) | 2.0% (1.2 to 2.0) |
| 60 s | **3.7% (1.7 to 4.6)** | **2.6% (1.4 to 2.7)** | 0.2% (0.1 to 0.2) | 0.9% (0.9 to 0.9) |
| 300 s | 0.5% (0.4 to 0.8) | 1.1% (1.1 to 1.1) | 0.1% | 0.4% (0.4 to 0.6) |
| 600 s | 0.2% | 0.9% | 0.1% | 0.3% (0.3 to 0.4) |

| Measure | Jadoon | Nadeem |
| --- | --- | --- |
| Current hand-made routes (student-min) | 40,201 | 37,280 |
| Best known plan (student-min) | 31,447 | 29,639 |
| Current routes above best known | 27.8% | 25.8% |
| Best plan vs current routes | -21.8% | -20.5% |
| Longest ride, best plan (min) | 53.0 (current 78.7) | 56.6 (current 65.6) |
| Buses used, best plan | 27 | 26 |
| Launch to first valid plan, limited / unlimited (median) | 3.5 to 4.9 s / 0.6 to 1.0 s | 3.7 to 4.4 s / 0.6 to 1.2 s |
| Peak memory, limited | 65 MB | 65 MB |

- Every plan in every run visited every stop, kept every bus within capacity and had no student over 90 minutes.

**Verdict against the thresholds fixed on 2026-11-04**

1. Limited setup within 5% of the best known plan at 60 s, both contractors: **pass** (Jadoon 3.7%, Nadeem 2.6%).
2. Peak memory under 400 MB in every limited run, none killed: **pass** (peak 65 MB, 0 killed).

**Observations for the report**

- The 0.1 CPU cap behaves like a 10x slowdown in CPU-seconds. Limited at 600 s (60 CPU-s) matches unlimited at 60 s
  (60 CPU-s) to the minute for both contractors (Jadoon 31,519 both; Nadeem 29,898 both). So the useful unit is
  solver CPU-seconds, not wall-clock seconds, and results from one machine carry to another by CPU time.
- 10 s is too short on the free tier. Loading the data and building the model take about 3 to 4 s at 0.1 CPU,
  which leaves about 0.6 CPU-s of search, and the first plan is poor (gap 12 to 24%, longest rides 88 to 90 min, at the cap).
- The 60 s pass is real but not comfortable for Jadoon: the worst repeat was 4.6% against a 5% threshold, and two of
  three limited 60 s repeats had a longest ride of 88 to 90 min (median plan quality is fine; the worst student is not).
  300 s limited removes both problems (gap 0.4 to 1.1%, longest ride 55 to 64 min). For a nightly re-plan, 300 s is the
  recommended setting; 60 s is the minimum.
- The search flattens fast: going from 300 s to 600 s limited gains 0.2 to 0.3 points.
- Memory is not a constraint: 65 MB peak is 13% of 512 MB, as expected from the 2026-10-21 note.
- The interim figures in the 4 Nov team overview PDF (gap 1.6% Jadoon, 0.2% Nadeem at 60 s, from 7 runs) are
  superseded by these.
- Caveats unchanged: free-flow travel times, synthetic students, limits simulated on one laptop with cgroups.

## 2026-11-09: Query-budget experiment planned (fixed before the main runs)

- Question: a deployed planner pays per travel-time query (OSRM on a small server, or a hosted matrix API).
  How few real queries still give routes as good as the full matrix?
- Ground truth: the full OSRM matrices from run M1. Each run pretends to query only some cells and estimates the rest.
- Queried cells: each stop's leg to campus, plus the leg to each of its K nearest stops by straight-line distance,
  K = 0, 3, 5, 10, 20, 40. Choosing neighbours needs only stop coordinates, no queries.
  Cells per contractor: (K + 1) x stops; full matrix = stops x stops (Jadoon 29,241, Nadeem 20,449).
- Estimators for the cells not queried, fitted only on queried cells:
  - `crowfly`: real time ~ a + b x straight-line distance (least squares).
  - `graph`: shortest path through the queried cells (Dijkstra); crowfly where no path exists. Not used at K = 0.
  - Control `exact`: the full matrix.
- Each run: optimize on the estimated matrix, then score the plan on the real matrix (`optimize.py: score`).
  Reported score = real total student ride time. Also recorded: estimate error on unqueried cells (median absolute
  and signed %), share of the plan's legs that were queried, longest real ride, students over 90 min on real times.
- Design (`run_query_budget.py`): 12 settings x 2 contractors x 3 repeats = 72 runs, 60 s search each, unlimited.
  Run B1 showed 60 s unlimited gives the same plan quality as 600 s at 0.1 CPU, so the search budget is held at a level
  where search time is not the bottleneck and the matrix is the only thing that changes. Gap is against the median of
  the `exact` control runs in this experiment, not against B1's reference.
- Run on the cloud workspace (2 cores, 2 runs in parallel), not the team laptop: this experiment measures plan quality,
  not compute limits. Machine details go in `results/query-budget/meta.json`.
- **Thresholds, fixed now:** (1) primary: `graph` at K = 10 has a median real total student ride time within 3% of the
  full-matrix control, for both contractors; (2) feasibility: every run with K >= 10 (either estimator) has no student
  over 90 min on real times.
- 3% chosen because B1 repeat-to-repeat spread at 60 s unlimited is up to about 1% and the time-budget threshold was 5%;
  a query saving that costs more than 3% of ride time is not worth it.
- Before writing this entry, a 5 s pipeline test (`--quick`, K = 10 and full only, 1 repeat, `results/query-budget-quick/`)
  checked the script end to end. Not a reported result. The thresholds above were already in the script before it ran.
- Caveats carried over: free-flow travel times, synthetic students. Ground truth is OSRM, not measured trips.
- Correction (2026-11-09, before any main run): the main runs will be done by the team on the research laptop through the
  hub (WSL), not on the cloud workspace. A cloud start was stopped after a few minutes and its rows discarded. Design and
  thresholds unchanged. Machine details go in `results/query-budget/meta.json`.

## 2026-11-09: Query-budget experiment results

### Run Q1: query-budget experiment (`run_query_budget.py`, `results/query-budget/`)

- Ran 2026-11-09 13:17 to 14:19 UTC on DESKTOP-5AQQKU3 (Intel i5-4310U, 4 threads, WSL2), OR-Tools 9.15.6755,
  2 runs in parallel, 60 s unlimited search each. 72 of 72 settings finished `ok`.
- Run history, kept as a record: the first start (13:06) failed all 72 runs at once because OR-Tools was not installed
  on this PC; those rows are in `runs.jsonl` with status `failed` and are replaced by the later `ok` rows in the summary.
  After installing, the run stopped once after 40 runs (WSL or the hub was interrupted, no error in the log) and was
  resumed; the 2 runs in progress were lost and redone. Script fixed the same day so a missing OR-Tools stops before any
  row is written and Resume reruns failed runs.
- Code: `190deb9`-dirty (the new script, uncommitted) for the first 40; `unknown` for the rest (git not available on this PC).
- Check: the full-matrix control matches B1 exactly (unlimited 60 s: Jadoon 31,519, Nadeem 29,898 student-min), so this
  machine and the B1 machine give the same plans at this budget.

**Real total student ride time, gap to the full-matrix control (median of 3 repeats)**

| Queried legs per stop | Cells (Jadoon / Nadeem) | Share of full matrix | Jadoon crowfly | Jadoon graph | Nadeem crowfly | Nadeem graph |
| --- | --- | --- | --- | --- | --- | --- |
| campus only (K = 0) | 171 / 143 | 0.6% / 0.7% | 5.3% | - | 5.6% | - |
| K = 3 | 684 / 572 | 2.3% / 2.8% | 3.7% | 4.0% | 2.9% | 2.5% |
| K = 5 | 1,026 / 858 | 3.5% / 4.2% | 3.5% | 2.4% | 1.7% | 1.9% |
| **K = 10** | 1,881 / 1,573 | 6.4% / 7.7% | 2.1% | **0.8%** | 1.1% | **0.1%** |
| K = 20 | 3,591 / 3,003 | 12.3% / 14.7% | 1.3% | 0.4% | 0.3% | 0.2% |
| K = 40 | 7,011 / 5,863 | 24.0% / 28.7% | 1.0% | 0.2% | -0.2% | -0.1% |
| full | 29,241 / 20,449 | 100% | control 31,519 | | control 29,898 | |

- Control spread over its own 3 repeats: 0 to 0.07% (Jadoon), 0 to 0.3% (Nadeem). Gaps under about 0.3% are noise.
- No plan in any run dropped a stop or had a student over 90 min, on estimated or on real times. Longest real ride
  55.7 to 68.2 min across all settings (control 56.1 / 64.0).

**Verdict against the thresholds fixed earlier today**

1. `graph` at K = 10 within 3% of the full matrix, both contractors: **pass** (Jadoon 0.84%, Nadeem 0.09%).
2. No student over 90 min on real times in any run with K >= 10: **pass** (0 of 36 runs).

**Observations for the report**

- About 15x fewer queries for under 1% loss: K = 10 needs 6.4% (Jadoon) and 7.7% (Nadeem) of the full matrix.
  Smallest K within 3%: `graph` K = 5 (Jadoon), K = 3 (Nadeem); `crowfly` K = 10 (Jadoon), K = 3 (Nadeem).
- Why it works: good routes are made of short legs between neighbouring stops, and those are exactly the legs queried.
  With `graph` at K = 10, 91% (Jadoon) and 97% (Nadeem) of the legs in the final plans were real queried times.
- The estimator's direction of error matters more than its size. `graph` overestimates unqueried legs a lot
  (median +47% / +45% at K = 10) but plans better than `crowfly`, which is more accurate (12% / 10% absolute error)
  but underestimates (-9.5% / -6.2%). An optimistic estimate makes long unqueried hops look cheap, so the optimizer
  uses them (only 79% / 85% real legs with `crowfly` K = 10) and the plan is worse than it thinks: Jadoon `crowfly` K = 10
  planned 31,460 student-min but really rides 32,185. A pessimistic estimate keeps the plan on real legs, and its
  planned score matches the real one (31,774 vs 31,784). Recommendation: overestimate, do not underestimate.
- The straight-line fit is stable from K = 3 on (Jadoon about 90 to 115 s + 0.082 s/m, about 44 km/h; Nadeem about 125 to
  170 s + 0.074 s/m). At K = 0 it is fitted only on long legs to campus and is badly off (+22% / +17%).
- At K <= 5 the `graph` estimator falls back to the straight-line fit for many cells (K = 3: 90% of Jadoon's estimated
  cells), because the near-neighbour graph is not yet connected; from K = 10 the fallback is under 5% of cells (a few
  outlying Nadeem stops stay unconnected up to K = 20).
- Even with no stop-to-stop queries at all (K = 0, only legs to campus), the plan is 5.3% / 5.6% from the full-matrix
  plan and still 17% / 15% better than the current routes on real times.
- Caveats: ground truth is OSRM free-flow, not measured trips; synthetic students; a real deployment would also need
  queries again when stops change. Query counts are cells; how they map to API calls depends on the provider.

**Optimization part of FYP-1: both experiments done.** Next: road-block test (OSRM, Docker), then rerouting.

## 2026-11-10: Plan review after the optimization experiments

Plan changes only; no runs. The hub's plan (`hub/project.json`) is updated to match.

- **Open decisions closed.** The three items under "Open decisions" above (maximum ride time, objective, stop time)
  were all decided on 2026-11-03 ("Optimizer model fixed"). Nothing is open there.
- **Rerouting wording.** The rerouting question is now "keep, skip, or let students walk to a nearby point", which
  replaces "keep, skip or merge" from 2026-10-21. Still to be confirmed with the supervisor against the proposal.
- **Rerouting scope for FYP-1:** morning runs to campus only, one bus rerouted at a time. Evening runs differ
  (students walk home after dark) and are out of scope for now.
- **Standard search budget: 300 s** for planning runs from now on; 60 s is the minimum. Reason: in B1 Jadoon passed
  at 60 s limited with a worst repeat of 4.6% against a 5% threshold.
- **Judging rule for future experiments:** thresholds are checked on the worst repeat as well as the median.
  B1 and Q1 keep the rules they were run under.
- **Pre-registration rule:** the logbook entry with the pass/fail rule is pushed before the first run. For Q1 the
  thresholds, script and results reached git in one commit (`9ed6a89`), so git history cannot show the order.
- **Solver time limit is wall-clock time.** The literature note left open whether the OR-Tools time limit counts
  wall or CPU time under a CPU cap. B1 answers it: 600 s limited gave the same plans as 60 s unlimited, so the
  limit is wall-clock.
- **Two robustness checks added to the optimization part** (re-runs on existing data, thresholds to be fixed in
  their own entries before running):
  - Traffic check: scale every travel time by 1.3 to 1.5 and re-score and re-plan; does the 90-minute limit hold?
  - Seed check: redraw the synthetic students with two or three other seeds; is the improvement still about 20%?
- **Rerouting evaluation, to be fixed before any rerouting run:**
  - A frozen set of road-closure scenarios on or near shuttle routes (random closures on roads no shuttle uses make
    every method look perfect), including the 24 Feb 2024 Shahrah-e-Faisal protest closure and University Road ponding.
  - Baselines: the published route with the blocked leg patched by a detour, and an oracle (exact solve, no time limit).
  - Scores: delay against the oracle, students asked to walk, extra walking distance per affected student.
  - The road-block test also covers slowed roads (partial speed reduction), not only full blocks.
- **Q1 carried into the rerouting design:** after a block, re-query only nearest-neighbour travel times and estimate
  the rest, erring high (overestimate, do not underestimate).
- Not done yet: owners and target dates for each next step; a hub warning when git is missing so runs are not
  recorded with code version `unknown`.

## 2026-11-10: Rerouting question confirmed

- The supervisor confirmed the rerouting question: "When a road is blocked, which road and which stops (keep, skip, or
  let students walk to a nearby point) give the lowest student delay, within the same limits?" It replaces the old
  SQ1/SQ2 wording in the proposal. Reported by the team on 2026-11-10.
- This supersedes "Still to be confirmed with the supervisor" in the plan-review entry above. The step is removed
  from the hub's next steps.

## 2026-11-10: Traffic check and seed check planned (fixed before any run)

Two robustness checks on the optimization results (runs B1 and Q1), both in `run_robustness.py`, both re-runs on the
saved data: no OSRM, no limits. Search 60 s unlimited per run (B1: 60 s unlimited = 600 s at 0.1 CPU in plan quality).

**Traffic check** (`run_robustness.py traffic`, `results/traffic-check/`)

- Question: the matrix holds free-flow times. If real morning times are 1.3 or 1.5 times longer, can the optimizer
  still keep every student under 90 minutes, and does it still beat the current routes?
- Design: every travel time multiplied by 1.0 (control), 1.3 and 1.5; stop times unchanged. Each run plans on the
  scaled matrix and is scored on the same matrix; the current routes are scored the same way. 3 factors x 2 contractors
  x 3 repeats = 18 runs.
- Also recorded, not judged: the control run's plan (made on free-flow times) re-scored at 1.3 and 1.5, to show what
  a plan made without traffic does in traffic.
- **Thresholds, fixed now, judged at x1.5 on the worst run:** (1) every x1.5 run is at least 15% below the current
  routes in total student ride time, both contractors; (2) no x1.5 run drops a stop or has a student over 90 minutes.

**Seed check** (`run_robustness.py seed`, `results/seed-check/`)

- Question: students are synthetic (seed 2026). Is the improvement over the current routes specific to that draw?
- Design: seed 2026 is the frozen dataset (control). For seeds 2027, 2028 and 2029 the students are redrawn with the
  rule from run D1 (each current route's bus filled to 65 to 90 percent, log-normal stop weights with sigma 0.6, at
  least one student per stop), over the frozen current routes in the order they are stored. Stops, routes, buses and
  travel times do not change, and the frozen dataset files are not rewritten. One run per contractor and seed: 8 runs.
  The redraw uses its own random stream per contractor, so it is the same rule as D1 but not the same code path;
  seed 2026 is therefore read from the frozen file, not redrawn.
- **Thresholds, fixed now, judged on the three new seeds, worst run:** (1) every run is at least 15% below the current
  routes for the same students, both contractors; (2) no run drops a stop or has a student over 90 minutes.

**Notes**

- 15% chosen because B1 found 21.8% (Jadoon) and 20.5% (Nadeem) on the frozen data; a result that falls below 15%
  under traffic or another draw would mean the headline figure does not carry.
- Before this entry the script was tested end to end with a stand-in for the solver that returns the current routes
  (no optimizer run, files written outside `results/`). That test showed current-route scores only: on scaled times
  the current routes themselves have rides over 90 minutes (Jadoon from x1.3, longest 97 min; both contractors at
  x1.5, longest 110 and 91 min). No optimized plan had been produced or seen when the thresholds were set.
- Hub: both checks are in `hub/experiments.json` with a pipeline test each (`--quick`, 5 s runs, separate folders,
  not reported results).
- Caveats: a single multiplier is not real traffic (it slows every road equally); the redraw varies who boards
  where, not the stops or routes.

## 2026-11-15: Traffic check and seed check results

Logged 2026-11-15 from the result files; the runs were done on 2026-11-10, after the rules above were pushed
(`a055729`). Both ran through the hub on DESKTOP-15B12RB (Intel i5-7300U, 4 threads, WSL2, Python 3.12.3,
OR-Tools 9.15.6755), 2 runs in parallel, 60 s unlimited search each. All runs finished `ok`, none failed or rerun.

### Run T1: traffic check (`run_robustness.py traffic`, `results/traffic-check/`)

- Ran 2026-11-10 18:13 to 18:22 UTC. 18 of 18 runs. Code: `9b96339` (clean).

**Planned and scored on the scaled times, 3 repeats (median; range in brackets)**

| Travel times | Contractor | Current routes (student-min) | Optimized (student-min) | Better than current | Longest ride, optimized (min) | Current routes: longest ride, stops over 90 min |
| --- | --- | --- | --- | --- | --- | --- |
| x1.0 (control) | Jadoon | 40,200 | 31,736 | 21.1% (20.7 to 21.4) | 53.9 to 56.3 | 78.7 min, 0 |
| x1.0 (control) | Nadeem | 37,281 | 29,924 | 19.7% (19.7 to 19.7) | 56.6 | 65.6 min, 0 |
| x1.3 | Jadoon | 50,433 | 39,987 | 20.7% (20.6 to 20.9) | 69.4 to 70.3 | 97.2 min, 2 |
| x1.3 | Nadeem | 46,817 | 37,661 | 19.6% (all three) | 71.0 | 80.9 min, 0 |
| **x1.5 (judged)** | Jadoon | 57,256 | 45,210 | **21.0% (20.5 to 21.1)** | 77.3 to 79.4 | 109.6 min, 8 |
| **x1.5 (judged)** | Nadeem | 53,180 | 42,653 | **19.8% (19.8 to 19.8)** | 83.6 | 91.1 min, 2 |

- No optimized plan in any run dropped a stop or had a student over 90 minutes.

**Recorded, not judged: the free-flow plan (made at x1.0) re-scored in traffic**

| Re-scored at | Jadoon (3 control plans) | Nadeem (3 control plans) |
| --- | --- | --- |
| x1.3 | 39,746 to 40,108 student-min, longest ride 66.9 to 69.8 min | 37,653 to 37,683, longest 71.0 min |
| x1.5 | 45,178 to 45,592 student-min, longest ride 75.6 to 78.8 min | 42,810 to 42,846, longest 80.7 min |

- Nobody over 90 minutes in any re-scored plan. Against the current routes on the same times the free-flow plans
  are 20.4 to 21.2% (Jadoon) and 19.4 to 19.6% (Nadeem) better.

**Verdict against the thresholds fixed on 2026-11-10 (judged at x1.5, worst run)**

1. Every x1.5 run at least 15% below the current routes, both contractors: **pass** (worst run Jadoon 20.54%, Nadeem 19.79%).
2. No x1.5 run drops a stop or has a student over 90 minutes: **pass** (0 of 6 runs; longest ride 79.4 and 83.6 min).

### Run S1: seed check (`run_robustness.py seed`, `results/seed-check/`)

- Ran 2026-11-10 18:23 to 18:27 UTC. 8 of 8 runs, one per contractor and seed. Code: `71b858f` (clean).

| Seed | Contractor | Students | Current routes (student-min) | Optimized (student-min) | Better than current | Longest ride, optimized / current (min) |
| --- | --- | --- | --- | --- | --- | --- |
| 2026 (frozen, control) | Jadoon | 906 | 40,200 | 31,792 | 20.9% | 53.9 / 78.7 |
| 2026 (frozen, control) | Nadeem | 900 | 37,281 | 29,921 | 19.7% | 56.6 / 65.6 |
| 2027 | Jadoon | 946 | 41,675 | 33,117 | 20.5% | 60.2 / 79.1 |
| 2027 | Nadeem | 923 | 37,695 | 30,629 | **18.8%** | 56.7 / 66.5 |
| 2028 | Jadoon | 984 | 45,871 | 34,617 | 24.5% | 59.0 / 78.7 |
| 2028 | Nadeem | 890 | 36,670 | 29,307 | 20.1% | 59.7 / 64.9 |
| 2029 | Jadoon | 941 | 43,175 | 32,974 | 23.6% | 56.2 / 79.4 |
| 2029 | Nadeem | 913 | 39,594 | 30,685 | 22.5% | 52.5 / 66.5 |

**Verdict against the thresholds fixed on 2026-11-10 (judged on seeds 2027 to 2029, worst run)**

1. Every run at least 15% below the current routes for the same students, both contractors: **pass** (worst run Nadeem seed 2027, 18.75%).
2. No run drops a stop or has a student over 90 minutes: **pass** (0 of 6 runs).

### Observations for the report

- The improvement over the current routes holds at about 20% under a uniform slowdown (19.6 to 21.1% across all
  factors) and across student draws (18.8 to 24.5%). The headline figure from B1 (21.8% and 20.5%) does not depend
  on free-flow times or on seed 2026.
- The 90-minute limit is where traffic bites, and it bites the current routes first: at x1.3 Jadoon's current routes
  have 2 stops over 90 minutes, at x1.5 Jadoon has 8 and Nadeem 2, while every optimized plan stays under.
  The margin is not large for Nadeem: longest ride 83.6 of 90 minutes at x1.5. Factors above 1.5 were not tested.
- Re-planning for a uniform slowdown gains almost nothing: at x1.5 the plan made on free-flow times is within 0.4%
  of the plan made on the scaled times and also keeps everyone under 90 minutes. This is expected when every road
  slows equally (the ranking of routes barely changes) and says nothing about uneven traffic, where knowing which
  roads are slow could change the plan.
- A near-constant percentage is partly built into the test: driving times scale and stop times do not, for both
  plans alike. The check is evidence about the 90-minute limit and the size of the saving in minutes, not about
  how routes should change in real traffic.
- The control runs here are not identical to B1 and Q1 at the same budget (60 s unlimited): Jadoon 31,603 to 31,884
  (median 31,736) and 31,792 in the seed check, against 31,519 in B1 and Q1; Nadeem 29,920 to 29,941, against 29,898.
  The current-route scores also differ by one student-minute (40,200 vs 40,201; 37,281 vs 37,280). One known
  difference in the code: `run_robustness.py` rounds travel times to whole seconds before planning, while the other
  scripts pass the saved times and the solver truncates them, so the solver sees a slightly different matrix. The
  machine and running 2 runs in parallel are other candidates. Which one explains the gap (Jadoon: 0.7% at the
  median, 1.2% in the worst repeat) was not tested. It does not affect either verdict.
- The pipeline tests for both checks (`--quick`, 5 s, `results/traffic-check-quick/`, `results/seed-check-quick/`)
  were run after the main runs and show improvements of 6 to 13%, below 15%. They are not reported results; 5 s is
  too short a search, as B1 showed for 10 s.
- Caveats unchanged: a single multiplier is not real traffic; the redraw varies who boards where, not the stops,
  routes or buses; travel times are OSRM, not measured trips.

**Optimization part of FYP-1: experiments B1 and Q1 and both robustness checks are done, all passed.**
Next: write the optimization chapter, then the road-block test and rerouting.

## 2026-11-16: Rerouting: problem, methods and rules (fixed before any scenario exists)

Plan: `research/plans/2026-11-15-rerouting-plan.md` (version 2); implementation plans in `research/plans/`.
This entry fixes what the experiments will judge. It is written before the scenario file is built, so no
delay has been seen. The values the draft left open were set to the proposed values (walkers start 60 s after
the decision at 1.2 m/s; thresholds below). They are not changed after any result exists.

**Problem (one bus, morning run)**

- Given: bus position and time; remaining stops with students, a walking limit and a must-serve flag;
  candidate boarding points (the remaining stops plus other known stops within 800 m walk); walking
  distances from OSRM's foot profile; one or more closures; points already committed to.
- Decide: which candidates to visit, in what order, and where each stop's students board.
- Rules: every stop boards at one visited point within its walking limit; a must-serve stop boards at
  itself; stop time 60 s per visited point plus 5 s per student; walkers start 60 s after the decision at
  1.2 m/s; the bus does not leave a point before its walkers arrive.
- Reachability: a point inside a full-block closure cannot be visited, in both travel-time sources.
  A stop with no boarding point in range is `unserved` and counts as a failure.
- Objective: earliest arrival at campus. Total walking breaks ties between plans the solver holds with
  equal arrival; the exact method guarantees the earliest arrival, not the least walking.

**Methods**

- R0: published order, every remaining stop visited, detour around the closure. Baseline.
- R2: greedy (add the point that boards the most students per second of detour, then try removals).
- R3: exact, by dynamic programming over (set of boarded stops, last point). On true travel times with
  no time limit this is the oracle: the best plan in this model, not a bound on any possible reroute.
  Run only for 16 or fewer stops plus committed points.

**Two travel-time sources**

- Truth: OSRM 5.27.1 re-customized with the closure, each time from an untouched copy of its files.
  Used only to build the scenario file and to score plans.
- Under test: a road graph built from the same map file, searched in memory on a corridor around the
  route. Plans made on it are scored on the truth. `backend/apps/transport/corridor.py` already holds
  a greedy covering-path heuristic for drawing route lines on the public Valhalla server; R2 here is
  a separate implementation for a blocked network.

**Scenarios**

- Synthetic: for each current route with at least 3 stops, two full-block closures, each a 200 m circle
  at the middle of a leg between two stops: leg ceil(n/3) and leg ceil(2n/3). Two bus positions each:
  at the first stop with nothing served, and at the last stop before the closure.
- Historical, reported separately and never pooled: Shahrah-e-Faisal between Karsaz and FTC, full
  block; University Road between Hasan Square and NIPA, slowed to 10 km/h.
- This narrows the 10 November wording "on or near shuttle routes" to closures on routes; a 200 m
  circle also closes the side roads beside them.
- Judged set: scenarios with at least 2 remaining stops where R0 loses at least 60 s. The share outside
  it is reported.

**Thresholds, fixed now, judged on synthetic scenarios in the judged set**

Quality pass (true times, no time limit; walking limits 0, 400, 800 m):
1. Closure-specific gain at 400 m, that is (R0 minus R3 with the closure) minus (R0 minus R3 with no
   closure): median at least 60 s.
2. R2's delay within 60 s of R3's in at least 90% of scenarios, and on the median of every route.
3. No run has a student walking beyond the limit or unserved where a boarding point exists, and R3
   never arrives later than R0.

Limits pass (512 MB, no swap, 0.1 CPU; graph loaded; plans made on the graph; 3 repeats; worst repeat):
4. A valid plan within 5 s in at least 95% of scenarios.
5. At 30 s, delay within 60 s of the oracle's in at least 90% of scenarios.
6. Peak memory under 400 MB including the graph.

Reported, not judged: must-serve stops (25% of remaining stops, fixed draw); the two arms that separate
graph error from the time limit; results per route with the worst route named; scaling runs.

**Gate rules for week 1, fixed now**

- Graph calibration against matrix M1: median absolute error at most 15%, median signed error not
  negative. One factor first; one factor per road class if that fails.
- Graph timing on the longest route's corridor under the limits: the 14 rows R0 needs in at most 5 s,
  31 rows in at most 30 s.
- If either fails: the limits pass plans on saved pre-closure times, reports solver-only time, and the
  travel-time source is stated as a limitation.

**Caveats carried over**: synthetic students; OSRM free-flow times as truth; limits simulated with
cgroups on a laptop; the bus is assumed to be at a stop when the closure is reported.

## 2026-11-17: Scaling runs planned (optimizer OS1, rerouting RS1 "stops"), fixed before either runs

Code: `54a55f2` (solver, road graph, offline builders, runner and optimizer scaling, with 450 unit tests).
Neither run has a pass or fail threshold; both report curves (work plan Section 8.6; entry of 2026-11-16).

**Machine for both runs.** This entry is written on a Windows 10 laptop (Intel Core i7 third generation,
4 cores / 8 threads, 8 GB) that cannot start WSL (virtualization is off in the firmware). So the runs below
have no free-tier limits, and peak memory is Windows' peak working set (`psutil`), not Linux `ru_maxrss`.
The two are close for a single Python process but are not the same measure; figures from this machine
are not pooled with the WSL runs B1, Q1, T1 and S1.

**OS1: optimizer scaling (`run_scale.py`, `results/optimizer-scale/`).**

- Instances: Jadoon (171 stops, 27 buses) and Nadeem (143 stops, 26 buses) as in B1; and Jadoon-doubled
  and Nadeem-doubled, where every stop is copied 30 s from its original with the same students, and
  every bus is copied too. The doubled instances test model size (342 and 286 stops), not geography.
- The plan's combined instances (All, 311 stops; All-doubled, 622) need `data/matrix_fall2026_v1_all.json`,
  which needs OSRM. They are recorded as skipped here and are run on the Docker laptop when the matrix exists;
  the doubled contractor instances stand in for size until then.
- Lookups: `callback` (every recorded result so far) and `matrix` (tables given to OR-Tools once).
  300 s each, one run per instance and lookup, no limits, one at a time, each in a fresh process.
- Measured: build time, time to first plan, peak memory, the best plan's cost at 10, 60 and 300 s,
  improvements, solve CPU time.
- Known before the run: `build_s` is not comparable between lookups. The callback lookup computes arc costs
  lazily during the search, so its cost shows up in `first_plan_s` and the search; the matrix lookup pays it
  inside `build_s`. Both are reported side by side. At 10 s on Nadeem (pipeline test) the default path gave
  29,989 student-min before and after the change, so the lookup option does not alter existing results.

**RS1 part "stops": rerouting solver against problem size (`run_reroute.py scale --only stops`).**

- Synthetic problems on one bus: 4, 8, 12, 16 and 20 stops; 1, 2 and 4 extra boarding candidates per stop;
  seeds 1 to 3 (45 problems). Stops uniform in a 2 km square, driving at 10 m/s, straight-line walking,
  limit 400 m. Real routes are not joined because the scenario tables hold no times between routes.
- Measured: CPU and wall time and peak memory of R2 and of R3 run to the end, R2's arrival minus R3's.
  Above 16 stops R3 is not run (the cap fixed on 2026-11-16) and the gap to the lower bound is reported.
- Unlimited only on this machine. The limited setup, the graph part (needs the Karachi graph), the buses
  part (needs the scenario file) and the slices part on frozen scenarios run on the WSL machine.

**R3 design change, recorded before any result.** Review found that R3 as planned (one search over
(set of boarded stops, last point), then merging repeated visits to a point) is not exact: on 34 of 800
small random problems the merged plan arrived later than brute force, because a merged visit's boarding
time is paid after the bus waits for walkers. R3 now has a second, exact phase: when the merged plan does
not reach the search's value, a label search over (set of boarded stops, last point, points visited) with
dominance and lower-bound pruning finds the best plan. It matches brute force on all 800 problems and on
every test. Both phases can be paused and resumed. The oracle remains "the best plan in this model".

## 2026-11-17: Rerouting: rules settled while building the code (fixed before any quality or limits run)

The code for every rerouting plan is written and tested (`54a55f2`, `7299036`; 217 solver and graph tests,
235 other tests). Each module was reviewed by a second agent, who had to show every bug with a failing test;
the bugs found were fixed. These rules were settled on the way. They change no threshold of 2026-11-16 and
no result exists for them yet. The team may still overrule any of them before the first quality run.

**Statuses and what counts.**
- `infeasible`: on true post-closure times the patched route (R0) never reaches campus or serves no stop, or
  the no-closure baseline is unreachable. `ok` and `infeasible` are counted results; every other status
  (`failed`, `invalid_on_truth`, `killed_memory`, `skipped`) is a failure.
- `invalid_on_truth`: a plan made on the road graph that true times make impossible, or that leaves a stop
  unserved although true times give it a boarding point in range.
- Threshold 3 also fails on any unserved stop that had a boarding point in range, and on any synthetic row
  whose status is not `ok` or `infeasible`.
- Threshold 4, "a valid plan within 5 s", means the plan held at 5 s is valid on true times, not only finite
  on the graph it was planned on.
- Threshold 6, memory, is judged on every `graph_limited` row (memory belongs to the worker process, which
  also handles unjudged and historical scenarios), as soon as any scenario is judged.
- The worst route in the quality pass is the one with the largest median R2 minus R3.

**Limits pass.** `graph_unlimited` runs once per scenario (planning without a cap is deterministic and its
timing is not judged); `graph_limited` and `truth_limited` run 3 repeats. A worker killed for memory keeps the
rows it finished; the scenarios it had not reached are `killed_memory`.

**Exact method (R3).** As recorded on 2026-11-17 (scaling entry), R3 is a search that allows a point to be
visited twice, then an exact repair when merging repeats loses time. Development timings on this laptop, at
full CPU: 13 stops and 30 points about 0.9 CPU-s; 16 stops and 30 points about 7 CPU-s; with an 800 m limit
the repair took 16 to 32 CPU-s on some 15-stop problems. Under 0.1 CPU that is minutes, which is why the
ladder hands out R0 and R2 at once and R3 only improves on them. RS1 will give the measured curve.

**Road graph.** The row cache holds at most 256 rows and at most 128 MiB: a row searched over the whole city
is about 1.6 MB, so 256 of them would not fit in 512 MB. A corridor's identity is its key plus a hash of its
nodes, so two corridors of the same name never share rows, and a corridor file built for another graph
version is refused.

**Scenario builder.** Historical stretches are covered by 60 m circles every 100 m, using the plan's count
max(2, round(L / 100) + 1); it leaves small gaps only on stretches of 121 to 149 m and 241 to 249 m, and the
real stretches are kilometres long. The leak check looks at route vertices inside the circles, so a long
straight segment crossing a circle without a vertex inside would be missed; any leak found stops the build.
A stretch first met on the last-stop-to-campus leg gets only the early trigger. A closure circle that holds
campus is reported.

**Optimizer.** A pair OSRM cannot route (null in a matrix) becomes a 10^7 s arc, so the stop is dropped
instead of crashing the solve. `ride_300s` includes a plan found just after the nominal limit.

**Machines.** Rows from this Windows laptop (no limits, Windows peak working set) are never pooled with WSL
rows. Runs that need the Docker laptop write to their own folders with `--out-dir`
(`results/optimizer-scale-wsl/`, `results/reroute-scale-wsl/`), and the result entry names the machine.

## 2026-11-17: Scaling results (OS1 optimizer; RS1 "stops", first run) and a change to R2

Machine: the Windows laptop named in the planning entry of today (no limits; Windows peak working set).
Code: `7299036` for every row below. Runs one at a time, each in a fresh process.

### Pipeline tests (not reported results)

`quality --quick` 15 of 15 rows ok, all three toy verdicts pass; `limits --quick --no-limits` 3 of 3 ok;
`scale --quick` 4 of 4 ok; `run_scale.py --quick` 2 of 2 ok (Nadeem, 10 s: 30,945 callback, 30,981 matrix).

### Run OS1: optimizer scaling (`run_scale.py`, `results/optimizer-scale/`)

- 8 of 12 runs, 300 s each. All and All-doubled skipped (no combined matrix yet). The first three runs ran
  2026-11-16 21:11 to 21:26 UTC; the run was cut off by the session ending and resumed 2026-11-17 12:00 to
  12:25 UTC (the interrupted Nadeem-matrix run was redone from the start). During the resumed part other
  light work ran on the laptop (editing documents, a background code-graph rebuild after commits).
- "Ride" is the solver's cost / 60 (student-minutes plus the small driving tie-breaker); "scored" is total
  student ride time of the returned plan scored as in B1. No run dropped a stop.

| Instance | Stops / buses | Lookup | Build (s) | First plan (s) | Peak (MB) | Ride 10 s | Ride 60 s | Ride 300 s | Scored 300 s (student-min) | Longest ride (min) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Nadeem | 143 / 26 | callback | 0.016 | 0.05 | 52 | 30,945 | 30,738 | 30,647 | 29,723 | 56.6 |
| Nadeem | 143 / 26 | matrix | 0.139 | 0.23 | 54 | 31,003 | 30,753 | 30,697 | 29,752 | 54.6 |
| Jadoon | 171 / 27 | callback | 0.017 | 0.07 | 53 | 32,730 | 32,482 | 32,474 | 31,472 | 53.7 |
| Jadoon | 171 / 27 | matrix | 0.037 | 0.06 | 55 | 33,012 | 32,522 | 32,474 | 31,472 | 53.7 |
| Nadeem-doubled | 286 / 52 | callback | 0.018 | 0.14 | 61 | 60,948 | 59,460 | 59,355 | 57,704 | 54.1 |
| Nadeem-doubled | 286 / 52 | matrix | 0.062 | 0.15 | 67 | 64,318 | 60,000 | 59,460 | 57,780 | 54.1 |
| Jadoon-doubled | 342 / 54 | callback | 0.019 | 0.18 | 63 | 66,211 | 63,547 | 63,447 | 61,614 | 51.3 |
| Jadoon-doubled | 342 / 54 | matrix | 0.078 | 0.21 | 73 | 68,997 | 65,003 | 63,547 | 61,698 | 52.4 |

Observations:

- Size is cheap. Doubling the stops (and buses) raised peak memory by 9 to 18 MB and kept building the
  model under 0.1 s; memory is far from binding, as the 21 October calculation said.
- Search converges at this size. With the callback lookup the 60 s plan is within 0.16% of the 300 s plan
  even at 342 stops (0.02% for Jadoon, 0.30% for Nadeem). Under 0.1 CPU this laptop's 60 s is about 600 s of
  wall time, so the standard 300 s budget fixed after B1 still holds for the current fleet.
- The matrix lookup does not help. It is never better at 300 s (equal for Jadoon, 0.16 to 0.18% worse
  elsewhere), is 0.2 to 5.5% worse at 10 s, and uses 2 to 10 MB more. The callback stays the default; the
  matrix lookup is kept only as an option. Its `build_s` includes building the tables, the callback's does
  not (its arcs are computed during the search), so the build column is not a fair comparison either way.
  The Nadeem-matrix build of 0.139 s, against 0.025 s in the pipeline test, is the resumed run's first
  process and is probably noise.
- The number of students does not change the model's size; only stops and buses do. The doubled
  instances test size, not geography (copies are 30 s from their originals).

What it does not show: the combined 311-stop and 622-stop problems (both fleets in one model) and any
timing under the free-tier limits; both run on the Docker laptop into `results/optimizer-scale-wsl/`.

### Run RS1, part "stops", first run (`results/reroute-scale-r2-insertion/`)

45 of 45 synthetic problems ok (4 to 20 stops, 1, 2 or 4 extra candidates per stop, 3 seeds), unlimited.
Medians over 3 seeds unless marked.

| Stops | Points (c = 1 / 2 / 4) | R2 CPU (max) | R3 CPU median, c = 1 / 2 / 4 (s) | R3 CPU max (s) | R3 peak (MB) | R2 minus R3, median c = 1 / 2 / 4 (s) |
| --- | --- | --- | --- | --- | --- | --- |
| 4 | 8 / 12 / 20 | < 0.02 s | 0.13 / 0.11 / 0.09 | 0.14 | 38 | 201 / 161 / 109 |
| 8 | 16 / 24 / 40 | < 0.02 s | 0.14 / 0.14 / 0.14 | 0.17 | 38 | 68 / 134 / 233 |
| 12 | 24 / 36 / 60 | < 0.02 s | 0.55 / 0.58 / 0.63 | 60.9 | 120 | 180 / 170 / 285 |
| 16 | 32 / 48 / 80 | < 0.02 s | 7.3 / 7.8 / 8.8 | 9.2 | 135 | 196 / 249 / 242 |
| 20 | 40 / 60 / 100 | < 0.02 s | not run (over 16) | - | - | R2 is 816 to 968 s above the lower bound (median) |

Observations:

- R3's time grows about 13 times from 12 to 16 stops, as 2^n predicts, and is otherwise flat in the number of
  candidates; one 12-stop problem with 4 candidates per stop needed the exact repair and took 60.9 s.
  Memory stays under 140 MB. Under 0.1 CPU a 16-stop R3 takes over a minute, so on the free tier R3 is
  a later improvement, never the first answer.
- **R2 as built was far from R3**: a median 70 to 285 s later, against the 60 s that threshold 2 asks for on
  real scenarios. Looking at the plans: R2 only inserted points greedily. It never improved the order, never
  added a point to cut the wait for walkers, and never swapped one point for another. Synthetic stops are
  scattered at random, which is harder than a real route, but the gap was too large to put down to that.
- The lower bound used above 16 stops is weak (R2 is 816 to 968 s above it), so beyond 16 stops it says
  little about R2's quality.

### Change to R2, made before any quality-pass run (`723f4c8`)

R2 keeps its greedy construction and its fallback to R0, and now improves the plan in rounds until nothing
changes: reorder (move one point, or reverse a segment), remove points (as before), move stops to their
nearest visited point, then add the one point, or failing that swap the one pair of points, that lowers the
arrival most. Tests check that R2's final plan cannot be improved by any single one of these moves. On a
spot check of the synthetic problems (seeds 1 to 3), R2's gap to R3 fell to 0 in most cases (largest 87 s),
and R2 takes at most 0.5 CPU-s at 20 stops and 100 points (about 5 s under 0.1 CPU, while R0's plan is
already out). The L1 description of R2 ("greedy, then try removals") is extended by this entry; the
thresholds do not change. RS1 "stops" is rerun with the new R2 into `results/reroute-scale/`.

## 2026-11-17: RS1 "stops" rerun with the improved R2 (`results/reroute-scale/`)

Same machine and problems as the first run; code `c1a9f8a` (R2 from `723f4c8`). 45 of 45 ok, unlimited.
Pipeline tests rerun on the same code: quality 15/15, limits 3/3 (no limits), scale 4/4, all ok.

| Stops | R2 CPU, max (s) | R3 CPU median / max (s) | R3 peak (MB) | R2 minus R3 per problem, c = 1 / 2 / 4, seeds 1 to 3 (s) |
| --- | --- | --- | --- | --- |
| 4 | 0.02 | 0.11 to 0.14 / 0.17 | 38 | 20, 0, 0 / 41, 0, 67 / 0, 0, 0 |
| 8 | 0.06 | 0.13 to 0.14 / 0.23 | 38 | 0, 0, 0 / 0, 0, 0 / 97, 52, 54 |
| 12 | 0.11 | 0.55 to 0.64 / 61.4 | 120 | 2, 97, 0 / 87, 0, 0 / 52, 0, 0 |
| 16 | 0.42 | 7.4 to 8.9 / 9.3 | 136 | 9, 45, 0 / 0, 42, 108 / 79, 16, 22 |
| 20 | 0.50 | not run (over 16 stops) | - | R2 is 685 to 773 s above the lower bound (median) |

- R2 is now within 60 s of R3 on 30 of 36 synthetic problems (83%) and equal on 19; the largest gap is 108 s.
  Before the change no group had a median under 68 s. This is not threshold 2, which is judged on real
  scenarios in the quality pass; it says the greedy method is no longer the obvious weak point. If the
  quality pass fails threshold 2, the per-route results will show whether random-looking geometry or the
  method is to blame.
- R2 costs at most 0.5 CPU-s (about 5 s under 0.1 CPU) and R3's times and memory are unchanged from the
  first run, including the one 12-stop problem whose exact repair takes about 61 s.
- The lower bound above 16 stops is still weak and is reported, not used to judge R2.

## 2026-11-17: Corrections to today's entries

- The scaling-results entry says the greedy-only R2 was "a median 70 to 285 s later" than R3; its own table's
  smallest group median is 68 s (8 stops, one candidate per stop). The range is 68 to 285 s.
- The first RS1 "stops" run was written to `results/reroute-scale/` and renamed to
  `results/reroute-scale-r2-insertion/` before the rerun; its `meta.json` carries a note saying so.
- Both scaling runs were started from the command line, not from the hub. The planning entry (`c4c13f5`) was
  committed before the runs but pushed only afterwards, with this day's other commits.
- Test counts at `c1a9f8a` and later: 221 solver and graph tests, 237 other tests, all passing.

## 2026-11-19: A1, L2 and L3: map file, road graph and road-block test

**Machine.** The laptop of runs N1 and M1 (`DESKTOP-15B12RB`), in WSL2 Ubuntu: kernel 6.18.58.1-microsoft-standard-WSL2,
4 CPUs, 3.7 GB RAM, systemd on, cgroup v2. Docker 29.1.3, image `ghcr.io/project-osrm/osrm-backend:v5.27.1`,
Python 3.12.3 (`~/fc-research-venv`). Code `7d6fb0a`, research code unchanged since. This machine can also run
the limited passes (systemd is on), unlike the Windows laptop of 17 Nov.

**Setup.** `scipy`, `osmium` and `psutil` added to the venv from `requirements.txt`. Tests in WSL: 221 in
`reroute/tests` and 265 in `tests` (1 skipped), all passing; the 237 of 17 Nov grew with later commits.

### A1: map file and OSRM

- Map file `~/fleetcentric-osrm/karachi.osm.pbf`, 11,556,317 bytes, made 3 Nov for run N1.
  SHA-256 `a99d2f81f722a3171966f55cb13840813651d0309fe97ec5a5ae3e264f9dc322`.
- The N1 car build was owned by root (written by Docker); its owner was changed to the user and an untouched
  copy made in `~/fleetcentric-osrm/car/`. A backup of the map file and the car build is in `research/map/`
  (not in git), with every file's SHA-256 in `research/map/wsl_inventory.txt`.
- Hand check of `osrm_tools`: fresh copy, plain customize 6.3 s, server on the copy, table between Saddar
  (24.8607, 67.0298) and campus (24.8569, 67.2647): 1756.6 s there, 1713.1 s back. Pass.

### L2: road graph `karachi_v1`

| Nodes | Edges | Segments | Points kept as nodes | Source SHA-256 |
| --- | --- | --- | --- | --- |
| 195,557 | 543,461 | 927,766 | 312 (campus and 311 stops) | `a99d2f81...c9dc322` (same as A1) |

- One point snapped more than 200 m from a road: Boat Basin, 224.4 m. Run M1 had the same stop as its largest
  snap (224 m, kept), so the graph and OSRM agree on it.
- Speed factor 1.0 until calibration (road-graph Task 6). Files: `data/graph_karachi_v1/`, 66 MB, largest file 7.4 MB.

### L3: road-block test (`results/roadblock/result.json`)

Leg: first leg of Jadoon R-10, Hyderi Super Mart KDA to Ziauddin, middle pair of map nodes 290257487 and 290257402.

| Question | Answer | Evidence | Selects |
| --- | --- | --- | --- |
| Does speed 0 block a road? | blocks | 132.7 s to 155.9 s; new route avoids the pair | Scenarios close roads at 0 km/h (`--block-kmh 0`) |
| Is a point on a closed segment moved to another road? | no route | Moved 0.0 m before; after the closure OSRM refuses the route (`NoRoute`) | Reachability rule confirmed (below) |
| Does a segment slowed to 5 km/h change routes? | same route, longer | 132.7 s to 138.5 s | University Road case stays in |
| Customize and reload | customize 6.66 s, start 1.80 s | Median of 5 | Scenario build time (below) |

Timings, 5 repeats: copy 0.10 to 0.16 s, customize 6.56 to 6.90 s, server start 1.70 to 1.83 s, peak memory of
the customize container 278 MB.

- The plan expected `moved` or `not moved` for the second question. OSRM does neither: it keeps the point on
  its closed road and reports no route. That is what the reachability rule of work plan Section 5 assumes (a
  point on a closed segment cannot be visited and its students must walk). The scenario build reads OSRM
  tables, where the same case should give `null`; the one-route check of the scenario build (offline-builders
  Task 6, Step 1) will show it.
- Scenario build time: about 106 customizations at about 8.5 s each (customize and start), so about 15 minutes
  plus the table requests.

## 2026-11-19: L5: snapping rule, graph rebuilt, calibration, corridors and G1 timings

Same machine as the entry above. Code: `71b9239` plus the snapping change below (not yet committed).

### A change: points snap to the main road network only

- The first corridor build had two legs with no path on the whole graph: Nadeem-16-B Bilawal Chowrangi to
  Hyperstar, and Nadeem-21 Lucky Star to FTC. Calibration counted 0.57% of 50,004 pairs unreachable.
- Cause: two stops snapped onto road pieces with no way back to the city. Hyperstar (2.8 m) was on a one-way
  parking aisle (way 483398850, `service=parking_aisle`, `oneway=yes`); FTC (65.6 m) on a 9-node piece of
  service road (way 1044817432) joined to the city only by one-way links. The other 310 points were in the
  largest strongly connected part of the graph, which holds 99.6% of its nodes.
- OSRM does not snap a point onto such a piece when a road of the main network is near, which is why the M1
  matrix has times for both legs. The graph now does the same: `build_graph.py` snaps only to map nodes of
  the largest strongly connected part (`main_component_ids`), and `Graph.nearest_node` returns only nodes of
  that part (`Graph.main_nodes`). Three tests added; four toy tests whose campus sat on the toy map's one-way
  dead end updated to the rule. 224 solver and graph tests pass.
- New snaps: Hyperstar 6.9 m, FTC 77.5 m. Boat Basin is still the only point over 200 m (224.4 m).

### Graph and calibration (graph rebuilt with the rule)

| Nodes | Edges | Segments | Speed factor | Median abs. error | Median signed error | Unreachable pairs |
| --- | --- | --- | --- | --- | --- | --- |
| 195,556 | 543,459 | 927,766 | 1.2493 | 8.05% | +3.05% | 0.00% of 50,004 |

Rule (work plan Section 6.2): median absolute error at most 15%, signed error not negative. **Pass** with one
factor; `--per-class` not needed. Before the rule change: factor 1.2487, 8.08%, +3.07%, 0.57% unreachable.

### Corridors (`data/corridors_fall2026_v1/`)

52 corridors, 1500 m buffer: nodes smallest 9,728 (Jadoon-R-20), median 15,860, largest 26,737 (Jadoon-R-5),
about 8% of the city graph. No stop outside its corridor and no unreachable leg.

### G1 timings (`results/graph-timing/timing.json`)

Route Jadoon-R-6 (13 stops, corridor 24,259 nodes). Limited: `MemoryMax=512M`, `MemorySwapMax=0`,
`CPUQuota=10%`, read back from the kernel. Wall seconds, worst repeat:

| Rows | Corridor, limited | City, limited | Corridor, no limits | G1 rule |
| --- | --- | --- | --- | --- |
| 1 | 0.60 | 4.30 | 0.04 | - |
| 14 | 1.21 | 8.60 | 0.10 | at most 5 s on the corridor: **pass** |
| 31 | 2.30 | 19.30 | 0.31 | at most 30 s on the corridor: **pass** |

- Peak memory 213 MB in both modes (under the 512 MB limit); graph load 0.28 s limited.
- Under 0.1 CPU the wall time is about 10 times the CPU time, as expected. The city-wide fallback is 7 to 8
  times slower than the corridor and is not judged.
- A first run on the graph before the rule change also passed (14 rows 0.81 s, 31 rows 1.60 s worst, limited);
  the numbers above replace it.

Gate G1 now stands at four of five: road-block answers, calibration, corridor timings and R3 exactness pass.
The walking-distance file is left.

## 2026-11-19: L4: walking distances between stops (`data/walk_fall2026_v1.json`)

Same machine. Foot build of OSRM made from the same map file (`a99d2f81...c9dc322`) in
`~/fleetcentric-osrm/foot/`: 420,108 nodes and 511,624 edges after extraction, peak memory 389 MB, about
20 s for extract, partition and customize together.

`build_walk.py`: one table call over the 311 stops with `annotations=distance`; pairs kept within 1,200 m
in a straight line and 1,000 m of walking.

| Statistic | Result | Expected (offline-builders, Task 3) |
| --- | --- | --- |
| Directed pairs kept | 700 (124 within 400 m, 458 within 800 m) | - |
| Walk metres of kept pairs | 42 to 998, median 680 | - |
| Detour factor (median walk / straight line, pairs within 800 m) | 1.38 | about 1.2 to 1.6; below 1.0 would mean distances and durations were mixed up |
| Stop visits with a same-route stop within 400 m walk | 17.2% | below the straight-line 30% of 15 Nov |
| Stop visits with a same-route stop within 800 m walk | 48.0% | below the straight-line 65% of 15 Nov |

All three as expected. At the default 400 m limit fewer than one stop in five has a same-route neighbour to
walk to, so the walking option will matter in a minority of scenarios; at 800 m it is about half. This bounds
how much R2 and R3 can gain over R0 by moving students, before any closure is placed.

With the walking file, gate G1 is met on all five items (the file is committed with this entry).

## 2026-11-19: Combined matrix (`data/matrix_fall2026_v1_all.json`)

Same machine; untouched car build (`~/fleetcentric-osrm/car/`) on port 5000. `build_matrix.py --combined`:
312 x 312 (campus and 311 stops), one table call, 0 unreachable pairs. One point moved more than 200 m to a
road: Boat Basin, 224 m, as in run M1 and the road graph.

Check against the saved per-contractor matrix `matrix_fall2026_v1.json`: Jadoon 29,584 pairs and Nadeem 20,736
pairs, **0 differ by more than 0.1 s**. The car build is the one of run N1, so the saved matrices stay version 1.
This unblocks All and All-doubled of run OS1 (optimizer-scaling, Task 3), run next into
`results/optimizer-scale-wsl/`.

## 2026-11-19: OS1 completed: All and All-doubled (`results/optimizer-scale-wsl/`)

Machine: `DESKTOP-15B12RB`, WSL2, Intel Core i5-7300U, 4 CPUs, no limits (Linux peak RSS). Code `975760c`.
4 of 4 runs ok, 300 s each, one at a time in fresh processes, nothing else running. These rows are not pooled
with the 17 Nov rows from the Windows laptop (`results/optimizer-scale/`), as the rules entry of 17 Nov says.

| Instance | Stops / buses | Lookup | Build (s) | First plan (s) | Peak (MB) | Ride 10 s | Ride 60 s | Ride 300 s | Scored 300 s (student-min) | Longest ride (min) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| All | 311 / 53 | callback | 0.016 | 0.19 | 74 | 65,824 | 63,123 | 62,936 | 60,995 | 58.9 |
| All | 311 / 53 | matrix | 0.047 | 0.12 | 83 | 68,347 | 64,075 | 63,053 | 61,119 | 56.6 |
| All-doubled | 622 / 106 | callback | 0.014 | 0.62 | 94 | 145,289 | 125,635 | 122,499 | 119,011 | 55.5 |
| All-doubled | 622 / 106 | matrix | 0.2 | 2.38 | 130 | 161,538 | 147,729 | 133,565 | 129,159 | 89.1 |

1,806 students (All) and 3,612 (All-doubled); no stop dropped in any run.

- Memory stays small: 74 MB at 311 stops and 94 MB at 622 with the callback, far under 512 MB.
- Convergence weakens with size. With the callback the 60 s plan is 0.30% above the 300 s plan at 311 stops
  (as for the contractor instances on 17 Nov) but 2.6% above it at 622 stops, and the search was still improving
  at 300 s (2,211 improvements). Under 0.1 CPU, 300 CPU-s is about 50 minutes of wall time, so a combined-fleet
  plan of twice today's size would not fit the 300 s wall budget fixed after B1 on a free-tier server.
- The matrix lookup is worse again, and much worse at 622 stops: 0.19% at 300 s for All, 9.0% for All-doubled,
  where its plan also has a 89-minute longest ride against 56 with the callback. This confirms the 17 Nov decision:
  the callback stays the default.
- Whether planning both fleets together beats planning each contractor alone is not answered here: the
  contractor rows were measured on another machine and are not compared with these.

Run OS1 is complete: 12 of 12 runs over the two machines.

## 2026-11-19: Historical closures pinned (`data/raw/historical_closures.json`)

Candidate end points were taken from the map file itself (the map node where the named carriageway meets the
named junction), then each was checked by Hassan on OpenStreetMap: on the carriageway, not on a flyover, slip
road or service lane, and at the right junction. The route line between each pair was checked on
OpenStreetMap's router and again on the untouched N1 car build (port 5000), with step names:

| Stretch | From | To | Length | Roads on the route | Factor |
| --- | --- | --- | --- | --- | --- |
| Shahrah-e-Faisal, Karsaz to FTC | 24.874816, 67.096223 (Karsaz Road junction) | 24.859143, 67.052244 (FTC) | 4,863 m | Shahrah-e-Faisal only (the map spells it three ways) | 0.0, full block |
| University Road, Hasan Square to NIPA | 24.900705, 67.072522 (Hasan Square, under the flyover) | 24.917938, 67.097152 (NIPA Chowrangi) | 3,142 m | University Road only (one way name, in Urdu) | 0.25, slowed |

OSRM moved none of the four points (0 m). Both stretches close both directions (60 m circles every 100 m
along the line, `build_scenarios.py`). The file is frozen from here, with the scenarios.
