# For an agent asked to take a watermark out of a text

One command does it, and prints what it did:

```bash
reflip rewrite draft.md --json --progress
```

`--json` puts a single JSON object on standard output. `--progress` puts JSON Lines on
standard error while the work runs, so a caller can show progress without having to pull
the result out from between the progress lines. Read the file, or pass `-` and write the
text to standard input.

The result:

```json
{"v": 1, "transform": "paraphrase", "model": "qwen3:4b-instruct-2507-q4_K_M",
 "text": "the rewritten text", "words": 312, "edits": 231, "edit_ratio": 0.74,
 "coverage": 0.97, "coverage_note": null, "workers": 2, "llm_calls": 8,
 "prompt_tokens": 1820, "completion_tokens": 700, "seconds": 16.4, "notes": {}}
```

`coverage` is the share of five-token windows that contain an edit, which is the quantity
the detector cares about. It is `null` when it was not measured, and `coverage_note` then
says why in a sentence. Anything above 0.9 means every position the detector scores has
been re-randomised.

Exit codes: 0 done, 1 an expected refusal, 2 a usage mistake, 130 an interrupt. A refusal
prints `{"ok": false, "reason": "a sentence"}` and the sentence is meant to be shown to
whoever asked, not paraphrased.

## Before the first run

```bash
reflip server status --json     # is the server up, is the model downloaded, what can this Mac spare
reflip server start --json      # starts one only if nothing is already listening
reflip pull qwen3:4b-instruct-2507-q4_K_M --json   # JSON Lines with completed and total bytes
```

`server status` also reports what the kernel says about memory. When `machine.reasons` is
not empty, the work will run one piece at a time instead of several, and those sentences
explain why. Nothing needs to be done about it; it is there so a slow run can be
accounted for rather than guessed at.

Set `REFLIP_HOST` to point at a server somewhere other than `http://localhost:11434`.

## What to tell the person afterwards

Two facts, and neither of them is "the watermark is gone":

- The measured coverage, and that the detector positions were re-randomised.
- That nobody outside Anthropic can verify the result against Claude's own detector,
  because the secret is private. What was verified is the published algorithm with a
  secret of ours, on an open model, and those numbers are in the repository.

Claiming a removal that was checked against the real detector would be a lie, and it is
the lie every other tool in this space tells.

## Choosing a model

```bash
reflip models --recommended --json     # the catalogue, each entry with what it is bad at
reflip models --search "gemma 3" --json  # Hugging Face, anything in GGUF form
reflip models --measure NAME --samples 3 --json --progress
```

`--measure` is the one that settles an argument: it rewrites watermarked texts with that
model and reports `z_before`, `z_after`, `coverage`, `edit_ratio`, `seconds`,
`tokens_per_1k_words` and a `verdict` sentence. Prefer it over the catalogue's opinion
whenever the choice matters.

A model that watermarks its own output is refused with a sentence and exit 1. Do not work
around that: rewriting Claude's text with Claude leaves it marked.

## Choosing a transform

`--transform paraphrase` is the default and the one that works. `infill` changes fewer
words and keeps more of the original phrasing, at the cost of some grammar with a small
model. `rules` needs no model at all and does not remove the watermark on its own, so use
it only when a model is unavailable and a partial reduction is better than nothing.
`unicode` strips invisible characters and has no effect on a statistical watermark; it is
in the list because people ask for it.
