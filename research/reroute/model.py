"""The rerouting problem for one bus, its plans, and the one function that scores a plan.

Every method in ``ladder.py`` builds a visit order and boarding choices and calls :func:`evaluate`;
the timing rules live here and nowhere else.

Node indexing: a problem with P points has P + 2 nodes. Indices ``0..P-1`` are the points in the
order given, ``P`` is the bus position (:attr:`Problem.start`) and ``P + 1`` is campus
(:attr:`Problem.campus`). A travel-time row is a sequence of P + 2 floats in seconds; ``math.inf``
means unreachable. All times are seconds after the decision time.

Pure Python: no file or network access, no Django.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Sequence

MAX_WALK_LIMIT_M = 800.0

RowsFn = Callable[[list[int]], Mapping[int, Sequence[float]]]


@dataclass(frozen=True)
class StopNeed:
    """A remaining stop: its id (also its point id), students waiting and walking rules."""

    id: int
    students: int
    walk_limit_m: float = 400.0
    must_serve: bool = False


@dataclass(frozen=True)
class Params:
    """Timing constants: stop time per visited point and per boarding student, and walkers."""

    stop_base_s: float = 60.0
    stop_per_student_s: float = 5.0
    walk_speed_mps: float = 1.2
    walk_lag_s: float = 60.0


class InvalidPlan(ValueError):
    """A plan breaks a rule of the problem (a repeated point, a stop with no valid boarding...)."""


class Problem:
    """One bus's rerouting problem.

    ``rows`` answers a batch of source node indices with their travel-time rows; it is called
    only for rows not fetched before, so the number of distinct rows fetched
    (:attr:`rows_requested`) measures how much routing work a method needed.
    ``walk`` maps ``(stop_id, point_id)`` to walking metres; missing pairs cannot be walked.
    """

    def __init__(self, stops: Sequence[StopNeed], points: Sequence[int], rows: RowsFn,
                 walk: Mapping[tuple[int, int], float], committed: Iterable[int] = (),
                 params: Params = Params()) -> None:
        self.stops: tuple[StopNeed, ...] = tuple(stops)
        self.points: tuple[int, ...] = tuple(points)
        self.committed: frozenset[int] = frozenset(committed)
        self.params = params
        self._rows = rows
        self._walk = walk

        self.index: dict[int, int] = {}
        for i, pid in enumerate(self.points):
            if pid in self.index:
                raise ValueError(f"duplicate point id {pid}")
            self.index[pid] = i
        seen: set[int] = set()
        for stop in self.stops:
            if stop.id in seen:
                raise ValueError(f"duplicate stop id {stop.id}")
            seen.add(stop.id)
            if stop.id not in self.index:
                raise ValueError(f"stop {stop.id} is not in the points list")
            if stop.students < 0:
                raise ValueError(f"stop {stop.id}: students must not be negative")
            if not 0.0 <= stop.walk_limit_m <= MAX_WALK_LIMIT_M:
                raise ValueError(f"stop {stop.id}: walk_limit_m must be between 0 and "
                                 f"{MAX_WALK_LIMIT_M:g}")
        for pid in sorted(self.committed):
            if pid not in self.index:
                raise ValueError(f"committed point {pid} is not in the points list")
        for pair, metres in walk.items():
            if not float(metres) >= 0.0:                     # also catches NaN
                raise ValueError(f"walk {pair}: metres must be a non-negative number")

        self.start: int = len(self.points)
        self.campus: int = len(self.points) + 1
        self._cache: dict[int, tuple[float, ...]] = {}

    @property
    def rows_requested(self) -> int:
        """Distinct travel-time rows fetched so far."""
        return len(self._cache)

    def fetch(self, nodes: list[int]) -> None:
        """Fetch every uncached row among ``nodes`` with a single call to ``rows``."""
        missing = list(dict.fromkeys(n for n in nodes if n not in self._cache))
        if not missing:
            return
        answer = self._rows(missing)
        width = len(self.points) + 2
        for n in missing:
            if n not in answer:
                raise ValueError(f"the rows function returned no row for node {n}")
            row = tuple(float(t) for t in answer[n])
            if len(row) != width:
                raise ValueError(f"row for node {n} has {len(row)} entries, expected {width}")
            bad = next((t for t in row if math.isnan(t) or t < 0.0), None)
            if bad is not None:
                raise ValueError(f"row for node {n} has an invalid travel time {bad!r}; "
                                 "times must be non-negative seconds or inf")
            self._cache[n] = row

    def row(self, node: int) -> tuple[float, ...]:
        """Travel times in seconds from ``node`` to every node, fetched once and cached."""
        if node not in self._cache:
            self.fetch([node])
        return self._cache[node]

    def walk_m(self, stop_id: int, point_id: int) -> float | None:
        """Metres a student walks from a stop to a point, or ``None`` when no walk is known."""
        if stop_id == point_id:
            return 0.0
        metres = self._walk.get((stop_id, point_id))
        return None if metres is None else float(metres)

    def can_board(self, stop: StopNeed, point_id: int) -> bool:
        """Whether the stop's students may board at the point (ignores reachability)."""
        if stop.id == point_id:
            return True
        if stop.must_serve:
            return False
        metres = self.walk_m(stop.id, point_id)
        return metres is not None and metres <= stop.walk_limit_m

    def ready_s(self, stop_id: int, point_id: int) -> float:
        """When the stop's walkers are at the point; 0 for students boarding at their own stop."""
        if stop_id == point_id:
            return 0.0
        metres = self.walk_m(stop_id, point_id)
        if metres is None:
            raise InvalidPlan(f"stop {stop_id} has no walk to point {point_id}")
        return self.params.walk_lag_s + metres / self.params.walk_speed_mps


def table_rows(matrix: Sequence[Sequence[float]]) -> RowsFn:
    """Wrap a full (P + 2) x (P + 2) travel-time table as a ``rows`` function."""
    def rows(nodes: list[int]) -> dict[int, Sequence[float]]:
        return {n: matrix[n] for n in nodes}
    return rows


def _finite_or_none(x: float) -> float | None:
    return x if math.isfinite(x) else None


@dataclass(frozen=True)
class Plan:
    """A scored plan. ``stop_walk_m`` holds the metres one student of each walking stop walks."""

    method: str
    visit: tuple[int, ...]
    board_at: dict[int, int]
    unserved: tuple[int, ...]
    arrival_s: float
    walk_m: float
    stop_walk_m: dict[int, float] = field(default_factory=dict)

    @property
    def key(self) -> tuple[float, float]:
        """The objective: earliest arrival, then least total walking (students x metres)."""
        return (self.arrival_s, self.walk_m)

    def to_json(self) -> dict:
        """JSON types only; an infinite arrival is stored as ``None``."""
        return {"method": self.method, "visit": list(self.visit),
                "board_at": [[s, p] for s, p in self.board_at.items()],
                "unserved": list(self.unserved), "arrival_s": _finite_or_none(self.arrival_s),
                "walk_m": self.walk_m,
                "stop_walk_m": [[s, m] for s, m in self.stop_walk_m.items()]}

    @classmethod
    def from_json(cls, d: dict) -> Plan:
        """Inverse of :meth:`to_json`."""
        arrival = d["arrival_s"]
        return cls(d["method"], tuple(d["visit"]), {int(s): int(p) for s, p in d["board_at"]},
                   tuple(d["unserved"]), math.inf if arrival is None else float(arrival),
                   float(d["walk_m"]), {int(s): float(m) for s, m in d.get("stop_walk_m", [])})


def _check(problem: Problem, visit: Sequence[int], board_at: Mapping[int, int],
           unserved: Sequence[int]) -> None:
    """Raise :class:`InvalidPlan` naming the first rule the plan breaks."""
    visited: set[int] = set()
    for pid in visit:
        if pid not in problem.index:
            raise InvalidPlan(f"point {pid} is not a candidate point")
        if pid in visited:
            raise InvalidPlan(f"point {pid} is visited twice")
        visited.add(pid)
    stop_ids = {s.id for s in problem.stops}
    for sid in list(board_at) + list(unserved):
        if sid not in stop_ids:
            raise InvalidPlan(f"stop {sid} is not a remaining stop")
    unserved_set = set(unserved)
    for stop in problem.stops:
        if stop.id in unserved_set:
            if stop.id in board_at:
                raise InvalidPlan(f"stop {stop.id} is both boarded and unserved")
            continue
        pid = board_at.get(stop.id)
        if pid is None:
            raise InvalidPlan(f"stop {stop.id} has no boarding point and is not unserved")
        if pid not in visited:
            raise InvalidPlan(f"stop {stop.id} boards at point {pid}, which is not visited")
        if not problem.can_board(stop, pid):
            raise InvalidPlan(f"stop {stop.id} cannot board at point {pid}")
    for pid in sorted(problem.committed):
        if pid not in visited:
            raise InvalidPlan(f"committed point {pid} is not visited")


def evaluate(problem: Problem, visit: Sequence[int], board_at: Mapping[int, int],
             unserved: Sequence[int] = ()) -> tuple[float, float]:
    """Score a plan: ``(arrival at campus in seconds, total walking in student-metres)``.

    The bus leaves a point at ``max(arrival, walkers ready) + stop_base_s + stop_per_student_s x
    students boarding``. An unreachable leg gives an infinite arrival; a broken rule raises
    :class:`InvalidPlan`.
    """
    _check(problem, visit, board_at, unserved)
    params = problem.params
    by_id = {s.id: s for s in problem.stops}
    students: dict[int, int] = {}
    ready: dict[int, float] = {}
    walk_total = 0.0
    for sid, pid in board_at.items():
        stop = by_id[sid]
        students[pid] = students.get(pid, 0) + stop.students
        ready[pid] = max(ready.get(pid, 0.0), problem.ready_s(sid, pid))
        walk_total += stop.students * problem.walk_m(sid, pid)

    t, prev = 0.0, problem.start
    for pid in visit:
        node = problem.index[pid]
        t += problem.row(prev)[node]
        if t == math.inf:
            return math.inf, walk_total
        t = (max(t, ready.get(pid, 0.0)) + params.stop_base_s
             + params.stop_per_student_s * students.get(pid, 0))
        prev = node
    return t + problem.row(prev)[problem.campus], walk_total


def make_plan(problem: Problem, method: str, visit: Sequence[int], board_at: Mapping[int, int],
              unserved: Sequence[int] = ()) -> Plan:
    """Score a plan with :func:`evaluate` and wrap it in a :class:`Plan`."""
    arrival, walk = evaluate(problem, visit, board_at, unserved)
    stop_walk = {sid: problem.walk_m(sid, pid) for sid, pid in board_at.items() if sid != pid}
    return Plan(method, tuple(visit), dict(board_at), tuple(unserved), arrival, walk, stop_walk)
