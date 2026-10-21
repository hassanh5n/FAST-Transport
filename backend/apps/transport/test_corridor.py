"""Main-road corridor: chunked routing, boarding points, loop cuts, stop order."""

import json
import math
import os
import tempfile
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from .corridor import build_corridor, cut_loops, haversine_m, line_length_m, route_through
from .models import Route, RouteStop, Stop
from .route_order import order_check, shortest_order
from .views.driver import _line_etas
from .views.maps import _road_geometry

LAT0, LNG0 = 24.90, 67.10                  # the "main road" runs east along this latitude
M_LAT = 1 / 111195                          # degrees of latitude per metre
M_LNG = M_LAT / math.cos(math.radians(LAT0))


def at(east_m, north_m=0):
    """[lng, lat] east_m along the main road and north_m up a side street."""
    return [round(LNG0 + east_m * M_LNG, 6), round(LAT0 + north_m * M_LAT, 6)]


def _encode(coordinates):
    """Polyline6, as Valhalla sends a leg's shape."""
    out, previous = [], [0, 0]
    for lng, lat in coordinates:
        for axis, value in enumerate((round(lat * 1e6), round(lng * 1e6))):
            delta = value - previous[axis]
            previous[axis] = value
            delta = ~(delta << 1) if delta < 0 else delta << 1
            while delta >= 0x20:
                out.append(chr((0x20 | (delta & 0x1F)) + 63))
                delta >>= 5
            out.append(chr(delta + 63))
    return "".join(out)


def _grid_router(calls):
    """A fake Valhalla on a grid: the main road is the east-west axis and every
    point is reached by a straight side street from the axis. A leg A -> B drives
    down A's street, along the main road, then up B's street."""
    def post(url, json=None, timeout=None):
        calls.append(json)
        points = [(loc["lon"], loc["lat"]) for loc in json["locations"]]
        legs = []
        for a, b in zip(points, points[1:]):
            path = [list(a), [a[0], LAT0], [b[0], LAT0], list(b)]
            path = [p for i, p in enumerate(path) if i == 0 or p != path[i - 1]]
            length = sum(haversine_m(p, q) for p, q in zip(path, path[1:]))
            legs.append({"shape": _encode(path), "summary": {"time": length / 10, "length": length / 1000}})
        return Mock(status_code=200, json=Mock(return_value={"trip": {"legs": legs}}), raise_for_status=Mock())
    return post


@override_settings(MAP_STOP_WALK_M=500, MAP_ROUTING_MAX_LOCATIONS=10, MAP_MAIN_ROAD_CLASS="secondary")
@patch("apps.transport.corridor.time.sleep")
class CorridorTests(SimpleTestCase):
    def test_more_than_ten_points_are_routed_in_chunks_that_share_an_end(self, _sleep):
        calls = []
        points = [at(1000 * i) for i in range(13)]
        with patch("apps.transport.corridor.requests.post", side_effect=_grid_router(calls)):
            line, seconds, legs = route_through(points)
        self.assertEqual([len(call["locations"]) for call in calls], [10, 4])
        last_of_first = calls[0]["locations"][-1]
        first_of_second = calls[1]["locations"][0]
        self.assertEqual((last_of_first["lon"], last_of_first["lat"]), (first_of_second["lon"], first_of_second["lat"]))
        self.assertEqual(len(legs), 12)
        self.assertEqual(len(line), len(seconds))
        self.assertAlmostEqual(line_length_m(line), 12000, delta=20)

    def test_stops_near_the_main_road_board_there_without_a_detour(self, _sleep):
        calls = []
        stops = [at(0), at(2000, 200), at(4000, -350), at(6000, 150), at(8000)]
        with patch("apps.transport.corridor.requests.post", side_effect=_grid_router(calls)):
            corridor = build_corridor(stops)
        self.assertEqual(len(calls), 1)                 # routed once, first stop to campus
        self.assertEqual(len(calls[0]["locations"]), 2)
        self.assertEqual(corridor["anchors"], [0, 4])
        walks = [stop["walk_m"] for stop in corridor["stops"]]
        self.assertEqual([round(w, -1) for w in walks], [0, 200, 350, 150, 0])
        self.assertAlmostEqual(corridor["stops"][1]["at"][1], LAT0, places=5)  # boards on the main road
        self.assertAlmostEqual(line_length_m(corridor["line"]), 8000, delta=20)
        times = [stop["s"] for stop in corridor["stops"]]
        self.assertEqual(times, sorted(times))
        self.assertEqual(times[0], 0)

    def test_a_stop_beyond_walking_distance_is_driven_to(self, _sleep):
        calls = []
        stops = [at(0), at(3000, 1200), at(6000)]
        with patch("apps.transport.corridor.requests.post", side_effect=_grid_router(calls)):
            corridor = build_corridor(stops)
        self.assertEqual(corridor["anchors"], [0, 1, 2])
        self.assertLess(corridor["stops"][1]["walk_m"], 5)
        # The out-and-back up the side street serves that stop, so it is not cut.
        self.assertAlmostEqual(line_length_m(corridor["line"]), 6000 + 2 * 1200, delta=30)

    def test_u_turn_loops_are_cut_but_not_ones_that_serve_a_stop(self, _sleep):
        # Along the road, 400 m up a side street and back (a detour), then on.
        line = [at(0), at(1000), at(1000, 400), at(1000), at(2000)]
        seconds = [0, 100, 40, 40, 100]
        stops = [at(0), at(1500, 100), at(2000)]
        cut, cut_seconds, removed = cut_loops(line, seconds, stops, 500)
        self.assertEqual(cut, [at(0), at(1000), at(2000)])
        self.assertEqual(len(cut_seconds), len(cut))
        self.assertAlmostEqual(removed, 800, delta=5)

        stops = [at(0), at(1000, 400), at(2000)]        # now the street has a stop at its end
        kept, _, removed = cut_loops(line, seconds, stops, 300)
        self.assertEqual(kept, line)
        self.assertEqual(removed, 0)

    def test_router_failure_steps_down_road_classes_then_gives_up(self, _sleep):
        import requests
        failing = Mock(side_effect=requests.RequestException("down"))
        with patch("apps.transport.corridor.requests.post", failing):
            self.assertIsNone(build_corridor([at(0), at(1000)]))
        classes = [call.kwargs["json"]["locations"][0]["search_filter"]["min_road_class"] for call in failing.call_args_list]
        self.assertEqual(classes, ["secondary", "tertiary", "unclassified", "residential"])


@override_settings(MAP_STOP_WALK_M=500, MAP_ROUTING_MAX_LOCATIONS=10, MAP_MAIN_ROAD_CLASS="secondary")
@patch("apps.transport.corridor.time.sleep")
class SavedLineTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_saved_geometry_carries_boarding_points_and_drives_live_etas(self, _sleep):
        stops = [at(0), at(2000, 300), at(4000)]
        with patch("apps.transport.corridor.requests.post", side_effect=_grid_router([])):
            geometry, source = _road_geometry([tuple(point) for point in stops])
        self.assertEqual(source, "provider")
        self.assertEqual(geometry["v"], 2)
        self.assertEqual([stop["pin"] for stop in geometry["stops"]], [[round(p[0], 5), round(p[1], 5)] for p in stops])
        self.assertEqual(len(geometry["leg_seconds"]), 2)

        route_stops = [
            SimpleNamespace(id=10 + i, stop=SimpleNamespace(longitude=p[0], latitude=p[1]))
            for i, p in enumerate(stops)
        ]
        bus = at(1000, 20)                              # on the main road, 1 km in
        with patch("apps.transport.corridor.requests.post") as router:
            etas = _line_etas(bus, route_stops[1:], geometry)
        router.assert_not_called()
        self.assertEqual([eta["route_stop_id"] for eta in etas], [11, 12])
        self.assertAlmostEqual(etas[0]["distance_m"], 1000, delta=20)
        self.assertAlmostEqual(etas[0]["eta_seconds"], 100, delta=3)       # 10 m/s in the fake
        self.assertAlmostEqual(etas[1]["eta_seconds"], 300 + 60, delta=3)  # + one stop's boarding time
        self.assertIsNone(_line_etas(at(1000, 2000), route_stops[1:], geometry))  # bus far off its line


class StopOrderTests(SimpleTestCase):
    def test_shortest_order_does_not_zig_zag(self):
        from .route_order import path_length_m
        campus = at(10000)
        # Two neighbourhoods north and south of the road, the same distance from
        # campus. Sorting by that distance alternates north, south, north, south.
        points = [at(0, 2000), at(0, -2000), at(100, 2100), at(100, -2100)]
        def crossings(order):
            sides = [points[i][1] > LAT0 for i in order]
            return sum(a != b for a, b in zip(sides, sides[1:]))

        radial = sorted(range(4), key=lambda i: -haversine_m(points[i], campus))
        self.assertEqual(crossings(radial), 3)          # back and forth across the road
        order = shortest_order(points, campus)
        self.assertEqual(crossings(order), 1)           # one side, then the other
        self.assertLess(path_length_m(points, order, campus), path_length_m(points, radial, campus) - 7000)

    def test_order_check_flags_a_back_and_forth_order(self):
        campus = at(20000)
        good = [at(0), at(3000), at(6000), at(9000)]
        self.assertIsNone(order_check(good, campus))
        bad = [at(0), at(9000), at(3000), at(6000)]
        found = order_check(bad, campus)
        self.assertEqual(found["suggested"], [0, 2, 3, 1])
        self.assertGreater(found["extra_km"], 5)


class RestoreStopOrderCommandTests(TestCase):
    def test_restores_the_timetable_order_and_drops_the_saved_line(self):
        route = Route.objects.create(name="Jadoon R-4", geometry={"type": "LineString", "coordinates": [[0, 0], [1, 1]]})
        names = ["Paradise Bakery", "Maymar Gate", "Al Asif"]
        for order, name in enumerate(names, start=1):
            stop = Stop.objects.create(name=name, latitude="24.9", longitude=f"67.{order}")
            RouteStop.objects.create(route=route, stop=stop, stop_order=order)
        campus = Stop.objects.create(name="FAST NUCES Main Campus", latitude="24.85", longitude="67.26", is_campus=True)
        RouteStop.objects.create(route=route, stop=campus, stop_order=4)
        source = {"routes": [{"operator": "Jadoon", "code": "R-4", "stops": [
            {"order": 1, "name": "Maymar Gate"}, {"order": 2, "name": "Al-Asif"}, {"order": 3, "name": "Paradise Bakery"},
        ]}]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(source, handle)
        self.addCleanup(os.remove, handle.name)

        def current():
            return list(RouteStop.objects.filter(route=route).order_by("stop_order").values_list("stop__name", flat=True))

        call_command("restore_stop_order", handle.name, stdout=StringIO())   # dry run
        self.assertEqual(current(), names + ["FAST NUCES Main Campus"])
        with self.captureOnCommitCallbacks(execute=False):
            call_command("restore_stop_order", handle.name, "--apply", stdout=StringIO())
        self.assertEqual(current(), ["Maymar Gate", "Al Asif", "Paradise Bakery", "FAST NUCES Main Campus"])
        route.refresh_from_db()
        self.assertIsNone(route.geometry)


class PlanImportOrderTests(SimpleTestCase):
    def test_json_order_key_sets_the_stop_order(self):
        from .route_plans import parse_plan_file
        plan = {"routes": [{"name": "R-1", "stops": [
            # "First" is the closest to campus: only the file's order puts it first
            {"order": 2, "name": "Second", "lat": 24.99, "lng": 67.05},
            {"order": 1, "name": "First", "lat": 24.93, "lng": 67.15},
            {"order": 3, "name": "Third", "lat": 24.95, "lng": 67.10},
        ]}]}
        snapshot, _ = parse_plan_file("plan.json", json.dumps(plan).encode())
        names = [stop["name"] for stop in snapshot["routes"][0]["stops"]]
        self.assertEqual(names[:3], ["First", "Second", "Third"])
