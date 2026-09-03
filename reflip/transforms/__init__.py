"""Transform registry. Every transform is `fn(text: str, opts: Options) -> TransformResult`."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Options:
    # LLM backend (OpenAI-compatible chat completions; Ollama serves one at /v1)
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    model: str = "qwen3:4b-instruct-2507-q4_K_M"
    temperature: float = 0.7
    seed: int | None = 0
    timeout: float = 600.0
    # edit geometry
    stride: int = 3          # max run of unedited WORDS (infill)
    span: int = 1            # words replaced per slot (infill)
    ngram_len: int = 5       # SynthID context length assumed for token-aware slotting
    tokenizer: object = None  # optional fast tokenizer for token-aware slotting and coverage checks
    min_coverage: float = 0.0  # paraphrase: re-ask while fewer than this share of ngram windows carry an edit
    max_passes: int = 3        # paraphrase: attempts per block when min_coverage is set
    # How many requests to keep in flight. The pieces of a text are independent of each
    # other, and a model server holds several at once, so this is the difference between
    # a minute and twenty seconds. reflip.mac.snapshot() picks the number from what the
    # machine has left; one is always safe.
    workers: int = 1
    # Called from worker threads as (phase, done, total, message). Whoever passes one is
    # responsible for its thread safety; the command line's writes to stderr under a lock.
    on_progress: object = None
    # rules
    rules: tuple[str, ...] = ()  # empty = all
    language: str = "en"


@dataclass
class TransformResult:
    text: str
    edits: int = 0
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    notes: dict = field(default_factory=dict)


Transform = Callable[[str, Options], TransformResult]

_REGISTRY: dict[str, Transform] = {}


def register(name: str):
    def deco(fn: Transform) -> Transform:
        _REGISTRY[name] = fn
        return fn
    return deco


def get(name: str) -> Transform:
    _load_all()
    if name not in _REGISTRY:
        raise KeyError(f"unknown transform {name!r}; known: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def names() -> list[str]:
    _load_all()
    return sorted(_REGISTRY)


def _load_all() -> None:
    # import side-effect registration
    from . import unicode as _u  # noqa: F401
    from . import rules as _r  # noqa: F401
    from . import llm as _l  # noqa: F401
