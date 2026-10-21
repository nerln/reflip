"""What the user is told, from a calibration written by hand so every answer is predictable."""
import json

import pytest

from reflip import detect_assess as da

LONG_EN = ("The council met on Tuesday to discuss the new bike lanes. " * 20).strip()
SHORT_EN = "The council met on Tuesday and the plan was approved by most of the members there."


def calib(allowed=True):
    bucket = {"threshold": -0.92, "human_scores": sorted([-1.1 + i * 0.0018 for i in range(100)])}
    cell = {"allowed": allowed, "why": "AUROC lower bound 0.70, under 0.85" if not allowed else "fine",
            "auroc": 0.95, "auroc_low": 0.9 if allowed else 0.7, "tpr": 0.8, "fpr": 0.003,
            "fpr_upper": 0.016, "n_human": 300}
    return {"v": 1, "pair": "qwen2.5-0.5b", "detector": "binoculars", "fpr": 0.01,
            "words": {"short": [40, 99], "medium": [100, 300], "long": [301, 600]},
            "buckets": {b: bucket for b in ("short", "medium", "long")},
            "cells": {f"{l}/{b}": cell for l in ("en", "it", "es") for b in ("short", "medium", "long")},
            "logistic": None}


def feats(binoculars):
    return {"binoculars": binoculars, "nll_obs": 2.0, "fdg_oo": 1.0, "fdg_po": 1.0, "burstiness": 0.5}


def test_too_short_is_refused_with_the_measured_floor():
    a = da.assess("Only a few words here.", None, calib())
    assert a["verdict"] is None and "40" in a["refused"]


def test_unknown_language_is_refused():
    a = da.assess("Der Rat hat am Dienstag die neuen Radwege beschlossen und alle waren dafür " * 5, None, calib())
    assert a["refused"] and "Italian, Spanish or English" in a["refused"]


def test_machine_like_text_crosses_the_threshold():
    a = da.assess(LONG_EN, feats(0.85), calib())
    assert a["verdict"] == "machine-like"
    assert a["human_tail"]["count"] == 0 and a["human_tail"]["of"] == 100
    assert a["human_tail"]["high"] < 0.05                      # Wilson upper bound on 0 of 100
    assert "p_machine_at_even_odds" not in a                   # no probability (PREREG amendment)
    assert any("1.6%" in line for line in da.sentences(a))


def test_human_like_text_is_no_evidence_not_proof():
    a = da.assess(LONG_EN, feats(1.05), calib())
    assert a["verdict"] == "no evidence"
    assert a["human_tail"]["share"] > 0.5
    assert any("not proof" in s for s in da.sentences(a))


def test_disallowed_cell_refuses_but_still_reports_the_tail():
    a = da.assess(LONG_EN, feats(0.85), calib(allowed=False))
    assert a["verdict"] is None and "0.85" in a["refused"]
    assert a["human_tail"] is not None


def test_every_answer_carries_the_vendor_watermark_note():
    for text, f in ((SHORT_EN, None), (LONG_EN, feats(0.9)), ("x", None)):
        a = da.assess(text, f, calib())
        assert "Anthropic" in a["note"] and "secrets" in a["note"]
        assert da.sentences(a)[-1] == da.VENDOR_NOTE


def test_longer_than_measured_is_filed_as_long():
    assert da.bucket_for(2000, calib()) == "long"
    assert da.bucket_for(30, calib()) is None


def test_the_answer_is_json_without_the_text():
    a = da.assess(LONG_EN, feats(0.9), calib())
    blob = json.dumps(a)
    assert "council met" not in blob                           # numbers only, never the text
