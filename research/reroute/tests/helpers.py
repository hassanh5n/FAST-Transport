"""Test problems for the rerouting solver: the hand-worked tiny problem, seeded random problems
on a metric table, and a brute-force solver to check the exact method against."""
from __future__ import annotations

import itertools
import math
import random

from reroute.model import InvalidPlan, Problem, StopNeed, evaluate, table_rows

INF = float("inf")
# Node indices: 0 = point 1, 1 = point 2, 2 = start, 3 = campus.
TINY = [
    [0,   200, INF, 590],   # from point 1
    [200, 0,   INF, 500],   # from point 2
    [100, 300, 0,   650],   # from start
    [INF, INF, INF, 0],     # from campus
]


def tiny_problem(**overrides) -> Problem:
    """The plan's tiny problem; ``walk``, ``stops``, ``committed`` and ``matrix`` can be replaced."""
    allowed = {"walk", "stops", "committed", "matrix"}
    unknown = set(overrides) - allowed
    if unknown:
        raise TypeError(f"unknown overrides: {sorted(unknown)}")
    stops = overrides.get("stops", [StopNeed(1, 4), StopNeed(2, 2)])
    walk = overrides.get("walk", {(2, 1): 240.0})
    matrix = overrides.get("matrix", TINY)
    return Problem(stops, [1, 2], table_rows(matrix), walk, committed=overrides.get("committed", ()))


def random_problem(seed: int, n_stops: int, n_extra: int, limit_m: float = 400.0) -> Problem:
    """Points, start and campus uniform in a 2 km square; drive time = metres / 10 (metric).

    Point ids are ``1..n_stops + n_extra``; the first ``n_stops`` are remaining stops with 1 to 9
    students each. Walking is the straight-line distance for every stop-point pair within 800 m.
    """
    rng = random.Random(seed)
    n_points = n_stops + n_extra
    xy = [(rng.uniform(0, 2000), rng.uniform(0, 2000)) for _ in range(n_points + 2)]
    students = [rng.randint(1, 9) for _ in range(n_stops)]
    matrix = [[math.dist(a, b) / 10.0 for b in xy] for a in xy]
    walk = {}
    for s in range(n_stops):
        for p in range(n_points):
            metres = math.dist(xy[s], xy[p])
            if s != p and metres <= 800.0:
                walk[(s + 1, p + 1)] = metres
    stops = [StopNeed(i + 1, students[i], walk_limit_m=limit_m) for i in range(n_stops)]
    return Problem(stops, list(range(1, n_points + 1)), table_rows(matrix), walk)


def brute_force(problem: Problem) -> float:
    """Smallest arrival over every boarding choice and every order of the points visited.

    Each servable stop picks one reachable point it can board at; the visited set is the points
    picked plus the committed points, tried in every order. A visit at which nobody boards is not
    enumerated (it only adds stop time on the metric tables these checks use). Unservable stops
    are passed as ``unserved``; ``InvalidPlan`` results are skipped.
    """
    start = problem.row(problem.start)
    reachable = [p for p in problem.points if start[problem.index[p]] < INF]
    choices, unserved = [], []
    for stop in problem.stops:
        options = [p for p in reachable if problem.can_board(stop, p)]
        if options:
            choices.append((stop.id, options))
        else:
            unserved.append(stop.id)
    best = INF
    ids = [sid for sid, _ in choices]
    for picks in itertools.product(*(options for _, options in choices)):
        board_at = dict(zip(ids, picks))
        points = sorted(set(picks) | problem.committed)
        for order in itertools.permutations(points):
            try:
                arrival, _ = evaluate(problem, order, board_at, unserved)
            except InvalidPlan:
                continue
            best = min(best, arrival)
    return best
