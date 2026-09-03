# reflip

Rewrite text so that a SynthID-style watermark no longer registers on the detector, and measure that it did.

Since 2 August 2026 Claude's text carries a statistical watermark, "a version of the SynthID-Text approach" in Anthropic's words. The watermark is a bias in which words were chosen; it is not a hidden character, and nobody outside Anthropic holds the key that reads it. `reflip` runs a local model through the text, then runs the published SynthID-Text detector, with a key it owns, on an open model, to check what each kind of edit does. Every number below comes from that check and can be reproduced with two commands.

- **Nothing leaves your machine.** The rewriter is a 2.5 GB model under Ollama. Any OpenAI-compatible endpoint works too.
- **The measurement is the product.** The rewriting is ordinary; the detector before and after, the share of watermark positions left untouched, the meaning kept and the tokens spent are what the forty-odd other "Claude watermark removers" do not publish.
- **It says what it cannot know.** Anthropic's key, context length and detector are private. The benchmark uses the published algorithm at its published settings; the threat-model section says how the answer moves if theirs differ.

## What the numbers say

24 watermarked texts of 144 to 420 tokens, detector z-score before and after each transform. z is the number of standard deviations above chance; unwatermarked text lands between -2 and +2, and z above 4 happens once in thirty thousand by accident. Full table with medians, the weighted-mean score DeepMind's code recommends, and the per-sample texts: `data/results/main/`.

| transform | z before | z after (mean) | z after (max) | z below 4 | positions intact | meaning kept (cosine) | words changed | LLM tokens per 1,000 words | seconds per text |
|---|---|---|---|---|---|---|---|---|---|
| none | 17.6 | 17.5 | 25.3 | 0 of 24 | 0.99 | 1.000 | 0% | 0 | 0 |
| unicode strip | 17.6 | 17.5 | 25.3 | 0 of 24 | 0.99 | 1.000 | 0% | 0 | 0 |
| rules, no model | 17.6 | 15.8 | 24.8 | 0 of 24 | 0.90 | 0.999 | 2% | 0 | 0 |
| infill, stride 4 | 17.6 | 1.5 | 12.6 | 22 of 24 | 0.11 | 0.972 | 28% | 9,900 | 31 |
| infill, stride 3 | 17.6 | 1.5 | 8.3 | 21 of 24 | 0.10 | 0.967 | 40% | 13,400 | 42 |
| infill, stride 2 | 17.6 | 1.2 | 10.1 | 22 of 24 | 0.08 | 0.959 | 58% | 17,900 | 53 |
| rules, then infill (stride 3) | 17.6 | 1.9 | 10.9 | 20 of 24 | 0.11 | 0.968 | 39% | 14,000 | 40 |
| paraphrase | 17.6 | 0.6 | 5.1 | 23 of 24 | 0.04 | 0.956 | 72% | 5,100 | 15 |
| paraphrase, coverage-checked (default with `--tokenizer`) | 17.6 | 0.3 | 2.4 | 24 of 24 | 0.03 | 0.955 | 74% | 5,800 | 17 |
| unwatermarked controls (23) | 0.0 | -0.1 | 1.2 | 23 of 23 | 0.99 | 1.000 | 0% | 0 | 0 |

Rewriter: `qwen3:4b-instruct-2507-q4_K_M` under Ollama on a 16 GB Apple Silicon laptop, temperature 0.7. Watermarked texts: Qwen2.5-1.5B-Instruct with the open SynthID-Text processor (context 4 tokens, 9 keys). "Positions intact" is measured on the re-tokenised edited text and is the quantity the theory is about: 0.04 means 96% of the detector's coins were re-flipped. The identity row sits at 0.99 rather than 1.00 because two texts do not survive a decode/encode round trip byte for byte; that is the floor for every row.

Four things the table settles:

1. **Stripping invisible characters does nothing.** Same score to the second decimal. This is what most "remover" sites do.
2. **Rules without a model do not get there.** Contractions, spelling variants, dashes and stock phrases change 2% of the words and take a tenth off the score. Removal needs an edit in every window of five tokens, and rules cannot supply that density.
3. **One edit per window is enough, on real text.** Every model-driven row re-randomises 90 to 96% of the detector's positions, and the mean score drops from 17.6 to between 0.6 and 1.9, inside the range of unwatermarked text. The theory that predicted this is in `tests/test_synthid.py`, without any language model.
4. **With a small local model, the full rewrite is the cheaper and cleaner way to get those edits.** Slot filling was designed to touch a quarter of the words and spend a fraction of the tokens. On this model it touches 28 to 58% of the words, spends two to three times the tokens of a paraphrase (every retry resends the text, and the numbered JSON answer is not short), takes twice as long, and leaves grammar slips that the meaning score does not see. The paraphrase reaches z 0.6 with 5,100 tokens per thousand words in 15 seconds. So the default is `paraphrase`; `infill` stays for the case where keeping most of the original wording matters more than fluency.

What is left over after a single paraphrase: one English sample stays at z 5.1 because the model rewrote it lightly (a third of the positions intact). That is why `reflip run` with `--tokenizer` re-asks the model for any paragraph in which fewer than 90% of the token windows carry an edit, and prints the coverage it reached. The "coverage-checked" row is that mode: every one of the 24 texts ends inside the range of the unwatermarked controls (maximum z 2.4 against the controls' 1.2), for 14% more tokens and two more seconds. The two Italian texts came out worse under every transform with this 4B model; a rewriter that is fluent in the language matters.

## Why the "watermark remover" websites do nothing

At every step, the sampler hashes a secret key together with the previous 4 tokens and each candidate token into a coin flip (a "g-value"), and nudges the choice toward candidates whose coins came up 1. The detector recomputes the same coins for a text and checks whether their mean is above 0.5. Stripping zero-width spaces, curly quotes or metadata leaves every coin exactly where it was. `reflip check` still lists the invisible characters in a file, because that is the only thing anyone can check without the key.

## Why one edit in five tokens is enough

Each coin depends on a token **and the 4 tokens before it**. Change one token, and the detector's recomputed coins for that token and for the 4 that follow it become fresh, unbiased flips: their hash context is no longer the one the sampler saw. If every window of 5 consecutive tokens contains at least one edited token, every coin is re-randomised and the detector sees noise, whatever the strength of the watermark. That is one edit in five tokens, about one word in three or four.

`tests/test_synthid.py` shows this without a language model: a toy generator that picks, among random candidates, the one with the most 1-coins scores z above 10 on 300 tokens; replacing every 5th token brings it below 4; replacing every 10th halves it. The benchmark shows it on real text, after re-tokenisation.

## What is verified, and what is not

- Verified: on the open SynthID-Text implementation (`transformers`' `SynthIDTextWatermarkLogitsProcessor`, ngram length 5, 9 keys, the paper's settings) applied to an open model, each transform's effect on the mean-g detector and on the weighted-mean detector, the share of positions left intact, meaning kept, words changed, tokens and time.
- Not verified, because it cannot be: Anthropic's key, context length, number of layers and detector. Anthropic says the watermark "may persist through some editing" and that "a complete rewrite where every word is replaced will" remove it, which is what the paraphrase row measures.

## Install

```bash
git clone https://github.com/nerln/reflip
pip install -e "./reflip[bench]"      # [bench] adds torch and transformers, needed for the coverage check and the benchmark
ollama pull qwen3:4b-instruct-2507-q4_K_M
```

## Use

```bash
reflip run draft.md -o clean.md                                    # paraphrase with the local model
reflip run draft.md --tokenizer Qwen/Qwen2.5-1.5B-Instruct -o clean.md   # same, and re-ask until 90% of 5-token windows carry an edit; prints the coverage
reflip run draft.md --transform infill --stride 3 -o clean.md      # touch fewer words, accept some grammar slips
reflip run draft.md --transform rules -o clean.md                  # no model at all: partial, see the table
reflip check draft.md                                              # invisible characters, and what cannot be checked
```

Any OpenAI-compatible endpoint works as the rewriter: `--base-url https://api.deepseek.com/v1 --api-key ... --model deepseek-chat`. Do not use a rewriter that watermarks its own output: Gemini does, and Claude models launched since August 2026 do. Models run under Ollama, llama.cpp or vLLM carry no watermark unless the operator adds one.

The coverage figure needs a tokenizer to count windows. Claude's is not public; the benchmark model's tokenizer is a proxy of similar granularity, and the threshold leaves margin.

## Benchmark

Reproduce: `reflip corpus --attn eager` (generates the watermarked and control texts, about 15 minutes on an M-series Mac), then `reflip bench --sweep-stride 2,3,4`. Transform outputs are cached, so re-scoring with other settings does not call the model again.

- **Corpus.** 24 prompts (22 English, 2 Italian: essays, emails, explanations, a story, a memo, a review) completed at temperature 0.9, top-p 0.95, with the watermark, and 23 completions of the same prompts without it as controls. Watermarked completions score between 8.6 and 25.3; controls between -1.6 and +1.2.
- **Detector.** Mean g-value, the paper's basic score, and the weighted-mean score DeepMind's reference code recommends, both as z-scores against the unwatermarked null.
- **Intact.** The fraction of positions whose g-value the detector recomputes unchanged, measured on the re-tokenised edited text.
- **Meaning and cost.** Cosine similarity of multilingual-e5-small embeddings between original and edited text, share of words changed, LLM tokens per thousand input words, wall time.

## What the other tools do

More than forty "Claude watermark remover" repositories and sites appeared in August 2026. They fall into three groups: invisible-character strippers (verifiable, and irrelevant to the statistical watermark; several miss variation selectors), "rewrite it with another model" wrappers with no measurement, and a few measurement studies that decline to claim removal. None publishes before-and-after numbers against a SynthID-class detector together with a quality cost. That gap is what this repository fills.

## Threat model, honestly

- **Context length.** The published SynthID-Text uses the previous 4 tokens (the Nature paper: "we use H = 4"), and Anthropic's description is "a few words that come before". A longer context means one edit re-randomises more coins and a sparser rewrite would do; a shorter one needs a denser rewrite. The paraphrase row changes 72% of the words and does not depend on the context length in any realistic range.
- **Tokenizer.** Anthropic's is not public. Word-level strides do not depend on it; the coverage check uses a proxy tokenizer of similar granularity.
- **Detector.** Anthropic may run a trained detector rather than the mean score. Every such detector is a function of the same g-values; once they are re-randomised there is nothing left to weight. Partial removal, the rules row, is where detectors differ, which is why both scores are reported.
- **Repeated contexts.** SynthID does not watermark a position whose 4-token context already appeared in the text, and the detector masks the same positions. The benchmark scores exactly what the detector would see, so this is inside the numbers.
- **Low-entropy text.** Code, lists of facts and very short texts carry little watermark to begin with, as Anthropic also says. The tool leaves code blocks, URLs, e-mails and placeholders untouched.

## Licence

MIT.
