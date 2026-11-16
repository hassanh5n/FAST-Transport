"""From a closure scenario to a solver problem, and plans scored on the true travel times.

Pure functions used by ``run_reroute.py`` (experiment-runner plan, Task 1; work plan Sections 5
and 8.3 to 8.4). A scenario and its closure have the shape of the scenario file built by
``build_scenarios.py``: the closure holds ``points`` (stop ids) and two square tables, ``pre`` (no
closure) and ``post`` (closure applied, truth), over those points with campus last; a scenario
names its bus ``position``, the ``remaining`` stops in published order, their ``students`` and the
extra ``candidates`` boarding points.

Problem node layout (as in ``reroute.model``): the scenario's points (remaining stops, then
candidates), then the bus position, then campus.

Delay is always measured against the published route with no closure from the same position
(:func:`baseline_arrival`), whatever table the plan was made or scored on.
"""
from __future__ import annotations

import math
import random
from typing import Mapping, Sequence

from reroute import InvalidPlan, Plan, Problem, StopNeed, evaluate, table_rows
from reroute.ladder import servable

MUST_SERVE_SHARE = 0.25
CHECKPOINTS_S = (1, 5, 30)

Walk = Mapping[tuple[int, int], float]


def case_points(scenario: dict) -> list[int]:
    """The scenario's boarding points: ``remaining`` followed by ``candidates``."""
    return list(scenario["remaining"]) + list(scenario["candidates"])


def sub_table(closure: dict, which: str, scenario: dict) -> list[list[float]]:
    """The (P + 2) square table of this scenario cut from the closure's ``pre`` or ``post`` table.

    Rows and columns: the scenario's points in order, then the bus position, then campus.
    """
    if which not in ("pre", "post"):
        raise ValueError(f"which must be 'pre' or 'post', not {which!r}")
    table = closure[which]
    index = {pid: i for i, pid in enumerate(closure["points"])}
    missing = [p for p in case_points(scenario) + [scenario["position"]] if p not in index]
    if missing:
        raise ValueError(f"scenario {scenario['id']}: points {missing} are not in closure {closure['id']}")
    order = [index[p] for p in case_points(scenario)] + [index[scenario["position"]], len(closure["points"])]
    return [[float(table[a][b]) for b in order] for a in order]


def _case_walk(scenario: dict, walk: Walk) -> dict[tuple[int, int], float]:
    """The walking pairs from a remaining stop to a point of this scenario (the rest cannot matter)."""
    points = case_points(scenario)
    return {(s, p): float(walk[(s, p)]) for s in scenario["remaining"] for p in points
            if s != p and (s, p) in walk}


def build_problem(scenario: dict, closure: dict, walk: Walk, limit_m: float, which: str = "post",
                  must_serve: Sequence[int] = (), rows=None) -> Problem:
    """The solver problem: remaining stops in order with their students, ``limit_m`` and the
    must-serve flags; ``rows`` defaults to the ``which`` table of the closure."""
    ms = set(must_serve)
    stops = [StopNeed(int(s), int(scenario["students"][str(s)]), float(limit_m), int(s) in ms)
             for s in scenario["remaining"]]
    if rows is None:
        rows = table_rows(sub_table(closure, which, scenario))
    return Problem(stops, case_points(scenario), rows, _case_walk(scenario, walk))


def baseline_arrival(scenario: dict, closure: dict, walk: Walk) -> float:
    """Arrival of the published order, every remaining stop visited, on the ``pre`` table."""
    problem = build_problem(scenario, closure, walk, 0.0, which="pre")
    remaining = [int(s) for s in scenario["remaining"]]
    arrival, _ = evaluate(problem, remaining, {s: s for s in remaining})
    return arrival


def score_on_truth(scenario: dict, closure: dict, walk: Walk, limit_m: float, plan: Plan,
                   must_serve: Sequence[int] = (), which: str = "post") -> dict:
    """Replay the plan's visit order and boarding choices on the ``which`` table (truth: ``post``).

    Returns ``status`` (``ok``, or ``invalid_on_truth`` when the plan breaks a rule there or never
    reaches campus), ``arrival_s``, ``delay_s``, ``walkers`` (students boarding away from their
    stop), ``walk_m_per_walker`` (``None`` when nobody walks), ``unserved`` (stops the plan leaves
    unserved) and ``unserved_avoidable`` (of those, stops that had a reachable boarding point).
    """
    truth = build_problem(scenario, closure, walk, limit_m, which=which, must_serve=must_serve)
    out = {"status": "invalid_on_truth", "arrival_s": None, "delay_s": None, "walkers": None,
           "walk_m_per_walker": None, "unserved": len(plan.unserved), "unserved_avoidable": None}
    try:
        arrival, walk_total = evaluate(truth, plan.visit, plan.board_at, plan.unserved)
    except InvalidPlan as err:
        out["error"] = str(err)
        return out
    if not math.isfinite(arrival):
        out["error"] = "a leg of the plan is unreachable on this table"
        return out
    students = {s.id: s.students for s in truth.stops}
    walkers = sum(students[s] for s, p in plan.board_at.items() if s != p)
    no_option = set(servable(truth)[1])
    out.update(status="ok", arrival_s=arrival,
               delay_s=arrival - baseline_arrival(scenario, closure, walk), walkers=walkers,
               walk_m_per_walker=walk_total / walkers if walkers else None,
               unserved_avoidable=sum(1 for s in plan.unserved if s not in no_option))
    return out


def must_serve_draw(scenario: dict) -> list[int]:
    """25% of the remaining stops (rounded up, at least one), drawn with a seed fixed by the id."""
    remaining = list(scenario["remaining"])
    if not remaining:
        return []
    k = max(1, math.ceil(MUST_SERVE_SHARE * len(remaining)))
    rng = random.Random(f"2026-{scenario['id']}")
    return sorted(rng.sample(remaining, k))


def checkpoints(timeline: Sequence[tuple[float, Plan]],
                at: Sequence[float] = CHECKPOINTS_S) -> dict[float, Plan | None]:
    """For each checkpoint, the last plan whose elapsed time is at or before it (``None`` if none)."""
    out: dict[float, Plan | None] = {}
    for t in at:
        held = None
        for elapsed, plan in timeline:
            if elapsed <= t:
                held = plan
        out[t] = held
    return out
