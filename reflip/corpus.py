"""Build the benchmark corpus: the same prompts completed with and without the watermark.

Output: data/corpus.jsonl, one JSON object per line:
  {"id": "wm-003", "prompt": ..., "text": ..., "ids": [...], "watermarked": true,
   "z": 12.3, "tokens": 351, "lang": "en", "model": "...", "temperature": 0.9, "top_p": 0.95}
Plain controls have id "plain-003" and watermarked=false.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROMPTS: list[tuple[str, str]] = [
    ("en", "Write a 300-word essay on why cities should invest in public libraries."),
    ("en", "Write a friendly email to a landlord asking to repair a broken heater, about 250 words."),
    ("en", "Explain to a curious teenager how vaccines train the immune system, in about 300 words."),
    ("en", "Write a product description for a mechanical keyboard aimed at programmers, about 250 words."),
    ("en", "Write the opening scene of a short story in which a lighthouse keeper receives an unexpected letter. About 350 words."),
    ("en", "Write a blog post intro about learning to cook after moving out for the first time, 300 words."),
    ("en", "Write a cover letter for a junior data analyst position at a logistics company, about 300 words."),
    ("en", "Explain what compound interest is and why it matters for someone in their twenties, 300 words."),
    ("en", "Write a persuasive op-ed arguing that cities should build more protected bike lanes, 350 words."),
    ("en", "Describe a day in the life of a beekeeper in early spring, about 300 words, third person."),
    ("en", "Write a FAQ answer explaining why a web app might log a user out unexpectedly, 250 words."),
    ("en", "Write a wedding toast from the best man to a couple who met while hiking, about 300 words."),
    ("en", "Summarise the causes of the 2008 financial crisis for a general reader in about 350 words."),
    ("en", "Write an encouraging message to a friend who just failed their driving test, about 250 words."),
    ("en", "Explain how a bill becomes a law in a parliamentary system, about 300 words."),
    ("en", "Write a travel-guide paragraph set about a small coastal town in Portugal, about 300 words."),
    ("en", "Write a reflective journal entry about the first week of a new job, about 300 words."),
    ("en", "Explain the rules of chess to a complete beginner in about 350 words."),
    ("en", "Write an internal memo announcing a switch to a four-day work week pilot, about 300 words."),
    ("en", "Write a review of a fictional neighbourhood ramen restaurant, about 300 words."),
    ("en", "Explain what a hash table is and when to use one, for a bootcamp student, about 300 words."),
    ("en", "Write a speech for a high-school graduation given by a science teacher, about 350 words."),
    ("it", "Scrivi un testo di circa 300 parole che spiega a un adolescente perché conviene imparare a cucinare."),
    ("it", "Scrivi una lettera di circa 250 parole a un amico per raccontargli un viaggio in treno attraverso la Spagna."),
]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--out", default="data/corpus.jsonl")
    ap.add_argument("--n", type=int, default=len(PROMPTS), help="number of prompts to use")
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--max-new-tokens", type=int, default=420)
    ap.add_argument("--min-tokens", type=int, default=120)
    ap.add_argument("--temperature", type=float, default=0.9)
    ap.add_argument("--top-p", type=float, default=0.95)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default=None)
    ap.add_argument("--dtype", default="float16", choices=["bfloat16", "float16", "float32"])
    ap.add_argument("--attn", default="sdpa", choices=["sdpa", "eager"])
    args = ap.parse_args(argv)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    from .synthid import PortableSynthID, Scorer, generate_watermarked

    device = args.device or ("mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu")
    tok = AutoTokenizer.from_pretrained(args.model, padding_side="left")
    dtype = torch.float32 if device == "cpu" else getattr(torch, args.dtype)
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=dtype, attn_implementation=args.attn).to(device).eval()
    proc = PortableSynthID(device=device)
    scorer = Scorer(tok)

    prompts = PROMPTS[: args.n]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    f = out.open("w")
    t_all = time.time()
    for b in range(0, len(prompts), args.batch):
        chunk = prompts[b : b + args.batch]
        texts = [tok.apply_chat_template([{"role": "user", "content": p}], tokenize=False, add_generation_prompt=True) for _, p in chunk]
        for watermarked in (True, False):
            t0 = time.time()
            ids_list = generate_watermarked(model, tok, texts, proc if watermarked else None,
                                            max_new_tokens=args.max_new_tokens, temperature=args.temperature,
                                            top_p=args.top_p, seed=args.seed + b)
            for k, ((lang, prompt), ids) in enumerate(zip(chunk, ids_list)):
                idx = b + k
                if len(ids) < args.min_tokens:
                    print(f"skip {idx} ({'wm' if watermarked else 'plain'}): only {len(ids)} tokens", file=sys.stderr)
                    continue
                text = tok.decode(ids, skip_special_tokens=True)
                sc = scorer.score_ids(ids)
                rec = dict(id=f"{'wm' if watermarked else 'plain'}-{idx:03d}", prompt=prompt, text=text, ids=ids,
                           watermarked=watermarked, z=sc.z, tokens=len(ids), lang=lang, model=args.model,
                           temperature=args.temperature, top_p=args.top_p)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                print(f"{rec['id']}: {len(ids)} tokens, z={sc.z:+.2f}", file=sys.stderr)
            print(f"batch {b}-{b+len(chunk)-1} {'wm' if watermarked else 'plain'} done in {time.time()-t0:.0f}s", file=sys.stderr)
    f.close()
    print(f"wrote {out} in {time.time()-t_all:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
