"""Meaning-preservation metrics that do not need an LLM judge.

Removing a watermark is only useful if the text still says the same thing, so every
transform in the bench is scored on meaning as well as on the detector. An LLM judge would
cost tokens and would itself be a noisy, watermarked opinion; instead we use two cheap and
reproducible instruments:

- cosine similarity between sentence embeddings of the original and the edited text
  (intfloat/multilingual-e5-small: 118M parameters, runs on CPU, handles en + it);
- perplexity under an open causal LM (optional, `--ppl`): if edits make the text less
  fluent, the perplexity goes up.

Both models are loaded lazily, inside methods, so importing this module costs nothing and
the base package keeps `requests` as its only hard dependency. `word_edit_ratio` is
re-exported here because it is the third meaning metric the bench reports.
"""
from __future__ import annotations

import math

from .words import word_edit_ratio

__all__ = ["Embedder", "Perplexity", "word_edit_ratio", "dot"]

E5_MODEL = "intfloat/multilingual-e5-small"
PPL_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"


def dot(a: list[float], b: list[float]) -> float:
    """Dot product of two equal-length vectors (cosine, when both are L2-normalised)."""
    if len(a) != len(b):
        raise ValueError(f"vectors differ in length: {len(a)} vs {len(b)}")
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))


def _mean_pool(hidden, attention_mask):
    """Average the token vectors of each sequence, ignoring padding (torch tensors)."""
    mask = attention_mask.unsqueeze(-1).to(hidden.dtype)
    return (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)


def _pick_device(device: str | None):
    import torch

    if device:
        return torch.device(device)
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


class Embedder:
    """Sentence embeddings with multilingual-e5-small (mean pooling, L2-normalised).

    e5 expects a task prefix; both sides of a similarity comparison get "query: ", as the
    model card prescribes for symmetric tasks.
    """

    def __init__(self, model_name: str = E5_MODEL, device: str | None = None,
                 batch_size: int = 16, max_length: int = 512, prefix: str = "query: "):
        self.model_name = model_name
        self.device_name = device
        self.batch_size = batch_size
        self.max_length = max_length
        self.prefix = prefix
        self._tok = None
        self._model = None

    def _load(self):
        if self._model is None:
            import torch
            from transformers import AutoModel, AutoTokenizer

            self._device = _pick_device(self.device_name)
            self._tok = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModel.from_pretrained(self.model_name).to(self._device).eval()
            self._torch = torch
        return self._tok, self._model, self._torch

    def embed(self, texts: list[str]) -> list[list[float]]:
        tok, model, torch = self._load()
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = [self.prefix + t for t in texts[i:i + self.batch_size]]
            enc = tok(batch, padding=True, truncation=True, max_length=self.max_length,
                      return_tensors="pt").to(self._device)
            with torch.no_grad():
                hidden = model(**enc).last_hidden_state
            pooled = _mean_pool(hidden, enc["attention_mask"])
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            out.extend(pooled.cpu().tolist())
        return out

    def cosine(self, a: str, b: str) -> float:
        if a == b:
            return 1.0
        va, vb = self.embed([a, b])
        return dot(va, vb)


class Perplexity:
    """Per-token negative log-likelihood under an open causal LM (fluency proxy).

    The first token is never predicted (no BOS is added), so the value is the mean NLL of
    tokens 2..n given their prefix. Texts longer than `max_length` tokens are truncated.
    """

    def __init__(self, model_name: str = PPL_MODEL, device: str | None = None,
                 max_length: int = 2048):
        self.model_name = model_name
        self.device_name = device
        self.max_length = max_length
        self._tok = None
        self._model = None

    def _load(self):
        if self._model is None:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            self._device = _pick_device(self.device_name)
            dtype = torch.float32 if self._device.type == "cpu" else torch.bfloat16
            self._tok = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForCausalLM.from_pretrained(self.model_name, dtype=dtype)
            self._model = self._model.to(self._device).eval()
            self._torch = torch
        return self._tok, self._model, self._torch

    def nll_per_token(self, text: str) -> float:
        tok, model, torch = self._load()
        ids = tok(text, return_tensors="pt", truncation=True,
                  max_length=self.max_length)["input_ids"].to(self._device)
        if ids.shape[1] < 2:
            return float("nan")
        with torch.no_grad():
            loss = model(input_ids=ids, labels=ids).loss
        return float(loss)

    def ppl(self, text: str) -> float:
        return math.exp(self.nll_per_token(text))
