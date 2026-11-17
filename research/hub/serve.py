"""Research hub: the research site plus buttons to run experiments and publish results.

    Double-click research/Research Hub.bat, or run:  python research/hub/serve.py

Runs on Windows, listens on 127.0.0.1 only, standard library only. Experiments (listed in
hub/experiments.json) run in WSL when WSL works (~/fc-research-venv). Without WSL they run on this
PC with research/.venv (or the Python running the hub when that is missing), except those marked
"needs": "linux", which are refused. Jobs can start now or at a set time, and can publish their
results when they finish. Publishing commits and pushes the research/ folder only. Nothing here
touches the website, its backend, settings or database.
"""
import argparse
import ctypes
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from collections import deque
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HUB = Path(__file__).resolve().parent
RESEARCH = HUB.parent
REPO = RESEARCH.parent
SITE = HUB / "_site"
LOGS = HUB / "_logs"
SCHEDULE_FILE = LOGS / "schedule.json"
sys.path.insert(0, str(HUB))
sys.path.insert(0, str(RESEARCH))
import build_site  # noqa: E402
import run_budget  # noqa: E402

VENV_PY = "~/fc-research-venv/bin/python"
NATIVE_VENV = RESEARCH / ".venv"
PORTS = range(8765, 8781)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def wsl_path(p):
    s = str(Path(p).resolve()).replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    return f"/mnt/{m.group(1).lower()}/{m.group(2)}" if m else s


WSL_REPO = wsl_path(REPO)


def clean(b):
    """wsl.exe prints its own errors in UTF-16 and Linux output in UTF-8."""
    return b.replace(b"\x00", b"").decode("utf-8", "replace")


def wsl(script, timeout=120):
    try:
        r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", script], capture_output=True, timeout=timeout,
                           creationflags=NO_WINDOW)
        return r.returncode, clean(r.stdout) + clean(r.stderr)
    except FileNotFoundError:
        return 127, "wsl.exe not found: WSL is not installed on this PC."
    except subprocess.TimeoutExpired:
        return 124, "WSL did not answer in time."


def _git_candidates():
    """git on PATH first, then the usual Git for Windows / Git Bash install folders (per-machine and per-user)."""
    roots = [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(os.path.join(local, "Programs"))
    roots += ["C:\\", "D:\\", "E:\\"]                          # Git installed at the top of a drive, e.g. D:\\Git
    found = [os.path.join(r, "Git", sub, "git.exe") for r in roots if r for sub in ("cmd", "bin", "mingw64\\bin")]
    extra = os.environ.get("FLEETCENTRIC_GIT")                 # set this if git lives somewhere else
    return ([extra] if extra else []) + ["git"] + [f for f in found if os.path.exists(f)]


GIT_CANDIDATES = _git_candidates()


def git(*args, timeout=60):
    """Run git in the repo. Never raises: a missing git must not stop an experiment from starting."""
    for exe in GIT_CANDIDATES:
        try:
            r = subprocess.run([exe, "-C", str(REPO), *args], capture_output=True, text=True, timeout=timeout,
                               creationflags=NO_WINDOW)
            return r.returncode, (r.stdout + r.stderr).strip()
        except FileNotFoundError:
            continue
        except (OSError, subprocess.SubprocessError) as exc:
            return 1, f"git failed: {exc}"
    return 127, "git not found: install Git for Windows (git-scm.com) to publish."


def code_version():
    rc, sha = git("rev-parse", "HEAD")
    if rc:
        return "unknown"
    _, dirty = git("status", "--porcelain", "--", "research", ":!research/results")
    return sha + ("-dirty" if dirty.strip() else "")


def pages_url():
    rc, url = git("remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url) if rc == 0 else None
    return f"https://{m.group(1).lower()}.github.io/{m.group(2)}/" if m else None


def keep_awake(on):
    """Stop Windows from idle-sleeping while this thread needs it (Windows' standard per-thread request)."""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))
    except (AttributeError, OSError):
        pass


# ---------------------------------------------------------------- site

_site_lock = threading.Lock()
_site = {"sig": None, "version": 0}


SKIP_TOP = {".venv", "venv", ".git"}          # Python environments (the native runner's .venv) are not site inputs
SKIP_DIRS = {"logs", "__pycache__"}
SKIP_HUB = {"_site", "_site_new", "_logs"}


def signature():
    """A hash of every site input under research/ (path, mtime, size). Run on each status poll, so it prunes
    research/.venv, the built site and logs instead of walking them."""
    items = []
    for dirpath, dirnames, filenames in os.walk(RESEARCH):
        rel = Path(dirpath).relative_to(RESEARCH).parts
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS
                       and not (not rel and d in SKIP_TOP)
                       and not (rel == ("hub",) and d in SKIP_HUB)
                       and not (Path(dirpath, d) / "pyvenv.cfg").exists()]
        for name in filenames:
            p = os.path.join(dirpath, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            items.append((p, st.st_mtime_ns, st.st_size))
    return hash(tuple(sorted(items)))


def ensure_site():
    with _site_lock:
        sig = signature()
        if sig == _site["sig"]:
            return _site["version"]
        tmp = HUB / "_site_new"
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        rc, commit = git("rev-parse", "HEAD")
        build_site.build(tmp, {"commit": commit if rc == 0 else None, "local": True})
        if SITE.exists():
            shutil.rmtree(SITE, ignore_errors=True)
        tmp.rename(SITE)
        _site["sig"], _site["version"] = sig, _site["version"] + 1
        return _site["version"]


# ---------------------------------------------------------------- environment

ENV = {"value": None}
WSL_BUSY = {"value": False}


def experiment(exp_id):
    return next((e for e in build_site.load_experiments() if e["id"] == exp_id), None)


def script_names():
    return sorted({Path(e["script"]).name for e in build_site.load_experiments()} | {"optimize.py"})


def native_venv_python(venv=NATIVE_VENV):
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def native_python():
    """research/.venv's Python when it exists, else the Python running the hub."""
    py = native_venv_python()
    return str(py) if py.exists() else sys.executable


def pick_runner(env):
    """'wsl' when the last setup check found a working WSL, else 'native' (this PC, no WSL)."""
    return "wsl" if env and env.get("wsl") else "native"


def runner():
    return pick_runner(ENV["value"])


def needs_linux(exp):
    return (exp or {}).get("needs") == "linux"


def linux_refusal(exp):
    return (f"{exp['title']} needs Linux: its free-tier limits come from systemd cgroups, which this PC "
            "can only provide through WSL, and WSL is not working here. Install WSL with systemd "
            "(see research/README.md), then press Check setup.")


def experiment_command(exp, run_with, version, python=None):
    """The command line that runs an experiment: through WSL, or natively from the repository root."""
    args = [a.replace("{code_version}", version) for a in exp.get("args", [])]
    if run_with == "wsl":
        quoted = " ".join(f"'{a}'" for a in args)
        return ["wsl.exe", "-e", "bash", "-lc", f"cd '{WSL_REPO}' && {VENV_PY} -u '{exp['script']}' {quoted}"]
    if needs_linux(exp):
        raise RuntimeError(linux_refusal(exp))
    return [python or native_python(), "-u", str(REPO / exp["script"]), *args]


INSTALL_NATIVE = (
    "import os, subprocess, sys\n"
    "venv, req = sys.argv[1], sys.argv[2]\n"
    "py = os.path.join(venv, 'Scripts', 'python.exe') if os.name == 'nt' else os.path.join(venv, 'bin', 'python')\n"
    "if not os.path.exists(py):\n"
    "    print('Creating', venv, flush=True)\n"
    "    subprocess.check_call([sys.executable, '-m', 'venv', venv])\n"
    "subprocess.check_call([py, '-m', 'pip', 'install', '-r', req])\n"
    "print('INSTALL-DONE')\n")


def install_command(run_with):
    if run_with == "wsl":
        return ["wsl.exe", "-e", "bash", "-lc", f"python3 -m venv ~/fc-research-venv && {VENV_PY} -m pip install -r "
                f"'{WSL_REPO}/research/requirements.txt' && echo INSTALL-DONE"]
    base = getattr(sys, "_base_executable", None) or sys.executable    # not the venv's own Python
    return [base, "-u", "-c", INSTALL_NATIVE, str(NATIVE_VENV), str(RESEARCH / "requirements.txt")]


def check_native(env):
    """Fill env for running on this PC: research/.venv and OR-Tools; no limits without WSL."""
    py = native_python()
    env.update(runner="native", venv=native_venv_python().exists(), python=py, limits=None)
    try:
        r = subprocess.run([py, "-c", "import ortools; print('ORTOOLS=' + ortools.__version__)"], capture_output=True,
                           timeout=120, creationflags=NO_WINDOW)
        out = clean(r.stdout)
    except (OSError, subprocess.SubprocessError):
        out = ""
    m = re.search(r"ORTOOLS=(\S+)", out)
    env["ortools"] = m.group(1) if m else None
    if not env["venv"] or not env["ortools"]:
        env["message"] = ("WSL is not available, so experiments run on this PC, but the research Python environment "
                          "(research/.venv with OR-Tools) is not set up yet. Press Install.")
    return env


def check_env():
    script = (f"echo WSL=ok; if [ -x {VENV_PY} ]; then echo VENV=ok; "
              f"{VENV_PY} -c 'import ortools; print(\"ORTOOLS=\" + ortools.__version__)' 2>/dev/null || echo ORTOOLS=; "
              f"cd '{WSL_REPO}' && {VENV_PY} research/run_budget.py --check 2>&1 | tail -3; else echo VENV=no; fi")
    rc, out = wsl(script, timeout=180)
    env = {"checked_at": now(), "wsl": "WSL=ok" in out, "venv": "VENV=ok" in out, "ortools": None, "limits": None,
           "runner": "wsl"}
    if not env["wsl"]:
        env["wsl_error"] = " ".join(out.split())[:300]
        ENV["value"] = check_native(env)
        return env
    m = re.search(r"ORTOOLS=(\S*)", out)
    env["ortools"] = (m.group(1) or None) if m else None
    lim = next((l for l in out.splitlines() if l.startswith("limits:")), None)
    if lim:
        env["limits"] = lim.rstrip().endswith(" OK")
    if not env["venv"]:
        env["message"] = "The research Python environment is not set up yet. Press Install."
    elif env["limits"] is False:
        env["message"] = ("The free-tier limits are not applied, so limited runs would mean nothing. "
                          "See 'Limits without Docker' in research/README.md.")
    ENV["value"] = env
    return env


def experiment_lines(lines, names):
    """The process lines that are experiment runs (not --check or --summarize)."""
    return [l for l in lines if any(n in l for n in names) and "--check" not in l and "--summarize" not in l]


def native_processes():
    """(pid, command line) of every Python process on this PC, except the hub itself."""
    if os.name == "nt":
        cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
               "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
               "ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"]
    else:
        cmd = ["pgrep", "-af", "python"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=60, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for line in clean(r.stdout).splitlines():
        pid, _, rest = line.strip().partition(" ")
        if pid.isdigit() and int(pid) != os.getpid():
            out.append((int(pid), rest))
    return out


def native_runs():
    names = script_names()
    return [(pid, cmd) for pid, cmd in native_processes() if experiment_lines([cmd], names)]


def wsl_busy():
    """True if an experiment script is running (in WSL, or on this PC without WSL), also one started outside the hub."""
    if ENV["value"] is None:                  # not checked yet: do not guess which runner to ask
        return WSL_BUSY["value"]
    if runner() == "native":
        WSL_BUSY["value"] = bool(native_runs())
        return WSL_BUSY["value"]
    rc, out = wsl("pgrep -af '[r]esearch/.*[.]py'; true", timeout=30)
    WSL_BUSY["value"] = bool(experiment_lines(out.splitlines(), script_names()))
    return WSL_BUSY["value"]


def kill_tree(pid):
    """End a process and everything it started (run_scale and run_reroute start worker processes)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, timeout=30,
                       creationflags=NO_WINDOW)
    else:
        subprocess.run(["pkill", "-TERM", "-P", str(pid)], capture_output=True, timeout=30)
        try:
            os.kill(pid, 15)
        except OSError:
            pass


def watch_wsl():
    """Refresh the busy flag in the background, so page requests never wait on WSL."""
    while True:
        try:
            wsl_busy()
        except Exception:  # noqa: BLE001 - keep the watcher alive
            pass
        time.sleep(20)


# ---------------------------------------------------------------- jobs

def runner_line(run_with, cmd):
    """First log line of a job: where it runs and the command (the install script shortened)."""
    where = "in WSL" if run_with == "wsl" else "on this PC (no WSL)"
    return f"Runs {where}: " + " ".join(c if len(c) < 200 else c.split("\n")[0] + " ..." for c in cmd)


class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.state, self.kind, self.title = "idle", None, None
        self.started_at = self.finished_at = self.exit_code = None
        self.publish_after, self.publish_result, self.stopped = False, None, False
        self.proc, self.tail, self.run_with = None, deque(maxlen=40), None

    def info(self):
        return {"state": self.state, "experiment": self.kind, "title": self.title, "started_at": self.started_at,
                "finished_at": self.finished_at, "exit_code": self.exit_code, "log_tail": list(self.tail),
                "publish_after": self.publish_after, "publish_result": self.publish_result, "stopped": self.stopped,
                "runner": self.run_with}

    def start(self, kind, publish_after=False):
        with self.lock:
            if self.state == "running":
                raise RuntimeError(f"{self.title} is already running.")
            if ENV["value"] is None:
                check_env()
            run_with = runner()
            if wsl_busy():
                where = "in WSL" if run_with == "wsl" else "on this PC"
                raise RuntimeError(f"An experiment is already running {where} (started outside this hub). Stop it first.")
            if kind == "install":
                title, publish_after = "Install the research Python environment", False
                cmd = install_command(run_with)
            else:
                exp = experiment(kind)
                if exp is None:
                    raise RuntimeError(f"Unknown experiment {kind}.")
                title = exp["title"]
                if run_with == "native" and needs_linux(exp):
                    raise RuntimeError(linux_refusal(exp))
                version = code_version()
                if version == "unknown" and any("{code_version}" in a for a in exp.get("args", [])):
                    # A run recorded with code version "unknown" cannot be traced back to its code.
                    raise RuntimeError("Git could not report the code version, so this run would be recorded "
                                       "as 'unknown'. Install Git for Windows (git-scm.com) and reopen the hub.")
                cmd = experiment_command(exp, run_with, version)
            LOGS.mkdir(exist_ok=True)
            log_path = LOGS / f"{kind}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
            if run_with == "wsl":
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
            else:
                # UTF-8 output whatever the console code page, so the log reads as it does from WSL.
                child_env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
                self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(REPO),
                                             env=child_env, creationflags=NO_WINDOW)
            self.run_with = run_with
            self.state, self.kind, self.title = "running", kind, title
            self.started_at, self.finished_at, self.exit_code = now(), None, None
            self.publish_after, self.publish_result, self.stopped = bool(publish_after), None, False
            self.tail.clear()
            self.tail.append(runner_line(run_with, cmd))
            WSL_BUSY["value"] = True
            threading.Thread(target=self._watch, args=(self.proc, log_path), daemon=True).start()

    def _watch(self, proc, log_path):
        keep_awake(True)
        try:
            with open(log_path, "w", encoding="utf-8") as log:
                log.write("".join(t + "\n" for t in self.tail))    # the runner line written by start()
                for raw in iter(proc.stdout.readline, b""):
                    line = clean(raw).rstrip()
                    if line:
                        self.tail.append(line)
                        log.write(line + "\n")
                        log.flush()
            proc.wait()
        finally:
            with self.lock:
                self.exit_code, self.state, self.finished_at = proc.returncode, "idle", now()
            WSL_BUSY["value"] = False
            if self.kind == "install":
                threading.Thread(target=check_env, daemon=True).start()
            elif self.publish_after and self.exit_code == 0 and not self.stopped:
                self.tail.append("Publishing results...")
                self.publish_result = publish()
                self.tail.append(self.publish_result["message"])
            keep_awake(False)

    def stop(self):
        with self.lock:
            proc = self.proc if self.state == "running" else None
            self.stopped = True
        if (self.run_with if proc else runner()) == "native":
            # The job's whole process tree, then any run started outside the hub.
            for pid in ([proc.pid] if proc else []) + [pid for pid, _ in native_runs()]:
                kill_tree(pid)
        else:
            # Stop the Linux processes as well: ending wsl.exe alone can leave them running.
            kills = "; ".join(f"pkill -f '[r]esearch/{n}'" for n in script_names())
            wsl(kills + "; true", timeout=30)
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
        WSL_BUSY["value"] = False


JOB = Job()


# ---------------------------------------------------------------- schedule

class Schedule:
    """One pending start time, kept in hub/_logs/schedule.json so it survives a hub restart."""

    def __init__(self):
        self.lock = threading.Lock()
        self.value, self.last = None, None
        try:
            self.value = json.loads(SCHEDULE_FILE.read_text())
        except (OSError, ValueError):
            pass

    def _save(self):
        LOGS.mkdir(exist_ok=True)
        if self.value:
            SCHEDULE_FILE.write_text(json.dumps(self.value))
        elif SCHEDULE_FILE.exists():
            SCHEDULE_FILE.unlink()

    def set(self, exp_id, hhmm, publish_after):
        exp = experiment(exp_id)
        if exp is None:
            raise RuntimeError(f"Unknown experiment {exp_id}.")
        if needs_linux(exp):
            if ENV["value"] is None:          # the startup check may still be running: check now, do not guess
                check_env()
            if runner() == "native":
                raise RuntimeError(linux_refusal(exp))
        m = re.match(r"^(\d{1,2}):(\d{2})$", hhmm or "")
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise RuntimeError("Give the start time as HH:MM.")
        local = datetime.now()
        at = local.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if at <= local:
            at += timedelta(days=1)
        with self.lock:
            self.value = {"experiment": exp_id, "title": exp["title"], "at": at.isoformat(timespec="minutes"),
                          "publish_after": bool(publish_after), "created_at": now()}
            self.last = None
            self._save()
        return self.value

    def cancel(self):
        with self.lock:
            self.value = None
            self._save()

    def info(self):
        return {"pending": self.value, "last": self.last}

    def loop(self):
        awake = False
        while True:
            with self.lock:
                v = self.value
            if v and not awake:
                keep_awake(True)          # the PC must still be awake at the start time
                awake = True
            elif not v and awake:
                keep_awake(False)
                awake = False
            if v and datetime.now() >= datetime.fromisoformat(v["at"]):
                try:
                    JOB.start(v["experiment"], v["publish_after"])
                    self.last = f"Started {v['title']} at {datetime.now().strftime('%H:%M')} as scheduled."
                except RuntimeError as e:
                    self.last = f"Scheduled start of {v['title']} skipped: {e}"
                self.cancel()
            time.sleep(15)


SCHEDULE = Schedule()


# ---------------------------------------------------------------- git and publish

_git_cache = {"value": None, "at": 0.0}
_publish_lock = threading.Lock()


def git_status(force=False):
    if not force and _git_cache["value"] and time.time() - _git_cache["at"] < 10:
        return _git_cache["value"]
    rc, branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if rc == 127:                                   # git not installed: say so once, not as a branch name
        return {"branch": None, "changes": 0, "ahead": 0, "pages_url": None, "error": branch}
    _, porcelain = git("status", "--porcelain", "--", "research")
    rc, ahead = git("rev-list", "--count", "@{u}..HEAD")
    info = {"branch": branch, "changes": len([l for l in porcelain.splitlines() if l.strip()]),
            "ahead": int(ahead) if rc == 0 and ahead.isdigit() else 0, "pages_url": pages_url()}
    _git_cache.update(value=info, at=time.time())
    return info


def publish():
    if JOB.state == "running":
        return {"ok": False, "message": "Wait for the running job to finish, or stop it, before publishing."}
    with _publish_lock:
        for exp in build_site.load_experiments():
            d = RESEARCH / exp["dir"]
            if exp.get("kind") == "budget" and (d / "runs.jsonl").exists():
                run_budget.summarize(d)
        steps = []
        rc, out = git("add", "--", "research")
        if rc:
            return {"ok": False, "message": f"git add failed: {out}"}
        staged = git("diff", "--cached", "--quiet", "--", "research")[0] == 1
        if staged:
            msg = f"Research: publish results ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
            rc, out = git("commit", "-m", msg, "--", "research")
            if rc:
                return {"ok": False, "message": f"git commit failed: {out[-400:]}"}
            steps.append("committed research/")
        rc, out = git("push", "origin", "HEAD", timeout=180)
        if rc:
            return {"ok": False, "message": f"Saved locally but the push failed: {out[-400:]}"}
        steps.append("pushed")
        git_status(force=True)
        url = pages_url()
        return {"ok": True, "message": f"Published ({', '.join(steps)}). The shared page updates in a minute or two"
                                       + (f": {url}" if url else ".")}


# ---------------------------------------------------------------- http

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def status(self):
        return {"local": True, "site_version": ensure_site(), "job": JOB.info(), "env": ENV["value"],
                "runner": runner() if ENV["value"] else None,
                "wsl_busy": JOB.state != "running" and WSL_BUSY["value"], "git": git_status(),
                "schedule": SCHEDULE.info()}

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/status":
            return self.send_json(self.status())
        if path in ("/", "/index.html", "/data/index.json"):
            ensure_site()
        return super().do_GET()

    def do_POST(self):
        # A custom header cannot be sent cross-site without a CORS preflight, which this server never answers.
        if self.headers.get("X-Hub") != "1":
            return self.send_json({"error": "forbidden"}, 403)
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        path = self.path.split("?")[0]
        try:
            if path == "/api/check":
                return self.send_json({"env": check_env()})
            if path == "/api/start":
                JOB.start(body.get("experiment", ""), body.get("publish_after", False))
                return self.send_json(self.status())
            if path == "/api/stop":
                JOB.stop()
                return self.send_json(self.status())
            if path == "/api/schedule":
                SCHEDULE.set(body.get("experiment", ""), body.get("at", ""), body.get("publish_after", False))
                return self.send_json(self.status())
            if path == "/api/schedule/cancel":
                SCHEDULE.cancel()
                return self.send_json(self.status())
            if path == "/api/publish":
                return self.send_json(publish())
        except RuntimeError as e:
            return self.send_json({"error": str(e)}, 409)
        return self.send_json({"error": "not found"}, 404)


def already_running():
    for port in PORTS:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1) as r:
                if json.loads(r.read()).get("local"):
                    return port
        except (OSError, ValueError):
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()

    port = already_running()
    if port and not args.port:
        print(f"The research hub is already running: http://127.0.0.1:{port}/")
        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{port}/")
        return

    print("Building the research site...")
    ensure_site()
    handler = functools.partial(Handler, directory=str(SITE))
    server = None
    for p in ([args.port] if args.port else PORTS):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), handler)
            break
        except OSError:
            continue
    if server is None:
        sys.exit("No free port between 8765 and 8780.")
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    for target in (check_env, watch_wsl, SCHEDULE.loop):
        threading.Thread(target=target, daemon=True).start()
    print(f"FleetCentric research hub: {url}")
    print("Keep this window open while you use the hub, and while a job runs or is scheduled.")
    print("Close it (or press Ctrl+C) to stop.")
    if SCHEDULE.value:
        print(f"Scheduled: {SCHEDULE.value['title']} at {SCHEDULE.value['at']}.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
