"""The benchmark's statistics and the two pre-registered rules, without any model."""
import random

import pytest
from sklearn.metrics import roc_auc_score

from reflip.detect_bench import allowed, auroc, boot_auroc, choose, cp_upper, quantile, split, wilson


@pytest.mark.parametrize("seed", range(5))
def test_auroc_matches_sklearn_with_ties(seed):
    rng = random.Random(seed)
    pos = [rng.choice([0.1, 0.2, 0.3, 0.5, 0.9]) for _ in range(40)]
    neg = [rng.choice([0.0, 0.1, 0.2, 0.3]) for _ in range(70)]
    want = roc_auc_score([1] * len(pos) + [0] * len(neg), pos + neg)
    assert auroc(pos, neg) == pytest.approx(want, abs=1e-12)


def test_auroc_extremes():
    assert auroc([2, 3], [0, 1]) == 1.0
    assert auroc([0, 1], [2, 3]) == 0.0
    assert auroc([1, 1], [1, 1]) == 0.5


def test_bootstrap_interval_brackets_the_estimate():
    rng = random.Random(0)
    pos = [rng.gauss(1, 1) for _ in range(60)]
    neg = [rng.gauss(0, 1) for _ in range(60)]
    lo, hi = boot_auroc(pos, neg, random.Random(1), n=400)
    assert lo < auroc(pos, neg) < hi


def test_wilson_interval():
    lo, hi = wilson(0, 75)
    assert lo == 0.0 and 0.03 < hi < 0.06
    lo, hi = wilson(10, 20)
    assert lo < 0.5 < hi


def test_quantile_interpolates():
    assert quantile([1, 2, 3, 4, 5], 0.5) == 3
    assert quantile([0, 10], 0.99) == pytest.approx(9.9)


def test_split_is_half_per_cell_and_rewrites_are_test_only():
    rows = [{"id": f"h{i}", "kind": "human", "lang": "en", "bucket": "medium"} for i in range(400)]
    rows += [{"id": f"a{i}", "kind": "ai", "lang": "en", "bucket": "medium"} for i in range(40)]
    rows += [{"id": f"w{i}", "kind": "ai_reflip", "lang": "en", "bucket": "medium"} for i in range(5)]
    rows += [{"id": f"l{i}", "kind": "human_l2", "lang": "en", "bucket": "medium"} for i in range(5)]
    split(rows)
    assert sum(r["half"] == "calib" for r in rows if r["kind"] == "human") == 100   # 100 calibrate, 300 test
    assert sum(r["half"] == "calib" for r in rows if r["kind"] == "ai") == 20
    assert all(r["half"] == "test" for r in rows if r["kind"] in ("ai_reflip", "human_l2"))
    again = [dict(r) for r in rows]
    split(again)
    assert [r["half"] for r in again] == [r["half"] for r in rows]   # seed 0, reproducible


def test_choice_rule_prefers_the_small_pair_within_half_a_point():
    pairs = {
        "qwen2.5-1.5b": {"detectors": {"binoculars": {"mean_auroc_medium_long": 0.954}}},
        "qwen2.5-0.5b": {"detectors": {"binoculars": {"mean_auroc_medium_long": 0.950},
                                       "perplexity": {"mean_auroc_medium_long": 0.900}}},
    }
    assert choose(pairs)[:2] == ("qwen2.5-0.5b", "binoculars")
    pairs["qwen2.5-1.5b"]["detectors"]["binoculars"]["mean_auroc_medium_long"] = 0.970
    assert choose(pairs)[:2] == ("qwen2.5-1.5b", "binoculars")


def test_clopper_pearson_upper_bound():
    assert cp_upper(0, 300) == pytest.approx(0.00994, abs=2e-4)    # zero in 300 bounds the rate under 1%
    assert cp_upper(0, 75) == pytest.approx(0.0392, abs=5e-4)      # the council's 3.9%
    assert cp_upper(1, 300) < 0.02 < cp_upper(2, 300)


def test_refusal_rule():
    good = {"auroc": 0.97, "auroc_low": 0.9, "tpr": 0.7, "fp": 1, "n_human": 300, "fpr_upper": cp_upper(1, 300)}
    assert allowed(good)[0]
    ok, why = allowed({**good, "auroc_low": 0.8})
    assert not ok and "0.80" in why
    ok, why = allowed({**good, "tpr": 0.3})
    assert not ok and "30%" in why
    ok, why = allowed({**good, "fp": 3, "fpr_upper": cp_upper(3, 300)})
    assert not ok and "3 of 300" in why
    assert not allowed({"n_ai": 2})[0]
