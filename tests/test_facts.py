import json
from pathlib import Path

import pytest

from reflip.facts import diff, lexicon_js, sentences

CASES = json.loads((Path(__file__).parent / "fixtures" / "facts-cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_shared_cases(case):
    d = diff(case["a"], case["b"], case["lang"])
    assert d["altered"] == case["altered"], d
    for part in ("numbers", "names", "quantifiers", "negations"):
        if part in case:
            assert d[part] == case[part], (part, d[part])


def test_the_same_text_changes_nothing():
    text = CASES[1]["a"]
    d = diff(text, text, "en")
    assert d["altered"] == 0 and sentences(d) == ["No number, name, negation or quantifier changed."]


def test_sentences_say_what_changed():
    lines = sentences(diff(CASES[1]["a"], CASES[1]["b"], "en"))
    assert lines[0].startswith("3 facts changed")
    assert "Numbers: gone 18, 412; new 16." in lines


def test_the_browser_reads_the_same_lexicon():
    js = Path(__file__).resolve().parent.parent / "docs" / "app" / "facts-lexicon.js"
    assert js.read_text() == lexicon_js(), "regenerate it with reflip.facts.lexicon_js()"
