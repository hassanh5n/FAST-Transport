"""Reviewer tests for the offline builders: each test demonstrates one defect found in review.

Run from `research/`: `python -m unittest tests.test_review_offline -v`.
"""
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import build_matrix
import build_scenarios as bs
import osrm_tools
import run_roadblock as rb
from reroute.graph import Graph
from tests.fake_osrm import FakeOsrm, make_osrm_folder
from tests.toy_city import INSTANCE, STUDENT_ROWS, TABLES, WALK, node_at


class FreshCopyAncestorTests(unittest.TestCase):
    def test_work_folder_that_contains_the_source_does_not_destroy_it(self):
        # `--work-dir ~/fleetcentric-osrm` (one level too high) must not wipe the untouched build.
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "fleetcentric-osrm"
            car = make_osrm_folder(home / "car")
            try:
                osrm_tools.fresh_copy(car, home)
            except (ValueError, FileNotFoundError):
                pass
            self.assertTrue((car / osrm_tools.OSRM_BASENAME).exists(),
                            "fresh_copy deleted the untouched OSRM build")


class LeakCheckTests(unittest.TestCase):
    def test_closure_containing_stops_still_checks_the_open_stops(self):
        # Nadeem R-2 is D, E, F after dropping X; leg 2's circle contains E and F. The module
        # docstring says "each pair of consecutive open points in route order (campus last) is
        # routed", so D -> campus must be routed on the closed server. Today no leg is checked
        # and `leaks` is 0 by construction, whatever OSRM does.
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fake = FakeOsrm(TABLES)
            b = bs.ScenarioBuilder(fake, Graph(TABLES), INSTANCE, STUDENT_ROWS, WALK,
                                   make_osrm_folder(tmp / "car"), tmp / "work", log=lambda s: None)
            routes = bs.route_stops(INSTANCE, STUDENT_ROWS, only=("Nadeem", "R-2"))
            out = b.build(routes, [])
            entry = {c["id"]: c for c in out["closures"]}["Nadeem-R-2-L2"]
            self.assertTrue(entry["closed_points"])
            starts = [i for i, c in enumerate(fake.calls) if c[0] == "start" and c[2] == bs.CLOSED_PORT]
            after_l2 = fake.calls[starts[-1]:]
            checked = [c for c in after_l2 if c[0] == "route" and c[1] == f"http://localhost:{bs.CLOSED_PORT}"]
            self.assertTrue(checked, "the leak check of Nadeem-R-2-L2 routed nothing on the closed server")


class _IgnoresEverySpeed(FakeOsrm):
    """An OSRM on which neither 0 nor 1 km/h has any effect."""

    def customize(self, work_dir, csv_text):
        self.customizations.append(csv_text)
        return self.customize_s


class RoadblockLabelTests(unittest.TestCase):
    def test_snap_evidence_names_the_speed_actually_on_the_test_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            fake = _IgnoresEverySpeed(TABLES)
            result = rb.run_test(fake, Graph(TABLES), (node_at(0, 0), node_at(0, 4)),
                                 make_osrm_folder(tmp / "car"), tmp / "work", repeats=1)
            self.assertEqual([c["answer"] for c in result["checks"][:2]], ["ignored", "ignored"])
            snap = result["checks"][2]
            # The last closure customized before the snapping check was written at 1 km/h.
            self.assertTrue(fake.customizations[1].strip().endswith(",1"))
            self.assertEqual(snap["evidence"]["closed_kmh"], 1,
                             "snapping was measured on the 1 km/h server but is labelled 0 km/h")


class _HtmlErrorServer:
    """Answers every GET with HTTP 502 and an HTML body, like a proxy in front of a dead OSRM."""

    def __init__(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                data = b"<html><body>502 Bad Gateway</body></html>"
                self.send_response(502)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


class BuildMatrixErrorTests(unittest.TestCase):
    def test_non_json_error_page_exits_with_a_clear_message(self):
        with _HtmlErrorServer() as srv:
            with self.assertRaises(SystemExit):
                build_matrix.table([(24.9, 67.1), (24.8, 67.2)], srv.base)


if __name__ == "__main__":
    unittest.main()
