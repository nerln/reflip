"""The machine-facing half of the command line.

Three commands whose output is JSON on one line, for the window in `macapp/` and for
any program or agent that wants to put a text through reflip without reading prose:
`reflip server` looks after the local model server, `reflip pull` downloads a model,
`reflip rewrite` does the work and reports what it cost.

Two rules hold this together. Every sentence a person will read is produced here and
travels as a string, so the window never writes its own explanation of why something
did not happen. And every JSON object carries `"v": 1`, so a reader that meets a
version it does not know can say so instead of guessing.

Progress goes to stderr as JSON Lines while the work runs, and the single result
object goes to stdout at the end. Keeping them on separate streams is what lets a
caller pipe the rewritten text somewhere without filtering progress out of it.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time

from . import server as srv
from .mac import snapshot
from .transforms import Options, TransformResult

V = 1
DEFAULT_COVERAGE_TOKENIZER = "Qwen/Qwen2.5-1.5B-Instruct"


def default_host() -> str:
    """Where the model server is, unless a flag says otherwise.

    The window passes it in the environment rather than as a flag, because an unknown
    flag is exit code 2 and an unread variable is harmless: the two halves can be
    upgraded in either order without a version handshake.
    """
    import os

    return os.environ.get("REFLIP_HOST") or os.environ.get("REFLIP_BASE_URL") or srv.DEFAULT_URL


def chat_endpoint(host: str, given: str | None, fallback: str) -> str:
    """The OpenAI-compatible URL to talk to: what was asked for, or the host's own /v1."""
    if given and given != fallback:
        return given
    return host.rstrip("/") + "/v1"


def emit(obj: dict, stream=None) -> None:
    """One JSON object, one line, flushed. A reader should never wait for a buffer."""
    stream = stream or sys.stdout
    stream.write(json.dumps(obj, ensure_ascii=False) + "\n")
    stream.flush()


class Reporter:
    """Writes progress lines to stderr, from whichever thread is reporting."""

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.lock = threading.Lock()

    def __call__(self, phase: str, done: int, total: int, message: str) -> None:
        if not self.enabled:
            return
        with self.lock:
            emit({"event": "progress", "phase": phase, "done": done, "total": total,
                  "message": message}, sys.stderr)

    def error(self, message: str) -> None:
        if self.enabled:
            with self.lock:
                emit({"event": "error", "message": message}, sys.stderr)


# --------------------------------------------------------------------------- server

def _picture(url: str, model: str) -> dict:
    """The whole state of play in one object: the server, this Mac, and whether we can work."""
    s = srv.status(url, model=model)
    m = snapshot()
    ready = s.running and s.has(model)
    reason = s.reason
    if ready and m.reasons:
        # Work is still possible; the sentences say it will be slower than usual.
        reason = None
    return {"v": V, "ready": ready, "reason": reason, "model": model,
            "server": s.to_dict(), "machine": m.to_dict()}


def cmd_server(args: argparse.Namespace) -> int:
    action = args.action or "status"
    message = None
    if action == "start":
        _, message = srv.start(args.base_url_host)
    elif action == "stop":
        _, message = srv.stop(args.base_url_host)
    elif action == "warm":
        _, message = srv.warm(args.model, args.base_url_host)
    picture = _picture(args.base_url_host, args.model)
    # Always a sentence, even for a plain status. The window shows what this says and
    # writes nothing of its own, so a missing message left it saying that reflip had
    # exited successfully and told it nothing.
    picture["message"] = message or picture["reason"] or (
        f"The model server is up at {picture['server']['url']}."
        if picture["server"]["running"] else "The model server is not running.")
    if args.json:
        emit(picture)
    else:
        s = picture["server"]
        print(message or (s["reason"] or f"The model server is up at {s['url']}."))
        if s["running"]:
            print(f"  version {s['version']}, {len(s['models'])} models downloaded"
                  + (f", loaded: {', '.join(s['loaded'])}" if s["loaded"] else ""))
        for line in picture["machine"]["reasons"]:
            print(f"  {line}")
    return 0 if picture["ready"] or action == "stop" else 1


def cmd_models(args: argparse.Namespace) -> int:
    s = srv.status(args.base_url_host)
    if args.json:
        emit({"v": V, "models": s.models, "default": srv.DEFAULT_MODEL, "reason": s.reason})
    elif not s.running:
        print(s.reason)
    else:
        for m in s.models:
            print(f"{m['name']}\t{m['size'] / 2**30:.1f} GB")
    return 0 if s.running else 1


def cmd_pull(args: argparse.Namespace) -> int:
    def on_progress(status: str, completed, total) -> None:
        if args.json:
            emit({"event": "pull", "status": status, "completed": completed, "total": total})
        elif total:
            pct = 100.0 * (completed or 0) / total
            print(f"\r{status}: {pct:5.1f}%", end="", file=sys.stderr, flush=True)

    ok, message = srv.pull(args.model, args.base_url_host, on_progress=on_progress)
    if args.json:
        emit({"event": "done", "ok": ok, "message": message})
    else:
        print(("\n" if not args.json else "") + message, file=sys.stderr)
    return 0 if ok else 1


# --------------------------------------------------------------------------- rewrite

def _tokenizer(name: str | None, explicit: bool):
    """The tokenizer used to count detector windows, or (None, sentence) saying why not.

    Never downloads unless the caller named one: a rewrite that silently pulls a model
    off the internet the first time it runs is not a local tool.
    """
    if name is None:
        return None, "Coverage was not measured because no tokenizer was named."
    try:
        from transformers import AutoTokenizer
    except ImportError:
        return None, ("Coverage was not measured because transformers is not installed "
                      "(pip install \"reflip[bench]\").")
    try:
        return AutoTokenizer.from_pretrained(name, local_files_only=not explicit), None
    except Exception as e:  # noqa: BLE001 - any loading failure is the same story here
        if explicit:
            return None, f"That tokenizer would not load: {' '.join(str(e).split())[:160]}"
        return None, (f"Coverage was not measured because {name} is not in the local cache. "
                      "Name it with --tokenizer to fetch it once.")


def _coverage(tok, orig: str, new: str, ngram_len: int) -> float | None:
    from .synthid import intact_fraction

    a = tok(orig, add_special_tokens=False)["input_ids"]
    b = tok(new, add_special_tokens=False)["input_ids"]
    return round(1.0 - intact_fraction(a, b, ngram_len), 4)


def _result_object(name: str, model: str, orig: str, res: TransformResult, seconds: float,
                   cov: float | None, cov_note: str | None, workers: int) -> dict:
    from .words import word_edit_ratio, words

    return {"v": V, "transform": name, "model": model, "text": res.text,
            "words": len(words(orig)), "edits": res.edits,
            "edit_ratio": round(word_edit_ratio(orig, res.text), 4),
            "coverage": cov, "coverage_note": cov_note, "workers": workers,
            "llm_calls": res.llm_calls, "prompt_tokens": res.prompt_tokens,
            "completion_tokens": res.completion_tokens, "seconds": round(seconds, 2),
            "notes": {k: v for k, v in res.notes.items() if not isinstance(v, (bytes, bytearray))}}


def cmd_rewrite(args: argparse.Namespace) -> int:
    from .cli import CliError, get_transform, read_input, run_transform

    reporter = Reporter(args.progress)
    text = read_input(args.file)
    needs_model = args.transform in ("paraphrase", "infill", "hybrid")

    if needs_model:
        picture = _picture(args.base_url_host, args.model)
        if not picture["ready"]:
            reporter.error(picture["reason"] or "The model server is not ready.")
            if args.json:
                emit({"v": V, "ok": False, "reason": picture["reason"], "server": picture["server"]})
            else:
                print(f"error: {picture['reason']}", file=sys.stderr)
            return 1

    workers = args.workers if args.workers else snapshot().workers
    explicit_tok = args.tokenizer is not None
    tok_name = args.tokenizer or (None if args.no_coverage else DEFAULT_COVERAGE_TOKENIZER)
    tok, cov_note = _tokenizer(tok_name, explicit_tok)

    base_url = chat_endpoint(args.base_url_host, args.base_url, Options.base_url)
    opts = Options(base_url=base_url, api_key=args.api_key, model=args.model,
                   temperature=args.temperature, seed=args.seed, stride=args.stride,
                   span=args.span, ngram_len=args.ngram_len, tokenizer=tok,
                   language=args.lang, workers=workers, on_progress=reporter,
                   min_coverage=args.min_coverage if tok is not None else 0.0,
                   max_passes=args.max_passes)

    fn = get_transform(args.transform)
    reporter("Starting", 0, 1, f"Rewriting with {args.model}" if needs_model else "Applying rules")
    t0 = time.perf_counter()
    try:
        res = run_transform(fn, text, opts)
    except CliError as e:
        reporter.error(str(e))
        if args.json:
            emit({"v": V, "ok": False, "reason": str(e)})
        else:
            print(f"error: {e}", file=sys.stderr)
        return e.code
    seconds = time.perf_counter() - t0

    cov = _coverage(tok, text, res.text, args.ngram_len) if tok is not None else None
    obj = _result_object(args.transform, args.model, text, res, seconds, cov, cov_note, workers)
    reporter("Done", 1, 1, "Finished")
    if args.json:
        emit(obj)
    else:
        if args.output:
            from .cli import write_output

            write_output(res.text, args.output)
        else:
            sys.stdout.write(res.text)
            sys.stdout.flush()
        line = (f"{args.transform}: {obj['edits']} edits, {obj['edit_ratio']:.1%} of words changed, "
                f"{obj['llm_calls']} calls, {obj['prompt_tokens']}+{obj['completion_tokens']} tokens, "
                f"{obj['seconds']:.1f}s, {workers} at a time")
        if cov is not None:
            line += f"; coverage {cov:.1%} of {args.ngram_len}-token windows"
        print(line, file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- parser

def add_parsers(sub, options) -> None:
    """Mount the machine-facing commands on the main parser."""
    host = default_host()
    common = dict(base_url_host=host)

    def with_host(p):
        p.add_argument("--host", dest="base_url_host", default=host,
                       help="where the model server listens (or REFLIP_HOST)")
        p.add_argument("--json", action="store_true", help="one line of JSON, for programs")
        return p

    s = with_host(sub.add_parser("server", help="start, stop or look at the local model server"))
    s.add_argument("action", nargs="?", choices=["status", "start", "stop", "warm"], default="status")
    s.add_argument("--model", default=srv.DEFAULT_MODEL)
    s.set_defaults(func=cmd_server, **common)

    m = with_host(sub.add_parser("models", help="what the server has downloaded"))
    m.set_defaults(func=cmd_models, **common)

    p = with_host(sub.add_parser("pull", help="download a model into the server"))
    p.add_argument("model", nargs="?", default=srv.DEFAULT_MODEL)
    p.set_defaults(func=cmd_pull, **common)

    r = with_host(sub.add_parser("rewrite", help="rewrite a text and report what it cost"))
    r.add_argument("file", nargs="?", default="-", help="input file, or - for stdin (default)")
    # No choices= here: the registry is the list, and a name it does not know comes back
    # as a one-line error naming the ones it does, which beats argparse's wall of text.
    r.add_argument("--transform", "-t", default="paraphrase",
                   metavar="{paraphrase,infill,hybrid,rules,unicode}")
    r.add_argument("--model", default=srv.DEFAULT_MODEL)
    r.add_argument("--base-url", default=options.base_url, help="OpenAI-compatible endpoint")
    r.add_argument("--api-key", default=options.api_key)
    r.add_argument("--stride", type=int, default=options.stride)
    r.add_argument("--span", type=int, default=options.span)
    r.add_argument("--temperature", type=float, default=options.temperature)
    r.add_argument("--seed", type=int, default=options.seed)
    r.add_argument("--lang", default=options.language)
    r.add_argument("--ngram-len", type=int, default=options.ngram_len)
    r.add_argument("--tokenizer", default=None,
                   help="tokenizer for the coverage check (fetched once if not cached)")
    r.add_argument("--no-coverage", action="store_true", help="skip the coverage check")
    r.add_argument("--min-coverage", type=float, default=0.9)
    r.add_argument("--max-passes", type=int, default=options.max_passes)
    r.add_argument("--workers", type=int, default=0, help="requests in flight (0: ask the machine)")
    r.add_argument("--progress", action="store_true", help="JSON Lines progress on stderr")
    r.add_argument("-o", "--output", default=None)
    r.set_defaults(func=cmd_rewrite, **common)
