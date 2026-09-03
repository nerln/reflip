"""Tests for reflip.transforms.llm with a fake chat backend (no model, no network).

The fake answers any ⟦n|orig⟧ slot with orig + "x" and rewrites a paraphrase block by
suffixing every word with "x", so every test can check byte-exact layout preservation.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import types

import pytest
import requests

from reflip.transforms import Options
from reflip.words import WORD_RE, words
import reflip.transforms.llm as llm

def sfx(o, c):
    return " ".join(w + c for w in o.split())


SLOT = re.compile(r"⟦(\d+)\|([^⟧]*)⟧")
USAGE = {"prompt_tokens": 100, "completion_tokens": 20}

PROSE = (
    "The lighthouse keeper had lived alone on the rock for eleven winters, and the letters "
    "that reached him were few. Most of them came from the harbour office, printed on thin "
    "grey paper that curled in the damp air. This one was different: the envelope was "
    "heavy, cream coloured, and addressed in a hand he had not seen since he was a boy."
)

MARKDOWN = """# A short guide

The quick brown fox jumps over the lazy dog. See https://example.com/a?b=1 and write to me@site.org today.
Use `pip install reflip` to begin, then run it: the tool works well and was tested in 2008.

```py
print("do not touch this text at all")
```

- first item of the list
- second item, with more words here
    indented continuation line stays put

> a quoted line with several words in it
"""


# ----------------------------------------------------------------------------- helpers

def fake_complete(calls: list | None = None, drop_first: bool = False, drop_all: bool = False):
    """Build a Chat.complete replacement. `drop_first`: omit every other slot on the first call."""
    calls = calls if calls is not None else []

    def complete(self, messages, **kw):
        user = messages[-1]["content"]
        calls.append(user)
        if "⟦" in user:
            found = SLOT.findall(user)
            if drop_all:
                found = []
            elif drop_first and len(calls) == 1:
                found = found[::2]
            return json.dumps({n: " ".join(w + "x" for w in o.split()) for n, o in found}), dict(USAGE)
        block = user.split("TEXT:\n", 1)[1]
        return json.dumps({"text": WORD_RE.sub(lambda m: m.group(0) + "x", block)}), dict(USAGE)

    complete.calls = calls
    return complete


def unedited_flags(orig: str, new: str) -> list[bool]:
    """Per word of `new`: True if it sits in an 'equal' block against `orig` (difflib on words)."""
    a = [w.text.lower() for w in words(orig)]
    b = [w.text.lower() for w in words(new)]
    flags = [False] * len(b)
    for _, j, n in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_matching_blocks():
        for t in range(j, j + n):
            flags[t] = True
    return flags


def max_run(flags: list[bool]) -> int:
    best = run = 0
    for f in flags:
        run = run + 1 if f else 0
        best = max(best, run)
    return best


def skeleton(text: str) -> str:
    """Everything that is not a word: must survive infill byte-for-byte."""
    return WORD_RE.sub("", text)


# ----------------------------------------------------------------------------- parse_json / tokens

@pytest.mark.parametrize("raw", [
    '{"1": "a", "2": "b"}',
    '<think>\nlet me see...\n</think>\n{"1": "a", "2": "b"}',
    '```json\n{"1": "a", "2": "b"}\n```',
    'Sure! Here is the mapping:\n{"1": "a", "2": "b"}\nHope this helps.',
    '<think>x</think>Here: ```\n{"1": "a", "2": "b"}```',
    '<think>unterminated {"9": "z"}',
])
def test_parse_json_variants(raw):
    if raw.startswith("<think>unterminated"):
        with pytest.raises(ValueError):
            llm.parse_json(raw)
        return
    assert llm.parse_json(raw) == {"1": "a", "2": "b"}


def test_parse_json_array_and_nested_braces():
    assert llm.parse_json('text [{"n": 1, "replacement": "x}"}] more') == [{"n": 1, "replacement": "x}"}]
    with pytest.raises(ValueError):
        llm.parse_json("no json here")


def test_estimate_tokens():
    assert llm.estimate_tokens("") == 0
    assert llm.estimate_tokens("abcd" * 10) == 10
    assert llm.estimate_tokens("abcde") == 2


# ----------------------------------------------------------------------------- Chat

def test_chat_unreachable_names_base_url(monkeypatch):
    monkeypatch.setattr(llm, "_BACKOFF", 0.0)
    sock_url = "http://127.0.0.1:9"  # discard port: connection refused at once
    chat = llm.Chat(sock_url, "k", "m", timeout=2)
    with pytest.raises(llm.ChatError) as ei:
        chat.complete([{"role": "user", "content": "hi"}])
    assert sock_url in str(ei.value)


class _Resp:
    def __init__(self, status, payload=None, text="err"):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def test_chat_retries_on_5xx_then_returns_usage(monkeypatch):
    monkeypatch.setattr(llm, "_BACKOFF", 0.0)
    sent: list[dict] = []
    answers = [
        _Resp(503),
        _Resp(200, {"choices": [{"message": {"content": '{"1":"a"}'}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3}}),
    ]

    def post(self, url, json=None, headers=None, timeout=None):
        sent.append(json)
        return answers.pop(0)

    monkeypatch.setattr(requests.Session, "post", post)
    chat = llm.Chat("http://x/v1/", "key", "model-z", timeout=1)
    content, usage = chat.complete([{"role": "user", "content": "q"}], json_mode=True, seed=4, max_tokens=9)
    assert content == '{"1":"a"}'
    assert usage == {"prompt_tokens": 7, "completion_tokens": 3}
    assert len(sent) == 2
    assert sent[0]["response_format"] == {"type": "json_object"}
    assert sent[0]["seed"] == 4 and sent[0]["max_tokens"] == 9 and sent[0]["model"] == "model-z"


def test_chat_usage_missing_is_zero_and_4xx_is_not_retried(monkeypatch):
    monkeypatch.setattr(llm, "_BACKOFF", 0.0)
    n = {"posts": 0}

    def post(self, url, **kw):
        n["posts"] += 1
        if n["posts"] == 1:
            return _Resp(200, {"choices": [{"message": {"content": "hi"}}]})
        return _Resp(404, text='{"error": "model not found"}')

    monkeypatch.setattr(requests.Session, "post", post)
    chat = llm.Chat("http://x/v1", "key", "m")
    assert chat.complete([]) == ("hi", {"prompt_tokens": 0, "completion_tokens": 0})
    with pytest.raises(llm.ChatError, match="model not found"):
        chat.complete([])
    assert n["posts"] == 2


# ----------------------------------------------------------------------------- infill

def test_infill_prose_stride_and_tokens(monkeypatch):
    fake = fake_complete()
    monkeypatch.setattr(llm.Chat, "complete", fake)
    stride = 3
    res = llm.infill(PROSE, Options(stride=stride))
    flags = unedited_flags(PROSE, res.text)
    assert max_run(flags) < stride, "every window of `stride` words must contain an edit"
    assert res.edits == res.notes["slots"] <= flags.count(False)
    assert res.notes["unfilled"] == 0
    assert res.llm_calls == len(fake.calls) == 1
    assert res.prompt_tokens == 100 and res.completion_tokens == 20
    assert "tokens_estimated" not in res.notes
    # every slot got exactly orig + "x" and nothing else moved
    assert skeleton(res.text) == skeleton(PROSE)
    for n, orig in SLOT.findall(fake.calls[0]):
        assert sfx(orig, "x") in res.text


def test_infill_preserves_layout_and_protected_spans(monkeypatch):
    fake = fake_complete()
    monkeypatch.setattr(llm.Chat, "complete", fake)
    res = llm.infill(MARKDOWN, Options(stride=3))
    assert skeleton(res.text) == skeleton(MARKDOWN)
    assert res.text.count("\n") == MARKDOWN.count("\n")
    for untouched in ('print("do not touch this text at all")', "https://example.com/a?b=1",
                      "me@site.org", "`pip install reflip`", "2008", "\n- ", "\n> ", "\n    indented"):
        assert untouched in res.text
    assert res.notes["skipped_protected"] > 0
    assert res.edits > 0 and res.notes["unfilled"] == 0
    # the prose after the code block was still covered
    tail = res.text.split("```\n\n", 1)[1]
    assert "x" in tail and max_run(unedited_flags(MARKDOWN.split("```\n\n", 1)[1], tail)) < 3


def test_infill_span_two_never_crosses_newline_or_punctuation(monkeypatch):
    fake = fake_complete()
    monkeypatch.setattr(llm.Chat, "complete", fake)
    text = "one two\nthree four, five six. seven eight nine ten"
    res = llm.infill(text, Options(stride=2, span=2))
    originals = [o for _, o in SLOT.findall(fake.calls[0])]
    assert originals, "slots were sent"
    for o in originals:
        assert "\n" not in o and "," not in o and "." not in o
        assert len(o.split()) <= 2
    assert any(len(o.split()) == 2 for o in originals)
    assert res.notes["span"] == 2
    assert skeleton(res.text) == skeleton(text)


def test_infill_retries_missing_slots_once(monkeypatch):
    fake = fake_complete(drop_first=True)
    monkeypatch.setattr(llm.Chat, "complete", fake)
    res = llm.infill(PROSE, Options(stride=3))
    assert len(fake.calls) == 2
    first = {n for n, _ in SLOT.findall(fake.calls[0])}
    second = {n for n, _ in SLOT.findall(fake.calls[1])}
    assert second and second < first, "the follow-up carries only the missing slots"
    assert "still need a replacement" in fake.calls[1]
    assert res.notes["unfilled"] == 0 and res.notes["retried"] == len(second)
    assert res.edits == res.notes["slots"]
    assert max_run(unedited_flags(PROSE, res.text)) < 3
    assert res.prompt_tokens == 200 and res.llm_calls == 2


def test_infill_unfilled_keeps_original(monkeypatch):
    fake = fake_complete(drop_all=True)
    monkeypatch.setattr(llm.Chat, "complete", fake)
    res = llm.infill(PROSE, Options(stride=3))
    assert res.text == PROSE
    assert res.edits == 0 and res.notes["unfilled"] == res.notes["slots"] > 0
    assert len(fake.calls) == 2


def test_infill_rejects_bad_fills_and_normalises_keys(monkeypatch):
    def complete(self, messages, **kw):
        found = SLOT.findall(messages[-1]["content"])
        reply = {}
        for k, (n, o) in enumerate(found):
            mode = k % 6
            if mode == 0:
                reply[n] = o.upper()                # identical (case-insensitive) -> invalid
            elif mode == 1:
                reply[n] = "new\nline"              # newline -> invalid
            elif mode == 2:
                reply[n] = "quoted 'ok'"            # inner quotes are fine, brackets are not
            elif mode == 3:
                reply[f"slot {n}"] = '"' + sfx(o, "y") + '"'      # key with prose, value in quotes -> accepted  # stylecheck: allow, test data for the rule that removes it
            elif mode == 4:
                reply[n] = {"replacement": sfx(o, "z")}  # nested object -> accepted
            else:
                reply[n] = "a b c d e"              # too long -> invalid
        return json.dumps(reply), dict(USAGE)

    monkeypatch.setattr(llm.Chat, "complete", complete)
    monkeypatch.setattr(llm, "_RETRY_UNFILLED", False)
    res = llm.infill(PROSE, Options(stride=2))
    slots = res.notes["slots"]
    expected_ok = sum(1 for k in range(slots) if k % 6 in (2, 3, 4))
    assert res.edits == expected_ok
    assert res.notes["unfilled"] == slots - expected_ok
    assert "'" in res.text and '"' not in res.text


def test_infill_case_follows_original(monkeypatch):
    def complete(self, messages, **kw):
        found = SLOT.findall(messages[-1]["content"])
        return json.dumps({n: ("ZEBRA" if o[0].islower() else "zebra") for n, o in found}), dict(USAGE)

    monkeypatch.setattr(llm.Chat, "complete", complete)
    res = llm.infill("Alpha beta gamma. Delta epsilon zeta.", Options(stride=2))
    assert "ZEBRA" not in res.text
    assert res.text.startswith("Zebra ") or " zebra" in res.text


def test_infill_chunks_long_text_globally_numbered(monkeypatch):
    fake = fake_complete()
    monkeypatch.setattr(llm.Chat, "complete", fake)
    text = "\n\n".join(f"Paragraph {k}. " + PROSE for k in range(6))  # ~370 words, > 60 slots
    res = llm.infill(text, Options(stride=3))
    assert len(fake.calls) >= 2 and res.notes["chunks"] == len(fake.calls)
    seen: list[int] = []
    for call in fake.calls:
        ns = [int(n) for n, _ in SLOT.findall(call)]
        assert len(ns) <= llm.MAX_SLOTS_PER_REQUEST
        assert ns == sorted(ns)
        seen.extend(ns)
    assert seen == list(range(1, res.notes["slots"] + 1))
    assert res.notes["unfilled"] == 0
    assert res.text.count("\n\n") == text.count("\n\n")


def test_infill_estimates_tokens_when_usage_missing(monkeypatch):
    def complete(self, messages, **kw):
        found = SLOT.findall(messages[-1]["content"])
        return json.dumps({n: o + "x" for n, o in found}), {"prompt_tokens": 0, "completion_tokens": 0}

    monkeypatch.setattr(llm.Chat, "complete", complete)
    res = llm.infill(PROSE, Options(stride=3))
    assert res.notes["tokens_estimated"] is True
    assert res.prompt_tokens > 0 and res.completion_tokens > 0


def test_infill_empty_text_makes_no_call(monkeypatch):
    fake = fake_complete()
    monkeypatch.setattr(llm.Chat, "complete", fake)
    res = llm.infill("", Options())
    assert res.text == "" and res.edits == 0 and res.llm_calls == 0


# ----------------------------------------------------------------------------- paraphrase

def test_paraphrase_rewrites_prose_keeps_code_and_markers(monkeypatch):
    fake = fake_complete()
    monkeypatch.setattr(llm.Chat, "complete", fake)
    res = llm.paraphrase(MARKDOWN, Options())
    assert 'print("do not touch this text at all")' in res.text
    assert "```py\n" in res.text
    assert res.text.count("\n\n") == MARKDOWN.count("\n\n")
    assert res.text.startswith("# ")
    assert "\n- firstx" in res.text and "\n- secondx" in res.text
    assert "\n> ax" in res.text
    assert "\n    indentedx" in res.text
    assert res.llm_calls == len(fake.calls) >= 3  # heading, paragraph, list+quote... see _blocks
    n_words = len(words(MARKDOWN))
    assert n_words - 10 <= res.edits <= n_words - 8
    assert res.prompt_tokens == 100 * res.llm_calls


def test_paraphrase_marker_enforced_when_model_drops_it(monkeypatch):
    def complete(self, messages, **kw):
        block = messages[-1]["content"].split("TEXT:\n", 1)[1]
        lines = [re.sub(r"^\s*[-*#>]+\s+", "", ln) + " more" for ln in block.split("\n")]
        return json.dumps({"text": "\n".join(lines)}), dict(USAGE)

    monkeypatch.setattr(llm.Chat, "complete", complete)
    text = "## Heading\n- alpha\n- beta\n"
    res = llm.paraphrase(text, Options())
    assert res.text == "## Heading more\n- alpha more\n- beta more\n"


def test_paraphrase_failed_block_kept(monkeypatch):
    def complete(self, messages, **kw):
        return "I cannot do that.", dict(USAGE)

    monkeypatch.setattr(llm.Chat, "complete", complete)
    res = llm.paraphrase(PROSE, Options())
    assert res.text == PROSE and res.edits == 0 and res.notes["blocks_failed"] == 1


# ----------------------------------------------------------------------------- hybrid

def install_fake_rules(monkeypatch, mapping: dict[str, str]):
    """A stand-in for reflip.transforms.rules: substitute whole words, count per rule."""
    mod = types.ModuleType("reflip.transforms.rules")

    def apply_rules(text, names=()):
        counts: dict[str, int] = {}

        def sub(m):
            w = m.group(0)
            if w.lower() in mapping:
                counts[w.lower()] = counts.get(w.lower(), 0) + 1
                r = mapping[w.lower()]
                return r.capitalize() if w[0].isupper() else r
            return w

        return WORD_RE.sub(sub, text), counts

    mod.apply_rules = apply_rules
    monkeypatch.setitem(sys.modules, "reflip.transforms.rules", mod)
    return mod


def test_hybrid_passes_already_and_keeps_stride(monkeypatch):
    fake = fake_complete()
    monkeypatch.setattr(llm.Chat, "complete", fake)
    install_fake_rules(monkeypatch, {"the": "a", "and": "plus", "of": "from"})
    seen: dict = {}
    real = llm.choose_slots

    def spy(ws, stride, already=None):
        seen["already"] = set(already or ())
        return real(ws, stride, already=already)

    monkeypatch.setattr(llm, "choose_slots", spy)
    stride = 3
    res = llm.hybrid(PROSE, Options(stride=stride))
    assert seen["already"], "hybrid must pass the rule-edited word indices as already="
    ruled_words = [w.text.lower() for w in words(res.text)]
    assert all(ruled_words[i] not in ("the", "and", "of") for i in seen["already"] if i < len(ruled_words))
    # the union of rule edits and infill edits satisfies the stride constraint
    assert max_run(unedited_flags(PROSE, res.text)) < stride
    assert res.notes["rules"] and set(res.notes["rules"]) <= {"the", "and", "of"}
    assert res.notes["rule_words"] == len(seen["already"])
    assert res.notes["slots_saved"] > 0
    assert res.edits == res.notes["rule_words"] + res.notes["slots"] - res.notes["unfilled"]
    assert res.llm_calls == len(fake.calls) == 1
    # fewer slots than plain infill on the same text
    plain = llm.infill(PROSE, Options(stride=stride))
    assert res.notes["slots"] < plain.notes["slots"]
    assert res.notes["slots_saved"] == plain.notes["slots"] - res.notes["slots"]


def test_hybrid_with_no_rule_hits_equals_infill(monkeypatch):
    fake = fake_complete()
    monkeypatch.setattr(llm.Chat, "complete", fake)
    install_fake_rules(monkeypatch, {"zzzz": "yyyy"})
    res = llm.hybrid(PROSE, Options(stride=3))
    plain = llm.infill(PROSE, Options(stride=3))
    assert res.text == plain.text
    assert res.notes["slots_saved"] == 0 and res.notes["rule_words"] == 0


# ----------------------------------------------------------------------------- live (one small call)

LIVE_URL = "http://localhost:11434/v1"
LIVE_MODEL = "qwen3:4b-instruct-2507-q4_K_M"


def test_live_ollama_infill(monkeypatch):
    try:
        r = requests.get(LIVE_URL + "/models", timeout=5)
        ids = {m["id"] for m in r.json().get("data", [])}
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"no Ollama at {LIVE_URL}: {e}")
    if LIVE_MODEL not in ids:
        pytest.skip(f"{LIVE_MODEL} not pulled")
    monkeypatch.setattr(llm, "_RETRY_UNFILLED", False)  # exactly one call
    text = ("Cities that invest in public libraries get more than shelves of books. A library "
            "offers warm rooms, free internet, and quiet desks to people who have none of "
            "those at home, and it asks nothing in return.")
    assert len(words(text)) == 37  # a guard on the fixture, not on the tool
    res = llm.infill(text, Options(base_url=LIVE_URL, model=LIVE_MODEL, stride=3, timeout=180))
    assert res.llm_calls == 1
    assert res.notes["slots"] >= 10
    assert res.edits >= res.notes["slots"] // 2, res.notes
    # Punctuation, not spacing. A slot that covers a phrase may come back shorter
    # ("at home" as "within"), which changes how many spaces are inside that span while
    # leaving every comma and full stop where it was.
    assert res.text != text
    assert re.sub(r"\s+", "", skeleton(res.text)) == re.sub(r"\s+", "", skeleton(text))
    assert res.prompt_tokens > 0


class _WordTok:
    def __call__(self, text, add_special_tokens=False, **kw):
        import re as _re
        return {"input_ids": [hash(t) % 50000 for t in _re.findall(r"\w+|[^\w\s]", text)]}


def test_paraphrase_reasks_until_coverage(monkeypatch):
    calls = []

    def complete(self, messages, **kw):
        calls.append(messages[-1]["content"])
        block = messages[-1]["content"].split("TEXT:\n", 1)[1]
        if len(calls) == 1:
            return json.dumps({"text": block}), dict(USAGE)  # lazy first answer: unchanged
        return json.dumps({"text": " ".join(w + "x" for w in block.split())}), dict(USAGE)

    monkeypatch.setattr(llm.Chat, "complete", complete)
    text = "one two three four five six seven eight nine ten eleven twelve"
    res = llm.paraphrase(text, Options(tokenizer=_WordTok(), min_coverage=0.9, max_passes=3))
    assert len(calls) == 2 and "previous attempt" in calls[1]
    assert res.text != text and res.notes["extra_passes"] == 1 and res.notes["low_coverage_blocks"] == 0
    assert res.notes["min_block_coverage"] >= 0.9

    calls.clear()
    res = llm.paraphrase(text, Options(tokenizer=None, min_coverage=0.9))
    assert len(calls) == 1 and res.text == text  # no tokenizer: no check, lazy answer accepted
