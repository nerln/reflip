"""Model-free tests of the SynthID testbed and of the edit-every-k-tokens theory.

We do not need a language model to check the detector arithmetic: a "generator" that at
each step picks, among K random candidate tokens, the one with the largest sum of g-values
is a caricature of tournament sampling, and its output is watermarked with the same key
the Scorer holds. From there we can measure exactly what edits do to the detector.
"""
import random

import pytest
import torch

from reflip.synthid import DEFAULT_NGRAM_LEN, PortableSynthID, Scorer, intact_fraction


class FakeTok:
    """Scorer only needs __call__(text, add_special_tokens=False)['input_ids']."""

    def __call__(self, text, add_special_tokens=False, **kw):
        return {"input_ids": [int(t) for t in text.split()]}


def simulate_watermarked(proc: PortableSynthID, n: int, k: int = 8, vocab: int = 50000, seed: int = 0) -> list[int]:
    rng = random.Random(seed)
    ids = [rng.randrange(vocab) for _ in range(proc.ngram_len - 1)]
    for _ in range(n):
        ctx = ids[-(proc.ngram_len - 1):]
        cands = [rng.randrange(vocab) for _ in range(k)]
        batch = torch.tensor([ctx + [c] for c in cands], dtype=torch.long)
        g = proc.compute_g_values(batch)[:, 0, :].sum(dim=1)  # (k,)
        ids.append(cands[int(torch.argmax(g))])
    return ids


@pytest.fixture(scope="module")
def scorer():
    return Scorer(FakeTok())


def test_table_is_device_independent():
    cpu = PortableSynthID(device="cpu")
    other = PortableSynthID(device="mps" if torch.backends.mps.is_available() else "cpu")
    assert torch.equal(cpu.sampling_table, other.sampling_table.cpu())


def test_null_text_scores_near_zero(scorer):
    rng = random.Random(1)
    zs = [scorer.score_ids([rng.randrange(50000) for _ in range(300)]).z for _ in range(20)]
    assert all(abs(z) < 4.5 for z in zs)
    assert abs(sum(zs) / len(zs)) < 1.0


def test_simulated_watermark_is_detected(scorer):
    ids = simulate_watermarked(scorer.proc, 300)
    s = scorer.score_ids(ids)
    assert s.mean_g > 0.6
    assert s.z > 10


def _replace_every(ids, k, seed=7):
    rng = random.Random(seed)
    return [rng.randrange(50000) if i % k == 0 else t for i, t in enumerate(ids)]


def test_edit_every_ngram_len_tokens_removes_watermark(scorer):
    ids = simulate_watermarked(scorer.proc, 400)
    edited = _replace_every(ids, DEFAULT_NGRAM_LEN)
    assert intact_fraction(ids, edited) == 0.0
    assert abs(scorer.score_ids(edited).z) < 4.0


def test_sparser_edits_only_weaken_it(scorer):
    ids = simulate_watermarked(scorer.proc, 400)
    z0 = scorer.score_ids(ids).z
    edited = _replace_every(ids, 2 * DEFAULT_NGRAM_LEN)
    frac = intact_fraction(ids, edited)
    assert 0.4 < frac < 0.6
    z1 = scorer.score_ids(edited).z
    assert 0.3 * z0 < z1 < 0.7 * z0


def test_insertions_and_deletions_count_as_edits(scorer):
    ids = simulate_watermarked(scorer.proc, 200)
    with_insert = ids[:100] + [123] + ids[100:]
    assert 0.95 < intact_fraction(ids, with_insert) < 1.0
    with_delete = ids[:100] + ids[101:]
    assert 0.95 < intact_fraction(ids, with_delete) < 1.0
