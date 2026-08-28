"""
Tests for the ruby text widget (src/ui/ruby_text.py).

Two halves:

* The wrap/height arithmetic, exercised through an injected LayoutModel so it
  runs with no display at all.
* The widget itself, which needs Tk. Those tests are skipped automatically when
  no display is available (see the `tk_root` fixture in conftest.py).

The pixel-exactness test is the important one: it compares the predicted height
against Text.count(..., 'ypixels') and is what proved that Tk charges spacing1 /
spacing3 once per *logical* line rather than once per wrapped display row.
"""
import tkinter as tk
from tkinter import font as tkfont

import pytest

from src.core import furigana as F
from src.core.furigana import RubySegment
from src.ui import ruby_text as R
from src.ui.ruby_text import LayoutModel, RowCounts, RubyText


# A deterministic stand-in for real font metrics: every base character is 10px
# wide, every ruby frame 30px, a plain row is 20px and a ruby row 40px.
FIXED = LayoutModel(
    content_plain=20,
    content_ruby=40,
    line_spacing=8,
    char_width=lambda ch: 10,
    ruby_width=lambda base, ruby: 30,
)

# Segments whose bases concatenate to SOURCE. Built by hand so the widget tests
# do not depend on which reading provider is installed.
SOURCE = "私は日本語を勉強しています。"
SEGMENTS = (
    RubySegment("私", "わたし"),
    RubySegment("は", None),
    RubySegment("日本語", "にほんご"),
    RubySegment("を", None),
    RubySegment("勉強", "べんきょう"),
    RubySegment("しています。", None),
)
NOTATION = F.to_notation(SEGMENTS)

HAS_PROVIDER = pytest.mark.skipif(
    not F.is_available(),
    reason="requires a reading provider (fugashi or pykakasi)"
)


def plain(text):
    """One unannotated segment."""
    return (RubySegment(text, None),)


# --------------------------------------------------------------------------- #
# Wrap simulation - no display needed
# --------------------------------------------------------------------------- #
class TestLayoutRows:
    def test_single_short_line(self):
        assert R.layout_rows(plain("abc"), 100, FIXED) == RowCounts(1, 0, 1)

    def test_exact_fit_does_not_wrap(self):
        assert R.layout_rows(plain("a" * 10), 100, FIXED) == RowCounts(1, 0, 1)

    def test_one_char_too_many_wraps(self):
        assert R.layout_rows(plain("a" * 11), 100, FIXED) == RowCounts(2, 0, 1)

    def test_newline_starts_a_logical_line(self):
        counts = R.layout_rows(plain("ab\ncd"), 100, FIXED)
        assert counts == RowCounts(2, 0, 2)

    def test_trailing_newline_keeps_the_empty_row(self):
        counts = R.layout_rows(plain("ab\n"), 100, FIXED)
        assert counts == RowCounts(2, 0, 2)

    def test_blank_lines_are_counted(self):
        counts = R.layout_rows(plain("a\n\n\nb"), 100, FIXED)
        assert counts == RowCounts(4, 0, 4)

    def test_ruby_marks_its_row(self):
        segments = (RubySegment("私", "わたし"),) + plain("は")
        assert R.layout_rows(segments, 100, FIXED) == RowCounts(0, 1, 1)

    def test_ruby_wraps_and_both_rows_are_ruby(self):
        # Four 30px frames do not fit in 100px: 3 + 1.
        segments = tuple(RubySegment("字", "じ") for _ in range(4))
        assert R.layout_rows(segments, 100, FIXED) == RowCounts(0, 2, 1)

    def test_plain_row_after_a_ruby_row(self):
        segments = (RubySegment("字", "じ"),) + plain("\n" + "a" * 5)
        assert R.layout_rows(segments, 100, FIXED) == RowCounts(1, 1, 2)

    def test_atom_wider_than_the_line_gets_its_own_row(self):
        wide = LayoutModel(20, 40, 8, lambda ch: 500, lambda b, r: 500)
        # Three unbreakable atoms, each wider than the line: three rows, no hang.
        assert R.layout_rows(plain("abc"), 100, wide) == RowCounts(3, 0, 1)

    def test_empty_input_still_occupies_one_row(self):
        assert R.layout_rows((), 100, FIXED) == RowCounts(1, 0, 1)
        assert R.layout_rows(plain(""), 100, FIXED) == RowCounts(1, 0, 1)

    def test_degenerate_width_is_clamped(self):
        # A zero or negative width must not divide by zero or loop forever.
        for width in (0, -50):
            counts = R.layout_rows(plain("abcd"), width, FIXED)
            assert counts.plain_rows == 1
            assert counts.logical_lines == 1


class TestMeasurePx:
    def test_plain_line(self):
        assert R.measure_px(plain("abc"), 100, FIXED) == 20 + 8

    def test_ruby_line(self):
        assert R.measure_px((RubySegment("私", "わたし"),), 100, FIXED) == 40 + 8

    def test_line_spacing_charged_once_per_logical_line(self):
        # Two display rows from ONE logical line: spacing counted once. This is
        # the Tk behaviour (spacing2 sits between wrapped rows and is 0 here).
        segments = tuple(RubySegment("字", "じ") for _ in range(4))
        assert R.measure_px(segments, 100, FIXED) == 40 * 2 + 8

    def test_two_logical_lines_charge_spacing_twice(self):
        assert R.measure_px(plain("a\nb"), 100, FIXED) == (20 + 8) * 2

    def test_row_height_properties(self):
        assert FIXED.row_plain == 28
        assert FIXED.row_ruby == 48

    def test_fallback_layout_matches_measured_yu_gothic(self):
        # Measured on Tk 8.6 at Yu Gothic 11/7. The ruby row lost the base
        # descent when the baseline lift landed: the plain text on the row no
        # longer hangs below the baseline the frame sits on.
        assert R.FALLBACK_LAYOUT.row_plain == 28
        assert R.FALLBACK_LAYOUT.row_ruby == 42
        assert R.FALLBACK_LAYOUT.content_lifted == 26


class TestEstimateRubyOverheadPx:
    def test_nothing_to_annotate_costs_nothing(self):
        for text in ("", "hello world", "こんにちは", "你好世界", "12345"):
            assert R.estimate_ruby_overhead_px(text, 600, model=FIXED) == 0, text

    def test_over_budget_text_costs_nothing(self):
        long_text = "日本語です。" * 1000
        assert len(long_text) > R.MAX_ANNOTATE_CHARS
        assert R.estimate_ruby_overhead_px(long_text, 600, model=FIXED) == 0

    def test_kanji_only_needs_the_hint(self):
        assert R.estimate_ruby_overhead_px("電源設定", 600, model=FIXED) == 0

    @HAS_PROVIDER
    def test_japanese_costs_the_difference(self):
        # One logical line either way, so the overhead is exactly the extra
        # height of a ruby row over a plain row.
        overhead = R.estimate_ruby_overhead_px(SOURCE, 600, "Japanese",
                                               model=FIXED)
        assert overhead == FIXED.content_ruby - FIXED.content_plain

    @HAS_PROVIDER
    def test_never_negative(self):
        # A narrow width makes the plain text wrap a lot; the capped ruby height
        # can end up smaller, and a negative budget would shrink the window.
        assert R.estimate_ruby_overhead_px(SOURCE * 20, 60, "Japanese",
                                           max_rows=1, model=FIXED) == 0


class TestEstimateNotationPx:
    def test_empty_notation_costs_nothing(self):
        assert R.estimate_notation_px("", 600) == 0

    def test_single_pair(self):
        assert R.estimate_notation_px("{漢字|かんじ}", 600, model=FIXED) == 48

    def test_capped_at_max_rows(self):
        many = "{字|じ}" * 200
        assert R.estimate_notation_px(many, 100, max_rows=3, model=FIXED) == 3 * 48

    def test_escaped_braces_are_not_pairs(self):
        # A literal "{a|b}" must cost a plain row, not a ruby row.
        assert R.estimate_notation_px(r"\{a\|b\}", 600, model=FIXED) == 28


# --------------------------------------------------------------------------- #
# The widget - needs Tk
# --------------------------------------------------------------------------- #
@pytest.fixture
def holder(tk_root):
    """A fixed-size frame so wrap width is predictable."""
    frame = tk.Frame(tk_root, width=620, height=400)
    frame.pack_propagate(False)
    frame.pack()
    yield frame
    frame.destroy()


@pytest.fixture
def widget(holder):
    w = RubyText(holder)
    w.pack(fill=tk.BOTH, expand=True)
    yield w
    w.destroy()


@pytest.fixture
def mapped_widget(tk_root):
    """A RubyText in a real, visible Toplevel.

    `tk_root` is withdrawn, so nothing inside it is ever mapped and an embedded
    frame reports winfo_y() == 0 forever. Anything that measures where a ruby
    pair actually landed needs a window Tk has really laid out - the same reason
    TestSizing builds its own Toplevel.
    """
    top = tk.Toplevel(tk_root)
    top.geometry('620x400')
    w = RubyText(top, width=30, height=6)
    w.pack(fill=tk.BOTH, expand=True)
    yield w
    top.destroy()


class TestInsertion:
    def test_order_is_preserved_at_the_start_index(self, widget):
        # Regression: inserting run after run at a fixed '1.0' reverses the text.
        widget.insert_notation('1.0', NOTATION)
        assert widget.get_plain() == SOURCE

    def test_order_is_preserved_at_end(self, widget):
        widget.insert_notation(tk.END, NOTATION)
        assert widget.get_plain() == SOURCE

    def test_appending_twice_concatenates(self, widget):
        widget.insert_notation(tk.END, NOTATION)
        widget.insert_notation(tk.END, NOTATION)
        assert widget.get_plain() == SOURCE * 2

    def test_insert_into_the_middle(self, widget):
        widget.insert_plain(tk.END, "AB")
        widget.insert_notation('1.1', NOTATION)
        assert widget.get_plain() == "A" + SOURCE + "B"

    def test_pair_count(self, widget):
        widget.insert_notation(tk.END, NOTATION)
        assert widget.ruby_pairs == 3
        assert widget.has_ruby is True

    def test_plain_text_creates_no_frames(self, widget):
        widget.insert_ruby(tk.END, "hello world")
        assert widget.ruby_pairs == 0
        assert widget.has_ruby is False
        assert widget.get_plain() == "hello world"

    def test_kana_only_creates_no_frames(self, widget):
        widget.insert_ruby(tk.END, "こんにちは")
        assert widget.ruby_pairs == 0
        assert widget.get_plain() == "こんにちは"

    def test_over_budget_text_is_inserted_plain(self, widget):
        long_text = "日本語です。" * 1000
        assert len(long_text) > R.MAX_ANNOTATE_CHARS
        widget.insert_ruby(tk.END, long_text)
        assert widget.ruby_pairs == 0
        assert widget.get_plain() == long_text

    def test_empty_insert_is_a_noop(self, widget):
        widget.insert_ruby(tk.END, "")
        widget.insert_notation(tk.END, "")
        widget.insert_plain(tk.END, "")
        assert widget.get_plain() == ""
        assert widget.ruby_pairs == 0

    @HAS_PROVIDER
    def test_insert_ruby_annotates_japanese(self, widget):
        widget.insert_ruby(tk.END, SOURCE)
        assert widget.has_ruby is True
        assert widget.get_plain() == SOURCE

    @HAS_PROVIDER
    def test_kanji_only_needs_the_hint(self, widget):
        widget.insert_ruby(tk.END, "電源設定")
        assert widget.ruby_pairs == 0
        widget.clear()
        widget.insert_ruby(tk.END, "電源設定", lang_hint="Japanese")
        assert widget.has_ruby is True
        assert widget.get_plain() == "電源設定"

    def test_disabled_state_survives_insertion(self, widget):
        widget.config(state='disabled')
        widget.insert_notation(tk.END, NOTATION)
        assert str(widget.cget('state')) == 'disabled'
        assert widget.get_plain() == SOURCE

    def test_set_notation_replaces_content(self, widget):
        widget.insert_plain(tk.END, "old content")
        widget.set_notation(NOTATION)
        assert widget.get_plain() == SOURCE
        assert widget.ruby_pairs == 3

    def test_set_ruby_replaces_content(self, widget):
        widget.insert_plain(tk.END, "old content")
        widget.set_ruby("plain")
        assert widget.get_plain() == "plain"

    def test_set_plain_flattens_ruby(self, widget):
        widget.insert_notation(tk.END, NOTATION)
        widget.set_plain(widget.get_plain())
        assert widget.ruby_pairs == 0
        assert widget.has_ruby is False
        # The whole text must survive the flattening, kanji included.
        assert widget.get_plain() == SOURCE
        assert widget.get('1.0', 'end-1c') == SOURCE

    def test_kanji_fg_override_colours_the_base(self, widget):
        widget.insert_notation(tk.END, NOTATION, tags='mine', kanji_fg='#4ec9b0')
        for frame in widget._frames:
            _reading, base = frame.winfo_children()
            assert str(base.cget('fg')) == '#4ec9b0'

    def test_default_ruby_colours_survive_the_theme(self, widget):
        # ttkbootstrap re-themes standard tk widgets and discards explicit
        # colours unless autostyle=False; the reading must stay distinguishable.
        widget.insert_notation(tk.END, NOTATION)
        reading, base = widget._frames[0].winfo_children()
        assert str(reading.cget('fg')) == R.RUBY_FG
        assert str(base.cget('fg')) == R.KANJI_FG

    def test_a_ruby_pair_wears_the_widgets_background(self, widget):
        # No plate: an annotated word is ordinary text with a reading over it,
        # the way Word draws ruby - not a tinted chip on the line.
        widget.insert_notation(tk.END, NOTATION)
        frame = widget._frames[0]
        reading, base = frame.winfo_children()
        expected = str(widget.cget('bg'))
        assert str(frame.cget('bg')) == expected
        assert str(reading.cget('bg')) == expected
        assert str(base.cget('bg')) == expected

    def test_a_caller_can_still_ask_for_a_plate(self, tk_root):
        # The mechanism is kept: only the default changed.
        plated = R.RubyText(tk_root, ruby_bg=R.RUBY_BG)
        plated.insert_notation(tk.END, NOTATION)
        assert str(plated._frames[0].cget('bg')) == R.RUBY_BG
        plated.destroy()


class TestReadback:
    def test_get_drops_ruby_but_get_plain_does_not(self, widget):
        widget.insert_notation(tk.END, NOTATION)
        # Documents exactly why get_plain() exists: an embedded window
        # contributes no characters to get() while consuming an index.
        assert widget.get('1.0', 'end-1c') != SOURCE
        assert widget.get_plain() == SOURCE

    def test_escaped_notation_round_trips_as_literal_text(self, widget):
        source = "a{b|c}d 漢字です"
        widget.insert_notation(tk.END, F.to_notation(
            (RubySegment("a{b|c}d ", None), RubySegment("漢字", "かんじ"),
             RubySegment("です", None))))
        assert widget.get_plain() == source

    def test_newlines_are_preserved(self, widget):
        widget.insert_notation(tk.END, NOTATION + "\n" + NOTATION)
        assert widget.get_plain() == SOURCE + "\n" + SOURCE

    def test_range_readback(self, widget):
        widget.insert_plain(tk.END, "abcdef")
        assert widget.get_plain('1.2', '1.4') == "cd"

    def test_clear_removes_frames_and_text(self, widget):
        widget.insert_notation(tk.END, NOTATION)
        frames = list(widget._frames)
        widget.clear()
        widget.update_idletasks()
        assert widget.get_plain() == ""
        assert widget.ruby_pairs == 0
        assert not any(f.winfo_exists() for f in frames)


class TestSizing:
    def _measure(self, tk_root, notation, width=620, **widget_kwargs):
        """Render `notation` in a visible toplevel and return (predicted, real)."""
        top = tk.Toplevel(tk_root)
        top.geometry(f"{width + 40}x400+100+100")
        frame = tk.Frame(top, width=width, height=380)
        frame.pack_propagate(False)
        frame.pack()
        w = RubyText(frame, **widget_kwargs)
        w.insert_notation(tk.END, notation)
        w.config(state='disabled')
        predicted = w.required_px(width)
        w.fit_height(width)
        w.pack(fill=tk.BOTH, expand=True)
        top.update_idletasks()
        top.update()
        real = w.count('1.0', 'end', 'ypixels')
        real = real[0] if real else 0
        req = w.winfo_reqheight()
        top.destroy()
        return predicted, real, req

    def test_prediction_matches_real_pixels(self, tk_root):
        # Exact, not approximate: this is the check that caught the spacing bug.
        for notation in (NOTATION,
                         NOTATION + "\n" + NOTATION,
                         "plain latin line only",
                         NOTATION * 6):                      # forces a wrap
            predicted, real, _req = self._measure(tk_root, notation)
            if not real:
                pytest.skip("Tk reported no laid-out pixels (headless display)")
            assert predicted == real, f"notation={notation!r}"

    def test_prediction_follows_the_widgets_line_spacing(self, tk_root):
        # The popup and main-window boxes are built with spacing1/spacing3 = 0,
        # so a model hard-coded to this module's default would be off by 8px on
        # every logical line.
        for kwargs in ({'spacing1': 0, 'spacing3': 0},
                       {'spacing1': 6, 'spacing3': 2},
                       {'base_font': ('Segoe UI', 11), 'spacing1': 0,
                        'spacing3': 0, 'wrap': tk.WORD}):
            predicted, real, _req = self._measure(
                tk_root, NOTATION + "\n" + NOTATION, **kwargs)
            if not real:
                pytest.skip("Tk reported no laid-out pixels (headless display)")
            assert predicted == real, kwargs

    def test_fit_height_does_not_clip(self, tk_root):
        predicted, real, req = self._measure(tk_root, NOTATION * 4)
        if not real:
            pytest.skip("Tk reported no laid-out pixels (headless display)")
        assert req >= real

    def test_fit_height_returns_capped_pixels(self, widget):
        widget.insert_notation(tk.END, "{字|じ}" * 400)
        capped = widget.fit_height(620, max_rows=3)
        assert capped == 3 * widget.layout.row_ruby
        assert int(widget.cget('height')) >= 1

    def test_fit_height_always_leaves_at_least_one_row(self, widget):
        widget.fit_height(620)
        assert int(widget.cget('height')) >= 1

    def test_fit_height_respects_min_rows(self, widget):
        # The popup measures word wrap and passes its row count as the floor;
        # this class simulates character wrap and must not shrink below it.
        widget.insert_notation(tk.END, NOTATION)
        widget.fit_height(620, min_rows=9)
        assert int(widget.cget('height')) == 9

    def test_required_px_without_a_width_does_not_raise(self, widget):
        widget.insert_notation(tk.END, NOTATION)
        assert widget.required_px() > 0

    def test_tk_layout_model_derives_row_heights(self, tk_root):
        model = R.tk_layout_model()
        assert model.content_ruby > model.content_plain
        assert model.row_ruby == model.content_ruby + model.line_spacing
        assert model.char_width("あ") > 0
        assert model.ruby_width("漢字", "かんじ") > 0


class TestWheel:
    def test_ruby_children_are_bound(self, widget):
        widget.insert_notation(tk.END, NOTATION)
        frame = widget._frames[0]
        for child in (frame,) + tuple(frame.winfo_children()):
            assert child.bind('<MouseWheel>'), "ruby child would be a scroll dead zone"

    def test_wheel_over_ruby_scrolls_the_widget(self, tk_root):
        top = tk.Toplevel(tk_root)
        top.geometry("660x140+100+100")
        w = RubyText(top, height=2)
        w.insert_notation(tk.END, "{日本語|にほんご}です。" * 80)
        w.config(state='disabled')
        w.pack(fill=tk.BOTH, expand=True)
        top.update_idletasks()
        top.update()

        before = w.yview()[0]
        label = w._frames[2].winfo_children()[1]
        label.event_generate('<MouseWheel>', delta=-120, x=2, y=2)
        top.update_idletasks()
        after = w.yview()[0]
        top.destroy()

        if before == after == 0.0 and w.winfo_exists():
            pytest.skip("widget did not overflow, nothing to scroll")
        assert after > before


class TestCopySelection:
    """Ctrl+C over annotated text.

    The Copy *buttons* always went through `get_plain()`, so this never showed
    up there - but a hand-made selection goes through Tk's own <<Copy>>, which
    exports the selected characters, and an embedded window has none. Every word
    carrying a reading dropped silently out of the clipboard.
    """

    @staticmethod
    def _copy(widget, first, last):
        widget.tag_remove('sel', '1.0', 'end')
        widget.tag_add('sel', first, last)
        widget.focus_set()
        widget.clipboard_clear()
        widget.clipboard_append('@@untouched@@')
        widget.event_generate('<<Copy>>')
        widget.update()
        return widget.clipboard_get()

    def test_the_whole_selection_survives(self, widget):
        widget.insert_notation(tk.END, NOTATION)
        assert self._copy(widget, '1.0', 'end-1c') == SOURCE

    def test_tk_alone_would_have_dropped_the_annotated_words(self, widget):
        # The bug, pinned: what the default binding had to work with.
        widget.insert_notation(tk.END, NOTATION)
        assert widget.get('1.0', 'end-1c') != SOURCE
        for segment in SEGMENTS:
            if segment.ruby:
                assert segment.base not in widget.get('1.0', 'end-1c')

    def test_readings_are_not_copied(self, widget):
        widget.insert_notation(tk.END, NOTATION)
        copied = self._copy(widget, '1.0', 'end-1c')
        for segment in SEGMENTS:
            if segment.ruby:
                assert segment.ruby not in copied

    def test_a_partial_selection_copies_only_that_part(self, widget):
        widget.insert_notation(tk.END, NOTATION)
        copied = self._copy(widget, '1.0', '1.2')
        assert copied == widget.get_plain('1.0', '1.2')
        assert copied != SOURCE

    def test_one_annotated_word_on_its_own(self, widget):
        widget.insert_notation(tk.END, NOTATION)
        annotated = [seg for seg in SEGMENTS if seg.ruby]
        index = widget.index(widget._frames[0])
        assert self._copy(widget, index, index + ' +1c') == annotated[0].base

    def test_plain_text_is_unaffected(self, widget):
        widget.insert_plain(tk.END, "hello world")
        assert self._copy(widget, '1.0', 'end-1c') == "hello world"

    def test_no_selection_is_left_to_tk(self, widget):
        widget.insert_notation(tk.END, NOTATION)
        widget.tag_remove('sel', '1.0', 'end')
        assert widget._on_copy() is None

    def test_the_handler_stops_tk_from_overwriting_it(self, widget):
        # Returning 'break' is what keeps the default binding from replacing
        # the clipboard with the character-only version.
        widget.insert_notation(tk.END, NOTATION)
        widget.tag_add('sel', '1.0', 'end-1c')
        assert widget._on_copy() == 'break'


class TestBaselineAlignment:
    """Annotated words must sit on the same line as the text around them.

    `align='baseline'` puts the *bottom of the frame* on the line's baseline, so
    the base characters inside end up a descent above it - 6px with Yu Gothic 11,
    measured, and clearly visible as text that does not line up. RubyText raises
    the plain runs of that line by the same amount.
    """

    @staticmethod
    def _baselines(widget):
        widget.update_idletasks()
        widget.update()
        if widget._frames and not widget._frames[0].winfo_ismapped():
            pytest.skip("Tk never mapped the embedded frames (headless display)")
        metrics = tkfont.Font(family=widget.base_font[0], size=widget.base_font[1])
        ascent = metrics.metrics('ascent')
        # The reference must be a real character: index '1.0' is an embedded
        # window whenever the text opens on an annotated word, and its bbox
        # describes the frame, not the text baseline.
        first_text = next((index for kind, _v, index
                           in widget.dump('1.0', 'end', text=True)
                           if kind == 'text'), None)
        plain = widget.bbox(first_text) if first_text else None
        if plain is None:
            pytest.skip("Tk laid out nothing (headless display)")
        return (plain[1] + ascent,
                [frame.winfo_y() + frame.winfo_children()[1].winfo_y() + ascent
                 for frame in widget._frames])

    def test_every_annotated_word_shares_the_plain_baseline(self, mapped_widget):
        mapped_widget.insert_notation(tk.END, NOTATION)
        plain_baseline, ruby_baselines = self._baselines(mapped_widget)
        assert ruby_baselines, "no ruby frames to check"
        for baseline in ruby_baselines:
            assert baseline == plain_baseline

    def test_the_lift_is_the_descent_plus_the_frame_padding(self, widget):
        metrics = tkfont.Font(family=widget.base_font[0], size=widget.base_font[1])
        assert widget.layout.lift == metrics.metrics('descent') + R.RUBY_PAD_Y

    def test_only_lines_carrying_ruby_are_lifted(self, widget):
        widget.insert_notation(tk.END, NOTATION + "\n")
        widget.insert_plain(tk.END, "plain second line")
        ranges = [str(i) for i in widget.tag_ranges(widget.LIFT_TAG)]
        assert ranges, "the annotated line was never lifted"
        assert all(index.startswith('1.') or index.startswith('2.0')
                   for index in ranges), ranges

    def test_plain_text_added_after_the_ruby_is_lifted_too(self, widget):
        # The dictionary window builds a line one run at a time; a Tk tag does
        # not grow into text inserted after its range, so the lift is re-applied.
        widget.insert_notation(tk.END, NOTATION)
        widget.insert_plain(tk.END, "tail")
        _first, last = widget.tag_ranges(widget.LIFT_TAG)[:2]
        assert widget.compare(last, '>=', 'end-1c')

    def test_a_widget_with_no_ruby_is_never_lifted(self, widget):
        widget.insert_plain(tk.END, "nothing japanese here")
        assert widget.tag_ranges(widget.LIFT_TAG) == ()

    def test_clearing_forgets_the_lifted_lines(self, widget):
        widget.insert_notation(tk.END, NOTATION)
        widget.clear()
        assert widget._lifted_lines == set()
        assert widget.tag_ranges(widget.LIFT_TAG) == ()


class TestWordLikeRhythm:
    def test_an_annotated_word_is_no_wider_than_its_characters(self, mapped_widget):
        # RUBY_PAD_X = 0: a word with a reading takes exactly the room its
        # characters take, so the line keeps an even rhythm. Only a reading
        # wider than its base widens the word, which is what Word does too.
        mapped_widget.insert_notation(tk.END, NOTATION)
        mapped_widget.update_idletasks()
        mapped_widget.update()
        metrics = tkfont.Font(family=mapped_widget.base_font[0],
                              size=mapped_widget.base_font[1])
        for frame in mapped_widget._frames:
            reading, base = frame.winfo_children()
            if frame.winfo_width() <= 1:
                pytest.skip("Tk laid out nothing (headless display)")
            natural = metrics.measure(base.cget('text'))
            assert frame.winfo_width() >= natural
            if metrics.measure(reading.cget('text')) <= natural:
                assert frame.winfo_width() == natural

    def test_the_model_charges_no_padding(self):
        assert R.RUBY_PAD_X == 0
        model = R.tk_layout_model()
        assert model.ruby_width("x", "y") == max(model.char_width("x"),
                                                 model.char_width("y"))
