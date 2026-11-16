"""Tests for `osrm_tools`: the pure helpers, HTTP against a fake server, Docker calls mocked.

No test needs Docker, an OSRM server or the map file.
"""
import io
import json
import math
import subprocess
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import osrm_tools
from osrm_tools import (IMAGE, OsrmError, clean_table, customize, fetch_json, fresh_copy, route,
                        speed_csv, start_server, stop_server, table, table_url, to_json_table,
                        wait_ready)


class OsrmToolsTests(unittest.TestCase):
    """The tests written out in the plan, Task 1 Step 1."""

    def test_speed_csv(self):
        self.assertEqual(speed_csv([(2, 1, 0), (1, 2, 0), (2, 1, 0)]), "1,2,0\n2,1,0\n")

    def test_table_url_puts_longitude_first(self):
        self.assertEqual(table_url("http://h:5000", [(24.9, 67.1), (24.8, 67.2)]),
                         "http://h:5000/table/v1/driving/67.100000,24.900000;67.200000,24.800000?annotations=duration")

    def test_null_becomes_infinity_and_back(self):
        self.assertEqual(clean_table([[0, None], [3.26, 0]]), [[0, math.inf], [3.26, 0]])
        self.assertEqual(to_json_table([[0, math.inf], [3.26, 0]]), [[0, None], [3.3, 0]])


class PureHelperTests(unittest.TestCase):
    def test_speed_csv_empty(self):
        self.assertEqual(speed_csv([]), "")

    def test_speed_csv_sorts_numerically(self):
        self.assertEqual(speed_csv([(10, 2, 5), (9, 3, 5)]), "9,3,5\n10,2,5\n")

    def test_speed_csv_refuses_two_speeds_for_one_segment(self):
        with self.assertRaises(ValueError):
            speed_csv([(1, 2, 0), (1, 2, 10)])

    def test_table_url_strips_trailing_slash_and_keeps_options(self):
        url = table_url("http://h:5001/", [(24.9, 67.1)], profile="foot", annotations="distance")
        self.assertEqual(url, "http://h:5001/table/v1/foot/67.100000,24.900000?annotations=distance")

    def test_table_url_needs_points(self):
        with self.assertRaises(ValueError):
            table_url("http://h", [])

    def test_unreachable_pair_survives_a_json_round_trip_as_infinity(self):
        # Review focus 1: `null` from OSRM is stored as `null` and read back as infinity, never zero.
        stored = json.dumps(to_json_table(clean_table([[0, None], [None, 0]])))
        self.assertEqual(stored, "[[0, null], [null, 0]]")
        self.assertEqual(clean_table(json.loads(stored)), [[0, math.inf], [math.inf, 0]])

    def test_to_json_table_refuses_nan(self):
        with self.assertRaises(ValueError):
            to_json_table([[math.nan]])


# ---------------------------------------------------------------------------------------------
# A fake OSRM server for the HTTP helpers.

class FakeOsrm:
    """A local HTTP server answering like `osrm-routed`; `script` lists (status, body) to send."""

    def __init__(self, script):
        self.script = list(script)
        self.paths = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 (name fixed by http.server)
                fake.paths.append(self.path)
                status, body = fake.script.pop(0) if len(fake.script) > 1 else fake.script[0]
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
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


TABLE_OK = {"code": "Ok", "durations": [[0, 310.46], [None, 0]], "distances": [[0, 2000.4], [1990, 0]]}
ROUTE_OK = {"code": "Ok",
            "routes": [{"duration": 99.0, "distance": 800.0,
                        "geometry": {"type": "LineString", "coordinates": [[67.1, 24.9], [67.2, 24.8]]},
                        "legs": [{"annotation": {"nodes": [11, 12, 13]}}]},
                       {"duration": 120.0}],
            "waypoints": [{"distance": 4.2}, {"distance": 7.5}]}
NO_SLEEP = {"sleep": lambda s: None}


class HttpTests(unittest.TestCase):
    def test_table_returns_cleaned_durations(self):
        with FakeOsrm([(200, TABLE_OK)]) as fake:
            self.assertEqual(table([(24.9, 67.1), (24.8, 67.2)], base=fake.base),
                             [[0, 310.46], [math.inf, 0]])
            self.assertTrue(fake.paths[0].startswith("/table/v1/driving/67.100000,24.900000;"))

    def test_table_can_return_distances(self):
        with FakeOsrm([(200, TABLE_OK)]) as fake:
            out = table([(24.9, 67.1), (24.8, 67.2)], base=fake.base, profile="foot", annotations="distance")
            self.assertEqual(out, [[0, 2000.4], [1990, 0]])
            self.assertIn("annotations=distance", fake.paths[0])

    def test_route_asks_for_full_geojson_and_returns_the_first_route(self):
        with FakeOsrm([(200, ROUTE_OK)]) as fake:
            r = route([(24.9, 67.1), (24.8, 67.2)], base=fake.base)
            self.assertEqual(r["duration"], 99.0)
            self.assertEqual(r["waypoints"], [{"distance": 4.2}, {"distance": 7.5}])
            query = parse_qs(urlsplit(fake.paths[0]).query)
            self.assertEqual(query, {"overview": ["full"], "geometries": ["geojson"]})

    def test_route_with_nodes_asks_for_node_annotations(self):
        with FakeOsrm([(200, ROUTE_OK)]) as fake:
            route([(24.9, 67.1), (24.8, 67.2)], base=fake.base, nodes=True)
            self.assertEqual(parse_qs(urlsplit(fake.paths[0]).query)["annotations"], ["nodes"])

    def test_route_needs_two_points(self):
        with self.assertRaises(ValueError):
            route([(24.9, 67.1)])

    def test_server_not_ready_is_retried(self):
        # Review focus 5: after a restart the first requests fail; the helper keeps asking.
        with FakeOsrm([(503, {"code": "Busy"}), (503, {"code": "Busy"}), (200, TABLE_OK)]) as fake:
            out = table([(24.9, 67.1), (24.8, 67.2)], base=fake.base)
            self.assertEqual(out[0][1], 310.46)
            self.assertEqual(len(fake.paths), 3)

    def test_refused_connections_are_retried(self):
        ok = mock.MagicMock()
        ok.__enter__.return_value = io.BytesIO(json.dumps(TABLE_OK).encode())
        refused = urllib.error.URLError(ConnectionRefusedError(10061, "refused"))
        with mock.patch.object(osrm_tools.urllib.request, "urlopen", side_effect=[refused, refused, ok]) as m:
            body = fetch_json("http://x/table", **NO_SLEEP)
        self.assertEqual(body["code"], "Ok")
        self.assertEqual(m.call_count, 3)

    def test_gives_up_after_the_wait_with_a_clear_message(self):
        clock = iter(range(0, 1000, 10))  # every call to the clock is 10 s later
        refused = urllib.error.URLError(ConnectionRefusedError(10061, "refused"))
        with mock.patch.object(osrm_tools.urllib.request, "urlopen", side_effect=refused) as m:
            with self.assertRaises(OsrmError) as ctx:
                fetch_json("http://x/table", wait_s=60, clock=lambda: next(clock), **NO_SLEEP)
        self.assertIn("did not answer within 60 s", str(ctx.exception))
        self.assertLessEqual(m.call_count, 8)

    def test_osrm_refusal_is_not_retried(self):
        with FakeOsrm([(400, {"code": "NoRoute", "message": "Impossible route"})]) as fake:
            with self.assertRaises(OsrmError) as ctx:
                route([(24.9, 67.1), (24.8, 67.2)], base=fake.base)
            self.assertEqual(ctx.exception.code, "NoRoute")
            self.assertEqual(len(fake.paths), 1)

    def test_wait_ready_polls_nearest(self):
        with FakeOsrm([(503, {}), (200, {"code": "Ok", "waypoints": []})]) as fake:
            wait_ready(fake.base, wait_s=5, **NO_SLEEP)
            self.assertTrue(all(p.startswith("/nearest/v1/driving/") for p in fake.paths))


# ---------------------------------------------------------------------------------------------
# File and Docker helpers, with `subprocess.run` mocked.

def completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class FreshCopyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "car"
        self.source.mkdir()
        for name in ("karachi.osrm.ebg", "karachi.osrm.cell_metrics", "karachi.osm.pbf", "notes.txt"):
            (self.source / name).write_text(name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_copies_only_osrm_files_into_an_emptied_folder(self):
        work = self.root / "work"
        work.mkdir()
        (work / "karachi.osrm.cell_metrics").write_text("customized before")
        (work / "updates.csv").write_text("1,2,0\n")
        fresh_copy(self.source, work)
        self.assertEqual(sorted(p.name for p in work.iterdir()),
                         ["karachi.osrm.cell_metrics", "karachi.osrm.ebg"])
        self.assertEqual((work / "karachi.osrm.cell_metrics").read_text(), "karachi.osrm.cell_metrics")

    def test_creates_the_work_folder(self):
        fresh_copy(self.source, self.root / "new" / "work")
        self.assertTrue((self.root / "new" / "work" / "karachi.osrm.ebg").exists())

    def test_refuses_to_empty_the_source(self):
        with self.assertRaises(ValueError):
            fresh_copy(self.source, self.source)

    def test_missing_osrm_files_fail_clearly(self):
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaises(FileNotFoundError) as ctx:
            fresh_copy(empty, self.root / "work")
        self.assertIn("karachi.osrm", str(ctx.exception))


class DockerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.work = Path(self.tmp.name)
        (self.work / "karachi.osrm.ebg").write_text("x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_customize_writes_the_speed_file_and_runs_the_image(self):
        with mock.patch.object(osrm_tools.subprocess, "run", return_value=completed()) as run:
            seconds = customize(self.work, "1,2,0\n")
        self.assertGreaterEqual(seconds, 0.0)
        self.assertEqual((self.work / "updates.csv").read_text(), "1,2,0\n")
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[:3], ["docker", "run", "--rm"])
        self.assertIn(IMAGE, cmd)
        self.assertEqual(cmd[cmd.index(IMAGE) + 1:],
                         ["osrm-customize", "/data/karachi.osrm", "--segment-speed-file", "/data/updates.csv"])
        self.assertIn(f"{self.work.resolve()}:/data", cmd)

    def test_customize_logged_returns_the_tool_output(self):
        log = "[info] RAM: peak bytes used: 4096\n"
        with mock.patch.object(osrm_tools.subprocess, "run", return_value=completed(0, log)):
            seconds, output = osrm_tools.customize_logged(self.work, "1,2,0\n")
        self.assertGreaterEqual(seconds, 0.0)
        self.assertIn("peak bytes used: 4096", output)

    def test_customize_without_rows_runs_a_plain_customize(self):
        with mock.patch.object(osrm_tools.subprocess, "run", return_value=completed()) as run:
            customize(self.work, "")
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[cmd.index(IMAGE) + 1:], ["osrm-customize", "/data/karachi.osrm"])

    def test_customize_failure_reports_the_last_lines(self):
        err = "\n".join(f"line {i}" for i in range(40)) + "\n[error] bad speed file"
        with mock.patch.object(osrm_tools.subprocess, "run", return_value=completed(1, "", err)):
            with self.assertRaises(RuntimeError) as ctx:
                customize(self.work, "1,2,0\n")
        self.assertIn("bad speed file", str(ctx.exception))
        self.assertNotIn("line 0\n", str(ctx.exception))

    def test_customize_needs_osrm_files(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(FileNotFoundError):
                customize(Path(empty), "")

    def test_missing_docker_is_a_clear_error(self):
        with mock.patch.object(osrm_tools.subprocess, "run", side_effect=FileNotFoundError("docker")):
            with self.assertRaises(RuntimeError) as ctx:
                customize(self.work, "")
        self.assertIn("docker", str(ctx.exception).lower())

    def test_start_server_replaces_the_container_and_waits(self):
        with mock.patch.object(osrm_tools.subprocess, "run", return_value=completed()) as run, \
                mock.patch.object(osrm_tools, "wait_ready") as ready:
            start_server(self.work, port=5002, name="osrm-scn")
        first, second = (c.args[0] for c in run.call_args_list)
        self.assertEqual(first, ["docker", "rm", "-f", "osrm-scn"])
        self.assertEqual(second[:4], ["docker", "run", "-d", "--name"])
        self.assertIn("5002:5000", second)
        self.assertEqual(second[second.index(IMAGE) + 1:],
                         ["osrm-routed", "--algorithm", "mld", "--max-table-size", "1000", "/data/karachi.osrm"])
        ready.assert_called_once_with("http://localhost:5002", wait_s=osrm_tools.READY_WAIT_S)

    def test_start_server_that_never_answers_shows_the_container_log(self):
        def fake_run(cmd, **kwargs):
            return completed(0, "[error] could not load cell metrics\n") if cmd[1] == "logs" else completed()

        with mock.patch.object(osrm_tools.subprocess, "run", side_effect=fake_run), \
                mock.patch.object(osrm_tools, "wait_ready", side_effect=OsrmError("did not answer")):
            with self.assertRaises(RuntimeError) as ctx:
                start_server(self.work)
        self.assertIn("could not load cell metrics", str(ctx.exception))

    def test_start_server_needs_osrm_files(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(FileNotFoundError):
                start_server(Path(empty))

    def test_stop_server_ignores_a_missing_container(self):
        with mock.patch.object(osrm_tools.subprocess, "run",
                               return_value=completed(1, "", "No such container: osrm")) as run:
            stop_server()
        self.assertEqual(run.call_args.args[0], ["docker", "rm", "-f", "osrm"])


if __name__ == "__main__":
    unittest.main()
