"""Reviewer tests for the hub's Windows-native runner (serve.py). No server, no WSL, nothing is run."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HUB = Path(__file__).resolve().parents[1] / "hub"
_spec = importlib.util.spec_from_file_location("hub_serve_review", HUB / "serve.py")
serve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(serve)


class SiteSignatureIgnoresTheNativeVenv(unittest.TestCase):
    """research/.venv is now the native runner's environment (Install creates it there). The hub's change
    detector, run on every /api/status poll (every 3 s), must not walk or react to it."""

    def test_venv_files_do_not_change_the_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / ".venv" / "Lib" / "site-packages" / "numpy"
            pkg.mkdir(parents=True)
            (pkg / "core.py").write_text("x = 1\n")
            (root / "results").mkdir()
            (root / "results" / "runs.jsonl").write_text("{}\n")
            with mock.patch.object(serve, "RESEARCH", root):
                before = serve.signature()
                (pkg / "core.py").write_text("x = 1  # pip upgraded this package\n")
                (pkg / "new_module.py").write_text("y = 2\n")
                after = serve.signature()
        self.assertEqual(before, after, "a pip install into research/.venv changes the site signature, so the "
                                        "hub rebuilds the site and walks every .venv file on each status poll")


class ScheduleBeforeTheFirstSetupCheck(unittest.TestCase):
    """On a PC without WSL, a needs-linux experiment must be refused at schedule time even when the
    startup setup check has not finished yet (the page shows nothing greyed out in that window)."""

    def test_needs_linux_schedule_is_refused_before_the_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            patches = [mock.patch.dict(serve.ENV, {"value": None}),
                       mock.patch.object(serve, "wsl", return_value=(127, "wsl.exe not found: WSL is not installed on this PC.")),
                       mock.patch.object(serve, "check_native", side_effect=lambda env: {**env, "runner": "native", "venv": True, "ortools": "9.15"}),
                       mock.patch.object(serve, "LOGS", Path(tmp)),
                       mock.patch.object(serve, "SCHEDULE_FILE", Path(tmp) / "schedule.json")]
            for p in patches:
                p.start()
            try:
                sched = serve.Schedule()
                sched.value = None
                with self.assertRaises(RuntimeError, msg="reroute-limits-quick was scheduled on a PC without WSL; "
                                                         "it is only refused when the start time comes"):
                    sched.set("reroute-limits-quick", "01:00", False)
            finally:
                for p in reversed(patches):
                    p.stop()


if __name__ == "__main__":
    unittest.main()
