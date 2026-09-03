"""Tests for reflip.server: the local model server, without any real process or socket.

`urllib.request.urlopen` is replaced with a small router keyed on the URL suffix,
`subprocess.run` / `Popen` and `shutil.which` are replaced with fakes, and every test
points PIDFILE/LOGFILE at a tmp_path so nothing here can touch ~/.reflip.
"""
from __future__ import annotations

import json
import signal
import urllib.error

import pytest

from reflip import server


# --------------------------------------------------------------------------- fakes

class FakeResponse:
    """Stands in for the context manager urlopen() returns for a plain GET."""

    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class FakeStream:
    """Stands in for the context manager urlopen() returns for the streaming /api/pull."""

    def __init__(self, lines: list[bytes]):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter(self._lines)


def router(*, version=None, tags=None, ps=None, fail=False):
    """A fake urlopen(url, timeout=...) that answers /api/version, /api/tags, /api/ps."""

    def fake_urlopen(url, timeout=None):
        if fail:
            raise urllib.error.URLError("connection refused")
        if url.endswith("/api/version"):
            return FakeResponse(version)
        if url.endswith("/api/tags"):
            return FakeResponse(tags if tags is not None else {"models": []})
        if url.endswith("/api/ps"):
            return FakeResponse(ps if ps is not None else {"models": []})
        raise AssertionError(f"unexpected url in test: {url}")

    return fake_urlopen


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """No test here may read or write the real ~/.reflip."""
    monkeypatch.setattr(server, "HOME", tmp_path)
    monkeypatch.setattr(server, "PIDFILE", tmp_path / "server.pid")
    monkeypatch.setattr(server, "LOGFILE", tmp_path / "server.log")
    return tmp_path


# --------------------------------------------------------------------------- binary()

def test_binary_found_on_path(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda name: "/opt/homebrew/bin/ollama")
    assert server.binary() == "/opt/homebrew/bin/ollama"


def test_binary_not_installed_anywhere(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda name: None)
    monkeypatch.setattr(server.os, "access", lambda p, m: False)
    assert server.binary() is None


def test_binary_falls_back_to_known_paths(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda name: None)

    def fake_access(p, m):
        return p == "/opt/homebrew/bin/ollama"

    monkeypatch.setattr(server.os, "access", fake_access)
    assert server.binary() == "/opt/homebrew/bin/ollama"


# --------------------------------------------------------------------------- status(): the four states

def test_status_not_installed(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda name: None)
    monkeypatch.setattr(server.os, "access", lambda p, m: False)
    monkeypatch.setattr(server.urllib.request, "urlopen", router(fail=True))
    s = server.status()
    assert s.installed is False and s.running is False
    assert "not installed" in s.reason and server.DOWNLOAD_PAGE in s.reason


def test_status_installed_but_not_running(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda name: "/opt/homebrew/bin/ollama")
    monkeypatch.setattr(server.urllib.request, "urlopen", router(fail=True))
    s = server.status()
    assert s.installed is True and s.running is False
    assert "ollama serve" in s.reason


def test_status_running_without_the_model(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda name: "/opt/homebrew/bin/ollama")
    fake = router(version={"version": "0.5.1"},
                 tags={"models": [{"name": "other:latest", "size": 123, "details": {"family": "x"}}]},
                 ps={"models": []})
    monkeypatch.setattr(server.urllib.request, "urlopen", fake)
    s = server.status(model="qwen3:4b-instruct-2507-q4_K_M")
    assert s.running is True
    assert s.has("qwen3:4b-instruct-2507-q4_K_M") is False
    assert "is not downloaded yet" in s.reason


def test_status_running_with_the_model_loaded(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda name: "/opt/homebrew/bin/ollama")
    model = "qwen3:4b-instruct-2507-q4_K_M"
    fake = router(version={"version": "0.5.1"},
                 tags={"models": [{"name": model, "size": 2600000000, "details": {"family": "qwen3"}}]},
                 ps={"models": [{"name": model}]})
    monkeypatch.setattr(server.urllib.request, "urlopen", fake)
    s = server.status(model=model)
    assert s.reason is None
    assert s.loaded == [model]
    assert s.models[0]["size"] == 2600000000


def test_status_has_matches_bare_name_without_tag(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda name: "/opt/homebrew/bin/ollama")
    fake = router(version={"version": "0.5.1"},
                 tags={"models": [{"name": "qwen3:4b-instruct-2507-q4_K_M", "size": 1}]}, ps={"models": []})
    monkeypatch.setattr(server.urllib.request, "urlopen", fake)
    s = server.status()
    assert s.has("qwen3") is True
    assert s.has("qwen3:8b") is False  # a different tag of the same family is not the same download


# --------------------------------------------------------------------------- _our_pid()

def test_our_pid_none_when_no_pidfile():
    assert server._our_pid() is None


def test_our_pid_dead_process_is_cleaned_up(monkeypatch):
    """Bug this guards: a stale pidfile from a crashed server must not be reported as ours
    forever, and must not be left on disk once we notice it is dead."""
    server.PIDFILE.write_text("424242")

    def fake_kill(pid, sig):
        raise ProcessLookupError(f"no such process: {pid}")

    monkeypatch.setattr(server.os, "kill", fake_kill)
    assert server._our_pid() is None
    assert not server.PIDFILE.exists()


def test_our_pid_alive_process_is_returned(monkeypatch):
    server.PIDFILE.write_text("555")
    monkeypatch.setattr(server.os, "kill", lambda pid, sig: None)  # alive: no exception
    assert server._our_pid() == 555


def test_our_pid_garbage_pidfile_is_ignored():
    server.PIDFILE.write_text("not-a-pid")
    assert server._our_pid() is None


# --------------------------------------------------------------------------- start()

def test_start_does_nothing_when_already_running(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda name: "/opt/homebrew/bin/ollama")
    monkeypatch.setattr(server.urllib.request, "urlopen",
                        router(version={"version": "1"}, tags={"models": []}, ps={"models": []}))
    s, msg = server.start()
    assert s.running is True
    assert msg == "A model server was already running, so nothing was started."


def test_start_refuses_when_runtime_is_not_installed(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda name: None)
    monkeypatch.setattr(server.os, "access", lambda p, m: False)
    monkeypatch.setattr(server.urllib.request, "urlopen", router(fail=True))
    s, msg = server.start()
    assert s.installed is False
    assert server.DOWNLOAD_PAGE in msg


def test_start_launches_and_waits_for_it_to_answer(monkeypatch):
    monkeypatch.setattr(server, "binary", lambda: "/opt/homebrew/bin/ollama")
    monkeypatch.setattr(server.time, "sleep", lambda s: None)

    calls = {"n": 0}
    running_after = 2  # status() reports running only from the third call on

    def fake_status(url=server.DEFAULT_URL, model=None):
        s = server.Server(url=url)
        s.installed = True
        s.running = calls["n"] >= running_after
        calls["n"] += 1
        return s

    monkeypatch.setattr(server, "status", fake_status)

    class FakeProc:
        pid = 4242

        def poll(self):
            return None  # still alive at every check

    monkeypatch.setattr(server.subprocess, "Popen", lambda *a, **kw: FakeProc())
    s, msg = server.start()
    assert "up at" in msg
    assert server.PIDFILE.read_text() == "4242"
    assert s.running is True


def test_start_reports_immediate_exit_with_log_tail(monkeypatch):
    monkeypatch.setattr(server, "binary", lambda: "/opt/homebrew/bin/ollama")
    monkeypatch.setattr(server, "status",
                        lambda url=server.DEFAULT_URL, model=None: server.Server(url=url, installed=True, running=False))
    monkeypatch.setattr(server, "_log_tail", lambda lines=3: "listen tcp 127.0.0.1:11434: address already in use")

    class FakeProc:
        pid = 55

        def poll(self):
            return 1  # already exited

    monkeypatch.setattr(server.subprocess, "Popen", lambda *a, **kw: FakeProc())
    s, msg = server.start()
    assert "stopped as it started" in msg
    assert "address already in use" in msg
    assert not server.PIDFILE.exists()


def test_start_sets_parallel_env_defaults(monkeypatch):
    """OLLAMA_NUM_PARALLEL must default to 4, or a parallel rewrite silently serialises."""
    monkeypatch.setattr(server, "binary", lambda: "/opt/homebrew/bin/ollama")
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    seen_env = {}

    def fake_status(url=server.DEFAULT_URL, model=None):
        s = server.Server(url=url)
        s.installed = True
        s.running = False  # never answers: start() must actually launch the process
        return s

    monkeypatch.setattr(server, "status", fake_status)

    class FakeProc:
        pid = 9

        def poll(self):
            return None

    def fake_popen(cmd, stdout, stderr, env, start_new_session):
        seen_env.update(env)
        return FakeProc()

    monkeypatch.setattr(server.subprocess, "Popen", fake_popen)
    server.start(timeout=0.05)  # short: it will time out waiting, that is not what is under test
    assert seen_env["OLLAMA_NUM_PARALLEL"] == "4"
    assert seen_env["OLLAMA_KEEP_ALIVE"] == "10m"


# --------------------------------------------------------------------------- stop()

def test_stop_leaves_a_foreign_server_running(monkeypatch):
    """No pidfile: this reflip did not start whatever is answering, so it must not touch it."""
    monkeypatch.setattr(server.shutil, "which", lambda name: "/opt/homebrew/bin/ollama")
    monkeypatch.setattr(server.urllib.request, "urlopen",
                        router(version={"version": "1"}, tags={"models": []}, ps={"models": []}))
    s, msg = server.stop()
    assert msg == "That server was not started by reflip, so it was left running."
    assert s.running is True


def test_stop_reports_nothing_running(monkeypatch):
    monkeypatch.setattr(server.urllib.request, "urlopen", router(fail=True))
    s, msg = server.stop()
    assert msg == "No server was running."


def test_stop_kills_the_server_it_started(monkeypatch):
    server.PIDFILE.write_text("777")
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    monkeypatch.setattr(server.os, "getpgid", lambda pid: pid)
    state = {"alive": True}
    killed = []

    def fake_kill(pid, sig):
        if sig == 0:
            if not state["alive"]:
                raise ProcessLookupError()
            return None
        killed.append(("kill", pid, sig))

    def fake_killpg(pgid, sig):
        killed.append(("killpg", pgid, sig))
        state["alive"] = False  # the process dies as soon as SIGTERM is sent

    monkeypatch.setattr(server.os, "kill", fake_kill)
    monkeypatch.setattr(server.os, "killpg", fake_killpg)
    monkeypatch.setattr(server.urllib.request, "urlopen", router(fail=True))
    s, msg = server.stop()
    assert msg == "The model server was stopped."
    assert ("killpg", 777, signal.SIGTERM) in killed
    assert not any(k[2] == signal.SIGKILL for k in killed), "a process that died must not also be SIGKILLed"
    assert not server.PIDFILE.exists()


def test_stop_sigkills_a_process_that_ignores_sigterm(monkeypatch):
    server.PIDFILE.write_text("778")
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    monkeypatch.setattr(server.os, "getpgid", lambda pid: pid)
    killed = []

    def fake_kill(pid, sig):
        killed.append(sig)
        return None  # os.kill(pid, 0) never raises: the process never dies on its own

    def fake_killpg(pgid, sig):
        killed.append(("pg", sig))

    monkeypatch.setattr(server.os, "kill", fake_kill)
    monkeypatch.setattr(server.os, "killpg", fake_killpg)
    monkeypatch.setattr(server.urllib.request, "urlopen", router(fail=True))
    s, msg = server.stop(timeout=0.01)
    assert ("pg", signal.SIGKILL) in killed


# --------------------------------------------------------------------------- pull()

def test_pull_streams_progress_then_errors_halfway(monkeypatch):
    lines = [
        json.dumps({"status": "pulling manifest", "completed": 10, "total": 100}).encode(),
        b"",  # a blank line, which real Ollama output includes: must be skipped, not crash
        json.dumps({"status": "pulling layer", "completed": 50, "total": 100}).encode(),
        json.dumps({"error": "disk full"}).encode(),
    ]
    monkeypatch.setattr(server.urllib.request, "urlopen", lambda req, timeout=None: FakeStream(lines))
    events = []
    ok, msg = server.pull("some-model", on_progress=lambda *a: events.append(a))
    assert ok is False
    assert msg == "disk full"
    assert events == [("pulling manifest", 10, 100), ("pulling layer", 50, 100)]


def test_pull_success_reports_done(monkeypatch):
    lines = [json.dumps({"status": "success", "completed": 100, "total": 100}).encode()]
    monkeypatch.setattr(server.urllib.request, "urlopen", lambda req, timeout=None: FakeStream(lines))
    ok, msg = server.pull("m")
    assert ok is True and "is downloaded" in msg


def test_pull_http_error_is_a_sentence(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError("url", 404, "not found", {}, None)

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)
    ok, msg = server.pull("m")
    assert ok is False and "404" in msg


def test_pull_network_error_is_a_sentence(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("connection reset")

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)
    ok, msg = server.pull("m")
    assert ok is False and "did not finish" in msg


def test_pull_tolerates_malformed_json_line(monkeypatch):
    lines = [b"not json at all", json.dumps({"status": "success"}).encode()]
    monkeypatch.setattr(server.urllib.request, "urlopen", lambda req, timeout=None: FakeStream(lines))
    events = []
    ok, msg = server.pull("m", on_progress=lambda *a: events.append(a))
    assert ok is True
    assert events == [("success", None, None)]


# --------------------------------------------------------------------------- warm()

def test_warm_success(monkeypatch):
    monkeypatch.setattr(server.urllib.request, "urlopen", lambda req, timeout=None: FakeResponse({}))
    ok, msg = server.warm("m")
    assert ok is True and "loaded and ready" in msg


def test_warm_http_error(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError("url", 500, "server error", {}, None)

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)
    ok, msg = server.warm("m")
    assert ok is False and "would not load" in msg and "500" in msg


def test_warm_connection_refused(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError(ConnectionRefusedError())

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)
    ok, msg = server.warm("m")
    assert ok is False and "would not load" in msg
