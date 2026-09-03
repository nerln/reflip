"""Harness and CLI tests on a fake corpus, without any model."""
import json
import re

import pytest

from reflip import bench, cli
from reflip.transforms import Options, TransformResult, register


class FakeTok:
    """Stable ids per word; punctuation gets its own id. Enough for the Scorer and intact_fraction."""

    def __call__(self, text, add_special_tokens=False, return_offsets_mapping=False):
        toks = re.findall(r"\w+|[^\w\s]", text)
        ids = [hash(t) % 50000 for t in toks]
        return {"input_ids": ids}


CALLS = {"count": 0}


@register("ident")
def _ident(text, opts):
    CALLS["count"] += 1
    return TransformResult(text=text)


@register("zzz")
def _zzz(text, opts):
    ws = text.split(" ")
    return TransformResult(text=" ".join("zzz" if i % 3 == 2 else w for i, w in enumerate(ws)),
                           edits=len(ws) // 3)


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "load_tokenizer", lambda name: FakeTok())
    tok = FakeTok()
    path = tmp_path / "corpus.jsonl"
    with path.open("w") as f:
        for i in range(4):
            text = " ".join(f"word{i}{k} thing{k} other{k}," for k in range(40))
            rec = {"id": f"wm-{i:03d}", "prompt": "p", "text": text, "ids": tok(text)["input_ids"],
                   "watermarked": True, "z": 9.0, "tokens": 120, "lang": "en", "model": "fake"}
            f.write(json.dumps(rec) + "\n")
            rec = dict(rec, id=f"plain-{i:03d}", watermarked=False, z=0.1)
            f.write(json.dumps(rec) + "\n")
    return path


def test_bench_writes_summary_and_measures_intact(corpus, tmp_path):
    out = tmp_path / "res"
    rc = bench.main(["--corpus", str(corpus), "--transforms", "ident,zzz", "--no-cosine", "--no-cache",
                     "--out-dir", str(out)])
    assert rc == 0
    summary = json.loads((out / "summary.json").read_text())
    lists = [v for v in (summary.values() if isinstance(summary, dict) else [summary])
             if isinstance(v, list) and v and isinstance(v[0], dict) and "transform" in v[0]]
    rows = {s["transform"]: s for s in lists[0]}
    assert (out / "summary.md").exists()
    assert rows["ident"]["intact_mean"] == 1.0
    assert rows["zzz"]["intact_mean"] < 0.2
    assert rows["ident"]["n"] == 4 and rows["zzz"]["errors"] == 0
    assert "control(plain)" in rows
    per_sample = [json.loads(l) for l in (out / "zzz.jsonl").read_text().splitlines()]
    assert len(per_sample) == 4 and all("z_after" in r and "zw_after" in r for r in per_sample)


def test_bench_cache_hit(corpus, tmp_path):
    out = tmp_path / "res"
    cache = tmp_path / "cache"
    CALLS["count"] = 0
    bench.main(["--corpus", str(corpus), "--transforms", "ident", "--no-cosine", "--cache-dir", str(cache),
                "--out-dir", str(out)])
    assert CALLS["count"] == 4
    bench.main(["--corpus", str(corpus), "--transforms", "ident", "--no-cosine", "--cache-dir", str(cache),
                "--out-dir", str(out)])
    assert CALLS["count"] == 4, "second run must be served from the cache"


def test_cli_run_check_transforms(tmp_path, capsys):
    src = tmp_path / "in.txt"
    src.write_text("Hello​ world, this is a test of the tool.")
    out = tmp_path / "out.txt"
    assert cli.main(["run", str(src), "--transform", "zzz", "-o", str(out)]) == 0
    assert "zzz" in out.read_text()
    err = capsys.readouterr().err
    assert "zzz" in err and "edits" in err
    assert cli.main(["check", str(src)]) == 0
    o = capsys.readouterr().out
    assert "ZERO WIDTH SPACE: 1" in o and "No public detector" in o
    assert cli.main(["transforms"]) == 0
    assert "hybrid" in capsys.readouterr().out
    assert cli.main(["run", str(tmp_path / "missing.txt"), "--transform", "zzz"]) != 0
