"""Tests for the road-graph scripts: build_graph, build_corridors, calibrate_graph, measure_graph.

``build_graph`` is run for real through ``pyosmium`` on a tiny hand-written ``.osm`` XML file of the
toy map, so the build path is exercised without the Karachi map file. Tests that need ``osmium``
are skipped where it is not installed.
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import build_corridors
import build_graph
import calibrate_graph
import measure_graph
from reroute.closure import Closure
from reroute.graph import Graph, TravelTimes, clear_row_cache, load_corridor, load_reuse
from reroute.roadnet import TABLE_KEYS, build_tables
from reroute.tests.toymap import N, TOY

try:
    import osmium  # noqa: F401
    HAVE_OSMIUM = True
except ImportError:            # pragma: no cover - the research venv has it
    HAVE_OSMIUM = False

FAR = (24.950, 67.002)          # about 5 km north of the toy roads

OSM_XML = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="hand">
{nodes}
  <node id="20" lat="24.905" lon="67.000"/>
  <node id="21" lat="24.905" lon="67.001"/>
  <node id="30" lat="24.906" lon="67.000"/>
  <node id="31" lat="24.906" lon="67.001"/>
  <node id="40" lat="24.907" lon="67.000"/>
  <node id="41" lat="24.907" lon="67.001"/>
  <node id="50" lat="24.908" lon="67.000"/>
  <node id="51" lat="24.908" lon="67.001"/>
  <node id="52" lat="24.908" lon="67.002"/>
  <way id="100"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><tag k="highway" v="residential"/></way>
  <way id="101"><nd ref="3"/><nd ref="5"/><nd ref="6"/><tag k="highway" v="primary"/><tag k="oneway" v="yes"/></way>
  <way id="102"><nd ref="7"/><nd ref="8"/><tag k="highway" v="residential"/></way>
  <way id="103"><nd ref="20"/><nd ref="21"/><tag k="highway" v="footway"/></way>
  <way id="104"><nd ref="30"/><nd ref="31"/><tag k="highway" v="service"/><tag k="access" v="private"/></way>
  <way id="105"><nd ref="40"/><nd ref="41"/><tag k="highway" v="motorway"/></way>
  <way id="106"><nd ref="50"/><nd ref="51"/><nd ref="999"/><nd ref="52"/><tag k="highway" v="tertiary"/></way>
</osm>
"""


def write_osm(path: Path) -> None:
    nodes = "\n".join(f'  <node id="{i}" lat="{lat}" lon="{lng}"/>' for i, (lat, lng) in N.items())
    path.write_text(OSM_XML.format(nodes=nodes))


def toy_instance() -> dict:
    stops = [{"name": "S2", "lat": 24.9001, "lng": 67.001}, {"name": "S4", "lat": 24.900, "lng": 67.003},
             {"name": "Far", "lat": FAR[0], "lng": FAR[1]}]
    return {"campus": {"name": "Campus", "lat": 24.902, "lng": 67.002}, "stops": stops,
            "contractors": {"Jadoon": {"buses": [], "stops": ["S2", "S4"],
                                       "baseline_routes": [{"code": "R-1", "stops": ["S2", "S4"]}]}}}


def save_toy_graph(directory: Path, keep=(2,), version="toy_v1", speed_factor=1.0) -> None:
    build_graph.write_graph(build_tables(TOY, keep_ids=keep), directory,
                            {"version": version, "speed_factor": speed_factor})


def quiet(fn, *args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*args)


class BuildGraphRulesTests(unittest.TestCase):
    def test_way_rules(self):
        self.assertEqual(build_graph.way_rules({"highway": "primary"}), ("primary", ""))
        self.assertIsNone(build_graph.way_rules({"highway": "footway"}))
        self.assertIsNone(build_graph.way_rules({"highway": "service", "access": "private"}))
        self.assertIsNone(build_graph.way_rules({"highway": "residential", "access": "no"}))
        self.assertIsNone(build_graph.way_rules({"highway": "residential", "motor_vehicle": "no"}))
        self.assertIsNone(build_graph.way_rules({"highway": "service", "area": "yes"}))
        self.assertEqual(build_graph.way_rules({"highway": "motorway"}), ("motorway", "yes"))
        self.assertEqual(build_graph.way_rules({"highway": "motorway_link", "oneway": "no"}), ("motorway_link", "no"))
        self.assertEqual(build_graph.way_rules({"highway": "secondary", "junction": "roundabout"}), ("secondary", "yes"))
        self.assertEqual(build_graph.way_rules({"highway": "primary", "oneway": "-1"}), ("primary", "-1"))

    def test_split_valid(self):
        a, b, c, d = (1, 0.0, 0.0), (2, 0.0, 0.1), (3, 0.0, 0.2), (4, 0.0, 0.3)
        self.assertEqual(build_graph.split_valid([a, b, None, c, d]), [[a, b], [c, d]])
        self.assertEqual(build_graph.split_valid([a, None, c]), [])

    # Review focus 1: a point far from any road is reported with its distance.
    def test_nearest_way_nodes_reports_far_points(self):
        snaps = build_graph.nearest_way_nodes(TOY, [(24.9001, 67.001), FAR])
        self.assertEqual(snaps[0][0], 2)
        self.assertAlmostEqual(snaps[0][1], 11.1, delta=1.0)
        self.assertGreater(snaps[1][1], 4000)

    def test_write_graph_writes_one_npy_per_array(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            save_toy_graph(Path(tmp))
            for k in TABLE_KEYS:
                self.assertTrue((Path(tmp) / f"{k}.npy").exists())
            self.assertFalse(list(Path(tmp).glob("*.npz")))
            meta = json.loads((Path(tmp) / "meta.json").read_text())
            self.assertEqual((meta["nodes"], meta["edges"], meta["segments"]), (7, 9, 10))


@unittest.skipUnless(HAVE_OSMIUM, "pyosmium is not installed")
class BuildGraphOsmTests(unittest.TestCase):
    def test_read_ways_applies_the_filter(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            path = Path(tmp) / "toy.osm"
            write_osm(path)
            ways = build_graph.read_ways(path)
        classes = sorted((w.highway, w.oneway, tuple(n[0] for n in w.nodes)) for w in ways)
        self.assertEqual(classes, [("motorway", "yes", (40, 41)), ("primary", "yes", (3, 5, 6)),
                                   ("residential", "", (1, 2, 3, 4)), ("residential", "", (7, 8)),
                                   ("tertiary", "", (50, 51))])

    def test_main_builds_a_loadable_graph(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            write_osm(tmp / "toy.osm")
            (tmp / "instance.json").write_text(json.dumps(toy_instance()))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = build_graph.main([str(tmp / "toy.osm"), "--instance", str(tmp / "instance.json"),
                                       "--out", str(tmp / "graph"), "--version", "toy_v1"])
            self.assertEqual(rc, 0)
            self.assertIn("Far", out.getvalue())
            meta = json.loads((tmp / "graph" / "meta.json").read_text())
            self.assertEqual((meta["version"], meta["keep_points"], meta["speed_factor"]), ("toy_v1", 4, 1.0))
            self.assertEqual([name for name, _ in meta["far_snaps"]], ["Far"])
            self.assertEqual(len(meta["source_sha256"]), 64)
            g = Graph.load(tmp / "graph")
            self.assertIn(2, g.node_id.tolist())               # the stop at node 2 stays a graph node
            idx = {int(m): i for i, m in enumerate(g.node_id.tolist())}
            t = float(TravelTimes(g, None).rows([idx[1]])[idx[1]][idx[6]])
            self.assertAlmostEqual(t, 41.3, delta=0.4)
            self.assertEqual(meta["nodes"], g.n_nodes)
            del g

    def test_missing_map_file(self):
        self.assertEqual(quiet(build_graph.main, ["no/such/file.osm.pbf"]), 2)


class BuildCorridorsTests(unittest.TestCase):
    def setUp(self):
        clear_row_cache()

    def test_route_path_through_stops(self):
        g = Graph(build_tables(TOY))
        idx = {int(m): i for i, m in enumerate(g.node_id.tolist())}
        path, broken = build_corridors.route_path(g, [idx[1], idx[4], idx[6]])
        self.assertEqual([int(g.node_id[i]) for i in path], [1, 3, 4, 3, 6])
        self.assertEqual(broken, [])
        _, broken = build_corridors.route_path(g, [idx[6], idx[1]])
        self.assertEqual(broken, [0])

    def test_main_writes_corridors_index_and_reuse_tables(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            save_toy_graph(tmp / "graph")
            (tmp / "instance.json").write_text(json.dumps(toy_instance()))
            rc = quiet(build_corridors.main, ["--graph", str(tmp / "graph"), "--instance", str(tmp / "instance.json"),
                                              "--out", str(tmp / "corr"), "--buffer", "50"])
            self.assertEqual(rc, 0)
            index = json.loads((tmp / "corr" / "index.json").read_text())
            (route,) = index["routes"]
            self.assertEqual((route["key"], route["stops_outside"], route["unreachable_legs"]), ("Jadoon-R-1", [], []))
            g = Graph.load(tmp / "graph")
            c = load_corridor(tmp / "corr", "Jadoon-R-1")
            self.assertEqual(sorted(g.node_id[c.nodes].tolist()), [2, 3, 4, 6])
            self.assertEqual(route["nodes"], len(c.nodes))
            table = load_reuse(tmp / "corr", "Jadoon-R-1")
            self.assertEqual([int(g.node_id[n]) for n in table.point_nodes], [2, 4, 6])
            # A closure on 3-4 leaves node 2's row to campus reusable only if its paths avoid 3-4: they do not.
            tt = TravelTimes(g, c, [Closure("x", ((24.900, 67.0025, 20.0),), 0.0)], reuse=table)
            tt.rows(table.point_nodes.tolist(), targets=table.point_nodes.tolist())
            self.assertEqual((tt.reused, tt.searches), (1, 2))         # campus is unaffected
            self.assertIsNone(load_corridor(tmp / "corr", "Nadeem-R-9"))
            del g

    def test_no_reuse_flag_and_missing_graph(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            self.assertEqual(quiet(build_corridors.main, ["--graph", str(tmp / "none")]), 2)
            save_toy_graph(tmp / "graph")
            (tmp / "instance.json").write_text(json.dumps(toy_instance()))
            quiet(build_corridors.main, ["--graph", str(tmp / "graph"), "--instance", str(tmp / "instance.json"),
                                         "--out", str(tmp / "corr"), "--no-reuse"])
            self.assertIsNone(load_reuse(tmp / "corr", "Jadoon-R-1"))
            self.assertIsNotNone(load_corridor(tmp / "corr", "Jadoon-R-1"))


class CalibrateTests(unittest.TestCase):
    def setUp(self):
        clear_row_cache()

    def test_fit_factor_is_the_60th_percentile(self):
        osrm = np.array([[0, 10, 20], [30, 0, 40], [50, 60, 0]], dtype=float)
        graph_s = np.array([[0, 10, 10], [10, 0, 10], [10, 10, 0]], dtype=float)
        self.assertAlmostEqual(calibrate_graph.fit_factor(osrm, graph_s), float(np.percentile([1, 2, 3, 4, 5, 6], 60)))

    def test_errors_and_rule(self):
        osrm = np.array([[0, 100, 100], [100, 0, 100], [100, 100, 0]], dtype=float)
        graph_s = np.array([[0, 110, 105], [np.inf, 0, 120], [100, 108, 0]], dtype=float)
        err = calibrate_graph.errors(osrm, graph_s, 1.0)
        self.assertEqual(err["pairs"], 6)
        self.assertAlmostEqual(err["unreachable_share"], 1 / 6, places=3)
        self.assertAlmostEqual(err["median_signed_error_pct"], 8.0)
        self.assertTrue(calibrate_graph.passes(err))
        self.assertFalse(calibrate_graph.passes({"median_abs_error_pct": 16.0, "median_signed_error_pct": 1.0}))
        self.assertFalse(calibrate_graph.passes({"median_abs_error_pct": 5.0, "median_signed_error_pct": -0.1}))
        self.assertFalse(calibrate_graph.passes({"median_abs_error_pct": None, "median_signed_error_pct": None}))

    def test_errors_leave_out_pairs_with_zero_graph_time(self):
        osrm = np.array([[0, 100], [100, 0]], dtype=float)
        graph_s = np.array([[0, 0], [110, 0]], dtype=float)        # 0 -> 1 snap to one graph node
        err = calibrate_graph.errors(osrm, graph_s, 1.0)
        self.assertEqual((err["pairs"], err["unreachable_share"]), (2, 0.0))
        self.assertAlmostEqual(err["median_signed_error_pct"], 10.0)

    def _setup(self, tmp: Path, residential=1.25, primary=1.25):
        save_toy_graph(tmp / "graph")
        instance = toy_instance()
        (tmp / "instance.json").write_text(json.dumps(instance))
        g = Graph.load(tmp / "graph")
        names = ["CAMPUS", "S2", "S4"]
        nodes = [g.nearest_node(*p)[0] for p in calibrate_graph.matrix_points(instance, names)]
        tt = TravelTimes(g, None)
        group, speeds = calibrate_graph.speed_groups(g)
        per_edge = calibrate_graph.edge_group_seconds(g, group, len(speeds))
        factor = np.array([residential if kmh == 25 else primary for kmh in speeds])
        durations = []
        for s in nodes:
            row = []
            for edges in tt.path_edges(s, nodes):
                row.append(float(per_edge[edges].sum(axis=0) @ factor) if len(edges) else None)
            durations.append(row)
        for i in range(3):
            durations[i][i] = 0
        durations[0] = [0, 500, 500]                         # campus -> stops: the toy graph cannot (one-way)
        matrix = {"instance": "toy", "built_at": "now", "contractors": {"Jadoon": {"nodes": names,
                                                                                    "durations_s": durations}}}
        (tmp / "matrix.json").write_text(json.dumps(matrix))
        del g, tt
        clear_row_cache()
        return ["--graph", str(tmp / "graph"), "--instance", str(tmp / "instance.json"),
                "--matrix", str(tmp / "matrix.json")]

    def test_main_fits_one_factor_and_writes_meta(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            args = self._setup(tmp)
            self.assertEqual(quiet(calibrate_graph.main, args), 0)
            meta = json.loads((tmp / "graph" / "meta.json").read_text())
            self.assertAlmostEqual(meta["speed_factor"], 1.25, places=3)
            cal = meta["calibration"]
            self.assertTrue(cal["pass"])
            self.assertAlmostEqual(cal["median_abs_error_pct"], 0.0, places=1)
            self.assertAlmostEqual(cal["unreachable_share"], 2 / 6, places=3)
            g = Graph.load(tmp / "graph")
            self.assertAlmostEqual(g.speed_factor, 1.25, places=3)
            del g

    def test_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            args = self._setup(tmp)
            before = (tmp / "graph" / "meta.json").read_text()
            quiet(calibrate_graph.main, args + ["--dry-run"])
            self.assertEqual((tmp / "graph" / "meta.json").read_text(), before)

    def test_per_class_recovers_class_factors(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            args = self._setup(tmp, residential=1.5, primary=1.0)
            g = Graph.load(tmp / "graph", mmap=False)
            original = np.array(g.edge_s)
            instance = json.loads((tmp / "instance.json").read_text())
            matrix = json.loads((tmp / "matrix.json").read_text())
            _, _, node_sets, osrm_sets = calibrate_graph.calibrate(g, instance, matrix)
            factors, speeds = calibrate_graph.fit_class_factors(g, node_sets, osrm_sets)
            got = dict(zip(speeds, factors.round(3).tolist()))
            self.assertAlmostEqual(got[25], 1.5, places=2)
            self.assertAlmostEqual(got[65], 1.0, places=2)
            del g
            clear_row_cache()
            self.assertEqual(quiet(calibrate_graph.main, args + ["--per-class"]), 0)
            self.assertTrue((tmp / "graph" / "edge_s_profile.npy").exists())
            np.testing.assert_allclose(np.load(tmp / "graph" / "edge_s_profile.npy"), original)
            meta = json.loads((tmp / "graph" / "meta.json").read_text())
            self.assertAlmostEqual(meta["speed_factor"], 1.0, places=2)
            self.assertAlmostEqual(meta["calibration"]["median_abs_error_pct"], 0.0, places=1)
            self.assertIn("25 km/h", meta["calibration"]["per_class"])


class MeasureGraphTests(unittest.TestCase):
    def setUp(self):
        clear_row_cache()

    def test_peak_memory_is_readable_on_this_platform(self):
        self.assertGreater(measure_graph.peak_rss_mb(), 1.0)
        self.assertGreater(measure_graph.rss_mb(), 1.0)

    def test_module_does_not_import_resource_at_top_level(self):
        source = Path(measure_graph.__file__).read_text()
        top = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
        self.assertFalse([line for line in top if "resource" in line])

    def test_longest_route_and_sources(self):
        inst = toy_instance()
        inst["contractors"]["Nadeem"] = {"baseline_routes": [{"code": "R-2", "stops": ["S2", "S4", "Far"]}]}
        self.assertEqual(measure_graph.longest_route(inst), ("Nadeem-R-2", ["S2", "S4", "Far"]))
        g = Graph(build_tables(TOY))
        src = measure_graph.pick_sources(g, None, [3, 3, 1], [5, 1], 5)
        self.assertEqual(src[:3], [3, 1, 5])
        self.assertEqual(len(set(src)), 5)

    def test_gate_g1(self):
        self.assertEqual(measure_graph.gate_g1(None)["verdict"], "not run")
        timing = {"timings": {"corridor": {"14": {"wall_worst_s": 4.0}, "31": {"wall_worst_s": 29.0}}}}
        self.assertEqual(measure_graph.gate_g1(timing)["verdict"], "pass")
        timing["timings"]["corridor"]["14"]["wall_worst_s"] = 5.5
        self.assertEqual(measure_graph.gate_g1(timing)["verdict"], "fail")

    def test_limited_is_refused_off_linux(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            save_toy_graph(tmp / "graph")
            (tmp / "instance.json").write_text(json.dumps(toy_instance()))
            with mock.patch.object(sys, "platform", "win32"):
                rc = quiet(measure_graph.main, ["--limited", "--graph", str(tmp / "graph"),
                                                "--instance", str(tmp / "instance.json"), "--out", str(tmp / "out")])
            self.assertEqual(rc, 2)
            self.assertFalse((tmp / "out" / "timing.json").exists())

    def test_no_limits_run_records_limits_none(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            save_toy_graph(tmp / "graph")
            (tmp / "instance.json").write_text(json.dumps(toy_instance()))
            quiet(build_corridors.main, ["--graph", str(tmp / "graph"), "--instance", str(tmp / "instance.json"),
                                         "--out", str(tmp / "corr"), "--buffer", "50"])
            rc = quiet(measure_graph.main, ["--no-limits", "--repeats", "2", "--graph", str(tmp / "graph"),
                                            "--corridors", str(tmp / "corr"), "--instance", str(tmp / "instance.json"),
                                            "--out", str(tmp / "out")])
            self.assertEqual(rc, 0)
            data = json.loads((tmp / "out" / "timing.json").read_text())
            run = data["runs"]["unlimited"]
            self.assertEqual(run["limits"], "none")
            self.assertEqual(data["gate_g1"]["verdict"], "not run")
            self.assertEqual(run["route"], "Jadoon-R-1")
            self.assertEqual(set(run["timings"]), {"corridor", "city"})
            self.assertEqual(len(run["timings"]["city"]["1"]["wall_s"]), 2)
            self.assertGreater(run["rss_mb"]["peak"], 0)


if __name__ == "__main__":
    unittest.main()
