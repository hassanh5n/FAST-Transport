"""Research hub: the research site plus buttons to run experiments in WSL and publish results.

    Double-click research/Research Hub.bat, or run:  python research/hub/serve.py

Runs on Windows, listens on 127.0.0.1 only, standard library only. Experiments (listed in
hub/experiments.json) run in WSL. Jobs can start now or at a set time, and can publish their
results when they finish. Publishing commits and pushes the research/ folder only. Nothing here
touches the website, its backend, settings or database.
"""
import argparse
import ctypes
import functools
import json
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


def git(*args, timeout=60):
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, timeout=timeout,
                       creationflags=NO_WINDOW)
    return r.returncode, (r.stdout + r.stderr).strip()


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


def signature():
    items = []
    for p in RESEARCH.rglob("*"):
        parts = p.relative_to(RESEARCH).parts
        if parts[:2] in (("hub", "_site"), ("hub", "_site_new"), ("hub", "_logs")) or "logs" in parts or "__pycache__" in parts:
            continue
        if p.is_file():
            st = p.stat()
            items.append((str(p), st.st_mtime_ns, st.st_size))
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


def check_env():
    script = (f"echo WSL=ok; if [ -x {VENV_PY} ]; then echo VENV=ok; "
              f"{VENV_PY} -c 'import ortools; print(\"ORTOOLS=\" + ortools.__version__)' 2>/dev/null || echo ORTOOLS=; "
              f"cd '{WSL_REPO}' && {VENV_PY} research/run_budget.py --check 2>&1 | tail -3; else echo VENV=no; fi")
    rc, out = wsl(script, timeout=180)
    env = {"checked_at": now(), "wsl": "WSL=ok" in out, "venv": "VENV=ok" in out, "ortools": None, "limits": None}
    m = re.search(r"ORTOOLS=(\S*)", out)
    env["ortools"] = (m.group(1) or None) if m else None
    lim = next((l for l in out.splitlines() if l.startswith("limits:")), None)
    if lim:
        env["limits"] = lim.rstrip().endswith(" OK")
    if not env["wsl"]:
        env["message"] = "WSL did not start: " + " ".join(out.split())[:300]
    elif not env["venv"]:
        env["message"] = "The research Python environment is not set up yet. Press Install."
    elif env["limits"] is False:
        env["message"] = ("The free-tier limits are not applied, so limited runs would mean nothing. "
                          "See 'Limits without Docker' in research/README.md.")
    ENV["value"] = env
    return env


def wsl_busy():
    """True if an experiment script is running in WSL (also one started outside the hub)."""
    rc, out = wsl("pgrep -af '[r]esearch/.*[.]py'; true", timeout=30)
    names = script_names()
    runs = [l for l in out.splitlines() if any(n in l for n in names) and "--check" not in l and "--summarize" not in l]
    WSL_BUSY["value"] = bool(runs)
    return WSL_BUSY["value"]


def watch_wsl():
    """Refresh the busy flag in the background, so page requests never wait on WSL."""
    while True:
        try:
            wsl_busy()
        except Exception:  # noqa: BLE001 - keep the watcher alive
            pass
        time.sleep(20)


# ---------------------------------------------------------------- jobs

class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.state, self.kind, self.title = "idle", None, None
        self.started_at = self.finished_at = self.exit_code = None
        self.publish_after, self.publish_result, self.stopped = False, None, False
        self.proc, self.tail = None, deque(maxlen=40)

    def info(self):
        return {"state": self.state, "experiment": self.kind, "title": self.title, "started_at": self.started_at,
                "finished_at": self.finished_at, "exit_code": self.exit_code, "log_tail": list(self.tail),
                "publish_after": self.publish_after, "publish_result": self.publish_result, "stopped": self.stopped}

    def start(self, kind, publish_after=False):
        with self.lock:
            if self.state == "running":
                raise RuntimeError(f"{self.title} is already running.")
            if wsl_busy():
                raise RuntimeError("An experiment is already running in WSL (started outside this hub). Stop it first.")
            if kind == "install":
                title, publish_after = "Install the research Python environment", False
                script = (f"python3 -m venv ~/fc-research-venv && {VENV_PY} -m pip install -r "
                          f"'{WSL_REPO}/research/requirements.txt' && echo INSTALL-DONE")
            else:
                exp = experiment(kind)
                if exp is None:
                    raise RuntimeError(f"Unknown experiment {kind}.")
                title = exp["title"]
                version = code_version()
                args = " ".join(f"'{a.replace('{code_version}', version)}'" for a in exp.get("args", []))
                script = f"cd '{WSL_REPO}' && {VENV_PY} -u '{exp['script']}' {args}"
            LOGS.mkdir(exist_ok=True)
            log_path = LOGS / f"{kind}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
            self.proc = subprocess.Popen(["wsl.exe", "-e", "bash", "-lc", script], stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
            self.state, self.kind, self.title = "running", kind, title
            self.started_at, self.finished_at, self.exit_code = now(), None, None
            self.publish_after, self.publish_result, self.stopped = bool(publish_after), None, False
            self.tail.clear()
            WSL_BUSY["value"] = True
            threading.Thread(target=self._watch, args=(self.proc, log_path), daemon=True).start()

    def _watch(self, proc, log_path):
        keep_awake(True)
        try:
            with open(log_path, "w", encoding="utf-8") as log:
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
    _, branch = git("rev-parse", "--abbrev-ref", "HEAD")
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
