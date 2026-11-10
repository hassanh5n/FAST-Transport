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
when the plan changes). Everything below is what the hub runs for you, for reference.

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
| `build_matrix.py` | Builds travel-time matrices from a local OSRM server |
| `data/raw/` | Inputs: Fall 2026 route plan, stop list, bus list (synthetic) |
| `data/instance_fall2026_v1.json` | The frozen dataset every experiment uses |
| `data/students_synthetic_fall2026.csv` | One row per synthetic student |
| `data/matrix_fall2026_v1.json` | Travel times and distances, campus plus every stop, per contractor |
| `optimize.py` | OR-Tools optimizer: plans all-stop routes and scores them against the current routes |
| `run_budget.py` | Time-budget experiment: optimizer under free-tier limits vs no limits |
| `run_query_budget.py` | Query-budget experiment: K nearest real travel times, the rest estimated |
| `run_robustness.py` | Traffic check and seed check on the optimization results |
| `results/` | Run reports (`opt-*.json/html`); `results/budget/` holds the time-budget experiment |
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

## Setup in WSL (Ubuntu), once

```bash
sudo apt update && sudo apt install -y python3-venv
python3 -m venv ~/fc-research-venv
~/fc-research-venv/bin/pip install -r $REPO/research/requirements.txt
```

The optimizer and the time-budget experiment need only this: the travel-time matrices are
already in `data/`. Docker and OSRM are needed only to rebuild the matrices or, later, to
block roads for the rerouting experiments.

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
