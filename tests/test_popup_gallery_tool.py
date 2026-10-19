"""
Tests for P0 of the quick-translate popup work (TODO.md): the shared corpus
(tests/popup_cases.py) and the gallery tool (tools/popup_gallery.py).

The tool must never draw on the user's screen nor touch their settings, the corpus
must describe the cases TODO.md §4 measured, and the metrics must be read the way
§4 defines them.
"""
import os
import re
import shutil
import sys

import pytest

_APPDATA_BEFORE_IMPORT = os.environ.get('APPDATA')

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'tools'))
import popup_gallery as tool  # noqa: E402
import popup_cases as cases  # noqa: E402

# Letters only Vietnamese writes: the project allows no Vietnamese in code.
VIETNAMESE = re.compile('[\u1ea0-\u1ef9\u0110\u0111\u01a0\u01a1\u01af\u01b0]')


class TestSafety:
    def test_it_refuses_to_run_without_a_private_desktop(self):
        with pytest.raises(SystemExit, match="refusing to draw on the screen"):
            tool.require_private_desktop(None, "CreateDesktopW failed")

    def test_on_the_private_desktop_it_carries_on(self):
        assert tool.require_private_desktop('crosstrans-tests-1', None) is None

    def test_importing_it_changes_nothing(self):
        # All of its work - the desktop, the settings folder, the windows - is in main().
        assert os.environ.get('APPDATA') == _APPDATA_BEFORE_IMPORT

    def test_settings_go_to_a_scratch_folder(self, monkeypatch):
        monkeypatch.setenv('APPDATA', r'C:\Users\someone\AppData\Roaming')
        scratch = tool.isolate_settings()
        try:
            assert os.environ['APPDATA'] == scratch
            assert os.path.isdir(scratch) and 'popup-gallery-' in os.path.basename(scratch)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


class FakeBox:
    """A Text widget as far as box_metrics() asks: 100x64 with a 1 px border, a 1 px
    highlight and 1 px of padding, holding content that needs `needed` pixels."""

    def __init__(self, needed, lines=2):
        self.needed, self.lines = needed, lines

    def winfo_height(self):
        return 64

    def winfo_width(self):
        return 100

    def cget(self, option):
        return {'pady': 1, 'padx': 1, 'borderwidth': 1, 'highlightthickness': 1}[option]

    def count(self, start, end, *options):
        if 'ypixels' in options:
            return (self.needed,)
        return (self.lines - 1,)


class TestMetrics:
    def test_a_box_with_room_to_spare_reports_the_blank(self):
        box = tool.box_metrics(FakeBox(needed=40), "short", measure=len)
        assert (box['given'], box['needed'], box['blank'], box['hidden']) == (58, 40, 18, 0)

    def test_a_box_too_small_reports_what_is_hidden(self):
        box = tool.box_metrics(FakeBox(needed=90), "long", measure=len)
        assert (box['blank'], box['hidden']) == (0, 32)

    def test_the_widest_line_is_capped_at_the_box(self):
        box = tool.box_metrics(FakeBox(needed=40), "x" * 500, measure=len)
        assert box['widest_line'] == box['width'] == 94

    def test_count_results_of_every_shape_are_read(self):
        # Text.count() returns a tuple, a bare int or None depending on the Tk build.
        assert [tool._first(v) for v in ((7,), 7, None)] == [7, 7, 0]

    def test_chars_per_line_is_the_worst_paragraph(self):
        # An unwrapped line counts whole (B: one 83-character line is over WCAG's 80 too);
        # a wrapped one counts per display line.
        class Wrapped:
            rows = {1: 1, 2: 2}                 # logical line -> display lines

            def count(self, start, end, *options):
                return (self.rows[int(start.split('.')[0])] - 1,)

        assert tool.chars_per_line(Wrapped(), "aaaaaa\nbbbbbbbbbb") == 6.0
        Wrapped.rows = {1: 1, 2: 1}
        assert tool.chars_per_line(Wrapped(), "aaaaaa\nbbbbbbbbbb") == 10.0

    @pytest.mark.parametrize('text, width, cut', [
        ("Get Free API Key", 14, True),         # the trial line's link, 2026-10-19
        ("API Settings", 14, False),
        ("✕", 3, False),
        ("Copy", 0, False),                     # no width set: sized to its text
    ])
    def test_a_text_longer_than_its_widget_is_cut(self, text, width, cut):
        class Button:
            def cget(self, option):
                return {'text': text, 'width': width}[option]

        assert tool.too_narrow_for_its_text(Button()) is cut

    def test_ruby_frames_inside_a_text_are_not_layout(self):
        # A ruby label scrolled out of view is unmapped; that is content, not a control
        # cut off at the popup's edge (seen on case G before this was excluded).
        class Node:
            def __init__(self, cls, *children):
                self.cls, self.children = cls, children

            def winfo_class(self):
                return self.cls

            def winfo_children(self):
                return self.children

        label = Node('Label')
        popup = Node('Toplevel', Node('Frame', Node('Text', Node('Frame', label))),
                     Node('Button'))
        assert label in list(tool.descendants(popup))
        assert label not in list(tool.descendants(popup, into_text=False))
        assert [n.cls for n in tool.descendants(popup, into_text=False)] == \
            ['Frame', 'Text', 'Button']


class TestCorpus:
    def test_the_thirteen_measured_cases_are_there(self):
        assert [c.key for c in cases.CASES] == list("ABCDEFGHIJKLM")

    def test_keys_are_unique_and_states_known(self):
        keys = [c.key for c in cases.ALL_CASES]
        assert len(keys) == len(set(keys))
        assert {c.state for c in cases.ALL_CASES} <= set(cases.STATES)
        assert {c.state for c in cases.STATE_CASES} == {cases.GRAMMAR, cases.REPLACE_PREVIEW,
                                                       cases.CUSTOM_PROMPT}

    def test_every_case_has_text(self):
        for c in cases.ALL_CASES:
            assert c.original.strip() and c.translated.strip() and c.target, c.key

    def test_the_error_case_is_one_the_popup_treats_as_an_error(self):
        from src.ui.quick_translate import is_error_text
        assert is_error_text(cases.case('K').translated)
        assert not any(is_error_text(c.translated) for c in cases.ALL_CASES if c.key != 'K')

    def test_japanese_sources_carry_kana_so_they_get_readings(self):
        for c in cases.ALL_CASES:
            if c.source == 'Japanese':
                assert re.search('[\u3040-\u30ff]', c.original), c.key

    def test_the_corpus_holds_no_vietnamese(self):
        for c in cases.ALL_CASES:
            for value in (c.original, c.translated, c.target, c.name):
                assert not VIETNAMESE.search(value), c.key


class TestOnARealPopup:
    """The tool's measurements on a real popup, on the private desktop."""

    @pytest.fixture
    def manager(self, tk_root):
        from src.ui.quick_translate import QuickTranslateManager
        mgr = QuickTranslateManager(tk_root, cases.FakeConfig())
        mgr._last_mouse_x, mgr._last_mouse_y = 500, 300
        yield mgr
        mgr.close()

    def test_a_case_is_rendered_and_measured(self, manager, tk_root):
        cases.show_case(manager, cases.case('C'))
        tk_root.update_idletasks()
        tk_root.update()
        row = tool.popup_metrics(manager, cases.case('C'), measure=len)
        assert row['key'] == 'C' and row['size'][0] > 0 and row['size'][1] > 0
        assert row['translation']['needed'] > 0 and row['translation']['lines'] >= 2
        assert row['close_button']['found']
        assert 0 < row['text_covers_pct'] <= 100

    def test_the_readings_block_is_measured_when_there_is_one(self, manager, tk_root):
        cases.show_case(manager, cases.case('E'))
        tk_root.update_idletasks()
        tk_root.update()
        row = tool.popup_metrics(manager, cases.case('E'), measure=len)
        assert 'original' in row and row['original']['needed'] > 0
