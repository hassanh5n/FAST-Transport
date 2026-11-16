"""A toy city for the offline-builder tests: a street grid, two routes and their students.

The grid has 5 rows (``i``) and 6 columns (``j``) of two-way residential streets (25 km/h). Node
``(i, j)`` has map id ``1000 + 10 i + j`` and sits at lat ``24.900 + 0.002 i``, lng
``67.000 + 0.0025 j``: rows are about 222 m apart, columns about 252 m apart. A separate street of
two nodes (900, 901) is joined to nothing, so a stop on it is unreachable by road.

Stops (instance ids are positions in ``STOP_NAMES``)::

    A (0,0)  B (0,4)  C (2,4)      Jadoon R-1: A, B, C (long legs; no closure contains a stop)
    D (3,0)  X (3,1)  E (3,2)  F (3,3)   Nadeem R-2: D, X, E, F, but X has no R-2 students
    Y on the isolated street, campus at (4,5)

Leg 2 of R-2 (E to F, about 252 m) is short enough that its 200 m closure contains both stops.
"""
from __future__ import annotations

from reroute.roadnet import Way, build_tables

ROWS, COLS = 5, 6


def node_id(i: int, j: int) -> int:
    return 1000 + 10 * i + j


def node_at(i: int, j: int) -> tuple[float, float]:
    return (round(24.900 + 0.002 * i, 6), round(67.000 + 0.0025 * j, 6))


Y_POINT = (24.9035, 67.0010)


def ways() -> list[Way]:
    out = [Way([(node_id(i, j), *node_at(i, j)) for j in range(COLS)], "residential") for i in range(ROWS)]
    out += [Way([(node_id(i, j), *node_at(i, j)) for i in range(ROWS)], "residential") for j in range(COLS)]
    out.append(Way([(900, *Y_POINT), (901, Y_POINT[0] + 0.0003, Y_POINT[1])], "residential"))
    return out


TABLES = build_tables(ways())

GRID = {"A": (0, 0), "B": (0, 4), "C": (2, 4), "D": (3, 0), "X": (3, 1), "E": (3, 2), "F": (3, 3)}
STOP_NAMES = ["A", "B", "C", "D", "X", "E", "F", "Y"]
ID = {name: k for k, name in enumerate(STOP_NAMES)}
CAMPUS = node_at(4, 5)


def stop_point(name: str) -> tuple[float, float]:
    return Y_POINT if name == "Y" else node_at(*GRID[name])


INSTANCE = {
    "version": "toy-v1",
    "campus": {"name": "Campus", "lat": CAMPUS[0], "lng": CAMPUS[1]},
    "contractors": {
        "Jadoon": {"baseline_routes": [{"code": "R-1", "stops": ["A", "B", "C"]}]},
        "Nadeem": {"baseline_routes": [{"code": "R-2", "stops": ["D", "X", "E", "F"]}]},
    },
    "stops": [{"name": n, "lat": stop_point(n)[0], "lng": stop_point(n)[1]} for n in STOP_NAMES],
}


def _rows(contractor: str, route: str, counts: dict[str, int]) -> list[dict]:
    return [{"contractor": contractor, "stop": s, "baseline_route": route}
            for s, n in counts.items() for _ in range(n)]


# X has a student only on another Nadeem route, so it is not a stop of R-2.
STUDENT_ROWS = (_rows("Jadoon", "R-1", {"A": 3, "B": 2, "C": 4})
                + _rows("Nadeem", "R-2", {"D": 2, "E": 1, "F": 5})
                + _rows("Nadeem", "R-9", {"X": 1}))

# Directed walking metres. A walks to Y (unreachable by road); D and E walk to X.
WALK = {(ID["A"], ID["Y"]): 150.0, (ID["D"], ID["X"]): 300.0, (ID["E"], ID["X"]): 250.0,
        (ID["C"], ID["B"]): 2000.0}
