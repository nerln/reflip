"""Measure the detectors on the corpus, the way docs/detect/PREREG.md says, and fit what the
command line needs to give a calibrated answer.

    python -m reflip.detect_bench score --pair qwen2.5-0.5b
    python -m reflip.detect_bench score --pair qwen2.5-1.5b
    python -m reflip.detect_bench evaluate

`score` reads every text once per model pair and keeps only numbers. `evaluate` splits each
language and length in half with seed 0, fits thresholds and probability maps on one half,
and reports every figure from the other. It writes the tables to data/results/detect/ and the
calibration the command line ships with to reflip/detect_calibration.json.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

from .detect import ONNX_PAIRS, PAIRS

ALL_PAIRS = {**PAIRS, **ONNX_PAIRS}
from .detect_corpus import BUCKETS, LANGS, path, read_jsonl

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "results" / "detect"
CALIBRATION = Path(__file__).resolve().parent / "detect_calibration.json"
BROWSER_CALIBRATION = Path(__file__).resolve().parent.parent / "docs" / "app" / "calibration-browser.json"
BOOT = 2000
FPR = 0.01

# Every score is oriented so that higher means more machine-like.
DETECTORS = {
    "binoculars": lambda f: -f["binoculars"],
    "fast_detectgpt": lambda f: f["fdg_oo"],
    "fast_detectgpt_cross": lambda f: f["fdg_po"],
    "perplexity": lambda f: -f["nll_obs"],
    "burstiness": lambda f: None if f["burstiness"] is None else -f["burstiness"],
    # "ppl_burstiness" is fitted, see fit_logistic; it is added after the split.
}


def corpus() -> list[dict]:
    rows = (read_jsonl(path("humans.jsonl")) + read_jsonl(path("ai.jsonl"))
            + read_jsonl(path("rewritten.jsonl")) + read_jsonl(path("learners.jsonl")))
    return [r for r in rows if r.get("bucket")]


HUMANS_CALIB = 100   # per language and length; the other 300 are test (PREREG amendment, point 1)
FPR_BOUND = 0.02     # one-sided 95% upper bound a cell's false positives must stay under (point 2)
TEST_ONLY = ("ai_reflip", "human_l2", "human_l2_corrected")


# --------------------------------------------------------------------------- scoring

def cmd_score(args) -> int:
    from .detect import make_detector

    out = path(f"scores-{args.pair}.jsonl")
    done = {r["id"] for r in read_jsonl(out)}
    todo = [r for r in corpus() if r["id"] not in done]
    if not todo:
        print("nothing to score", file=sys.stderr)
        return 0
    # A fresh process per batch: on Apple's GPU the memory a long run holds grows until it
    # stops (166, 395 and 155 texts on 21 and 22 October), and exiting is what gives it back.
    if args.limit:
        todo = todo[:args.limit]
    det = make_detector(args.pair)
    t0 = time.time()
    with out.open("a") as f:
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


# --------------------------------------------------------------------------- statistics

def auroc(pos: list[float], neg: list[float]) -> float:
    """P(a machine text scores above a human one), ties counted half. Mann-Whitney."""
    if not pos or not neg:
        return float("nan")
    allv = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    rank_sum, i = 0.0, 0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        mid = (i + j + 1) / 2.0                      # average rank, 1-based
        rank_sum += mid * sum(1 for k in range(i, j) if allv[k][1] == 1)
        i = j
    n1, n0 = len(pos), len(neg)
    return (rank_sum - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def boot_auroc(pos, neg, rng, n=BOOT) -> tuple[float, float]:
    vals = []
    for _ in range(n):
        p = [pos[rng.randrange(len(pos))] for _ in pos]
        q = [neg[rng.randrange(len(neg))] for _ in neg]
        vals.append(auroc(p, q))
    vals.sort()
    return vals[int(0.025 * n)], vals[int(0.975 * n) - 1]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


def cp_upper(k: int, n: int, conf: float = 0.95) -> float:
    """One-sided Clopper-Pearson upper bound on a rate seen as k out of n."""
    from scipy.stats import beta

    if n == 0:
        return float("nan")
    return 1.0 if k >= n else float(beta.ppf(conf, k + 1, n - k))


def quantile(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


# --------------------------------------------------------------------------- split and fits

def split(rows: list[dict]) -> None:
    """Mark each row calib or test, per language, length and class, seed 0."""
    rng = random.Random(0)
    groups: dict = {}
    for r in rows:
        if r["kind"] in TEST_ONLY:
            r["half"] = "test"                      # rewrites and learners are only evaluated
            continue
        groups.setdefault((r["lang"], r["bucket"], r["kind"]), []).append(r)
    for key in sorted(groups):
        g = sorted(groups[key], key=lambda r: r["id"])
        rng.shuffle(g)
        n_cal = min(HUMANS_CALIB, len(g) // 2) if key[2] == "human" else len(g) // 2
        for i, r in enumerate(g):
            r["half"] = "calib" if i < n_cal else "test"


def fit_logistic(rows: list[dict], bucket: str):
    """Perplexity and burstiness together, fitted on the calibration half of one length."""
    from sklearn.linear_model import LogisticRegression

    cal = [r for r in rows if r["half"] == "calib" and r["bucket"] == bucket and r["kind"] in ("human", "ai")]
    bursts = [r["f"]["burstiness"] for r in cal if r["f"]["burstiness"] is not None]
    fill = sum(bursts) / len(bursts) if bursts else 0.0
    X = [[r["f"]["nll_obs"], r["f"]["burstiness"] if r["f"]["burstiness"] is not None else fill] for r in cal]
    y = [1 if r["kind"] == "ai" else 0 for r in cal]
    m = LogisticRegression(class_weight="balanced").fit(X, y)
    a, b = m.coef_[0]
    c = m.intercept_[0]
    return {"w_nll": float(a), "w_burst": float(b), "bias": float(c), "fill_burst": fill}


def apply_logistic(p: dict, f: dict) -> float:
    burst = f["burstiness"] if f["burstiness"] is not None else p["fill_burst"]
    return p["w_nll"] * f["nll_obs"] + p["w_burst"] * burst + p["bias"]


# --------------------------------------------------------------------------- evaluation

def evaluate_pair(pair: str, rows: list[dict], rng: random.Random) -> dict:
    scores = {r["id"]: r for r in read_jsonl(path(f"scores-{pair}.jsonl")) if "error" not in r}
    data = [dict(r, f=scores[r["id"]]) for r in rows if r["id"] in scores]
    logit = {b: fit_logistic(data, b) for b in BUCKETS}
    dets = dict(DETECTORS)
    out = {"pair": pair, "detectors": {}, "logistic": logit}
    for name in list(dets) + ["ppl_burstiness"]:
        def s(r, name=name):
            if name == "ppl_burstiness":
                return apply_logistic(logit[r["bucket"]], r["f"])
            return dets[name](r["f"])
        res = {"cells": {}, "buckets": {}, "langs": {}, "generators": {}, "genres": {}, "rewritten": {}}
        thr = {}
        for b in BUCKETS:
            cal_h = [s(r) for r in data if r["half"] == "calib" and r["bucket"] == b and r["kind"] == "human"]
            cal_h = [v for v in cal_h if v is not None]
            thr[b] = quantile(cal_h, 1 - FPR) if cal_h else float("nan")
        res["thresholds"] = thr

        def block(sel_h, sel_a, b):
            pos = [v for v in (s(r) for r in sel_a) if v is not None]
            neg = [v for v in (s(r) for r in sel_h) if v is not None]
            if len(pos) < 5 or len(neg) < 5:
                return {"n_ai": len(pos), "n_human": len(neg)}
            a = auroc(pos, neg)
            lo, hi = boot_auroc(pos, neg, rng)
            t = thr[b] if isinstance(b, str) else None
            d = {"n_ai": len(pos), "n_human": len(neg), "auroc": a, "auroc_low": lo, "auroc_high": hi}
            if t is not None and not math.isnan(t):
                tp, fp = sum(v > t for v in pos), sum(v > t for v in neg)
                d.update(tpr=tp / len(pos), tpr_ci=wilson(tp, len(pos)),
                         fpr=fp / len(neg), fpr_ci=wilson(fp, len(neg)),
                         fp=fp, fpr_upper=cp_upper(fp, len(neg)))
            return d

        test = [r for r in data if r["half"] == "test"]
        for lang in LANGS:
            for b in BUCKETS:
                h = [r for r in test if r["lang"] == lang and r["bucket"] == b and r["kind"] == "human"]
                a_ = [r for r in test if r["lang"] == lang and r["bucket"] == b and r["kind"] == "ai"]
                res["cells"][f"{lang}/{b}"] = block(h, a_, b)
        for b in BUCKETS:
            h = [r for r in test if r["bucket"] == b and r["kind"] == "human"]
            a_ = [r for r in test if r["bucket"] == b and r["kind"] == "ai"]
            res["buckets"][b] = block(h, a_, b)
            for gen in ("qwen3", "gemma3", "claude"):
                ag = [r for r in a_ if r.get("generator") == gen]
                res["generators"][f"{gen}/{b}"] = block(h, ag, b)
            for genre in ("wiki", "news"):
                hg = [r for r in h if r.get("genre") == genre]
                ag = [r for r in a_ if r.get("genre") == genre]
                res["genres"][f"{genre}/{b}"] = block(hg, ag, b)
            w = [r for r in test if r["bucket"] == b and r["kind"] == "ai_reflip"]
            if w:
                res["rewritten"][b] = block(h, w, b)
            for kind in ("human_l2", "human_l2_corrected"):
                for lang in LANGS:
                    ls = [v for v in (s(r) for r in test if r["kind"] == kind and r["lang"] == lang
                                      and r["bucket"] == b) if v is not None]
                    if ls and not math.isnan(thr[b]):
                        fp = sum(v > thr[b] for v in ls)
                        res.setdefault("learners", {})[f"{kind}/{lang}/{b}"] = {
                            "n": len(ls), "fp": fp, "fpr": fp / len(ls), "fpr_ci": wilson(fp, len(ls)),
                            "fpr_upper": cp_upper(fp, len(ls))}
        for lang in LANGS:
            h = [r for r in test if r["lang"] == lang and r["kind"] == "human" and r["bucket"] != "short"]
            a_ = [r for r in test if r["lang"] == lang and r["kind"] == "ai" and r["bucket"] != "short"]
            res["langs"][lang] = block(h, a_, None)
        ml = [res["cells"][f"{l}/{b}"].get("auroc") for l in LANGS for b in ("medium", "long")]
        ml = [v for v in ml if v is not None and not math.isnan(v)]
        res["mean_auroc_medium_long"] = sum(ml) / len(ml) if len(ml) == 6 else float("nan")
        out["detectors"][name] = res
    return out


def choose(pairs: dict) -> tuple[str, str, float]:
    """The pre-registered rule: best mean test AUROC over medium and long; ties to 0.5B."""
    cands = []
    for pair, ev in pairs.items():
        for name, res in ev["detectors"].items():
            v = res["mean_auroc_medium_long"]
            if not math.isnan(v):
                cands.append((v, pair, name))
    cands.sort(reverse=True)
    best = cands[0]
    for v, pair, name in cands:
        if best[0] - v <= 0.005 and pair == "qwen2.5-0.5b":
            return pair, name, v
    return best[1], best[2], best[0]


def allowed(cell: dict) -> tuple[bool, str]:
    """The pre-registered refusal rule for one language and length, with the amendment."""
    lo, tpr, up = cell.get("auroc_low"), cell.get("tpr"), cell.get("fpr_upper")
    if lo is None or tpr is None or up is None:
        return False, "not enough measured texts"
    if lo < 0.85:
        return False, f"AUROC lower bound {lo:.2f}, under 0.85"
    if tpr < 0.5:
        return False, f"the threshold catches {tpr:.0%} of machine texts, under half"
    if up > FPR_BOUND:
        return False, (f"the threshold flagged {cell['fp']} of {cell['n_human']} human texts, so the "
                       f"false-positive rate could be as high as {up:.1%}, over {FPR_BOUND:.0%}")
    return True, (f"AUROC {cell['auroc']:.2f} (lower bound {lo:.2f}); catches {tpr:.0%} of machine texts; "
                  f"flags at most {up:.1%} of human texts (95% upper bound)")


def calibration(pair: str, name: str, ev: dict, rows: list[dict]) -> dict:
    """What `reflip detect` ships with: thresholds, human tails and probability bands."""
    scores = {r["id"]: r for r in read_jsonl(path(f"scores-{pair}.jsonl")) if "error" not in r}
    data = [dict(r, f=scores[r["id"]]) for r in rows if r["id"] in scores and r["half"] == "calib"]
    res = ev["detectors"][name]

    def s(r):
        if name == "ppl_burstiness":
            return apply_logistic(ev["logistic"][r["bucket"]], r["f"])
        return DETECTORS[name](r["f"])

    buckets = {}
    for b in BUCKETS:
        h = [v for v in (s(r) for r in data if r["bucket"] == b and r["kind"] == "human") if v is not None]
        buckets[b] = {"threshold": res["thresholds"][b], "human_scores": sorted(h)}
    cells = {}
    for key, cell in res["cells"].items():
        ok, why = allowed(cell)
        cells[key] = {"allowed": ok, "why": why, "auroc": cell.get("auroc"),
                      "auroc_low": cell.get("auroc_low"), "tpr": cell.get("tpr"), "fpr": cell.get("fpr"),
                      "fpr_upper": cell.get("fpr_upper"), "n_human": cell.get("n_human")}
    learners = {k: v for k, v in res.get("learners", {}).items() if k.startswith("human_l2/")}
    return {"v": 1, "pair": pair, "detector": name, "fpr": FPR, "buckets": buckets, "cells": cells,
            "learners": learners,
            "logistic": ev["logistic"] if name == "ppl_burstiness" else None,
            "words": {k: list(v) for k, v in BUCKETS.items()}, "protocol": "docs/detect/PREREG.md"}


def md_table(ev: dict) -> str:
    lines = ["| detector | " + " | ".join(f"{l} {b}" for l in LANGS for b in BUCKETS) + " | mean medium+long |",
             "|---|" + "---|" * (len(LANGS) * len(BUCKETS)) + "---|"]
    for name, res in ev["detectors"].items():
        cells = []
        for l in LANGS:
            for b in BUCKETS:
                c = res["cells"][f"{l}/{b}"]
                cells.append(f"{c['auroc']:.2f} ({c['auroc_low']:.2f}-{c['auroc_high']:.2f})" if "auroc" in c else "-")
        cells.append(f"{res['mean_auroc_medium_long']:.3f}")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def cell_table(ev: dict, name: str) -> str:
    """Per cell, for the chosen detector: what the threshold does on the test half, and the verdict rule."""
    res = ev["detectors"][name]
    lines = ["| cell | AUROC (95%) | machine caught | humans flagged | upper bound | verdict |",
             "|---|---|---|---|---|---|"]
    for l in LANGS:
        for b in BUCKETS:
            c = res["cells"][f"{l}/{b}"]
            ok, why = allowed(c)
            if "auroc" not in c:
                lines.append(f"| {l} {b} | - | - | - | - | refused: {why} |")
                continue
            lines.append(f"| {l} {b} | {c['auroc']:.2f} ({c['auroc_low']:.2f}-{c['auroc_high']:.2f}) | "
                         f"{c['tpr']:.0%} of {c['n_ai']} | {c['fp']} of {c['n_human']} | {c['fpr_upper']:.1%} | "
                         f"{'given' if ok else 'refused: ' + why} |")
    return "\n".join(lines)


def side_tables(ev: dict, name: str) -> str:
    res = ev["detectors"][name]
    out = ["| reflip-rewritten machine text | AUROC against humans | caught at the threshold |", "|---|---|---|"]
    for b, c in res["rewritten"].items():
        out.append(f"| {b} ({c.get('n_ai', 0)} texts) | "
                   + (f"{c['auroc']:.2f} | {c['tpr']:.0%} |" if "auroc" in c else "too few | - |"))
    out += ["", "| second-language writers | texts | flagged as machine | upper bound |", "|---|---|---|---|"]
    for k, c in sorted(res.get("learners", {}).items()):
        out.append(f"| {k} | {c['n']} | {c['fp']} ({c['fpr']:.1%}) | {c['fpr_upper']:.1%} |")
    out += ["", "| generator | bucket | AUROC |", "|---|---|---|"]
    for k, c in res["generators"].items():
        if "auroc" in c:
            g, b = k.split("/")
            out.append(f"| {g} | {b} | {c['auroc']:.2f} ({c['auroc_low']:.2f}-{c['auroc_high']:.2f}) |")
    out += ["", "| human genre | bucket | AUROC |", "|---|---|---|"]
    for k, c in res["genres"].items():
        if "auroc" in c:
            g, b = k.split("/")
            out.append(f"| {g} | {b} | {c['auroc']:.2f} ({c['auroc_low']:.2f}-{c['auroc_high']:.2f}) |")
    return "\n".join(out)


def cmd_evaluate(args) -> int:
    rows = corpus()
    split(rows)
    rng = random.Random(0)
    pairs = {}
    for pair in PAIRS:          # the server pairs compete for the default; the browser's below
        if path(f"scores-{pair}.jsonl").is_file():
            print(f"evaluating {pair}", file=sys.stderr)
            pairs[pair] = evaluate_pair(pair, rows, rng)
    if not pairs:
        print("no scores yet: run `score` first", file=sys.stderr)
        return 1
    pair, name, v = choose(pairs)
    # The browser runs the 4-bit files, whose scores differ: same detector, its own thresholds
    # and refusal table, from the same split and the same rules (PREREG amendment, point 6).
    browser = {p: evaluate_pair(p, rows, random.Random(0))
               for p in ONNX_PAIRS if path(f"scores-{p}.jsonl").is_file()}
    RESULTS.mkdir(parents=True, exist_ok=True)
    counts = {}
    for r in rows:
        k = f"{r['kind']}/{r['lang']}/{r['bucket']}"
        counts[k] = counts.get(k, 0) + 1
    (RESULTS / "summary.json").write_text(json.dumps({"chosen": {"pair": pair, "detector": name,
                                                                 "mean_auroc_medium_long": v},
                                                      "counts": counts, "pairs": pairs,
                                                      "browser": browser}, indent=1))
    md = [f"# Detection benchmark\n\nChosen by the pre-registered rule: **{name}** on **{pair}**, "
          f"mean test AUROC over the six medium and long cells {v:.3f}. Every number below comes "
          f"from the test half; the protocol is docs/detect/PREREG.md.\n",
          f"\n## {name} on {pair}, cell by cell\n\n{cell_table(pairs[pair], name)}\n",
          f"\n## {name} on {pair}: rewritten text, second-language writers, generators, genres\n\n"
          f"{side_tables(pairs[pair], name)}\n"]
    for p, ev in browser.items():
        md.append(f"\n## In the browser: {name} on {p} (4-bit), cell by cell\n\n{cell_table(ev, name)}\n")
        md.append(f"\n{side_tables(ev, name)}\n")
    for p, ev in {**pairs, **browser}.items():
        md.append(f"\n## {p}: test AUROC of every detector, with 95% interval\n\n{md_table(ev)}\n")
    (RESULTS / "summary.md").write_text("\n".join(md))
    CALIBRATION.write_text(json.dumps(calibration(pair, name, pairs[pair], rows)))
    for p, ev in browser.items():
        BROWSER_CALIBRATION.parent.mkdir(parents=True, exist_ok=True)
        BROWSER_CALIBRATION.write_text(json.dumps(calibration(p, name, ev, rows)))
    print("\n".join(md))
    print(f"\nwrote {RESULTS / 'summary.md'}, {CALIBRATION}"
          + (f" and {BROWSER_CALIBRATION}" if browser else ""), file=sys.stderr)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reflip-detect-bench", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--pair", choices=sorted(ALL_PAIRS), required=True)
    s.add_argument("--limit", type=int, default=0, help="score at most this many texts, then exit")
    s.set_defaults(fn=cmd_score)
    sub.add_parser("evaluate").set_defaults(fn=cmd_evaluate)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
