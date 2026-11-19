#!/usr/bin/env bash
# Copy the OSRM map files from WSL (~/fleetcentric-osrm) into research/map/ and write an inventory.
# Run once from WSL:  bash /mnt/c/Users/hp/Desktop/FAST-Transport/research/map/copy_from_wsl.sh
set -u
SRC="$HOME/fleetcentric-osrm"
DST="$(cd "$(dirname "$0")" && pwd)"
INV="$DST/wsl_inventory.txt"

{
  echo "# WSL inventory, $(date -Is)"
  echo "## ls -la $SRC"; ls -la "$SRC" 2>&1
  echo; echo "## subfolders"; for d in "$SRC"/*/; do [ -d "$d" ] && { echo "### $d"; ls -la "$d"; }; done
  echo; echo "## du"; du -sh "$SRC"/* 2>&1
  echo; echo "## home (top level)"; ls -la "$HOME"
  echo; echo "## venvs in home"
  for v in "$HOME"/*/bin/python "$HOME"/.*/bin/python; do
    [ -x "$v" ] || continue
    echo "### $v ($("$v" --version 2>&1))"
    "$v" -m pip freeze 2>/dev/null
  done
  echo; echo "## docker"; (docker --version; docker images 2>&1 | head) 2>&1
  echo; echo "## systemd/cgroup"; stat -fc %T /sys/fs/cgroup 2>&1; ps -p 1 -o comm= 2>&1
} > "$INV"

copy() {  # copy one file into DST/<subdir>, skipping identical copies
  local f="$1" sub="$2"
  mkdir -p "$DST/$sub"
  if [ -f "$DST/$sub/$(basename "$f")" ] && cmp -s "$f" "$DST/$sub/$(basename "$f")"; then return; fi
  echo "copy $f -> map/$sub/"; cp -p "$f" "$DST/$sub/"
}

# 1. The map file OSRM and the road graph are built from (run N1).
[ -f "$SRC/karachi.osm.pbf" ] && copy "$SRC/karachi.osm.pbf" .
# 2. The car build (karachi.osrm*): from car/ if it exists, else from the top folder.
if ls "$SRC"/car/karachi.osrm* >/dev/null 2>&1; then
  for f in "$SRC"/car/karachi.osrm*; do copy "$f" car; done
else
  for f in "$SRC"/karachi.osrm*; do [ -f "$f" ] && copy "$f" car; done
fi
# 3. The foot build, if it was made.
for f in "$SRC"/foot/karachi.osrm*; do [ -f "$f" ] && copy "$f" foot; done
# Not copied: pakistan-latest.osm.pbf (re-downloadable, only cut down to karachi.osm.pbf),
# work/ (scratch, refilled on every customization), and any venv (not portable).

echo; echo "## sha256 (copied files)" >> "$INV"
(cd "$DST" && find . -type f \( -name '*.pbf' -o -name 'karachi.osrm*' \) -print0 | sort -z | xargs -0 -r sha256sum) >> "$INV"
echo "done. inventory: $INV"
