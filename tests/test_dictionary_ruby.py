"""
Tests for furigana + highlighting in the dictionary result window (F5).

Two halves:

* `TestRuns*` are headless - they assert the run model: which parts of the
  result get a reading, which stay bare, and which are colour-coded.
* `TestWindow` drives the real `show_dictionary_result()`, which is where the
  regression risk lives: the looked-up-word highlight used to be applied with
  `Text.search()` *after* insertion, and an annotated word has no characters
  left to find.

The display half is skipped automatically without a display (`tk_root`).
"""
import inspect
import tkinter as tk
from tkinter import font as tkfont

import pytest

from src.core import furigana as F
from src.ui.dictionary_render import (
    DictRun,
    field_policy,
    overhead_px,
    runs_to_segments,
    source_language_hint,
    split_dictionary_text,
)
from src.ui.quick_translate import (
    DICT_RESULT_CHROME_PX,
    DICT_RESULT_FONT,
    HIGHLIGHT_COLORS,
    QuickTranslateManager,
    _align_dictionary_text,
)
from src.ui.ruby_text import RubyText

HAS_PROVIDER = pytest.mark.skipif(
    not F.is_available(),
    reason="requires a reading provider (fugashi or pykakasi)"
)

# A realistic lookup: Japanese source word, English target.
RESULT = """## 勉強

1. **Translation**: study
2. **Source Language**: Japanese
3. **Definition**: the act of studying
4. **Word Type**: noun
5. **Pronunciation**: /benkyoː/, /ベンキョウ/
6. **Synonyms** (if any): 学習 → learning, 研究 → research
7. **Antonyms** (if any): None
8. **Examples**:
   - 毎日日本語を勉強しています。 → I study Japanese every day.
"""

# The mirror case: English source word, Japanese target, so the *target*
# language fields are the Japanese ones.
RESULT_JA_TARGET = """## dog

1. **Translation**: 犬
2. **Source Language**: English
3. **Definition**: 家で飼う動物
4. **Word Type**: noun
5. **Pronunciation**: /dɔɡ/, /ドッグ/
"""

ALIGNED = _align_dictionary_text(RESULT)
ALIGNED_JA = _align_dictionary_text(RESULT_JA_TARGET)


def runs_for(text=None, target_lang="English", words=("勉強",), annotate=True):
    return split_dictionary_text(text if text is not None else ALIGNED,
                                 target_lang, list(words), HIGHLIGHT_COLORS,
                                 annotate=annotate)


def joined(runs):
    return ''.join(run.base for run in runs)


def runs_on_line(runs, needle):
    """The runs of the first line whose reconstructed text contains `needle`."""
    current = []
    for run in runs:
        if run.base == '\n':
            if needle in ''.join(r.base for r in current):
                return current
            current = []
        else:
            current.append(run)
    return current if needle in ''.join(r.base for r in current) else []


def readings(runs):
    """{base: ruby} for every annotated run."""
    return {run.base: run.ruby for run in runs if run.ruby}


@pytest.fixture(autouse=True)
def _clear_cache():
    F.clear_cache()
    yield
    F.clear_cache()


# --------------------------------------------------------------------------- #
# The run model
# --------------------------------------------------------------------------- #
class TestRunsCoverText:
    def test_runs_reconstruct_the_input_exactly(self):
        # Same guarantee as engine invariant I1: rendering never edits the text.
        assert joined(runs_for()) == ALIGNED

    def test_holds_for_empty_and_odd_input(self):
        for text in ("", "\n", "no fields here", "---\n\n## x\n", "\n\n\n"):
            assert joined(runs_for(text)) == text

    def test_holds_without_words_or_annotation(self):
        assert joined(runs_for(words=(), annotate=False)) == ALIGNED

    @HAS_PROVIDER
    def test_holds_for_the_japanese_target_case(self):
        assert joined(runs_for(ALIGNED_JA, "Japanese", ("dog",))) == ALIGNED_JA


class TestRunsAnnotation:
    def test_label_column_stays_plain(self):
        # Labels are padded with spaces to align the value column; a ruby frame
        # is a different width and would break the alignment.
        line = runs_on_line(runs_for(), "**Translation**")
        assert line[0].ruby is None
        assert line[0].base.startswith("1. **Translation**:")
        assert line[0].base.endswith(" ")          # alignment padding kept

    @HAS_PROVIDER
    def test_target_language_field_annotates_kanji_only_text(self):
        # 犬 has no kana, so only the authoritative target-language hint can
        # annotate it. This is the F0 gap closed for dictionary output.
        line = runs_on_line(runs_for(ALIGNED_JA, "Japanese", ("dog",)),
                            "**Translation**")
        assert "犬" in readings(line)

    @HAS_PROVIDER
    def test_definition_in_the_target_language_is_annotated(self):
        line = runs_on_line(runs_for(ALIGNED_JA, "Japanese", ("dog",)),
                            "**Definition**")
        assert readings(line), "no reading in the target-language definition"

    @HAS_PROVIDER
    def test_source_language_field_uses_the_declared_source(self):
        # Target is English, so the Japanese here can only be annotated because
        # the model declared "Source Language: Japanese".
        line = runs_on_line(runs_for(), "**Synonyms**")
        assert readings(line), "declared source language was not used"

    @HAS_PROVIDER
    def test_kanji_only_header_is_annotated_via_the_declared_source(self):
        line = runs_on_line(runs_for(), "## 勉強")
        assert "勉強" in readings(line)

    def test_no_hint_when_the_source_language_is_not_japanese(self):
        # 汉字 is Chinese; nothing declares Japanese, so it must stay plain.
        text = "## 汉字\n\n2. **Source Language**: Chinese\n"
        assert not readings(runs_for(text, "English", ()))

    def test_pronunciation_value_is_never_annotated(self):
        # Hiragana over katakana/IPA is redundant and invites misreading.
        line = runs_on_line(runs_for(), "**Pronunciation**")
        assert not readings(line)

    def test_pronunciation_is_matched_by_label_not_only_by_number(self):
        text = "2. **Pronunciation**: 勉強 /ベンキョウ/\n2. **Source Language**: Japanese"
        assert not readings(runs_for(text, "Japanese", ()))

    def test_field_five_is_suppressed_even_if_renamed(self):
        assert field_policy(5, "Reading") == (False, False)

    def test_field_policy_classifies_by_label_when_renumbered(self):
        assert field_policy(9, "Translation") == (True, True)
        assert field_policy(9, "Examples") == (True, False)

    def test_separators_and_blanks_produce_no_readings(self):
        assert not readings(runs_for("---\n\n   \n"))

    @HAS_PROVIDER
    def test_toggle_off_disables_every_reading(self):
        runs = runs_for(annotate=False)
        assert not readings(runs)
        # ...but the highlighting survives.
        assert any(run.color for run in runs)

    @HAS_PROVIDER
    def test_a_word_keeps_its_sentence_context(self):
        # The example sentence is annotated in one pass (it sits on the line
        # below the `8. **Examples**:` label). Annotating the highlighted word
        # on its own instead would hand the tokenizer an all-kanji fragment,
        # which cannot be annotated at all.
        line = runs_on_line(runs_for(), "毎日")
        assert readings(line) == {"毎日": "まいにち", "日本語": "にほんご",
                                  "勉強": "べんきょう"}


class TestSourceLanguageHint:
    def test_reads_the_declared_language(self):
        assert source_language_hint(["2. **Source Language**: Japanese"]) == "Japanese"

    def test_accepts_the_japanese_spelling(self):
        assert source_language_hint(["2. **Source Language**: 日本語"]) == "Japanese"

    def test_other_languages_give_no_hint(self):
        for value in ("Chinese", "English", "Vietnamese", ""):
            assert source_language_hint([f"2. **Source Language**: {value}"]) is None

    def test_missing_field_gives_no_hint(self):
        assert source_language_hint(["## word", "1. **Translation**: x"]) is None

    @HAS_PROVIDER
    def test_each_entry_is_resolved_separately(self):
        # A multi-word lookup can mix source languages, and the second entry
        # must not inherit the first one's hint. Both kanji-only strings below
        # sit in *source-language* fields, so only the per-entry hint decides
        # them - a document-wide hint would annotate the French entry too.
        text = ("## 犬\n"
                "2. **Source Language**: Japanese\n"
                "6. **Synonyms** (if any): 子犬 → puppy\n"
                "## chien\n"
                "2. **Source Language**: French\n"
                "6. **Synonyms** (if any): 犬 → dog\n")
        runs = split_dictionary_text(text, "English", [], HIGHLIGHT_COLORS)
        japanese_entry = runs_on_line(runs, "子犬")
        french_entry = runs_on_line(runs, "犬 → dog")
        assert readings(japanese_entry), "declared Japanese entry was not annotated"
        assert not readings(french_entry), "French entry inherited a hint"


class TestRunsHighlighting:
    def test_each_word_gets_its_palette_colour(self):
        runs = runs_for(words=("勉強", "study"))
        colors = {run.base: run.color for run in runs if run.color}
        assert colors["勉強"] == HIGHLIGHT_COLORS[0]
        assert colors["study"] == HIGHLIGHT_COLORS[1]

    def test_matching_is_case_insensitive(self):
        runs = runs_for("Study and STUDY", words=("study",))
        assert [r.base for r in runs if r.color] == ["Study", "STUDY"]

    def test_longest_word_wins_at_the_same_position(self):
        # "ice" must not mask "ice cream" and leave " cream" unhighlighted.
        runs = runs_for("ice cream is cold", words=("ice", "ice cream"))
        assert [r.base for r in runs if r.color] == ["ice cream"]

    def test_every_occurrence_is_highlighted(self):
        runs = runs_for(words=("勉強",))
        colored = [r for r in runs if r.color]
        assert len(colored) == ALIGNED.count("勉強")
        assert all("勉強" in r.base for r in colored)

    def test_blank_words_are_ignored(self):
        assert all(r.color is None for r in runs_for(words=("", None)))

    def test_a_word_inside_a_label_is_coloured_but_stays_plain(self):
        runs = runs_for("1. **Translation**: x", words=("Translation",))
        marked = [r for r in runs if r.color]
        assert [r.base for r in marked] == ["Translation"]
        assert all(r.ruby is None for r in marked)

    def test_surrounding_text_is_not_swallowed(self):
        runs = runs_for("a study b", words=("study",))
        assert [r.base for r in runs] == ["a ", "study", " b"]

    @HAS_PROVIDER
    def test_an_annotated_word_carries_the_colour(self):
        # The point of the whole design: colour and reading on the same run,
        # both in the header and mid-sentence.
        runs = runs_for()
        marked = [r for r in runs if r.base == "勉強"]
        assert len(marked) == 2
        assert all(r.ruby == "べんきょう" for r in marked)
        assert all(r.color == HIGHLIGHT_COLORS[0] for r in marked)


class TestMeasurement:
    def test_no_annotation_means_no_overhead(self):
        runs = runs_for(annotate=False)
        assert overhead_px(runs, 600, base_font=DICT_RESULT_FONT) == 0

    def test_latin_only_result_needs_no_overhead(self):
        runs = runs_for("1. **Translation**: dog", words=())
        assert overhead_px(runs, 600, base_font=DICT_RESULT_FONT) == 0

    @HAS_PROVIDER
    def test_annotated_result_needs_more_room(self):
        assert overhead_px(runs_for(), 600, base_font=DICT_RESULT_FONT) > 0

    @HAS_PROVIDER
    def test_segments_reconstruct_the_text(self):
        segments = runs_to_segments(runs_for())
        assert ''.join(seg.base for seg in segments) == ALIGNED
        assert any(seg.ruby for seg in segments)

    def test_oversized_body_is_left_plain(self):
        # Past the render budget the text still has to survive verbatim.
        huge = "私は" * 3000
        runs = runs_for(f"1. **Definition**: {huge}", "Japanese", ())
        assert joined(runs) == f"1. **Definition**: {huge}"
        assert not readings(runs)

    def test_runs_to_segments_maps_one_to_one(self):
        runs = (DictRun("私", "わたし", "#fff"), DictRun(" is me"))
        assert [s.ruby for s in runs_to_segments(runs)] == ["わたし", None]


# --------------------------------------------------------------------------- #
# The real window
# --------------------------------------------------------------------------- #
class FakeConfig:
    def __init__(self, furigana_enabled=True):
        self._furigana = furigana_enabled

    def get_furigana_enabled(self):
        return self._furigana

    def get_quick_replace(self):
        return False


@pytest.fixture
def show_result(tk_root):
    """Open the real dictionary result window; returns (window, RubyText)."""
    opened = []

    def _show(result=RESULT, target_lang="English", words=("勉強",),
              furigana_enabled=True):
        mgr = QuickTranslateManager(tk_root, FakeConfig(furigana_enabled))
        mgr._last_mouse_x, mgr._last_mouse_y = 500, 300
        mgr.show_dictionary_result(result, target_lang, None, list(words))
        tk_root.update_idletasks()
        window = tk_root.winfo_children()[-1]
        opened.append(window)
        boxes = []

        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, RubyText):
                    boxes.append(child)
                walk(child)

        walk(window)
        assert len(boxes) == 1, f"expected one RubyText, found {len(boxes)}"
        return window, boxes[0]

    yield _show
    for window in opened:
        try:
            window.destroy()
        except tk.TclError:
            pass


def ruby_bases(box):
    """Base text of every ruby pair in the widget."""
    return [box.pair_base_text(frame) for frame in box._frames]


def ruby_color(box, base):
    """Foreground of the base characters of the ruby pair for `base`."""
    for frame in box._frames:
        if box.pair_base_text(frame) == base:
            return str(box.pair_labels(frame)[1][0].cget('fg'))
    return None


class TestWindow:
    @HAS_PROVIDER
    def test_japanese_gets_readings(self, show_result):
        _window, box = show_result()
        assert box.has_ruby is True

    def test_text_is_intact_and_read_only(self, show_result):
        _window, box = show_result()
        assert box.get_plain() == ALIGNED
        assert str(box.cget('state')) == 'disabled'

    @HAS_PROVIDER
    def test_annotated_word_keeps_its_highlight(self, show_result):
        # The regression this phase had to avoid: Text.search() cannot find an
        # annotated word, so the colour used to vanish exactly where a reading
        # appeared.
        _window, box = show_result()
        assert "勉強" in ruby_bases(box)
        assert ruby_color(box, "勉強").lower() == HIGHLIGHT_COLORS[0].lower()

    def test_unannotated_word_still_gets_its_tag(self, show_result):
        _window, box = show_result(words=("study",))
        tag = f"lookup_{HIGHLIGHT_COLORS[0].lstrip('#')}"
        assert box.tag_ranges(tag), "highlight tag was never applied"

    def test_toggle_off_leaves_plain_text_and_highlights(self, show_result):
        _window, box = show_result(furigana_enabled=False)
        assert box.has_ruby is False
        assert box.get_plain() == ALIGNED
        tag = f"lookup_{HIGHLIGHT_COLORS[0].lstrip('#')}"
        assert box.tag_ranges(tag)

    def test_monospace_base_font_is_kept(self, show_result):
        # The aligned columns only line up in a monospace font.
        _window, box = show_result()
        assert box.base_font == DICT_RESULT_FONT

    @HAS_PROVIDER
    def test_pronunciation_line_has_no_ruby(self, show_result):
        _window, box = show_result()
        assert "ベンキョウ" not in ruby_bases(box)

    @HAS_PROVIDER
    def test_window_is_taller_when_annotated(self, show_result, tk_root):
        window_on, _ = show_result()
        window_off, _ = show_result(furigana_enabled=False)
        tk_root.update_idletasks()
        assert window_on.winfo_height() > window_off.winfo_height()

    def test_latin_only_result_is_unchanged(self, show_result):
        text = "## dog\n\n1. **Translation**: chien\n"
        _window, box = show_result(text, "French", ("dog",))
        assert box.has_ruby is False
        assert box.get_plain() == _align_dictionary_text(text)


class TestWindowFitsItsContent:
    """D1: the window used to be sized as if it rendered in the popup's font.

    `calculate_size()` measured Segoe UI 11 (20px rows) while this window renders
    DICT_RESULT_FONT (15px rows), and it reserved the popup's 100px of chrome plus
    a 30px "title bar compensation" on a window whose chrome is 71px and whose
    title bar is outside `geometry()` entirely. The result was a band of empty
    space that grew with the result: 139px on a 12-line lookup, 199px on 24 lines.

    What is left is the one spare row `calculate_size()` deliberately adds, so the
    assertions are written in rows of the real font rather than raw pixels - a
    machine with different metrics still gets a meaningful bound.
    """

    LONG = RESULT + "\n" + "\n".join(
        f"   - example sentence number {i} with some length to it." for i in range(12)
    )

    @staticmethod
    def _band(box, tk_root):
        """Pixels of empty box below the last row of text."""
        tk_root.update_idletasks()
        content = box.count('1.0', 'end', 'ypixels')
        if isinstance(content, tuple):
            content = content[0]
        return box.winfo_height() - content

    @staticmethod
    def _row_px():
        return tkfont.Font(family=DICT_RESULT_FONT[0],
                           size=DICT_RESULT_FONT[1]).metrics('linespace')

    @pytest.mark.parametrize("furigana_enabled", [True, False])
    @pytest.mark.parametrize("result", [RESULT, LONG], ids=["short", "long"])
    def test_no_empty_band_below_the_text(self, show_result, tk_root,
                                          result, furigana_enabled):
        _window, box = show_result(result, furigana_enabled=furigana_enabled)
        band = self._band(box, tk_root)
        assert band >= 0, "content is taller than its box - the text is clipped"
        assert band <= 3 * self._row_px(), (
            f"{band}px of empty space below the text "
            f"(more than three {DICT_RESULT_FONT} rows)"
        )

    def test_the_band_does_not_grow_with_the_result(self, show_result, tk_root):
        """The old bug's signature: 12 lines wasted 139px, 24 lines wasted 199px."""
        _w1, short_box = show_result(RESULT)
        _w2, long_box = show_result(self.LONG)
        assert self._band(long_box, tk_root) <= self._band(short_box, tk_root) + 1

    def test_sizing_and_layout_agree_on_the_chrome(self):
        """Both halves of show_dictionary_result() must subtract the same number.

        One computes the window height, the other derives the box's row count
        from it; if they disagree the box is sized for a window that was never
        requested.
        """
        source = inspect.getsource(QuickTranslateManager.show_dictionary_result)
        assert source.count("DICT_RESULT_CHROME_PX") == 2
        assert "height + 30" not in source

    def test_the_popup_default_is_untouched(self, tk_root):
        """calculate_size() gained parameters; its old behaviour must be identical."""
        mgr = QuickTranslateManager(tk_root, FakeConfig())
        mgr._last_mouse_x, mgr._last_mouse_y = 500, 300
        text = "A translated sentence that is long enough to wrap at least once. " * 3
        assert mgr.calculate_size(text) == mgr.calculate_size(
            text, base_font=('Segoe UI', 11), vertical_padding=100)

    def test_dictionary_font_gives_a_shorter_window_than_the_popup_font(self, tk_root):
        mgr = QuickTranslateManager(tk_root, FakeConfig())
        mgr._last_mouse_x, mgr._last_mouse_y = 500, 300
        as_popup = mgr.calculate_size(ALIGNED)[1]
        as_dictionary = mgr.calculate_size(
            ALIGNED, base_font=DICT_RESULT_FONT,
            vertical_padding=DICT_RESULT_CHROME_PX)[1]
        assert as_dictionary < as_popup
