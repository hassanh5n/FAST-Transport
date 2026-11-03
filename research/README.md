# Research: route optimization and rerouting

This folder is research only. Nothing here is imported by the website, and nothing
here changes the backend, frontend, settings or database. Results reach the live
system only after the team decides they are good enough to build in properly.

## Scope

| Phase | Question |
| --- | --- |
| FYP-1 | **Optimization:** can all-stop routes be built from a travel-time matrix within free-tier CPU and query limits, and how do they compare with the current hand-made routes? |
| FYP-1 | **Rerouting:** when a road is blocked, which road and which stops (keep, skip, merge) give the lowest student delay? |
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

## Setup in WSL (Ubuntu), once

OSRM and the map files live in your WSL home folder, not in this repository.

```bash
# Docker inside WSL (no Docker Desktop needed) and the map cutting tool
sudo apt update && sudo apt install -y docker.io osmium-tool python3-venv
sudo service docker start
sudo usermod -aG docker $USER        # then close and reopen the WSL window

# Python for the research scripts, separate from the website's environment
python3 -m venv ~/fc-research-venv
~/fc-research-venv/bin/pip install -r /mnt/c/Users/hp/Desktop/FAST-Transport/research/requirements.txt
```

## Build the Karachi road network, once (about 10 to 20 minutes)

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

cd /mnt/c/Users/hp/Desktop/FAST-Transport
~/fc-research-venv/bin/python research/build_matrix.py

docker stop osrm      # when done
```

`build_matrix.py` makes one OSRM call per contractor and prints any stop that
had to be moved more than 200 m to reach a road. Check those on a map.
