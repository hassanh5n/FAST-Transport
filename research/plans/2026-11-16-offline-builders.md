# Offline Builders Implementation Plan (road-block test, walking distances, scenarios)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce, once, on the laptop that has Docker, the three things every later run reads from the repository: the road-block test results, the walking distances between stops, and the frozen closure scenarios with true travel times from OSRM.

**Architecture:** One helper module wraps the OSRM command-line tools and HTTP services. Three scripts use it. Everything that can be decided without OSRM (where closures go, which stops are candidates, how tables are cleaned) is in pure functions with unit tests; the parts that need Docker are verified by running them and checking stated outputs.

**Tech Stack:** Python 3.10+ standard library, `numpy`; Docker with the image `ghcr.io/project-osrm/osrm-backend:v5.27.1`; run inside WSL on the Docker laptop.

**Spec:** `research/plans/2026-11-15-rerouting-plan.md` (version 2), Sections 8.1 and 8.2 and work items A1 to A5. Uses `reroute.closure` and `Graph` from `research/plans/2026-11-16-road-graph.md`.

## Global Constraints

- Every OSRM customization starts from an untouched copy of the OSRM files. Customizing rewrites segment data, so closures would otherwise accumulate.
- A stop's id is its position (0-based) in the `stops` list of `data/instance_fall2026_v1.json`. Campus has id `-1` in files and is always the last row and column of a table.
- A point inside a full-block circle is unreachable: its row and column in the true table are infinite, whatever OSRM answers. In JSON, infinity is written as `null`.
- Synthetic closures are circles of 200 m radius, factor 0, centred on the road path at the middle of a leg between two stops. Historical closures are chains of 60 m circles every 100 m along the road.
- University Road is slowed to 10 km/h (in the speed file) and carried as factor 0.25 in the scenario file.
- Frozen outputs are never edited by hand; to change one, change the script, bump the version and rebuild.
- Commit messages start with `Research:` and carry no co-author line.

## Review Focus

1. **OSRM returns no route for a pair** (`null` in a table): stored as `null`, read back as infinity, never as zero. Task 1.
2. **A route with three stops**: the two closure legs are different legs. Task 4.
3. **A closure that contains a stop of the route**: the scenario is kept and tagged, and that stop is marked closed. Task 4.
4. **A stop with no students on this route** (shared with another contractor): it is not a remaining stop of this route. Task 4.
5. **The server is not ready when the first request is sent after a restart**: requests retry for up to 60 s before failing. Task 1.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `research/osrm_tools.py` | Copy OSRM files, write speed files, customize, start and stop the server, `table`, `route` |
| `research/run_roadblock.py` | The road-block test; writes `results/roadblock/` |
| `research/build_walk.py` | Walking distances; writes `data/walk_fall2026_v1.json` |
| `research/scenario_rules.py` | Pure rules: closure legs, circles along a line, candidates, students per route stop, table cleaning |
| `research/build_scenarios.py` | Drives OSRM over every closure; writes `data/scenarios_reroute_v1.json` |
| `research/data/raw/historical_closures.json` | The two historical road stretches, as end points pinned by the team |
| `research/tests/test_osrm_tools.py`, `research/tests/test_scenario_rules.py` | Unit tests (run from `research/` with `python -m unittest discover -s tests -t . -v`) |

**Folders on the Docker laptop** (not in the repository): `~/fleetcentric-osrm/car/` holds the untouched car build from run N1 (`karachi.osrm*`); `~/fleetcentric-osrm/foot/` the foot build; `~/fleetcentric-osrm/work/` is scratch, recreated per closure.

---

### Task 1: OSRM helper

**Files:**
- Create: `research/osrm_tools.py`, `research/tests/__init__.py`
- Test: `research/tests/test_osrm_tools.py`

**Interfaces:**
- Produces:
  - `IMAGE = "ghcr.io/project-osrm/osrm-backend:v5.27.1"`.
  - `speed_csv(rows: Iterable[tuple[int, int, int]]) -> str`: one line per row, `from,to,kmh`, newline-terminated, duplicates removed, sorted.
  - `table_url(base: str, points: Sequence[tuple[float, float]], profile: str = "driving", annotations: str = "duration") -> str`: points are `(lat, lng)`; the URL has `lng,lat` pairs to six decimals.
  - `clean_table(values: list[list[float | None]]) -> list[list[float]]`: `None` becomes `math.inf`.
  - `to_json_table(values) -> list[list[float | None]]`: infinity becomes `None`, finite values rounded to one decimal.
  - `fresh_copy(source_dir: Path, work_dir: Path) -> None`: empties `work_dir` and copies every `karachi.osrm*` file.
  - `customize(work_dir: Path, csv_text: str) -> float`: writes `updates.csv`, runs `osrm-customize /data/karachi.osrm --segment-speed-file /data/updates.csv` in the image, returns wall seconds. Raises `RuntimeError` with the tool's last lines on a non-zero exit.
  - `start_server(data_dir: Path, port: int = 5000, name: str = "osrm") -> None`: removes any container of that name, starts `osrm-routed --algorithm mld --max-table-size 1000 /data/karachi.osrm`, then polls the server for up to 60 s until a request answers `Ok`.
  - `stop_server(name: str = "osrm") -> None`.
  - `table(points, base="http://localhost:5000", profile="driving", annotations="duration") -> list[list[float]]`: cleaned.
  - `route(points, base="http://localhost:5000", nodes: bool = False) -> dict`: the first route, requested with `overview=full&geometries=geojson` and, when `nodes` is true, `annotations=nodes`.

- [ ] **Step 1: Write the failing tests** (pure functions only)

```python
import math, unittest
from osrm_tools import speed_csv, table_url, clean_table, to_json_table

class OsrmToolsTests(unittest.TestCase):
    def test_speed_csv(self):
        self.assertEqual(speed_csv([(2, 1, 0), (1, 2, 0), (2, 1, 0)]), "1,2,0\n2,1,0\n")

    def test_table_url_puts_longitude_first(self):
        self.assertEqual(table_url("http://h:5000", [(24.9, 67.1), (24.8, 67.2)]),
                         "http://h:5000/table/v1/driving/67.100000,24.900000;67.200000,24.800000?annotations=duration")

    def test_null_becomes_infinity_and_back(self):
        self.assertEqual(clean_table([[0, None], [3.26, 0]]), [[0, math.inf], [3.26, 0]])
        self.assertEqual(to_json_table([[0, math.inf], [3.26, 0]]), [[0, None], [3.3, 0]])
```

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `osrm_tools.py`.** Shell out with `subprocess.run`; HTTP with `urllib.request`.
- [ ] **Step 4: Run the unit tests and confirm they pass.**
- [ ] **Step 5: Check the Docker parts by hand on the Docker laptop:**

```bash
python -c "import osrm_tools as o, pathlib as p; h=p.Path.home()/'fleetcentric-osrm'; o.fresh_copy(h/'car', h/'work'); print(o.customize(h/'work', '')); o.start_server(h/'work'); print(o.table([(24.8607,67.0298),(24.8569,67.2647)])); o.stop_server()"
```

Expected: a customize time of a few seconds, then a 2 x 2 table with zeros on the diagonal and two times of roughly 2,000 to 3,500 seconds (Saddar to campus).

- [ ] **Step 6: Commit** with message `Research: OSRM helper for customizing and querying`.

---

### Task 2: Road-block test (work item A2)

**Files:**
- Create: `research/run_roadblock.py`
- Output: `research/results/roadblock/result.json`

**Interfaces:**
- Consumes: `osrm_tools`, `reroute.graph.Graph`, `reroute.closure`.
- Produces `result.json` with keys `machine`, `osrm_image`, `checks` (each `{"question", "answer", "evidence"}`) and `timings`.

The script runs four checks on one fixed leg: the first leg of Jadoon route R-10 (Hyderi Super Mart KDA to Ziauddin).

- [ ] **Step 1: Write the script.**
  1. **Speed 0.** Get the leg's route with `nodes=True`. Take the middle pair of consecutive map node ids; write speed 0 for both directions; customize a fresh copy; restart; route again. Answer `blocks` if the new route's node list no longer contains that pair in either direction and its duration is larger; `ignored` if the route is unchanged.
  2. **Snapping.** Ask for a route that starts at the midpoint of the closed pair. Record how far OSRM moved the start (`waypoints[0].distance`) before and after the closure. Answer `moved` if it grew by more than 20 m.
  3. **Slowed.** Same pair at 5 km/h on a fresh copy. Answer `changes route`, `same route, longer` or `no effect`.
  4. **Timings.** Five repeats of: fresh copy, customize with one closed pair, server start until the first `Ok`. Record each part's wall seconds and the peak memory Docker reports for the customize container.
- [ ] **Step 2: Run it on the Docker laptop.** Expected, from OSRM's current source code (not checked on 5.27.1, which is why this test exists): check 1 answers `blocks`. If it answers `ignored`, rerun with 1 km/h and record that scenarios must use 1 km/h.
- [ ] **Step 3: Commit the script and `result.json`** with message `Research: road-block test results`, and write the logbook entry: the four answers, the timings table, and what each answer selects (work plan Section 8.1).

---

### Task 3: Walking distances (work item A3)

**Files:**
- Create: `research/build_walk.py`
- Output: `research/data/walk_fall2026_v1.json`

**Interfaces:**
- Consumes: `osrm_tools`.
- Produces: `{"version": "walk-fall2026-v1", "instance": "fall2026-v1", "profile": "foot", "built_at": ..., "max_m": 1000, "pairs": [[from_id, to_id, metres], ...], "stats": {"detour_factor": ..., "share_same_route_400": ..., "share_same_route_800": ...}}`. Pairs are directed, ids are stop ids, metres are whole numbers, and only pairs of at most 1,000 m walk are kept.
- `load_walk(path) -> dict[tuple[int, int], float]` in the same file, for the runner.

- [ ] **Step 1: Build OSRM with the foot profile, once:**

```bash
mkdir -p ~/fleetcentric-osrm/foot && cd ~/fleetcentric-osrm/foot && cp ../karachi.osm.pbf .
IMG=ghcr.io/project-osrm/osrm-backend:v5.27.1
docker run --rm -t -v "$PWD:/data" $IMG osrm-extract -p /opt/foot.lua /data/karachi.osm.pbf
docker run --rm -t -v "$PWD:/data" $IMG osrm-partition /data/karachi.osrm
docker run --rm -t -v "$PWD:/data" $IMG osrm-customize /data/karachi.osrm
```

- [ ] **Step 2: Write the script.** Start the foot server on port 5001; one table call for all 311 stops with `annotations=distance`; keep pairs within 1,200 m straight-line and 1,000 m walk. `detour_factor` is the median of walk metres over straight-line metres for pairs within 800 m straight-line. `share_same_route_400` and `_800` are the shares of stop visits on the current routes that have another stop of the same route within that walk.
- [ ] **Step 3: Run it.** Expected: a detour factor between about 1.2 and 1.6; shares below the straight-line figures of 30% (400 m) and 65% (800 m) measured on 15 November. A factor below 1.0 means distances and durations were mixed up.
- [ ] **Step 4: Commit** with message `Research: walking distances between stops`. Log the three statistics.

---

### Task 4: Scenario rules

**Files:**
- Create: `research/scenario_rules.py`
- Test: `research/tests/test_scenario_rules.py`

**Interfaces:**
- Produces:
  - `closure_legs(n_stops: int) -> list[int]`: for a route of `n_stops` stops (at least 3), the two leg numbers to close, where leg `k` joins stop `k` and stop `k + 1` (1-based): `ceil(n / 3)` and `ceil(2n / 3)`, the second capped at `n - 1`. Routes with fewer than 3 stops return `[]`.
  - `midpoint(line: Sequence[tuple[float, float]]) -> tuple[float, float]`: the point halfway along a polyline of `(lat, lng)` by length.
  - `circles_along(line, spacing_m: float = 100.0, radius_m: float = 60.0) -> list[tuple[float, float, float]]`: `max(2, round(length / spacing_m) + 1)` circles, evenly spaced by length from the first point to the last.
  - `route_students(csv_rows: Iterable[dict], contractor: str, route_code: str) -> dict[str, int]`: students per stop name for one route, counted from `students_synthetic_fall2026.csv` (`contractor`, `stop`, `baseline_route`).
  - `candidates(remaining: Sequence[int], walk: Mapping[tuple[int, int], float], max_m: float = 800.0) -> list[int]`: other stop ids within `max_m` walk of any remaining stop, ascending, excluding the remaining stops themselves.
  - `triggers(stop_ids: Sequence[int], leg: int) -> list[dict]`: the two bus positions for a closure on leg `leg`: `{"trigger": "early", "position": stop_ids[0], "remaining": all stops}` and `{"trigger": "late", "position": stop_ids[leg - 1], "remaining": stops after position `leg`}`. When `leg` is 1 both would start at the first stop; then the early one is kept and the late one has the first stop as position and the rest as remaining.
  - `apply_closed(table: list[list[float]], closed: Sequence[bool]) -> list[list[float]]`: rows and columns of closed points set to infinity, except the diagonal.
  - `scenario_id(contractor, route_code, leg, trigger) -> str`: for example `Jadoon-R-10-L2-early`.

- [ ] **Step 1: Write the failing tests**

```python
import math, unittest
from scenario_rules import (closure_legs, midpoint, circles_along, route_students, candidates, triggers, apply_closed, scenario_id)

class ScenarioRulesTests(unittest.TestCase):
    def test_closure_legs(self):
        self.assertEqual([closure_legs(n) for n in (2, 3, 4, 6, 13)], [[], [1, 2], [2, 3], [2, 4], [5, 9]])

    def test_midpoint_is_by_length(self):
        lat, lng = midpoint([(24.9, 67.0), (24.9, 67.001), (24.9, 67.004)])
        self.assertAlmostEqual(lng, 67.002, places=5)

    def test_circles_along_cover_the_line(self):
        cs = circles_along([(24.9, 67.0), (24.9, 67.003)])          # about 302 m
        self.assertEqual(len(cs), 4)
        self.assertEqual((cs[0][:2], cs[-1][2]), ((24.9, 67.0), 60.0))
        self.assertAlmostEqual(cs[-1][1], 67.003, places=5)

    def test_route_students_counts_only_this_route(self):
        rows = [{"contractor": "Jadoon", "stop": "A", "baseline_route": "R-1"}] * 3 + \
               [{"contractor": "Jadoon", "stop": "A", "baseline_route": "R-2"},
                {"contractor": "Nadeem", "stop": "A", "baseline_route": "R-1"}]
        self.assertEqual(route_students(rows, "Jadoon", "R-1"), {"A": 3})

    def test_candidates(self):
        walk = {(1, 7): 300.0, (2, 9): 900.0, (1, 2): 100.0, (2, 5): 800.0}
        self.assertEqual(candidates([1, 2], walk), [5, 7])

    def test_triggers(self):
        t = triggers([10, 11, 12, 13], leg=2)
        self.assertEqual(t[0], {"trigger": "early", "position": 10, "remaining": [10, 11, 12, 13]})
        self.assertEqual(t[1], {"trigger": "late", "position": 11, "remaining": [12, 13]})

    def test_trigger_on_first_leg(self):
        t = triggers([10, 11, 12], leg=1)
        self.assertEqual(t[1], {"trigger": "late", "position": 10, "remaining": [11, 12]})

    def test_apply_closed(self):
        out = apply_closed([[0, 5, 9], [5, 0, 4], [9, 4, 0]], [False, True, False])
        self.assertEqual(out, [[0, math.inf, 9], [math.inf, 0, math.inf], [9, math.inf, 0]])

    def test_scenario_id(self):
        self.assertEqual(scenario_id("Jadoon", "R-10", 2, "early"), "Jadoon-R-10-L2-early")
```

In the early trigger the bus is at the first stop's location and that stop is still to be served; in the late trigger the stop at the bus's position has just been served.

- [ ] **Step 2: Run and confirm failure.**
- [ ] **Step 3: Implement `scenario_rules.py`.**
- [ ] **Step 4: Run and confirm the tests pass.**
- [ ] **Step 5: Commit** with message `Research: scenario placement rules`.

---

### Task 5: Historical closures

**Files:**
- Create: `research/data/raw/historical_closures.json`

- [ ] **Step 1: Pin the end points on a map.** For each stretch, find the two end points on OpenStreetMap, on the carriageway itself, and write them down with the source:

```json
[{"id": "shahrah-e-faisal-2024-02-24", "name": "Shahrah-e-Faisal, Karsaz to FTC", "factor": 0.0,
  "from": {"lat": null, "lng": null}, "to": {"lat": null, "lng": null}, "both_directions": true,
  "source": "Aaj English TV, 24 Feb 2024; see the literature note, reference 76"},
 {"id": "university-road-ponding", "name": "University Road, Hasan Square to NIPA", "factor": 0.25,
  "from": {"lat": null, "lng": null}, "to": {"lat": null, "lng": null}, "both_directions": true,
  "source": "Hussain, Ahmed and Ali 2018; see the literature note, reference 75"}]
```

The coordinates are deliberately empty here: they must be read off the map by a person, not guessed.

- [ ] **Step 2: Check each stretch** by asking the unblocked OSRM server for the route between its end points and looking at the line on a map: it must follow the named road and nothing else. Record the length in the file as `length_m`.
- [ ] **Step 3: Commit** with message `Research: historical closure stretches pinned on the map`.

---

### Task 6: Build the scenarios (work item A4)

**Files:**
- Create: `research/build_scenarios.py`
- Output: `research/data/scenarios_reroute_v1.json`

**Interfaces:**
- Consumes: Tasks 1, 3, 4 and 5; `Graph.load`, `closed_segments`, `osrm_speed_rows`, `closed_points`, `Closure`.
- Produces the scenario file:

```json
{"version": "reroute-v1", "instance": "fall2026-v1", "graph": "karachi_v1", "walk": "walk-fall2026-v1",
 "built_at": "...", "osrm_image": "...",
 "closures": [{"id": "Jadoon-R-10-L2", "kind": "synthetic", "contractor": "Jadoon", "route": "R-10", "leg": 2,
               "circles": [[24.91, 67.05, 200.0]], "factor": 0.0,
               "points": [12, 40, 41, 77], "closed_points": [40],
               "pre": [[0, 310.5, null]], "post": [[0, null, null]],
               "segments": 37, "leaks": 0, "customize_s": 4.6}],
 "scenarios": [{"id": "Jadoon-R-10-L2-early", "closure": "Jadoon-R-10-L2", "trigger": "early",
                "position": 12, "remaining": [12, 40, 41], "students": {"12": 6, "40": 3, "41": 9},
                "candidates": [77], "tags": {"remaining": 3, "closure_contains_stop": true}}]}
```

  - `points` are the stop ids the tables cover: every stop of the route, then every candidate of either trigger. `pre` and `post` are square tables over `points` followed by campus as the last row and column, in seconds, `null` for unreachable.
  - Historical closures have `kind` `historical`, no `leg`, and one closure entry per affected route, with scenarios for the early trigger and for a late trigger at the last stop before the stretch.
- `load_scenarios(path) -> dict` in the same file returns the parsed file with `null` turned into infinity.
- Command: `python research/build_scenarios.py` (all), `--route Jadoon:R-10` (one route, for checking), `--resume` (skip closures already in the output).

- [ ] **Step 1: Write the script.** Per route:
  1. Stop ids in route order; students per stop from `route_students`; a stop with no students on this route is dropped from the route.
  2. `pre` table from the untouched server (kept running on port 5000 for the whole build).
  3. For each leg from `closure_legs`: the leg's road line from `route`; the circle at its `midpoint`; closed segments from the graph; speed rows; fresh copy; customize; server on port 5002; `post` table, with `apply_closed` for the points inside the circle. The `pre` table is left as OSRM returned it.
  4. **Leak check:** for each pair of consecutive points in route order whose two ends are open, request the route on the customized server and count it as a leak if any vertex of its line lies inside the circle. Store the count.
  5. Scenarios from `triggers`, with `candidates` from the walking file.
- [ ] **Step 2: Run one route** (`--route Jadoon:R-10`) and check by eye: two closures, four scenarios, `leaks` is 0, `post` times are at least `pre` times wherever both are finite, and at least one `post` time is larger.
- [ ] **Step 3: Run everything.** Expected: 104 synthetic closures and 208 scenarios, minus any route left with fewer than 3 stops after dropping stops without students; about 106 customizations at the time measured in Task 2. The script prints the totals, the number of closures with leaks, and the number of scenarios whose closure contains a stop.
- [ ] **Step 4: Stop if any closure has leaks.** A leak means OSRM still routes through a road the graph thinks is closed. Find out why (a segment missed by the geometry match, or a one-way pair written in one direction only) before freezing the file.
- [ ] **Step 5: Commit** with message `Research: frozen closure scenarios reroute-v1`. Log the counts, the tags and the build time. From this commit on the file is frozen.

---

### Task 7: Combined matrix for the optimizer scaling run (work item A5)

**Files:**
- Modify: `research/build_matrix.py`
- Output: `research/data/matrix_fall2026_v1_all.json`

**Interfaces:**
- Produces: with `--combined`, one table over campus and all 311 stops in instance order, written in the same shape as the existing file under the single key `contractors["All"]`. The existing file and the default behaviour are untouched.

- [ ] **Step 1: Add the `--combined` option** using `argparse`; without it the script behaves exactly as before.
- [ ] **Step 2: Run it** against the untouched car server. Expected: `All: 312 x 312 matrix, 1 call, 0 unreachable pairs`.
- [ ] **Step 3: Check it against the saved matrix:** every Jadoon pair in the combined table equals the same pair in `matrix_fall2026_v1.json` to within 0.1 s. If not, the map build differs from run N1 and both matrices must be rebuilt as version 2.
- [ ] **Step 4: Commit** with message `Research: combined 311-stop travel-time matrix`.
