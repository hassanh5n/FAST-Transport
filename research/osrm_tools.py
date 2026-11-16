"""Helpers around the OSRM command-line tools (in Docker) and the OSRM HTTP services.

Used by the offline builders (road-block test, walking distances, scenario build). Standard library
only. Points are always `(lat, lng)` in Python; OSRM URLs carry `lng,lat`.

Typical use on the Docker laptop (see `plans/2026-11-16-offline-builders.md`, Task 1):

    fresh_copy(home / "car", home / "work")       # never customize the untouched copy
    customize(home / "work", speed_csv(rows))     # rows: (from_node, to_node, km/h)
    start_server(home / "work", port=5002, name="osrm-scn")
    times = table(points, base="http://localhost:5002")
    stop_server("osrm-scn")

Unreachable pairs: OSRM writes `null` in a table. `clean_table` turns it into `math.inf` and
`to_json_table` writes infinity back as `null`, so an unreachable pair never becomes zero.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Iterable, Sequence

IMAGE = "ghcr.io/project-osrm/osrm-backend:v5.27.1"
OSRM_BASENAME = "karachi.osrm"
READY_WAIT_S = 60.0
REQUEST_TIMEOUT_S = 120.0
RETRY_PAUSE_S = 1.0
ERROR_TAIL_LINES = 20
# A point in the map (the campus) used to ask a freshly started server whether it answers.
PROBE_POINT = (24.856899, 67.264684)

Point = tuple[float, float]


class OsrmError(RuntimeError):
    """OSRM refused a request (`code` is OSRM's answer code) or never answered (`code` is None)."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code


# --- pure helpers --------------------------------------------------------------------------------

def speed_csv(rows: Iterable[tuple[int, int, int]]) -> str:
    """The text of an OSRM segment-speed file: `from,to,kmh` per line, sorted, duplicates removed.

    Raises ValueError if one directed segment is given two different speeds.
    """
    speeds: dict[tuple[int, int], int] = {}
    for a, b, kmh in rows:
        key, kmh = (int(a), int(b)), int(kmh)
        if speeds.setdefault(key, kmh) != kmh:
            raise ValueError(f"segment {key[0]}->{key[1]} given two speeds: {speeds[key]} and {kmh} km/h")
    return "".join(f"{a},{b},{kmh}\n" for (a, b), kmh in sorted(speeds.items()))


def _coordinates(points: Sequence[Point]) -> str:
    if not points:
        raise ValueError("at least one point is needed")
    return ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in points)


def table_url(base: str, points: Sequence[Point], profile: str = "driving",
              annotations: str = "duration") -> str:
    """URL of an OSRM table request over `points` given as `(lat, lng)`."""
    return f"{base.rstrip('/')}/table/v1/{profile}/{_coordinates(points)}?annotations={annotations}"


def route_url(base: str, points: Sequence[Point], nodes: bool = False) -> str:
    """URL of an OSRM route request with the full GeoJSON line (and map node ids when `nodes`)."""
    if len(points) < 2:
        raise ValueError("a route needs at least two points")
    url = f"{base.rstrip('/')}/route/v1/driving/{_coordinates(points)}?overview=full&geometries=geojson"
    return url + ("&annotations=nodes" if nodes else "")


def clean_table(values: list[list[float | None]]) -> list[list[float]]:
    """An OSRM table with `null` (no route) replaced by infinity."""
    return [[math.inf if v is None else v for v in row] for row in values]


def to_json_table(values: list[list[float]]) -> list[list[float | None]]:
    """A table ready for JSON: infinity (or None) becomes `null`, finite values one decimal."""
    def cell(v: float | None) -> float | None:
        if v is None or v == math.inf:
            return None
        if not math.isfinite(v):
            raise ValueError(f"table value {v!r} cannot be stored")
        return round(v, 1)
    return [[cell(v) for v in row] for row in values]


# --- HTTP ------------------------------------------------------------------------------------------

def _short(url: str, limit: int = 120) -> str:
    return url if len(url) <= limit else url[:limit] + "..."


def fetch_json(url: str, wait_s: float = READY_WAIT_S, timeout_s: float = REQUEST_TIMEOUT_S, *,
               clock: Callable[[], float] = time.monotonic,
               sleep: Callable[[float], None] = time.sleep) -> dict:
    """GET an OSRM URL and return its JSON body when OSRM answers `Ok`.

    A server that is not ready yet (connection refused or reset, a timeout, an HTTP 5xx) is asked
    again every second for up to `wait_s` seconds; then OsrmError is raised. An answer other than
    `Ok` (for example `NoRoute`) raises OsrmError at once, with OSRM's code in `.code`.
    """
    start = clock()
    while True:
        try:
            with urllib.request.urlopen(url, timeout=timeout_s) as response:
                body = json.load(response)
            break
        except urllib.error.HTTPError as err:
            with err:
                payload = err.read() if err.code < 500 else b""
            if err.code < 500:
                try:
                    body = json.loads(payload or b"{}")
                except json.JSONDecodeError:
                    body = {"code": f"HTTP {err.code}"}
                break
            last = f"HTTP {err.code}"
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as err:
            last = str(getattr(err, "reason", err))
        if clock() - start >= wait_s:
            raise OsrmError(f"OSRM did not answer within {wait_s:g} s ({last}): {_short(url)}")
        sleep(RETRY_PAUSE_S)
    code = body.get("code")
    if code != "Ok":
        raise OsrmError(f"OSRM refused the request: {code} {body.get('message', '')}".rstrip()
                        + f" ({_short(url)})", code=code)
    return body


def wait_ready(base: str, wait_s: float = READY_WAIT_S, **retry) -> None:
    """Block until the server at `base` answers a `nearest` request with `Ok`, for up to `wait_s`."""
    lat, lng = PROBE_POINT
    fetch_json(f"{base.rstrip('/')}/nearest/v1/driving/{lng:.6f},{lat:.6f}", wait_s=wait_s, **retry)


def table(points: Sequence[Point], base: str = "http://localhost:5000", profile: str = "driving",
          annotations: str = "duration") -> list[list[float]]:
    """One OSRM table over `points`, cleaned (`null` becomes infinity).

    Returns the durations (seconds) or, with `annotations="distance"`, the distances (metres).
    """
    if annotations not in ("duration", "distance"):
        raise ValueError("annotations must be 'duration' or 'distance'")
    body = fetch_json(table_url(base, points, profile, annotations))
    return clean_table(body[annotations + "s"])


def route(points: Sequence[Point], base: str = "http://localhost:5000", nodes: bool = False) -> dict:
    """OSRM's first route through `points`, with the full GeoJSON line.

    With `nodes`, each leg carries `annotation.nodes` (map node ids). The answer's `waypoints`
    (where each point was snapped, with `distance` in metres) are added to the returned route under
    `"waypoints"`, because the road-block test needs them.
    """
    body = fetch_json(route_url(base, points, nodes))
    first = dict(body["routes"][0])
    first["waypoints"] = body.get("waypoints", [])
    return first


# --- files and Docker ------------------------------------------------------------------------------

def _osrm_files(folder: Path) -> list[Path]:
    files = sorted(p for p in Path(folder).glob(OSRM_BASENAME + "*") if p.is_file())
    if not files:
        raise FileNotFoundError(f"no {OSRM_BASENAME}* files in {folder}; build the map there first "
                                f"(osrm-extract, osrm-partition, osrm-customize)")
    return files


def fresh_copy(source_dir: Path, work_dir: Path) -> None:
    """Empty `work_dir` and copy every `karachi.osrm*` file of `source_dir` into it.

    Raises ValueError when `work_dir` is `source_dir` or contains it: emptying it would delete the
    untouched build, which takes hours to rebuild from the map file.
    """
    source_dir, work_dir = Path(source_dir), Path(work_dir)
    if source_dir.resolve().is_relative_to(work_dir.resolve()):
        raise ValueError(f"the work folder {work_dir} must not be (or contain) the untouched source "
                         f"folder {source_dir}")
    files = _osrm_files(source_dir)
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)
    for f in files:
        shutil.copy2(f, work_dir / f.name)


def _docker(args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["docker", *args], capture_output=True, text=True)
    except FileNotFoundError as err:
        raise RuntimeError("docker is not installed or not on PATH; the OSRM steps run on the "
                           "Docker laptop") from err


def _tail(result: subprocess.CompletedProcess) -> str:
    lines = ((result.stdout or "") + (result.stderr or "")).strip().splitlines()
    return "\n".join(lines[-ERROR_TAIL_LINES:])


def _mount(folder: Path) -> str:
    return f"{Path(folder).resolve()}:/data"


def customize(work_dir: Path, csv_text: str) -> float:
    """Write `updates.csv` in `work_dir` and run `osrm-customize` with it; return wall seconds.

    Empty `csv_text` runs a plain customize (no speed file), which restores free-flow weights.
    Raises RuntimeError with the tool's last lines on a non-zero exit.
    """
    return customize_logged(work_dir, csv_text)[0]


def customize_logged(work_dir: Path, csv_text: str) -> tuple[float, str]:
    """`customize`, also returning the tool's output (stdout then stderr).

    The road-block test reads OSRM's own `RAM: peak bytes used` line from it.
    """
    work_dir = Path(work_dir)
    _osrm_files(work_dir)
    (work_dir / "updates.csv").write_text(csv_text, newline="\n")
    cmd = ["run", "--rm", "-v", _mount(work_dir), IMAGE, "osrm-customize", f"/data/{OSRM_BASENAME}"]
    if csv_text:
        cmd += ["--segment-speed-file", "/data/updates.csv"]
    start = time.perf_counter()
    result = _docker(cmd)
    seconds = time.perf_counter() - start
    if result.returncode != 0:
        raise RuntimeError(f"osrm-customize failed (exit {result.returncode}):\n{_tail(result)}")
    return seconds, (result.stdout or "") + (result.stderr or "")


def start_server(data_dir: Path, port: int = 5000, name: str = "osrm") -> None:
    """(Re)start `osrm-routed` on `data_dir` as container `name` and wait until it answers `Ok`."""
    _osrm_files(data_dir)
    _docker(["rm", "-f", name])
    result = _docker(["run", "-d", "--name", name, "-p", f"{port}:5000", "-v", _mount(data_dir), IMAGE,
                      "osrm-routed", "--algorithm", "mld", "--max-table-size", "1000",
                      f"/data/{OSRM_BASENAME}"])
    if result.returncode != 0:
        raise RuntimeError(f"could not start the OSRM container {name}:\n{_tail(result)}")
    try:
        wait_ready(f"http://localhost:{port}", wait_s=READY_WAIT_S)
    except OsrmError as err:
        logs = _tail(_docker(["logs", "--tail", str(ERROR_TAIL_LINES), name]))
        raise RuntimeError(f"OSRM container {name} did not become ready: {err}\n{logs}") from err


def stop_server(name: str = "osrm") -> None:
    """Remove the container `name`; a container that does not exist is not an error."""
    _docker(["rm", "-f", name])
