# Research: route optimization and rerouting

This folder is research only. Nothing here is imported by the website, and nothing
here changes the backend, frontend, settings or database. Results reach the live
system only after the team decides they are good enough to build in properly.

## Research hub: start here

Double-click **`research/Research Hub.bat`**. It opens one page in your browser with everything:

- **Overview**: the research questions, progress, pass/fail, what's next, latest logbook entries.
- **Experiments**: charts and tables per experiment, updated as runs finish.
- **Runs**: every optimizer run, with current vs optimized routes on a map.
- **Data**: the dataset and a map of every stop.
- **Documents**: logbook, this README, literature, PDFs.
- **Run & publish** (only in the hub): check the WSL setup, start / resume / stop experiments,
  and publish results to the shared page. No terminal commands needed.

Teammates and the supervisor open the shared read-only copy:
**https://hassanh5n.github.io/FAST-Transport/**. It is rebuilt by
`.github/workflows/research-site.yml` whenever research/ changes on main (the Publish button
does that push). The website's own deploy ignores research-only pushes.

The hub's files are in `hub/` (`serve.py` local server, `build_site.py` page builder,
`web/` the page, `project.json` the questions and next steps shown on the overview; edit it
when the plan changes). Everything below is what the hub runs for you, for reference. The Run
buttons start the scripts in WSL; on a PC where WSL will not start, run the scripts by hand from
the Windows environment below.

## Scope

| Phase | Question |
| --- | --- |
| FYP-1 | **Optimization:** can all-stop routes be built from a travel-time matrix within free-tier CPU and query limits, and how do they compare with the current hand-made routes? |
| FYP-1 | **Rerouting:** when a road is blocked, which road and which stops (keep, skip, or let students walk to a nearby point) give the lowest student delay? Morning runs, one bus at a time. |
| FYP-2 | **Context:** how much real incidents slow shuttle routes, recorded on an H3 grid. |
| FYP-2 | **Prediction:** whether that context predicts travel times better than the timetable and the router. |

## Layout

| Path | What it is |
| --- | --- |
| `build_instance.py` | Builds the dataset from `data/raw/`. Same output every run (seed 2026). Already run; rerun only if `data/raw/` changes. |
| `build_matrix.py` | Builds travel-time matrices from a local OSRM server; `--combined` builds one table over all 311 stops (`data/matrix_fall2026_v1_all.json`) |
| `data/raw/` | Inputs: Fall 2026 route plan, stop list, bus list (synthetic) |
| `data/raw/historical_closures.json` | The two historical road stretches (Shahrah-e-Faisal block, University Road ponding). End points are `null` until a person pins them on the map |
| `data/instance_fall2026_v1.json` | The frozen dataset every experiment uses |
| `data/students_synthetic_fall2026.csv` | One row per synthetic student |
| `data/matrix_fall2026_v1.json` | Travel times and distances, campus plus every stop, per contractor |
| `data/scenarios_toy.json` | Three hand-made toy closure scenarios for the `--quick` rerouting runs (written by `run_reroute.py make-toy`) |
| `optimize.py` | OR-Tools optimizer: plans all-stop routes and scores them against the current routes. The `solve()` argument `lookup` (`"callback"`, the default, or `"matrix"`) picks how travel times reach OR-Tools; it is not a command-line option |
| `run_budget.py` | Time-budget experiment: optimizer under free-tier limits vs no limits |
| `run_query_budget.py` | Query-budget experiment: K nearest real travel times, the rest estimated |
| `run_robustness.py` | Traffic check and seed check on the optimization results |
| `scale_instances.py` | Optimizer instances of growing size: one contractor, all 311 stops, and "doubled" copies |
| `run_scale.py` | Optimizer scaling run: build time, memory and plan quality as stops and buses grow |
| `reroute/` | The rerouting solver package. `model.py` (the problem for one bus, plans, scoring), `ladder.py` (R0 patched route, R2 greedy, R3 exact, run in that order), `wire.py` (request and proposal formats), `roadnet.py` (road tables from map ways), `closure.py` (closures matched to roads by geometry), `graph.py` (road graph at run time: corridors, closures, travel-time rows). Tests in `reroute/tests/` |
| `reroute_cases.py` | From a closure scenario to a solver problem, and plans scored on true travel times |
| `run_reroute.py` | Rerouting experiments: quality pass, limits pass, scaling runs |
| `build_graph.py` | Builds the compact road graph (`data/graph_karachi_v1/`) from the map file |
| `calibrate_graph.py` | Fits the graph's speed factor against the saved OSRM matrix |
| `build_corridors.py` | One search corridor per current route, with its pre-closure table (`data/corridors_fall2026_v1/`) |
| `measure_graph.py` | Graph timings and memory, with or without the free-tier limits (gate G1) |
| `osrm_tools.py` | Helpers for the OSRM tools in Docker and the OSRM HTTP services |
| `run_roadblock.py` | Road-block test: does OSRM route around a road set to 0 km/h, and how long does re-customizing take |
| `build_walk.py` | Walking distances between stops from OSRM's foot profile (`data/walk_fall2026_v1.json`) |
| `scenario_rules.py` | Pure rules for the closure scenarios: closure legs, circles along a line, candidates |
| `build_scenarios.py` | Builds the frozen closure scenarios with true travel times from OSRM (`data/scenarios_reroute_v1.json`) |
| `tests/` | Unit tests for the scripts above (OSRM is faked) |
| `results/` | Run reports (`opt-*.json/html`); `results/budget/` holds the time-budget experiment; one folder per later experiment |
| `plans/` | Rerouting work plan, implementation plans and `PROGRESS.md` |
| `literature/` | Literature notes |

## Dataset rules (3 Nov 2026)

- Stop locations are used as given. 11 stops had none and are placed from their
  route neighbours (marked `interpolated`).
- Same name or within 25 m means one stop, as in `stop_import.py`.
- Each contractor plans its own routes with its own buses. A stop may be served by both.
- Jadoon runs 27 routes with 26 buses, so `JDN-126` (45 seats) is added.
- Students are synthetic: each current route's bus is filled to 65 to 90 percent,
  spread over its stops with log-normal weights, at least one student per stop.

To change anything, edit `build_instance.py`, bump the version (`v2`) and rebuild.
Never edit a frozen file by hand.

## Paths

Commands below use `REPO`, the repository as WSL sees it. Set it once per WSL window:

```bash
REPO=/mnt/d/Projects/Python/SE/Project/fast-transport   # D:\Projects\Python\SE\Project\fast-transport
```

(On the laptop where the matrices were built, the repository was at
`/mnt/c/Users/hp/Desktop/FAST-Transport`.)

## If WSL will not start

`WSL2 is unable to start since virtualization is not enabled` with
`HCS_E_HYPERV_NOT_INSTALLED` means the Windows "Virtual Machine Platform" feature is off.
In an administrator PowerShell, then restart Windows:

```powershell
wsl.exe --install --no-distribution
```

If it still fails, turn on virtualization (Intel VT-x / AMD SVM) in the BIOS.

## Windows research environment

On a PC without WSL, most of the research code still runs in a plain Windows Python. Once, from
the repository root in PowerShell:

```powershell
python -m venv research\.venv
research\.venv\Scripts\python -m pip install -r research\requirements.txt
```

`research/.venv` is gitignored. `psutil` gives peak memory on Windows (Linux uses the standard
library). Run the scripts with `research\.venv\Scripts\python` instead of
`~/fc-research-venv/bin/python`.

Works without WSL:

- the unit tests (below);
- the optimizer, the optimizer scaling run, the query-budget experiment, the traffic and seed
  checks, and their `--quick` pipeline tests;
- the rerouting `--quick` pipeline tests (the quick limits pass needs `--no-limits`);
- the rerouting scaling run's unlimited rows (`--no-limits`; the `stops` part needs no data file);
- the rerouting quality pass, once the scenario and walking files exist;
- the road-graph scripts (`build_graph.py`, `calibrate_graph.py`, `build_corridors.py`,
  `measure_graph.py --no-limits`), once the map file is on this PC.

Needs WSL (Linux): anything inside the free-tier limits, because the limits come from systemd
(all of `run_budget.py`, `--quick` included, the rerouting limits pass, limited scaling rows,
`measure_graph.py --limited`), and the hub's Run buttons. Needs Docker and OSRM: the offline
builders and `build_matrix.py`. Without the limits a script records `limits: none` and refuses to
claim a free-tier result.

## Setup in WSL (Ubuntu), once

```bash
sudo apt update && sudo apt install -y python3-venv
python3 -m venv ~/fc-research-venv
~/fc-research-venv/bin/pip install -r $REPO/research/requirements.txt
```

The optimizer and the time-budget experiment need only this: the travel-time matrices are
already in `data/`. Docker and OSRM are needed only to rebuild the matrices and to build the
rerouting data (road-block test, walking distances, closure scenarios, combined matrix).

## Tests

From `research/` (the `-t .` makes `research/` the import root). On Windows:

```powershell
cd research
.venv\Scripts\python -m unittest discover -s reroute/tests -t . -v    # solver and road graph
.venv\Scripts\python -m unittest discover -s tests -t . -v            # scripts, OSRM faked
```

In WSL, the same two commands with `~/fc-research-venv/bin/python`. Neither needs OSRM, Docker,
the map file or the limits. On 17 Nov 2026: 217 and 235 tests, all passing.

## Limits without Docker (systemd cgroups)

The free-tier limits (512 MB, no swap, 0.1 CPU) are applied with systemd, which uses the same
kernel feature (cgroups v2) that `docker run --memory --cpus` uses. Turn systemd on once:

```bash
sudo nano /etc/wsl.conf      # keep anything already there, and add:
                             # [boot]
                             # systemd=true
```

Then `wsl --shutdown` in PowerShell, reopen Ubuntu, and check:

```bash
stat -fc %T /sys/fs/cgroup                               # must print cgroup2fs
~/fc-research-venv/bin/python $REPO/research/run_budget.py --check
```

`--check` starts a limited scope and reads back what the kernel applied
(`memory.max=536870912`, `memory.swap.max=0`, `cpu.max=10000 100000`). If it fails, try
`--check --sudo`. Every later command then needs `--sudo` too.

## Time-budget experiment

Does the optimizer find good routes on a free-tier server, and how much quality do the limits
cost? Each contractor is solved at 10, 60, 300 and 600 s, 3 repeats, limited and unlimited,
plus a 30-minute unlimited reference: 50 runs, about 4.5 hours.

```bash
cd $REPO
~/fc-research-venv/bin/python research/run_budget.py --quick    # about 3 min: tests the whole pipeline
~/fc-research-venv/bin/python research/run_budget.py            # the real run, overnight
```

- Resumable: finished runs are in `results/budget/runs.jsonl`, so rerunning the command continues.
- Output: `results/budget/summary.html` (chart and table) and `summary.json`; per-run JSON and logs.
- Pass/fail thresholds are fixed in `run_budget.py` and LOGBOOK (2026-11-04) before any run.
- Keep the laptop plugged in, stop Windows from sleeping, and run nothing heavy alongside.

## Query-budget experiment

How few real travel-time queries still give good routes? Each run "queries" only each stop's leg to
campus and its K nearest stops (K = 0, 3, 5, 10, 20, 40), estimates the rest (straight-line fit, or
shortest path through the queried legs), plans on that matrix and scores the plan on the full OSRM
matrix. The full matrix is the control. 72 runs, 60 s each, about 40 minutes with `--workers 2`.
No limits and no OSRM needed: it uses the saved matrices.

```bash
cd $REPO
~/fc-research-venv/bin/python research/run_query_budget.py --quick --workers 2   # about 20 s pipeline test
~/fc-research-venv/bin/python research/run_query_budget.py --workers 2           # the real run, resumable
~/fc-research-venv/bin/python research/run_query_budget.py --summarize           # print the results table
```

Thresholds are fixed in `run_query_budget.py` and LOGBOOK (2026-11-09) before the runs.

## Traffic check and seed check

Two short checks on the optimization results, both re-runs on the saved data (no limits, no OSRM).
The traffic check multiplies every travel time by 1.0, 1.3 and 1.5 and plans again (18 runs, about
10 minutes). The seed check redraws the synthetic students with three other seeds (8 runs, about 5 minutes).

```bash
cd $REPO
~/fc-research-venv/bin/python research/run_robustness.py traffic --quick --workers 2   # pipeline test
~/fc-research-venv/bin/python research/run_robustness.py traffic --workers 2           # the real run, resumable
~/fc-research-venv/bin/python research/run_robustness.py seed --workers 2
```

Thresholds are fixed in `run_robustness.py` and LOGBOOK (2026-11-10) before the runs.

## Optimizer scaling

How do build time, memory and plan quality grow with stops and buses, and does handing OR-Tools the
travel times as a matrix (`lookup="matrix"`) instead of a Python callback change that? Instances
Jadoon (171 stops), Nadeem (143), All (311, both fleets) and All-doubled (622: every stop and bus
twice, each copy 30 s from its original, so it tests model size, not geography), both lookups,
300 s each, no limits, each run a fresh process. No pass/fail threshold: it reports curves.

```bash
cd $REPO
~/fc-research-venv/bin/python research/run_scale.py --quick       # pipeline test: Nadeem, 10 s, both lookups
~/fc-research-venv/bin/python research/run_scale.py               # the run: 4 instances x 2 lookups x 300 s, about 40 min
~/fc-research-venv/bin/python research/run_scale.py --summarize   # print the table of finished runs
~/fc-research-venv/bin/python research/run_scale.py --instances Jadoon,Nadeem,Jadoon-doubled,Nadeem-doubled
```

- `--instances` takes comma-separated names; `<name>-doubled` works for any instance.
- All and All-doubled need the combined matrix `data/matrix_fall2026_v1_all.json`
  (`build_matrix.py --combined`, Docker laptop). Without it they are recorded as `skipped` and run
  on the next start once the file exists. Until then Jadoon-doubled and Nadeem-doubled stand in.
- Resumable: finished runs are in `results/optimizer-scale/runs.jsonl`.
- `build_s` is not comparable between the two lookups (the callback is lazy).
- Run OS1 (Jadoon, Nadeem and both doubled, both lookups, 300 s) is running on 17 Nov 2026.
  Results: pending.

## Rerouting experiments

The problem, methods and thresholds are fixed in LOGBOOK (2026-11-16) before any scenario exists,
and are copied into `run_reroute.py`. Three passes:

- **quality**: every scenario x walking limits 0, 400 and 800 m x R0, R2 and R3 on true times, no
  time limit, plus the no-closure control and must-serve arms at 400 m (5 rows per scenario).
- **limits**: every scenario at 400 m inside the free-tier limits (512 MB, no swap, 0.1 CPU;
  systemd, as in run B1). Arms `graph_limited`, `graph_unlimited` and `truth_limited`; every plan
  is scored on true times against the oracle.
- **scale**: curves, no verdicts. Parts `stops`, `graph`, `buses` and `slices`.

First the pipeline tests on the toy file (seconds; no OSRM, no graph):

```bash
cd $REPO
~/fc-research-venv/bin/python research/run_reroute.py make-toy                      # writes data/scenarios_toy.json
~/fc-research-venv/bin/python research/run_reroute.py quality --quick               # results/reroute-quality-quick/
~/fc-research-venv/bin/python research/run_reroute.py limits --quick --no-limits    # no systemd: a dry run
~/fc-research-venv/bin/python research/run_reroute.py scale --quick                 # stops at 4 and 8, slices on the toy file
```

The real runs need `data/scenarios_reroute_v1.json` and `data/walk_fall2026_v1.json` (the `stops`
part of the scaling run needs neither); the limits pass and the `graph` and `buses` parts of the
scaling run also need the road graph and the corridors (all built below). `quality` and `limits`
stop when the scenario file is missing; the scaling run skips the parts whose files are missing:

```bash
~/fc-research-venv/bin/python research/run_reroute.py quality --workers 2           # results/reroute-quality/
~/fc-research-venv/bin/python research/run_reroute.py limits                        # WSL with systemd; add --sudo if needed
~/fc-research-venv/bin/python research/run_reroute.py scale                         # or --only stops|graph|buses|slices
~/fc-research-venv/bin/python research/run_reroute.py scale --only stops --no-limits   # unlimited rows only
~/fc-research-venv/bin/python research/run_reroute.py quality --summarize           # rebuild summary.json from finished runs
```

- Without systemd, `limits` and `scale` refuse to run unless `--no-limits` is given (`scale
  --quick` is always unlimited and needs no option); every row then records limits `none`, so the
  numbers say nothing about the free tier. With `--no-limits` the scaling run makes no `limited`
  rows; a later run with systemd adds them.
- `--quick` reads the toy file only and writes to a `-quick` folder. The quick limits pass runs
  only `truth_limited` (the toy file has no road graph).
- Resumable: each finished run is one line in `<dir>/runs.jsonl`; rerunning the command skips
  finished runs and retries `failed` and `skipped` ones. `ok` and `infeasible` are counted results;
  any other status is a failure.
- `--summarize` works with every pass.
- On 17 Nov 2026 the quick pipeline tests and run RS1 `stops` part, unlimited (4 to 20 stops x 1, 2
  and 4 candidates x 3 seeds), are running. Results: pending. Nothing has been run on Karachi
  scenarios yet: the scenario file does not exist.

## Build the Karachi road network, once (about 10 to 20 minutes)

Needs Docker Engine inside WSL (`sudo apt install -y docker.io osmium-tool`; no Docker Desktop).
Already done once (runs N1 and M1 in LOGBOOK); repeat only to rebuild the matrices.

```bash
mkdir -p ~/fleetcentric-osrm && cd ~/fleetcentric-osrm
wget https://download.geofabrik.de/asia/pakistan-latest.osm.pbf
osmium extract -b 66.90,24.70,67.45,25.15 pakistan-latest.osm.pbf -o karachi.osm.pbf

IMG=ghcr.io/project-osrm/osrm-backend:v5.27.1
docker run --rm -t -v "$PWD:/data" $IMG osrm-extract -p /opt/car.lua /data/karachi.osm.pbf
docker run --rm -t -v "$PWD:/data" $IMG osrm-partition /data/karachi.osrm
docker run --rm -t -v "$PWD:/data" $IMG osrm-customize /data/karachi.osrm
```

The MLD pipeline (partition + customize) is used because rerouting later needs to
block a road and re-customize in seconds; the other pipeline (CH) needs a full rebuild.

## Each work session

```bash
sudo service docker start
cd ~/fleetcentric-osrm
docker run -d --rm --name osrm -p 5000:5000 -v "$PWD:/data" ghcr.io/project-osrm/osrm-backend:v5.27.1 \
    osrm-routed --algorithm mld --max-table-size 1000 /data/karachi.osrm

# check: one route from Saddar to campus, should print "Ok"
curl -s "http://localhost:5000/route/v1/driving/67.0298,24.8607;67.2647,24.8569?overview=false" | head -c 120

cd $REPO
~/fc-research-venv/bin/python research/build_matrix.py

docker stop osrm      # when done
```

`build_matrix.py` makes one OSRM call per contractor and prints any stop that
had to be moved more than 200 m to reach a road. Check those on a map.

## Road graph (offline, needs the map file)

The rerouter searches its own compact road graph instead of asking OSRM. It must be built from
the same `karachi.osm.pbf` OSRM was built from (run N1). The scripts need only the venv (Windows or
WSL); `--limited` needs WSL with systemd. In order:

```bash
cd $REPO
# 1. Build data/graph_karachi_v1/ (prints the counts and every point snapped more than 200 m from a road)
~/fc-research-venv/bin/python research/build_graph.py ~/fleetcentric-osrm/karachi.osm.pbf

# 2. Speed factor against the saved OSRM matrix. Rule: median absolute error at most 15%,
#    median signed error not negative. If the single factor fails, try --per-class.
~/fc-research-venv/bin/python research/calibrate_graph.py --dry-run     # print the figures, write nothing
~/fc-research-venv/bin/python research/calibrate_graph.py               # one factor for every road
~/fc-research-venv/bin/python research/calibrate_graph.py --per-class   # one factor per road class, then one overall

# 3. One corridor per current route, with its pre-closure table (data/corridors_fall2026_v1/).
#    Run it after calibration: the pre-closure tables are tied to the speed factor.
~/fc-research-venv/bin/python research/build_corridors.py

# 4. Timings and memory, written to results/graph-timing/timing.json under the mode's name
~/fc-research-venv/bin/python research/measure_graph.py --no-limits     # no limits, recorded as "limits": "none"
~/fc-research-venv/bin/python research/measure_graph.py --limited       # WSL only: MemoryMax=512M, MemorySwapMax=0, CPUQuota=10%
```

`measure_graph.py` with no option is the same as `--no-limits`. Add `--sudo` to `--limited` if the
limits are not applied otherwise. Gate G1: on the corridor, under the limits, 14 rows in at most
5 s of wall time and 31 rows in at most 30 s, judged on the worst repeat. Only a `--limited` run
whose limits were read back from the kernel can pass or fail it; on Windows `--limited` refuses to
run. `build_graph.py` also reads a small `.osm` XML file (`--out data/graph_test` keeps it apart
from the real graph). Not built yet: the map file is on the Docker laptop only. Counts, calibration
and G1 timings: pending.

## Offline builders on the Docker laptop

These scripts drive OSRM in Docker and need the map file, so they run on the laptop that has both
(in WSL, with the venv). Folders, not in the repository:

- `~/fleetcentric-osrm/car/`: the untouched car build from run N1 (`karachi.osrm*`). Never customize it.
- `~/fleetcentric-osrm/foot/`: the foot build, for walking distances.
- `~/fleetcentric-osrm/work/`: scratch, emptied and refilled for every customization.

Once:

```bash
cd ~/fleetcentric-osrm
sha256sum karachi.osm.pbf                     # log it in LOGBOOK (work item A1)
mkdir -p car && cp karachi.osrm* car/         # the untouched copy

mkdir -p foot && cd foot && cp ../karachi.osm.pbf .
IMG=ghcr.io/project-osrm/osrm-backend:v5.27.1
docker run --rm -t -v "$PWD:/data" $IMG osrm-extract -p /opt/foot.lua /data/karachi.osm.pbf
docker run --rm -t -v "$PWD:/data" $IMG osrm-partition /data/karachi.osrm
docker run --rm -t -v "$PWD:/data" $IMG osrm-customize /data/karachi.osrm
```

The scripts start and stop their own OSRM containers (untouched car build on port 5000, foot on
5001, customized copy on 5002), so stop the `osrm` container of a work session first
(`docker stop osrm`). Build the road graph (above) before the road-block test and the scenarios:
both read it. Then, in order:

```bash
cd $REPO/research

# 1. Road-block test: speed 0, snapping, slowed road, timings -> results/roadblock/result.json.
#    Its block_kmh (0 or 1) is the speed the scenarios must use; null means neither speed blocked.
~/fc-research-venv/bin/python run_roadblock.py

# 2. Walking distances between stops -> data/walk_fall2026_v1.json
~/fc-research-venv/bin/python build_walk.py                 # starts the foot server itself
~/fc-research-venv/bin/python build_walk.py --no-start      # or use a foot server already on --port
```

3. **Pin the historical closures by hand.** In `data/raw/historical_closures.json`, fill each
   stretch's `from` and `to` with end points read off OpenStreetMap, on the carriageway itself.
   They must be read off the map by a person, not guessed. Check each stretch by routing between its
   end points on the untouched server and looking at the line: it must follow the named road and
   nothing else. Record the length as `length_m`.

```bash
# 4. Scenarios. One route first, to check (written to results/scenarios-check/):
~/fc-research-venv/bin/python build_scenarios.py --route Jadoon:R-10 --block-kmh 0
# then every route -> data/scenarios_reroute_v1.json
~/fc-research-venv/bin/python build_scenarios.py --block-kmh 0
~/fc-research-venv/bin/python build_scenarios.py --block-kmh 0 --resume     # keep closures already built
~/fc-research-venv/bin/python build_scenarios.py --skip-historical          # synthetic closures only

# 5. Combined matrix over all 311 stops -> data/matrix_fall2026_v1_all.json (needs the
#    untouched server on port 5000, as in "Each work session")
cd $REPO
~/fc-research-venv/bin/python research/build_matrix.py --combined
```

- `--block-kmh` is `0` unless the road-block test answered `1` (OSRM ignored 0 km/h); follow its
  `block_kmh`. A slowed stretch is written at 10 km/h.
- `build_scenarios.py` prints the totals, the closures with leaks and the scenarios whose closure
  contains a stop. Expected: about 104 synthetic closures and 208 scenarios, plus the historical ones.
- `build_matrix.py --combined` checks every pair of the saved per-contractor matrix against the new
  table (within 0.1 s). A difference means the map build is not the one of run N1, and both
  matrices must be rebuilt as version 2.
- Commit the walking file and the scenario file; after that they are frozen.
- None of this has been run yet. Road-block facts, walking statistics and scenario counts: pending.

## Rerouting solver for the website

Nothing is built into the website yet (work plan Section 12 is a design only). `reroute.wire` is
the contract a caller would use:

- `parse_request(request, rows, walk)` checks a request and returns a `Problem`, or raises
  `RequestError` naming the field at fault. Request fields: `schema` (1), `now` (ISO 8601 with a
  UTC offset), `position` and `campus` (`lat`, `lng`), `remaining` (the stops still to serve, in
  published order: `stop_id`, `students`, optional `walk_limit_m` from 0 to 800, default 400, and
  `must_serve`, default false), `candidates` (extra boarding points, `stop_id`), `closures` (a
  list) and optional `committed` (stop ids already promised to students). Travel times (`rows`)
  and walking distances (`walk`) are the caller's job; closures and coordinates are only checked
  for presence.
- `reroute.Ladder` runs R0, R2 and R3 in that order and keeps the best plan, so a plan exists as
  soon as R0 and R2 have run. R3 runs in slices and its state can be saved between them.
- `to_proposal(request, plan, compute_s, baseline_arrival_s=None, revision=1, state=None)` gives
  the proposal: `schema`, `status`, `reason`, `revision`, `method`, `visit`, `stops` (one entry per
  remaining stop with `action` `keep`, `walk` or `unserved`, `board_at` and `walk_m`), `arrival`,
  `delay_s` (against the baseline arrival, when given), `students_walking`, `compute_s` and `state`.
- Status is `reroute`, `no_change` (the published order with nobody walking) or `failed`.
  `failed_proposal(reason)` is the proposal when no plan could be made at all.
- **A proposal with status `failed` must not be acted on.** It may still carry the plan, for
  information only; `arrival` and `delay_s` are then `null`. A committed point that becomes
  unreachable currently reports `campus unreachable`.
