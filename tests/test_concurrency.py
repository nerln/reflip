"""Concurrency tests for reflip.transforms.llm: the thread pool that runs LLM blocks.

Every fake Chat here sleeps a little (so completion order can differ from submission
order) and records which thread it ran on, so the tests can tell "ran in parallel" from
"ran in the caller's own thread" by inspection rather than by timing alone.
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from reflip.transforms import Options
from reflip.transforms import llm


def _blocked_text(n: int) -> str:
    """n prose paragraphs, each its own block for paraphrase (blank-line separated)."""
    return "\n\n".join(f"Paragraph number {k} has several words in it worth rewriting." for k in range(n))


# --------------------------------------------------------------------------- ordering

def test_results_come_back_in_input_order_despite_reversed_completion(monkeypatch):
    """Block 0 sleeps longest, the last block sleeps almost nothing: if completion order
    leaked into the output, block 0's text would land somewhere other than first."""
    n = 6
    text = _blocked_text(n)
    seen_threads: list[int] = []
    lock = threading.Lock()

    def complete(self, messages, **kw):
        block = messages[-1]["content"].split("TEXT:\n", 1)[1]
        k = int(block.split()[2])  # "Paragraph number K has..."
        time.sleep(0.03 * (n - k))  # block 0 finishes last, block n-1 finishes first
        with lock:
            seen_threads.append(threading.get_ident())
        return json.dumps({"text": f"REWRITTEN-{k} " + block}), {"prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(llm.Chat, "complete", complete)
    res = llm.paraphrase(text, Options(workers=n))
    for k in range(n):
        assert f"REWRITTEN-{k} " in res.text
    # the paragraphs must still be in their original 0..n-1 order in the joined text
    positions = [res.text.index(f"REWRITTEN-{k} ") for k in range(n)]
    assert positions == sorted(positions)
    assert len(set(seen_threads)) > 1, "the pool must actually have used more than one thread"


def test_workers_one_is_truly_sequential(monkeypatch):
    """No thread pool at all when workers=1: every block runs on the calling thread, one
    fully completes before the next starts."""
    n = 5
    text = _blocked_text(n)
    caller_thread = threading.get_ident()
    events: list[tuple[str, int, int]] = []  # ("start"|"end", block, ident)

    def complete(self, messages, **kw):
        block = messages[-1]["content"].split("TEXT:\n", 1)[1]
        k = int(block.split()[2])
        events.append(("start", k, threading.get_ident()))
        time.sleep(0.01)
        events.append(("end", k, threading.get_ident()))
        return json.dumps({"text": block}), {"prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(llm.Chat, "complete", complete)
    llm.paraphrase(text, Options(workers=1))
    assert all(ident == caller_thread for _, _, ident in events)
    # strictly alternating start/end pairs in block order: no interleaving is possible
    # with a single worker, so this is really testing that no pool was spun up at all.
    expected = []
    for k in range(n):
        expected.append(("start", k))
        expected.append(("end", k))
    assert [(kind, k) for kind, k, _ in events] == expected


def test_workers_above_one_uses_a_pool_of_that_size_at_most(monkeypatch):
    n = 10
    text = _blocked_text(n)
    in_flight = {"count": 0, "max": 0}
    lock = threading.Lock()

    def complete(self, messages, **kw):
        with lock:
            in_flight["count"] += 1
            in_flight["max"] = max(in_flight["max"], in_flight["count"])
        time.sleep(0.02)
        with lock:
            in_flight["count"] -= 1
        return json.dumps({"text": messages[-1]["content"].split("TEXT:\n", 1)[1]}), \
            {"prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(llm.Chat, "complete", complete)
    llm.paraphrase(text, Options(workers=3))
    assert in_flight["max"] <= 3
    assert in_flight["max"] > 1, "workers=3 that never overlaps is not actually parallel"


# --------------------------------------------------------------------------- exceptions

def test_worker_exception_does_not_corrupt_other_workers_results(monkeypatch):
    """One block's fake Chat call raises; the blocks computed by other threads, running
    concurrently, must keep their own correct values rather than seeing a torn or
    partially-overwritten one from the failing thread."""
    n = 20
    computed: list[object] = [None] * n
    failing_index = n // 2

    def fn(i):
        time.sleep(0.005 if i % 2 else 0.015)
        value = {"i": i, "tag": f"value-{i}"}
        computed[i] = value
        if i == failing_index:
            raise RuntimeError(f"synthetic failure at {i}")
        return value

    opts = Options(workers=8)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        llm._map_ordered(fn, list(range(n)), opts, "phase")
    for i, v in enumerate(computed):
        if v is not None:
            assert v == {"i": i, "tag": f"value-{i}"}, f"slot {i} was corrupted"


def test_map_ordered_single_worker_exception_stops_cleanly(monkeypatch):
    def fn(i):
        if i == 2:
            raise ValueError("boom")
        return i

    opts = Options(workers=1)
    with pytest.raises(ValueError, match="boom"):
        llm._map_ordered(fn, [0, 1, 2, 3, 4], opts, "phase")


# --------------------------------------------------------------------------- token counting

def test_token_counting_exact_under_eight_concurrent_workers():
    """Run 20 times: concurrent _Usage.add() calls must sum to exactly the right totals,
    never off by one from a lost update."""
    for trial in range(20):
        acc = llm._Usage()
        messages = [{"role": "user", "content": "x" * 4}]  # estimate_tokens("xxxx") == 1

        def worker(k):
            acc.add(messages, "y" * 4 * (k + 1), {"prompt_tokens": 10 + k, "completion_tokens": 5 + k})

        threads = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert acc.calls == 8, f"trial {trial}: lost a call"
        assert acc.prompt == sum(10 + k for k in range(8)), f"trial {trial}: prompt tokens off"
        assert acc.completion == sum(5 + k for k in range(8)), f"trial {trial}: completion tokens off"


def test_token_counting_exact_end_to_end_paraphrase(monkeypatch):
    """Same claim, exercised through the real code path: paraphrase() with 8 workers over
    many blocks, usage summed from real (fake) API replies."""
    n = 24
    text = _blocked_text(n)

    def complete(self, messages, **kw):
        time.sleep(0.002)
        return json.dumps({"text": messages[-1]["content"].split("TEXT:\n", 1)[1]}), \
            {"prompt_tokens": 13, "completion_tokens": 7}

    monkeypatch.setattr(llm.Chat, "complete", complete)
    for trial in range(20):
        res = llm.paraphrase(text, Options(workers=8))
        assert res.llm_calls == n, f"trial {trial}: {res.llm_calls} calls, expected {n}"
        assert res.prompt_tokens == 13 * n, f"trial {trial}: prompt token total off"
        assert res.completion_tokens == 7 * n, f"trial {trial}: completion token total off"


# --------------------------------------------------------------------------- _Counters

def test_counters_never_lose_an_increment_under_load():
    for trial in range(10):
        c = llm._Counters({"n": 0})
        threads = [threading.Thread(target=lambda: [c.bump("n") for _ in range(250)]) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert c["n"] == 2000, f"trial {trial}: lost increments"


def test_counters_least_is_also_thread_safe():
    c = llm._Counters({})

    def worker(v):
        for _ in range(100):
            c.least("m", v)

    threads = [threading.Thread(target=worker, args=(v,)) for v in (0.9, 0.5, 0.7, 0.3, 0.95)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert c["m"] == 0.3
