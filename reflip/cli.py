"""Command-line entry point (`reflip`).

`reflip run` is the everyday face of the package: read a text, apply one transform, write
the text back byte-for-byte except for the edits, and account for the cost on stderr in a
single line (edits, share of words touched, LLM calls and tokens, and, when a tokenizer is
named, the share of ngram_len-token windows that contain an edit, which is the quantity
the SynthID detector actually cares about). Everything else is dispatch: `bench` and
`corpus` forward their arguments to those modules, `transforms` lists the registry.

Design decision: `reflip check` refuses to pretend. Anthropic's key is private, so no
program outside Anthropic can tell whether a text carries Claude's watermark. `check` only
scans for invisible characters, which are a different, trivially removable marker, and
then says so in one sentence. Failures exit non-zero with one line and no traceback:
a missing Ollama should read like a missing Ollama, not like a stack dump.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

from . import transforms
from .transforms import Options, Transform, TransformResult
from .words import word_edit_ratio

DEFAULT_TRANSFORM = "paraphrase"
KNOWN_TRANSFORMS = "{hybrid,infill,paraphrase,rules,unicode}"
NO_DETECTOR = ("No public detector exists for Claude's key, so a file cannot be checked for the "
               "statistical watermark; use `reflip bench` to measure a transform against the "
               "open SynthID implementation.")


class CliError(Exception):
    """A user-facing failure: printed as one line, no traceback."""

    def __init__(self, msg: str, code: int = 1):
        super().__init__(msg)
        self.code = code


# --- helpers -------------------------------------------------------------------------

def read_input(path: str) -> str:
    """Read a file or stdin ("-") without newline translation."""
    if path == "-":
        return sys.stdin.read()
    p = Path(path)
    if not p.is_file():
        raise CliError(f"no such file: {path}", code=2)
    with p.open(encoding="utf-8", newline="") as f:
        return f.read()


def write_output(text: str, out: str | None) -> None:
    if out:
        with Path(out).open("w", encoding="utf-8", newline="") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
        sys.stdout.flush()


def get_transform(name: str) -> Transform:
    try:
        return transforms.get(name)
    except KeyError as e:
        raise CliError(str(e.args[0]), code=2) from e
    except ImportError as e:
        raise CliError(f"transform {name!r} is not importable: {e}", code=2) from e


def one_line(exc: BaseException, limit: int = 300) -> str:
    msg = " ".join(f"{type(exc).__name__}: {exc}".split())
    return msg if len(msg) <= limit else msg[:limit - 3] + "..."


def run_transform(fn: Transform, text: str, opts: Options) -> TransformResult:
    """Call the transform, turning backend failures into one-line errors."""
    try:
        import requests
    except ImportError:  # pragma: no cover - requests is a hard dependency
        return fn(text, opts)
    try:
        return fn(text, opts)
    except requests.exceptions.ConnectionError as e:
        raise CliError(f"cannot reach the LLM backend at {opts.base_url} "
                       f"(is Ollama running?): {one_line(e)}") from e
    except requests.exceptions.Timeout as e:
        raise CliError(f"LLM backend at {opts.base_url} timed out after {opts.timeout:g}s: "
                       f"{one_line(e)}") from e


def coverage(orig: str, new: str, tokenizer_name: str, ngram_len: int) -> tuple[float, str]:
    """Share of ngram_len-token windows of `new` that contain an edit (1 - intact fraction)."""
    from . import bench
    from .synthid import intact_fraction

    tok = bench.load_tokenizer(tokenizer_name)
    a = tok(orig, add_special_tokens=False)["input_ids"]
    b = tok(new, add_special_tokens=False)["input_ids"]
    return 1.0 - intact_fraction(a, b, ngram_len), tokenizer_name


def report_line(name: str, orig: str, res: TransformResult, seconds: float,
                cov: tuple[float, str] | None, ngram_len: int) -> str:
    ratio = word_edit_ratio(orig, res.text)
    line = (f"{name}: {res.edits} edits, {ratio:.1%} of words changed, {res.llm_calls} LLM calls, "
            f"{res.prompt_tokens} prompt + {res.completion_tokens} completion tokens, {seconds:.1f}s")
    if cov is not None:
        share, tok_name = cov
        line += f"; coverage: {share:.1%} of {ngram_len}-token windows contain an edit ({tok_name})"
    return line


def format_scan(result) -> list[str]:
    """Render whatever `unicode.scan` returns (dict, list, dataclass or scalar) as lines."""
    if is_dataclass(result) and not isinstance(result, type):
        result = asdict(result)
    if isinstance(result, dict):
        items = list(result.items())
        if not items:
            return ["no invisible characters found"]
        return [f"  {k}: {v}" for k, v in items]
    if isinstance(result, (list, tuple, set)):
        if not result:
            return ["no invisible characters found"]
        return [f"  {x}" for x in result]
    return [f"  {result}"]


# --- subcommands ---------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    fn = get_transform(args.transform)
    text = read_input(args.file)
    tok = None
    if args.tokenizer:
        from . import bench

        tok = bench.load_tokenizer(args.tokenizer)
    opts = Options(base_url=args.base_url, api_key=args.api_key, model=args.model,
                   temperature=args.temperature, seed=args.seed, stride=args.stride,
                   span=args.span, ngram_len=args.ngram_len, tokenizer=tok, language=args.lang,
                   min_coverage=args.min_coverage if tok is not None else 0.0, max_passes=args.max_passes)
    t0 = time.perf_counter()
    res = run_transform(fn, text, opts)
    seconds = time.perf_counter() - t0
    write_output(res.text, args.output)
    cov = coverage(text, res.text, args.tokenizer, args.ngram_len) if args.tokenizer else None
    print(report_line(args.transform, text, res, seconds, cov, args.ngram_len), file=sys.stderr)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    text = read_input(args.file)
    try:
        from .transforms import unicode as uni
    except ImportError as e:
        print(f"invisible-character scan unavailable: {one_line(e)}")
    else:
        print(f"invisible characters in {args.file}:")
        for line in format_scan(uni.scan(text)):
            print(line)
    print(NO_DETECTOR)
    return 0


def cmd_transforms(args: argparse.Namespace) -> int:
    try:
        names = transforms.names()
    except ImportError as e:
        raise CliError(f"transform modules not importable: {e}") from e
    for name in names:
        print(name)
    return 0


def forward(command: str, rest: list[str]) -> int:
    """`bench` and `corpus` own their argv: hand it over untouched (so `--help` reaches them)."""
    if command == "bench":
        from . import bench

        return int(bench.main(rest) or 0)
    from . import corpus

    return int(corpus.main(rest) or 0)


FORWARDED = ("bench", "corpus")


# --- parser ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="reflip", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="command", metavar="COMMAND")

    run = sub.add_parser("run", help="apply a transform to a file or stdin")
    run.add_argument("file", nargs="?", default="-", help="input file, or - for stdin (default)")
    run.add_argument("--transform", "-t", default=DEFAULT_TRANSFORM, metavar=KNOWN_TRANSFORMS)
    run.add_argument("--stride", type=int, default=Options.stride, help="max run of unedited words")
    run.add_argument("--span", type=int, default=Options.span, help="words replaced per slot")
    run.add_argument("--model", default=Options.model)
    run.add_argument("--base-url", default=Options.base_url)
    run.add_argument("--api-key", default=Options.api_key)
    run.add_argument("--temperature", type=float, default=Options.temperature)
    run.add_argument("--seed", type=int, default=Options.seed)
    run.add_argument("--tokenizer", default=None, help="HF tokenizer name: report window coverage")
    run.add_argument("--tokenaware", action="store_true", help="(implied by --tokenizer) choose slots in token space")
    run.add_argument("--ngram-len", type=int, default=Options.ngram_len)
    run.add_argument("--min-coverage", type=float, default=0.9,
                     help="paraphrase: with --tokenizer, re-ask while fewer windows than this carry an edit")
    run.add_argument("--max-passes", type=int, default=Options.max_passes)
    run.add_argument("--lang", default=Options.language, help="language for the rule pass")
    run.add_argument("-o", "--output", default=None, help="write here instead of stdout")
    run.set_defaults(func=cmd_run)

    check = sub.add_parser("check", help="scan a file for invisible characters (no detector exists)")
    check.add_argument("file")
    check.set_defaults(func=cmd_check)

    lst = sub.add_parser("transforms", help="list registered transforms")
    lst.set_defaults(func=cmd_transforms)

    # listed for --help only: main() forwards their argv before argparse touches it
    sub.add_parser("bench", help="run the verification bench (see `reflip bench --help`)", add_help=False)
    sub.add_parser("corpus", help="generate the benchmark corpus (see `reflip corpus --help`)", add_help=False)
    return ap


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv and argv[0] in FORWARDED:
            return forward(argv[0], argv[1:])
        parser = build_parser()
        args = parser.parse_args(argv)
        if not getattr(args, "func", None):
            parser.print_help(sys.stderr)
            return 2
        return int(args.func(args) or 0)
    except CliError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.code
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except BrokenPipeError:
        return 0
    except Exception as e:  # noqa: BLE001 - one line, no traceback
        print(f"error: {one_line(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
