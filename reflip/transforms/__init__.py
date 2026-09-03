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

    _load_local()


LOCAL_ERRORS: dict[str, str] = {}  # file name -> the sentence explaining why it did not load
_LOADED_LOCAL = False


def local_dir():
    """Where a person's own transforms live: ~/.reflip/transforms, or REFLIP_HOME's."""
    import os
    from pathlib import Path

    return Path(os.environ.get("REFLIP_HOME", Path.home() / ".reflip")) / "transforms"


def _load_local() -> None:
    """Import every .py file in the local transforms directory, once.

    This is what keeps the list of transforms out of the binary. A person who wants a
    rewrite of their own, or a house style enforced before the model ever sees the text,
    drops a file in that directory with a `@register("name")` function in it and the name
    appears in `reflip transforms` and in the window's picker without rebuilding either.

    A file that fails to import is recorded and skipped rather than taking the tool down
    with it: the four transforms that ship here are the ones people rely on, and a typo in
    somebody's experiment must not stop them working.
    """
    global _LOADED_LOCAL
    if _LOADED_LOCAL:
        return
    _LOADED_LOCAL = True
    import importlib.util

    directory = local_dir()
    try:
        files = sorted(p for p in directory.glob("*.py") if not p.name.startswith("_"))
    except OSError:
        return
    for path in files:
        spec = importlib.util.spec_from_file_location(f"reflip_local_{path.stem}", path)
        if spec is None or spec.loader is None:
            LOCAL_ERRORS[path.name] = "That file could not be read as Python."
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:  # noqa: BLE001 - somebody else's file, any failure is theirs
            LOCAL_ERRORS[path.name] = f"{type(e).__name__}: {' '.join(str(e).split())[:160]}"
