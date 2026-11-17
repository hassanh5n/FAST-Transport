"""The method ladder: R0 (patched published route), R2 (greedy), R3 (exact), and :class:`Ladder`,
which runs them in that order, keeps the best plan, and can be saved and restored between slices.

Every method builds a visit order and boarding choices and scores them with
:func:`reroute.model.evaluate`. ``numpy`` is needed by R3 only and is imported inside its
functions, so importing this module needs the standard library alone.
"""
from __future__ import annotations

import base64
import dataclasses
import math
import time
from typing import TYPE_CHECKING

from reroute.model import Plan, Problem, StopNeed, evaluate, make_plan

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import numpy

MAX_EXACT_BITS = 16
_INF = math.inf


# --------------------------------------------------------------------------- shared helpers

def _options(problem: Problem) -> dict[int, list[tuple[float, int]]]:
    """For each stop, the reachable points it can board at as ``(walk_m, point_id)``, best first.

    A point is reachable when the bus position's row has a finite entry for it.
    """
    start = problem.row(problem.start)
    reachable = [p for p in problem.points if start[problem.index[p]] < _INF]
    options: dict[int, list[tuple[float, int]]] = {}
    for stop in problem.stops:
        found = [(problem.walk_m(stop.id, p), p) for p in reachable if problem.can_board(stop, p)]
        options[stop.id] = sorted(found)
    return options


def servable(problem: Problem) -> tuple[list[StopNeed], list[int]]:
    """Split the stops into those with a reachable boarding point and the ids of the rest."""
    options = _options(problem)
    return ([s for s in problem.stops if options[s.id]],
            [s.id for s in problem.stops if not options[s.id]])


def _leg(problem: Problem, a: int, b: int) -> float:
    """Driving seconds between two node indices."""
    return problem.row(a)[b]


def _added_time(through: float, direct: float) -> float:
    """Driving time added by a detour; repairing a broken leg is best, an infinite detour worst."""
    if through == _INF:
        return _INF
    if direct == _INF:
        return -_INF
    return through - direct


def _best_insertion(problem: Problem, order: list[int], point_id: int) -> tuple[int, float]:
    """Position and added driving time of the cheapest insertion; ties go to the earliest."""
    nodes = [problem.start] + [problem.index[p] for p in order] + [problem.campus]
    node = problem.index[point_id]
    best_pos, best_added = 0, _INF
    for pos in range(len(order) + 1):
        a, b = nodes[pos], nodes[pos + 1]
        added = _added_time(_leg(problem, a, node) + _leg(problem, node, b), _leg(problem, a, b))
        if pos == 0 or added < best_added:
            best_pos, best_added = pos, added
    return best_pos, best_added


def insert_cheapest(problem: Problem, order: list[int], point_id: int) -> list[int]:
    """A new order with the point inserted where it adds the least driving time.

    Legs from the bus position and to campus count. Ties go to the earliest position.
    """
    pos, _ = _best_insertion(problem, order, point_id)
    return order[:pos] + [point_id] + order[pos:]


def _nearest_visited(options: list[tuple[float, int]], visited: set[int]) -> int | None:
    """The visited point with the least walking among a stop's options (ties: lowest id)."""
    for _, pid in options:
        if pid in visited:
            return pid
    return None


def _better(new: Plan, old: Plan | None) -> bool:
    """Whether ``new`` should replace ``old``: a lower key and no more unserved stops."""
    return old is None or (new.key < old.key and len(new.unserved) <= len(old.unserved))


# --------------------------------------------------------------------------- R0

def solve_r0(problem: Problem) -> Plan:
    """R0: the published order with the closure patched.

    Every servable stop whose own point is reachable is visited in published order. A servable
    stop whose own point is not boards at the reachable point in range with the least walking
    (ties: lowest id), inserted with :func:`insert_cheapest` if not already visited. Committed
    points not yet visited are inserted the same way, in ascending id order.
    """
    options = _options(problem)
    start = problem.row(problem.start)
    own_ok = {s.id for s in problem.stops if start[problem.index[s.id]] < _INF}
    visit = [s.id for s in problem.stops if s.id in own_ok]
    board_at = {sid: sid for sid in visit}
    for stop in problem.stops:
        if stop.id in own_ok or not options[stop.id]:
            continue
        pid = options[stop.id][0][1]
        board_at[stop.id] = pid
        if pid not in visit:
            visit = insert_cheapest(problem, visit, pid)
    for pid in sorted(problem.committed):
        if pid not in visit:
            visit = insert_cheapest(problem, visit, pid)
    unserved = [s.id for s in problem.stops if not options[s.id]]
    return make_plan(problem, "R0", visit, board_at, unserved)


# --------------------------------------------------------------------------- R2

def solve_r2(problem: Problem) -> Plan:
    """R2: greedy insertion by students boarded per second of detour, then a removal pass.

    1. Start from the committed points, inserted cheapest-first in ascending id order.
    2. Repeatedly insert the unvisited reachable point with the largest gain / cost, where gain is
       the students of unassigned stops that can board there (a zero-student stop counts as one)
       and cost is the added driving time plus ``stop_base_s``; those stops board there. Stops
       left over can board only at points already visited and go to the nearest one.
    3. Improve, in rounds, until a round changes nothing (at most ``_R2_MAX_ROUNDS``):
       a. the visiting order by local search (:func:`_improve_order`: move one point, or reverse
          a segment, while that lowers the key);
       b. removals (:func:`_remove_points`): drop a non-committed visited point and move its
          stops to the nearest visited point in range, while that lowers the key;
       c. move every stop to its nearest visited point if that does not make the key worse;
       d. one addition (:func:`_add_point`): the unvisited point, position and boarders that
          lower the key most; stops move to it only if it shortens their walk. If no addition
          helps, one swap (:func:`_swap_point`): a visited point out, an unvisited one in.
    4. Fall back to R0's plan (method ``"R2"``) if R0 arrives earlier.
    """
    options = _options(problem)
    by_id = {s.id: s for s in problem.stops}
    unserved = [s.id for s in problem.stops if not options[s.id]]
    boarders: dict[int, list[int]] = {}
    for stop in problem.stops:
        for _, pid in options[stop.id]:
            boarders.setdefault(pid, []).append(stop.id)
    base = problem.params.stop_base_s

    order: list[int] = []
    for pid in sorted(problem.committed):
        order = insert_cheapest(problem, order, pid)
    board_at: dict[int, int] = {}
    unassigned = {s.id for s in problem.stops if options[s.id]}
    while unassigned:
        visited = set(order)
        best = None                                   # (ratio, point id, position)
        for pid in sorted(boarders):
            if pid in visited:
                continue
            gain = sum(max(by_id[sid].students, 1) for sid in boarders[pid] if sid in unassigned)
            if gain == 0:
                continue
            pos, added = _best_insertion(problem, order, pid)
            cost = added + base
            ratio = _INF if cost <= 0 else gain / cost
            if best is None or ratio > best[0]:
                best = (ratio, pid, pos)
        if best is None:
            break
        _, pid, pos = best
        order.insert(pos, pid)
        for sid in boarders[pid]:
            if sid in unassigned:
                board_at[sid] = pid
                unassigned.discard(sid)
    for sid in sorted(unassigned):
        board_at[sid] = _nearest_visited(options[sid], set(order))

    key = evaluate(problem, order, board_at, unserved)
    for _ in range(_R2_MAX_ROUNDS):
        order, key = _improve_order(problem, order, board_at, unserved, key)
        order, board_at, key, removed = _remove_points(problem, options, order, board_at, unserved, key)
        visited = set(order)
        nearest = {sid: _nearest_visited(options[sid], visited) for sid in board_at}
        moved = False
        if nearest != board_at:
            near_key = evaluate(problem, order, nearest, unserved)
            if near_key <= key:
                board_at, key, moved = nearest, near_key, True
        order, board_at, key, added = _add_point(problem, options, order, board_at, unserved, key)
        if not added:
            order, board_at, key, added = _swap_point(problem, options, order, board_at, unserved, key)
        if not (removed or moved or added):
            break

    plan = make_plan(problem, "R2", order, board_at, unserved)
    r0 = solve_r0(problem)
    if r0.arrival_s < plan.arrival_s:
        return dataclasses.replace(r0, method="R2")
    return plan


_R2_MAX_ROUNDS = 25


def _remove_points(problem: Problem, options: Mapping[int, list[tuple[float, int]]], order: list[int],
                   board_at: dict[int, int], unserved: Sequence[int], key: tuple[float, float]
                   ) -> tuple[list[int], dict[int, int], tuple[float, float], bool]:
    """Removal passes of R2 until one changes nothing; returns the plan and whether any point went."""
    removed_any, changed = False, True
    while changed:
        changed = False
        for pid in list(order):
            if pid in problem.committed or pid not in order:
                continue
            trial_order = [q for q in order if q != pid]
            remaining = set(trial_order)
            trial_board = dict(board_at)
            for sid, at in board_at.items():
                if at == pid:
                    trial_board[sid] = _nearest_visited(options[sid], remaining)
            if None in trial_board.values():
                continue
            trial_key = evaluate(problem, trial_order, trial_board, unserved)
            if trial_key < key:
                order, board_at, key, changed, removed_any = trial_order, trial_board, trial_key, True, True
    return order, board_at, key, removed_any


def _add_point(problem: Problem, options: Mapping[int, list[tuple[float, int]]], order: list[int],
               board_at: dict[int, int], unserved: Sequence[int], key: tuple[float, float]
               ) -> tuple[list[int], dict[int, int], tuple[float, float], bool]:
    """The best single addition of an unvisited point, if it lowers the key.

    A stop moves to the new point only when that shortens its walk; a point that would board
    nobody is not tried (it only adds stop time). Every position is scored, because adding a
    point can cut the time the bus waits for walkers even when it adds driving. O(U x n^2) for U
    candidate points and n visited points.
    """
    visited = set(order)
    walk_of = {sid: {q: d for d, q in opts} for sid, opts in options.items()}
    best = None
    for pid in sorted({q for opts in options.values() for _, q in opts} - visited):
        board = dict(board_at)
        for sid, at in board_at.items():
            w = walk_of[sid]
            if pid in w and w[pid] < w.get(at, _INF):
                board[sid] = pid
        if board == board_at:
            continue
        for pos in range(len(order) + 1):
            visit = order[:pos] + [pid] + order[pos:]
            k = evaluate(problem, visit, board, unserved)
            if k < key and (best is None or k < best[0]):
                best = (k, visit, board)
    if best is None:
        return order, board_at, key, False
    return best[1], best[2], best[0], True


def _swap_point(problem: Problem, options: Mapping[int, list[tuple[float, int]]], order: list[int],
                board_at: dict[int, int], unserved: Sequence[int], key: tuple[float, float]
                ) -> tuple[list[int], dict[int, int], tuple[float, float], bool]:
    """The best single swap of a visited, non-committed point for an unvisited one, if it lowers
    the key. The new point takes the position of the old one or any other; the old point's stops
    move to their nearest remaining visited point, and any stop moves to the new point when that
    shortens its walk. O(V x U x n^2) evaluations of :func:`evaluate`.
    """
    walk_of = {sid: {q: d for d, q in opts} for sid, opts in options.items()}
    unvisited = sorted({q for opts in options.values() for _, q in opts} - set(order))
    best = None
    for out in order:
        if out in problem.committed:
            continue
        rest = [q for q in order if q != out]
        for pid in unvisited:
            keep = set(rest) | {pid}
            board = {}
            for sid, at in board_at.items():
                target = at if at != out else _nearest_visited(options[sid], keep)
                if target is None:
                    break
                w = walk_of[sid]
                if pid in w and w[pid] < w.get(target, _INF):
                    target = pid
                board[sid] = target
            else:
                if pid not in board.values():
                    continue
                for pos in range(len(rest) + 1):
                    visit = rest[:pos] + [pid] + rest[pos:]
                    k = evaluate(problem, visit, board, unserved)
                    if k < key and (best is None or k < best[0]):
                        best = (k, visit, board)
    if best is None:
        return order, board_at, key, False
    return best[1], best[2], best[0], True


def _improve_order(problem: Problem, order: list[int], board_at: Mapping[int, int],
                   unserved: Sequence[int], key: tuple[float, float],
                   max_passes: int = 50) -> tuple[list[int], tuple[float, float]]:
    """Local search on the visiting order with the boarding points fixed.

    Neighbours: move one point to another position (or-opt of length 1) and reverse a segment
    (2-opt; with the waits for walkers the table is not symmetric in time, so every reversal is
    scored). The first neighbour that lowers the key is taken and the pass starts again; it stops
    when a pass finds nothing, or after ``max_passes`` improvements. Each neighbour is scored with
    :func:`evaluate`, so a pass costs O(n^3) for n visited points (n is at most a few dozen).
    Greedy insertion alone left R2 a median 70 to 285 s behind R3 on synthetic problems
    (logbook, 2026-11-17).
    """
    n = len(order)
    if n < 2 or key[0] == _INF:
        return order, key
    for _ in range(max_passes):
        improved = False
        candidates = []
        for i in range(n):
            rest = order[:i] + order[i + 1:]
            candidates.extend(rest[:j] + [order[i]] + rest[j:] for j in range(n) if j != i)
        for i in range(n - 1):
            candidates.extend(order[:i] + order[i:j][::-1] + order[j:] for j in range(i + 2, n + 1))
        for cand in candidates:
            k = evaluate(problem, cand, board_at, unserved)
            if k < key:
                order, key, improved = cand, k, True
                break
        if not improved:
            break
    return order, key


# --------------------------------------------------------------------------- R3
#
# R3 runs in two phases, both processing boarded-stop masks in increasing order and both
# resumable between slices:
#
# 1. The search: a vectorised dynamic programme over (mask, last point). It does not remember
#    which points were visited, so its best path may come back to a point. That makes it a
#    relaxation: its value is a lower bound on the best plan's arrival (on tables that satisfy
#    the triangle inequality). If the best path visits no point twice, or merging the repeats
#    still reaches the search's value, that plan is optimal and R3 stops there.
# 2. The repair, run only otherwise: an exact label search over (mask, last point) that keeps
#    the set of visited points in each label and never returns to one. Labels are pruned by
#    dominance (no later, no more walking, a subset of the visited points) and by a bound
#    against the earlier of the merged plan and R2's plan. Merging cannot replace it: moving
#    a first visit's boarders to the last visit puts their boarding time after any wait for
#    walkers there.

def _encode(array: numpy.ndarray) -> dict:
    return {"dtype": str(array.dtype), "shape": list(array.shape),
            "data": base64.b64encode(array.tobytes()).decode("ascii")}


def _decode(d: dict) -> numpy.ndarray:
    import numpy as np
    raw = base64.b64decode(d["data"])
    return np.frombuffer(raw, dtype=np.dtype(d["dtype"])).reshape(d["shape"]).copy()


def _tolerance(x: float) -> float:
    """Slack for comparing arrival times summed in different orders."""
    return 1e-6 * max(1.0, abs(x))


def _cannot_beat(ctx: _R3Context, k: int, leave: float, rest: int, limit: float) -> bool:
    """Whether a bus leaving point index ``k`` at ``leave``, with the bits in ``rest`` still to
    board and no point visited twice, surely arrives after ``limit``.

    Uses lower bounds that hold on tables satisfying the triangle inequality. Driving: the bus
    must still pass a point (other than ``k``) that can board each remaining bit, then reach
    campus, and stop once more for all remaining students. Waiting: for each remaining bit, the
    bus leaves a point that can board it no earlier than its walkers are ready there plus one
    stop for that bit's students, then drives to campus.
    """
    campus = ctx.campus_list[k]
    if not rest:
        return leave + campus > limit
    reach, bit_students = ctx.reach[k], ctx.bit_students
    drive, students, bits = 0.0, 0, []
    while rest:
        low = rest & -rest
        rest ^= low
        bit = low.bit_length() - 1
        bits.append(bit)
        if reach[bit] > drive:
            drive = reach[bit]
        students += bit_students[bit]
    params = ctx.problem.params
    if drive == _INF:
        return True
    if leave + drive + params.stop_base_s + params.stop_per_student_s * students > limit:
        return True
    options = ctx.bound_options[k]
    for bit in bits:
        if all(max(leave + to_point, ready) + stop_s + to_campus > limit
               for to_point, ready, to_campus, stop_s in options[bit]):
            return True
    return False


class _Repair:
    """The exact label search of R3's second phase.

    ``labels[i]`` is ``[mask, k, leave, walk, visited, parent, alive]``: the bus leaves point
    index ``k`` at ``leave`` having boarded ``mask``, with ``walk`` student-metres, having
    visited the point indices in the bit set ``visited``; ``parent`` is the label it came from.
    Label 0 is the bus position (``k == -1``). A label is marked dead when a later label
    dominates it; that only happens before its mask is processed, so a dead label has no
    children. ``upper`` is the arrival of a plan already known (the merged plan or R2's): labels
    that :func:`_cannot_beat` it are dropped.
    """

    def __init__(self, upper: float, labels: list[list] | None = None,
                 next_mask: int = 0) -> None:
        self.upper = upper
        self.labels = labels if labels is not None else [[0, -1, 0.0, 0.0, 0, -1, True]]
        self.next_mask = next_mask
        self.buckets: dict[int, dict[int, list[int]]] = {}
        for i, lab in enumerate(self.labels):
            if lab[6] and lab[0] >= next_mask:
                self.buckets.setdefault(lab[0], {}).setdefault(lab[1], []).append(i)

    def to_json(self) -> dict:
        return {"upper": self.upper if math.isfinite(self.upper) else None,
                "next_mask": self.next_mask, "labels": self.labels}

    @classmethod
    def from_json(cls, d: dict) -> _Repair:
        upper = _INF if d["upper"] is None else float(d["upper"])
        return cls(upper, [list(lab) for lab in d["labels"]], int(d["next_mask"]))

    def _insert(self, mask: int, k: int, leave: float, walk: float, visited: int,
                parent: int) -> None:
        """Add a label unless one already at ``(mask, k)`` dominates it; drop those it dominates."""
        bucket = self.buckets.setdefault(mask, {}).setdefault(k, [])
        survivors = []
        for i in bucket:
            _, _, t, w, v, _, _ = self.labels[i]
            if t <= leave and w <= walk and v & ~visited == 0:
                return
            if leave <= t and walk <= w and visited & ~v == 0:
                self.labels[i][6] = False
            else:
                survivors.append(i)
        survivors.append(len(self.labels))
        self.labels.append([mask, k, leave, walk, visited, parent, True])
        bucket[:] = survivors

    def expand(self, ctx: _R3Context, mask: int) -> None:
        """Extend every live label of ``mask`` to each unvisited point, boarding a prefix there."""
        by_point = self.buckets.pop(mask, {})
        base = ctx.problem.params.stop_base_s
        full = (1 << (len(ctx.bit_stops) + len(ctx.bit_points))) - 1
        n_points = len(ctx.point_ids)
        limit = self.upper + _tolerance(self.upper) if math.isfinite(self.upper) else _INF
        for k, ids in by_point.items():
            for i in ids:
                _, _, t, w, visited, _, _ = self.labels[i]
                for k2 in range(n_points):
                    if visited >> k2 & 1:
                        continue
                    arrive = t + (ctx.start_list[k2] if k < 0 else ctx.drive_list[k][k2])
                    if arrive == _INF:
                        continue
                    boarded, board_s, walk_m = 0, 0.0, 0.0
                    for bit_value, ready, board, metres in ctx.groups[k2]:
                        if mask & bit_value:
                            continue
                        boarded |= bit_value
                        board_s += board
                        walk_m += metres
                        leave = max(arrive, ready) + base + board_s
                        new_mask = mask | boarded
                        if _cannot_beat(ctx, k2, leave, full & ~new_mask, limit):
                            continue
                        self._insert(new_mask, k2, leave, w + walk_m, visited | 1 << k2, i)

    def best_path(self, ctx: _R3Context) -> list[tuple[int, int]] | None:
        """``(point index, bits boarded)`` per visit of the best finished label, or ``None``."""
        full = (1 << (len(ctx.bit_stops) + len(ctx.bit_points))) - 1
        best, best_key = None, (_INF, _INF)
        for i, (mask, k, t, w, _, _, alive) in enumerate(self.labels):
            if alive and mask == full and k >= 0:
                key = (t + ctx.campus_list[k], w)
                if key < best_key:
                    best, best_key = i, key
        if best is None or best_key[0] == _INF:
            return None
        steps = []
        while best > 0:
            mask, k, _, _, _, parent, _ = self.labels[best]
            steps.append((k, mask & ~self.labels[parent][0]))
            best = parent
        steps.reverse()
        return steps


class R3State:
    """The exact method's search tables, resumable between slices.

    One bit per servable stop (published order), then one per committed point (ascending id).
    ``value[mask, k]`` is the earliest time the bus can leave point ``point_ids[k]`` having boarded
    exactly the stops in ``mask``, revisits allowed; ``walk`` is the walking (student-metres) of
    that entry, used only to break ties between equal leaving times. ``parent_mask`` and
    ``parent_point`` (``-1`` for the bus position) rebuild the path. Masks are processed in
    increasing order; ``next_mask`` is the first not yet processed. ``repair`` holds the second
    phase (see the comment above) once it has started, else ``None``.
    """

    def __init__(self, bit_stops: list[int], bit_points: list[int], point_ids: list[int],
                 value: numpy.ndarray, walk: numpy.ndarray, parent_mask: numpy.ndarray,
                 parent_point: numpy.ndarray, next_mask: int = 0, done: bool = False,
                 repair: _Repair | None = None) -> None:
        self.bit_stops = bit_stops
        self.bit_points = bit_points
        self.point_ids = point_ids
        self.value = value
        self.walk = walk
        self.parent_mask = parent_mask
        self.parent_point = parent_point
        self.next_mask = next_mask
        self.done = done
        self.repair = repair
        self._ctx: _R3Context | None = None

    @property
    def n_bits(self) -> int:
        return len(self.bit_stops) + len(self.bit_points)

    def to_json(self) -> dict:
        """JSON types only; arrays are base64 strings of their bytes with shape and dtype."""
        return {"bit_stops": list(self.bit_stops), "bit_points": list(self.bit_points),
                "point_ids": list(self.point_ids), "next_mask": self.next_mask, "done": self.done,
                "value": _encode(self.value), "walk": _encode(self.walk),
                "parent_mask": _encode(self.parent_mask),
                "parent_point": _encode(self.parent_point),
                "repair": None if self.repair is None else self.repair.to_json()}

    @classmethod
    def from_json(cls, d: dict) -> R3State:
        """Inverse of :meth:`to_json`."""
        repair = d.get("repair")
        return cls(list(d["bit_stops"]), list(d["bit_points"]), list(d["point_ids"]),
                   _decode(d["value"]), _decode(d["walk"]), _decode(d["parent_mask"]),
                   _decode(d["parent_point"]), int(d["next_mask"]), bool(d["done"]),
                   None if repair is None else _Repair.from_json(repair))


@dataclasses.dataclass
class _R3Context:
    """Static tables derived from the problem; rebuilt after a restore, never saved.

    Boarding pairs ``(point k, bit)`` are grouped by point and sorted by ready time inside each
    group, so the prefixes of a group are the sets of stops worth boarding there together.
    """

    problem: Problem
    bit_stops: list[int]
    bit_points: list[int]
    point_ids: list[int]
    unserved: list[int]
    # Filled by _r3_tables:
    start: numpy.ndarray | None = None        # (K,) bus position to each point
    drive: numpy.ndarray | None = None        # (K, K) point to point
    campus: numpy.ndarray | None = None       # (K,) point to campus
    pair_k: numpy.ndarray | None = None       # point of each pair
    pair_bit: numpy.ndarray | None = None     # 1 << bit
    pair_cum: numpy.ndarray | None = None     # OR of the group's bits up to this pair
    pair_ready: numpy.ndarray | None = None   # walkers' ready time
    pair_vals: numpy.ndarray | None = None    # (E, 2) boarding seconds, students x metres
    pair_first: numpy.ndarray | None = None   # index of the first pair of each pair's group
    # Plain-Python copies for the repair phase:
    groups: list[list[tuple[int, float, float, float]]] = dataclasses.field(default_factory=list)
    start_list: list[float] = dataclasses.field(default_factory=list)
    drive_list: list[list[float]] = dataclasses.field(default_factory=list)
    campus_list: list[float] = dataclasses.field(default_factory=list)
    bit_students: list[int] = dataclasses.field(default_factory=list)
    # For _cannot_beat: bound_options[k][bit] lists (drive k to q, ready at q, q to campus, stop
    # seconds) for every other point q where the bit can board; reach[k][bit] is the least
    # drive k to q plus q to campus over those points (inf when there are none).
    bound_options: list[list[list[tuple[float, float, float, float]]]] = dataclasses.field(
        default_factory=list)
    reach: list[list[float]] = dataclasses.field(default_factory=list)


def _r3_layout(problem: Problem) -> _R3Context:
    """Bits, useful points and unserved stops, without fetching any row but the start row."""
    options = _options(problem)
    bit_stops = [s.id for s in problem.stops if options[s.id]]
    bit_points = sorted(problem.committed)
    if len(bit_stops) + len(bit_points) > MAX_EXACT_BITS:
        raise ValueError("too many stops for the exact method")
    useful = {pid for sid in bit_stops for _, pid in options[sid]}
    start = problem.row(problem.start)
    useful |= {pid for pid in bit_points if start[problem.index[pid]] < _INF}
    point_ids = [p for p in problem.points if p in useful]
    unserved = [s.id for s in problem.stops if not options[s.id]]
    return _R3Context(problem, bit_stops, bit_points, point_ids, unserved)


def _r3_tables(ctx: _R3Context) -> None:
    """Fetch every row with one call and build the numeric tables of ``ctx``."""
    import numpy as np
    problem, params = ctx.problem, ctx.problem.params
    nodes = [problem.index[p] for p in ctx.point_ids]
    problem.fetch([problem.start] + nodes)
    width = len(problem.points) + 2
    rows = np.array([problem.row(n) for n in nodes], dtype=np.float64).reshape(len(nodes), width)
    ctx.start = np.array(problem.row(problem.start), dtype=np.float64)[nodes]
    ctx.drive = rows[:, nodes]
    ctx.campus = rows[:, problem.campus]
    ctx.start_list = ctx.start.tolist()
    ctx.drive_list = ctx.drive.tolist()
    ctx.campus_list = ctx.campus.tolist()

    by_id = {s.id: s for s in problem.stops}
    ctx.bit_students = ([by_id[sid].students for sid in ctx.bit_stops]
                        + [0] * len(ctx.bit_points))
    pairs = []                          # (k, bit value, cum, ready, board, walk, first)
    ctx.groups = []
    for k, pid in enumerate(ctx.point_ids):
        group = []
        for bit, sid in enumerate(ctx.bit_stops):
            stop = by_id[sid]
            if problem.can_board(stop, pid):
                group.append((problem.ready_s(sid, pid), bit,
                              params.stop_per_student_s * stop.students,
                              stop.students * problem.walk_m(sid, pid)))
        for j, cid in enumerate(ctx.bit_points):
            if cid == pid:
                group.append((0.0, len(ctx.bit_stops) + j, 0.0, 0.0))
        group.sort()
        ctx.groups.append([(1 << bit, ready, board, walk) for ready, bit, board, walk in group])
        cum = 0
        first = len(pairs)
        for ready, bit, board, walk in group:
            cum |= 1 << bit
            pairs.append((k, 1 << bit, cum, ready, board, walk, first))
    cols = list(zip(*pairs)) if pairs else [()] * 7
    n_pairs = len(pairs)
    ctx.pair_k = np.array(cols[0], dtype=np.int64)
    ctx.pair_bit = np.array(cols[1], dtype=np.int64)
    ctx.pair_cum = np.array(cols[2], dtype=np.int64)
    ctx.pair_ready = np.array(cols[3], dtype=np.float64)
    ctx.pair_vals = np.array([cols[4], cols[5]], dtype=np.float64).reshape(2, n_pairs).T.copy()
    ctx.pair_first = np.array(cols[6], dtype=np.int64)

    n_bits = len(ctx.bit_stops) + len(ctx.bit_points)
    at_points: list[list[tuple[int, float, float]]] = [[] for _ in range(n_bits)]
    for k, group in enumerate(ctx.groups):
        for bit_value, ready, board, _ in group:
            at_points[bit_value.bit_length() - 1].append((k, ready, board))
    ctx.bound_options = [
        [[(ctx.drive_list[k][q], ready, ctx.campus_list[q], params.stop_base_s + board)
          for q, ready, board in at_points[bit] if q != k] for bit in range(n_bits)]
        for k in range(len(ctx.point_ids))]
    ctx.reach = [[min((d + c for d, _, c, _ in opts), default=_INF) for opts in per_bit]
                 for per_bit in ctx.bound_options]


def _context(problem: Problem, state: R3State) -> _R3Context:
    """The static tables for ``state``, rebuilt if the state was restored or the problem changed."""
    ctx = state._ctx
    if ctx is not None and ctx.problem is problem:
        return ctx
    ctx = _r3_layout(problem)
    if (ctx.bit_stops, ctx.bit_points, ctx.point_ids) != (
            state.bit_stops, state.bit_points, state.point_ids):
        raise ValueError("this R3 state was made for a different problem")
    _r3_tables(ctx)
    state._ctx = ctx
    return ctx


def r3_start(problem: Problem) -> R3State:
    """Set up the exact search. Raises ``ValueError`` when there are more than
    :data:`MAX_EXACT_BITS` servable stops plus committed points."""
    import numpy as np
    ctx = _r3_layout(problem)
    _r3_tables(ctx)
    n_masks, k = 1 << (len(ctx.bit_stops) + len(ctx.bit_points)), len(ctx.point_ids)
    state = R3State(ctx.bit_stops, ctx.bit_points, ctx.point_ids,
                    value=np.full((n_masks, k), _INF), walk=np.full((n_masks, k), _INF),
                    parent_mask=np.zeros((n_masks, k), dtype=np.uint16),
                    parent_point=np.full((n_masks, k), -1, dtype=np.int16))
    state._ctx = ctx
    return state


def _group_prefix_sums(ctx: _R3Context, free: numpy.ndarray) -> numpy.ndarray:
    """``(E, 2)``: boarding seconds and walking of the free pairs in each group prefix.

    A cumulative sum over all pairs, minus its value just before each pair's group starts, so
    the work grows linearly with the number of pairs.
    """
    import numpy as np
    cum = np.cumsum(ctx.pair_vals * free[:, None], axis=0)
    before = np.vstack([np.zeros((1, 2)), cum])[ctx.pair_first]
    return cum - before


def _expand(ctx: _R3Context, state: R3State, mask: int) -> None:
    """Relax every transition out of ``mask``: drive to a point, board a prefix of its group."""
    import numpy as np
    n_points = len(ctx.point_ids)
    if mask == 0:
        arrive = ctx.start
        came_from = np.full(n_points, -1, dtype=np.int64)
        walk_in = np.zeros(n_points)
    else:
        row = state.value[mask]
        if row.size == 0 or row.min() == _INF:
            return                                    # no point, or no way to board these stops
        cand = row[:, None] + ctx.drive
        came_from = cand.argmin(axis=0)
        arrive = cand[came_from, np.arange(n_points)]
        walk_in = state.walk[mask][came_from]

    free = (ctx.pair_bit & mask) == 0
    arr = arrive[ctx.pair_k]
    valid = np.flatnonzero(free & (arr < _INF))
    if valid.size == 0:
        return
    sums = _group_prefix_sums(ctx, free)[valid]
    ks = ctx.pair_k[valid]
    flat = (ctx.pair_cum[valid] | mask) * n_points + ks
    leave = (np.maximum(arr[valid], ctx.pair_ready[valid]) + ctx.problem.params.stop_base_s
             + sums[:, 0])
    new_walk = walk_in[ks] + sums[:, 1]
    values, walks = state.value.reshape(-1), state.walk.reshape(-1)
    cur, cur_walk = values[flat], walks[flat]
    better = np.flatnonzero((leave < cur) | ((leave == cur) & (new_walk < cur_walk)))
    if better.size == 0:
        return
    idx = flat[better]
    values[idx] = leave[better]
    walks[idx] = new_walk[better]
    state.parent_mask.reshape(-1)[idx] = mask
    state.parent_point.reshape(-1)[idx] = came_from[ks[better]]


def _plan_from_steps(ctx: _R3Context, steps: list[tuple[int, int]]) -> Plan:
    """A plan from ``(point index, bits boarded)`` visits; a repeated point is merged into its
    last occurrence (all its stops board at the later visit)."""
    last = {k: i for i, (k, _) in enumerate(steps)}
    visit = [ctx.point_ids[k] for i, (k, _) in enumerate(steps) if last[k] == i]
    board_at = {}
    for k, bits in steps:
        for bit, sid in enumerate(ctx.bit_stops):
            if bits >> bit & 1:
                board_at[sid] = ctx.point_ids[k]
    return make_plan(ctx.problem, "R3", visit, board_at, ctx.unserved)


def _search_result(ctx: _R3Context, state: R3State) -> tuple[Plan | None, float]:
    """The first phase's best path as a plan (repeats merged) and the search's value.

    The plan is ``None`` when the search found no way to board every bit; the value is then
    infinite.
    """
    import numpy as np
    full = (1 << state.n_bits) - 1
    total = state.value[full] + ctx.campus
    if not total.size or total.min() == _INF:
        return None, _INF
    best = float(total.min())
    tied = np.flatnonzero(total == best)
    k = int(tied[np.argmin(state.walk[full][tied])])
    steps = []                                       # (point index, bits boarded there)
    mask = full
    while True:
        prev_mask, prev_k = int(state.parent_mask[mask, k]), int(state.parent_point[mask, k])
        steps.append((k, mask & ~prev_mask))
        if prev_k < 0:
            break
        mask, k = prev_mask, prev_k
    steps.reverse()
    return _plan_from_steps(ctx, steps), best


def _finish_search(ctx: _R3Context, state: R3State, upper_bound: float | None) -> None:
    """After the last mask of the search: stop if its plan is certified, else start the repair,
    bounded by the earlier of the merged plan and ``upper_bound`` (the arrival of a plan at least
    as good as R2's; R2 is run when it is not given)."""
    if state.n_bits == 0:
        state.done = True
        return
    plan, best = _search_result(ctx, state)
    if plan is None or plan.arrival_s <= best + _tolerance(best):
        state.done = True
    else:
        if upper_bound is None:
            upper_bound = solve_r2(ctx.problem).arrival_s
        state.repair = _Repair(min(plan.arrival_s, upper_bound))


def r3_advance(problem: Problem, state: R3State, max_masks: int | None = None,
               deadline: float | None = None, upper_bound: float | None = None) -> R3State:
    """Process masks in increasing order: the search's from ``state.next_mask``, then the
    repair's, if one is needed.

    Stops after ``max_masks`` masks or once ``time.perf_counter()`` passes ``deadline``,
    whichever comes first. Returns the same state object, updated. ``upper_bound`` is the arrival
    of a plan already known to be at least as good as R2's (the ladder passes its best plan's);
    it bounds the repair, and without it R2 is run when the repair starts.
    """
    ctx = _context(problem, state)
    n_masks = 1 << state.n_bits
    processed = 0
    while True:
        if state.next_mask >= n_masks and state.repair is None and not state.done:
            _finish_search(ctx, state, upper_bound)
        if state.repair is not None and state.repair.next_mask >= n_masks - 1:
            state.done = True
        if state.done:
            break
        if (max_masks is not None and processed >= max_masks) or (
                deadline is not None and time.perf_counter() > deadline):
            break
        if state.repair is None:
            _expand(ctx, state, state.next_mask)
            state.next_mask += 1
        else:
            state.repair.expand(ctx, state.repair.next_mask)
            state.repair.next_mask += 1
        processed += 1
    return state


def r3_plan(problem: Problem, state: R3State, fallback: Plan | None = None) -> Plan:
    """The exact method's plan, method ``"R3"``. Requires ``state.done``.

    This is the search's plan when it was certified, else the better of the merged plan and the
    repair's plan; if that arrives later than R2's, R2's visit order and boarding choices are
    returned under method ``"R3"``. On a table that satisfies the triangle inequality the result
    is the optimum: the repair prunes only labels that cannot beat R2, so when it keeps nothing
    better, R2's plan is optimal. On a table that does not, the search's value need not be a
    bound and the pruning need not be safe; the result is then valid and no later than R2's.
    ``fallback`` is a plan already known to be at least as good as R2's (the ladder passes its
    best plan); without it, R2 is run when needed.
    """
    if not state.done:
        raise ValueError("the R3 search has not finished")
    ctx = _context(problem, state)
    if state.n_bits == 0:
        return make_plan(problem, "R3", [], {}, ctx.unserved)

    plan, best = _search_result(ctx, state)
    if state.repair is not None:
        steps = state.repair.best_path(ctx)
        if steps is not None:
            exact = _plan_from_steps(ctx, steps)
            if plan is None or exact.key < plan.key:
                plan = exact
    if plan is not None and plan.arrival_s <= best + _tolerance(best):
        return plan

    if fallback is None:
        fallback = solve_r2(problem)
    if plan is None or fallback.arrival_s < plan.arrival_s:
        return dataclasses.replace(fallback, method="R3")
    return plan


def solve_r3(problem: Problem) -> Plan:
    """R3: the exact method, run to the end in one go."""
    state = r3_start(problem)
    r3_advance(problem, state)
    return r3_plan(problem, state)


def lower_bound(problem: Problem) -> float:
    """Direct time to campus, plus ``stop_base_s`` for the fewest points that could board every
    servable stop, plus ``stop_per_student_s`` per student at servable stops.

    A bound on tables that satisfy the triangle inequality.
    """
    options = _options(problem)
    direct = problem.row(problem.start)[problem.campus]
    serv = [s for s in problem.stops if options[s.id]]
    if not serv:
        return direct
    cover: dict[int, int] = {}
    for stop in serv:
        for _, pid in options[stop.id]:
            cover[pid] = cover.get(pid, 0) + 1
    params = problem.params
    return (direct + params.stop_base_s * math.ceil(len(serv) / max(cover.values()))
            + params.stop_per_student_s * sum(s.students for s in serv))


# --------------------------------------------------------------------------- the ladder

class Ladder:
    """Runs R0, then R2, then R3 in slices, keeping the best plan found so far.

    ``stage`` is the next thing to run: ``"R0"``, ``"R2"``, ``"R3"`` or ``"done"``. ``best`` is
    replaced only by a plan with a lower key and no more unserved stops. When R3 is skipped
    because the problem is too large, ``bound`` holds :func:`lower_bound`.
    """

    def __init__(self, problem: Problem) -> None:
        self.problem = problem
        self.best: Plan | None = None
        self.stage = "R0"
        self.bound: float | None = None
        self._r3: R3State | None = None

    @property
    def done(self) -> bool:
        return self.stage == "done"

    def _offer(self, plan: Plan) -> None:
        if _better(plan, self.best):
            self.best = plan

    def step(self, max_masks: int | None = None, deadline: float | None = None) -> Plan:
        """Run the next piece of work and return ``best``.

        R0 and R2 each run in full in one call. After R2 the ladder either finishes (R3 skipped
        for size) or moves to R3, which later calls advance by a slice of ``max_masks`` masks or
        until ``deadline``.
        """
        if self.stage == "R0":
            self._offer(solve_r0(self.problem))
            self.stage = "R2"
        elif self.stage == "R2":
            self._offer(solve_r2(self.problem))
            bits = len(servable(self.problem)[0]) + len(self.problem.committed)
            if bits > MAX_EXACT_BITS:
                self.bound = lower_bound(self.problem)
                self.stage = "done"
            else:
                self.stage = "R3"
        elif self.stage == "R3":
            if self._r3 is None:
                self._r3 = r3_start(self.problem)
            r3_advance(self.problem, self._r3, max_masks=max_masks, deadline=deadline,
                       upper_bound=self.best.arrival_s)
            if self._r3.done:
                self._offer(r3_plan(self.problem, self._r3, fallback=self.best))
                self._r3 = None
                self.stage = "done"
        return self.best

    def run(self, deadline: float | None = None) -> Plan:
        """Step until done or past ``deadline``; R0 always completes, even past the deadline."""
        if self.stage == "R0":
            self.step()
        while not self.done and (deadline is None or time.perf_counter() < deadline):
            self.step(deadline=deadline)
        return self.best

    def to_json(self) -> dict:
        """JSON types only: the stage, the best plan, the bound and the R3 state if any."""
        return {"stage": self.stage, "best": None if self.best is None else self.best.to_json(),
                "bound": None if self.bound is None or not math.isfinite(self.bound)
                else self.bound,
                "bound_infinite": self.bound is not None and not math.isfinite(self.bound),
                "r3": None if self._r3 is None else self._r3.to_json()}

    @classmethod
    def from_json(cls, problem: Problem, d: dict) -> Ladder:
        """Restore a ladder saved with :meth:`to_json` for the same problem."""
        lad = cls(problem)
        lad.stage = d["stage"]
        lad.best = None if d["best"] is None else Plan.from_json(d["best"])
        lad.bound = _INF if d.get("bound_infinite") else d["bound"]
        lad._r3 = None if d["r3"] is None else R3State.from_json(d["r3"])
        return lad
