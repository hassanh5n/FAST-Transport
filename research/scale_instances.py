"""Optimizer instances of growing size for the scaling run (run_scale.py). Pure functions, no OR-Tools.

An instance is a dict {"name", "T", "q", "capacities", "nodes"} in optimize.py: solve's terms: node 0 is
campus, T[a][b] is seconds from node a to node b, q[i] the students at stop i, one capacity per bus,
nodes[i] the stop's name. A contractor instance also carries "baseline_routes" (the current routes as
node indices) so its plans can be compared with today's routes.

    contractor_instance   one contractor's stops and buses, as optimize.py: main builds them
    combined_instance     all 311 stops and both fleets in one problem (needs the combined matrix)
    doubled_instance      every stop and every bus twice; a copy sits gap_s seconds from its original

The doubled instance tests model size, not geography: copies add no new travel times.
"""

CAMPUS = "CAMPUS"


def contractor_instance(inst: dict, mat: dict, contractor: str) -> dict:
    """One contractor's problem from the frozen instance and matrix files (data/*_fall2026_v1.json)."""
    by_name = {s["name"]: s for s in inst["stops"]}
    m = mat["contractors"][contractor]
    nodes, T = m["nodes"], m["durations_s"]
    c = inst["contractors"][contractor]
    pos = {n: i for i, n in enumerate(nodes)}
    return {"name": contractor, "T": T,
            "q": [0] + [by_name[n]["students"].get(contractor, 0) for n in nodes[1:]],
            "capacities": [b["capacity"] for b in c["buses"]],
            "nodes": nodes,
            "baseline_routes": [[pos[s] for s in r["stops"]] for r in c["baseline_routes"]]}


def combined_instance(inst: dict, mat_all: dict) -> dict:
    """Every stop in one problem. q sums each stop's students over contractors; capacities are all
    contractors' buses. mat_all is matrix_fall2026_v1_all.json, with one entry "All" (node 0 campus).

    Raises KeyError if the matrix names a stop the instance lacks, or misses a stop that has students."""
    m = mat_all["contractors"]["All"]
    nodes, T = m["nodes"], m["durations_s"]
    by_name = {s["name"]: s for s in inst["stops"]}
    missing = [s["name"] for s in inst["stops"] if sum(s["students"].values()) and s["name"] not in nodes]
    if missing:
        raise KeyError(f"combined matrix lacks {len(missing)} stops with students, e.g. {missing[:3]}")
    return {"name": "All", "T": T,
            "q": [0] + [sum(by_name[n]["students"].values()) for n in nodes[1:]],
            "capacities": [b["capacity"] for c in inst["contractors"].values() for b in c["buses"]],
            "nodes": nodes}


def doubled_instance(base: dict, gap_s: float = 30.0) -> dict:
    """Every stop of base twice, every bus twice; node 0 stays campus.

    Stop i (1..n-1) gets a copy at i + n - 1. The copy is gap_s seconds from its original in both
    directions, has the original's times to and from every other node, and carries the same students.
    base is not changed."""
    T, n = base["T"], len(base["T"])

    def original(k):
        return k if k < n else k - (n - 1)

    size = 2 * n - 1
    T2 = [[0 if a == b else gap_s if original(a) == original(b) else T[original(a)][original(b)]
           for b in range(size)] for a in range(size)]
    out = {"name": f"{base['name']}-doubled", "T": T2,
           "q": list(base["q"]) + list(base["q"][1:]),
           "capacities": list(base["capacities"]) * 2}
    if "nodes" in base:
        out["nodes"] = list(base["nodes"]) + [f"{name} (copy)" for name in base["nodes"][1:]]
    return out
