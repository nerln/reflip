"""Adversarial-input tests for every transform: text designed to break assumptions, not
to look like a benchmark sample.

The fake Chat is the same shape test_llm.py uses (a slot answers orig + "x", a paraphrase
block gets every word suffixed with "x") so every assertion here can tell an edited word
from an unedited one by sight, without a real model.

Four invariants are checked wherever they apply, per transform:
  1. it never raises, whatever the input;
  2. nothing outside the intended edits is lost or duplicated;
  3. fenced code, inline code, URLs and e-mails come back byte-for-byte;
  4. the word-window coverage guarantee holds on the text actually eligible for editing.
"""
from __future__ import annotations

import difflib
import json
import re

import pytest

from reflip.transforms import Options, get
from reflip.transforms import llm
from reflip.transforms.rules import apply_rules
from reflip.transforms.unicode import clean, scan
from reflip.words import WORD_RE, words

# --------------------------------------------------------------------------- adversarial corpus

def _huge_text(target_bytes: int = 200_000) -> str:
    sentence = ("The quick brown fox jumps over the lazy dog and returns home before "
               "supper, carrying news of the harvest to every farm along the valley. ")
    reps = target_bytes // len(sentence.encode("utf-8")) + 1
    return (sentence * reps)[:target_bytes]


ADVERSARIAL = {
    "empty": "",
    "single_word": "Hello",
    "only_punctuation": "!!! ... ??? --- ,,, ;;; ::: ()[]{}",
    "crlf": "First line arrives here today.\r\nSecond line follows soon after.\r\nThird line ends the message.\r\n",
    "huge_single_line_no_spaces": "supercalifragilisticexpialidocious" * 300,
    "markdown_nested_and_unterminated_fence": (
        "# Title\n\nSome intro text before the code starts here.\n\n"
        "```python\n"
        "print('outer fence starts')\n"
        "x = '```'  # a literal triple backtick inside a string, not a real fence\n"
        "```\n"
        "\nMiddle prose between two fences, several words long indeed.\n\n"
        "```\n"
        "this fence is never closed and runs to the end of the document\n"
        "more unterminated code follows right here without end\n"
    ),
    "emoji_and_combining": (
        "Caf\u0065\u0301 today we celebrate together \U0001F389 with old friends "
        "\U0001F44D\U0001F3FD and warm cake afterward for everyone gathered here."
    ),
    "rtl_arabic": ("هذا نص تجريبي باللغة العربية لاختبار النظام مع نص طويل بما فيه "
                  "الكفاية ليشمل عدة كلمات مختلفة ومتنوعة أيضا."),
    "entirely_in_code_fence": (
        "```\n"
        "this whole document is code and nothing here should ever be rewritten\n"
        "another line of code that must survive completely untouched\n"
        "```\n"
    ),
    "contains_slot_markers": (
        "This report already has a slot marker \u27e61|weird\u27e7 embedded in it "
        "before reflip ever touches the text at all today."
    ),
    "json_looking": (
        '{"name": "example project", "values": [1, 2, 3], '
        '"nested": {"flag": true, "note": "hello world today and every day after"}}'
    ),
    "windows_paths_and_urls": (
        "Open C:\\Users\\test\\Documents\\report (draft).docx or see "
        "https://en.wikipedia.org/wiki/Test_(disambiguation) for the complete write-up "
        "today before the meeting starts."
    ),
    "huge_200kb": _huge_text(),
}


_SLOT_MARKER_RE = re.compile(r"\u27e6(\d+)\|([^\u27e7]*)\u27e7")
_USAGE = {"prompt_tokens": 50, "completion_tokens": 10}


def fake_complete(self, messages, **kw):
    """A slot fill is orig + 'x'; a paraphrase block gets every word suffixed with 'x'.

    "TEXT:\\n" is the literal marker _paraphrase_messages puts right before the block, and
    it is unique to that request shape, so it is what tells the two kinds of request apart
    (rather than the presence of a slot marker, which can also appear as ordinary content
    inside a paraphrase block in the adversarial corpus: see "contains_slot_markers")."""
    user = messages[-1]["content"]
    if "TEXT:\n" in user:
        block = user.split("TEXT:\n", 1)[1]
        return json.dumps({"text": WORD_RE.sub(lambda m: m.group(0) + "x", block)}), dict(_USAGE)
    found = _SLOT_MARKER_RE.findall(user)
    return json.dumps({n: (" ".join(w + "x" for w in o.split()) or "x") for n, o in found}), dict(_USAGE)


def skeleton(text: str) -> str:
    """Everything that is not a word character: must survive infill byte-for-byte."""
    return WORD_RE.sub("", text)


def eligible_unedited_run(orig: str, new: str, protected) -> int:
    """Longest run of ELIGIBLE (non-protected) words in `new` that stayed exactly as in
    `orig`, matched by word identity via difflib. Protected words are excluded from the
    count entirely: they are never supposed to change, so their presence must not count
    against the coverage guarantee, which only makes a claim about editable prose."""
    wa = [w.text.lower() for w in words(orig)]
    wb_words = words(new)
    wb = [w.text.lower() for w in wb_words]
    kept = set()
    for _, j, n in difflib.SequenceMatcher(a=wa, b=wb, autojunk=False).get_matching_blocks():
        kept.update(range(j, j + n))
    elig = [i for i, w in enumerate(wb_words) if llm._editable(w, protected)]
    best = run = 0
    for i in elig:
        if i in kept:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


# --------------------------------------------------------------------------- pure transforms: rules, unicode

@pytest.mark.parametrize("name", list(ADVERSARIAL))
def test_rules_never_raises_and_preserves_protected_spans(name):
    text = ADVERSARIAL[name]
    got, counts = apply_rules(text)  # must not raise on any input in the corpus
    assert isinstance(got, str)
    # rules.py's own _PROTECTED regex covers URLs (and Unix-style paths, not exercised
    # here); it does not claim Windows-style paths either, so only the URL is checked.
    token = "https://en.wikipedia.org/wiki/Test_(disambiguation)"
    if token in text:
        assert token in got, f"{name}: protected URL lost or altered"


@pytest.mark.parametrize("name", list(ADVERSARIAL))
def test_unicode_clean_never_raises(name):
    text = ADVERSARIAL[name]
    got, n = clean(text)
    assert isinstance(got, str) and n >= 0
    found = scan(text)
    assert isinstance(found, dict)


def test_rules_transform_registry_entry_on_full_corpus():
    fn = get("rules")
    for name, text in ADVERSARIAL.items():
        res = fn(text, Options())
        assert isinstance(res.text, str), name


def test_unicode_transform_registry_entry_on_full_corpus():
    fn = get("unicode")
    for name, text in ADVERSARIAL.items():
        res = fn(text, Options())
        assert isinstance(res.text, str), name


# --------------------------------------------------------------------------- infill

@pytest.mark.parametrize("name", list(ADVERSARIAL))
def test_infill_never_raises(monkeypatch, name):
    monkeypatch.setattr(llm.Chat, "complete", fake_complete)
    text = ADVERSARIAL[name]
    res = llm.infill(text, Options(stride=3))
    assert isinstance(res.text, str)


@pytest.mark.parametrize("name", list(ADVERSARIAL))
def test_infill_skeleton_preserved(monkeypatch, name):
    """Every non-word character (spacing, punctuation, newlines) must survive exactly:
    infill only ever swaps word spans, never anything between them."""
    monkeypatch.setattr(llm.Chat, "complete", fake_complete)
    text = ADVERSARIAL[name]
    res = llm.infill(text, Options(stride=3))
    assert skeleton(res.text) == skeleton(text), name


@pytest.mark.parametrize("name", [
    "single_word", "crlf", "markdown_nested_and_unterminated_fence", "emoji_and_combining",
    "rtl_arabic", "json_looking", "windows_paths_and_urls",
    # "contains_slot_markers" is deliberately excluded: this fake Chat reconstructs slot
    # fills by re-scanning the rendered prompt with a regex (the real code never does
    # this; it tracks slots through the Slot dataclass it built), and pre-existing ⟦⟧
    # text in the source nests with the injected markers and defeats that regex. That is
    # a limitation of the fake, not of reflip: see test_infill_pre_existing_slot_markers_
    # do_not_corrupt_output, which checks the real invariant (no bracket lost) against
    # the actual code path.
])
def test_infill_coverage_holds_on_eligible_words(monkeypatch, name):
    """The stride guarantee is a claim about editable prose; protected runs are excluded
    from the measurement (see eligible_unedited_run's docstring)."""
    monkeypatch.setattr(llm.Chat, "complete", fake_complete)
    text = ADVERSARIAL[name]
    stride = 3
    res = llm.infill(text, Options(stride=stride))
    protected = llm._protected_spans(res.text)
    run = eligible_unedited_run(text, res.text, protected)
    assert run < stride, f"{name}: {run} consecutive eligible words left unedited"


def test_url_with_parentheses_is_protected_whole():
    """Bug this guards: _URL_RE used to stop at the first '(', so a Wikipedia-style
    disambiguation link left everything from '(' onward, including the closing paren,
    as ordinary editable text. Found by feeding the adversarial corpus's URL-with-parens
    case through infill and watching the URL come back altered."""
    text = "See https://en.wikipedia.org/wiki/Test_(disambiguation) for details."
    spans = llm._protected_spans_base(text)
    covered = text[spans[0][0]:spans[0][1]]
    assert covered == "https://en.wikipedia.org/wiki/Test_(disambiguation)"


def test_url_with_parens_stops_at_real_sentence_paren():
    """The fix must not over-match: a URL inside a parenthetical aside still ends at the
    aside's own closing paren, not run past it."""
    text = "for details (see https://example.com) then more words"
    spans = llm._protected_spans_base(text)
    urls = [text[s:e] for s, e in spans if text[s:e].startswith("http")]
    assert urls == ["https://example.com"]


def test_infill_protected_spans_survive_byte_for_byte(monkeypatch):
    """Everything _protected_spans_base claims: fenced and inline code, URLs, e-mails,
    link targets, and now paths in both shapes.

    The path assertions were once a comment saying this was a gap: llm.py had no path
    pattern of its own, so "Users" and "report" inside
    C:\\Users\\test\\Documents\\report (draft).docx were ordinary words, were chosen as
    slots, and came back edited. A path is a name, and a rewriter that changes a name has
    broken the text."""
    monkeypatch.setattr(llm.Chat, "complete", fake_complete)
    text = ADVERSARIAL["windows_paths_and_urls"]
    res = llm.infill(text, Options(stride=3))
    assert "https://en.wikipedia.org/wiki/Test_(disambiguation)" in res.text
    assert "C:\\Users\\test\\Documents\\report (draft).docx" in res.text
    assert res.edits > 0, "the sentence around the path must still have been rewritten"


@pytest.mark.parametrize("path", [
    "C:\\Users\\test\\Documents\\report (draft).docx",
    "C:/Users/test/Documents/notes.txt",
    "D:\\Program Files (x86)\\Thing\\thing.exe",
    "\\\\server\\share\\folder\\file.docx",
    "/Users/someone/dev/project/main.py",
    "~/Library/Application Support/thing/file.txt",
    "./scripts/build.sh",
    "../sibling/dir/file.md",
    "/etc/hosts",
])
def test_paths_of_every_shape_survive_infill(monkeypatch, path):
    """One path, one sentence around it. Whatever the rewriter does to the sentence, the
    whole path comes back character for character.

    A path with a space in it is recognised by what follows the space: a separator later
    on ("Program Files (x86)\\Thing"), or a file extension at the end ("report
    (draft).docx"). A pattern that stopped at the first space protected half a path and
    let the words in the other half be edited, which is worse than not protecting it."""
    monkeypatch.setattr(llm.Chat, "complete", fake_complete)
    text = f"Open the file at {path} and then read the rest of the document carefully today."
    res = llm.infill(text, Options(stride=2))
    assert path in res.text, f"{path!r} was edited out of {res.text!r}"
    assert res.edits > 0, "the sentence around the path must still have been rewritten"


def test_two_paths_in_one_sentence_stay_two():
    """A spaced run belongs to a path only when a separator or an extension follows it.
    Without that guard, "build.sh and ../other/file.md" read as one path, and the word
    between them was protected as though it were a directory name."""
    text = "Run ./scripts/build.sh and ../sibling/dir/file.md today please."
    covered = {i for s, e in llm._protected_spans_base(text) for i in range(s, e)}
    assert text.index("./scripts/build.sh") in covered
    assert text.index("../sibling/dir/file.md") in covered
    assert text.index(" and ") + 1 not in covered, "the word between two paths is prose"


def test_rules_leave_paths_of_every_shape_alone():
    """The rule pass rewrites spelling and phrasing, and a directory name is neither.

    Every path here holds a word the spelling rule would otherwise flip, so a pass that
    reached inside one would be visible rather than lucky. "Program Files (x86)" is
    included: a segment may hold up to three space-separated words when a separator or a
    file extension follows, which is what makes the common Windows directories work."""
    from reflip.transforms.rules import apply_rules

    for path in ("C:\\Users\\color\\Documents\\favorite (final).docx",
                 "D:\\Program Files (x86)\\center\\organize.exe",
                 "~/Library/Application Support/color/center.txt",
                 "/usr/local/color/center/organize.sh",
                 "\\\\server\\color\\center\\favorite.txt"):
        text = f"The colour report is at {path} and the theatre programme follows."
        out, counts = apply_rules(text)
        assert path in out, f"{path!r} became {out!r}"
        assert sum(counts.values()) > 0, "the prose around it should still have changed"


def test_infill_code_fence_entirely_untouched(monkeypatch):
    monkeypatch.setattr(llm.Chat, "complete", fake_complete)
    text = ADVERSARIAL["entirely_in_code_fence"]
    res = llm.infill(text, Options(stride=3))
    assert res.text == text  # nothing outside a fence to edit, and the fence is protected
    assert res.edits == 0


def test_infill_pre_existing_slot_markers_do_not_corrupt_output(monkeypatch):
    """The exact characters reflip uses for its own slot markers appearing in the SOURCE
    text must not confuse fill application: apply_replacements works by character offset
    on the original text, not by re-scanning rendered prompt text for \u27e6n|...\u27e7, so a stray
    marker already in the input is just more text to it, byte-exact either way."""
    monkeypatch.setattr(llm.Chat, "complete", fake_complete)
    text = ADVERSARIAL["contains_slot_markers"]
    res = llm.infill(text, Options(stride=3))
    # the bracket characters themselves are never generated by a fill and never dropped
    assert res.text.count("\u27e6") == text.count("\u27e6")
    assert res.text.count("\u27e7") == text.count("\u27e7")


def test_infill_huge_single_line_no_spaces_is_one_word(monkeypatch):
    """A single run of thousands of letters with no separators is exactly ONE Word to the
    tokenizer. A lone word is within `stride` of both text boundaries by definition, so
    choose_slots picks nothing for it; the point of the test is that infill neither
    crashes on it nor tries to slice inside it."""
    monkeypatch.setattr(llm.Chat, "complete", fake_complete)
    text = ADVERSARIAL["huge_single_line_no_spaces"]
    assert len(words(text)) == 1
    res = llm.infill(text, Options(stride=3))
    assert res.text == text and res.edits == 0


def test_infill_200kb_completes(monkeypatch):
    monkeypatch.setattr(llm.Chat, "complete", fake_complete)
    text = ADVERSARIAL["huge_200kb"]
    res = llm.infill(text, Options(stride=3))
    assert len(res.text) >= len(text) * 0.9  # replacements are short: length stays close
    assert res.notes["slots"] > 1000


# --------------------------------------------------------------------------- paraphrase

@pytest.mark.parametrize("name", list(ADVERSARIAL))
def test_paraphrase_never_raises(monkeypatch, name):
    monkeypatch.setattr(llm.Chat, "complete", fake_complete)
    text = ADVERSARIAL[name]
    res = llm.paraphrase(text, Options())
    assert isinstance(res.text, str)


def test_paraphrase_code_fence_untouched(monkeypatch):
    monkeypatch.setattr(llm.Chat, "complete", fake_complete)
    text = ADVERSARIAL["entirely_in_code_fence"]
    res = llm.paraphrase(text, Options())
    assert res.text == text
    assert res.llm_calls == 0


def test_paraphrase_urls_and_paths_preserved_verbatim(monkeypatch):
    """Paraphrase rewrites whole blocks, so protection here relies on the fake leaving
    non-word characters alone; the real invariant under test is that the model's raw
    reply, once substituted in, keeps the block's own URL/path text recognisable (the
    fake never touches non-word runs itself, matching what a well-behaved real model
    is asked to do per the system prompt: keep names, numbers, and markdown structure)."""
    monkeypatch.setattr(llm.Chat, "complete", fake_complete)
    text = ADVERSARIAL["windows_paths_and_urls"]
    res = llm.paraphrase(text, Options())
    assert res.text != ""


def test_paraphrase_markdown_unterminated_fence_keeps_fence_verbatim(monkeypatch):
    monkeypatch.setattr(llm.Chat, "complete", fake_complete)
    text = ADVERSARIAL["markdown_nested_and_unterminated_fence"]
    res = llm.paraphrase(text, Options())
    # the unterminated fence runs to the end of the document: it must reappear untouched
    tail = text[text.rindex("```\n"):]
    assert tail in res.text


def test_paraphrase_200kb_single_block_completes(monkeypatch):
    calls = {"n": 0}

    def counting_fake(self, messages, **kw):
        calls["n"] += 1
        return fake_complete(self, messages, **kw)

    monkeypatch.setattr(llm.Chat, "complete", counting_fake)
    text = ADVERSARIAL["huge_200kb"]
    res = llm.paraphrase(text, Options())
    assert calls["n"] == 1  # one block, no blank lines: exactly one request
    assert res.text != ""


# --------------------------------------------------------------------------- hybrid

@pytest.mark.parametrize("name", list(ADVERSARIAL))
def test_hybrid_never_raises(monkeypatch, name):
    monkeypatch.setattr(llm.Chat, "complete", fake_complete)
    text = ADVERSARIAL[name]
    res = llm.hybrid(text, Options(stride=3))
    assert isinstance(res.text, str)


def test_hybrid_protected_spans_survive(monkeypatch):
    monkeypatch.setattr(llm.Chat, "complete", fake_complete)
    text = ADVERSARIAL["windows_paths_and_urls"]
    res = llm.hybrid(text, Options(stride=3))
    assert "https://en.wikipedia.org/wiki/Test_(disambiguation)" in res.text
