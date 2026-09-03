"""Invisible-character cleaner: the negative control.

Every "Claude watermark remover" website does this and nothing else: delete zero-width
characters, soft hyphens and exotic spaces. It cannot touch a SynthID watermark, which
lives in the choice of words, not in the characters. It is here so that the benchmark
can show that (the detector does not move), and as a courtesy cleaner for text that
really does carry copy-paste junk. `scan` powers `reflip check`.
"""
from __future__ import annotations

import re
import unicodedata

from . import Options, TransformResult, register

INVISIBLE = frozenset(
    [0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0x2061, 0x2062, 0x2063, 0x2064,
     0xFEFF, 0x00AD, 0x180E, 0x061C, 0x034F]
)
EXOTIC_SPACES = frozenset(
    [0x00A0, 0x202F, 0x2007, 0x2009, 0x200A, 0x3000, 0x2002, 0x2003, 0x2004, 0x2005,
     0x2006, 0x2008, 0x205F, 0x1680]
)
_VS_LO, _VS_HI = 0xFE00, 0xFE0F  # variation selectors: kept after emoji-range characters
_FENCE = re.compile(r"```.*?```", re.S)


def _name(ch: str) -> str:
    try:
        return unicodedata.name(ch)
    except ValueError:
        return f"U+{ord(ch):04X}"


def _is_target(prev: str | None, ch: str) -> bool:
    o = ord(ch)
    if o in INVISIBLE or o in EXOTIC_SPACES:
        return True
    if _VS_LO <= o <= _VS_HI:
        return not (prev is not None and ord(prev) >= 0x2600)
    return False


def scan(text: str) -> dict[str, int]:
    """Counts of invisible / exotic characters, by Unicode name."""
    found: dict[str, int] = {}
    prev = None
    for ch in text:
        if _is_target(prev, ch):
            n = _name(ch)
            found[n] = found.get(n, 0) + 1
        prev = ch
    return found


def _clean_segment(seg: str) -> tuple[str, int]:
    out = []
    n = 0
    prev = None
    for ch in seg:
        if _is_target(prev, ch):
            n += 1
            if ord(ch) in EXOTIC_SPACES:
                out.append(" ")
        else:
            out.append(ch)
        prev = ch
    return "".join(out), n


def clean(text: str) -> tuple[str, int]:
    """Remove invisible characters outside fenced code blocks; exotic spaces become spaces."""
    out = []
    n = 0
    pos = 0
    for m in _FENCE.finditer(text):
        seg, k = _clean_segment(text[pos:m.start()])
        out.append(seg)
        n += k
        out.append(m.group(0))
        pos = m.end()
    seg, k = _clean_segment(text[pos:])
    out.append(seg)
    n += k
    return "".join(out), n


@register("unicode")
def unicode_transform(text: str, opts: Options) -> TransformResult:
    found = scan(text)
    new, n = clean(text)
    return TransformResult(text=new, edits=n, notes={"found": found})
