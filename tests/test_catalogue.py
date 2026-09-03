"""Tests for reflip.catalogue: refusal, the static recommendation list, and Hugging Face
search/quantisations, all without a real network call.
"""
from __future__ import annotations

import json
import urllib.error

import pytest

from reflip import catalogue


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


# --------------------------------------------------------------------------- refusal()

@pytest.mark.parametrize("ref", [
    "anthropic/claude-3-haiku",
    "claude-3-5-sonnet",
    "some-org/Claude-Instant",
    "google/gemini-1.5-pro",
    "Gemini-nano",
])
def test_refusal_flags_watermarking_models(ref):
    reason = catalogue.refusal(ref)
    assert reason is not None and reason.strip().endswith(".")


@pytest.mark.parametrize("ref", [
    "qwen3:4b-instruct-2507-q4_K_M",
    "gemma3:4b",  # Gemma's open weights: explicitly not refused, see the module docstring
    "hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M",
    "llama3.2:3b",
])
def test_refusal_does_not_flag_ordinary_models(ref):
    assert catalogue.refusal(ref) is None


# --------------------------------------------------------------------------- recommended()

def test_recommended_marks_exact_matches_installed():
    rows = catalogue.recommended({"qwen3:4b-instruct-2507-q4_K_M"})
    by_ref = {r["ref"]: r for r in rows}
    assert by_ref["qwen3:4b-instruct-2507-q4_K_M"]["installed"] is True
    assert by_ref["gemma3:4b"]["installed"] is False


def test_recommended_matches_bare_name_across_tags():
    rows = catalogue.recommended({"qwen3"})
    by_ref = {r["ref"]: r for r in rows}
    assert by_ref["qwen3:4b-instruct-2507-q4_K_M"]["installed"] is True
    assert by_ref["qwen3:8b"]["installed"] is True
    assert by_ref["qwen3:4b-instruct-2507-q8_0"]["installed"] is True


def test_recommended_with_no_installed_set():
    rows = catalogue.recommended()
    assert all(r["installed"] is False for r in rows)
    assert all(r["watch_out"] for r in rows), "every entry must carry a caveat, per the docstring"


def test_recommended_never_includes_a_refused_model():
    rows = catalogue.recommended()
    for r in rows:
        assert catalogue.refusal(r["ref"]) is None, r["ref"]


# --------------------------------------------------------------------------- search()

def test_search_returns_gguf_results(monkeypatch):
    payload = [{"id": "bartowski/Foo-Instruct-GGUF", "downloads": 500, "likes": 10, "gated": False}]
    monkeypatch.setattr(catalogue.urllib.request, "urlopen", lambda url, timeout=None: FakeResponse(payload))
    results, note = catalogue.search("foo")
    assert len(results) == 1
    r = results[0]
    assert r["ref"] == "hf.co/bartowski/Foo-Instruct-GGUF:Q4_K_M"
    assert r["repo"] == "bartowski/Foo-Instruct-GGUF"
    assert r["refused"] is None
    assert note is not None and "not recommendations" in note


def test_search_flags_a_watermarking_repo_but_still_lists_it(monkeypatch):
    payload = [{"id": "anthropic/claude-oss-weights", "downloads": 1}]
    monkeypatch.setattr(catalogue.urllib.request, "urlopen", lambda url, timeout=None: FakeResponse(payload))
    results, _ = catalogue.search("claude")
    assert len(results) == 1
    assert results[0]["refused"] is not None  # listed, but marked so a caller can grey it out


def test_search_network_failure_is_a_sentence_not_an_exception(monkeypatch):
    def fake_urlopen(url, timeout=None):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(catalogue.urllib.request, "urlopen", fake_urlopen)
    results, note = catalogue.search("foo")
    assert results == []
    assert note is not None and "could not be reached" in note


def test_search_empty_results_no_note(monkeypatch):
    monkeypatch.setattr(catalogue.urllib.request, "urlopen", lambda url, timeout=None: FakeResponse([]))
    results, note = catalogue.search("zzz-nothing-matches-zzz")
    assert results == [] and note is None


def test_search_limit_is_clamped(monkeypatch):
    seen = {}

    def fake_urlopen(url, timeout=None):
        seen["url"] = url
        return FakeResponse([])

    monkeypatch.setattr(catalogue.urllib.request, "urlopen", fake_urlopen)
    catalogue.search("x", limit=500)
    assert "limit=50" in seen["url"]  # clamped to the API's actual ceiling
    catalogue.search("x", limit=0)
    assert "limit=1" in seen["url"]


# --------------------------------------------------------------------------- quantisations()

def test_quantisations_lists_gguf_tags(monkeypatch):
    payload = {"siblings": [
        {"rfilename": "model-Q4_K_M.gguf"}, {"rfilename": "model-Q8_0.gguf"},
        {"rfilename": "README.md"}, {"rfilename": "model-Q4_K_M.gguf"},  # duplicate: must dedupe
    ]}
    monkeypatch.setattr(catalogue.urllib.request, "urlopen", lambda url, timeout=None: FakeResponse(payload))
    tags, note = catalogue.quantisations("some/repo")
    assert tags == ["Q4_K_M", "Q8_0"]
    assert note is None


def test_quantisations_no_gguf_files(monkeypatch):
    monkeypatch.setattr(catalogue.urllib.request, "urlopen",
                        lambda url, timeout=None: FakeResponse({"siblings": [{"rfilename": "README.md"}]}))
    tags, note = catalogue.quantisations("some/repo")
    assert tags == [] and "no GGUF files" in note


def test_quantisations_repo_not_found(monkeypatch):
    def fake_urlopen(url, timeout=None):
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    monkeypatch.setattr(catalogue.urllib.request, "urlopen", fake_urlopen)
    tags, note = catalogue.quantisations("nonexistent/repo")
    assert tags == [] and "could not be read" in note
