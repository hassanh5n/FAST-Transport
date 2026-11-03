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
