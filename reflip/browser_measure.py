"""Score what the browser's rewriters wrote, the way the benchmark scores the command line.

web/measure-rewriters.mjs runs each browser model over the 24 watermarked benchmark texts in
headless Chrome on WebGPU and saves the output to data/results/browser-rewriters.jsonl. This
reads it back and computes the same numbers as the README's main table, with the same
detector, key and tokenizer, plus the facts check, then writes the summary the page shows
(docs/app/rewriters-measured.json).

    python -m reflip.browser_measure            # the browser rows
    python -m reflip.browser_measure --main     # facts changed per 1,000 words for every
                                                # transform in data/results/main
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .facts import diff as facts_diff
from .words import word_edit_ratio

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "data" / "corpus.jsonl"
BROWSER = ROOT / "data" / "results" / "browser-rewriters.jsonl"
SUMMARY = ROOT / "docs" / "app" / "rewriters-measured.json"
THRESHOLD = 4.0


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.is_file() else []


def watermarked() -> dict[str, dict]:
    return {r["id"]: r for r in read_jsonl(CORPUS) if r.get("watermarked")}


def facts_rate(pairs: list[tuple[str, str, str]]) -> tuple[float, int, int]:
    """Facts changed per 1,000 words of the originals, over (original, rewritten, lang) pairs."""
    altered = words = 0
    for a, b, lang in pairs:
        d = facts_diff(a, b, lang)
        altered += d["altered"]
        words += d["words"]
    return (1000 * altered / words if words else 0.0), altered, words


def cmd_main(args) -> int:
    corpus = watermarked()
    print("| transform | facts changed per 1,000 words | texts |")
    print("|---|---|---|")
    for f in sorted((ROOT / "data" / "results" / "main").glob("*.jsonl")):
        rows = [r for r in read_jsonl(f) if r.get("id") in corpus and "text" in r]
        if not rows:
            continue
        rate, _, _ = facts_rate([(corpus[r["id"]]["text"], r["text"], corpus[r["id"]].get("lang", "en")) for r in rows])
        print(f"| {f.stem} | {rate:.1f} | {len(rows)} |")
    return 0


def cmd_browser(args) -> int:
    from transformers import AutoTokenizer

    from .synthid import Scorer, intact_fraction

    corpus = watermarked()
    rows = read_jsonl(BROWSER)
    if not rows:
        print("nothing measured yet: run web/measure-rewriters.mjs", file=sys.stderr)
        return 1
    tokenizers: dict[str, Scorer] = {}
    out: dict[str, list[dict]] = {}
    for r in rows:
        rec = corpus[r["id"]]
        name = rec.get("model", "Qwen/Qwen2.5-1.5B-Instruct")
        if name not in tokenizers:
            tokenizers[name] = Scorer(AutoTokenizer.from_pretrained(name))
        sc = tokenizers[name]
        new_ids = sc.encode(r["text"])
        d = facts_diff(rec["text"], r["text"], rec.get("lang", "en"))
        out.setdefault(r["model"], []).append({
            "id": r["id"], "z_before": sc.score_ids(rec["ids"]).z, "z_after": sc.score_ids(new_ids).z,
            "intact": intact_fraction(rec["ids"], new_ids, sc.ngram_len),
            "edit_ratio": word_edit_ratio(rec["text"], r["text"]),
            "facts": d["altered"], "words": d["words"], "seconds": r["seconds"]})

    def mean(xs):
        return sum(xs) / len(xs) if xs else None

    models = {}
    for m, rs in out.items():
        words = sum(x["words"] for x in rs)
        models[m] = {
            "texts": len(rs),
            "z_before": round(mean([x["z_before"] for x in rs]), 2),
            "z_after": round(mean([x["z_after"] for x in rs]), 2),
            "z_after_max": round(max(x["z_after"] for x in rs), 2),
            "below_threshold": sum(1 for x in rs if x["z_after"] < THRESHOLD),
            "intact": round(mean([x["intact"] for x in rs]), 3),
            "edit_ratio": round(mean([x["edit_ratio"] for x in rs]), 3),
            "facts_per_1000_words": round(1000 * sum(x["facts"] for x in rs) / words, 1) if words else None,
            "seconds_per_text": round(mean([x["seconds"] for x in rs]), 1),
        }
    SUMMARY.write_text(json.dumps({
        "v": 1, "threshold": THRESHOLD, "corpus": "data/corpus.jsonl (24 watermarked texts)",
        "how": "web/measure-rewriters.mjs in headless Chrome 152 on WebGPU (Apple M-series), "
               "scored by reflip.browser_measure with the benchmark's detector and key",
        "models": models}, indent=1) + "\n")
    print("| browser model | z before | z after (mean) | z after (max) | z below 4 | positions intact | "
          "facts changed per 1,000 words | words changed | seconds per text |")
    print("|---|---|---|---|---|---|---|---|---|")
    for m, s in models.items():
        print(f"| {m} | {s['z_before']} | {s['z_after']} | {s['z_after_max']} | {s['below_threshold']} of "
              f"{s['texts']} | {s['intact']} | {s['facts_per_1000_words']} | {s['edit_ratio']:.0%} | {s['seconds_per_text']} |")
    print(f"\nwrote {SUMMARY}", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reflip-browser-measure", description=__doc__.split("\n\n")[0])
    ap.add_argument("--main", action="store_true", help="facts column for the main table instead")
    args = ap.parse_args(argv)
    return cmd_main(args) if args.main else cmd_browser(args)


if __name__ == "__main__":
    sys.exit(main())
