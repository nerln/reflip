"""The detectors' arithmetic on logits we choose, so every expected value is worked by hand."""
import math

import pytest
import torch

from reflip.detect import burstiness_from, features_from_logits, guess_language, sentence_spans, word_count


def uniform(T, V):
    return torch.zeros(T, V)


def test_identical_uniform_models_give_binoculars_one():
    T, V = 10, 50
    ids = torch.randint(0, V, (T,))
    f = features_from_logits(uniform(T, V), uniform(T, V), ids, list(range(T)), "x " * T)
    assert f.nll_obs == pytest.approx(math.log(V), rel=1e-6)
    assert f.xent == pytest.approx(math.log(V), rel=1e-6)
    assert f.binoculars == pytest.approx(1.0, rel=1e-6)


def test_predictable_text_scores_more_machine_like():
    """Tokens the model expected: low perplexity, low Binoculars, high Fast-DetectGPT."""
    T, V = 40, 30
    ids = torch.randint(0, V, (T,))
    peaked = torch.full((T, V), -4.0)
    for t in range(T - 1):
        peaked[t, ids[t + 1]] = 4.0          # the next token is the one the model expected
    surprised = torch.full((T, V), -4.0)
    for t in range(T - 1):
        surprised[t, (ids[t + 1] + 1) % V] = 4.0   # the model expected something else
    starts = list(range(T))
    expected = features_from_logits(peaked, peaked, ids, starts, "a b")
    unexpected = features_from_logits(surprised, surprised, ids, starts, "a b")
    assert expected.nll_obs < unexpected.nll_obs
    assert expected.binoculars < unexpected.binoculars
    assert expected.fdg_oo > 0 > unexpected.fdg_oo


def test_fast_detectgpt_matches_the_reference_formula():
    torch.manual_seed(0)
    T, V = 12, 20
    ids = torch.randint(0, V, (T,))
    ref, score = torch.randn(T, V), torch.randn(T, V)
    f = features_from_logits(score, ref, ids, list(range(T)), "z")
    # the reference implementation, written out: scoring = observer, reference = performer
    ls = torch.log_softmax(score[:-1], -1)
    pr = torch.softmax(ref[:-1], -1)
    ll = ls.gather(1, ids[1:, None]).squeeze(1)
    mean = (pr * ls).sum(-1)
    var = (pr * ls * ls).sum(-1) - mean ** 2
    want = float((ll.sum() - mean.sum()) / var.sum().sqrt())
    assert f.fdg_po == pytest.approx(want, rel=1e-5)


def test_chunking_does_not_change_the_numbers(monkeypatch):
    import reflip.detect as d

    torch.manual_seed(1)
    T, V = 300, 25
    ids = torch.randint(0, V, (T,))
    a, b = torch.randn(T, V), torch.randn(T, V)
    whole = features_from_logits(a, b, ids, list(range(T)), "t")
    monkeypatch.setattr(d, "CHUNK", 7)
    chunked = d.features_from_logits(a, b, ids, list(range(T)), "t")
    for k in ("nll_obs", "nll_perf", "xent", "binoculars", "fdg_oo", "fdg_po"):
        assert getattr(chunked, k) == pytest.approx(getattr(whole, k), rel=1e-5), k


def test_burstiness_is_the_spread_of_sentence_means():
    text = "One two three four. Five six seven eight."
    starts = [0, 4, 8, 14, 20, 25, 29, 35]          # token starts, four per sentence
    nll = [1, 1, 1, 1, 3, 3, 3, 3]
    b, n = burstiness_from(nll, starts, text)
    assert n == 2
    assert b == pytest.approx(1.0)                  # means 1 and 3, population std 1


def test_burstiness_needs_two_real_sentences():
    assert burstiness_from([1, 2, 3], [0, 1, 2], "Only one sentence here")[0] is None
    # a one-word second sentence does not count as a sentence for the spread
    assert burstiness_from([1, 1, 1, 9], [0, 2, 4, 10], "a b c. Ok.")[0] is None


def test_sentence_spans_handle_quotes_and_ellipses():
    spans = sentence_spans('He said "no." Then left… And came back?')
    assert len(spans) == 3


def test_language_guess():
    assert guess_language("The cat sat on the mat and it was happy with the view")[0] == "en"
    assert guess_language("Il gatto non è sul tappeto, ma della casa sono anche le chiavi")[0] == "it"
    assert guess_language("El gato está en la casa con los niños y las llaves del coche")[0] == "es"
    assert guess_language("12345 !!!") == (None, 0.0)


def test_word_count_ignores_numbers_and_punctuation():
    assert word_count("Hello, world: 42 times!") == 3


def test_too_short_to_score():
    with pytest.raises(ValueError):
        features_from_logits(uniform(1, 5), uniform(1, 5), torch.tensor([3]), [0], "a")
