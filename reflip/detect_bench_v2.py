"""The second detection round: docs/detect/PREREG-v2.md.

    python -m reflip.detect_bench_v2 score --pair qwen2.5-1.5b --limit 150
    python -m reflip.detect_bench_v2 score --pair qwen2.5-0.5b-q4f16 --limit 150
    python -m reflip.detect_bench_v2 evaluate

What is fixed in the protocol is fixed here too: Binoculars only, the two pairs the first round
chose, a threshold at the 99.5th percentile of the calibration humans of each length (the 99th
reported beside it), and the first round's rule. Nothing here chooses a detector or a pair.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

from .detect_bench import (BUCKETS, DETECTORS, LANGS, allowed, auroc, boot_auroc, cp_upper,
                           quantile, read_jsonl)

ROOT = Path(__file__).resolve().parent.parent
V1 = ROOT / "data" / "detect"
V2 = V1 / "v2"
RESULTS = ROOT / "data" / "results" / "detect-v2"
PAIRS = ("qwen2.5-1.5b", "qwen2.5-0.5b-q4f16")
DETECTOR = "binoculars"
CALIB_PER_CELL = 250
Q_MAIN, Q_SECOND = 0.995, 0.99
V1_VERDICTS = {"qwen2.5-1.5b": 1, "qwen2.5-0.5b-q4f16": 0}   # cells the first round allowed
CALIBRATION = {"qwen2.5-1.5b": ROOT / "reflip" / "detect_calibration.json",
               "qwen2.5-0.5b-q4f16": ROOT / "docs" / "app" / "calibration-browser.json"}


def corpus() -> list[dict]:
    rows = (read_jsonl(V2 / "humans.jsonl") + read_jsonl(V2 / "ai.jsonl")
            + read_jsonl(V2 / "rewritten.jsonl") + read_jsonl(V2 / "learners.jsonl"))
    # the first round's English and Spanish learners, scored again under the new threshold
    rows += [r for r in read_jsonl(V1 / "learners.jsonl") if r["lang"] in ("en", "es")]
    return [r for r in rows if r.get("bucket")]


def split(rows: list[dict]) -> None:
    """250 humans per cell for calibration, seed 10; every other text is test."""
    rng = random.Random(10)
    for r in rows:
        r["half"] = "test"
    for lang in LANGS:
        for b in BUCKETS:
            cell = sorted((r for r in rows if r["kind"] == "human" and r["lang"] == lang and r["bucket"] == b),
                          key=lambda r: r["id"])
            rng.shuffle(cell)
            for r in cell[:CALIB_PER_CELL]:
                r["half"] = "calib"


def scores(pair: str) -> dict[str, dict]:
    out = {}
    for f in (V1 / f"scores-{pair}.jsonl", V2 / f"scores-{pair}.jsonl"):
        for r in read_jsonl(f):
            if "error" not in r:
                out[r["id"]] = r
    return out


def cmd_score(args) -> int:
    from .detect import make_detector

    done = set(scores(args.pair)) | {r["id"] for r in read_jsonl(V2 / f"scores-{args.pair}.jsonl")}
    todo = [r for r in corpus() if r["id"] not in done]
    if not todo:
        print("nothing to score", file=sys.stderr)
        return 0
    if args.limit:
        todo = todo[:args.limit]     # a fresh process per batch: see detect_bench.cmd_score
    det = make_detector(args.pair)
    V2.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with (V2 / f"scores-{args.pair}.jsonl").open("a") as f:
        for n, r in enumerate(todo, 1):
            try:
                feats = det.features(r["text"]).to_dict()
            except ValueError as e:
                feats = {"error": str(e)}
            f.write(json.dumps({"id": r["id"], **feats}) + "\n")
            if n % 50 == 0:
                f.flush()
                print(f"{args.pair}: {n}/{len(todo)} in {time.time() - t0:.0f}s", file=sys.stderr)
    return 0


def evaluate_pair(pair: str, rows: list[dict]) -> dict:
    S = scores(pair)
    data = [r for r in rows if r["id"] in S]

    def s(r):
        return DETECTORS[DETECTOR](S[r["id"]])

    rng = random.Random(0)
    thr = {}
    for b in BUCKETS:
        cal = [s(r) for r in data if r["half"] == "calib" and r["kind"] == "human" and r["bucket"] == b]
        thr[b] = {"main": quantile(cal, Q_MAIN), "second": quantile(cal, Q_SECOND), "n_calib": len(cal),
                  "human_scores": sorted(cal)}
    test = [r for r in data if r["half"] == "test"]

    def at(pos, neg, t):
        tp, fp = sum(v > t for v in pos), sum(v > t for v in neg)
        return {"tpr": tp / len(pos) if pos else float("nan"), "fp": fp,
                "fpr": fp / len(neg) if neg else float("nan"), "fpr_upper": cp_upper(fp, len(neg)) if neg else None}

    cells = {}
    for lang in LANGS:
        for b in BUCKETS:
            neg = [s(r) for r in test if r["kind"] == "human" and r["lang"] == lang and r["bucket"] == b]
            pos = [s(r) for r in test if r["kind"] == "ai" and r["lang"] == lang and r["bucket"] == b]
            c = {"n_human": len(neg), "n_ai": len(pos)}
            if len(pos) >= 5 and len(neg) >= 5:
                lo, hi = boot_auroc(pos, neg, rng)
                c.update(auroc=auroc(pos, neg), auroc_low=lo, auroc_high=hi)
                c.update(at(pos, neg, thr[b]["main"]))
                c["second"] = at(pos, neg, thr[b]["second"])
            ok, why = allowed(c)
            c["allowed"], c["why"] = ok, why
            cells[f"{lang}/{b}"] = c
    gens = {}
    for b in BUCKETS:
        neg = [s(r) for r in test if r["kind"] == "human" and r["bucket"] == b]
        for g in sorted({r.get("generator") for r in test if r["kind"] == "ai"} - {None}):
            pos = [s(r) for r in test if r["kind"] == "ai" and r["bucket"] == b and r.get("generator") == g]
            if len(pos) >= 5:
                lo, hi = boot_auroc(pos, neg, rng)
                gens[f"{g}/{b}"] = {"n": len(pos), "auroc": auroc(pos, neg), "auroc_low": lo, "auroc_high": hi,
                                    "tpr": at(pos, neg, thr[b]["main"])["tpr"]}
    rewritten = {}
    for b in BUCKETS:
        neg = [s(r) for r in test if r["kind"] == "human" and r["bucket"] == b]
        pos = [s(r) for r in test if r["kind"] == "ai_reflip" and r["bucket"] == b]
        if len(pos) >= 5:
            rewritten[b] = {"n": len(pos), "auroc": auroc(pos, neg), "tpr": at(pos, neg, thr[b]["main"])["tpr"]}
    learners = {}
    for kind in ("human_l2", "human_l2_corrected"):
        for lang in LANGS:
            for b in BUCKETS:
                v = [s(r) for r in test if r["kind"] == kind and r["lang"] == lang and r["bucket"] == b]
                if v:
                    m, sec = sum(x > thr[b]["main"] for x in v), sum(x > thr[b]["second"] for x in v)
                    learners[f"{kind}/{lang}/{b}"] = {"n": len(v), "fp": m, "fpr": m / len(v),
                                                       "fpr_upper": cp_upper(m, len(v)),
                                                       "fp_second": sec, "fpr_second": sec / len(v)}
    return {"pair": pair, "thresholds": thr, "cells": cells, "generators": gens, "rewritten": rewritten,
            "learners": learners, "verdicts": sum(c["allowed"] for c in cells.values())}


def table(ev: dict) -> str:
    out = ["| cell | AUROC (95%) | machine caught | humans flagged | upper bound | verdict | at 99% (secondary) |",
           "|---|---|---|---|---|---|---|"]
    for k, c in ev["cells"].items():
        lang, b = k.split("/")
        if "auroc" not in c:
            out.append(f"| {lang} {b} | - | - | - | - | refused: {c['why']} | - |")
            continue
        sec = c["second"]
        out.append(f"| {lang} {b} | {c['auroc']:.2f} ({c['auroc_low']:.2f}-{c['auroc_high']:.2f}) | {c['tpr']:.0%} of {c['n_ai']} | "
                   f"{c['fp']} of {c['n_human']} | {c['fpr_upper']:.1%} | {'given' if c['allowed'] else 'refused: ' + c['why']} | "
                   f"catches {sec['tpr']:.0%}, flags {sec['fp']} (up to {sec['fpr_upper']:.1%}) |")
    return "\n".join(out)


def calibration(ev: dict) -> dict:
    """What `reflip detect` and the page ship with, in the first round's format."""
    keep = ("allowed", "why", "auroc", "auroc_low", "tpr", "fpr", "fpr_upper", "n_human")
    return {"v": 2, "pair": ev["pair"], "detector": DETECTOR, "fpr": round(1 - Q_MAIN, 4),
            "protocol": "docs/detect/PREREG-v2.md",
            "buckets": {b: {"threshold": t["main"], "human_scores": t["human_scores"]} for b, t in ev["thresholds"].items()},
            "cells": {k: {kk: c.get(kk) for kk in keep} for k, c in ev["cells"].items()},
            "learners": {k: v for k, v in ev["learners"].items() if k.startswith("human_l2/")},
            "logistic": None, "words": {k: list(v) for k, v in BUCKETS.items()}}


def cmd_evaluate(args) -> int:
    rows = corpus()
    split(rows)
    RESULTS.mkdir(parents=True, exist_ok=True)
    md = ["# Detection, second round", "",
          "Protocol: docs/detect/PREREG-v2.md. Binoculars; threshold at the 99.5th percentile of the calibration "
          "humans of each length; every number from the test half.", ""]
    out = {}
    for pair in PAIRS:
        if not (V2 / f"scores-{pair}.jsonl").is_file():
            continue
        ev = evaluate_pair(pair, rows)
        out[pair] = ev
        ships = ev["verdicts"] > V1_VERDICTS[pair]
        md += [f"## {pair}: {ev['verdicts']} cells with a verdict (first round: {V1_VERDICTS[pair]})", "", table(ev), "",
               "| generator | bucket | n | AUROC | caught |", "|---|---|---|---|---|"]
        md += [f"| {k.split('/')[0]} | {k.split('/')[1]} | {g['n']} | {g['auroc']:.2f} ({g['auroc_low']:.2f}-{g['auroc_high']:.2f}) "
               f"| {g['tpr']:.0%} |" for k, g in ev["generators"].items()]
        md += ["", "| second-language writers | n | flagged at 99.5% | upper bound | flagged at 99% |", "|---|---|---|---|---|"]
        md += [f"| {k} | {v['n']} | {v['fp']} ({v['fpr']:.1%}) | {v['fpr_upper']:.1%} | {v['fp_second']} ({v['fpr_second']:.1%}) |"
               for k, v in ev["learners"].items()]
        md += ["", "| reflip-rewritten | n | AUROC | caught |", "|---|---|---|---|"]
        md += [f"| {b} | {v['n']} | {v['auroc']:.2f} | {v['tpr']:.0%} |" for b, v in ev["rewritten"].items()]
        md += ["", f"Ships: {'yes, more verdicts than the first round' if ships else 'no, the first round keeps its calibration'}.", ""]
        if ships and not args.dry_run:
            CALIBRATION[pair].write_text(json.dumps(calibration(ev)))
    slim = {}
    for p, ev in out.items():
        slim[p] = {k: v for k, v in ev.items() if k != "thresholds"}
        slim[p]["thresholds"] = {b: {k: v for k, v in t.items() if k != "human_scores"} for b, t in ev["thresholds"].items()}
    (RESULTS / "summary.json").write_text(json.dumps(slim, indent=1))
    (RESULTS / "summary.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reflip-detect-bench-v2", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--pair", choices=PAIRS, required=True)
    s.add_argument("--limit", type=int, default=0)
    s.set_defaults(fn=cmd_score)
    e = sub.add_parser("evaluate")
    e.add_argument("--dry-run", action="store_true", help="write the summary, never the shipped calibration")
    e.set_defaults(fn=cmd_evaluate)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
