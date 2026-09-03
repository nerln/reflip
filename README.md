# reflip

Remove SynthID-style text watermarks (the kind Claude has carried since 2 August 2026) with the fewest possible edits, and **measure** that you did.

- **Algorithmic where it can be, LLM only where it must.** A rule pass changes tokens without any model. A local model fills the gaps. Nothing leaves your machine.
- **Token-frugal.** The default mode rewrites about a quarter of the words, not the whole text. With Ollama that is zero API tokens.
- **Verifiable.** Nobody outside Anthropic has the key, so nobody can score Claude text. What can be done is to run the *published* algorithm (Google DeepMind's SynthID-Text, the one Anthropic says it uses "a version of") with a key we own, on an open model, and read the detector before and after each transform. `reflip bench` does exactly that, and the numbers below come from it.

## Why the "watermark remover" websites do nothing

The watermark is not a hidden character. It is a bias in *which words were chosen*. At every step, the sampler hashes a secret key together with the previous 4 tokens and each candidate token into a coin flip (a "g-value"), and nudges the choice toward candidates whose coins came up 1. The detector recomputes the same coins for a text and checks whether their mean is above 0.5. Stripping zero-width spaces, curly quotes or metadata leaves every coin exactly where it was. `reflip check` will still tell you what invisible characters a text contains, because that is the only thing anyone can check without the key.

## Why you do not need to rewrite everything

Each coin depends on a token **and the 4 tokens before it**. Change one token, and the detector's recomputed coins for that token and for the 4 that follow it become fresh, unbiased flips: their hash context is no longer the one the sampler saw. So if every window of 5 consecutive tokens contains at least one edited token, *every* coin is re-randomised and the detector sees noise, no matter how strong the watermark was. That is one edit in five tokens, about one word in three or four. `reflip` picks those words to be content words, where a synonym costs nothing, and lets a local model choose the synonym. Rule-based edits (contractions, spelling variants, dashes, stock phrases) are used first, so the model has less to do.

`tests/test_synthid.py` shows this without any language model: a toy generator that picks, among random candidates, the one with the most 1-coins scores z > 10 on 300 tokens; replacing every 5th token brings it to |z| < 4 (noise); replacing every 10th halves it.

## What is verified, and what is not

- Verified: on the open SynthID-Text implementation (`transformers`' `SynthIDTextWatermarkLogitsProcessor`, ngram length 5, 9 keys) applied to an open model, each transform's effect on the mean-g detector, on the fraction of coins left untouched, and on meaning (embedding cosine) and edit volume. See the table below and `data/results/`.
- Not verified, because it cannot be: Anthropic's key, context length, number of layers, or detector. Anthropic says the watermark "may persist through some editing" and that "a complete rewrite where every word is replaced will" remove it. If their context is longer than 4 tokens, fewer edits are needed than here; if it is shorter, more. `--stride` controls the density; the `paraphrase` mode rewrites everything and does not depend on the context length at all.

## Install

```bash
pip install reflip              # the tool
pip install "reflip[bench]"     # + torch/transformers for the benchmark
ollama pull qwen3:4b-instruct-2507-q4_K_M   # default local rewriter (2.5 GB)
```

## Use

```bash
reflip run draft.md -o clean.md                    # hybrid: rules, then local infill (default)
reflip run draft.md --transform infill --stride 3  # infill only
reflip run draft.md --transform paraphrase         # full rewrite, most robust, most tokens
reflip run draft.md --transform rules              # no model at all (partial removal, see table)
reflip check draft.md                              # invisible characters, and a reminder of what cannot be checked
```

Any OpenAI-compatible endpoint works as the rewriter: `--base-url https://api.deepseek.com/v1 --api-key ... --model deepseek-chat`. Do not use a rewriter that watermarks its own output (Gemini does; new Claude models do).

Pass `--tokenizer Qwen/Qwen2.5-1.5B-Instruct` to choose edit positions in token space and to get a coverage figure ("97% of 5-token windows contain an edit") in the report line.

## Benchmark

RESULTS_TABLE

Reproduce: `reflip corpus` (generates the watermarked and control texts, ~15 min on an M-series Mac), then `reflip bench`.

## Licence

MIT.
