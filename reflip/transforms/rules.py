"""Rule-based, meaning-preserving edits that change tokens without any model.

Why: every token you change re-randomises its own g-value and the ngram_len-1 after it,
so cheap deterministic edits (contractions, US/UK spelling, dashes, stock phrases) buy
coverage for free before a model is asked to do anything. Alone they are too sparse to
remove a watermark from long text (the benchmark shows how far they get); in the hybrid
transform they reduce how many words the model has to touch.

Every rule is `fn(segment) -> (new_segment, edits)` and only ever sees text outside the
protected spans (fenced code, inline code, URLs, e-mails, file paths).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Callable

from ..words import words
from . import Options, TransformResult, register

RuleFn = Callable[[str], tuple[str, int]]


@dataclass(frozen=True)
class Rule:
    name: str
    fn: RuleFn
    languages: tuple[str, ...] = ("en",)


# --------------------------------------------------------------------------- protected spans
_PROTECTED = re.compile(
    r"```.*?```"                       # fenced code
    r"|`[^`\n]+`"                       # inline code
    r"|https?://\S+|www\.\S+"           # URLs
    r"|[\w.+-]+@[\w-]+\.[\w.-]+"        # e-mails
    # File paths, in the two shapes people write them. The Unix one has been here from the
    # start; the Windows one was missing in both this module and llm.py, so a rule could
    # flip the spelling of a directory name and hand back a path to a file nobody has.
    # A segment allows one balanced (...) group, and a space directly before one ("report
    # (draft).docx", the "(x86)" half of "Program Files (x86)"): see llm.py's
    # _WINDOWS_PATH_RE for why a bare, un-parenthesised space still ends the segment.
    r"""|(?<![A-Za-z0-9])[A-Za-z]:[\\/](?:[^\s<>\[\]]|(?: +[\w(][^\s<>\[\]/\\:]*){1,3}(?=[\\/])|(?: +[^\s<>\[\]/\\:]*\.[A-Za-z0-9]{1,8})(?![^\s<>\[\]]))*|\\\\[^\s<>\[\]/\\:]+(?:\\(?:[^\s<>\[\]]|(?: +[\w(][^\s<>\[\]/\\:]*){1,3}(?=[\\/])|(?: +[^\s<>\[\]/\\:]*\.[A-Za-z0-9]{1,8})(?![^\s<>\[\]]))*)+"""
    r"""|(?<![\w/:~.])(?:~|\.{1,2})?/(?:[\w.\-]|\([^\s<>()\[\]]*\)|(?: +[\w(][\w.\-()]*){1,3}(?=/)|(?: +[^\s<>\[\]/\\:]*\.[A-Za-z0-9]{1,8})(?![^\s<>\[\]]))+(?:/(?:[\w.\-]|\([^\s<>()\[\]]*\)|(?: +[\w(][\w.\-()]*){1,3}(?=/)|(?: +[^\s<>\[\]/\\:]*\.[A-Za-z0-9]{1,8})(?![^\s<>\[\]]))+)*/?"""
    , re.S,
)


def _apply_outside_protected(text: str, fn: RuleFn) -> tuple[str, int]:
    out = []
    n = 0
    pos = 0
    for m in _PROTECTED.finditer(text):
        seg, k = fn(text[pos:m.start()])
        out.append(seg)
        n += k
        out.append(m.group(0))
        pos = m.end()
    seg, k = fn(text[pos:])
    out.append(seg)
    n += k
    return "".join(out), n


def _match_case(src: str, repl: str) -> str:
    if src.isupper() and len(src) > 1:
        return repl.upper()
    if src[:1].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


def _sub_count(pattern: re.Pattern, repl, text: str) -> tuple[str, int]:
    count = 0

    def _r(m):
        nonlocal count
        r = repl(m) if callable(repl) else m.expand(repl)
        if r != m.group(0):
            count += 1
        return r

    return pattern.sub(_r, text), count


# --------------------------------------------------------------------------- rules
_DASH = re.compile(r"(?<=[^\s\d,;:(\[])[ \t]*[—–][ \t]*(?=[^\s\d,;:)\]])")  # stylecheck: allow, the pattern this rule removes


def rule_dashes(seg: str) -> tuple[str, int]:
    return _sub_count(_DASH, ", ", seg)


_TYPO = {"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "‚": "'",
         "…": "...", "‑": "-", "‐": "-"}
_TYPO_RE = re.compile("|".join(map(re.escape, _TYPO)))


def rule_typography(seg: str) -> tuple[str, int]:
    return _sub_count(_TYPO_RE, lambda m: _TYPO[m.group(0)], seg)


_EXPAND = {
    "don't": "do not", "doesn't": "does not", "didn't": "did not", "can't": "cannot",
    "won't": "will not", "isn't": "is not", "aren't": "are not", "wasn't": "was not",
    "weren't": "were not", "hasn't": "has not", "haven't": "have not", "hadn't": "had not",
    "wouldn't": "would not", "couldn't": "could not", "shouldn't": "should not",
    "i'm": "I am", "you're": "you are", "we're": "we are", "they're": "they are",
    "it's": "it is", "i've": "I have", "you've": "you have", "we've": "we have",
    "they've": "they have", "i'll": "I will", "you'll": "you will", "we'll": "we will",
    "they'll": "they will", "he'll": "he will", "she'll": "she will", "it'll": "it will",
    "let's": "let us",
}
# contract only the unambiguous expansions (not "it is" -> "it's", which is often wrong in register)
_CONTRACT = {v: k for k, v in _EXPAND.items() if k not in ("it's",)}
_CONTRACT = {k.lower(): v for k, v in _CONTRACT.items()}
_CONTR_RE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(k) for k in list(_EXPAND) + list(_CONTRACT)), key=len, reverse=True)) + r")\b",
    re.I,
)


def _contraction(m: re.Match) -> str:
    src = m.group(0)
    key = src.lower().replace("’", "'")
    if key in _EXPAND:
        out = _EXPAND[key]
    elif key in _CONTRACT:
        out = _CONTRACT[key]
    else:
        return src
    if out.startswith("I ") or out == "I":
        return out if src[:1].isupper() or src.lower().startswith("i") else out
    return _match_case(src, out)


def rule_contractions(seg: str) -> tuple[str, int]:
    return _sub_count(_CONTR_RE, _contraction, seg.replace("’", "'"))


_SERIAL = re.compile(r"\b(\w+), (\w+), (and|or) (\w+)\b")


def rule_serial_comma(seg: str) -> tuple[str, int]:
    return _sub_count(_SERIAL, r"\1, \2 \3 \4", seg)


_SPELL_PAIRS = [
    ("color", "colour"), ("favorite", "favourite"), ("honor", "honour"), ("behavior", "behaviour"),
    ("center", "centre"), ("theater", "theatre"), ("meter", "metre"), ("analyze", "analyse"),
    ("organize", "organise"), ("realize", "realise"), ("recognize", "recognise"),
    ("apologize", "apologise"), ("criticize", "criticise"), ("minimize", "minimise"),
    ("optimize", "optimise"), ("prioritize", "prioritise"), ("summarize", "summarise"),
    ("emphasize", "emphasise"), ("defense", "defence"), ("offense", "offence"),
    ("catalog", "catalogue"), ("dialog", "dialogue"), ("gray", "grey"), ("traveling", "travelling"),
    ("traveled", "travelled"), ("canceled", "cancelled"), ("modeling", "modelling"),
    ("labeled", "labelled"), ("fulfill", "fulfil"), ("enroll", "enrol"), ("skillful", "skilful"),
    ("jewelry", "jewellery"), ("pajamas", "pyjamas"), ("aluminum", "aluminium"),
    ("mustache", "moustache"), ("neighbor", "neighbour"), ("labor", "labour"), ("flavor", "flavour"),
    ("humor", "humour"), ("rumor", "rumour"), ("vapor", "vapour"), ("mold", "mould"),
    ("plow", "plough"), ("harbor", "harbour"), ("armor", "armour"), ("liter", "litre"),
    ("fiber", "fibre"), ("saber", "sabre"), ("civilization", "civilisation"),
    ("organization", "organisation"), ("realization", "realisation"), ("customize", "customise"),
    ("memorize", "memorise"), ("maximize", "maximise"), ("utilize", "utilise"),
]
_SUFFIXES = ["", "s", "d", "ed", "ing", "r", "rs", "ful", "fully", "less"]


def _spell_forms(us: str, uk: str) -> list[tuple[str, str]]:
    forms = []
    for suf in _SUFFIXES:
        if suf in ("d", "r", "rs") and not us.endswith("e"):
            continue
        if suf in ("ed",) and us.endswith("e"):
            continue
        if suf == "ing":
            forms.append((us[:-1] + "ing" if us.endswith("e") else us + "ing",
                          uk[:-1] + "ing" if uk.endswith("e") else uk + "ing"))
            continue
        forms.append((us + suf, uk + suf))
    return forms


_US2UK: dict[str, str] = {}
for _us, _uk in _SPELL_PAIRS:
    for a, b in _spell_forms(_us, _uk):
        _US2UK.setdefault(a, b)
_UK2US = {b: a for a, b in _US2UK.items()}
_SPELL_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, list(_US2UK) + list(_UK2US)), key=len, reverse=True)) + r")\b", re.I)


def rule_spelling(seg: str) -> tuple[str, int]:
    hits = [m.group(0).lower() for m in _SPELL_RE.finditer(seg)]
    if not hits:
        return seg, 0
    us = sum(h in _US2UK for h in hits)
    uk = sum(h in _UK2US for h in hits)
    table = _US2UK if us >= uk else _UK2US

    def _r(m):
        k = m.group(0).lower()
        return _match_case(m.group(0), table[k]) if k in table else m.group(0)

    return _sub_count(_SPELL_RE, _r, seg)


_PHRASES = {
    "in order to": "to", "utilize": "use", "utilise": "use", "e.g.,": "for example,",
    "e.g.": "for example", "i.e.,": "that is,", "i.e.": "that is", "for instance": "for example",
    "additionally,": "also,", "furthermore,": "also,", "moreover,": "also,", "therefore": "so",
    "in addition,": "also,", "a number of": "several", "due to the fact that": "because",
    "at this point in time": "now", "prior to": "before", "subsequent to": "after",
    "in the event that": "if", "whether or not": "whether", "each and every": "every",
    "it is important to note that": "note that", "it's worth noting that": "notably,",  # stylecheck: allow, a phrase this rule replaces
    "in conclusion,": "to sum up,", "delve into": "dig into", "crucial": "key",
    "seamless": "smooth", "robust": "solid", "a wide range of": "many", "in today's world": "today",
    "plays a vital role": "matters", "it is essential to": "you must", "ensure that": "make sure that",
    "individuals": "people", "assist": "help", "commence": "begin", "endeavor": "try",
    "endeavour": "try", "numerous": "many", "obtain": "get", "sufficient": "enough",
    "terminate": "end", "additional": "extra", "approximately": "about", "demonstrate": "show",
    "facilitate": "help", "regarding": "about", "subsequently": "later", "nevertheless,": "still,",
    "consequently,": "so,", "leverage": "use", "in essence": "essentially", "with regard to": "about",
    "in terms of": "for", "on a daily basis": "daily", "the majority of": "most",
    "a variety of": "various", "in spite of": "despite", "as a result,": "so,", "in the process of": "while",
}


def _phrase_pattern(k: str) -> str:
    tail = "" if not k[-1].isalnum() else r"\b"
    return r"\b" + re.escape(k) + tail


_PHRASE_RE = re.compile("|".join(_phrase_pattern(k) for k in sorted(_PHRASES, key=len, reverse=True)), re.I)


def rule_phrases(seg: str) -> tuple[str, int]:
    return _sub_count(_PHRASE_RE, lambda m: _match_case(m.group(0), _PHRASES[m.group(0).lower()]), seg)


_PERCENT = re.compile(r"\b(\d+(?:\.\d+)?) percent\b")
_THOUSANDS = re.compile(r"(?<![\d.,:/])\d{1,3}(?:,\d{3})+(?![\d,:/])")


def rule_numbers(seg: str) -> tuple[str, int]:
    seg, a = _sub_count(_PERCENT, r"\1%", seg)
    seg, b = _sub_count(_THOUSANDS, lambda m: m.group(0).replace(",", ""), seg)
    return seg, a + b


RULES: list[Rule] = [
    Rule("dashes", rule_dashes, ("en", "it", "*")),
    Rule("typography", rule_typography, ("en", "it", "*")),
    Rule("contractions", rule_contractions),
    Rule("serial_comma", rule_serial_comma),
    Rule("spelling", rule_spelling),
    Rule("phrases", rule_phrases),
    Rule("numbers", rule_numbers),
]


def apply_rules(text: str, names: tuple[str, ...] | list[str] = (), language: str = "en") -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for rule in RULES:
        if names and rule.name not in names:
            continue
        if language not in rule.languages and "*" not in rule.languages:
            continue
        text, n = _apply_outside_protected(text, rule.fn)
        counts[rule.name] = n
    return text, counts


@register("rules")
def rules_transform(text: str, opts: Options) -> TransformResult:
    new, counts = apply_rules(text, tuple(opts.rules), opts.language)
    total = sum(counts.values())
    n_words = max(1, len(words(text)))
    return TransformResult(text=new, edits=total, notes={"rules": counts, "density": round(100 * total / n_words, 2)})
