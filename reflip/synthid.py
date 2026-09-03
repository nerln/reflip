"""Open SynthID-Text testbed.

Anthropic says Claude's text watermark is "a version of the SynthID-Text approach"
(https://www.anthropic.com/news/claude-text-watermark). Their key is private, so nobody
outside Anthropic can score Claude text. What we CAN do is run the published algorithm
(transformers' SynthIDTextWatermarkLogitsProcessor, Dathathri et al., Nature 2024) with a
key we own, on an open model, and measure exactly what each transformation does to the
detector. That is what this module provides.

Fix over the stock processor: the stock class draws its sampling table with a generator on
the *generation device*, so a text generated on MPS/CUDA cannot be scored on CPU with the
same seed (the tables differ). PortableSynthID draws the table on CPU and moves it.
"""
from __future__ import annotations

import difflib
import math
from dataclasses import asdict, dataclass

import torch
from transformers.generation.logits_process import SynthIDTextWatermarkLogitsProcessor

DEFAULT_KEYS = [654, 400, 836, 123, 340, 443, 597, 160, 57]  # transformers' doc example
DEFAULT_NGRAM_LEN = 5  # hash covers the 4 previous tokens + the candidate token


class PortableSynthID(SynthIDTextWatermarkLogitsProcessor):
    """SynthID-Text logits processor whose key is device-independent."""

    def __init__(
        self,
        ngram_len: int = DEFAULT_NGRAM_LEN,
        keys: list[int] | None = None,
        sampling_table_size: int = 2**16,
        sampling_table_seed: int = 0,
        context_history_size: int = 1024,
        device: str | torch.device = "cpu",
        skip_first_ngram_calls: bool = False,
    ):
        super().__init__(
            ngram_len=ngram_len,
            keys=list(keys or DEFAULT_KEYS),
            sampling_table_size=sampling_table_size,
            sampling_table_seed=sampling_table_seed,
            context_history_size=context_history_size,
            device=torch.device(device),
            skip_first_ngram_calls=skip_first_ngram_calls,
        )
        gen = torch.Generator(device="cpu").manual_seed(sampling_table_seed)
        self.sampling_table = torch.randint(0, 2, (sampling_table_size,), generator=gen).to(self.device)

    def reset(self) -> None:
        """Must be called before every generate() call when the processor is reused."""
        self.state = None


@dataclass
class Score:
    tokens: int
    scored: int  # positions with a non-repeated context (the ones the detector counts)
    mean_g: float
    z: float
    p: float  # one-sided p-value under the null (unwatermarked text)
    z_w: float = 0.0  # weighted-mean score (DeepMind detector_mean.py weights linspace(10,1,depth))

    def to_dict(self) -> dict:
        return asdict(self)


def z_to_p(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


class Scorer:
    """Mean-g-value detector (the paper's simplest scoring function).

    Under the null every g-value is Bernoulli(1/2), so the mean over n*depth values has
    standard deviation 0.5/sqrt(n*depth). z is the number of those standard deviations
    above 0.5. Human/unwatermarked text lands around z ~ N(0,1).
    """

    def __init__(
        self,
        tokenizer,
        ngram_len: int = DEFAULT_NGRAM_LEN,
        keys: list[int] | None = None,
        sampling_table_seed: int = 0,
    ):
        self.tok = tokenizer
        self.ngram_len = ngram_len
        self.proc = PortableSynthID(
            ngram_len=ngram_len, keys=keys, sampling_table_seed=sampling_table_seed, device="cpu"
        )

    def encode(self, text: str) -> list[int]:
        return self.tok(text, add_special_tokens=False)["input_ids"]

    def g_values(self, ids: list[int]) -> tuple[torch.Tensor, torch.Tensor]:
        t = torch.tensor([ids], dtype=torch.long)
        g = self.proc.compute_g_values(t)[0].float()  # (num_ngrams, depth)
        mask = self.proc.compute_context_repetition_mask(t)[0]  # (num_ngrams,) True = counted
        return g, mask

    def score_ids(self, ids: list[int]) -> Score:
        if len(ids) < self.ngram_len + 1:
            return Score(tokens=len(ids), scored=0, mean_g=0.5, z=0.0, p=0.5)
        g, mask = self.g_values(ids)
        n = int(mask.sum())
        if n == 0:
            return Score(tokens=len(ids), scored=0, mean_g=0.5, z=0.0, p=0.5)
        mean = float(g[mask].mean())
        depth = g.shape[1]
        z = (mean - 0.5) / (0.5 / math.sqrt(n * depth))
        # weighted mean: earlier tournament layers carry more signal, weights renormalised to sum to depth
        w = torch.linspace(10.0, 1.0, depth)
        w = w * depth / w.sum()
        per_pos = (g[mask] * w).sum(dim=1) / depth
        mean_w = float(per_pos.mean())
        sd_w = math.sqrt(0.25 * float((w * w).sum()) / (depth * depth * n))
        z_w = (mean_w - 0.5) / sd_w
        return Score(tokens=len(ids), scored=n, mean_g=round(mean, 5), z=round(z, 3), p=z_to_p(z), z_w=round(z_w, 3))

    def score(self, text: str) -> Score:
        return self.score_ids(self.encode(text))


def intact_fraction(orig_ids: list[int], new_ids: list[int], ngram_len: int = DEFAULT_NGRAM_LEN) -> float:
    """Fraction of positions in new_ids whose g-value the detector will recompute UNCHANGED.

    A position i keeps its original g-value iff tokens i-(ngram_len-1)..i are all original
    tokens, contiguous in the original sequence. Everything else is re-hashed to a fresh
    coin flip. So 0.0 means every g-value has been randomised: the watermark is gone in
    expectation, whatever its strength was.
    """
    if len(new_ids) < ngram_len:
        return 0.0
    sm = difflib.SequenceMatcher(a=orig_ids, b=new_ids, autojunk=False)
    # block id per new position (-1 = not part of any matching block)
    block_of = [-1] * len(new_ids)
    for k, (i, j, n) in enumerate(sm.get_matching_blocks()):
        for t in range(j, j + n):
            block_of[t] = k
    intact = 0
    total = len(new_ids) - ngram_len + 1
    for pos in range(ngram_len - 1, len(new_ids)):
        b = block_of[pos]
        if b >= 0 and all(block_of[q] == b for q in range(pos - ngram_len + 1, pos)):
            intact += 1
    return intact / total


def generate_watermarked(model, tokenizer, prompts: list[str], proc: PortableSynthID | None,
                         max_new_tokens: int = 400, temperature: float = 1.0, top_p: float = 1.0,
                         seed: int | None = None) -> list[list[int]]:
    """Generate completions (as token id lists, prompt stripped). proc=None -> unwatermarked."""
    from transformers import LogitsProcessorList

    if seed is not None:
        torch.manual_seed(seed)
    device = next(model.parameters()).device
    enc = tokenizer(prompts, return_tensors="pt", padding=True).to(device)
    kw = dict(do_sample=True, temperature=temperature, top_p=top_p, top_k=0,
              max_new_tokens=max_new_tokens, pad_token_id=tokenizer.pad_token_id)
    if proc is not None:
        proc.reset()
        kw["logits_processor"] = LogitsProcessorList([proc])
    out = model.generate(**enc, **kw)
    n_prompt = enc["input_ids"].shape[1]
    res = []
    for row in out[:, n_prompt:]:
        ids = row.tolist()
        # strip padding / eos
        eos = getattr(model.generation_config, "eos_token_id", None)
        eos = set(eos) if isinstance(eos, (list, tuple)) else {eos}
        stop = {tokenizer.pad_token_id, tokenizer.eos_token_id} | eos
        cut = next((k for k, i in enumerate(ids) if i in stop), len(ids))
        ids = [i for i in ids[:cut] if i not in stop]
        res.append(ids)
    return res
