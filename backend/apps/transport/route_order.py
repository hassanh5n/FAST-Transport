"""
Stop order without a router: the shortest straight-line path that ends at campus.

Used when a plan file gives neither a stop order nor pickup times, and to warn an
admin when a route's saved order makes the bus double back. Straight lines are
only a proxy for roads, so the warning has a generous margin.
"""

from .corridor import haversine_m

ORDER_WARN_RATIO = 1.25     # the saved order is this much longer than the suggested one...
ORDER_WARN_EXTRA_M = 1500   # ...and at least this many metres longer


def path_length_m(points, order, end):
    path = [points[i] for i in order] + [end]
    return sum(haversine_m(a, b) for a, b in zip(path, path[1:]))


def shortest_order(points, end):
    """Indices of `points` in the order a bus would pick them up on its way to `end`.

    Starts at the point farthest from `end`, chains nearest neighbours, then
    improves with 2-opt (reversing a run of stops when that shortens the path).
    """
    count = len(points)
    if count <= 1:
        return list(range(count))
    start = max(range(count), key=lambda i: haversine_m(points[i], end))
    order, left = [start], set(range(count)) - {start}
    while left:
        here = points[order[-1]]
        nearest = min(left, key=lambda i: haversine_m(here, points[i]))
        order.append(nearest)
        left.remove(nearest)

    best = path_length_m(points, order, end)
    improved = True
    while improved:
        improved = False
        for i in range(count - 1):
            for k in range(i + 1, count):
                candidate = order[:i] + order[i:k + 1][::-1] + order[k + 1:]
                length = path_length_m(points, candidate, end)
                if length < best - 1:
                    order, best, improved = candidate, length, True
    return order


def order_check(points, end):
    """None when the saved order is fine, else how much shorter a reordering is.

    `points` are the pickup stops in their saved order (campus excluded).
    """
    if len(points) < 3:
        return None
    current = path_length_m(points, list(range(len(points))), end)
    order = shortest_order(points, end)
    best = path_length_m(points, order, end)
    if current < best * ORDER_WARN_RATIO or current - best < ORDER_WARN_EXTRA_M:
        return None
    return {"extra_km": round((current - best) / 1000, 1), "suggested": order}
