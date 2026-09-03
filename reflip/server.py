"""Find, start, watch and stop the local model server.

The sibling tools on this machine have no daemon and no server. This one needs
one, because the rewriting is done by a model and the model lives behind an HTTP
API. So the rule here is narrower: reflip starts a server only when asked, only
when nothing is already listening, and stops only the process it started itself.
A server that was already up when we arrived is left alone, because it belongs
to whoever started it.

Nothing is installed for you. When the runtime is missing the caller gets a
sentence saying so and where to get it, never a silent failure.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

RUNTIME = "ollama"
DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3:4b-instruct-2507-q4_K_M"
HOME = Path(os.environ.get("REFLIP_HOME", Path.home() / ".reflip"))
PIDFILE = HOME / "server.pid"
LOGFILE = HOME / "server.log"
START_TIMEOUT = 40.0
DOWNLOAD_PAGE = "https://ollama.com/download"


@dataclass
class Server:
    """What the server is doing, in the words the window will show."""

    url: str = DEFAULT_URL
    installed: bool = False
    running: bool = False
    ours: bool = False          # started by reflip, so ours to stop
    version: str | None = None
    models: list[dict] = field(default_factory=list)
    loaded: list[str] = field(default_factory=list)  # models currently in memory
    reason: str | None = None   # why it is not usable, as a sentence

    def has(self, model: str) -> bool:
        names = {m.get("name", "") for m in self.models}
        if model in names:
            return True
        # A model asked for without its tag matches the one that is downloaded.
        return ":" not in model and any(n.split(":")[0] == model for n in names)

    def to_dict(self) -> dict:
        return {"url": self.url, "installed": self.installed, "running": self.running,
                "ours": self.ours, "version": self.version, "reason": self.reason,
                "models": self.models, "loaded": self.loaded}


def binary() -> str | None:
    """Where the runtime is. A Finder-launched app inherits a PATH without homebrew in it."""
    found = shutil.which(RUNTIME)
    if found:
        return found
    for p in (f"/usr/local/bin/{RUNTIME}", f"/opt/homebrew/bin/{RUNTIME}",
              f"/Applications/Ollama.app/Contents/Resources/{RUNTIME}"):
        if os.access(p, os.X_OK):
            return p
    return None


def _get(url: str, path: str, timeout: float = 3.0) -> dict | None:
    try:
        with urllib.request.urlopen(url.rstrip("/") + path, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None


def _our_pid() -> int | None:
    """The pid we wrote when we started a server, if that process is still alive."""
    try:
        pid = int(PIDFILE.read_text().strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        PIDFILE.unlink(missing_ok=True)
        return None
    return pid


def status(url: str = DEFAULT_URL, model: str | None = None) -> Server:
    """One reading of the server. Cheap enough to call on a timer."""
    s = Server(url=url)
    s.installed = binary() is not None
    version = _get(url, "/api/version")
    s.running = version is not None
    if version:
        s.version = version.get("version")
        tags = _get(url, "/api/tags") or {}
        s.models = [{"name": m.get("name"), "size": m.get("size", 0),
                     "family": (m.get("details") or {}).get("family")}
                    for m in tags.get("models", [])]
        ps = _get(url, "/api/ps") or {}
        s.loaded = [m.get("name") for m in ps.get("models", [])]
    s.ours = _our_pid() is not None and s.running
    if not s.running:
        s.reason = ("The model server is not running. Start it here, or run `ollama serve`."
                    if s.installed else
                    f"Ollama is not installed on this Mac. It is a free download at {DOWNLOAD_PAGE}.")
    elif model and not s.has(model):
        s.reason = f"The server is running, and {model} is not downloaded yet."
    return s


def _log_tail(lines: int = 3) -> str:
    try:
        tail = LOGFILE.read_text(errors="replace").strip().splitlines()[-lines:]
    except OSError:
        return "nothing was written to the log"
    return " / ".join(t.strip() for t in tail) or "nothing was written to the log"


def start(url: str = DEFAULT_URL, timeout: float = START_TIMEOUT,
          on_line=None) -> tuple[Server, str]:
    """Start a server unless one is already answering. Returns (status, sentence).

    The child is detached into its own session. Without that, quitting the window
    that started it delivered the same interrupt to the server and took the model
    down with it, which is not what leaving it running means.
    """
    s = status(url)
    if s.running:
        return s, "A model server was already running, so nothing was started."
    if not s.installed:
        return s, s.reason or "The model runtime is not installed."

    HOME.mkdir(parents=True, exist_ok=True)
    log = LOGFILE.open("a")
    log.write(f"\n=== reflip started a server at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    log.flush()
    env = dict(os.environ)
    # Keep the requests the rewriter sends in flight together. The default is one,
    # which turns a four-way parallel rewrite back into a queue.
    env.setdefault("OLLAMA_NUM_PARALLEL", "4")
    env.setdefault("OLLAMA_KEEP_ALIVE", "10m")
    proc = subprocess.Popen([binary(), "serve"], stdout=log, stderr=subprocess.STDOUT,
                            env=env, start_new_session=True)
    PIDFILE.write_text(str(proc.pid))

    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            PIDFILE.unlink(missing_ok=True)
            return status(url), f"The server stopped as it started. Its last words: {_log_tail()}"
        s = status(url)
        if s.running:
            return s, f"The model server is up at {url}."
        if on_line:
            on_line("waiting for the server to answer")
        time.sleep(0.4)
    return status(url), f"The server did not answer within {timeout:.0f} seconds. See {LOGFILE}."


def stop(url: str = DEFAULT_URL, timeout: float = 10.0) -> tuple[Server, str]:
    """Stop the server, but only when we are the ones who started it."""
    pid = _our_pid()
    if pid is None:
        s = status(url)
        if s.running:
            return s, "That server was not started by reflip, so it was left running."
        return s, "No server was running."
    os.killpg(os.getpgid(pid), signal.SIGTERM)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.2)
    else:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    PIDFILE.unlink(missing_ok=True)
    return status(url), "The model server was stopped."


def pull(model: str, url: str = DEFAULT_URL, on_progress=None) -> tuple[bool, str]:
    """Download a model, reporting (status, completed, total) as it goes.

    Streamed over the server's own API rather than by running the runtime's pull
    command, so the same code works against a server on another machine and the
    progress arrives as numbers instead of as terminal escape sequences.
    """
    body = json.dumps({"model": model, "stream": True}).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + "/api/pull", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3600) as r:
            for raw in r:
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("error"):
                    return False, str(msg["error"])
                if on_progress:
                    on_progress(msg.get("status", ""), msg.get("completed"), msg.get("total"))
    except urllib.error.HTTPError as e:
        return False, f"The server refused the download: {e.code} {e.reason}"
    except (urllib.error.URLError, OSError) as e:
        return False, f"The download did not finish: {e}"
    return True, f"{model} is downloaded."


def warm(model: str, url: str = DEFAULT_URL, timeout: float = 300.0) -> tuple[bool, str]:
    """Load the model into memory so the first real request is not the slow one."""
    body = json.dumps({"model": model, "messages": [], "stream": False}).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            return True, f"{model} is loaded and ready."
    except urllib.error.HTTPError as e:
        return False, f"The server would not load {model}: {e.code} {e.reason}"
    except (urllib.error.URLError, OSError) as e:
        return False, f"The server would not load {model}: {e}"
