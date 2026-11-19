# research/map

A Windows-side copy of the OSRM map files from WSL (`~/fleetcentric-osrm`), made by
`copy_from_wsl.sh`. Not in git (too large); `wsl_inventory.txt` lists what was copied, with SHA-256.

- `karachi.osm.pbf`: the map run N1 built OSRM from. `build_graph.py` reads it on Windows:
  `research\.venv\Scripts\python research\build_graph.py research\map\karachi.osm.pbf`
- `car/`: the untouched car build (`karachi.osrm*`). `foot/`: the foot build, once made.

The Docker scripts (`run_roadblock.py`, `build_walk.py`, `build_scenarios.py`) still default to
`~/fleetcentric-osrm` inside WSL. Keep running them there: Docker reads WSL's own disk much faster
than `/mnt/c`. Use this folder as the backup and for the Windows-side graph build.
