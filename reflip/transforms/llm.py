"""LLM-backed transforms: ``infill`` (token-frugal), ``paraphrase`` (baseline), ``hybrid``.

Why this module exists
----------------------
SynthID-Text lives in token *choices*: the g-value of a token is a hash of the secret key,
the ngram_len-1 tokens before it and the token itself. Changing one token therefore
re-randomises its own g-value and the g-values of the ngram_len-1 tokens that follow. So
the cheapest way to erase the watermark is not to rewrite the text, but to change one word
in every window of ``stride`` words (``reflip.words`` picks which). Those few words still
have to be replaced by something that reads naturally, and that is the only job we give
the language model here: fill numbered slots. The model never rewrites the sentence, so
the rest of the text stays byte-for-byte identical and the edit count is exactly the slot
count.

Key design decisions
--------------------
* One request per chunk of text, all slots of the chunk in a single JSON object. A slot
  prompt costs a few tokens per slot instead of a full rewrite per sentence; a local
  Ollama model (the default backend) makes it free.
* Every fill is validated (differs from the original, no newline/brackets/quotes, short).
  Bad or missing fills are retried ONCE in a smaller follow-up request with one sentence
  of context each; whatever is still missing keeps the original word and is reported as
  ``unfilled`` so the bench can tell the difference between "the model refused" and
  "the method does not work".
* ``paraphrase`` is deliberately the naive baseline (full rewrite of every block) so the
  bench can show what the frugal method saves.
* ``hybrid`` runs the deterministic rules first and only asks the model for the windows
  the rules left untouched.

Everything except the intended edits (newlines, markdown, code blocks, URLs, indentation)
is preserved exactly: replacements are applied by offset with ``apply_replacements``.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import bisect
import difflib
import json
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

from ..words import (
    WORD_RE,
    Word,
    apply_replacements,
    choose_slots,
    choose_slots_tokenaware,
    word_edit_ratio,
    words,
)
from . import Options, TransformResult, register

# --------------------------------------------------------------------------- Chat client

_ATTEMPTS = 3
_BACKOFF = 0.5  # seconds; doubled at each retry


class ChatError(RuntimeError):
    """The chat server could not be reached or answered with an error."""


class Chat:
    """Minimal OpenAI-compatible chat-completions client on ``requests``.

    Ollama serves this API at http://localhost:11434/v1; OpenAI, DeepSeek, Groq, Mistral
    and Together speak the same dialect, so one client covers all of them.
    """

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.session = requests.Session()

    def complete(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: float = 0.7,
        seed: int | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, dict]:
        """Return ``(content, usage)``; usage has prompt_tokens/completion_tokens (0 if absent)."""
        body: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": temperature}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if seed is not None:
            body["seed"] = seed
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        data = self._post("/chat/completions", body)
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise ChatError(f"unexpected reply from {self.base_url}: {str(data)[:300]}") from e
        usage = data.get("usage") or {}
        return content, {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
        }

    def _post(self, path: str, body: dict) -> dict:
        url = self.base_url + path
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last: Exception | None = None
        for attempt in range(_ATTEMPTS):
            if attempt:
                time.sleep(_BACKOFF * 2 ** (attempt - 1))
            try:
                r = self.session.post(url, json=body, headers=headers, timeout=self.timeout)
            except requests.exceptions.RequestException as e:
                last = e
                continue
            if r.status_code >= 500:
                last = ChatError(f"HTTP {r.status_code}: {r.text[:300]}")
                continue
            if r.status_code >= 400:
                raise ChatError(f"{url} answered HTTP {r.status_code}: {r.text[:300]}")
            try:
                return r.json()
            except ValueError as e:
                raise ChatError(f"{url} did not return JSON: {r.text[:300]}") from e
        raise ChatError(
            f"cannot reach the chat server at {self.base_url} after {_ATTEMPTS} attempts ({last}). "
            "Is it running? For Ollama: `ollama serve`, then `ollama pull <model>`."
        ) from last


def estimate_tokens(text: str) -> int:
    """Rough token count (~4 characters per token) for reports when the API sends no usage."""
    return (len(text) + 3) // 4


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_FENCE_RE = re.compile(r"```[\w+-]*[ \t]*\n?(.*?)```", re.DOTALL)


def parse_json(content: str) -> Any:
    """Parse the model's reply as JSON, tolerating qwen3 ``<think>`` blocks, code fences and prose.

    Returns the first balanced object or array found; raises ValueError if there is none.
    """
    s = _THINK_RE.sub("", content)
    if "<think>" in s:  # unterminated think block: the model ran out of tokens inside it
        s = s.split("<think>", 1)[0]
    m = _FENCE_RE.search(s)
    if m:
        s = m.group(1)
    s = s.strip()
    try:
        return json.loads(s)
    except ValueError:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(s):
        if ch in "{[":
            try:
                value, _ = dec.raw_decode(s, i)
                return value
            except ValueError:
                continue
    raise ValueError(f"no JSON object or array in the model's reply: {s[:200]!r}")


# --------------------------------------------------------------------------- shared helpers

class _Usage:
    """Sums token usage over calls; falls back to estimate_tokens when the API sends none."""

    def __init__(self) -> None:
        self.calls = 0
        self.prompt = 0
        self.completion = 0
        self.estimated = False
        # Requests run on several threads. A token count that is only nearly right is
        # worse than none, because it goes into a table people compare.
        self.lock = threading.Lock()

    def add(self, messages: list[dict], content: str, usage: dict) -> None:
        with self.lock:
            self._add(messages, content, usage)

    def _add(self, messages: list[dict], content: str, usage: dict) -> None:
        self.calls += 1
        p, c = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        if not p:
            p, self.estimated = estimate_tokens("".join(m["content"] for m in messages)), True
        if not c and content:
            c, self.estimated = estimate_tokens(content), True
        self.prompt += p
        self.completion += c

    def fill(self, res: TransformResult) -> TransformResult:
        res.llm_calls += self.calls
        res.prompt_tokens += self.prompt
        res.completion_tokens += self.completion
        if self.estimated:
            res.notes["tokens_estimated"] = True
        return res


class _Counters(dict):
    """A dict whose increments from several threads do not lose counts."""

    def __init__(self, initial: dict) -> None:
        super().__init__(initial)
        self._lock = threading.Lock()

    def bump(self, key: str, by: int = 1) -> None:
        with self._lock:
            self[key] = self.get(key, 0) + by

    def least(self, key: str, value) -> None:
        with self._lock:
            self[key] = value if key not in self else min(self[key], value)


class _Progress:
    """Counts finished pieces and tells the caller, from whichever thread finished one."""

    def __init__(self, opts: Options, phase: str, total: int) -> None:
        self.fn = opts.on_progress
        self.phase = phase
        self.total = total
        self.done = 0
        self.lock = threading.Lock()
        self.announce(0, f"{phase}: 0 of {total}")

    def announce(self, done: int, message: str) -> None:
        if self.fn:
            self.fn(self.phase, done, self.total, message)

    def one(self) -> None:
        with self.lock:
            self.done += 1
            done = self.done
        self.announce(done, f"{self.phase}: {done} of {self.total}")


def _map_ordered(fn, items: list, opts: Options, phase: str) -> list:
    """Run fn over items, at most opts.workers at a time, and return the results in order.

    Threads rather than processes: each of these calls spends its life inside urllib
    waiting for the model server, so the interpreter lock is released the whole time and
    a process pool would only add the cost of shipping the text between them.
    """
    if not items:
        return []
    progress = _Progress(opts, phase, len(items))
    workers = max(1, min(int(opts.workers or 1), len(items)))
    if workers == 1:
        out = []
        for it in items:
            out.append(fn(it))
            progress.one()
        return out
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="reflip") as pool:
        futures = [pool.submit(fn, it) for it in items]
        results = []
        for f in futures:
            results.append(f.result())
            progress.one()
    return results


def _chat(opts: Options) -> Chat:
    return Chat(opts.base_url, opts.api_key, opts.model, opts.timeout)


def _safe_parse(content: str) -> Any | None:
    try:
        return parse_json(content)
    except ValueError:
        return None


_FENCE_OPEN_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
_INLINE_CODE_RE = re.compile(r"`+[^`\n]+`+")
_URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>()\[\]]+")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LINK_TARGET_RE = re.compile(r"\]\([^)\s]+\)")


def _fence_spans(text: str) -> list[tuple[int, int]]:
    """Offsets of fenced code blocks (an unterminated fence runs to the end of the text)."""
    spans: list[tuple[int, int]] = []
    open_at: int | None = None
    marker = ""
    pos = 0
    for line in text.splitlines(keepends=True):
        m = _FENCE_OPEN_RE.match(line)
        if m and open_at is None:
            open_at, marker = pos, m.group(1)
        elif m and open_at is not None and m.group(1)[0] == marker[0] and len(m.group(1)) >= len(marker):
            spans.append((open_at, pos + len(line)))
            open_at = None
        pos += len(line)
    if open_at is not None:
        spans.append((open_at, len(text)))
    return spans


def _protected_spans_base(text: str) -> list[tuple[int, int]]:
    """Regions no slot may touch: fenced code, inline code, URLs, e-mails, link targets."""
    spans = _fence_spans(text)
    for rx in (_INLINE_CODE_RE, _URL_RE, _EMAIL_RE, _LINK_TARGET_RE):
        spans.extend((m.start(), m.end()) for m in rx.finditer(text))
    return sorted(spans)


def _editable(w: Word, protected: list[tuple[int, int]]) -> bool:
    """A word can be a slot if it has letters (numbers are facts) and lies outside protected spans."""
    if not any(ch.isalpha() for ch in w.text):
        return False
    return not any(s < w.end and w.start < e for s, e in protected)


# --------------------------------------------------------------------------- infill

MAX_SLOTS_PER_REQUEST = 60
MAX_WORDS_PER_REQUEST = 1500
_RETRY_UNFILLED = True  # tests flip this to keep a live check to one call

_BLANK_RE = re.compile(r"\n[ \t\r]*\n(?:[ \t\r]*\n)*")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")
_SENT_END_RE = re.compile(r"[.!?…]+[\"'”’)\]]*(?=\s|$)|\n")
_SLOT_RE = re.compile(r"⟦(\d+)\|([^⟧]*)⟧")
_QUOTES = "\"'“”„‘’«»‹›`"
_FORBIDDEN = set("⟦⟧[]{}()<>\"“”„«»`")


@dataclass(frozen=True)
class Slot:
    n: int  # global 1-based number, in text order
    start: int  # char offsets in the text
    end: int
    original: str


def _build_slots(text: str, ws: list[Word], idxs: list[int], span: int,
                 protected: list[tuple[int, int]]) -> tuple[list[Slot], int]:
    """Turn chosen word indices into slots; returns (slots, skipped).

    A content word gets a slot of up to `span` words. A function word ("one", "of", "as")
    cannot be swapped for a synonym without breaking the sentence, so its slot is widened
    to reach the next content word (at most 3 words away): the model then rephrases a
    phrase, which it does well, instead of guessing a drop-in for "of". Slots only grow
    across plain spaces (never across a newline or punctuation) and never into protected
    spans. A chosen word that already lies inside the previous slot is absorbed.
    """
    ok = [_editable(w, protected) for w in ws]

    def can_extend(j: int) -> bool:
        return (j + 1 < len(ws) and ok[j + 1]
                and text[ws[j].end:ws[j + 1].start].strip(" \t") == "")

    ranges: list[tuple[int, int]] = []
    skipped = 0
    for i in idxs:
        if not ok[i]:
            skipped += 1
            continue
        if ranges and i <= ranges[-1][1]:
            continue
        j = i
        limit = max(span, 1)
        if not ws[i].is_content:
            limit = max(limit, 3)
            while j - i < limit - 1 and can_extend(j):
                j += 1
                if ws[j].is_content:
                    break
        else:
            while j - i < limit - 1 and can_extend(j):
                j += 1
        ranges.append((i, j))
    slots = [Slot(k + 1, ws[a].start, ws[b].end, text[ws[a].start:ws[b].end])
             for k, (a, b) in enumerate(ranges)]
    return slots, skipped


def _plan_slots(text: str, ws: list[Word], opts: Options, already: set[int] | None) -> tuple[list[Slot], int]:
    if opts.tokenizer is not None:
        idxs = choose_slots_tokenaware(text, ws, opts.tokenizer, opts.ngram_len, already=already)
    else:
        idxs = choose_slots(ws, opts.stride, already=already)
    return _build_slots(text, ws, idxs, max(1, opts.span), _protected_spans(text))


def _paragraphs(text: str) -> list[tuple[int, int]]:
    out, pos = [], 0
    for m in _BLANK_RE.finditer(text):
        if m.start() > pos:
            out.append((pos, m.start()))
        pos = m.end()
    if pos < len(text):
        out.append((pos, len(text)))
    return out


def _sentences(text: str, start: int, end: int) -> list[tuple[int, int]]:
    out, pos = [], start
    for m in _SENT_SPLIT_RE.finditer(text, start, end):
        if m.start() > pos:
            out.append((pos, m.start()))
        pos = m.end()
    if pos < end:
        out.append((pos, end))
    return out


def _chunks(text: str, ws: list[Word], slots: list[Slot]) -> list[tuple[int, int, list[Slot]]]:
    """Group paragraphs into requests of at most ~MAX_SLOTS slots / ~MAX_WORDS words.

    A paragraph that is too big on its own is cut at sentence ends; a single oversized
    sentence goes alone. Slot numbering is global, so a chunk is just a window."""
    slot_starts = [s.start for s in slots]
    word_starts = [w.start for w in ws]

    def in_range(starts: list[int], a: int, b: int) -> tuple[int, int]:
        return bisect.bisect_left(starts, a), bisect.bisect_left(starts, b)

    units: list[tuple[int, int]] = []
    for a, b in _paragraphs(text):
        s0, s1 = in_range(slot_starts, a, b)
        w0, w1 = in_range(word_starts, a, b)
        if s1 - s0 > MAX_SLOTS_PER_REQUEST or w1 - w0 > MAX_WORDS_PER_REQUEST:
            units.extend(_sentences(text, a, b))
        else:
            units.append((a, b))

    chunks: list[tuple[int, int, list[Slot]]] = []
    cur: list[tuple[int, int]] = []
    n_slots = n_words = 0
    for a, b in units:
        s0, s1 = in_range(slot_starts, a, b)
        w0, w1 = in_range(word_starts, a, b)
        if cur and (n_slots + s1 - s0 > MAX_SLOTS_PER_REQUEST or n_words + w1 - w0 > MAX_WORDS_PER_REQUEST):
            chunks.append(_close(cur, slots, slot_starts))
            cur, n_slots, n_words = [], 0, 0
        cur.append((a, b))
        n_slots += s1 - s0
        n_words += w1 - w0
    if cur:
        chunks.append(_close(cur, slots, slot_starts))
    return [c for c in chunks if c[2]]


def _close(cur: list[tuple[int, int]], slots: list[Slot], slot_starts: list[int]) -> tuple[int, int, list[Slot]]:
    a, b = cur[0][0], cur[-1][1]
    return a, b, slots[bisect.bisect_left(slot_starts, a):bisect.bisect_left(slot_starts, b)]


def _render(text: str, start: int, end: int, slots: list[Slot]) -> str:
    out, pos = [], start
    for s in slots:
        out.append(text[pos:s.start])
        out.append(f"⟦{s.n}|{s.original}⟧")
        pos = s.end
    out.append(text[pos:end])
    return "".join(out)


def _system_prompt(max_words: int) -> str:
    return (
        "You are a meticulous copy editor. You receive a text in which some words or short "
        "phrases are marked as numbered slots written as ⟦n|original⟧. For every slot, "
        "propose a replacement so that the sentence reads naturally and keeps exactly the same "
        "meaning. Nothing outside the slots will change, so read each sentence with your "
        "replacement dropped in before you answer.\n"
        "Rules for each replacement:\n"
        "1. It must differ from the original (a change of capitalisation does not count).\n"
        "2. It must be a grammatical drop-in: same part of speech, tense, number, person and "
        "register, fitting the surrounding words and punctuation exactly as they are.\n"
        "3. When a slot covers several words, rewrite the whole phrase as one natural phrase "
        "(for example ⟦3|one of the⟧ heaters -> \"a\" or \"a single\"; ⟦7|as soon as⟧ possible -> "
        "\"as quickly as\").\n"
        f"4. At most {max(max_words, 3)} words; no newline, brackets, quotation marks, markdown or slot marks.\n"
        "5. Write in the same language as the text. Never alter names, numbers, code or URLs.\n"
        "Reply with ONE JSON object mapping each slot number (as a string key) to its "
        'replacement, for example {"1": "quick", "2": "beneath the"}. No other keys, no commentary.'
    )


def _chunk_messages(text: str, start: int, end: int, slots: list[Slot], max_words: int) -> list[dict]:
    first, last = slots[0].n, slots[-1].n
    user = (
        f"Text with {len(slots)} slots (numbers {first} to {last}):\n\n"
        f"{_render(text, start, end, slots)}\n\n"
        f'Return the JSON object with the keys "{first}" to "{last}".'
    )
    return [{"role": "system", "content": _system_prompt(max_words)}, {"role": "user", "content": user}]


def _sentence_bounds(text: str) -> list[int]:
    return [m.end() for m in _SENT_END_RE.finditer(text)]


def _sentence_of(text: str, bounds: list[int], slot: Slot) -> tuple[int, int]:
    k = bisect.bisect_right(bounds, slot.start)
    a = bounds[k - 1] if k else 0
    k = bisect.bisect_left(bounds, slot.end)
    b = bounds[k] if k < len(bounds) else len(text)
    return a, b


def _followup_messages(text: str, slots: list[Slot], max_words: int) -> list[dict]:
    bounds = _sentence_bounds(text)
    lines = []
    for s in slots:
        a, b = _sentence_of(text, bounds, s)
        lines.append(f"{s.n}: {_render(text, a, b, [s]).strip()}")
    user = (
        "These slots still need a replacement. Each line shows one slot inside its sentence; "
        "replace only the marked word(s), following the rules.\n\n" + "\n".join(lines) +
        "\n\nReturn the JSON object with one key per slot number."
    )
    return [{"role": "system", "content": _system_prompt(max_words)}, {"role": "user", "content": user}]


def _match_case(orig: str, fill: str) -> str:
    """Make the fill's capitalisation follow the original's."""
    if orig.isupper() and len(orig) > 1:
        return fill.upper()
    if orig[:1].isupper():
        return fill[0].upper() + fill[1:] if fill[:1].islower() else fill
    if orig.islower():
        return fill.lower() if fill.isupper() else fill[:1].lower() + fill[1:]
    return fill


def _valid_fill(orig: str, fill: Any, max_words: int) -> str | None:
    if isinstance(fill, dict):  # {"replacement": "..."} style answers
        fill = next((v for v in fill.values() if isinstance(v, str)), None)
    if not isinstance(fill, str):
        return None
    f = fill.strip()
    if len(f) >= 2 and f[0] in _QUOTES and f[-1] in _QUOTES:  # the model quoted its answer
        f = f[1:-1].strip()
    if not f or "\n" in f or _FORBIDDEN & set(f) or len(f.split()) > max_words:
        return None
    if " ".join(f.split()).lower() == " ".join(orig.split()).lower():
        return None
    ow = orig.split()
    if len(ow) > 1 and f.split()[0].lower() == ow[0].lower():
        # the coverage plan anchors on the slot's first word: keeping it would leave a hole
        return None
    return _match_case(orig, f)


def _fills_from(parsed: Any, by_n: dict[int, Slot], max_words: int) -> dict[int, str]:
    """Normalise the model's JSON (dict, or list of {n, replacement}) into {n: valid fill}."""
    items: list[tuple[Any, Any]] = []
    if isinstance(parsed, dict):
        items = list(parsed.items())
    elif isinstance(parsed, list):
        for it in parsed:
            if isinstance(it, dict):
                key = next((it[k] for k in ("n", "slot", "id", "number") if k in it), None)
                val = next((it[k] for k in ("replacement", "text", "word", "value") if k in it), None)
                items.append((key, val))
    out: dict[int, str] = {}
    for key, val in items:
        m = re.search(r"\d+", str(key))
        if not m or int(m.group()) not in by_n:
            continue
        n = int(m.group())
        fill = _valid_fill(by_n[n].original, val, max_words)
        if fill is not None:
            out[n] = fill
    return out


def _request_fills(chat: Chat, messages: list[dict], by_n: dict[int, Slot], opts: Options,
                   max_words: int, acc: _Usage, stats: dict) -> dict[int, str]:
    content, usage = chat.complete(messages, json_mode=True, temperature=opts.temperature, seed=opts.seed)
    acc.add(messages, content, usage)
    parsed = _safe_parse(content)
    if parsed is None:
        stats["parse_errors"] = stats.get("parse_errors", 0) + 1
        return {}
    return _fills_from(parsed, by_n, max_words)


def _fill_slots(chat: Chat, text: str, ws: list[Word], slots: list[Slot], opts: Options,
                acc: _Usage, stats: dict) -> dict[int, str]:
    max_words = max(3, opts.span)
    by_n = {s.n: s for s in slots}
    fills: dict[int, str] = {}
    chunks = _chunks(text, ws, slots)
    stats["chunks"] = len(chunks)
    for got in _map_ordered(
            lambda c: _request_fills(chat, _chunk_messages(text, c[0], c[1], c[2], max_words),
                                     by_n, opts, max_words, acc, stats),
            chunks, opts, "Filling in words"):
        fills.update(got)
    missing = [s for s in slots if s.n not in fills]
    if missing and _RETRY_UNFILLED:
        stats["retried"] = len(missing)
        for k in range(0, len(missing), MAX_SLOTS_PER_REQUEST):
            batch = missing[k:k + MAX_SLOTS_PER_REQUEST]
            fills.update(_request_fills(chat, _followup_messages(text, batch, max_words), by_n, opts, max_words, acc, stats))
    return fills


def _infill(text: str, opts: Options, already: set[int] | None = None) -> TransformResult:
    """Shared machinery of ``infill`` and ``hybrid``: plan slots, fill them, apply."""
    ws = words(text)
    slots, skipped = _plan_slots(text, ws, opts, already)
    acc = _Usage()
    stats: dict = {}
    fills = _fill_slots(_chat(opts), text, ws, slots, opts, acc, stats) if slots else {}
    slot_words = [Word(s.start, s.end, s.original) for s in slots]
    new = apply_replacements(text, slot_words, {k: fills[s.n] for k, s in enumerate(slots) if s.n in fills})
    notes = {
        "slots": len(slots),
        "unfilled": len(slots) - len(fills),
        "stride": opts.stride,
        "span": opts.span,
        "tokenaware": opts.tokenizer is not None,
        "skipped_protected": skipped,
        **stats,
    }
    return acc.fill(TransformResult(text=new, edits=len(fills), notes=notes))


@register("infill")
def infill(text: str, opts: Options) -> TransformResult:
    """Replace one word in every window of `stride` words (or `ngram_len` tokens) with a synonym."""
    return _infill(text, opts)


# --------------------------------------------------------------------------- paraphrase

_MARKER_RE = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)]|#{1,6}|>)[ \t]+")


def _blocks(text: str) -> list[tuple[str, bool]]:
    """Split into (piece, rewrite?) pieces: prose blocks are rewritten, separators and code pass through."""
    fixed = _fence_spans(text)
    fixed.extend((m.start(), m.end()) for m in _BLANK_RE.finditer(text))
    fixed.sort()
    out: list[tuple[str, bool]] = []
    pos = 0
    for a, b in fixed:
        if b <= pos:  # a blank line inside a fence
            continue
        a = max(a, pos)  # a blank line that starts on the fence's closing newline
        if a > pos:
            out.append((text[pos:a], True))
        out.append((text[a:b], False))
        pos = b
    if pos < len(text):
        out.append((text[pos:], True))
    return out


def _keep_layout(orig: str, new: str) -> tuple[str, bool]:
    """Line by line, a rewritten line takes the original's list/heading/quote marker and
    indentation. Only possible when the model kept the line count; returns (text, kept)."""
    ol, nl = orig.split("\n"), new.split("\n")
    if len(ol) != len(nl):
        return new, False
    fixed = []
    for o, n in zip(ol, nl):
        m = _MARKER_RE.match(o)
        prefix = m.group(0) if m else o[:len(o) - len(o.lstrip(" \t"))]
        fixed.append(prefix + _MARKER_RE.sub("", n, count=1).lstrip(" \t"))
    return "\n".join(fixed), True


def _paraphrase_messages(block: str, strong: bool = False) -> list[dict]:
    system = ('You rewrite text in your own words. Reply with ONE JSON object {"text": "..."} '
              "containing only the rewritten text, nothing else.")
    user = (
        "Rewrite the following text in your own words, changing the wording throughout (change at "
        "least every third word), while keeping the meaning, tone, length (within 15%), language, "
        "names, numbers, and any markdown structure (bullets, headings, quotes, line breaks, "
        "emphasis). Keep every line break where it is.\n\n"
    )
    if strong:
        user += (
            "The previous attempt kept too many of the original word sequences. This time change "
            "nearly every word and reorder clauses where the meaning allows; keep only names, "
            "numbers and the meaning.\n\n"
        )
    return [{"role": "system", "content": system}, {"role": "user", "content": user + "TEXT:\n" + block}]


def _coverage(orig: str, new: str, opts: Options) -> float:
    """Share of ngram_len-token windows of `new` that contain an edit, under opts.tokenizer."""
    from ..synthid import intact_fraction

    a = opts.tokenizer(orig, add_special_tokens=False)["input_ids"]
    b = opts.tokenizer(new, add_special_tokens=False)["input_ids"]
    return 1.0 - intact_fraction(a, b, opts.ngram_len)


def _ask_rewrite(chat: Chat, core: str, opts: Options, acc: _Usage, strong: bool) -> str | None:
    messages = _paraphrase_messages(core, strong=strong)
    content, usage = chat.complete(messages, json_mode=True, temperature=opts.temperature, seed=opts.seed)
    acc.add(messages, content, usage)
    parsed = _safe_parse(content)
    new = parsed.get("text") if isinstance(parsed, dict) else parsed if isinstance(parsed, str) else None
    return new if isinstance(new, str) and new.strip() else None


def _rewrite_block(chat: Chat, block: str, opts: Options, acc: _Usage, stats: dict) -> str:
    """Rewrite one prose block; on a failed reply the block is returned unchanged.

    With opts.tokenizer and opts.min_coverage set, the block is checked: if fewer than
    min_coverage of its ngram windows carry an edit, the model is asked again (up to
    opts.max_passes attempts, stronger wording) and the best attempt is kept.
    """
    core = block.strip("\n")
    lead, trail = block[:block.index(core)], block[block.index(core) + len(core):]
    check = opts.tokenizer is not None and opts.min_coverage > 0
    best, best_cov = None, -1.0
    for attempt in range(max(1, opts.max_passes) if check else 1):
        new = _ask_rewrite(chat, core, opts, acc, strong=attempt > 0)
        if new is None:
            continue
        cov = _coverage(core, new, opts) if check else 1.0
        if cov > best_cov:
            best, best_cov = new, cov
        if not check or cov >= opts.min_coverage:
            break
        stats.bump("extra_passes")
    if best is None:
        stats.bump("blocks_failed")
        return block
    if check:
        stats.least("min_block_coverage", round(best_cov, 3))
        if best_cov < opts.min_coverage:
            stats.bump("low_coverage_blocks")
    new, kept = _keep_layout(core, best.strip("\n").rstrip())
    if not kept:
        stats.bump("lines_changed")
    return lead + new + trail


@register("paraphrase")
def paraphrase(text: str, opts: Options) -> TransformResult:
    """Baseline: ask the model to rewrite every prose block; code and blank lines pass through."""
    chat = _chat(opts)
    acc = _Usage()
    # Counters incremented from worker threads: a plain dict loses counts on +=.
    stats = _Counters({"blocks_failed": 0, "lines_changed": 0, "extra_passes": 0,
                       "low_coverage_blocks": 0})
    pieces = _blocks(text)
    todo = [i for i, (piece, rewrite) in enumerate(pieces) if rewrite and WORD_RE.search(piece)]
    rewritten = _map_ordered(lambda i: _rewrite_block(chat, pieces[i][0], opts, acc, stats),
                             todo, opts, "Rewriting")
    out = [piece for piece, _ in pieces]
    for i, piece in zip(todo, rewritten):
        out[i] = piece
    new_text = "".join(out)
    n_words = len(words(text))
    edits = round(word_edit_ratio(text, new_text) * n_words)
    return acc.fill(TransformResult(text=new_text, edits=edits,
                                    notes={"words": n_words, "workers": max(1, int(opts.workers or 1)),
                                           **dict(stats)}))


# --------------------------------------------------------------------------- hybrid

def _changed_word_indices(orig: str, new: str) -> set[int]:
    """Indices (in `new`) of words that are not part of a run kept verbatim from `orig`."""
    import difflib
    wa = [w.text.lower() for w in words(orig)]
    wb = [w.text.lower() for w in words(new)]
    kept: set[int] = set()
    sm = difflib.SequenceMatcher(a=wa, b=wb, autojunk=False)
    for _, jb, n in sm.get_matching_blocks():
        kept.update(range(jb, jb + n))
    return {k for k in range(len(wb)) if k not in kept}


@register("hybrid")
def hybrid(text: str, opts: Options) -> TransformResult:
    """Deterministic rules first, then infill only in the windows the rules left untouched."""
    import importlib

    apply_rules = importlib.import_module(__package__ + ".rules").apply_rules

    ruled, counts = apply_rules(text, names=opts.rules)
    already = _changed_word_indices(text, ruled)
    plain_slots, _ = _plan_slots(text, words(text), opts, None)  # what infill alone would need
    res = _infill(ruled, opts, already=already)
    res.edits += len(already)
    res.notes.update({
        "rules": dict(counts),
        "rule_words": len(already),
        "slots_saved": len(plain_slots) - res.notes["slots"],
    })
    return res


_PLACEHOLDER = re.compile(r"\[[^\]\n]{1,40}\]|\{[^}\n]{1,40}\}|<[^>\n]{1,40}>")


def _protected_spans(text: str) -> list[tuple[int, int]]:
    """Base protected spans plus template placeholders like [Name], {city}, <date>."""
    spans = list(_protected_spans_base(text))
    spans += [(m.start(), m.end()) for m in _PLACEHOLDER.finditer(text)]
    return sorted(spans)
