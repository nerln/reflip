"""Turn a detector's score into an answer a person can act on, or a refusal.

No model is loaded here: this file reads the calibration that the benchmark fitted
(reflip/detect_calibration.json) and the numbers a detector produced, and decides what may
be said. The browser version does the same thing in JavaScript from the same JSON, and the
two are tested against each other, which is why the logic lives apart from the models.

The answer never says "AI" or "human" on its own. It says two things:

1. How many of the human texts we measured, at this length, scored at least as
   machine-like as this one. That needs no assumption about who usually sends texts to
   the tool, and it is the number that matters to a person being accused.
2. Whether the score crosses the threshold set to flag 1% of human texts, but only for a
   language and length where the benchmark showed the threshold catches machine text and
   flags at most 2% of human text even at the top of its interval. Elsewhere the tool
   refuses, and prints the numbers that made it refuse.

There is no probability. An earlier draft gave one under an assumed prior of one in two,
and the expansion council pointed out what a reader does with it: reads it as the chance
that a person cheated.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .detect import guess_language, word_count

CALIBRATION = Path(__file__).resolve().parent / "detect_calibration.json"
LANG_NAMES = {"en": "English", "it": "Italian", "es": "Spanish"}

VENDOR_NOTE = ("This cannot tell whether Claude or Gemini wrote a text from their watermarks: "
               "Anthropic's watermark (on Claude models launched since 2 August 2026) and "
               "Google's can only be read with secrets those companies keep.")


def load(path: Path = CALIBRATION) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def score_of(calib: dict, f: dict) -> float | None:
    """The calibrated detector's score from a features dict, higher meaning more machine-like."""
    name = calib["detector"]
    if name == "binoculars":
        return -f["binoculars"]
    if name == "fast_detectgpt":
        return f["fdg_oo"]
    if name == "fast_detectgpt_cross":
        return f["fdg_po"]
    if name == "perplexity":
        return -f["nll_obs"]
    if name == "burstiness":
        return None if f.get("burstiness") is None else -f["burstiness"]
    if name == "ppl_burstiness":
        raise ValueError("ppl_burstiness needs the bucket: use score_in_bucket")
    raise KeyError(name)


def score_in_bucket(calib: dict, f: dict, bucket: str) -> float | None:
    if calib["detector"] != "ppl_burstiness":
        return score_of(calib, f)
    p = calib["logistic"][bucket]
    burst = f["burstiness"] if f.get("burstiness") is not None else p["fill_burst"]
    return p["w_nll"] * f["nll_obs"] + p["w_burst"] * burst + p["bias"]


def bucket_for(words: int, calib: dict) -> str | None:
    for name, (lo, hi) in calib["words"].items():
        if lo <= words <= hi:
            return name
    # Longer than the longest measured texts: the detectors read 512 tokens anyway, so a
    # long text is scored on its opening and filed with the long ones.
    longest = max(calib["words"].items(), key=lambda kv: kv[1][1])
    if words > longest[1][1]:
        return longest[0]
    return None


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


def assess(text: str, features: dict | None, calib: dict, lang: str | None = None) -> dict:
    """The full answer for one text. `features` may be None when the text was refused early."""
    words = word_count(text)
    guessed, share = guess_language(text)
    lang = lang or guessed
    out = {"v": 1, "words": words, "language": lang, "language_confidence": round(share, 3),
           "detector": calib["detector"], "pair": calib["pair"], "note": VENDOR_NOTE,
           "verdict": None, "refused": None, "score": None, "human_tail": None, "cell": None}
    lo_words = min(lo for lo, _ in calib["words"].values())
    if words < lo_words:
        out["refused"] = (f"The text has {words} words. The shortest texts this was measured on had "
                          f"{lo_words}, and below that the scores were not checked against anything.")
        return out
    if lang not in LANG_NAMES:
        out["refused"] = ("The language could not be recognised as Italian, Spanish or English, "
                          "the only three this was measured on.")
        return out
    bucket = bucket_for(words, calib)
    out["bucket"] = bucket
    if features is None:
        return out
    s = score_in_bucket(calib, features, bucket)
    if s is None:
        out["refused"] = "The text has fewer than two sentences, so this detector has nothing to read."
        return out
    b = calib["buckets"][bucket]
    hs = b["human_scores"]
    k = sum(1 for v in hs if v >= s)
    lo, hi = wilson(k, len(hs))
    out["score"] = s
    out["human_tail"] = {"count": k, "of": len(hs), "share": k / len(hs), "low": lo, "high": hi}
    cell = calib["cells"].get(f"{lang}/{bucket}", {})
    out["cell"] = cell
    # second-language writers: measured apart, never calibrated on (PREREG amendment, point 3)
    out["learners"] = (calib.get("learners") or {}).get(f"human_l2/{lang}/{bucket}")
    if not cell.get("allowed"):
        out["refused"] = (f"No verdict for {LANG_NAMES[lang]} at this length ({bucket}): {cell.get('why', 'not measured')}. "
                          "The share of human texts below still holds.")
        return out
    out["verdict"] = "machine-like" if s > b["threshold"] else "no evidence"
    return out


def sentences(a: dict) -> list[str]:
    """The answer as a person reads it. The JSON carries the same facts as numbers."""
    lines = []
    if a.get("human_tail"):
        t = a["human_tail"]
        lines.append(f"Of {t['of']} human texts of this length that were measured, {t['count']} scored at "
                     f"least this machine-like ({t['share']:.1%}; 95% interval {t['low']:.1%} to {t['high']:.1%}).")
    cell = a.get("cell") or {}
    if a.get("verdict") == "machine-like":
        lines.append(f"Verdict: machine-like. The score is past a threshold that flagged at most "
                     f"{cell.get('fpr_upper', 0.02):.1%} of human texts in this language and length "
                     "(95% upper bound).")
    elif a.get("verdict") == "no evidence":
        lines.append("Verdict: no evidence of machine writing at the 1% threshold. That is not proof a "
                     "person wrote it.")
    if a.get("refused"):
        lines.append(a["refused"])
    if a.get("human_tail"):
        name = LANG_NAMES.get(a.get("language"), "this language")
        l2 = a.get("learners")
        if l2:
            lines.append(f"Essays by people writing {name} as a second language, at this length, crossed the "
                         f"threshold {l2['fp']} times in {l2['n']} ({l2['fpr']:.1%}; up to {l2['fpr_upper']:.1%}).")
        else:
            lines.append(f"Not measured on people writing {name} as a second language: no open corpus of "
                         "their texts at this length was found.")
    lines.append(a["note"])
    return lines
