# Route Optimization under Free-Tier Limits

Draft of 15 November 2026, updated 17 November 2026, written from `research/LOGBOOK.md` (runs D1, N1, M1,
O0, O1, B1, Q1, T1, S1, OS1).
Every number in this chapter is in the logbook or in the result files under `research/results/`.

## 1. Introduction

FAST NUCES Karachi runs its shuttle service on 52 morning routes operated by two contractors. The routes
are made by hand: someone chooses which stops go on which bus and in what order, and the transport
system then draws the road path through that order. Nothing in the process says whether the order is a
good one.

This chapter tests whether the routes can be planned by an optimizer instead, on the kind of server a
self-funded student project can afford. The reference machine is a free-tier web service with 512 MB of
memory, no swap and one tenth of a CPU core. The question is:

> Can all-stop routes be built from a travel-time matrix within free-tier CPU and query limits, and how
> do they compare with the current hand-made routes?

The question has three parts, each answered by an experiment whose pass or fail rule was written down
before it ran:

1. **Time.** Under the free-tier limits, how close does the optimizer get to the best plan it can find,
   and how long does it need?
2. **Queries.** A deployed planner pays for every travel time it asks a routing engine for. How few real
   travel times still give good routes?
3. **Robustness.** Do the results survive slower roads and a different draw of students?

The original proposal framed the research around memory. An early calculation changed that: the travel
times for 280 stops take about 0.3 MB, so memory cannot be the limit that binds. The limits that bind on
free hosting are CPU time and the number of travel-time queries, and the research questions were reset
to those on 21 October 2026. Section 9 lists what else changed from the proposal.

The main results are these. The best plans cut total student ride time by 21.8% (Jadoon) and 20.5%
(Nadeem) against the current routes. Under the free-tier limits the optimizer is within 3.7% and 2.6% of
those plans after 60 seconds and within about 1% after 300 seconds, using 65 MB of memory. Querying only
each stop's ten nearest stops, about 7% of the full matrix, costs less than 1% in plan quality. The
improvement stays near 20% when every travel time is multiplied by 1.5 and when the students are
redrawn. All of this rests on synthetic students and free-flow travel times, which Section 9 discusses.

## 2. Background

Planning school or university shuttles is the School Bus Routing Problem (SBRP): choose stops, assign
students to them, group stops into routes that respect bus capacity and ride-time limits, and order the
stops on each route [1], [2]. It generalises the Capacitated Vehicle Routing Problem, which is NP-hard,
so practical solvers are heuristics and metaheuristics rather than exact methods [3]. This chapter takes
the stops and the students at each stop as given and studies the last two steps, grouping and ordering.
Stop selection with a walking limit [10] is left to the rerouting part of the project, where it is the
central idea.

Two tools carry the work. Google OR-Tools provides a routing solver that builds a first solution with a
constructive heuristic and improves it with local search under a metaheuristic [4]; the one used here is
guided local search, which penalises features of local optima so the search moves on [5]. The Open
Source Routing Machine (OSRM) computes road travel times over OpenStreetMap data and returns a full
table of pairwise times in one call [6]. OSRM offers two preprocessing pipelines. This project uses the
multi-level Dijkstra pipeline, an implementation of customizable route planning [7], because a changed
road speed can then be applied by re-running one short step, which the rerouting work depends on.

Work on very large routing instances shows that a solver does not need every pairwise distance: pruning
each customer's neighbourhood to its nearest candidates keeps quality high while the instance grows
[8], [9], [11]. The query-budget experiment in Section 7.3 applies the same idea for a different reason.
The aim there is not speed on a large instance but fewer paid queries on a small one.

Published routing studies report solution quality against running time on capable hardware. They rarely
state what a small shared server can do, and they do not count routing-engine queries as a cost. Those
two measurements are what this chapter adds.

## 3. Problem model

The model was fixed on 3 November 2026, before any optimizer run.

**Setting.** Each contractor is planned separately, with its own stops and its own buses. A stop served
by both contractors appears in both problems with each contractor's own students. Only the morning run
to campus is modelled.

**Routes.** A bus starts at its first stop, visits stops in order and ends at campus. It does not wait
between stops. Every bus arrives at campus at exactly 08:00, so each route's departure time follows from
its length.

**Stop time.** A stop with $q_i$ students takes $60 + 5\,q_i$ seconds.

**Constraints.**

- Every stop is visited exactly once, by one bus. A stop may be left out only if no plan can serve it,
  which the model allows at a very large penalty so that an infeasible case is reported, not hidden. No
  run in this chapter left a stop out.
- The students on a bus never exceed its seats. Buses have 30 to 60 seats.
- No student rides longer than 90 minutes.

**Ride time.** A student's ride time $r_i$ is the time from the bus reaching the student's stop to its
arrival at campus. It includes the stop time at the student's own stop and at every later stop.

**Objective.** Minimise total student ride time,

$$\min \; \sum_{i} q_i \, r_i \;+\; \text{(driving seconds of all buses)},$$

where the second term is small beside the first and acts as a tie-breaker. The unit reported throughout
is the student-minute.

The objective was chosen over "fewest buses first" because the fleet is already contracted for the
semester. One consequence should be stated plainly: an objective that rewards short rides uses every bus
it is given. Nadeem has 26 buses and 25 current routes, and every optimized Nadeem plan uses all 26.
Jadoon has 27 routes and 27 buses in the dataset, so the comparison there is bus for bus.

**Scoring.** The current routes are scored by the same function on the same travel-time matrix as the
optimized plans (`optimize.py: score`), so both are measured the same way.

## 4. Dataset and road network

### 4.1 Dataset (run D1)

The dataset, version `fall2026-v1`, is built by `build_instance.py` from the Fall 2026 route plan, the
stop list and the bus list. It is frozen: every experiment reads the same file, and a rebuild gives a
byte-identical result (checked by file hash on two machines).

| Item | Jadoon | Nadeem | Total |
| --- | --- | --- | --- |
| Stops | 171 | 143 | 311 unique (3 shared) |
| Current routes | 27 | 25 | 52 |
| Buses | 27 | 26 (1 spare) | 53 |
| Seats | 1,220 | 1,195 | 2,415 |
| Students (synthetic) | 906 | 900 | 1,806 |

Three rules shaped it:

- **Locations.** Stop locations are used as given. Eleven stops had none and were placed from their
  neighbours on the route, evenly between located neighbours or in 300 m steps at a route's start or
  end. They are marked as interpolated in the file.
- **Merging.** Two stops with the same name, or within 25 m of each other, are one stop. This is the
  rule the transport system itself uses when importing stops. It merged three pairs.
- **Buses.** The bus list is synthetic. Jadoon ran 27 routes with 26 listed buses, so one 45-seat bus
  was added. Larger buses were given to routes with more stops.

**Students are synthetic.** The team had no access to real registrations. Each current route's bus was
filled to a load factor drawn uniformly between 65% and 90% of its seats, and those students were spread
over the route's stops with log-normal weights (sigma 0.6), with at least one student per stop, under
random seed 2026. This gives 1 to 19 students per stop (median 5) and route load factors of 0.66 to 0.90
(mean 0.78). The current routes are feasible by construction, and the optimizer must serve exactly the
same students.

### 4.2 Road network and travel times (runs N1, M1)

The road network is the Geofabrik extract of OpenStreetMap for Pakistan dated 2 November 2026, cut to a
box around Karachi (66.90, 24.70 to 67.45, 25.15) and processed with OSRM 5.27.1 using the car profile.
The graph has 409,528 nodes and 582,290 edges. Partitioning took 6.5 s and customizing 4.5 s on a team
laptop, with peak memory of 214 MB and 291 MB.

One OSRM table call per contractor gave the full directed matrices of driving times and distances
between campus and every stop: 172 x 172 for Jadoon and 144 x 144 for Nadeem, 50,320 cells in two calls.

| Item | Jadoon | Nadeem |
| --- | --- | --- |
| Unreachable pairs | 0 | 0 |
| Largest move to reach a road | 80 m | 224 m (Boat Basin, kept) |
| Free-flow time to campus, min / median / max | 13 / 28 / 40 min | 9 / 27 / 39 min |
| Median difference between A to B and B to A | 8% | 7% |

Two properties matter for what follows. The times are free-flow: OSRM assumes empty roads, so real
morning times are higher. And the matrix is not symmetric, because of one-way roads and divided
carriageways, so the optimizer uses the full directed matrix.

## 5. Optimizer

The optimizer (`optimize.py`) is a direct statement of the model in Section 3 for the OR-Tools routing
solver, version 9.15 [4]. It uses one vehicle per bus with that bus's capacity, a time dimension that
carries the 08:00 arrival and the 90-minute limit, and a cost on each stop's arrival time weighted by
its students, which is the ride-time objective. The first solution comes from the path-cheapest-arc
heuristic and is improved by guided local search [5] until a time limit.

The solver is given no tuning beyond these choices. Each experimental run is a fresh process, so memory
is measured per run. Repeats of one setting can return different plans, because the time limit stops
the search at a slightly different point each time; this is why settings are repeated.

Two development runs on an unthrottled machine checked the model before any experiment. With a 20 s
limit (run O0) the plans were 21.5% and 19.7% better than the current routes; with 60 s (run O1) they
improved by a further 0.2% and 0.5%. Neither is a reported result. They showed that the search flattens
early on a fast machine, which is the behaviour the time-budget experiment then tested under limits.

## 6. Experimental method

**Rules fixed before running.** For each experiment, the question, design and pass or fail thresholds
were written in the logbook before the first run. The thresholds are also constants in the experiment
scripts. For the traffic and seed checks, the logbook entry reached the shared repository in a commit
earlier than the code version recorded in the runs, so the order can be shown from the history. For the
query-budget experiment the entry, script and results reached the repository in one commit, so there the
order rests on the logbook alone.

**Free-tier limits.** The limits are applied with Linux control groups through `systemd-run`: 512 MB of
memory, no swap, and a CPU quota of 10%. This is the kernel mechanism a container runtime uses. Before
the runs, the experiment starts a limited process and reads back what the kernel applied
(`memory.max=536870912`, `memory.swap.max=0`, `cpu.max=10000 100000`); if the values differ, nothing
runs. A run that exceeds the memory limit is killed and counted as a failure.

**Measures.** The quality of a plan is its total student ride time. A gap is the percentage by which a
plan exceeds a reference plan. Each run also records the longest ride, buses used, stops left out, wall
and CPU time, peak memory, and the time from launch to the first valid plan.

**Repeats.** Settings are repeated three times and the median is reported, with the range where it
matters. From 10 November the team also judges thresholds on the worst repeat; the time-budget and
query-budget experiments keep the median rule they were run under.

**Machines.** All runs were on team laptops under WSL2 with OR-Tools 9.15.6755. The time-budget
experiment ran on an Intel i7-3770, the query-budget experiment on an i5-4310U, and the two robustness
checks on an i5-7300U. Each experiment's machine details are saved with its results. The scaling run
OS1 (Section 7.6) is the exception: it ran on a Windows laptop without WSL, has no threshold and is not
counted in the table below.

| Experiment | Runs | Search budget | Setup | Threshold |
| --- | --- | --- | --- | --- |
| Time budget (B1) | 50 | 10, 60, 300, 600 s; 1,800 s reference | limited and unlimited | limited within 5% of best known at 60 s; peak memory under 400 MB, none killed |
| Query budget (Q1) | 72 | 60 s | unlimited | `graph` estimator at K = 10 within 3% of the full matrix; nobody over 90 min at K >= 10 |
| Traffic check (T1) | 18 | 60 s | unlimited | at x1.5, every run at least 15% better than current routes; nobody over 90 min, no stop left out |
| Seed check (S1) | 8 | 60 s | unlimited | on new seeds, every run at least 15% better than current routes; nobody over 90 min, no stop left out |

All 148 planned runs finished and are included; no finished run was excluded. In the query-budget
experiment a first start failed before any search because OR-Tools was not installed on that laptop, and
a later interruption lost two runs in progress. Those runs were started again with the same settings,
and the failed rows are kept in `runs.jsonl` as a record.

## 7. Results

### 7.1 Optimized plans against the current routes

The best plan found for each contractor came from the 30-minute unlimited reference run of experiment B1.

| Measure | Jadoon | Nadeem |
| --- | --- | --- |
| Current hand-made routes (student-min) | 40,201 | 37,280 |
| Best known plan (student-min) | 31,447 | 29,639 |
| Change against current routes | -21.8% | -20.5% |
| Longest ride, current / best plan (min) | 78.7 / 53.0 | 65.6 / 56.6 |
| Buses used, current / best plan | 27 / 27 | 25 / 26 |

On the synthetic students this is 9.7 minutes less per student per morning for Jadoon and 8.5 for
Nadeem. Every plan in every run visited every stop, kept every bus within its seats and kept every
student under 90 minutes.

### 7.2 Time budget (run B1)

Each contractor was solved at four search budgets, three times each, with and without the free-tier
limits, plus the reference run: 50 runs between 4 and 6 November. Table entries are the median total
student ride time and its gap to the best known plan.

| Budget | Jadoon limited | Nadeem limited | Jadoon unlimited | Nadeem unlimited |
| --- | --- | --- | --- | --- |
| 10 s | 38,056 (21.0%) | 35,337 (19.2%) | 32,122 (2.2%) | 30,227 (2.0%) |
| 60 s | **32,599 (3.7%)** | **30,414 (2.6%)** | 31,519 (0.2%) | 29,898 (0.9%) |
| 300 s | 31,607 (0.5%) | 29,951 (1.1%) | 31,472 (0.1%) | 29,765 (0.4%) |
| 600 s | 31,519 (0.2%) | 29,898 (0.9%) | 31,472 (0.1%) | 29,716 (0.3%) |

**Verdict.** Both thresholds pass. At 60 s the limited setup is within 5% of the best known plan for
both contractors (3.7% and 2.6%). Peak memory in limited runs was 65 MB against a 400 MB threshold, and
no run was killed.

Four observations follow from the runs.

- **The CPU cap is a tenfold slowdown, nothing more.** A limited run of 600 s uses 60 CPU-seconds and
  returns the same plan as an unlimited run of 60 s, to the student-minute, for both contractors (31,519
  and 29,898). Plan quality depends on solver CPU-seconds. This also settles a practical point: the
  solver's time limit counts wall-clock time, so on a capped server the limit must be set ten times
  longer for the same result.
- **Ten seconds is too short on the free tier.** Loading the data and building the model take 3 to 4 s
  at 0.1 CPU, which leaves under one CPU-second of search. The plans are about 20% from the best and
  have longest rides of 88 to 90 minutes, at the limit.
- **Sixty seconds passes but is not comfortable.** For Jadoon the three limited repeats at 60 s were
  1.7%, 3.7% and 4.6% from the best, and two of them had a longest ride of 88 to 90 minutes. The total
  is good, but the worst-off student is not. At 300 s both problems go away: gaps of 0.4% to 1.1% and
  longest rides of 55 to 64 minutes.
- **The search flattens quickly.** Doubling the limited budget from 300 s to 600 s gains 0.2 to 0.3
  percentage points.

Even the 60 s limited plans are 18.9% (Jadoon) and 18.4% (Nadeem) better than the current routes. The
recommended setting for a nightly re-plan on the free tier is 300 s per contractor, with 60 s as the
minimum. The first valid plan is available 3.5 to 4.9 s after launch under the limits, and 0.6 to 1.2 s
without them.

### 7.3 Query budget (run Q1)

The full matrices of run M1 serve as ground truth. Each run pretends to have queried only some cells:
every stop's leg to campus, plus its legs to its K nearest stops by straight-line distance, for K = 0,
3, 5, 10, 20 and 40. Choosing the neighbours needs only coordinates. The remaining cells are estimated
from the queried ones by one of two estimators:

- `crowfly`: a least-squares line, time = a + b x straight-line distance.
- `graph`: the shortest path through the queried legs, falling back to `crowfly` where no path exists.

The optimizer plans on the estimated matrix, and the plan is then scored on the real matrix, so the
score is what students would actually ride. The search budget is 60 s unlimited, which B1 showed equals
600 s on the free tier, so search time is not the bottleneck and only the matrix changes. The gap is
measured against the full-matrix control in the same experiment (Jadoon 31,519, Nadeem 29,898
student-minutes, identical to B1 at this budget).

| Queried legs per stop | Share of full matrix (Jadoon / Nadeem) | Jadoon `crowfly` | Jadoon `graph` | Nadeem `crowfly` | Nadeem `graph` |
| --- | --- | --- | --- | --- | --- |
| campus only (K = 0) | 0.6% / 0.7% | 5.3% | - | 5.6% | - |
| K = 3 | 2.3% / 2.8% | 3.7% | 4.0% | 2.9% | 2.5% |
| K = 5 | 3.5% / 4.2% | 3.5% | 2.4% | 1.7% | 1.9% |
| **K = 10** | 6.4% / 7.7% | 2.1% | **0.8%** | 1.1% | **0.1%** |
| K = 20 | 12.3% / 14.7% | 1.3% | 0.4% | 0.3% | 0.2% |
| K = 40 | 24.0% / 28.7% | 1.0% | 0.2% | -0.2% | -0.1% |

The control's own three repeats differ by up to 0.07% (Jadoon) and 0.3% (Nadeem), so gaps below about
0.3%, including the small negative ones, are noise.

**Verdict.** Both thresholds pass. The `graph` estimator at K = 10 is within 3% of the full matrix for
both contractors (0.84% and 0.09%), and none of the 36 runs with K of 10 or more had a student over 90
minutes on real times. In fact no run at any K did.

Three observations follow.

- **About fifteen times fewer queries cost under 1%.** K = 10 needs 1,881 cells for Jadoon and 1,573 for
  Nadeem, against 29,241 and 20,449. Good routes are made of short legs between neighbouring stops, and
  those are the legs that were queried: with `graph` at K = 10, 91% (Jadoon) and 97% (Nadeem) of the legs
  in the final plans were real queried times.
- **The direction of the estimate's error matters more than its size.** At K = 10 the `graph` estimator
  is far less accurate on the cells it estimates (it overestimates them by a median of 47% and 45%) than
  `crowfly` (12% and 10% absolute error), yet it plans better. `crowfly` underestimates (by 9.5% and
  6.2%), which makes long unqueried hops look cheap. The optimizer then uses them, and the plan is worse
  than it believes: Jadoon's `crowfly` plan at K = 10 scored 31,460 on its own matrix but 32,185 on real
  times. An overestimate keeps the plan on real legs, and its expected score matches the real one
  (31,774 against 31,784). The rule this gives is to err high when a travel time must be guessed.
- **Even no stop-to-stop queries gives a usable plan.** With only the legs to campus queried (K = 0),
  the plan is 5.3% and 5.6% from the full-matrix plan and still 17% and 15% better than the current
  routes on real times.

The `graph` estimator needs K of at least 10 to work as intended. At K = 3 the nearest-neighbour legs do
not yet form a connected network, and the estimator falls back to the straight-line fit for most cells
(90% of Jadoon's estimated cells); from K = 10 the fallback is under 5%.

### 7.4 Traffic check (run T1)

The matrix holds free-flow times. This check multiplies every travel time by 1.0 (control), 1.3 and 1.5,
leaves stop times unchanged, plans on the scaled matrix and scores on it, with the current routes scored
the same way. Three repeats per setting.

| Travel times | Contractor | Current routes (student-min) | Optimized, median (student-min) | Better than current, median (range) | Longest ride, optimized (min) | Current routes: stops over 90 min |
| --- | --- | --- | --- | --- | --- | --- |
| x1.0 | Jadoon | 40,200 | 31,736 | 21.1% (20.7 to 21.4) | 53.9 to 56.3 | 0 |
| x1.0 | Nadeem | 37,281 | 29,924 | 19.7% (19.7 to 19.7) | 56.6 | 0 |
| x1.3 | Jadoon | 50,433 | 39,987 | 20.7% (20.6 to 20.9) | 69.4 to 70.3 | 2 |
| x1.3 | Nadeem | 46,817 | 37,661 | 19.6% | 71.0 | 0 |
| **x1.5** | Jadoon | 57,256 | 45,210 | **21.0% (20.5 to 21.1)** | 77.3 to 79.4 | 8 |
| **x1.5** | Nadeem | 53,180 | 42,653 | **19.8% (19.8 to 19.8)** | 83.6 | 2 |

**Verdict.** Both thresholds pass, judged at x1.5 on the worst run: the smallest improvement is 20.5%
(Jadoon) and 19.8% (Nadeem) against a threshold of 15%, and no optimized plan has a student over 90
minutes or leaves a stop out.

The 90-minute limit is where slower roads bite, and they bite the current routes first. At x1.3 two of
Jadoon's current stops have rides over 90 minutes; at x1.5 eight of Jadoon's and two of Nadeem's do, with
longest rides of 110 and 91 minutes. The optimized plans stay under the limit, though Nadeem's margin at
x1.5 is small (83.6 minutes). Factors above 1.5 were not tested.

The check also re-scored the control plans, made on free-flow times, on the slower matrices. At x1.5
they are within 0.4% of the plans made for x1.5 and also keep every student under 90 minutes. Planning
for a uniform slowdown therefore gains almost nothing. This is expected, because slowing every road
equally barely changes which plan is best, and it says nothing about uneven traffic.

### 7.5 Seed check (run S1)

The students are one random draw. This check redraws them under seeds 2027, 2028 and 2029 with the rule
of Section 4.1, over the same current routes, stops, buses and travel times, and runs the optimizer once
per contractor and seed. Seed 2026, the frozen dataset, is the control.

| Seed | Contractor | Students | Current routes (student-min) | Optimized (student-min) | Better than current | Longest ride, optimized (min) |
| --- | --- | --- | --- | --- | --- | --- |
| 2026 (control) | Jadoon | 906 | 40,200 | 31,792 | 20.9% | 53.9 |
| 2026 (control) | Nadeem | 900 | 37,281 | 29,921 | 19.7% | 56.6 |
| 2027 | Jadoon | 946 | 41,675 | 33,117 | 20.5% | 60.2 |
| 2027 | Nadeem | 923 | 37,695 | 30,629 | **18.8%** | 56.7 |
| 2028 | Jadoon | 984 | 45,871 | 34,617 | 24.5% | 59.0 |
| 2028 | Nadeem | 890 | 36,670 | 29,307 | 20.1% | 59.7 |
| 2029 | Jadoon | 941 | 43,175 | 32,974 | 23.6% | 56.2 |
| 2029 | Nadeem | 913 | 39,594 | 30,685 | 22.5% | 52.5 |

**Verdict.** Both thresholds pass, judged on the three new seeds: the smallest improvement is 18.8%
against a threshold of 15%, and no run has a student over 90 minutes or leaves a stop out. The
improvement is not specific to seed 2026.

### 7.6 Model size and arc lookup (run OS1)

This run asks how build time, memory and plan quality grow with the number of stops and buses, and
whether handing OR-Tools the travel times as tables (`matrix` lookup) beats the Python callback every
other run used (`callback` lookup). Besides Jadoon and Nadeem it uses doubled instances, where every
stop and bus is copied, each copy 30 s from its original with the same students. They test model size,
not geography. Each instance ran once per lookup for 300 s, in a fresh process. It has no threshold and
reports curves (logbook, 17 November 2026, scaling results).

| Instance | Stops / buses | Peak memory, callback / matrix (MB) | Cost at 10 s, callback / matrix | Cost at 300 s, callback / matrix | Scored at 300 s, callback / matrix (student-min) |
| --- | --- | --- | --- | --- | --- |
| Nadeem | 143 / 26 | 52 / 54 | 30,945 / 31,003 | 30,647 / 30,697 | 29,723 / 29,752 |
| Jadoon | 171 / 27 | 53 / 55 | 32,730 / 33,012 | 32,474 / 32,474 | 31,472 / 31,472 |
| Nadeem-doubled | 286 / 52 | 61 / 67 | 60,948 / 64,318 | 59,355 / 59,460 | 57,704 / 57,780 |
| Jadoon-doubled | 342 / 54 | 63 / 73 | 66,211 / 68,997 | 63,447 / 63,547 | 61,614 / 61,698 |

"Cost" is the solver's own objective divided by 60 (student-minutes plus a small driving tie-breaker);
"scored" is the returned plan's total student ride time, scored as in B1. No run left a stop out.

- **Size is cheap.** Doubling the stops and buses raised peak memory by 9 to 18 MB, and building the
  model stayed under 0.1 s.
- **The search converges at this size.** With the callback, the 60 s plan is within 0.16% of the 300 s
  plan at 342 stops (0.02% for Jadoon, 0.30% for Nadeem), so the 300 s budget chosen after B1 still holds
  for the current fleet.
- **The matrix lookup does not help.** It is never better at 300 s (equal for Jadoon, 0.16 to 0.18% worse
  elsewhere), is 0.2 to 5.5% worse at 10 s, and uses 2 to 10 MB more. The callback stays the default.

The caveats are larger than for the other experiments. The run was on a Windows laptop (Intel Core i7
third generation, 4 cores, 8 GB) where WSL cannot start, so it had no free-tier limits, and peak memory
is Windows' peak working set rather than Linux's `ru_maxrss`; its figures are not pooled with B1, Q1, T1
or S1. Only 8 of the 12 planned runs exist: the combined instances All (311 stops, both fleets in one
model) and All-doubled (622) need a combined travel-time matrix that needs OSRM, and they run on the
Docker laptop together with timings under the limits. The run was interrupted once and resumed, with
light other work on the laptop during the resumed part.

## 8. Discussion

**What the results say about the research question.** On this dataset, all-stop routes can be built
within free-tier limits. Memory is not a constraint at all: 65 MB is 13% of the 512 MB available. CPU is
the constraint, and it behaves simply. One tenth of a core means ten times the waiting for the same
plan, and 300 s of waiting is enough to be within about 1% of the best plan found in 30 minutes on an
unrestricted machine. A planning job that runs once a night, or once a semester, can afford that.

**Why the routes improve by about 20%.** The comparison is against routes scored in the same model, so
the gain is a property of the stop grouping and ordering, not of the scoring. The optimized plans
shorten the longest ride as well as the total: from 78.7 to 53.0 minutes for Jadoon. A measure the
current routes cannot be given credit for is anything outside the model, such as roads a bus cannot
use, areas a driver knows, or arrangements made with students. Section 9 returns to this.

**What the query result means in practice.** A deployed planner would not need the whole matrix. It
could ask a routing engine for each stop's leg to campus and its ten nearest stops, about 7% of the
cells, fill the rest by shortest paths through those legs, and lose under 1%. How cells translate into
cost depends on the provider: OSRM answers a whole table in one call, while hosted matrix services
usually charge by cell. The result is stated in cells for that reason.

**What carries into rerouting.** Three findings shape the next part of the project.

1. *Budget.* The standard search budget for planning runs is now 300 s, with 60 s as the minimum.
   A rerouting decision has seconds, not minutes, so it cannot re-run this optimizer; it needs a
   smaller problem (one bus) and a method that always has an answer ready.
2. *Queries after a block.* When a road is blocked, travel times change. The query result suggests
   re-querying only nearest-neighbour legs and estimating the rest.
3. *Err high.* When a travel time must be estimated, an overestimate is safer than an underestimate,
   because the plan then avoids the legs it knows least about.

## 9. Limitations

- **Students are synthetic.** Stop-level demand is drawn from a rule, not from registrations. The rule
  fills each current route's own bus, so the current routes are feasible by construction and their
  loads are balanced by design. Real demand may be more uneven. The seed check varies who boards where
  under the same rule; it does not test a different rule. The absolute savings in student-minutes are
  therefore estimates, and the analysis should be repeated when registration data is available.
- **Travel times are free-flow and unvalidated.** The matrix comes from OSRM's default speeds, not from
  measured trips, and the buses carry no GPS trackers whose records could check it. The traffic check
  applies one multiplier to every road, which is not how congestion behaves. It supports the 90-minute
  limit and the size of the saving under a general slowdown, not a claim about real rush-hour routes.
- **The current routes are judged inside the model.** They may follow rules the model cannot see, and
  their real departure times were not used. The 20% figure compares two plans under one set of
  assumptions. It is not a measurement of time students would save.
- **The bus counts differ for Nadeem.** The optimized Nadeem plans use 26 buses and the current routes
  25. Part of Nadeem's improvement may come from the extra bus. No run was made with Nadeem held to 25
  buses.
- **The free tier is simulated.** The limits are the kernel's, applied on a laptop. A real shared host
  may add effects this does not capture, such as noisy neighbours, cold starts or a request timeout.
- **One solver, one configuration.** The proposal planned a hand-built heuristic and a metaheuristic
  compared against OR-Tools, student-to-stop assignment, and standard benchmark instances. These were
  dropped when the questions were reset on 21 October 2026. The gaps in this chapter are to the best
  plan this solver found, not to a proven optimum, and no claim is made about other solvers.
- **Small differences between control runs.** At the same 60 s unlimited budget, the control runs of
  the robustness checks (Jadoon 31,603 to 31,884) are not identical to those of B1 and Q1 (31,519).
  `run_robustness.py` rounds travel times to whole seconds where the other scripts leave the solver to
  truncate them, and the machine differed; which of these explains the difference was not tested. It is
  under 1.2% and affects no verdict.
- **Morning runs only.** Evening runs, where students are dropped off and walk home, were not modelled.

## 10. Summary

On a frozen dataset of 311 stops, 53 buses and 1,806 synthetic students, an OR-Tools optimizer cut total
student ride time by about a fifth against the current hand-made routes and shortened the longest ride.
Under free-tier limits it reaches within 3.7% of its best plan in 60 s and about 1% in 300 s, in 65 MB
of memory. It needs real travel times for only each stop's ten nearest stops. The improvement holds
when roads are uniformly 50% slower and when students are redrawn. All four experiments passed
thresholds fixed before they ran.

The answer to the research question is yes, with the caveats of Section 9: the limits of free hosting
do not prevent good route planning at this scale. What they do prevent is using the same method to
react within seconds to a blocked road. That is the subject of the rerouting part of this project.

## References

[1] J. Park and B.-I. Kim, "The school bus routing problem: A review," *European Journal of Operational
Research*, vol. 202, no. 2, pp. 311-319, 2010.

[2] W. A. Ellegood, S. Solomon, J. North, and J. F. Campbell, "School bus routing problem: Contemporary
trends and research directions," *Omega*, vol. 95, art. 102056, 2020.

[3] P. Toth and D. Vigo, Eds., *Vehicle Routing: Problems, Methods, and Applications*, 2nd ed.
(MOS-SIAM Series on Optimization). Philadelphia, PA, USA: SIAM, 2014.

[4] L. Perron and V. Furnon, "OR-Tools," Google. [Online]. Available:
https://developers.google.com/optimization/

[5] C. Voudouris and E. Tsang, "Guided local search and its application to the traveling salesman
problem," *European Journal of Operational Research*, vol. 113, no. 2, pp. 469-499, 1999.

[6] D. Luxen and C. Vetter, "Real-time routing with OpenStreetMap data," in *Proc. 19th ACM SIGSPATIAL
Int. Conf. Advances in Geographic Information Systems*, Chicago, IL, USA, 2011, pp. 513-516.

[7] D. Delling, A. V. Goldberg, T. Pajor, and R. F. Werneck, "Customizable route planning," in *Proc.
10th Int. Symp. Experimental Algorithms (SEA)*, LNCS 6630, 2011, pp. 376-387.

[8] F. Arnold, M. Gendreau, and K. Sörensen, "Efficiently solving very large-scale routing problems,"
*Computers & Operations Research*, vol. 107, pp. 32-42, 2019.

[9] L. Accorsi and D. Vigo, "A fast and scalable heuristic for the solution of large-scale capacitated
vehicle routing problems," *Transportation Science*, vol. 55, no. 4, pp. 832-856, 2021.

[10] P. Schittekat, J. Kinable, K. Sörensen, M. Sevaux, F. Spieksma, and J. Springael, "A metaheuristic
for the school bus routing problem with bus stop selection," *European Journal of Operational Research*,
vol. 229, no. 2, pp. 518-528, 2013.

[11] P. Toth and D. Vigo, "The granular tabu search and its application to the vehicle-routing problem,"
*INFORMS Journal on Computing*, vol. 15, no. 4, pp. 333-346, 2003.

## Appendix A. Reproducing the results

All commands run from the repository root in WSL, with the environment from `research/README.md`. The
travel-time matrices are in the repository, so OSRM is not needed.

| Result | Command | Output |
| --- | --- | --- |
| Dataset (D1) | `python research/build_instance.py` | `research/data/instance_fall2026_v1.json` |
| Time budget (B1) | `python research/run_budget.py` | `research/results/budget/` |
| Query budget (Q1) | `python research/run_query_budget.py --workers 2` | `research/results/query-budget/` |
| Traffic check (T1) | `python research/run_robustness.py traffic --workers 2` | `research/results/traffic-check/` |
| Seed check (S1) | `python research/run_robustness.py seed --workers 2` | `research/results/seed-check/` |
| Scaling (OS1, Windows) | `python research/run_scale.py --instances Jadoon,Nadeem,Jadoon-doubled,Nadeem-doubled` | `research/results/optimizer-scale/` |

Each results folder holds `meta.json` (machine and settings), `runs.jsonl` (one line per run),
`summary.json` (the tables above) and one file per run with its routes. Charts and maps of every run
are on the research hub, which exports them as PNG, CSV and LaTeX.

## Appendix B. Notes for the authors (remove before submission)

- **References.** All eleven checked on 20 November 2026 against publisher, DBLP or RePEc records:
  authors, titles, venues, volumes and pages match, including [5] and [11], which were first cited from
  memory. Changes made: the page range of [7] (376-387) and the series name of [3]. [4] is software
  and has no page range.
- **Free-tier figures.** The chapter says "a free-tier web service with 512 MB and one tenth of a CPU
  core" without naming a provider. The logbook attributes these limits to Render's free tier. Add a
  dated citation of the provider's documentation if the provider is to be named.
- **Figures.** No figure is embedded. Suggested: the gap-against-budget chart for B1, the
  gap-against-K chart for Q1, and one map pair of current and optimized routes, all from the hub's
  export buttons.
- **Format.** This is Markdown with IEEE-style numbered references, the style the proposal uses. It
  converts to Word or LaTeX with Pandoc.
