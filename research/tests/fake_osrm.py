"""A stand-in for the `osrm_tools` module, backed by a toy road map, for tests without Docker.

It offers the functions the offline builders call (`fresh_copy`, `customize`, `start_server`,
`stop_server`, `table`, `route`) with the same signatures and answer shapes as OSRM:

* the "OSRM files" are a dummy `karachi.osrm` file in a folder; `customize` writes `updates.csv`
  there, and `start_server` reads that file, so a server sees exactly the speeds customized into
  the folder it was started on (closures accumulate if a caller forgets the fresh copy, as in OSRM);
* a point snaps to the nearest map node that has an open road, and `waypoints[].distance` says how
  far it moved;
* times come from a Dijkstra search over the directed segment table of
  :func:`reroute.roadnet.build_tables`; a speed of 0 removes a segment, another speed retimes it;
* a table answers `None` for a pair with no route, and `route` raises `OsrmError("NoRoute")`.

`ignore_block=True` makes speed 0 have no effect, to imitate an OSRM that ignores it.
"""
from __future__ import annotations

import heapq
import math
from pathlib import Path
from typing import Sequence

import osrm_tools
from osrm_tools import OsrmError, clean_table
from reroute.roadnet import haversine_m

BASENAME = osrm_tools.OSRM_BASENAME


def make_osrm_folder(folder: Path) -> Path:
    """A folder holding a dummy untouched OSRM build."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / BASENAME).write_text("toy map")
    return folder


class FakeOsrm:
    """The fake server farm. ``tables`` are the arrays of :func:`reroute.roadnet.build_tables`."""

    IMAGE = osrm_tools.IMAGE

    def __init__(self, tables: dict, ignore_block: bool = False, customize_s: float = 1.5) -> None:
        self.ignore_block = ignore_block
        self.customize_s = customize_s
        self.customize_peak_bytes = 123_456_789
        self.coords: dict[int, tuple[float, float]] = {}
        self.segments: list[tuple[int, int, float, float]] = []      # from, to, metres, seconds
        for k in range(len(tables["seg_from"])):
            a, b = int(tables["seg_from"][k]), int(tables["seg_to"][k])
            self.coords[a] = (float(tables["seg_lat1"][k]), float(tables["seg_lng1"][k]))
            self.coords[b] = (float(tables["seg_lat2"][k]), float(tables["seg_lng2"][k]))
            self.segments.append((a, b, float(tables["seg_m"][k]), float(tables["seg_s"][k])))
        self.servers: dict[int, dict[tuple[int, int], int]] = {}
        self.names: dict[str, int] = {}
        self.customizations: list[str] = []
        self.calls: list[tuple] = []

    # --- files and "Docker" ------------------------------------------------------------------

    def fresh_copy(self, source_dir: Path, work_dir: Path) -> None:
        osrm_tools.fresh_copy(source_dir, work_dir)

    def customize_logged(self, work_dir: Path, csv_text: str) -> tuple[float, str]:
        seconds = self.customize(work_dir, csv_text)
        return seconds, f"[info] RAM: peak bytes used: {self.customize_peak_bytes}\n"

    def customize(self, work_dir: Path, csv_text: str) -> float:
        work_dir = Path(work_dir)
        if not (work_dir / BASENAME).exists():
            raise FileNotFoundError(f"no {BASENAME} in {work_dir}")
        old = (work_dir / "updates.csv").read_text() if (work_dir / "updates.csv").exists() else ""
        # Like osrm-customize, an earlier customization stays in the segment data.
        (work_dir / "updates.csv").write_text(old + csv_text)
        self.customizations.append(csv_text)
        return self.customize_s

    def start_server(self, data_dir: Path, port: int = 5000, name: str = "osrm") -> None:
        data_dir = Path(data_dir)
        if not (data_dir / BASENAME).exists():
            raise FileNotFoundError(f"no {BASENAME} in {data_dir}")
        speeds: dict[tuple[int, int], int] = {}
        csv = data_dir / "updates.csv"
        if csv.exists():
            for line in csv.read_text().splitlines():
                if line.strip():
                    a, b, kmh = (int(x) for x in line.split(","))
                    speeds[(a, b)] = kmh
        if name in self.names:
            self.servers.pop(self.names[name], None)
        self.names[name] = port
        self.servers[port] = speeds
        self.calls.append(("start", str(data_dir), port, name))

    def stop_server(self, name: str = "osrm") -> None:
        port = self.names.pop(name, None)
        if port is not None:
            self.servers.pop(port, None)
        self.calls.append(("stop", name))

    # --- routing -------------------------------------------------------------------------------

    def _speeds(self, base: str) -> dict[tuple[int, int], int]:
        port = int(base.rstrip("/").rsplit(":", 1)[1])
        if port not in self.servers:
            raise OsrmError(f"OSRM did not answer within 60 s (connection refused): {base}")
        return self.servers[port]

    def _adjacency(self, speeds: dict[tuple[int, int], int]) -> dict[int, list[tuple[int, float]]]:
        adj: dict[int, list[tuple[int, float]]] = {}
        for a, b, metres, seconds in self.segments:
            kmh = speeds.get((a, b))
            if kmh is not None:
                if kmh == 0:
                    if not self.ignore_block:
                        continue
                else:
                    seconds = metres / (kmh / 3.6)
            adj.setdefault(a, []).append((b, seconds))
            adj.setdefault(b, [])
        return adj

    def _snap(self, adj, lat: float, lng: float) -> tuple[int, float]:
        # Every node with an open segment is a key of `adj`; a node whose roads are all closed is not.
        best = min(adj, key=lambda n: (haversine_m(lat, lng, *self.coords[n]), n))
        return best, haversine_m(lat, lng, *self.coords[best])

    @staticmethod
    def _search(adj, source: int) -> tuple[dict[int, float], dict[int, int]]:
        dist, pred, heap = {source: 0.0}, {}, [(0.0, source)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist.get(u, math.inf):
                continue
            for v, w in adj.get(u, []):
                if d + w < dist.get(v, math.inf):
                    dist[v], pred[v] = d + w, u
                    heapq.heappush(heap, (d + w, v))
        return dist, pred

    def table(self, points: Sequence[tuple[float, float]], base: str = "http://localhost:5000",
              profile: str = "driving", annotations: str = "duration") -> list[list[float]]:
        self.calls.append(("table", base, len(points)))
        adj = self._adjacency(self._speeds(base))
        nodes = [self._snap(adj, lat, lng)[0] for lat, lng in points]
        out = []
        for a in nodes:
            dist, _ = self._search(adj, a)
            out.append([round(dist[b], 1) if b in dist else None for b in nodes])
        return clean_table(out)

    def route(self, points: Sequence[tuple[float, float]], base: str = "http://localhost:5000",
              nodes: bool = False) -> dict:
        self.calls.append(("route", base, tuple(points)))
        adj = self._adjacency(self._speeds(base))
        snapped = [self._snap(adj, lat, lng) for lat, lng in points]
        path, duration, legs = [snapped[0][0]], 0.0, []
        for (a, _), (b, _) in zip(snapped, snapped[1:]):
            dist, pred = self._search(adj, a)
            if b not in dist:
                raise OsrmError("OSRM refused the request: NoRoute", code="NoRoute")
            leg = [b]
            while leg[-1] != a:
                leg.append(pred[leg[-1]])
            leg.reverse()
            legs.append({"duration": dist[b], **({"annotation": {"nodes": leg}} if nodes else {})})
            path += leg[1:]
            duration += dist[b]
        line = [[self.coords[n][1], self.coords[n][0]] for n in path]
        if len(line) == 1:
            line.append(line[0])
        waypoints = [{"distance": d, "location": [self.coords[n][1], self.coords[n][0]]} for n, d in snapped]
        return {"duration": duration, "geometry": {"type": "LineString", "coordinates": line},
                "legs": legs, "waypoints": waypoints}
