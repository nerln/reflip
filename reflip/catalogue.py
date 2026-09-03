"""Which model to rewrite with, and how to find out rather than be told.

Two things live here. A short list of models worth trying, each with a plain sentence
about what it is good and bad at, and a search over Hugging Face for anything else in a
format the local server can run. Neither of them is a recommendation you have to take on
faith: `reflip models --measure NAME` runs that model over watermarked texts from the
benchmark corpus and reports what the detector said, so the list can be checked and
argued with.

The one hard rule in here is the `watermarks` field. A rewriter that marks its own output
turns the whole exercise into a swap of one watermark for another, so any model that does
is refused rather than ranked.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field

HF_API = "https://huggingface.co/api/models"
HF_TIMEOUT = 15.0


@dataclass
class Model:
    """One candidate rewriter, described the way a person would ask about it."""

    ref: str                      # what to pass to `reflip pull`
    params: str                   # "4B", "8B", a mixture of experts
    size_gb: float                # the download, at the quantisation named in ref
    good_at: str                  # one sentence
    watch_out: str                # one sentence, always present: nothing here is perfect
    languages: str
    measured: str | None = None   # what a measurement on this machine said, or None
    watermarks: bool = False      # true means it is disqualified, not ranked
    source: str = "ollama"        # "ollama" library, or "hf" for a Hugging Face repository
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# Ordered by how well they fit the job: a rewriter needs to be fluent and fast, and
# needs no reasoning at all. A thinking model spends its tokens deciding how to
# paraphrase, which is why the reasoning variants are further down than their size
# suggests. "measured" is filled in only where a number was actually produced on this
# machine and can be reproduced with `reflip models --measure`.
CATALOGUE: list[Model] = [
    Model(
        ref="qwen3:4b-instruct-2507-q4_K_M", params="4B", size_gb=2.5,
        good_at="Fluent English at a speed that keeps a rewrite under twenty seconds, on a "
                "laptop with 16 GB of memory. This is the model every number in the README "
                "was measured with.",
        watch_out="Its Italian is noticeably weaker than its English, and it slips on "
                  "grammar when asked to fill single words rather than rewrite a sentence.",
        languages="English well, other European languages adequately",
        measured="24 watermarked texts: detector z from 17.6 to 0.28, 74% of words changed, "
                 "5,800 tokens per 1,000 words, 17 seconds per text.",
        tags=["default", "fast"],
    ),
    Model(
        ref="qwen3:4b-instruct-2507-q8_0", params="4B", size_gb=4.3,
        good_at="The same model at a higher precision. Worth trying if the q4 version "
                "produces sentences that read slightly off.",
        watch_out="Nearly twice the download and noticeably slower on a machine that is "
                  "already short of memory.",
        languages="English well, other European languages adequately",
        tags=["quality"],
    ),
    Model(
        ref="gemma3:4b", params="4B", size_gb=3.3,
        good_at="Stronger on languages other than English than the 4B Qwen, which matters "
                "because the two Italian texts in the benchmark came out worst of all.",
        watch_out="Gemma is Google's, and Google watermarks the Gemini service. The open "
                  "weights do not carry it: SynthID is applied while sampling, and a local "
                  "server does not apply it unless you configure it to. Running the same "
                  "model through Google's API would mark the output.",
        languages="Strong multilingual",
        tags=["multilingual"],
    ),
    Model(
        ref="llama3.2:3b", params="3B", size_gb=2.0,
        good_at="The smallest download here that still rewrites whole paragraphs sensibly. "
                "A reasonable choice on a machine with 8 GB.",
        watch_out="Repeats phrasing from the original more than the Qwen models do, which "
                  "shows up directly as lower coverage.",
        languages="English, some European",
        tags=["small"],
    ),
    Model(
        ref="mistral-small:24b", params="24B", size_gb=14.0,
        good_at="The best prose of anything on this list, and good Italian and French.",
        watch_out="Fourteen gigabytes. On a 16 GB laptop it will page, and reflip will drop "
                  "to one request at a time. Sensible on 32 GB or more.",
        languages="Strong European languages",
        tags=["quality", "large"],
    ),
    Model(
        ref="qwen3:8b", params="8B", size_gb=5.2,
        good_at="Better sentences than the 4B when it finishes.",
        watch_out="It is a reasoning model: it thinks before it answers, and the thinking is "
                  "wasted on a paraphrase.",
        languages="English well, other European languages adequately",
        measured="Unusable on this laptop for this job: 464 seconds for one text, against "
                 "17 for the 4B instruct model.",
        tags=["slow"],
    ),
    Model(
        ref="hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M", params="7B", size_gb=4.7,
        good_at="A middle size, pulled straight from Hugging Face rather than the Ollama "
                "library. Use it as the example of how to run anything that is published "
                "as a GGUF file.",
        watch_out="Not measured here. Any model you have not measured is a guess, and "
                  "`reflip models --measure` exists to stop it being one.",
        languages="English well, other European languages adequately",
        source="hf",
        tags=["hugging-face"],
    ),
]

# Never use these to rewrite: they mark their own output, so the result carries a
# watermark again, this time somebody else's.
REFUSED = {
    "claude": "Claude models launched since 2 August 2026 watermark their own text.",
    "gemini": "The Gemini app and API watermark their own text.",
    "anthropic": "Claude models launched since 2 August 2026 watermark their own text.",
}


def refusal(ref: str) -> str | None:
    """The sentence explaining why this model must not be the rewriter, if it must not."""
    low = ref.lower()
    for needle, why in REFUSED.items():
        if needle in low:
            return why
    return None


def recommended(installed: set[str] | None = None) -> list[dict]:
    """The catalogue, with each entry marked as downloaded or not."""
    installed = installed or set()
    out = []
    for m in CATALOGUE:
        d = m.to_dict()
        d["installed"] = m.ref in installed or m.ref.split(":")[0] in {i.split(":")[0] for i in installed}
        out.append(d)
    return out


def search(query: str, limit: int = 12) -> tuple[list[dict], str | None]:
    """Hugging Face repositories in GGUF form, most downloaded first.

    Returns (results, note). The note is a sentence when something is worth saying about
    the search rather than about a result, such as the network being unreachable.
    """
    params = urllib.parse.urlencode({
        "search": query, "filter": "gguf", "sort": "downloads",
        "direction": "-1", "limit": str(max(1, min(limit, 50))),
    })
    try:
        with urllib.request.urlopen(f"{HF_API}?{params}", timeout=HF_TIMEOUT) as r:
            found = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        return [], f"Hugging Face could not be reached: {' '.join(str(e).split())[:120]}"
    results = []
    for m in found:
        repo = m.get("id", "")
        results.append({
            "ref": f"hf.co/{repo}:Q4_K_M",
            "repo": repo,
            "downloads": m.get("downloads", 0),
            "likes": m.get("likes", 0),
            "gated": bool(m.get("gated")),
            "page": f"https://huggingface.co/{repo}",
            "refused": refusal(repo),
        })
    note = None
    if results:
        note = ("These are search results, not recommendations. Q4_K_M is assumed as the "
                "quantisation; check the repository for which files it actually has, and "
                "measure the model before trusting it.")
    return results, note


def quantisations(repo: str) -> tuple[list[str], str | None]:
    """The GGUF files a Hugging Face repository actually publishes."""
    try:
        with urllib.request.urlopen(f"{HF_API}/{repo}", timeout=HF_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        return [], f"That repository could not be read: {' '.join(str(e).split())[:120]}"
    files = [f.get("rfilename", "") for f in data.get("siblings", [])]
    tags = sorted({f.rsplit("-", 1)[-1].removesuffix(".gguf") for f in files if f.endswith(".gguf")})
    if not tags:
        return [], "That repository has no GGUF files, so the local server cannot run it."
    return tags, None
