"""The hand-made toy road map of the road-graph plan.

Coordinates are degrees; at this latitude 0.001 of longitude is about 100.8 m and 0.001 of
latitude about 111.2 m. Worked from the speeds: segment 1 to 2 is about 100.8 m and 14.5 s, the
compressed edge 1 to 3 about 201.6 m and 29.0 s, edge 3 to 6 about 222.4 m and 12.3 s; node 1 to
node 6 takes about 41.3 s and node 6 to node 1 is unreachable.
"""
from __future__ import annotations

from reroute.roadnet import Way

N: dict[int, tuple[float, float]] = {
    1: (24.900, 67.000), 2: (24.900, 67.001), 3: (24.900, 67.002), 4: (24.900, 67.003),
    5: (24.901, 67.002), 6: (24.902, 67.002), 7: (24.910, 67.000), 8: (24.910, 67.010)}


def way(ids: list[int], highway: str, oneway: str = "") -> Way:
    """A way through the toy nodes ``ids`` in order."""
    return Way([(i, *N[i]) for i in ids], highway, oneway)


TOY: list[Way] = [
    way([1, 2, 3, 4], "residential"),        # two-way street, node 2 is a pass-through
    way([3, 5, 6], "primary", "yes"),        # one-way, node 5 is a pass-through
    way([7, 8], "residential"),              # one long segment, about 1 km
]
