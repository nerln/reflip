"""Tests for the model-free pieces: word slotting, rule edits, invisible-character cleaning."""
import pytest

from reflip.transforms import Options, get
from reflip.transforms.rules import apply_rules
from reflip.transforms.unicode import clean, scan
from reflip.words import apply_replacements, choose_slots, choose_slots_tokenaware, word_edit_ratio, words

TEXTS = [
    "Cities should invest heavily in parks because they improve the health of citizens.",
    "One. Two, three; four! Five? Six... seven (eight) nine, ten.",
    "a b c d e f g h i j k l m n o p q r s t u v w x y z",
    "Short.",
    "",
]


@pytest.mark.parametrize("stride", [1, 2, 3, 4, 5, 6])
@pytest.mark.parametrize("text", TEXTS)
def test_choose_slots_max_gap(stride, text):
    ws = words(text)
    slots = choose_slots(ws, stride)
    assert slots == sorted(set(slots))
    prev = -1
    for s in slots + [len(ws)]:
        assert s - prev <= stride
        prev = s


def test_choose_slots_respects_already():
    ws = words(TEXTS[0])
    already = {1, 4}
    slots = choose_slots(ws, 3, already=already)
    assert not set(slots) & already
    allv = sorted(set(slots) | already)
    prev = -1
    for s in allv + [len(ws)]:
        assert s - prev <= 3
        prev = s


class FakeFastTok:
    """Splits every word longer than 4 chars into two pseudo-tokens; punctuation is its own token."""

    def __call__(self, text, add_special_tokens=False, return_offsets_mapping=False):
        import re
        offs = []
        for m in re.finditer(r"\w+|[^\w\s]", text):
            s, e = m.span()
            if e - s > 4:
                offs += [(s, s + 3), (s + 3, e)]
            else:
                offs.append((s, e))
        return {"input_ids": list(range(len(offs))), "offset_mapping": offs}


@pytest.mark.parametrize("text", TEXTS[:3])
def test_choose_slots_tokenaware_covers_every_window(text):
    tok = FakeFastTok()
    ws = words(text)
    ngram = 5
    slots = choose_slots_tokenaware(text, ws, tok, ngram)
    offs = tok(text, return_offsets_mapping=True)["offset_mapping"]
    edited_tok = set()
    for wi in slots:
        w = ws[wi]
        for ti, (s, e) in enumerate(offs):
            if s < w.end and w.start < e:
                edited_tok.add(ti)
    for start in range(0, len(offs) - ngram + 1):
        window = set(range(start, start + ngram))
        assert window & edited_tok, f"window at {start} has no edit in {text!r}"


def test_apply_replacements_preserves_everything_else():
    t = "Keep  spacing,\n\tand punctuation! Ok?"
    ws = words(t)
    out = apply_replacements(t, ws, {1: "SPACING", 4: "Fine"})
    assert out == "Keep  SPACING,\n\tand punctuation! Fine?"


def test_word_edit_ratio():
    assert word_edit_ratio("a b c d", "a b c d") == 0.0
    assert word_edit_ratio("a b c d", "a x c y") == 0.5
    assert word_edit_ratio("", "x") == 0.0


# ----------------------------------------------------------------------------- rules
def test_rules_each_positive():
    cases = {
        "dashes": ("word — word", "word, word"),
        "typography": ("“hi” it’s…", '"hi" it\'s...'),
        "contractions": ("Don't stop. I'm here. We will go.", "Do not stop. I am here. We'll go."),
        "serial_comma": ("apples, pears, and plums", "apples, pears and plums"),
        "spelling": ("the color and the favorite theater", "the colour and the favourite theatre"),
        "phrases": ("In order to utilize it, e.g. now", "To use it, for example now"),  # stylecheck: allow, test data for the rule that removes it
        "numbers": ("10 percent of 1,000 people", "10% of 1000 people"),
    }
    for name, (src, want) in cases.items():
        got, counts = apply_rules(src, (name,))
        assert got == want, (name, got)
        assert counts[name] >= 1


def test_rules_leave_protected_spans_and_numbers_alone():
    src = "See https://x.y/a—b and `don't` and me@x.org, from 2019–2021, at /usr/bin/don't"  # stylecheck: allow, test data for the rule that removes it
    got, _ = apply_rules(src)
    assert "https://x.y/a—b" in got and "`don't`" in got and "me@x.org" in got and "2019–2021" in got
    assert "/usr/bin/don't" in got


def test_rules_keep_case_and_layout():
    src = "DON'T shout.\n\n  Indented color line.\nCan't we?"
    got, _ = apply_rules(src)
    assert got == "DO NOT shout.\n\n  Indented colour line.\nCannot we?"
    assert "  " not in got.replace("\n  ", "")


def test_rules_ambiguous_contractions_untouched():
    src = "I'd say he's fine and that's it."
    got, counts = apply_rules(src, ("contractions",))
    assert got == src and counts["contractions"] == 0


def test_rules_transform_reports_density():
    res = get("rules")("Don't use the color red.", Options())
    assert res.edits == 2
    assert res.notes["density"] == 40.0
    assert res.notes["rules"]["contractions"] == 1


def test_rules_italian_only_typographic():
    src = "Non c’è — davvero. Additionally, color."  # stylecheck: allow, test data for the rule that removes it
    got, counts = apply_rules(src, language="it")
    assert got == "Non c'è, davvero. Additionally, color."
    assert "phrases" not in counts and "spelling" not in counts


# ----------------------------------------------------------------------------- unicode
def test_unicode_clean_and_scan():
    src = "a​b c 👍️ d️ ```x​y``` ­e"
    got, n = clean(src)
    assert got == "ab c 👍️ d ```x​y``` e"
    assert n == 4
    found = scan(src)
    assert found["ZERO WIDTH SPACE"] == 2  # scan looks inside code too
    assert found["NO-BREAK SPACE"] == 1 and found["SOFT HYPHEN"] == 1
    assert found.get("VARIATION SELECTOR-16") == 1


def test_unicode_transform_is_identity_on_clean_text():
    res = get("unicode")("plain text, nothing hidden", Options())
    assert res.text == "plain text, nothing hidden" and res.edits == 0
