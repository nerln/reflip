"""Build the corpus the detectors are measured on: human, machine and rewritten text.

    python -m reflip.detect_corpus humans              # fetch and cut the human excerpts
    python -m reflip.detect_corpus requests            # topics and lengths for the machine texts
    python -m reflip.detect_corpus generate qwen3      # write machine texts with a local model
    python -m reflip.detect_corpus generate gemma3
    python -m reflip.detect_corpus rewrite             # put some machine texts through reflip
    python -m reflip.detect_corpus status

Everything follows docs/detect/PREREG.md. Every step appends to a JSON Lines file and skips
what is already there, so an interrupted run picks up where it stopped: a corpus that has
to be rebuilt from nothing after a crash at hour two gets built with corners cut.

Human text is never redistributed. The excerpts live under data/detect/ on this machine,
which git ignores; what the repository carries is a manifest of where each one came from
(dataset, row, how many sentences), enough to cut the same excerpt again.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from .detect import sentence_spans, word_count

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "detect"
ROWS_API = "https://datasets-server.huggingface.co/rows"

BUCKETS = {"short": (40, 99), "medium": (100, 300), "long": (301, 600)}
HUMAN_PER_CELL = 400          # 100 calibration, 300 test: see the amendment in PREREG.md
AI_PER_CELL = 40
LANGS = ("en", "it", "es")

# (dataset, config, split, text field, topic field, rows in the split)
SOURCES = {
    ("en", "wiki"): ("wikimedia/wikipedia", "20231101.en", "train", "text", "title", 6407814),
    ("it", "wiki"): ("wikimedia/wikipedia", "20231101.it", "train", "text", "title", 1833639),
    ("es", "wiki"): ("wikimedia/wikipedia", "20231101.es", "train", "text", "title", 1841155),
    ("en", "news"): ("EdinburghNLP/xsum", "default", "train", "document", "summary", 204045),
    ("it", "news"): ("ARTeLab/ilpost", "default", "train", "source", "target", 35201),
    ("es", "news"): ("GEM/mlsum", "es", "train", "text", "title", 259888),
}

# Asked-for lengths. Models overshoot short requests and undershoot long ones, so the asks
# sit inside each bucket rather than at its middle, and every text is filed by the length it
# came out at.
ASK = {"short": 65, "medium": 190, "long": 420}

PROMPTS = {
    ("en", "wiki"): "Write an encyclopedia-style passage of about {n} words about: {topic}. "
                    "Plain prose in English: no title, no headings, no lists, no preamble.",
    ("en", "news"): "Write a news article of about {n} words based on this summary: {topic} "
                    "Plain prose in English: no headline, no lists, no preamble.",
    ("it", "wiki"): "Scrivi un passo in stile enciclopedico di circa {n} parole su: {topic}. "
                    "Solo prosa in italiano: niente titolo, niente intestazioni, niente elenchi, niente premesse.",
    ("it", "news"): "Scrivi un articolo di giornale di circa {n} parole a partire da questo sommario: {topic} "
                    "Solo prosa in italiano: niente titolo, niente elenchi, niente premesse.",
    ("es", "wiki"): "Escribe un pasaje de estilo enciclopédico de unas {n} palabras sobre: {topic}. "
                    "Solo prosa en español: sin título, sin encabezados, sin listas, sin preámbulos.",
    ("es", "news"): "Escribe un artículo periodístico de unas {n} palabras a partir de este resumen: {topic} "
                    "Solo prosa en español: sin titular, sin listas, sin preámbulos.",
}

# Writers in a second language: a population of its own (PREREG amendment, point 3). Each
# essay comes with the version a corrector produced, which is reported apart as well.
LEARNERS = {
    "es": ("Ro551/cowsl2h_essays", "default", "train", "essay", "corrected", 2918),
    "en": ("srky/ICNALE_writing_score", "default", "train", "OriginalText", "EditedText", 800),
}
LEARNERS_PER_LANG = 150

LOCAL_GENERATORS = {"qwen3": "qwen3:4b-instruct-2507-q4_K_M", "gemma3": "gemma3:4b"}
GENERATOR_SHARE = ("qwen3", "gemma3", "claude")   # round robin, about a third each


# --------------------------------------------------------------------------- io

def path(name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    return OUT / name


def read_jsonl(p: Path) -> list[dict]:
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def append_jsonl(p: Path, rec: dict) -> None:
    with p.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def bucket_of(words: int) -> str | None:
    for name, (lo, hi) in BUCKETS.items():
        if lo <= words <= hi:
            return name
    return None


# --------------------------------------------------------------------------- humans

def fetch_rows(dataset: str, config: str, split: str, offset: int, length: int = 100) -> list[dict]:
    q = urllib.parse.urlencode({"dataset": dataset, "config": config, "split": split,
                                "offset": offset, "length": length})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(f"{ROWS_API}?{q}", timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            return [{"row_idx": x["row_idx"], **x["row"]} for x in data.get("rows", [])]
        except Exception:  # noqa: BLE001 - the server rate-limits; back off and retry
            time.sleep(5 * (attempt + 1))
    return []


_LIST_LIKE = re.compile(r"^\s*([-*•·]|\d+[.)])\s")


def prose(text: str, genre: str) -> str:
    """The running prose of a document: paragraphs, not headings, lists or tables."""
    keep = []
    for line in text.split("\n"):
        s = line.strip()
        if not s or "|" in s or _LIST_LIKE.match(s):
            continue
        if word_count(s) < (12 if genre == "wiki" else 6):
            continue                       # headings, captions, bylines
        if s[-1] not in ".!?…»\"”'’)":
            continue                       # a line that does not end a sentence is not prose
        keep.append(s)
    return "\n".join(keep)


def cut(text: str, lo: int, hi: int, rng: random.Random) -> tuple[str, int] | None:
    """The first sentences of `text` adding up to a length drawn from [lo, hi], or None."""
    spans = sentence_spans(text)
    target = rng.randint(lo, hi)
    words = 0
    end = None
    for k, (a, b) in enumerate(spans):
        words += word_count(text[a:b])
        if words >= lo and words >= min(target, hi):
            if words <= hi:
                end = (b, k + 1)
            break
    if end is None:
        return None
    return text[:end[0]].strip(), end[1]


def cmd_humans(args) -> int:
    rng = random.Random(0)
    out = path("humans.jsonl")
    have = read_jsonl(out)
    seen = {(r["dataset"], r["config"], r["row_idx"]) for r in have}
    count = {}
    for r in have:
        count[(r["lang"], r["bucket"], r["genre"])] = count.get((r["lang"], r["bucket"], r["genre"]), 0) + 1
    topics = path("topics.jsonl")
    per_genre = HUMAN_PER_CELL // 2
    quota = {(lang, b, g): per_genre for lang in LANGS for b in BUCKETS for g in ("wiki", "news")}

    def need(lang, bucket, genre):
        return quota[(lang, bucket, genre)] - count.get((lang, bucket, genre), 0)

    # Two passes. The second only runs where a genre ran dry (Il Post has few long
    # articles): the other genre's quota for that cell grows by the shortfall.
    for pass_no in (1, 2):
        if pass_no == 2:
            grew = False
            for lang in LANGS:
                for b in BUCKETS:
                    for g, other in (("news", "wiki"), ("wiki", "news")):
                        if need(lang, b, g) > 0:
                            quota[(lang, b, other)] += need(lang, b, g)
                            quota[(lang, b, g)] = count.get((lang, b, g), 0)
                            grew = True
            if not grew:
                break
        _fill(quota, need, count, seen, out, topics, rng)
    for lang in LANGS:
        for b in BUCKETS:
            missing = sum(need(lang, b, g) for g in ("wiki", "news"))
            if missing > 0:
                print(f"{lang} {b}: still {missing} short of {HUMAN_PER_CELL}", file=sys.stderr)
    return 0


def _fill(quota, need, count, seen, out, topics, rng) -> None:
    for (lang, genre), (ds, cfg, split, field, tfield, total) in SOURCES.items():
        tries = 0
        while any(need(lang, b, genre) > 0 for b in BUCKETS) and tries < 40:
            tries += 1
            offset = rng.randrange(0, max(1, total - 100))
            rows = fetch_rows(ds, cfg, split, offset)
            for row in rows:
                key = (ds, cfg, row["row_idx"])
                if key in seen:
                    continue
                body = prose(str(row.get(field) or ""), genre)
                w = word_count(body)
                feasible = [b for b, (lo, _) in BUCKETS.items() if w >= lo and need(lang, b, genre) > 0]
                if not feasible:
                    continue
                bucket = feasible[-1]          # the longest bucket the document can still fill
                got = cut(body, *BUCKETS[bucket], rng)
                if not got:
                    continue
                excerpt, n_sent = got
                rec = {"id": f"h-{lang}-{genre}-{row['row_idx']}", "kind": "human", "lang": lang,
                       "genre": genre, "bucket": bucket, "words": word_count(excerpt),
                       "dataset": ds, "config": cfg, "split": split, "row_idx": row["row_idx"],
                       "sentences": n_sent, "text": excerpt}
                append_jsonl(out, rec)
                topic = str(row.get(tfield) or "").strip()
                if topic:
                    append_jsonl(topics, {"lang": lang, "genre": genre, "topic": topic[:400],
                                          "source": rec["id"]})
                seen.add(key)
                count[(lang, bucket, genre)] = count.get((lang, bucket, genre), 0) + 1
            short = {b: need(lang, b, genre) for b in BUCKETS}
            print(f"{lang} {genre}: batch {tries}, still needed {short}", file=sys.stderr)


# --------------------------------------------------------------------------- machine text

def cmd_requests(args) -> int:
    """One generation request per machine text, spread over generators, languages, lengths."""
    rng = random.Random(1)
    topics = read_jsonl(path("topics.jsonl"))
    out = path("requests.jsonl")
    if out.is_file() and not args.force:
        print("requests.jsonl exists; --force to rebuild", file=sys.stderr)
        return 1
    out.unlink(missing_ok=True)
    k = 0
    for lang in LANGS:
        pool = [t for t in topics if t["lang"] == lang]
        rng.shuffle(pool)
        i = 0
        for bucket in BUCKETS:
            # 20% more than needed: a text that comes out at the wrong length is filed where it
            # lands, and some cells would otherwise end short.
            for j in range(int(AI_PER_CELL * 1.2)):
                t = pool[i % len(pool)]
                i += 1
                gen = GENERATOR_SHARE[k % len(GENERATOR_SHARE)]
                k += 1
                append_jsonl(out, {"id": f"r-{lang}-{bucket}-{j:03d}", "lang": lang,
                                   "genre": t["genre"], "ask_bucket": bucket, "ask_words": ASK[bucket],
                                   "topic": t["topic"], "generator": gen,
                                   "prompt": PROMPTS[(lang, t["genre"])].format(n=ASK[bucket], topic=t["topic"])})
    print(f"wrote {k} requests", file=sys.stderr)
    return 0


_MD = re.compile(r"^\s*(#+\s.*|\*\*[^*]+\*\*\s*)$", re.M)


def tidy(text: str) -> str:
    """What a reader would see: no markdown headings or bold title lines left behind."""
    text = _MD.sub("", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def chat_local(model: str, prompt: str, seed: int, max_tokens: int, url: str) -> str:
    body = json.dumps({"model": model, "stream": False,
                       "messages": [{"role": "user", "content": prompt}],
                       "options": {"temperature": 0.8, "top_p": 0.95, "seed": seed,
                                   "num_predict": max_tokens}}).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))["message"]["content"]


def cmd_generate(args) -> int:
    gen = args.generator
    if gen not in LOCAL_GENERATORS:
        print(f"{gen} is not a local generator; claude texts come from requests-claude.json", file=sys.stderr)
        return 2
    model = LOCAL_GENERATORS[gen]
    out = path("ai.jsonl")
    done = {r["id"] for r in read_jsonl(out)}
    todo = [r for r in read_jsonl(path("requests.jsonl")) if r["generator"] == gen and r["id"] not in done]
    t_all = time.time()
    for n, r in enumerate(todo, 1):
        seed = int(r["id"].rsplit("-", 1)[1]) + 1000 * LANGS.index(r["lang"])
        try:
            text = tidy(chat_local(model, r["prompt"], seed, int(r["ask_words"] * 2.4) + 40, args.url))
        except Exception as e:  # noqa: BLE001 - one failed request must not end a two-hour run
            print(f"{r['id']}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        w = word_count(text)
        append_jsonl(out, {"id": r["id"], "kind": "ai", "lang": r["lang"], "genre": r["genre"],
                           "bucket": bucket_of(w), "words": w, "generator": gen, "model": model,
                           "topic": r["topic"], "text": text})
        if n % 10 == 0:
            print(f"{gen}: {n}/{len(todo)} in {time.time() - t_all:.0f}s", file=sys.stderr)
    return 0


def cmd_claude_requests(args) -> int:
    """The Claude requests as one file per language, for the agents that write them."""
    reqs = [r for r in read_jsonl(path("requests.jsonl")) if r["generator"] == "claude"]
    for lang in LANGS:
        mine = [{"id": r["id"], "prompt": r["prompt"]} for r in reqs if r["lang"] == lang]
        path(f"requests-claude-{lang}.json").write_text(json.dumps(mine, ensure_ascii=False, indent=1))
        print(f"{lang}: {len(mine)} requests", file=sys.stderr)
    return 0


def cmd_claude_ingest(args) -> int:
    """Fold the agents' answers into ai.jsonl, filed by the length they came out at."""
    out = path("ai.jsonl")
    done = {r["id"] for r in read_jsonl(out)}
    reqs = {r["id"]: r for r in read_jsonl(path("requests.jsonl"))}
    added = 0
    for lang in LANGS:
        recs = read_jsonl(path(f"claude-{lang}.jsonl"))
        # The agents write their answers in blocks of a dozen, as JSON arrays, so that a
        # failure halfway loses one block and not the whole language.
        for part in sorted(OUT.glob(f"claude-{lang}-part*.json")):
            try:
                recs.extend(json.loads(part.read_text()))
            except json.JSONDecodeError as e:
                print(f"{part.name}: not valid JSON ({e}); skipped", file=sys.stderr)
        for rec in recs:
            r = reqs.get(rec.get("id"))
            if not r or rec["id"] in done or not rec.get("text"):
                continue
            text = tidy(rec["text"])
            w = word_count(text)
            append_jsonl(out, {"id": r["id"], "kind": "ai", "lang": r["lang"], "genre": r["genre"],
                               "bucket": bucket_of(w), "words": w, "generator": "claude",
                               "model": "claude-haiku-5-5", "topic": r["topic"], "text": text})
            added += 1
    print(f"added {added} claude texts", file=sys.stderr)
    return 0



def cmd_learners(args) -> int:
    """Second-language essays and their corrected versions, scored but never calibrated on."""
    rng = random.Random(4)
    out = path("learners.jsonl")
    have = read_jsonl(out)
    seen = {r["id"] for r in have}
    for lang, (ds, cfg, split, f_orig, f_corr, total) in LEARNERS.items():
        n = sum(1 for r in have if r["lang"] == lang and r["kind"] == "human_l2")
        tries = 0
        while n < LEARNERS_PER_LANG and tries < 30:
            tries += 1
            rows = fetch_rows(ds, cfg, split, rng.randrange(0, max(1, total - 100)))
            for row in rows:
                rid = f"l-{lang}-{row['row_idx']}"
                if rid in seen or n >= LEARNERS_PER_LANG:
                    continue
                orig = " ".join(str(row.get(f_orig) or "").split())
                corr = " ".join(str(row.get(f_corr) or "").split())
                w = word_count(orig)
                b = bucket_of(min(w, 600)) if w >= 40 else None
                if not b or not corr:
                    continue
                base = {"lang": lang, "genre": "learner", "dataset": ds, "config": cfg,
                        "split": split, "row_idx": row["row_idx"]}
                append_jsonl(out, {"id": rid, "kind": "human_l2", "bucket": b, "words": w,
                                   "text": orig, **base})
                wc = word_count(corr)
                append_jsonl(out, {"id": rid + "-c", "kind": "human_l2_corrected",
                                   "bucket": bucket_of(min(wc, 600)) if wc >= 40 else None,
                                   "words": wc, "text": corr, **base})
                seen.add(rid)
                n += 1
        print(f"{lang}: {n} learner essays", file=sys.stderr)
    return 0


def cmd_italian_long(args) -> int:
    """More long Italian requests for the two local models (PREREG amendment, point 5)."""
    rng = random.Random(5)
    topics = [t for t in read_jsonl(path("topics.jsonl")) if t["lang"] == "it"]
    rng.shuffle(topics)
    out = path("requests.jsonl")
    have = {r["id"] for r in read_jsonl(out)}
    k = 0
    for j in range(args.n):
        t = topics[j % len(topics)]
        gen = ("qwen3", "gemma3")[j % 2]
        rid = f"r-it-long-x{j:03d}"
        if rid in have:
            continue
        append_jsonl(out, {"id": rid, "lang": "it", "genre": t["genre"], "ask_bucket": "long",
                           "ask_words": 450, "topic": t["topic"], "generator": gen,
                           "prompt": PROMPTS[("it", t["genre"])].format(n=450, topic=t["topic"])})
        k += 1
    print(f"added {k} long Italian requests", file=sys.stderr)
    return 0

# --------------------------------------------------------------------------- rewritten

def cmd_rewrite(args) -> int:
    import subprocess

    rng = random.Random(2)
    out = path("rewritten.jsonl")
    done = {r["source"] for r in read_jsonl(out)}
    ai = [r for r in read_jsonl(path("ai.jsonl")) if r["bucket"] in ("medium", "long")]
    picked = []
    for lang in LANGS:
        pool = [r for r in ai if r["lang"] == lang]
        rng.shuffle(pool)
        # spread over the three generators so no family decides the result alone
        by_gen = {g: [r for r in pool if r["generator"] == g] for g in GENERATOR_SHARE}
        k = 0
        while len([p for p in picked if p["lang"] == lang]) < args.per_lang and any(by_gen.values()):
            g = GENERATOR_SHARE[k % 3]
            k += 1
            if by_gen[g]:
                picked.append(by_gen[g].pop())
    reflip = ROOT / "bin" / "reflip"
    for n, r in enumerate(picked, 1):
        if r["id"] in done:
            continue
        # --allow-fact-changes: the detector is measured on what reflip hands back, and the
        # facts it changed are recorded next to the text rather than used to drop it
        p = subprocess.run([str(reflip), "rewrite", "-", "--json", "--allow-fact-changes"],
                           input=r["text"], capture_output=True, text=True, timeout=900)
        if p.returncode != 0:
            print(f"{r['id']}: reflip exited {p.returncode}: {p.stderr[-200:]}", file=sys.stderr)
            continue
        res = json.loads(p.stdout)
        w = word_count(res["text"])
        append_jsonl(out, {"id": "w-" + r["id"], "kind": "ai_reflip", "lang": r["lang"],
                           "genre": r["genre"], "bucket": bucket_of(w), "words": w,
                           "generator": r["generator"], "model": res["model"], "source": r["id"],
                           "edit_ratio": res["edit_ratio"],
                           "facts_altered": (res.get("facts") or {}).get("altered"), "text": res["text"]})
        print(f"rewrite {n}/{len(picked)}", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- status

def cmd_status(args) -> int:
    rows = (read_jsonl(path("humans.jsonl")) + read_jsonl(path("ai.jsonl"))
            + read_jsonl(path("rewritten.jsonl")) + read_jsonl(path("learners.jsonl")))
    table: dict = {}
    for r in rows:
        key = (r["kind"], r["lang"], r["bucket"])
        table[key] = table.get(key, 0) + 1
    for kind in ("human", "ai", "ai_reflip", "human_l2", "human_l2_corrected"):
        print(kind)
        for lang in LANGS:
            print("  ", lang, {b: table.get((kind, lang, b), 0) for b in list(BUCKETS) + [None]})
    gens: dict = {}
    for r in rows:
        if r["kind"] == "ai":
            gens[(r["generator"], r["lang"])] = gens.get((r["generator"], r["lang"]), 0) + 1
    print("ai by generator", gens)
    return 0


def cmd_manifest(args) -> int:
    """What the repository may carry: where each human excerpt came from, and our own texts."""
    humans = [{k: r[k] for k in ("id", "lang", "genre", "bucket", "words", "dataset", "config",
                                 "split", "row_idx", "sentences")} for r in read_jsonl(path("humans.jsonl"))]
    machine = read_jsonl(path("ai.jsonl")) + read_jsonl(path("rewritten.jsonl"))
    target = ROOT / "docs" / "detect" / "corpus-manifest.json"
    target.write_text(json.dumps({"humans": humans, "machine": machine}, ensure_ascii=False))
    print(f"{target}: {len(humans)} human sources, {len(machine)} machine texts", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reflip-detect-corpus", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("humans").set_defaults(fn=cmd_humans)
    r = sub.add_parser("requests")
    r.add_argument("--force", action="store_true")
    r.set_defaults(fn=cmd_requests)
    g = sub.add_parser("generate")
    g.add_argument("generator", choices=sorted(LOCAL_GENERATORS))
    g.add_argument("--url", default="http://localhost:11434")
    g.set_defaults(fn=cmd_generate)
    sub.add_parser("claude-requests").set_defaults(fn=cmd_claude_requests)
    sub.add_parser("claude-ingest").set_defaults(fn=cmd_claude_ingest)
    w = sub.add_parser("rewrite")
    w.add_argument("--per-lang", type=int, default=15)
    w.set_defaults(fn=cmd_rewrite)
    sub.add_parser("learners").set_defaults(fn=cmd_learners)
    il = sub.add_parser("italian-long")
    il.add_argument("--n", type=int, default=40)
    il.set_defaults(fn=cmd_italian_long)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("manifest").set_defaults(fn=cmd_manifest)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
