"""Verification harness: what does each transform do to the open SynthID detector?

A watermark-removal tool that cannot show its detector scores is a guess. This module is
the proof: it takes the corpus written by `reflip.corpus` (the same prompts completed with
and without the watermark, with the exact token ids the model emitted), runs every
transform on every watermarked sample, and re-scores the result with the same key. It
reports the detector before and after (z-score), the *mechanism* (intact fraction: how
many g-values survived unchanged), and the price (cosine similarity, word edit ratio, LLM
tokens, seconds). Plain controls are scored too, so the reader can see where unwatermarked
text lands and judge the threshold.

Two design decisions worth knowing:

1. `z_before` is computed from the STORED ids, never from a re-tokenisation of the text.
   The detector hashes the token sequence the model actually emitted; decoding and
   re-encoding can split tokens differently, and that difference would be silently counted
   as removal. `z_after` is computed from the re-tokenised edited text, because that is all
   a real detector ever sees. The `none` transform (identity) makes the gap visible.
2. Every transform output is cached in `<cache-dir>/<transform>/<sample id>-<digest>.json`,
   keyed by a digest of the options that change the output (model, temperature, seed,
   stride, span, ngram_len, rules, language, token-aware tokenizer). Re-running the bench
   with a different threshold, tokenizer or metric set re-scores without calling the LLM.

Heavy imports (torch, transformers, through `reflip.synthid`) happen inside functions, so
`import reflip.bench` is cheap and the CLI's `--help` does not load torch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import transforms
from .transforms import Options, Transform, TransformResult
from .words import word_edit_ratio, words

DEFAULT_TRANSFORMS = "none,unicode,rules,infill,hybrid,paraphrase"
DEFAULT_NGRAM_LEN = 5
CONTROL_LABEL = "control(plain)"
SWEEP_TRANSFORM = "infill"
PPL_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --- model loaders (module-level so tests can monkeypatch them) -------------------------

def load_tokenizer(name: str):
    """Load ONLY the tokenizer of an HF model (never the weights)."""
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(name)


def make_embedder(device: str | None = None):
    from .similarity import Embedder

    return Embedder(device=device)


def make_perplexity(model_name: str = PPL_MODEL, device: str | None = None):
    from .similarity import Perplexity

    return Perplexity(model_name=model_name, device=device)


# --- corpus and transform specs ---------------------------------------------------------

def read_corpus(path: Path, lang: str | None = None,
                limit: int | None = None) -> tuple[list[dict], list[dict]]:
    """Return (watermarked, plain) records; `limit` applies to each group separately."""
    wm: list[dict] = []
    plain: list[dict] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if lang and rec.get("lang") != lang:
                continue
            (wm if rec.get("watermarked") else plain).append(rec)
    if limit is not None:
        wm, plain = wm[:limit], plain[:limit]
    return wm, plain


def identity(text: str, opts: Options) -> TransformResult:
    return TransformResult(text=text)


@dataclass(frozen=True)
class Spec:
    label: str        # row name in the summary, e.g. "infill@4"
    base: str         # registry name, e.g. "infill" ("none" = identity)
    stride: int | None  # stride override from "name@stride", else None


def parse_spec(spec: str) -> Spec:
    spec = spec.strip()
    if "@" in spec:
        base, s = spec.split("@", 1)
        try:
            stride = int(s)
        except ValueError as e:
            raise ValueError(f"bad transform spec {spec!r}: stride must be an int") from e
        return Spec(label=f"{base}@{stride}", base=base, stride=stride)
    return Spec(label=spec, base=spec, stride=None)


def expand_transforms(transforms_csv: str, sweep_stride: str | None = None) -> list[Spec]:
    """Comma list -> specs; `--sweep-stride 2,3` appends infill@2, infill@3. Deduplicated."""
    specs: list[Spec] = []
    for item in transforms_csv.split(","):
        if item.strip():
            specs.append(parse_spec(item))
    if sweep_stride:
        for s in sweep_stride.split(","):
            if s.strip():
                specs.append(parse_spec(f"{SWEEP_TRANSFORM}@{int(s)}"))
    seen: set[str] = set()
    return [sp for sp in specs if not (sp.label in seen or seen.add(sp.label))]


def resolve(base: str) -> Transform:
    """Registry lookup; "none" is the identity. Raises KeyError/ImportError if unknown."""
    if base == "none":
        return identity
    return transforms.get(base)


def safe_name(label: str) -> str:
    return re.sub(r"[^\w.@-]+", "_", label).strip("_")


# --- cache --------------------------------------------------------------------------

def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def options_digest(base: str, opts: Options, tokenizer_name: str | None) -> tuple[str, dict]:
    """Digest of the options that change a transform's output (12 hex chars of sha1)."""
    matter = {
        "transform": base,
        "model": opts.model,
        "temperature": opts.temperature,
        "seed": opts.seed,
        "stride": opts.stride,
        "span": opts.span,
        "ngram_len": opts.ngram_len,
        "rules": list(opts.rules),
        "language": opts.language,
        "tokenaware": tokenizer_name if opts.tokenizer is not None else None,
    }
    digest = hashlib.sha1(json.dumps(matter, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return digest, matter


class Cache:
    """One JSON file per (transform, sample, options digest); the input text is checked by sha1."""

    def __init__(self, root: Path):
        self.root = root

    def path(self, base: str, sample_id: str, digest: str) -> Path:
        return self.root / safe_name(base) / f"{sample_id}-{digest}.json"

    def get(self, base: str, sample_id: str, digest: str, text: str) -> dict | None:
        p = self.path(base, sample_id, digest)
        if not p.exists():
            return None
        try:
            entry = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log(f"cache: ignoring unreadable {p}: {e}")
            return None
        if entry.get("text_sha1") != sha1(text):
            return None
        return entry

    def put(self, base: str, sample_id: str, digest: str, text: str, entry: dict, options: dict) -> None:
        p = self.path(base, sample_id, digest)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(entry, text_sha1=sha1(text), options=options, sample_id=sample_id)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


# --- metrics --------------------------------------------------------------------------

class Metrics:
    """Detector, embedder and perplexity, all built lazily and cached per model name."""

    def __init__(self, ngram_len: int = DEFAULT_NGRAM_LEN, tokenizer_name: str | None = None,
                 cosine: bool = True, ppl: bool = False, ppl_model: str = PPL_MODEL,
                 device: str | None = None):
        self.ngram_len = ngram_len
        self.tokenizer_name = tokenizer_name
        self.want_cosine = cosine
        self.want_ppl = ppl
        self.ppl_model = ppl_model
        self.device = device
        self._tokenizers: dict[str, object] = {}
        self._scorers: dict[str, object] = {}
        self._embedder = None
        self._embedder_failed = False
        self._ppl = None
        self._ppl_failed = False

    def tokenizer_for(self, rec: dict) -> str:
        name = self.tokenizer_name or rec.get("model")
        if not name:
            raise ValueError(f"record {rec.get('id')!r} has no 'model' and no --tokenizer was given")
        return name

    def tokenizer(self, name: str):
        if name not in self._tokenizers:
            log(f"loading tokenizer {name}")
            self._tokenizers[name] = load_tokenizer(name)
        return self._tokenizers[name]

    def scorer(self, name: str):
        if name not in self._scorers:
            from .synthid import Scorer

            self._scorers[name] = Scorer(self.tokenizer(name), ngram_len=self.ngram_len)
        return self._scorers[name]

    def cosine(self, a: str, b: str) -> float | None:
        if not self.want_cosine or self._embedder_failed:
            return None
        if self._embedder is None:
            try:
                self._embedder = make_embedder(self.device)
            except Exception as e:  # noqa: BLE001 - optional metric, never fatal
                log(f"cosine disabled: cannot build embedder ({type(e).__name__}: {e})")
                self._embedder_failed = True
                return None
        try:
            return round(float(self._embedder.cosine(a, b)), 4)
        except Exception as e:  # noqa: BLE001
            log(f"cosine disabled: {type(e).__name__}: {e}")
            self._embedder_failed = True
            return None

    def ppl(self, text: str) -> float | None:
        if not self.want_ppl or self._ppl_failed:
            return None
        if self._ppl is None:
            try:
                self._ppl = make_perplexity(self.ppl_model, self.device)
            except Exception as e:  # noqa: BLE001
                log(f"ppl disabled: cannot build perplexity model ({type(e).__name__}: {e})")
                self._ppl_failed = True
                return None
        return round(float(self._ppl.ppl(text)), 2)

    def measure(self, rec: dict, new_text: str) -> dict:
        """Detector before (stored ids) and after (re-tokenised edited text), plus meaning."""
        from .synthid import intact_fraction

        scorer = self.scorer(self.tokenizer_for(rec))
        before = scorer.score_ids(rec["ids"])
        new_ids = scorer.encode(new_text)
        after = scorer.score_ids(new_ids)
        return {
            "tokens_before": before.tokens,
            "tokens_after": after.tokens,
            "scored_before": before.scored,
            "scored_after": after.scored,
            "z_before": before.z,
            "z_after": after.z,
            "zw_before": before.z_w,
            "zw_after": after.z_w,
            "p_after": after.p,
            "intact": round(intact_fraction(rec["ids"], new_ids, self.ngram_len), 4),
            "cosine": self.cosine(rec["text"], new_text),
            "edit_ratio": round(word_edit_ratio(rec["text"], new_text), 4),
            "ppl_before": self.ppl(rec["text"]),
            "ppl_after": self.ppl(new_text),
        }


# --- evaluation ------------------------------------------------------------------------

def apply_transform(fn: Transform, base: str, rec: dict, opts: Options, digest: str,
                    matter: dict, cache: Cache | None) -> tuple[dict, bool]:
    """Run the transform (or read it from the cache). Returns (entry, cached)."""
    text = rec["text"]
    if cache is not None:
        hit = cache.get(base, rec["id"], digest, text)
        if hit is not None:
            return hit, True
    t0 = time.perf_counter()
    res = fn(text, opts)
    entry = {
        "text": res.text,
        "edits": res.edits,
        "llm_calls": res.llm_calls,
        "prompt_tokens": res.prompt_tokens,
        "completion_tokens": res.completion_tokens,
        "notes": res.notes,
        "seconds": round(time.perf_counter() - t0, 3),
    }
    if cache is not None:
        cache.put(base, rec["id"], digest, text, entry, matter)
    return entry, False


def sample_row(spec: Spec, rec: dict, entry: dict, cached: bool, metrics: Metrics) -> dict:
    row = {
        "id": rec["id"],
        "transform": spec.label,
        "lang": rec.get("lang"),
        "cached": cached,
        "seconds": entry.get("seconds", 0.0),
        "edits": entry.get("edits", 0),
        "llm_calls": entry.get("llm_calls", 0),
        "prompt_tokens": entry.get("prompt_tokens", 0),
        "completion_tokens": entry.get("completion_tokens", 0),
        "input_words": len(words(rec["text"])),
    }
    row.update(metrics.measure(rec, entry["text"]))
    row["text"] = entry["text"]
    return row


def error_row(spec_label: str, rec: dict, exc: BaseException) -> dict:
    return {"id": rec["id"], "transform": spec_label, "lang": rec.get("lang"),
            "error": f"{type(exc).__name__}: {exc}"}


def progress(spec_label: str, i: int, n: int, row: dict) -> None:
    if "error" in row:
        log(f"[{spec_label}] {i}/{n} {row['id']}: ERROR {row['error']}")
        return
    cos = "-" if row["cosine"] is None else f"{row['cosine']:.3f}"
    log(f"[{spec_label}] {i}/{n} {row['id']}: z {row['z_before']:+.2f} -> {row['z_after']:+.2f}, "
        f"intact {row['intact']:.3f}, cos {cos}, edit {row['edit_ratio']:.1%}, "
        f"{row['llm_calls']} calls, {row['seconds']:.1f}s{' (cache)' if row['cached'] else ''}")


def evaluate(spec: Spec, fn: Transform, samples: list[dict], make_opts: Callable[[dict, Spec], Options],
             metrics: Metrics, cache: Cache | None, out_path: Path) -> list[dict]:
    """Run one transform over all samples, writing rows as they come. Never raises per sample."""
    rows: list[dict] = []
    with out_path.open("w", encoding="utf-8") as f:
        for i, rec in enumerate(samples, 1):
            try:
                opts = make_opts(rec, spec)
                digest, matter = options_digest(spec.base, opts, metrics.tokenizer_for(rec))
                entry, cached = apply_transform(fn, spec.base, rec, opts, digest, matter, cache)
                row = sample_row(spec, rec, entry, cached, metrics)
            except Exception as e:  # noqa: BLE001 - one bad sample must not kill the bench
                row = error_row(spec.label, rec, e)
            rows.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            progress(spec.label, i, len(samples), row)
    return rows


def control_rows(plain: list[dict], metrics: Metrics, out_path: Path) -> list[dict]:
    """Score the unwatermarked controls once (identity transform on plain text)."""
    spec = Spec(label=CONTROL_LABEL, base="none", stride=None)
    entry_of = lambda rec: {"text": rec["text"], "seconds": 0.0}  # noqa: E731
    rows: list[dict] = []
    with out_path.open("w", encoding="utf-8") as f:
        for i, rec in enumerate(plain, 1):
            try:
                row = sample_row(spec, rec, entry_of(rec), False, metrics)
            except Exception as e:  # noqa: BLE001
                row = error_row(spec.label, rec, e)
            rows.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            progress(spec.label, i, len(plain), row)
    return rows


# --- summary ---------------------------------------------------------------------------

def _mean(values: list) -> float | None:
    vals = [v for v in values if v is not None]
    return round(statistics.fmean(vals), 4) if vals else None


def _share(values: list[float], below: float) -> float | None:
    return round(sum(v < below for v in values) / len(values), 4) if values else None


def summarise(label: str, rows: list[dict], threshold: float) -> dict:
    ok = [r for r in rows if "error" not in r]
    z_after = [r["z_after"] for r in ok]
    in_words = sum(r["input_words"] for r in ok)
    llm_tokens = sum(r["prompt_tokens"] + r["completion_tokens"] for r in ok)
    return {
        "transform": label,
        "n": len(ok),
        "errors": len(rows) - len(ok),
        "cached": sum(bool(r.get("cached")) for r in ok),
        "z_before_mean": _mean([r["z_before"] for r in ok]),
        "z_after_mean": _mean(z_after),
        "z_after_median": round(statistics.median(z_after), 4) if z_after else None,
        "z_after_max": max(z_after) if z_after else None,
        "zw_after_mean": _mean([r.get("zw_after") for r in ok]),
        "share_zw_below_threshold": _share([r.get("zw_after", 0.0) for r in ok], threshold),
        "share_below_threshold": _share(z_after, threshold),
        "share_below_2": _share(z_after, 2.0),
        "intact_mean": _mean([r["intact"] for r in ok]),
        "cosine_mean": _mean([r["cosine"] for r in ok]),
        "edit_ratio_mean": _mean([r["edit_ratio"] for r in ok]),
        "llm_tokens_per_1k_words": round(1000.0 * llm_tokens / in_words, 1) if in_words else None,
        "seconds_mean": _mean([r["seconds"] for r in ok]),
        "ppl_before_mean": _mean([r.get("ppl_before") for r in ok]),
        "ppl_after_mean": _mean([r.get("ppl_after") for r in ok]),
    }


def _fmt(v, spec: str = ".2f") -> str:
    if v is None:
        return "-"
    return format(v, spec)


def markdown_table(summaries: list[dict], threshold: float, ppl: bool = False) -> str:
    head = ["transform", "n", "err", "z before", "z after", "median", "max",
            f"<{threshold:g}", "<2", "z_w after", "intact", "cosine", "edit", "LLM tok/1k w", "s/sample"]
    if ppl:
        head += ["ppl before", "ppl after"]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for s in summaries:
        cells = [s["transform"], str(s["n"]), str(s["errors"]),
                 _fmt(s["z_before_mean"]), _fmt(s["z_after_mean"]), _fmt(s["z_after_median"]),
                 _fmt(s["z_after_max"]), _fmt(s["share_below_threshold"], ".0%"),
                 _fmt(s["share_below_2"], ".0%"), _fmt(s.get("zw_after_mean")), _fmt(s["intact_mean"], ".3f"),
                 _fmt(s["cosine_mean"], ".3f"), _fmt(s["edit_ratio_mean"], ".1%"),
                 _fmt(s["llm_tokens_per_1k_words"], ".0f"), _fmt(s["seconds_mean"], ".1f")]
        if ppl:
            cells += [_fmt(s["ppl_before_mean"]), _fmt(s["ppl_after_mean"])]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_summary(out_dir: Path, config: dict, summaries: list[dict], threshold: float, ppl: bool) -> str:
    table = markdown_table(summaries, threshold, ppl)
    (out_dir / "summary.json").write_text(
        json.dumps({"config": config, "transforms": summaries}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    errors = sum(s["errors"] for s in summaries)
    md = [
        "# reflip bench",
        "",
        f"corpus `{config['corpus']}`: {config['n_watermarked']} watermarked, {config['n_plain']} plain; "
        f"tokenizer `{config['tokenizer'] or 'per record'}`; ngram_len {config['ngram_len']}; "
        f"threshold z<{threshold:g}; LLM `{config['model']}` (T={config['temperature']}, seed={config['seed']}, "
        f"stride {config['stride']}, span {config['span']}{', token-aware' if config['tokenaware'] else ''}).",
        "",
        "z: SynthID mean-g detector, standard deviations above chance (score from stored ids "
        "before, from the re-tokenised text after). intact: share of positions whose g-value the "
        "detector recomputes unchanged (0 = fully re-randomised). cosine: multilingual-e5-small. "
        "edit: share of words not kept verbatim.",
        "",
        table,
        "",
        f"{errors} sample(s) errored." if errors else "No sample errored.",
        "",
    ]
    (out_dir / "summary.md").write_text("\n".join(md), encoding="utf-8")
    return table


# --- CLI --------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="reflip bench", description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default="data/corpus.jsonl")
    ap.add_argument("--transforms", default=DEFAULT_TRANSFORMS,
                    help="comma list; 'none' = identity; 'infill@4' overrides the stride")
    ap.add_argument("--limit", type=int, default=None, help="first N watermarked (and N plain) samples")
    ap.add_argument("--lang", default=None, help="only records with this lang")
    ap.add_argument("--stride", type=int, default=Options.stride)
    ap.add_argument("--span", type=int, default=Options.span)
    ap.add_argument("--model", default=Options.model)
    ap.add_argument("--base-url", default=Options.base_url)
    ap.add_argument("--api-key", default=Options.api_key)
    ap.add_argument("--temperature", type=float, default=Options.temperature)
    ap.add_argument("--seed", type=int, default=Options.seed)
    ap.add_argument("--tokenizer", default=None, help="HF name; default = each record's model")
    ap.add_argument("--tokenaware", action="store_true", help="choose slots in token space of --tokenizer")
    ap.add_argument("--ngram-len", type=int, default=DEFAULT_NGRAM_LEN, help="must match the corpus generator")
    ap.add_argument("--threshold", type=float, default=4.0, help="z below which we call the mark gone")
    ap.add_argument("--ppl", action="store_true", help="also measure perplexity (loads a 1.5B model)")
    ap.add_argument("--ppl-model", default=PPL_MODEL)
    ap.add_argument("--no-cosine", action="store_true", help="skip the embedding similarity")
    ap.add_argument("--device", default=None, help="device for embedder/ppl (default cpu)")
    ap.add_argument("--out-dir", default="data/results")
    ap.add_argument("--cache-dir", default="data/cache")
    ap.add_argument("--sweep-stride", default=None, help='e.g. "2,3,4,5,6": adds infill@s rows')
    ap.add_argument("--no-cache", action="store_true")
    return ap


def resolve_specs(specs: list[Spec]) -> list[tuple[Spec, Transform]]:
    """Look every spec up; unknown or unimportable ones are logged and skipped."""
    out: list[tuple[Spec, Transform]] = []
    for spec in specs:
        try:
            out.append((spec, resolve(spec.base)))
        except (KeyError, ImportError) as e:
            log(f"skipping transform {spec.label!r}: {e}")
    return out


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    corpus = Path(args.corpus)
    if not corpus.exists():
        log(f"error: corpus not found: {corpus} (run `reflip corpus` first)")
        return 2
    wm, plain = read_corpus(corpus, lang=args.lang, limit=args.limit)
    if not wm and not plain:
        log(f"error: no records in {corpus}")
        return 2
    runnable = resolve_specs(expand_transforms(args.transforms, args.sweep_stride))
    if not runnable and wm:
        log("error: no runnable transform")
        return 2

    metrics = Metrics(ngram_len=args.ngram_len, tokenizer_name=args.tokenizer,
                      cosine=not args.no_cosine, ppl=args.ppl, ppl_model=args.ppl_model,
                      device=args.device)
    cache = None if args.no_cache else Cache(Path(args.cache_dir))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def make_opts(rec: dict, spec: Spec) -> Options:
        tok = metrics.tokenizer(metrics.tokenizer_for(rec)) if args.tokenaware else None
        return Options(base_url=args.base_url, api_key=args.api_key, model=args.model,
                       temperature=args.temperature, seed=args.seed,
                       stride=spec.stride if spec.stride is not None else args.stride,
                       span=args.span, ngram_len=args.ngram_len, tokenizer=tok,
                       language=rec.get("lang", Options.language))

    t_all = time.perf_counter()
    summaries: list[dict] = []
    for spec, fn in runnable:
        log(f"== {spec.label}: {len(wm)} watermarked samples")
        rows = evaluate(spec, fn, wm, make_opts, metrics, cache, out_dir / f"{safe_name(spec.label)}.jsonl")
        summaries.append(summarise(spec.label, rows, args.threshold))
    if plain:
        log(f"== {CONTROL_LABEL}: {len(plain)} plain samples")
        rows = control_rows(plain, metrics, out_dir / f"{safe_name(CONTROL_LABEL)}.jsonl")
        summaries.append(summarise(CONTROL_LABEL, rows, args.threshold))

    config = {"corpus": str(corpus), "n_watermarked": len(wm), "n_plain": len(plain),
              "tokenizer": args.tokenizer, "tokenaware": args.tokenaware, "ngram_len": args.ngram_len,
              "threshold": args.threshold, "model": args.model, "temperature": args.temperature,
              "seed": args.seed, "stride": args.stride, "span": args.span, "lang": args.lang,
              "limit": args.limit, "ppl": args.ppl, "cosine": not args.no_cosine,
              "cache": None if cache is None else str(cache.root),
              "seconds": round(time.perf_counter() - t_all, 1)}
    table = write_summary(out_dir, config, summaries, args.threshold, args.ppl)
    errors = sum(s["errors"] for s in summaries)
    log(f"wrote {out_dir / 'summary.md'} ({errors} errored sample(s), {config['seconds']}s)")
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
