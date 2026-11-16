"""Rerouting solver core: one bus, a ladder of methods (R0 patched route, R2 greedy, R3 exact).

Pure Python plus ``numpy`` (imported by R3 only, when it runs). No Django, no file or network
access. The road graph modules (``reroute.graph``, ``reroute.closure``, ``reroute.roadnet``) are
imported directly by their users and are deliberately not imported here.
"""
from reroute.ladder import Ladder, lower_bound, solve_r0, solve_r2, solve_r3
from reroute.model import InvalidPlan, Params, Plan, Problem, StopNeed, evaluate, table_rows
from reroute.wire import RequestError, failed_proposal, parse_request, to_proposal

__all__ = [
    "StopNeed", "Params", "Problem", "Plan", "InvalidPlan", "table_rows", "evaluate",
    "Ladder", "solve_r0", "solve_r2", "solve_r3", "lower_bound",
    "parse_request", "to_proposal", "failed_proposal", "RequestError",
]
