"""What a rewrite changed in the facts of a text: numbers, names, negations, quantifiers.

A paraphrase that sounds right can still say something else: a figure dropped, a name gone,
a "not" lost, "most" turned into "all". On dense technical prose the earlier benchmark found
21 to 32 such breaks per text. This module counts them without a model, so it runs on any
machine and, ported line by line to docs/app/facts.js, in the browser.

It is a check, not a proof. It catches the changes it has words for, in English, Italian and
Spanish, and nothing else: a claim reworded with every number and name intact is invisible
to it. The lexicon both versions read is facts_lexicon.json.
"""

from __future__ import annotations

import bisect
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

LEXICON = json.loads((Path(__file__).resolve().parent / "facts_lexicon.json").read_text())

# a number with thousands groups and decimals, or a word with inner apostrophes and hyphens
WORD = re.compile(r"[0-9]+(?:[.,'  ][0-9]{3})*(?:[.,][0-9]+)?%?|[^\W\d_]+(?:['’-][^\W\d_]+)*")
SENTENCE_END = re.compile(r"[.!?…]+[\"'”»)\]]*\s+|\n")
OPENERS = " \t\r\n\"'“‘«([-–—*#>•"
NEGATIVE_CONTRACTION = re.compile(r"n['’]t\b", re.IGNORECASE)


@dataclass
class Facts:
    numbers: Counter = field(default_factory=Counter)
    names: Counter = field(default_factory=Counter)       # capitalised, not opening a sentence
    lowered: set = field(default_factory=set)             # every word, lower-cased, anywhere
    negations: int = 0
    quantifiers: Counter = field(default_factory=Counter)
    words: int = 0


def tokens(text: str) -> list[tuple[str, bool, int, int]]:
    """Words and numbers, each with whether it opens a sentence or a line, and where it is.
    Curly apostrophes are read as straight ones: "Landlord’s" and "Landlord's" are one name."""
    starts = [0] + [m.end() for m in SENTENCE_END.finditer(text)]
    out = []
    for m in WORD.finditer(text):
        s = starts[bisect.bisect_right(starts, m.start()) - 1]
        out.append((m.group(0).replace("\u2019", "'"), text[s:m.start()].strip(OPENERS) == "", m.start(), m.end()))
    return out


LIST_MARKER = re.compile(r"[.)](\s|$)")
TITLE_WORD = re.compile(r"[^\W\d_]{4,}")


def heading_spans(text: str) -> list[tuple[int, int]]:
    """Lines that are headings: markdown '#', a line in bold, or a short Title Case line
    without closing punctuation. Their capitals are style, not names."""
    spans, pos = [], 0
    for line in text.split("\n"):
        t = line.strip()
        long_words = TITLE_WORD.findall(t)
        title = (t and t[-1] not in ".!?:;," and len(t.split()) <= 12 and long_words
                 and sum(w[0].isupper() for w in long_words) >= 0.6 * len(long_words) and len(long_words) >= 2)
        if t.startswith("#") or (t.startswith("**") and t.endswith("**") and len(t) > 4) or title:
            spans.append((pos, pos + len(line)))
        pos += len(line) + 1
    return spans


def digit_value(tok: str, lang: str) -> float | None:
    t = tok.rstrip("%").replace(" ", "").replace(" ", "").replace("'", "")
    if lang == "en":
        t = t.replace(",", "")
    elif "," in t or re.search(r"\.\d{3}(?!\d)", t):
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def italian_word(w: str) -> float | None:
    """Italian writes a number as one word: trecentoquarantacinque, duemila, ventitré."""
    lex = LEXICON["numbers"]["it"]
    if w in lex["alone_excluded"] or w in lex["scales"] or w in lex["thousand_many"]:
        return None                     # "milioni di persone" is not a number on its own
    total, current, i = 0, 0, 0
    while i < len(w):
        p = next((p for p in IT_PARTS if w.startswith(p, i)), None)
        if p is None:
            return None
        i += len(p)
        if p in lex["morphemes"]:
            current += lex["morphemes"][p]
        elif p in lex["hundred"]:
            current = (current or 1) * 100
        elif p in lex["thousand_one"]:
            total, current = total + 1000, 0
        elif p in lex["thousand_many"]:
            total, current = total + (current or 1) * 1000, 0
        else:
            total, current = total + (current or 1) * lex["scales"][p], 0
    return float(total + current) if w else None


_it = LEXICON["numbers"]["it"]
IT_PARTS = sorted(list(_it["morphemes"]) + _it["hundred"] + _it["thousand_one"] + _it["thousand_many"]
                  + list(_it["scales"]), key=len, reverse=True)


def word_numbers(words: list[str], lang: str) -> list[float]:
    """The value of each run of number words."""
    lex = LEXICON["numbers"][lang]
    scales = lex["scales"]
    out, i, n = [], 0, len(words)
    while i < n:
        if lang == "it":
            v = italian_word(words[i])
            if v is None and words[i] in lex["one"] and i + 1 < n and words[i + 1] in scales:
                v = 1.0
            if v is None:
                i += 1
                continue
            j, total, current = i + 1, 0.0, v
            while j < n:
                if words[j] in scales:
                    total, current = total + (current or 1) * scales[words[j]], 0.0
                    j += 1
                elif total and words[j] in lex["joiners"] and j + 1 < n and italian_word(words[j + 1]) is not None:
                    current += italian_word(words[j + 1])
                    j += 2
                else:
                    break
            out.append(total + current)
            i = j
            continue
        # English and Spanish write a number as a run of words
        j, total, current, seen = i, 0.0, 0.0, False
        while j < n:
            x = words[j]
            nxt = words[j + 1] if j + 1 < n else ""
            if x in lex["units"]:
                current += lex["units"][x]
            elif lang == "es" and x in lex["hundreds"]:
                current += lex["hundreds"][x]
            elif lang == "en" and x in lex["hundred"] and seen:
                current = (current or 1) * 100
            elif x in scales and (seen or x in lex.get("alone_scales", [])):
                total, current = total + (current or 1) * scales[x], 0.0
            elif not seen and x in lex["one"] and (nxt in scales or (lang == "en" and nxt in lex["hundred"])):
                current += 1
            elif seen and x in lex["joiners"] and _joins(words[j - 1], nxt, lex, lang):
                j += 1
                continue
            else:
                break
            seen = True
            j += 1
        if seen:
            out.append(total + current)
            i = j
        else:
            i += 1
    return out


def _joins(prev: str, nxt: str, lex: dict, lang: str) -> bool:
    """'two hundred and five', 'treinta y tres': and/y only after a hundred, a scale or a ten."""
    if lang == "en":
        return (prev in lex["hundred"] or prev in lex["scales"]) and nxt in lex["units"]
    ten = lex["units"].get(prev, 0)
    return ten >= 30 and ten % 10 == 0 and 0 < lex["units"].get(nxt, 0) < 10


def facts(text: str, lang: str) -> Facts:
    f = Facts()
    toks = tokens(text)
    words = [t.lower() for t, *_ in toks]
    f.words = sum(1 for t, *_ in toks if not t[0].isdigit())
    scales = LEXICON["numbers"][lang]["scales"]
    for k, (t, opening, a, b) in enumerate(toks):
        if t[0].isdigit():
            # "1." or "2)" at the start of a line numbers a list; it is not a fact
            if opening and LIST_MARKER.match(text, b):
                continue
            v = digit_value(t, lang)
            if v is not None:
                # "3 million" is the number three million, as "three million" is
                nxt = words[k + 1] if k + 1 < len(words) else ""
                f.numbers[v * scales.get(nxt, 1)] += 1
    split = [p for w in words if not w[0].isdigit() for p in w.split("-")]
    for v in word_numbers(split, lang):
        f.numbers[v] += 1
    heads = heading_spans(text)
    for t, opening, a, b in toks:
        f.lowered.add(t.lower())
        if (t[0].isupper() and len(t) > 1 and not opening and not (lang == "en" and t.startswith("I'"))
                and not any(x <= a < y for x, y in heads)):
            f.names[t] += 1
    neg = set(LEXICON["negations"][lang])
    f.negations = sum(1 for w in split if w in neg)
    if lang == "en":
        f.negations += len(NEGATIVE_CONTRACTION.findall(text))
    lowered = " " + " ".join(split) + " "
    for phrase, cls in sorted(LEXICON["quantifiers"][lang].items(), key=lambda kv: (-len(kv[0]), kv[0])):
        k = lowered.count(" " + phrase + " ")
        if k:
            f.quantifiers[cls] += k
            lowered = lowered.replace(" " + phrase + " ", " | ")
    return f


def language(text: str, hint: str | None = None) -> str | None:
    """The language to read facts in: a clear guess from the text, else the hint if the
    lexicon has it. The guess comes first because the command line's --lang defaults to en."""
    from .detect import guess_language

    lang, share = guess_language(text)
    if lang in LEXICON["negations"] and share >= 0.6:
        return lang
    return hint if hint in LEXICON["negations"] else None


def fact_spans(text: str, lang: str) -> list[tuple[int, int]]:
    """Character spans of the words a rewrite must not touch: names, number words,
    negations and quantifiers. Infill leaves them out of its slots; digits are already out."""
    neg = set(LEXICON["negations"][lang])
    quant = {p for p in LEXICON["quantifiers"][lang] if " " not in p}
    lex = LEXICON["numbers"][lang]
    numberish = set(lex.get("units", {})) | set(lex.get("hundreds", {})) | set(lex["scales"]) \
        | set(lex.get("hundred", []))
    spans = []
    starts = [0] + [m.end() for m in SENTENCE_END.finditer(text)]
    for m in WORD.finditer(text):
        t = m.group(0)
        low = t.lower()
        s = starts[bisect.bisect_right(starts, m.start()) - 1]
        opening = text[s:m.start()].strip(OPENERS) == ""
        if (low in neg or low in quant or low in numberish or NEGATIVE_CONTRACTION.search(t)
                or (lang == "it" and italian_word(low) is not None)
                or (t[0].isupper() and len(t) > 1 and not opening)):
            spans.append((m.start(), m.end()))
    return spans


def lexicon_js() -> str:
    """docs/app/facts-lexicon.js, the browser's copy of the lexicon; a test keeps them equal."""
    return ("// Generated from reflip/facts_lexicon.json by reflip.facts.lexicon_js(). Do not edit.\n"
            "export default " + json.dumps(LEXICON, ensure_ascii=False, indent=1) + ";\n")


def _fmt(v: float) -> str:
    return str(int(v)) if v == int(v) else f"{v:g}"


def diff(original: str, rewritten: str, lang: str) -> dict:
    """What changed between two texts, and how many facts that is per thousand words."""
    a, b = facts(original, lang), facts(rewritten, lang)
    missing_num, added_num = a.numbers - b.numbers, b.numbers - a.numbers
    # a name is kept if the word appears anywhere in the other text, in any case: moved to the
    # start of a sentence, or written in capitals, it is the same name
    missing_names = Counter({k: v for k, v in (a.names - b.names).items() if k.lower() not in b.lowered})
    added_names = Counter({k: v for k, v in (b.names - a.names).items() if k.lower() not in a.lowered})
    missing_q, added_q = a.quantifiers - b.quantifiers, b.quantifiers - a.quantifiers
    altered = (sum(missing_num.values()) + sum(added_num.values()) + sum(missing_names.values())
               + sum(added_names.values()) + abs(a.negations - b.negations)
               + sum(missing_q.values()) + sum(added_q.values()))
    return {
        "lang": lang,
        "words": a.words,
        "altered": altered,
        # half up, as JavaScript's Math.round does: Python's round() goes to even on .x5
        "per_1000_words": math.floor(10000 * altered / a.words + 0.5) / 10 if a.words else 0.0,
        "numbers": {"missing": sorted(_fmt(v) for v in missing_num.elements()),
                    "added": sorted(_fmt(v) for v in added_num.elements())},
        "names": {"missing": sorted(missing_names.elements()), "added": sorted(added_names.elements())},
        "negations": {"before": a.negations, "after": b.negations},
        "quantifiers": {"missing": sorted(missing_q.elements()), "added": sorted(added_q.elements())},
    }


def sentences(d: dict) -> list[str]:
    """The diff in plain words: a head line, then one line per kind of fact that changed."""
    def pair(label, part, fmt=str):
        bits = []
        if part["missing"]:
            bits.append("gone " + ", ".join(fmt(x) for x in part["missing"]))
        if part["added"]:
            bits.append("new " + ", ".join(fmt(x) for x in part["added"]))
        return f"{label}: {'; '.join(bits)}." if bits else None

    head = (f"{d['altered']} facts changed ({d['per_1000_words']:g} per 1,000 words)." if d["altered"]
            else "No number, name, negation or quantifier changed.")
    n = d["negations"]
    lines = [head, pair("Numbers", d["numbers"]), pair("Names", d["names"]),
             f"Negations: {n['before']} before, {n['after']} after." if n["before"] != n["after"] else None,
             pair("Quantifiers", d["quantifiers"], lambda q: q.replace("_", " "))]
    return [x for x in lines if x]
