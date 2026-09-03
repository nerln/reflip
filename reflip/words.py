"""Word segmentation and edit-slot selection.

The SynthID detector hashes each token together with the ngram_len-1 tokens before it.
Changing one token re-randomises the g-values of that token and of the
ngram_len-1 tokens after it. If every window of ngram_len consecutive tokens contains at
least one edited token, every g-value is re-randomised and the watermark is gone. The
functions here pick the *fewest* words to edit under that constraint, preferring content
words (where a synonym costs nothing) over function words.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)

STOPWORDS = frozenset(
    """a an the and or but nor so yet of to in on at for with by from as is are was were be been
    being it its this that these those he she they we you i me him her them us his their our your
    my not no do does did done have has had having will would can could should shall may might
    must than then if when while where which who whom whose what how why there here also just
    very too only own same such into onto over under up down out off again further once all any
    both each few more most other some because until about above below between through during
    before after per via
    il lo la i gli le un uno una di a da in con su per tra fra e o ma se che chi cui non più
    anche come dove quando mentre questo questa questi queste quello quella quelli quelle
    sono è era erano essere avere ha hanno del della dei delle dal dalla nel nella nei nelle
    al alla ai alle sul sulla sui sulle""".split()
)


@dataclass(frozen=True)
class Word:
    start: int
    end: int
    text: str

    @property
    def is_content(self) -> bool:
        t = self.text.lower()
        return t.isalpha() and len(t) >= 4 and t not in STOPWORDS


def words(text: str) -> list[Word]:
    return [Word(m.start(), m.end(), m.group(0)) for m in WORD_RE.finditer(text)]


def _content_score(w: Word) -> float:
    t = w.text.lower()
    if not t.isalpha() or t in STOPWORDS:
        return 0.0
    if len(t) >= 4:
        return 1.0
    return 0.3


def choose_slots(ws: list[Word], stride: int, already: set[int] | None = None) -> list[int]:
    """Indices of words to edit so that every run of `stride` consecutive words has one.

    Greedy: walk the words; as soon as `stride` words have gone by without an edit, pick
    the best word inside that run (content word first, then the latest one so that edits
    are as sparse as the constraint allows). Words in `already` count as edited (they
    are not returned), which is how the hybrid transform reports what the rules already did.
    """
    if stride < 1:
        raise ValueError("stride must be >= 1")
    already = already or set()
    chosen: list[int] = []
    last = -1
    for i in range(len(ws)):
        if i in already:
            last = i
            continue
        if i - last >= stride:
            lo, hi = last + 1, i
            best = max(range(lo, hi + 1), key=lambda j: (_content_score(ws[j]), j))
            chosen.append(best)
            last = best
    return chosen


def choose_slots_tokenaware(text: str, ws: list[Word], tokenizer, ngram_len: int,
                            already: set[int] | None = None) -> list[int]:
    """Like choose_slots, but the constraint is in *tokens* of the given tokenizer:
    every window of ngram_len consecutive tokens must contain a token of an edited word.

    Requires a fast tokenizer (offset_mapping). The edited word's FIRST token is taken as
    the edit position, which is conservative (a shorter replacement still covers).
    """
    enc = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    offsets = enc["offset_mapping"]
    n_tok = len(offsets)
    if n_tok == 0:
        return []
    # token index -> word index (or -1)
    tok2word = [-1] * n_tok
    wi = 0
    for ti, (s, e) in enumerate(offsets):
        while wi < len(ws) and ws[wi].end <= s:
            wi += 1
        if wi < len(ws) and ws[wi].start < e and s < ws[wi].end:
            tok2word[ti] = wi
    word_first_tok = {}
    for ti, w in enumerate(tok2word):
        if w >= 0 and w not in word_first_tok:
            word_first_tok[w] = ti
    already = already or set()
    chosen: list[int] = []
    last_tok = -1
    for ti in range(n_tok):
        if tok2word[ti] in already:
            last_tok = ti
            continue
        if ti - last_tok >= ngram_len:
            cands = sorted({tok2word[q] for q in range(last_tok + 1, ti + 1) if tok2word[q] >= 0})
            if not cands:
                # only punctuation/whitespace tokens in the window: extend to the next word
                continue
            best = max(cands, key=lambda j: (_content_score(ws[j]), j))
            if chosen and best == chosen[-1]:
                continue
            chosen.append(best)
            last_tok = word_first_tok[best]
    return chosen


def apply_replacements(text: str, ws: list[Word], repl: dict[int, str]) -> str:
    """Replace words by index. Preserves everything else byte-for-byte."""
    out = []
    pos = 0
    for i, w in enumerate(ws):
        if i in repl:
            out.append(text[pos:w.start])
            out.append(repl[i])
            pos = w.end
    out.append(text[pos:])
    return "".join(out)


def word_edit_ratio(a: str, b: str) -> float:
    """Fraction of words in `a` that are not kept verbatim in `b` (difflib on lowercase words)."""
    import difflib

    wa = [w.text.lower() for w in words(a)]
    wb = [w.text.lower() for w in words(b)]
    if not wa:
        return 0.0
    sm = difflib.SequenceMatcher(a=wa, b=wb, autojunk=False)
    kept = sum(n for _, _, n in sm.get_matching_blocks())
    return 1.0 - kept / len(wa)
