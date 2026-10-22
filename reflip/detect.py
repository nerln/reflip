"""Telling human writing from machine writing, and saying how sure the answer can be.

reflip started as the tool that takes a watermark out. This is the other direction: look at
a text and estimate whether a model wrote it. Two families of evidence exist, and they are
not the same kind of thing.

**A watermark** is proof, but only for whoever holds the secret. reflip can find the
SynthID-style watermark its own benchmark uses, because it holds that secret. It cannot find
Anthropic's (on every Claude model launched since 2 August 2026) or Google's, and nothing
outside those companies can: the secret is the whole point of the design. Every place this
module is offered says so.

**Zero-shot statistics** need no secret and prove nothing on their own. Machine text tends
to be more predictable to a language model than human text, and the detectors below turn
that tendency into a score. How far the score can be trusted depends on the language, the
length and who wrote the text, and that is measured, not assumed: see docs/detect/PREREG.md
and the numbers it produced.

The detectors, all computed from one forward pass of each of two models that share a
tokenizer, an observer (a base model) and a performer (its instruct version):

- Binoculars (Hans et al., 2024): perplexity under the performer divided by the
  cross-perplexity between the two. Lower is more machine-like. The division is the idea:
  a prompt can make human-looking text predictable, and dividing by how predictable the
  observer expected *any* continuation to be cancels most of that.
- Fast-DetectGPT, analytic form (Bao et al., 2024): how much more likely the actual tokens
  are than the tokens the reference model would have sampled, in standard deviations.
  Higher is more machine-like.
- Perplexity under the observer, and burstiness: the spread of perplexity from sentence to
  sentence, which is GPTZero's published intuition. Both are the baselines the others have
  to beat.

The arithmetic is kept in plain functions over logits so it can be tested without loading a
model, and so the browser version can be checked against it number for number.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass

# The pairs the protocol measures. Both exist as ONNX files for the browser, which is why
# the choice is between these and not a larger pair that would score better on a server.
PAIRS: dict[str, tuple[str, str]] = {
    "qwen2.5-0.5b": ("Qwen/Qwen2.5-0.5B", "Qwen/Qwen2.5-0.5B-Instruct"),
    "qwen2.5-1.5b": ("Qwen/Qwen2.5-1.5B", "Qwen/Qwen2.5-1.5B-Instruct"),
}
DEFAULT_PAIR = "qwen2.5-0.5b"
MAX_TOKENS = 512
# Vocabulary-sized tensors are 600 KB per position in float32; 512 positions at once is
# 300 MB per tensor and there are five. Accumulating over chunks keeps the peak flat.
CHUNK = 128

_SENTENCE_END = re.compile(r"[.!?…]+[\"'”’»)\]]*(?=\s|$)")


@dataclass
class Features:
    """Everything the detectors read from one text. Numbers only, never the text itself."""

    tokens: int
    nll_obs: float           # mean negative log-likelihood under the observer
    nll_perf: float          # the same under the performer
    xent: float              # mean cross-entropy, observer's distribution against performer's
    binoculars: float        # nll_perf / xent; lower is more machine-like
    fdg_oo: float            # Fast-DetectGPT, reference and scoring model both the observer
    fdg_po: float            # reference the performer, scoring the observer
    burstiness: float | None  # spread of per-sentence mean NLL under the observer
    sentences: int

    @property
    def ppl_obs(self) -> float:
        return math.exp(min(self.nll_obs, 50.0))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ppl_obs"] = self.ppl_obs
        return d


# --------------------------------------------------------------------------- arithmetic

def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Character spans of sentences. Crude on purpose: it only has to agree with itself."""
    spans, start = [], 0
    for m in _SENTENCE_END.finditer(text):
        end = m.end()
        if text[start:end].strip():
            spans.append((start, end))
        start = end
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


def burstiness_from(nll, starts: list[int], text: str) -> tuple[float | None, int]:
    """Standard deviation of the per-sentence mean NLL, or None with fewer than two sentences.

    `nll[i]` belongs to the token that starts at character `starts[i]`. A sentence needs
    three scored tokens to count: a one-word sentence has a mean that is mostly noise.
    """
    spans = sentence_spans(text)
    if len(spans) < 2:
        return None, len(spans)
    sums = [0.0] * len(spans)
    counts = [0] * len(spans)
    j = 0
    for value, pos in zip(nll, starts):
        while j < len(spans) - 1 and pos >= spans[j][1]:
            j += 1
        sums[j] += float(value)
        counts[j] += 1
    means = [s / c for s, c in zip(sums, counts) if c >= 3]
    if len(means) < 2:
        return None, len(spans)
    mu = sum(means) / len(means)
    return math.sqrt(sum((m - mu) ** 2 for m in means) / len(means)), len(spans)


def features_from_logits(obs_logits, perf_logits, ids, starts: list[int], text: str) -> Features:
    """The detectors' arithmetic, from two models' logits over the same token ids.

    obs_logits, perf_logits: (T, V) tensors, row t predicting token t + 1.
    ids: (T,) token ids. starts: character offset of each token, len T.
    Follows the official Binoculars and Fast-DetectGPT code; the one difference is that the
    cross-entropy here is averaged over the same T - 1 positions as the perplexity, where the
    reference code also counts the last position, which predicts past the end of the text.
    """
    import torch

    T = int(ids.shape[0])
    if T < 2:
        raise ValueError("a text needs at least two tokens to be scored")
    tgt = ids[1:].long().to(obs_logits.device)
    n = T - 1
    sum_nll_o = sum_nll_p = sum_xent = 0.0
    ll_o = mean_oo = var_oo = mean_po = var_po = 0.0
    per_token_nll = []
    for a in range(0, n, CHUNK):
        b = min(n, a + CHUNK)
        lo = torch.log_softmax(obs_logits[a:b].float(), dim=-1)
        lp = torch.log_softmax(perf_logits[a:b].float(), dim=-1)
        t = tgt[a:b].unsqueeze(1)
        nll_o = -lo.gather(1, t).squeeze(1)
        nll_p = -lp.gather(1, t).squeeze(1)
        po = lo.exp()
        pp = lp.exp()
        sum_nll_o += float(nll_o.sum())
        sum_nll_p += float(nll_p.sum())
        sum_xent += float(-(po * lp).sum(dim=-1).sum())
        # Fast-DetectGPT: scoring model the observer, reference either model.
        ll_o += float((-nll_o).sum())
        m_oo = (po * lo).sum(dim=-1)
        var_oo += float(((po * lo * lo).sum(dim=-1) - m_oo * m_oo).sum())
        mean_oo += float(m_oo.sum())
        m_po = (pp * lo).sum(dim=-1)
        var_po += float(((pp * lo * lo).sum(dim=-1) - m_po * m_po).sum())
        mean_po += float(m_po.sum())
        per_token_nll.extend(nll_o.tolist())
    nll_obs = sum_nll_o / n
    nll_perf = sum_nll_p / n
    xent = sum_xent / n
    burst, n_sent = burstiness_from(per_token_nll, starts[1:], text)
    return Features(
        tokens=T,
        nll_obs=nll_obs,
        nll_perf=nll_perf,
        xent=xent,
        binoculars=nll_perf / xent if xent > 0 else float("inf"),
        fdg_oo=(ll_o - mean_oo) / math.sqrt(max(var_oo, 1e-9)),
        fdg_po=(ll_o - mean_po) / math.sqrt(max(var_po, 1e-9)),
        burstiness=burst,
        sentences=n_sent,
    )


# --------------------------------------------------------------------------- models

def pick_device(device: str | None = None) -> str:
    import torch

    if device:
        return device
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class Detector:
    """Two models loaded once, scored one text at a time.

    One text at a time because padding a batch changes nothing about the scores and costs
    a NaN on Apple's GPU: scaled-dot-product attention with a padding mask came back NaN
    in bfloat16 on MPS when the benchmark corpus was generated, and the scores of a
    detector are worth nothing if one in a hundred is quietly not a number.
    """

    def __init__(self, pair: str = DEFAULT_PAIR, device: str | None = None,
                 max_tokens: int = MAX_TOKENS):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if pair not in PAIRS:
            raise KeyError(f"unknown pair {pair!r}; known: {sorted(PAIRS)}")
        self.pair = pair
        self.max_tokens = max_tokens
        self.device = pick_device(device)
        dtype = torch.float32 if self.device == "cpu" else torch.bfloat16
        obs_name, perf_name = PAIRS[pair]
        self.tok = AutoTokenizer.from_pretrained(obs_name)
        self.observer = AutoModelForCausalLM.from_pretrained(obs_name, dtype=dtype).to(self.device).eval()
        self.performer = AutoModelForCausalLM.from_pretrained(perf_name, dtype=dtype).to(self.device).eval()
        self._torch = torch

    def encode(self, text: str):
        enc = self.tok(text, add_special_tokens=False, return_offsets_mapping=True,
                       truncation=True, max_length=self.max_tokens)
        return enc["input_ids"], [s for s, _ in enc["offset_mapping"]]

    def features(self, text: str) -> Features:
        # Apple's GPU shares memory with everything else on the machine, and the benchmark run
        # of 21 October stopped at text 166 of 4,552 when other programs held 15 GB of it. A
        # text that does not fit now usually fits a few seconds later, after the cache is freed.
        import time

        for wait in (5, 20, 60, None):
            try:
                return self._features(text)
            except RuntimeError as e:
                if "out of memory" not in str(e) or wait is None:
                    raise
                if self.device == "mps":
                    self._torch.mps.empty_cache()
                time.sleep(wait)

    def _features(self, text: str) -> Features:
        torch = self._torch
        ids, starts = self.encode(text)
        if len(ids) < 2:
            raise ValueError("the text is too short to score")
        x = torch.tensor([ids], device=self.device)
        with torch.no_grad():
            obs = self.observer(input_ids=x).logits[0, :-1]
            perf = self.performer(input_ids=x).logits[0, :-1]
            if not (torch.isfinite(obs).all() and torch.isfinite(perf).all()):
                # Rare in bfloat16; recompute on the CPU in float32 rather than return nonsense.
                obs = self.observer.float().cpu()(input_ids=x.cpu()).logits[0, :-1]
                perf = self.performer.float().cpu()(input_ids=x.cpu()).logits[0, :-1]
                self.observer.to(self.device, dtype=torch.bfloat16)
                self.performer.to(self.device, dtype=torch.bfloat16)
        out = features_from_logits(obs, perf, torch.tensor(ids), starts, text)
        # Two 150 MB logit tensors per text; the allocator keeps them pooled unless asked,
        # and the pool is what ran out at text 395 of the 22 October run.
        del obs, perf
        if self.device == "mps":
            torch.mps.empty_cache()
        return out


# The browser downloads 4-bit ONNX files, and 4-bit weights move every logit a little. A
# calibration fitted on the bfloat16 models above would be applied to scores it never saw,
# so the browser gets its own calibration, measured on these exact files with onnxruntime.
ONNX_PAIRS: dict[str, tuple[str, str, str]] = {
    "qwen2.5-0.5b-q4f16": ("onnx-community/Qwen2.5-0.5B", "onnx-community/Qwen2.5-0.5B-Instruct",
                           "onnx/model_q4f16.onnx"),
}


class OnnxDetector:
    """The browser's detector, run in Python on the browser's files, for calibration."""

    def __init__(self, pair: str = "qwen2.5-0.5b-q4f16", max_tokens: int = MAX_TOKENS):
        import numpy as np
        import onnxruntime as ort
        import torch
        from huggingface_hub import hf_hub_download
        from transformers import AutoTokenizer

        obs_repo, perf_repo, fname = ONNX_PAIRS[pair]
        self.pair = pair
        self.max_tokens = max_tokens
        self.tok = AutoTokenizer.from_pretrained(PAIRS["qwen2.5-0.5b"][0])
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        self.sessions = [ort.InferenceSession(hf_hub_download(r, fname), opts,
                                              providers=["CPUExecutionProvider"]) for r in (obs_repo, perf_repo)]
        self.past = [i for i in self.sessions[0].get_inputs() if i.name.startswith("past_key_values")]
        self._np, self._torch = np, torch

    def _logits(self, sess, ids):
        np = self._np
        T = len(ids)
        feed = {"input_ids": np.array([ids], dtype=np.int64),
                "attention_mask": np.ones((1, T), dtype=np.int64),
                "position_ids": np.arange(T, dtype=np.int64)[None, :]}
        for i in self.past:
            heads, dim = i.shape[1], i.shape[3]
            feed[i.name] = np.zeros((1, heads, 0, dim), dtype=np.float32)
        return sess.run(["logits"], feed)[0][0, :-1]

    def features(self, text: str) -> Features:
        enc = self.tok(text, add_special_tokens=False, return_offsets_mapping=True,
                       truncation=True, max_length=self.max_tokens)
        ids, starts = enc["input_ids"], [s for s, _ in enc["offset_mapping"]]
        if len(ids) < 2:
            raise ValueError("the text is too short to score")
        torch = self._torch
        obs, perf = (torch.from_numpy(self._logits(s, ids)) for s in self.sessions)
        return features_from_logits(obs, perf, torch.tensor(ids), starts, text)


def make_detector(pair: str):
    return OnnxDetector(pair) if pair in ONNX_PAIRS else Detector(pair)


# --------------------------------------------------------------------------- language

# Twenty of the commonest short words of each language, minus the ones they share in
# writing ("la", "de", "no", "e"). Enough to decide among three languages on forty words,
# which is the shortest text the detectors are measured on.
_STOP = {
    "en": "the and of to is in that it was for with as on are this be by have not but from at which".split(),
    "it": "il di che per un una non sono del della con gli nel alla anche come più dei delle questo".split(),
    "es": "el que los las del por una con es para al su se como pero más sus este entre fue".split(),
}
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def guess_language(text: str) -> tuple[str | None, float]:
    """('en'|'it'|'es', share of the votes) or (None, 0.0) when nothing matched."""
    votes = {k: 0 for k in _STOP}
    sets = {k: set(v) for k, v in _STOP.items()}
    for w in _WORD.findall(text.lower()):
        for k, s in sets.items():
            if w in s:
                votes[k] += 1
    total = sum(votes.values())
    if not total:
        return None, 0.0
    best = max(votes, key=votes.get)
    return best, votes[best] / total


def word_count(text: str) -> int:
    return len(_WORD.findall(text))
