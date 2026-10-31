# How well does the facts check see changed facts? The protocol, fixed before any number

Written on 31 October 2026, before the sample was drawn and before any annotation existed.
Anything changed after a result was seen is recorded at the bottom with the reason.

## The question

`reflip diff` (reflip/facts.py, and docs/app/facts.js line for line) counts numbers, names,
negations and quantifiers that a rewrite dropped or added. Until now it was tested only on
cases written by hand. On real rewrites: when it says a kind of fact changed, did it? When a
fact of that kind changed, did it say so? And how often does a rewrite change the meaning in
a way none of the four kinds covers, which the check cannot see at all?

## The sample

Paragraph pairs, original and rewrite, at least 30 words in the original, drawn with seed 0:

| stratum | source | pairs |
| --- | --- | --- |
| paraphrase, before the guard | `data/results/main/paraphrase.jsonl` against `data/corpus.jsonl` | 30 |
| infill, stride 3, with the guard | `data/results/facts/infill.jsonl` | 30 |
| browser rewriters | `data/results/browser-rewriters.jsonl` (Qwen2.5 0.5B, Gemma 3 1B) | 30 |
| reflip rewrites in Italian and Spanish | `data/detect/rewritten.jsonl` against `data/detect/ai.jsonl` | 30 |

Paragraphs are aligned by position after splitting on blank lines; a pair is eligible only if
original and rewrite have the same number of paragraphs. All texts are machine texts or the
benchmark's own watermarked texts: no human excerpt from the detection corpus is used.

The 120 pairs are split, with seed 0 and stratified, into a **development half** (60) and a
**held-out half** (60).

## The reference: two blind annotators, a third to settle

Each pair is annotated by two Claude Sonnet 5.5 agents working independently, who never see
the facts check's output. For each pair they list, in the original's language:

- numbers dropped or added (a figure written as digits or as words is the same number);
- names dropped or added (people, places, organisations, works; a name moved or re-cased is kept);
- whether a negation was lost or added, so that a statement's polarity flipped;
- quantifiers whose strength changed (all, most, some, only, at least, about, and the like);
- any other change of meaning, in one line each.

Where the two disagree on whether a kind changed, a third Sonnet 5.5 agent, shown both
annotations and the texts, decides by majority. The reference is that majority. The agents'
instructions are in `docs/facts/annotation-instructions.md`, written with this file.

## What is measured

On all 120 pairs, for the facts check as it stands at commit time of this file:

- per kind (numbers, names, negations, quantifiers): pair-level **precision** (the check says
  the kind changed, and the reference agrees) and **recall** (the reference says it changed,
  and the check agrees), with Wilson 95% intervals;
- the same for "any of the four kinds";
- the **share of pairs whose meaning changed only in ways outside the four kinds**, with its
  interval: what the check cannot see. A pair counts when both first annotators list another
  change of meaning and the reference has none of the four kinds;
- agreement between the first two annotators, Cohen's kappa per kind.

## Improving it without fooling ourselves

The errors of the development half may be read and the check changed to fix them. Every such
change is listed below with the error that prompted it. The changed check is then measured once
on the held-out half, whose errors are not read before that number exists. The README reports
the first measurement on all 120 pairs and the held-out one, and says which is which.

## Changes after seeing results

Measured first, on all 120 pairs, as fixed above: `data/results/facts-eval/summary-all-v1-check.md`.
Then the development half's errors were read (only those) and these changes made:

1. **Names.** Fourteen false alarms on the development half. A colon followed by a space now
   opens a clause ("Tip 3: Putting..."); words inside a label in bold are not names; in English
   a word ending in -ing is not a name, nor is a capitalised function word (By, During, Some, a
   short list per language in facts_lexicon.json); a possessive, a plural s and a hyphen no
   longer make a different name (Amazon's, RRSPs, Tax-Free).
2. **Negations are shown, not counted.** Ten false alarms on the development half and one flip
   in all 120 pairs: the count of negation words changes whenever a rewrite says "failed to"
   for "did not", "lacking" for "without". The check still reports the counts, as a line to look
   at, and no longer adds them to the facts changed or re-asks a paragraph over them. Its
   negation row below is still measured the way a reader would see it.
3. **Quantifiers.** A few words seen in the errors joined the lexicon: handful, countless,
   plenty, virtually, practically; scarsi, talora; escasos, ocasional, rara vez.
4. **The reference.** Some annotators listed a quantifier while writing "(same)" next to it;
   those entries no longer count as a change. This applies to both halves.

The changed check was then measured once on the held-out half, below.
