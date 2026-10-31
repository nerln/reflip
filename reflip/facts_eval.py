"""Measure the facts check against blind annotators: docs/facts/PROTOCOL.md.

    python -m reflip.facts_eval sample      # draw the 120 pairs, write the annotation batches
    python -m reflip.facts_eval disagree    # after two annotations: what the third agent settles
    python -m reflip.facts_eval score       # after adjudication: the metrics
    python -m reflip.facts_eval score --half heldout   # the held-out half only

Annotations are written by Claude Sonnet agents into data/facts-eval/annotations/; this file
only samples, compares and counts.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from pathlib import Path

from .facts import diff as facts_diff

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "facts-eval"
RESULTS = ROOT / "data" / "results" / "facts-eval"
KINDS = ("numbers", "names", "negation", "quantifiers")
PER_STRATUM = 30
MIN_WORDS = 30
BATCH = 10
BLANK = re.compile(r"\n\s*\n")


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.is_file() else []


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in BLANK.split(text) if p.strip()]


def words(text: str) -> int:
    return len(re.findall(r"[^\W\d_]+", text))


def strata() -> dict[str, list[dict]]:
    """Every eligible paragraph pair, by stratum: (source id, paragraph index, texts, lang)."""
    corpus = {r["id"]: r for r in read_jsonl(ROOT / "data" / "corpus.jsonl")}
    ai = {r["id"]: r for r in read_jsonl(ROOT / "data" / "detect" / "ai.jsonl")}

    def pairs(rows, original_of, label):
        out = []
        for r in rows:
            src = original_of(r)
            if not src:
                continue
            a, b = paragraphs(src["text"]), paragraphs(r["text"])
            if len(a) != len(b):
                continue
            for i, (pa, pb) in enumerate(zip(a, b)):
                if words(pa) >= MIN_WORDS:
                    out.append({"stratum": label, "source": r["id"], "model": r.get("model", ""),
                                "paragraph": i, "lang": src.get("lang", "en"), "original": pa, "rewrite": pb})
        return out

    return {
        "paraphrase-before-guard": pairs(read_jsonl(ROOT / "data/results/main/paraphrase.jsonl"),
                                         lambda r: corpus.get(r["id"]), "paraphrase-before-guard"),
        "infill-with-guard": pairs(read_jsonl(ROOT / "data/results/facts/infill.jsonl"),
                                   lambda r: corpus.get(r["id"]), "infill-with-guard"),
        "browser": pairs(read_jsonl(ROOT / "data/results/browser-rewriters.jsonl"),
                         lambda r: corpus.get(r["id"]), "browser"),
        "it-es-rewrites": pairs([r for r in read_jsonl(ROOT / "data/detect/rewritten.jsonl") if r["lang"] in ("it", "es")],
                                lambda r: ai.get(r["source"]), "it-es-rewrites"),
    }


def cmd_sample(args) -> int:
    rng = random.Random(0)
    chosen = []
    for name, pool in strata().items():
        rng.shuffle(pool)
        picked = pool[:PER_STRATUM]
        if len(picked) < PER_STRATUM:
            print(f"{name}: only {len(picked)} eligible pairs", file=sys.stderr)
        halves = ["dev"] * (len(picked) // 2) + ["heldout"] * (len(picked) - len(picked) // 2)
        rng.shuffle(halves)
        for p, h in zip(picked, halves):
            chosen.append(dict(p, half=h))
    rng.shuffle(chosen)
    for k, p in enumerate(chosen, 1):
        p["id"] = f"fe-{k:03d}"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pairs.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in chosen))
    batches = OUT / "batches"
    batches.mkdir(exist_ok=True)
    for b in range(0, len(chosen), BATCH):
        blind = [{"id": p["id"], "lang": p["lang"], "original": p["original"], "rewrite": p["rewrite"]}
                 for p in chosen[b:b + BATCH]]
        (batches / f"batch-{b // BATCH + 1:02d}.json").write_text(json.dumps(blind, ensure_ascii=False, indent=1))
    by = {}
    for p in chosen:
        by.setdefault((p["stratum"], p["lang"], p["half"]), 0)
        by[(p["stratum"], p["lang"], p["half"])] += 1
    for k, v in sorted(by.items()):
        print(" ".join(k), v)
    print(f"{len(chosen)} pairs, {math.ceil(len(chosen) / BATCH)} batches in {batches}", file=sys.stderr)
    return 0


def changed(a: dict) -> dict[str, bool]:
    """Which of the four kinds an annotation says changed."""
    return {
        "numbers": bool(a["numbers"]["missing"] or a["numbers"]["added"]),
        "names": bool(a["names"]["missing"] or a["names"]["added"]),
        "negation": bool(a["negation_flip"]),
        "quantifiers": bool(a["quantifiers"]),
    }


def tool_changed(p: dict) -> dict[str, bool]:
    d = facts_diff(p["original"], p["rewrite"], p["lang"])
    return {
        "numbers": bool(d["numbers"]["missing"] or d["numbers"]["added"]),
        "names": bool(d["names"]["missing"] or d["names"]["added"]),
        "negation": d["negations"]["before"] != d["negations"]["after"],
        "quantifiers": bool(d["quantifiers"]["missing"] or d["quantifiers"]["added"]),
    }


def annotations(who: str) -> dict[str, dict]:
    out = {}
    for f in sorted((OUT / "annotations").glob(f"*-{who}.json")):
        for a in json.loads(f.read_text())["pairs"]:
            out[a["id"]] = a
    return out


def cmd_disagree(args) -> int:
    pairs = {p["id"]: p for p in read_jsonl(OUT / "pairs.jsonl")}
    a, b = annotations("a"), annotations("b")
    todo = []
    for pid, p in pairs.items():
        if pid not in a or pid not in b:
            print(f"{pid}: missing an annotation", file=sys.stderr)
            continue
        ca, cb = changed(a[pid]), changed(b[pid])
        kinds = [k for k in KINDS if ca[k] != cb[k]]
        if kinds:
            todo.append({"id": pid, "lang": p["lang"], "original": p["original"], "rewrite": p["rewrite"],
                         "disputed": kinds, "annotator_1": a[pid], "annotator_2": b[pid]})
    (OUT / "disputes.json").write_text(json.dumps(todo, ensure_ascii=False, indent=1))
    print(f"{len(todo)} pairs with a disputed kind, {sum(len(t['disputed']) for t in todo)} disputes", file=sys.stderr)
    return 0


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


def kappa(xs: list[bool], ys: list[bool]) -> float:
    n = len(xs)
    if not n:
        return float("nan")
    po = sum(x == y for x, y in zip(xs, ys)) / n
    px, py = sum(xs) / n, sum(ys) / n
    pe = px * py + (1 - px) * (1 - py)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def reference(pid: str, a: dict, b: dict, settled: dict) -> dict[str, bool]:
    ca, cb = changed(a[pid]), changed(b[pid])
    out = {}
    for k in KINDS:
        out[k] = ca[k] if ca[k] == cb[k] else bool(settled[pid][k])
    return out


def cmd_score(args) -> int:
    pairs = [p for p in read_jsonl(OUT / "pairs.jsonl") if args.half in ("all", p["half"])]
    a, b = annotations("a"), annotations("b")
    settled = {s["id"]: s for s in json.loads((OUT / "settled.json").read_text())["pairs"]} \
        if (OUT / "settled.json").is_file() else {}
    rows = []
    for p in pairs:
        if p["id"] not in a or p["id"] not in b:
            continue
        ca, cb = changed(a[p["id"]]), changed(b[p["id"]])
        if any(ca[k] != cb[k] for k in KINDS) and p["id"] not in settled:
            print(f"{p['id']}: dispute not settled yet", file=sys.stderr)
            return 1
        ref = reference(p["id"], a, b, settled)
        other = bool(a[p["id"]]["other"]) and bool(b[p["id"]]["other"])
        rows.append({"id": p["id"], "stratum": p["stratum"], "lang": p["lang"], "ref": ref,
                     "tool": tool_changed(p), "other": other, "a": ca, "b": cb})

    def block(kind):
        get = (lambda r, s: any(r[s].values())) if kind == "any" else (lambda r, s: r[s][kind])
        tp = sum(get(r, "tool") and get(r, "ref") for r in rows)
        fp = sum(get(r, "tool") and not get(r, "ref") for r in rows)
        fn = sum(not get(r, "tool") and get(r, "ref") for r in rows)
        prec = tp / (tp + fp) if tp + fp else float("nan")
        rec = tp / (tp + fn) if tp + fn else float("nan")
        out = {"tp": tp, "fp": fp, "fn": fn, "precision": prec, "precision_ci": wilson(tp, tp + fp),
               "recall": rec, "recall_ci": wilson(tp, tp + fn)}
        if kind != "any":
            out["kappa"] = kappa([r["a"][kind] for r in rows], [r["b"][kind] for r in rows])
        return out

    invisible = sum(r["other"] and not any(r["ref"].values()) for r in rows)
    summary = {"half": args.half, "pairs": len(rows), "kinds": {k: block(k) for k in KINDS + ("any",)},
               "outside_the_four": {"count": invisible, "share": invisible / len(rows) if rows else float("nan"),
                                    "ci": wilson(invisible, len(rows))},
               "by_stratum": {s: len([r for r in rows if r["stratum"] == s]) for s in sorted({r["stratum"] for r in rows})}}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"summary-{args.half}.json").write_text(json.dumps(summary, indent=1))
    (RESULTS / f"rows-{args.half}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    lines = [f"# Facts check against blind annotators ({args.half}, {len(rows)} pairs)", "",
             "| kind | precision (95%) | recall (95%) | tp | fp | fn | annotator kappa |", "|---|---|---|---|---|---|---|"]
    for k, v in summary["kinds"].items():
        lines.append(f"| {k} | {v['precision']:.2f} ({v['precision_ci'][0]:.2f}-{v['precision_ci'][1]:.2f}) | "
                     f"{v['recall']:.2f} ({v['recall_ci'][0]:.2f}-{v['recall_ci'][1]:.2f}) | {v['tp']} | {v['fp']} | {v['fn']} | "
                     f"{v.get('kappa', float('nan')):.2f} |")
    o = summary["outside_the_four"]
    lines += ["", f"Pairs whose meaning changed only outside the four kinds (both annotators agree): "
                  f"{o['count']} of {len(rows)} ({o['share']:.0%}, {o['ci'][0]:.0%} to {o['ci'][1]:.0%})."]
    (RESULTS / f"summary-{args.half}.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reflip-facts-eval", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sample").set_defaults(fn=cmd_sample)
    sub.add_parser("disagree").set_defaults(fn=cmd_disagree)
    s = sub.add_parser("score")
    s.add_argument("--half", choices=["all", "dev", "heldout"], default="all")
    s.set_defaults(fn=cmd_score)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
