# Detecting AI text: the protocol, fixed before any number was seen

Written on 21 October 2026, before the corpus existed and before any detector was run on
it. Anything changed after a result was seen is recorded at the bottom with the reason,
so a reader can tell a decision made in advance from one made after looking.

## The question

How well do open, zero-shot detectors tell human writing from machine writing in Italian,
Spanish and English, at three lengths, including machine text that reflip has rewritten?
And, separately: can the watermark detector find a watermark whose secret it holds?

## The corpus

**Human texts.** Drawn at random offsets, one excerpt per source document, cut at a
sentence boundary to the target length:

| language | encyclopaedic | news |
| --- | --- | --- |
| English | Wikipedia, 1 Nov 2023 snapshot (`wikimedia/wikipedia`, `20231101.en`) | BBC articles from XSum (`EdinburghNLP/xsum`, 2010 to 2017) |
| Italian | Wikipedia, `20231101.it` | Il Post articles (`ARTeLab/ilpost`, 2020 to 2021) |
| Spanish | Wikipedia, `20231101.es` | El País articles from MLSUM (`GEM/mlsum`, `es`, 2010 to 2019) |

The Wikipedia snapshot postdates November 2022, so a few edits may have been written with
a model. That risk is accepted and stated, because the larger risk on Wikipedia goes the
other way: the detectors' own models have read it, and memorised text looks machine-made
to a perplexity-based detector. The genre split is reported so that this shows.

**Lengths**, in words: short 40 to 99, medium 100 to 300, long 301 to 600.

**Sizes per language and length**: 150 human texts and 40 machine texts. Human texts are
cheap and set the false-positive rate, which is the number a person accused of using a
model cares about.

**Machine texts** are written on the topic of a human document (its title or its summary),
in the same language and genre, asked for at the target length, then filed by the length
they actually came out at. Three families, about a third each:

- `qwen3:4b-instruct-2507-q4_K_M`, local;
- `gemma3:4b`, local;
- `claude-haiku-5-5`, through the `claude` command line.

**Rewritten machine texts**: 15 per language from the medium and long buckets, put through
`reflip rewrite` (paraphrase with the coverage check, default model). Reported on their
own and not used to choose a detector.

## The detectors

All of them read at most 512 tokens and use a pair of models that share a tokenizer, an
observer (base) and a performer (instruct):

1. **Binoculars**: perplexity of the text under the performer, divided by the
   cross-perplexity between observer and performer. Lower means more machine-like.
2. **Fast-DetectGPT**, analytic form, two variants: reference and scoring model both the
   observer; reference the performer and scoring the observer. Higher means more
   machine-like.
3. **Perplexity** under the observer. Lower means more machine-like.
4. **Burstiness**: the standard deviation of the per-sentence mean negative log-likelihood
   under the observer. Lower means more machine-like. Needs two sentences.
5. **Perplexity plus burstiness**: a two-feature logistic regression, fitted on the
   calibration half only.

**Model pairs**: `Qwen/Qwen2.5-0.5B` with `Qwen/Qwen2.5-0.5B-Instruct`, and
`Qwen/Qwen2.5-1.5B` with `Qwen/Qwen2.5-1.5B-Instruct`. Both pairs exist in ONNX form, so
the browser version can run the same weights.

## How it is measured

Each language and length cell is split in half, stratified by class, with seed 0. The
calibration half fits thresholds and probability maps; **every reported number comes from
the test half**.

- **AUROC**, with a 95% bootstrap interval (2,000 resamples).
- **The 1% false-positive threshold**, set per length on the calibration humans of all
  three languages together, so that it rests on 225 texts instead of 75; then the
  false-positive rate and the true-positive rate that threshold gives on the test half,
  per cell, with intervals.
- Broken down by language, length, generator, human genre, and for reflip's rewrites.

## Decisions fixed now

**Which detector becomes the default.** The detector and pair with the highest mean test
AUROC over the six medium and long cells. If two are within 0.005, the 0.5B pair wins,
because it is the one a browser can download.

**When to refuse a verdict.** A language and length cell gets a verdict only if its test
AUROC has a 95% lower bound of at least 0.85 *and* the 1% threshold catches at least half
of its machine texts. Otherwise the command line refuses for that language at that length
and prints the two numbers that made it refuse.

**What the output says.** Never a bare "AI" or "human". The share of measured human texts
that scored at least as machine-like, with its interval; the verdict at the 1% threshold
where one is allowed; and a probability only under a stated 50 percent prior.

**The watermark.** Measured only on texts marked with a secret the detector holds (the
benchmark's own). Anthropic's watermark, live since 2 August 2026, and Google's cannot be
detected without their secrets, and the tool says so wherever it offers watermark
detection.

## Amendment of 21 October 2026, before any score was computed

Made after the expansion council (docs/council/2026-10-21-espansione.md) and before any
detector had scored a single text of this corpus. No benchmark number existed when it was
written, so it is a change of protocol, not a reaction to a result.

1. **More human texts.** 75 test humans per cell cannot support the phrase "1% false
   positives": zero errors in 75 only bounds the true rate below about 3.9%. Each language and
   length now has **400 human texts: 100 for calibration, 300 for test**. The 1% threshold is
   still set per length on the calibration humans of all three languages together, now 300
   texts. Machine texts keep the 50/50 split.
2. **The refusal rule also looks at false positives.** A cell gets a verdict only if, in
   addition to the two conditions above, the one-sided 95% upper bound (Clopper-Pearson) of
   its test false-positive rate at the threshold is **at most 2%**. With 300 test humans that
   allows at most one human text flagged. The answer then states that bound, per language
   and length, instead of saying "1%".
3. **Writers in a second language are their own population.** Perplexity-based detectors
   are known to flag them (Liang et al., 2023), and they are the people most likely to be
   accused. Where a learner corpus is openly available for a language, its texts are scored
   and their false-positive rate at the threshold is reported separately. They are not used
   for calibration and not used to choose the detector. A language with no openly available
   learner corpus is reported as not measured.
4. **What the output says.** The probability under a 50% prior is dropped from what a person
   reads: it invites a reading as "the chance this person cheated". The answer is the share of
   measured human texts that scored at least as machine-like, with its interval, and the
   verdict where the cell allows one.
5. **Italian long machine texts.** Claude Haiku wrote most long Italian requests short, so the
   Italian long cell has fewer machine texts than the others. More long Italian texts are
   requested from the two local models until the cell has 40.

6. **The browser's detector is calibrated on its own files.** The browser runs the 0.5B pair
   as 4-bit ONNX files (`onnx/model_q4f16.onnx` of `onnx-community/Qwen2.5-0.5B` and
   `-Instruct`), because that is what a browser can download. Its scores differ from the
   full-precision ones (on one test sentence Binoculars was 0.97 against 1.04), so the browser
   gets its own thresholds and its own table of allowed and refused cells, computed on the same
   split with the same rules, for the detector chosen above. The command line keeps the
   full-precision pair.

Added the same day, after the corpus was built and before any detector scored it:

7. **Italian long human texts: 320, not 400.** The two Italian sources ran out of articles over
   300 words before the target. That cell has 100 human texts for calibration and 220 for test,
   so zero false positives bound the rate under 1.4%, and one already exceeds the 2% bound.
8. **No extra Italian long requests were needed.** The first round of generation filed 40
   Italian texts in the long bucket, which point 5 asked for.

## How the run went, before any result was looked at

- The full-precision 0.5B pair stopped twice on Apple's GPU running out of memory (after 166
  and 395 texts, with other programs holding 15 to 16 GB). Scoring resumes where it stopped,
  one text at a time, so the scores of the texts already done are unchanged. The detector now
  frees the GPU's pool after each text and retries a text that does not fit.
- The browser's 4-bit pair was scored with onnxruntime on the processor, which is also where
  the browser runs it: on WebGPU the same files gave other scores (Binoculars 1.245 against
  0.995 on one text), while the browser's own processor backend matched onnxruntime to the
  third decimal on the two texts compared. So the browser calibration describes what the page
  computes.

## Results, 22 October 2026

Full tables: `data/results/detect/summary.md`. All numbers from the test half.

- **Chosen detector:** Binoculars on the 1.5B pair, mean test AUROC 0.965 over the six medium
  and long cells (0.5B pair: 0.942; the browser's 4-bit 0.5B pair: 0.947).
- **Verdicts the command line gives:** one cell of nine, English long: AUROC 0.97 (0.95 to
  0.99), the threshold catches 12 of 24 machine texts and flagged 0 of 300 human texts, so the
  false-positive rate is under 1.0% at 95%. Every other cell is refused. Short texts fail on the
  AUROC bound (0.73 to 0.80); English medium catches 46%, under half; the other four fail the
  false-positive bound, flagging 2 to 11 of 220 to 300 human texts.
- **Verdicts the browser gives:** none. Its best cell, Italian long, has AUROC 0.99 and catches
  80%, but flagged 3 of 220 human texts.
- **Machine text rewritten by reflip:** AUROC against humans 0.56 (medium) and 0.71 (long), 25%
  and 19% caught at the threshold, against 0.95 and 0.98 for machine text at the same lengths
  that was not rewritten.
- **Writers in a second language:** at the threshold, 0 of 135 English learner essays (medium)
  and 3 of 130 Spanish ones (2.3%, up to 5.9%); the corrected Spanish versions, 7 of 132 (5.3%).
  Italian learners: not measured, no open corpus found.
- **By generator:** Claude Haiku 5.5 is the hardest to tell apart at every length (AUROC 0.75,
  0.92, 0.95 for short, medium, long), the two local 4B models the easiest.

## Changes after seeing results

None to the tool: it ships the calibration the pre-registered rules produced.

One exploratory analysis, decided after seeing that most refusals came from the false-positive
bound: a threshold per language and length instead of one per length
(`data/results/detect/exploratory-per-language.md`). It made things worse, 0 cells of 9 on
either pair, because 100 calibration texts give a noisier 99th percentile than 300. What the
numbers say instead: with about 300 test humans per cell, the 2% bound allows one false positive,
and a threshold aimed at 1% flags about three. A verdict at this strictness needs either a
threshold aimed lower than 1%, which catches less, or several times more human text per cell.
