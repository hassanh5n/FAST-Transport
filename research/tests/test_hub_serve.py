"""The hub's runner choice: WSL when it works, else this PC; experiments marked "needs": "linux" refused without WSL.

Pure decision logic only: no server, no WSL, no experiment is started (Popen is replaced).
"""
import importlib.util
import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

HUB = Path(__file__).resolve().parents[1] / "hub"
_spec = importlib.util.spec_from_file_location("hub_serve", HUB / "serve.py")
serve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(serve)

NATIVE_ENV = {"wsl": False, "venv": True, "ortools": "9.15", "limits": None, "runner": "native"}
WSL_ENV = {"wsl": True, "venv": True, "ortools": "9.15", "limits": True, "runner": "wsl"}


class FakeProc:
    def __init__(self, cmd, **kw):
        self.cmd, self.kw, self.pid, self.returncode = cmd, kw, 4242, None
        self.stdout = io.BytesIO(b"1 runs already done, 0 to go\n")

    def wait(self, timeout=None):
        self.returncode = 0
        return 0


class RunnerChoice(unittest.TestCase):
    def test_wsl_when_the_check_found_it(self):
        self.assertEqual(serve.pick_runner(WSL_ENV), "wsl")
        self.assertEqual(serve.pick_runner(NATIVE_ENV), "native")
        self.assertEqual(serve.pick_runner({"wsl": False}), "native")

    def test_needs_linux_marks_exactly_the_systemd_experiments(self):
        marked = {e["id"] for e in serve.build_site.load_experiments() if serve.needs_linux(e)}
        self.assertEqual(marked, {"time-budget", "time-budget-quick", "reroute-limits", "reroute-limits-quick",
                                  "reroute-scale"})

    def test_native_python_is_the_venv_or_this_python(self):
        py = serve.native_python()
        self.assertTrue(py == str(serve.native_venv_python()) or py == serve.sys.executable)


class CommandLine(unittest.TestCase):
    def test_native_command_runs_the_script_from_the_repo_with_the_same_args(self):
        exp = serve.experiment("optimizer-scale-quick")
        cmd = serve.experiment_command(exp, "native", "abc123", python="py.exe")
        self.assertEqual(cmd[:2], ["py.exe", "-u"])
        self.assertEqual(Path(cmd[2]), serve.REPO / "research" / "run_scale.py")
        self.assertEqual(cmd[3:], ["--quick", "--code-version", "abc123"])
        self.assertNotIn("wsl.exe", cmd)

    def test_wsl_command_is_unchanged(self):
        exp = serve.experiment("optimizer-scale-quick")
        cmd = serve.experiment_command(exp, "wsl", "abc123")
        self.assertEqual(cmd[:4], ["wsl.exe", "-e", "bash", "-lc"])
        self.assertEqual(cmd[4], f"cd '{serve.WSL_REPO}' && {serve.VENV_PY} -u 'research/run_scale.py' "
                                 "'--quick' '--code-version' 'abc123'")

    def test_native_refuses_needs_linux_and_names_wsl(self):
        exp = serve.experiment("reroute-limits-quick")
        with self.assertRaises(RuntimeError) as ctx:
            serve.experiment_command(exp, "native", "abc123")
        self.assertIn("WSL", str(ctx.exception))
        self.assertIn(exp["title"], str(ctx.exception))
        serve.experiment_command(exp, "wsl", "abc123")          # fine where the limits exist

    def test_install_command(self):
        self.assertEqual(serve.install_command("wsl")[0], "wsl.exe")
        cmd = serve.install_command("native")
        self.assertNotIn("wsl.exe", cmd)
        self.assertIn("venv", cmd[3])
        self.assertEqual(cmd[-2:], [str(serve.NATIVE_VENV), str(serve.RESEARCH / "requirements.txt")])

    def test_experiment_lines_skip_checks(self):
        lines = ["12 python research/run_scale.py --quick", "13 python research/run_budget.py --check",
                 "14 python research/run_reroute.py quality --summarize", "15 python other.py"]
        self.assertEqual(serve.experiment_lines(lines, serve.script_names()), lines[:1])

    @unittest.skipUnless(os.name == "nt", "taskkill exists on Windows only")
    def test_stop_kills_the_tree_on_windows(self):
        with mock.patch.object(serve.subprocess, "run") as run:
            serve.kill_tree(123)
        self.assertEqual(run.call_args[0][0], ["taskkill", "/T", "/F", "/PID", "123"])


class JobStart(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patches = [mock.patch.dict(serve.ENV, {"value": dict(NATIVE_ENV)}),
                   mock.patch.object(serve, "wsl_busy", return_value=False),
                   mock.patch.object(serve, "code_version", return_value="abc123"),
                   mock.patch.object(serve, "LOGS", Path(self.tmp.name)),
                   mock.patch.object(serve, "keep_awake")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_refuses_needs_linux_without_wsl(self):
        job = serve.Job()
        with mock.patch.object(serve.subprocess, "Popen") as popen:
            with self.assertRaises(RuntimeError) as ctx:
                job.start("time-budget-quick")
        popen.assert_not_called()
        self.assertIn("WSL", str(ctx.exception))
        self.assertEqual(job.state, "idle")

    def test_schedule_refuses_needs_linux_without_wsl(self):
        with self.assertRaises(RuntimeError):
            serve.Schedule().set("reroute-limits", "01:00", False)

    def test_native_start_runs_from_the_repo_and_logs_the_runner(self):
        job = serve.Job()
        with mock.patch.object(serve.subprocess, "Popen", side_effect=FakeProc) as popen:
            job.start("optimizer-scale-quick")
        proc = popen.call_args
        self.assertEqual(proc.kwargs["cwd"], str(serve.REPO))
        self.assertEqual(proc.kwargs["env"]["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(proc.args[0][-3:], ["--quick", "--code-version", "abc123"])
        for _ in range(100):
            if job.state == "idle":
                break
            time.sleep(0.02)
        self.assertEqual((job.state, job.exit_code, job.run_with), ("idle", 0, "native"))
        log = next(Path(self.tmp.name).glob("optimizer-scale-quick-*.log")).read_text(encoding="utf-8")
        self.assertTrue(log.startswith("Runs on this PC (no WSL): "))
        self.assertIn("0 to go", log)

    def test_wsl_start_keeps_the_wsl_command(self):
        serve.ENV["value"] = dict(WSL_ENV)
        job = serve.Job()
        with mock.patch.object(serve.subprocess, "Popen", side_effect=FakeProc) as popen:
            job.start("time-budget-quick")
        self.assertEqual(popen.call_args.args[0][0], "wsl.exe")
        self.assertNotIn("cwd", popen.call_args.kwargs)
        for _ in range(100):
            if job.state == "idle":
                break
            time.sleep(0.02)


if __name__ == "__main__":
    unittest.main()
