"""The machine-facing command line: the JSON shapes the window and other programs read.

No model is called and no server is contacted: the server module is replaced by a stand-in,
because a test that needs a running model server is a test that fails on someone else's Mac.
"""
import io
import json
import sys

import pytest

from reflip import agent, cli
from reflip.transforms import Options, TransformResult, register


class FakeServer:
    """Stands in for reflip.server: same three functions, no network."""

    DEFAULT_URL = "http://localhost:11434"
    DEFAULT_MODEL = "test-model"

    def __init__(self, running=True, has_model=True):
        self.running = running
        self.has_model = has_model
        self.calls = []

    class _S:
        def __init__(self, outer):
            self.url = FakeServer.DEFAULT_URL
            self.installed = True
            self.running = outer.running
            self.ours = False
            self.version = "9.9.9"
            self.models = [{"name": "test-model", "size": 2600000000, "family": "test"}] if outer.has_model else []
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

    def start(self, url=DEFAULT_URL, **kw):
        self.calls.append("start")
        self.running = True
        return self._S(self), "The model server is up at http://localhost:11434."

    def stop(self, url=DEFAULT_URL, **kw):
        self.calls.append("stop")
        self.running = False
        return self._S(self), "The model server was stopped."

    def warm(self, model, url=DEFAULT_URL, **kw):
        return True, f"{model} is loaded and ready."

    def pull(self, model, url=DEFAULT_URL, on_progress=None):
        for i in (1, 2):
            on_progress("pulling manifest", i * 50, 100)
        return True, f"{model} is downloaded."


@register("echo")
def _echo(text, opts):
    """A transform that changes one word, so the numbers in the result are not all zero."""
    if opts.on_progress:
        opts.on_progress("Rewriting", 1, 2, "Rewriting: 1 of 2")
    return TransformResult(text=text.replace("lighthouse", "beacon"), edits=1,
                           llm_calls=2, prompt_tokens=100, completion_tokens=20,
                           notes={"workers": opts.workers})


TEXT = "The lighthouse keeper had lived alone on the rock for eleven winters."


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


def test_server_status_json_shape(fake):
    code, out, err = run(["server", "status", "--json", "--model", "test-model"])
    assert code == 0
    d = json.loads(out)
    assert d["v"] == 1 and d["ready"] is True and d["reason"] is None
    assert d["server"]["running"] is True and d["server"]["version"] == "9.9.9"
    assert d["server"]["models"][0]["name"] == "test-model"
    for key in ("total", "free_for_work", "pressure", "cores", "workers", "reasons"):
        assert key in d["machine"]
    assert isinstance(d["machine"]["reasons"], list)


def test_server_not_running_is_a_sentence_and_exit_one(fake):
    fake.running = False
    code, out, _ = run(["server", "status", "--json", "--model", "test-model"])
    assert code == 1
    d = json.loads(out)
    assert d["ready"] is False
    assert d["reason"].endswith(".") and "not running" in d["reason"]


def test_server_start_and_stop_report_what_happened(fake):
    fake.running = False
    code, out, _ = run(["server", "start", "--json", "--model", "test-model"])
    assert code == 0 and fake.calls == ["start"]
    assert "up at" in json.loads(out)["message"]
    code, out, _ = run(["server", "stop", "--json", "--model", "test-model"])
    assert fake.calls == ["start", "stop"]
    assert json.loads(out)["message"] == "The model server was stopped."


def test_pull_streams_lines_then_a_done(fake):
    code, out, _ = run(["pull", "test-model", "--json"])
    assert code == 0
    lines = [json.loads(x) for x in out.strip().splitlines()]
    assert [x["event"] for x in lines] == ["pull", "pull", "done"]
    assert lines[0]["completed"] == 50 and lines[0]["total"] == 100
    assert lines[-1]["ok"] is True


def test_rewrite_result_object(fake):
    code, out, err = run(["rewrite", "-", "--transform", "echo", "--json", "--progress",
                          "--no-coverage", "--model", "test-model", "--workers", "3"], stdin=TEXT)
    assert code == 0
    d = json.loads(out)
    assert d["v"] == 1 and d["transform"] == "echo" and d["model"] == "test-model"
    assert d["text"] == TEXT.replace("lighthouse", "beacon")
    assert d["words"] == 12 and d["edits"] == 1 and 0 < d["edit_ratio"] < 0.2
    assert d["coverage"] is None and d["coverage_note"]
    assert d["llm_calls"] == 2 and d["prompt_tokens"] == 100 and d["completion_tokens"] == 20
    assert d["workers"] == 3 and d["notes"]["workers"] == 3
    assert isinstance(d["seconds"], float)

    events = [json.loads(x) for x in err.strip().splitlines()]
    assert all(e["event"] == "progress" for e in events)
    assert {"phase", "done", "total", "message"} <= set(events[0])
    assert events[-1]["phase"] == "Done"


def test_rewrite_refuses_when_the_model_is_missing(fake):
    fake.has_model = False
    code, out, err = run(["rewrite", "-", "--transform", "paraphrase", "--json", "--progress",
                          "--model", "test-model"], stdin=TEXT)
    assert code == 1
    d = json.loads(out)
    assert d["ok"] is False and "not downloaded" in d["reason"]
    assert json.loads(err.strip().splitlines()[-1])["event"] == "error"


def test_rules_transform_needs_no_server(fake):
    fake.running = False
    code, out, _ = run(["rewrite", "-", "--transform", "rules", "--json", "--no-coverage"],
                       stdin="Don't use the color red in order to show it.")
    assert code == 0
    d = json.loads(out)
    assert "Do not" in d["text"] and "colour" in d["text"]
    assert d["llm_calls"] == 0


def test_rewrite_without_json_writes_the_text_and_a_report(fake):
    code, out, err = run(["rewrite", "-", "--transform", "echo", "--no-coverage",
                          "--model", "test-model"], stdin=TEXT)
    assert code == 0
    assert out == TEXT.replace("lighthouse", "beacon")
    assert "1 edits" in err and "at a time" in err


def test_workers_default_comes_from_the_machine(fake, monkeypatch):
    from reflip import mac

    monkeypatch.setattr(agent, "snapshot", lambda: mac.Machine(workers=2, reasons=[]))
    code, out, _ = run(["rewrite", "-", "--transform", "echo", "--json", "--no-coverage",
                        "--model", "test-model"], stdin=TEXT)
    assert json.loads(out)["workers"] == 2


def test_coverage_note_when_transformers_is_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "transformers", None)
    tok, note = agent._tokenizer("whatever", explicit=False)
    assert tok is None and "transformers" in note


def test_parallel_map_keeps_order_and_counts(monkeypatch):
    from reflip.transforms import llm

    seen = []
    opts = Options(workers=4, on_progress=lambda *a: seen.append(a))
    out = llm._map_ordered(lambda i: i * 2, list(range(10)), opts, "Rewriting")
    assert out == [i * 2 for i in range(10)]
    assert seen[0][:3] == ("Rewriting", 0, 10)
    assert seen[-1][:3] == ("Rewriting", 10, 10)


def test_parallel_counters_do_not_lose_increments():
    import threading

    from reflip.transforms.llm import _Counters

    c = _Counters({"n": 0})
    threads = [threading.Thread(target=lambda: [c.bump("n") for _ in range(200)]) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert c["n"] == 1600
