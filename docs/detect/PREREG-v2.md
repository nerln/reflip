# Detection, second protocol: a stricter threshold on more human text

Written on 31 October 2026, after the first protocol's results (PREREG.md) were known and
before any text of this second round was drawn, generated or scored. Anything changed after a
result of this round was seen is recorded at the bottom with the reason.

## Why a second round

The first round gave a verdict in one cell of nine. Five of the eight refusals came from the
false-positive bound: with 300 test humans per cell the 2% bound allows one false positive,
and a threshold aimed at 1% flags about three. This round asks whether a threshold aimed lower,
measured on more human text, gives verdicts where the first could not, without loosening the
rule. It also fills two gaps the first left: Italian second-language writers, and Claude
models other than Haiku.

## Fixed before anything is measured

- **Detectors, not chosen again.** The command line keeps Binoculars on the Qwen2.5 1.5B pair,
  the browser Binoculars on the 4-bit 0.5B pair, as the first round chose them.
- **The rule, unchanged.** A language and length cell gets a verdict only if its test AUROC has a
  95% lower bound of at least 0.85, the threshold catches at least half of its machine texts,
  and the one-sided 95% Clopper-Pearson upper bound of its test false-positive rate is at most 2%.
- **The threshold.** Per length, on the calibration humans of the three languages together, at
  the **99.5th percentile** (aimed at 0.5% false positives). The 99th percentile is reported
  beside it as a secondary number and is not used for verdicts.
- **What ships.** If this round gives a verdict in more cells than the first, the command line
  and the browser switch to its calibration. If not, they keep the first round's.

## The data, all of it new

Nothing from the first round is reused for calibration or test, so no number of this round
rests on texts whose scores were already seen.

**Human texts**: 1,000 per language and length, half encyclopaedic and half news, drawn with
seed 10 from the first round's sources, excluding every document the first round used: English
Wikipedia and BBC (XSum); Italian Wikipedia and Il Post, with **Fanpage** (`ARTeLab/fanpage`)
added for Italian news when Il Post runs out of long articles (it gave only 120 long ones in
the first round); Spanish Wikipedia and El País (MLSUM). Lengths as before: 40 to 99, 100 to
300, 301 to 600 words. Split per cell: **250 for calibration, 750 for test**. A cell that cannot
be filled is reported with the number it reached.

**Machine texts**: 60 per language and length, all test, on topics from the new human
documents, asked for at the target length and filed by the length they came out at:
- 20 from `qwen3:4b-instruct-2507-q4_K_M` and 20 from `gemma3:4b`, locally, as before;
- 20 from **Claude Sonnet 5.5**, written by agents given the same prompts.

**Second-language writers**, test only, never calibrated on: Italian learner essays from MERLIN
(`aseifert/merlin`, `italian.jsonl`, sentences joined back into essays by their document id),
with their corrected versions; the first round's English and Spanish learner essays are scored
again with the new threshold.

**Machine text rewritten by reflip**: 15 per language from the new machine texts, medium and
long, through `reflip rewrite` with its defaults, test only.

## What is reported

Per cell, on the test half: AUROC with its bootstrap interval; at the 99.5% threshold the
machine texts caught and the human texts flagged, with the Clopper-Pearson bound and the
verdict; the same at the 99% threshold, marked secondary. By generator, Claude Sonnet included.
Learners' false-positive rates at both thresholds. Rewritten text's AUROC and catch rate.

## Changes after seeing results

None yet.
