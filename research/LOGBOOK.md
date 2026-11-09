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
