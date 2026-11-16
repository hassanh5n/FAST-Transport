"""Reviewer tests for the optimizer-scaling module (optimize.py lookup, scale_instances.py, run_scale.py).

Written by the independent review, not the implementer. A failing test here demonstrates a defect.
"""
import json
import re
import tempfile
import unittest
from pathlib import Path

from optimize import solve

HUB_STOP = re.compile(r"research/run_scale[.]py")     # hub/serve.py stop(): pkill -f '[r]esearch/run_scale.py'
HUB_BUSY = re.compile(r"research/.*[.]py")             # hub/serve.py wsl_busy(): pgrep -af '[r]esearch/.*[.]py'


class WorkerIsVisibleToTheHubTests(unittest.TestCase):
    """The hub stops a run with `pkill -f '[r]esearch/run_scale.py'` and decides whether something is
    running with `pgrep -af '[r]esearch/.*[.]py'` (hub/serve.py: stop, wsl_busy). Both only match
    processes whose command line names the script. A multiprocessing "spawn" worker's command line is
    `python -c "from multiprocessing.spawn import spawn_main; ..."`, so Stop left the 300 s solve running.
    run_scale.py now starts each worker as `python .../research/run_scale.py --worker ...`."""

    def test_worker_command_names_the_script(self):
        from run_scale import worker_command
        argv = worker_command({"key": "k", "instance": "Nadeem", "lookup": "matrix"}, Path("out"), 10, Path("r.json"))
        cmdline = " ".join(argv).replace("\\", "/")
        self.assertRegex(cmdline, HUB_STOP)
        self.assertRegex(cmdline, HUB_BUSY)

    def test_running_worker_command_line_names_the_script_and_returns_its_row(self):
        import psutil
        from run_scale import plan, start_worker
        job = plan(["Nadeem"], lookups=["matrix"], quick=True)[0]
        with tempfile.TemporaryDirectory() as tmp:
            out_dir, result = Path(tmp), Path(tmp) / "row.json"
            (out_dir / "runs").mkdir()
            proc = start_worker(job, out_dir, 1, result)
            try:
                cmdline = " ".join(psutil.Process(proc.pid).cmdline()).replace("\\", "/")
            finally:
                code = proc.wait(timeout=120)
            self.assertRegex(cmdline, HUB_STOP, f"hub Stop cannot reach the worker: {cmdline!r}")
            self.assertEqual(code, 0)
            row = json.loads(result.read_text())
            self.assertEqual((row["key"], row["status"], row["budget_s"]), (job["key"], "ok", 1))
            self.assertTrue((out_dir / "runs" / f"{job['key']}.json").exists())    # written by the worker

    def test_worker_failure_becomes_a_failed_row(self):
        from run_scale import run_in_worker
        job = {"key": "scale-x", "setup": "Nobody matrix", "instance": "Nobody", "lookup": "matrix", "repeat": 1}
        with tempfile.TemporaryDirectory() as tmp:
            row = run_in_worker(job, Path(tmp), 1)
        self.assertEqual(row["status"], "failed")
        self.assertIn("Nobody", row["error"])


class NoneArcTests(unittest.TestCase):
    """Review Focus 3 with the matrix's own marker for 'no road' (None), not just a long time."""

    T = [[0, 900.4, 800.2, None],
         [900.4, 0, 120.7, None],
         [800.2, 130.2, 0, None],
         [None, None, None, 0]]
    Q = [0, 5, 3, 8]

    def test_none_arcs_drop_the_stop_under_both_lookups(self):
        a, _ = solve(self.T, self.Q, [10, 10], 2, lookup="callback")
        b, _ = solve(self.T, self.Q, [10, 10], 2, lookup="matrix")
        self.assertEqual((a["dropped"], b["dropped"]), ([3], [3]))


class PeakMemoryUnitsTests(unittest.TestCase):
    """ru_maxrss is KB on Linux and bytes on macOS (reviewer note on optimize.peak_memory_mb)."""

    def _peak(self, platform, maxrss):
        import sys
        import types
        from unittest import mock
        import optimize
        fake = types.SimpleNamespace(RUSAGE_SELF=0, getrusage=lambda _: types.SimpleNamespace(ru_maxrss=maxrss))
        with mock.patch.dict(sys.modules, {"resource": fake}), mock.patch.object(optimize.sys, "platform", platform):
            return optimize.peak_memory_mb()

    def test_linux_kb(self):
        self.assertEqual(self._peak("linux", 512 * 1024), 512)

    def test_macos_bytes(self):
        self.assertEqual(self._peak("darwin", 512 * 1024 * 1024), 512)


if __name__ == "__main__":
    unittest.main()
