"""The `reflip rewrite` contract under failure: every documented exit code, and the
promise that stdout carries nothing but one parseable JSON object whenever `--json` is
given, including on every kind of failure. No network and no model: reflip.server is
replaced with a stand-in exactly as in test_agent.py.
"""
from __future__ import annotations

import io
import json
import sys

import pytest

from reflip import agent, cli
from reflip.transforms import TransformResult, register


class FakeServer:
    DEFAULT_URL = "http://localhost:11434"
    DEFAULT_MODEL = "test-model"

    def __init__(self, running=True, has_model=True, refuses=False):
        self.running = running
        self.has_model = has_model
        self.refuses = refuses  # simulate a connection actively refused

    class _S:
        def __init__(self, outer):
            self.url = FakeServer.DEFAULT_URL
            self.installed = True
            self.running = outer.running
            self.ours = False
            self.version = "9.9.9"
            self.models = [{"name": "test-model", "size": 1}] if outer.has_model else []
            self.loaded = []
            self.reason = None if outer.running else "The model server is not running."
            if outer.running and not outer.has_model:
                self.reason = "The server is running, and test-model is not downloaded yet."

        def has(self, model):
            return any(m["name"] == model for m in self.models)

        def to_dict(self):
            return {"url": self.url, "installed": self.installed, "running": self.running,
                    "ours": self.ours, "version": self.version, "reason": self.reason,
                    "models": self.models, "loaded": self.loaded}

    def status(self, url=DEFAULT_URL, model=None):
        return self._S(self)


@register("upper")
def _upper(text, opts):
    """A minimal real transform: uppercase every letter. Deterministic, no LLM."""
    return TransformResult(text=text.upper(), edits=len(text.split()))


@register("boom")
def _boom(text, opts):
    """A transform that raises something other than CliError, to probe what the CLI
    does with a genuinely unexpected failure (not one of the documented refusals)."""
    raise RuntimeError("this transform is broken")


@pytest.fixture
def fake(monkeypatch):
    f = FakeServer()
    monkeypatch.setattr(agent, "srv", f)
    monkeypatch.setattr(agent.srv, "DEFAULT_MODEL", "test-model", raising=False)
    return f


def run(argv, stdin=None):
    out, err = io.StringIO(), io.StringIO()
    old = sys.stdout, sys.stderr, sys.stdin
    sys.stdout, sys.stderr = out, err
    if stdin is not None:
        sys.stdin = io.StringIO(stdin)
    try:
        code = cli.main(argv)
    finally:
        sys.stdout, sys.stderr, sys.stdin = old
    return code, out.getvalue(), err.getvalue()


def assert_stdout_is_one_json_object_and_nothing_else(out: str) -> dict:
    """The documented contract: with --json, stdout is one parseable JSON object, no
    stray prose, no traceback text, nothing extra on another line."""
    lines = out.splitlines()
    assert len(lines) == 1, f"stdout must be exactly one line of JSON, got: {out!r}"
    d = json.loads(lines[0])  # raises if it is not valid JSON
    assert "v" in d
    return d


# --------------------------------------------------------------------------- file / stdin

def test_missing_file_exit_2_and_json_stdout_stays_parseable(fake):
    code, out, err = run(["rewrite", "/no/such/file/anywhere.txt", "--transform", "upper", "--json"])
    assert code == 2
    d = assert_stdout_is_one_json_object_and_nothing_else(out)
    assert d["ok"] is False and "no such file" in d["reason"]
    assert "Traceback" not in err


def test_missing_file_exit_2_without_json_no_traceback(fake):
    code, out, err = run(["rewrite", "/no/such/file/anywhere.txt", "--transform", "upper"])
    assert code == 2
    assert out == ""
    assert "no such file" in err
    assert "Traceback" not in err


def test_empty_stdin_succeeds(fake):
    code, out, err = run(["rewrite", "-", "--transform", "upper", "--json", "--no-coverage"], stdin="")
    assert code == 0
    d = json.loads(out)
    assert d["text"] == "" and d["words"] == 0 and d["edits"] == 0


def test_empty_stdin_without_json_writes_nothing_to_stdout(fake):
    code, out, err = run(["rewrite", "-", "--transform", "upper", "--no-coverage"], stdin="")
    assert code == 0
    assert out == ""


# --------------------------------------------------------------------------- unknown transform

def test_unknown_transform_exit_2_and_json_stdout_stays_parseable(fake):
    code, out, err = run(["rewrite", "-", "--transform", "not-a-real-transform", "--json"], stdin="hi")
    assert code == 2
    d = assert_stdout_is_one_json_object_and_nothing_else(out)
    assert d["ok"] is False
    assert "not-a-real-transform" in d["reason"]
    assert "Traceback" not in err


def test_unknown_transform_exit_2_without_json(fake):
    code, out, err = run(["rewrite", "-", "--transform", "not-a-real-transform"], stdin="hi")
    assert code == 2
    assert out == ""
    assert "not-a-real-transform" in err
    assert "Traceback" not in err


# --------------------------------------------------------------------------- workers

def test_workers_zero_falls_back_to_machine_default(fake, monkeypatch):
    from reflip import mac

    monkeypatch.setattr(agent, "snapshot", lambda: mac.Machine(workers=2, reasons=[]))
    code, out, _ = run(["rewrite", "-", "--transform", "upper", "--json", "--no-coverage",
                        "--workers", "0"], stdin="hello there")
    assert code == 0
    assert json.loads(out)["workers"] == 2


def test_workers_99_does_not_crash_on_a_small_text(fake):
    code, out, err = run(["rewrite", "-", "--transform", "upper", "--json", "--no-coverage",
                          "--workers", "99"], stdin="hello there")
    assert code == 0
    d = json.loads(out)
    assert d["workers"] == 99  # reported as asked; the pool itself caps at item count internally
    assert d["text"] == "HELLO THERE"


# --------------------------------------------------------------------------- server states

def test_server_refuses_connection_exit_1_sentence_no_traceback(fake):
    fake.running = False
    code, out, err = run(["rewrite", "-", "--transform", "paraphrase", "--json",
                          "--model", "test-model"], stdin="hello there")
    assert code == 1
    d = assert_stdout_is_one_json_object_and_nothing_else(out)
    assert d["ok"] is False
    assert d["reason"] and d["reason"].strip()
    assert "Traceback" not in err and "Traceback" not in out


def test_server_refuses_connection_without_json(fake):
    fake.running = False
    code, out, err = run(["rewrite", "-", "--transform", "paraphrase",
                          "--model", "test-model"], stdin="hello there")
    assert code == 1
    assert out == ""
    assert "error:" in err
    assert "Traceback" not in err


def test_model_not_downloaded_exit_1(fake):
    fake.has_model = False
    code, out, err = run(["rewrite", "-", "--transform", "paraphrase", "--json",
                          "--model", "test-model"], stdin="hello there")
    assert code == 1
    d = assert_stdout_is_one_json_object_and_nothing_else(out)
    assert d["ok"] is False and "not downloaded" in d["reason"]


def test_model_not_downloaded_without_json(fake):
    fake.has_model = False
    code, out, err = run(["rewrite", "-", "--transform", "paraphrase",
                          "--model", "test-model"], stdin="hello there")
    assert code == 1
    assert out == ""
    assert "not downloaded" in err


# --------------------------------------------------------------------------- success shape

def test_success_json_is_the_only_thing_on_stdout(fake):
    code, out, err = run(["rewrite", "-", "--transform", "upper", "--json", "--progress",
                          "--no-coverage"], stdin="hello world")
    assert code == 0
    d = assert_stdout_is_one_json_object_and_nothing_else(out)
    assert d["text"] == "HELLO WORLD"
    # progress lines went to stderr, never stdout, even with --progress
    for line in err.strip().splitlines():
        json.loads(line)  # every stderr line is its own valid JSON object too


def test_success_without_json_writes_text_then_report_to_stderr(fake):
    code, out, err = run(["rewrite", "-", "--transform", "upper", "--no-coverage"], stdin="hello world")
    assert code == 0
    assert out == "HELLO WORLD"
    assert "edits" in err


# --------------------------------------------------------------------------- unexpected failure

def test_transform_raising_a_plain_exception_does_not_crash_the_process(fake):
    """Not one of the documented refusals: cli.main's outermost catch-all must still turn
    it into an exit code and a one-line message rather than an unhandled traceback."""
    code, out, err = run(["rewrite", "-", "--transform", "boom", "--no-coverage"], stdin="hello")
    assert code == 1
    assert "Traceback" not in err
    assert "this transform is broken" in err
