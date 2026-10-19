"""
Geometry of the quick-translate popup, on the real widgets (TODO.md; Decision 34).

Every case and state of tests/popup_cases.py is put up through the real
QuickTranslateManager on the private desktop (Decision 32) and measured with the
gallery tool's own functions (tools/popup_gallery.py), so a number in TODO.md, an
image in the gallery and an assertion here are the same measurement.
"""
import ctypes
import dataclasses
import os
import statistics
import sys
import time
import tkinter as tk
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'tools'))
import popup_gallery as gallery  # noqa: E402
import popup_cases as cases  # noqa: E402
from src.constants import POPUP_COLLAPSED_ORIGINAL_ROWS  # noqa: E402
from src.core import furigana  # noqa: E402
from src.ui import popup_layout, quick_translate  # noqa: E402
from src.ui.quick_translate import QuickTranslateManager  # noqa: E402

EVERY_CASE = pytest.mark.parametrize('case', cases.ALL_CASES, ids=lambda c: c.key)


@pytest.fixture
def manager(tk_root):
    mgr = QuickTranslateManager(tk_root, cases.FakeConfig())
    mgr._last_mouse_x, mgr._last_mouse_y = 500, 300
    yield mgr
    mgr.close()


def settle(manager, tk_root, timeout=2.0):
    """Run the event loop until the popup has been measured and shown."""
    tk_root.update_idletasks()
    tk_root.update()
    deadline = time.perf_counter() + timeout
    while (manager.popup is not None and manager._layout is not None
           and not manager._layout.get('revealed') and time.perf_counter() < deadline):
        time.sleep(0.005)
        tk_root.update()


def put_up(manager, tk_root, case):
    furigana.clear_cache()
    cases.show_case(manager, case)
    settle(manager, tk_root)


def alpha(manager):
    return float(manager.popup.attributes('-alpha'))


def needs_icons(manager):
    if manager._icon_family() is None:
        pytest.skip("no icon font on this system: the words come back, the bar is wide")


# --------------------------------------------------------------------------- #
# P1 - the close button and nothing cut off (TODO.md S1, S2)
# --------------------------------------------------------------------------- #
class TestCloseButton:
    """The bar needed 735 px, the popup was 670, and the close button, packed last,
    was the one squeezed out on every short result."""

    @EVERY_CASE
    def test_the_close_button_is_drawn_inside_the_popup(self, manager, tk_root, case):
        put_up(manager, tk_root, case)
        close = gallery.close_button_metrics(manager.popup)
        assert close == {'found': True, 'shown': True, 'full_width': True, 'inside': True}, (
            f"{case.key} ({case.name}): popup {manager.popup.winfo_width()} px wide, "
            f"close button {close}")

    def test_it_is_in_the_header_beside_the_credit(self, manager, tk_root):
        put_up(manager, tk_root, cases.case('A'))
        assert manager.popup_attribution.master is manager.popup_close_btn.master

    def test_a_long_credit_is_cut_and_the_button_stays(self, manager, tk_root):
        long_model = ("an-extremely-long-model-name-" * 6) + " (Provider)"
        put_up(manager, tk_root, dataclasses.replace(cases.case('A'), model=long_model))
        assert manager.popup_attribution.cget('text').endswith(popup_layout.ELLIPSIS)
        assert gallery.close_button_metrics(manager.popup)['inside']


class TestNothingIsCutOff:
    """No button or label squeezed, cut at the edge, or given fewer characters than its
    text ("Get Free API Key" in a 14-character button)."""

    @EVERY_CASE
    def test_no_button_or_label_is_cut_off(self, manager, tk_root, case):
        put_up(manager, tk_root, case)
        assert gallery.clipped_controls(manager.popup) == [], (
            f"{case.key} ({case.name}): popup {manager.popup.winfo_width()} px wide")


class TestRowWidth:
    """The width a row of buttons needs is read off the buttons, before anything is
    shown - so the popup can be made wide enough without mapping it first (which would
    flash it at the wrong place) and without a constant that drifts."""

    def test_it_is_known_before_the_window_is_shown(self, tk_root):
        top = tk.Toplevel(tk_root)
        top.withdraw()
        try:
            row = tk.Frame(top)
            row.pack(fill='x')
            for text, padx in (("Copy", 0), ("Replace", (4, 0)), ("Open Translator", 4)):
                tk.Button(row, text=text, padx=12).pack(side='left', padx=padx)
            tk.Button(row, text="x", width=3).pack(side='right')
            before = quick_translate.packed_row_width(row)
            tk_root.update_idletasks()
            assert before == row.winfo_reqwidth()
        finally:
            top.destroy()

    def test_padding_on_one_side_counts_once(self, tk_root):
        top = tk.Toplevel(tk_root)
        top.withdraw()
        try:
            one, two = tk.Frame(top), tk.Frame(top)
            tk.Button(one, text="Replace").pack(side='left', padx=(4, 0))
            tk.Button(two, text="Replace").pack(side='left', padx=4)
            assert quick_translate.packed_row_width(two) - quick_translate.packed_row_width(one) == 4
        finally:
            top.destroy()


# --------------------------------------------------------------------------- #
# P2 - measured, readable, capped, beside the cursor (DoD2, DoD3, DoD5, DoD6, DoD7)
# --------------------------------------------------------------------------- #
class TestBoxesFitTheirContent:
    """Every box exactly as tall as its content up to the cap; what does not fit is
    reachable through a scrollbar that is there to see (TODO.md S4, S6)."""

    @EVERY_CASE
    def test_no_blank_band_and_nothing_hidden_without_a_scrollbar(self, manager, tk_root,
                                                                   case):
        put_up(manager, tk_root, case)
        boxes = [(manager.popup_text, manager._text_scrollbar)]
        if manager.popup_furigana is not None:
            boxes.append((manager.popup_furigana, manager._original_scrollbar))
        for box, scrollbar in boxes:
            metrics = gallery.box_metrics(box, box.get_plain(), measure=len)
            assert metrics['blank'] <= 2, (case.key, metrics)
            if metrics['hidden']:
                assert scrollbar.winfo_ismapped(), (case.key, metrics)


class TestReadableLines:
    """About 70 characters a line for Latin text, 36 for CJK - WCAG 1.4.8 asks for at
    most 80 / 40 (TODO.md S5)."""

    @pytest.mark.parametrize('key', ['B', 'C', 'D', 'F', 'G'])
    def test_latin_lines_stay_within_seventy_five_characters(self, manager, tk_root, key):
        put_up(manager, tk_root, cases.case(key))
        box = manager.popup_text
        assert gallery.chars_per_line(box, box.get_plain()) <= 75

    def test_cjk_lines_stay_within_forty(self, manager, tk_root):
        put_up(manager, tk_root, cases.case('M'))
        box = manager.popup_text
        assert gallery.chars_per_line(box, box.get_plain()) <= 40


class TestShortResultsAreSmall:
    """A short result is no longer held at 735 px by the bar (TODO.md S3, DoD4)."""

    @pytest.mark.parametrize('key', ['A', 'E'])
    def test_a_short_result_gets_a_small_popup(self, manager, tk_root, key):
        needs_icons(manager)
        put_up(manager, tk_root, cases.case(key))
        assert manager.popup.winfo_width() <= 420


class TestHeightAndPlace:
    """At most the cap, inside the work area, never over the cursor (TODO.md S6)."""

    @EVERY_CASE
    def test_within_the_cap_and_the_screen_and_off_the_cursor(self, manager, tk_root, case):
        put_up(manager, tk_root, case)
        popup, layout = manager.popup, manager._layout
        x, y = popup.winfo_x(), popup.winfo_y()
        width, height = popup.winfo_width(), popup.winfo_height()
        work = layout['work']
        assert height <= layout['cap']
        assert work.left <= x and x + width <= work.right
        assert work.top <= y and y + height <= work.bottom
        assert not popup_layout.covers(x, y, width, height, manager._anchor())

    def test_at_the_bottom_right_corner_it_opens_up_and_left(self, manager, tk_root):
        work = manager._work_area()
        manager._last_mouse_x, manager._last_mouse_y = work.right - 20, work.bottom - 20
        put_up(manager, tk_root, cases.case('C'))
        popup = manager.popup
        assert popup.winfo_x() + popup.winfo_width() <= manager._last_mouse_x
        assert popup.winfo_y() + popup.winfo_height() <= manager._last_mouse_y


class TestShownOnlyOnceMeasured:
    """Built at alpha 0 and shown when measured: no flash, no jump - and always shown
    in the end (TODO.md §5.2, DoD6)."""

    def test_it_is_invisible_until_measured(self, manager, tk_root):
        cases.show_case(manager, cases.case('C'))
        assert alpha(manager) == 0.0 and not manager._layout['done']
        settle(manager, tk_root)
        assert manager._layout['done'] and alpha(manager) == 1.0

    def test_it_is_shown_only_after_its_final_size_is_drawn(self, manager, tk_root):
        cases.show_case(manager, cases.case('A'))
        tk_root.update_idletasks()
        tk_root.update()
        assert manager._layout['done'] and alpha(manager) == 0.0     # measured, not yet seen
        settle(manager, tk_root)
        assert alpha(manager) == 1.0

    def test_a_failure_while_measuring_still_shows_it(self, manager, tk_root, monkeypatch):
        def broken(*args, **kwargs):
            raise RuntimeError("measuring broke")
        monkeypatch.setattr(manager, '_fit_boxes', broken)
        cases.show_case(manager, cases.case('C'))
        settle(manager, tk_root)
        assert alpha(manager) == 1.0

    def test_the_watchdog_shows_a_popup_never_laid_out(self, manager, tk_root):
        cases.show_case(manager, cases.case('A'))
        manager._finish_layout(manager._generation, forced=True)
        assert alpha(manager) == 1.0

    def test_a_closed_popup_ignores_its_late_watchdog(self, manager, tk_root):
        cases.show_case(manager, cases.case('C'))
        generation = manager._generation
        manager.close()
        tk_root.update()
        manager._finish_layout(generation, forced=True)
        assert manager.popup is None

    def test_a_newer_popup_ignores_the_older_ones_step_two(self, manager, tk_root):
        cases.show_case(manager, cases.case('C'))
        older = manager._generation
        cases.show_case(manager, cases.case('A'))
        manager._finish_layout(older, forced=True)
        assert not manager._layout['done']
        settle(manager, tk_root)
        assert manager._layout['done'] and manager._layout['revealed']

    def test_measuring_is_quick(self, manager, tk_root):
        # Measured 2-8 ms on this case (TODO.md S9); the bound only catches a box
        # measured before it has its width (wrapped a character per line).
        put_up(manager, tk_root, cases.case('C'))
        started = time.perf_counter()
        manager._fit_boxes(reposition=False)
        assert time.perf_counter() - started < 0.5


# --------------------------------------------------------------------------- #
# P3 - the layout (C)
# --------------------------------------------------------------------------- #
class TestActionBar:
    """Copy and Replace as words, the rest as icons with a tooltip (TODO.md Q1 (c))."""

    def test_two_words_and_four_named_icons(self, manager, tk_root):
        needs_icons(manager)
        put_up(manager, tk_root, cases.case('B'))
        assert manager.popup_copy_btn.cget('text') == "Copy"
        assert manager.popup_replace_btn.cget('text') == "Replace"
        family = manager._icon_family()
        for button, name in ((manager.popup_retranslate_btn, "Re-translate"),
                             (manager.popup_dict_btn, "Dictionary"),
                             (manager.popup_open_btn, "Open Translator"),
                             (manager.popup_custom_prompt_btn, "Custom Prompt")):
            assert button.action_name == name
            assert family in str(button.cget('font'))

    def test_a_tooltip_names_the_icon(self, manager, tk_root):
        needs_icons(manager)
        put_up(manager, tk_root, cases.case('B'))
        tip = next(t for t in manager._tooltips if t.widget is manager.popup_open_btn)
        tip.show()
        tk_root.update()
        assert tip.window is not None and tip.window.winfo_exists()
        assert tip.window.winfo_children()[0].cget('text') == "Open Translator"
        tip.hide()
        assert tip.window is None

    def test_a_tooltip_never_takes_the_focus(self, manager, tk_root):
        needs_icons(manager)
        put_up(manager, tk_root, cases.case('B'))
        tip = manager._tooltips[0]
        tip.show()
        tk_root.update()
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(tip.window.winfo_id()) or tip.window.winfo_id()
        assert user32.GetWindowLongW(hwnd, quick_translate.GWL_EXSTYLE) & \
            quick_translate.WS_EX_NOACTIVATE
        tip.hide()

    def test_the_dictionary_icon_keeps_its_tooltip(self, manager, tk_root):
        # _update_dict_button_state() unbinds <Enter>; the tooltip is attached after it.
        needs_icons(manager)
        put_up(manager, tk_root, cases.case('B'))
        assert any(t.widget is manager.popup_dict_btn for t in manager._tooltips)
        assert manager.popup_dict_btn.bind('<Enter>')

    def test_a_grammar_fix_keeps_copy_replace_and_open(self, manager, tk_root):
        put_up(manager, tk_root, cases.case('B-grammar'))
        assert manager.popup_open_btn is not None and manager.popup_copy_btn is not None
        assert manager.popup_retranslate_btn is None
        assert manager.popup_dict_btn is None and manager.popup_custom_prompt_btn is None

    def test_without_an_icon_font_the_words_come_back(self, manager, tk_root):
        manager._icon_family_cache = (None,)
        put_up(manager, tk_root, cases.case('B'))
        assert manager.popup_open_btn.cget('text') == "Open Translator"
        assert manager.popup_open_btn.action_name == "Open Translator"
        assert gallery.close_button_metrics(manager.popup)['inside']

    def test_the_icon_font_is_the_first_one_installed(self):
        pick = quick_translate.icon_font_family
        assert pick(['Arial', 'Segoe MDL2 Assets']) == 'Segoe MDL2 Assets'
        assert pick(['Segoe MDL2 Assets', 'Segoe Fluent Icons']) == 'Segoe Fluent Icons'
        assert pick(['Arial']) is None


class TestOriginalBlock:
    """The original with its readings: named, and collapsed to three rows when longer
    (TODO.md Q5)."""

    def test_a_long_original_starts_collapsed(self, manager, tk_root):
        put_up(manager, tk_root, cases.case('G'))
        toggle = manager.popup_original_toggle
        assert toggle.winfo_ismapped() and toggle.cget('text') == "Show all"
        rows = manager._rows_px(manager.popup_furigana, POPUP_COLLAPSED_ORIGINAL_ROWS)
        assert gallery.content_box(manager.popup_furigana, 'y') == rows

    def test_show_all_opens_it_within_the_cap(self, manager, tk_root):
        put_up(manager, tk_root, cases.case('G'))
        before = manager.popup_furigana.winfo_height()
        manager._toggle_original()
        tk_root.update()
        assert manager.popup_original_toggle.cget('text') == "Show less"
        assert manager.popup_furigana.winfo_height() > before
        assert manager.popup.winfo_height() <= manager._layout['cap']

    def test_a_short_original_has_no_toggle(self, manager, tk_root):
        put_up(manager, tk_root, cases.case('E'))
        assert not manager.popup_original_toggle.winfo_ismapped()

    def test_it_is_named(self, manager, tk_root):
        put_up(manager, tk_root, cases.case('E'))
        names = [w.cget('text') for w in manager._original_header.winfo_children()]
        assert "Original (Japanese)" in names


# --------------------------------------------------------------------------- #
# P4 - a size the user chooses (TODO.md Q6)
# --------------------------------------------------------------------------- #
class SizeConfig(cases.FakeConfig):
    def __init__(self):
        self.saved = (None, None)

    def get_quick_popup_size(self):
        return self.saved

    def set_quick_popup_size(self, width, height):
        self.saved = (width, height)


@pytest.fixture
def sized(tk_root):
    config = SizeConfig()
    mgr = QuickTranslateManager(tk_root, config)
    mgr._last_mouse_x, mgr._last_mouse_y = 500, 300
    yield mgr, config
    mgr.close()


class TestGrip:
    def test_dragging_the_grip_resizes_and_is_remembered(self, sized, tk_root):
        mgr, config = sized
        put_up(mgr, tk_root, cases.case('C'))
        width, height = mgr.popup.winfo_width(), mgr.popup.winfo_height()
        mgr._grip_press(SimpleNamespace(x_root=100, y_root=100))
        mgr._grip_drag(SimpleNamespace(x_root=180, y_root=160))
        mgr._grip_release()
        tk_root.update()
        assert (mgr.popup.winfo_width(), mgr.popup.winfo_height()) == (width + 80, height + 60)
        assert config.saved == (width + 80, height + 60)
        assert mgr._grip_outline is None

    def test_the_next_popup_reads_at_the_remembered_width(self, sized, tk_root):
        mgr, config = sized
        config.saved = (480, 300)
        put_up(mgr, tk_root, cases.case('D'))
        assert mgr._layout['width'] == 480
        assert mgr.popup.winfo_height() <= 300

    def test_a_short_result_stays_small_whatever_was_remembered(self, sized, tk_root):
        mgr, config = sized
        config.saved = (900, 700)
        put_up(mgr, tk_root, cases.case('A'))
        assert mgr.popup.winfo_width() < 900

    def test_a_double_click_returns_to_automatic(self, sized, tk_root):
        mgr, config = sized
        config.saved = (480, 300)
        put_up(mgr, tk_root, cases.case('D'))
        mgr._grip_reset()
        tk_root.update()
        assert config.saved == (None, None)
        assert mgr._layout['cap'] == popup_layout.height_cap(mgr._layout['work'])


def grip_drag(mgr, dx, dy):
    """One motion of a drag that started at (100, 100)."""
    mgr._grip_drag(SimpleNamespace(x_root=100 + dx, y_root=100 + dy))


def run_until(tk_root, done, timeout=2.0):
    deadline = time.perf_counter() + timeout
    while not done() and time.perf_counter() < deadline:
        time.sleep(0.005)
        tk_root.update()


class TestGripDragsAnOutline:
    """A drag moves an outline; the popup is laid out when the drag pauses and on
    release (Decision 35). Laid out on every motion it cost 14-190 ms a step, and a
    long text followed the mouse at a few frames a second."""

    @pytest.fixture
    def no_pause(self, monkeypatch):
        # No pause preview inside these tests, however slow the runner.
        monkeypatch.setattr(quick_translate, 'POPUP_GRIP_PREVIEW_MS', 60_000)

    @pytest.fixture
    def layouts(self, sized, monkeypatch):
        """Every time the popup is laid out at the user's size."""
        mgr, _ = sized
        calls = []
        fit = mgr._fit_boxes

        def counted(*args, **kwargs):
            calls.append(kwargs.get('size'))
            return fit(*args, **kwargs)

        monkeypatch.setattr(mgr, '_fit_boxes', counted)
        return calls

    def test_while_dragging_only_the_outline_moves(self, sized, tk_root, no_pause):
        mgr, config = sized
        put_up(mgr, tk_root, cases.case('C'))
        width, height = mgr.popup.winfo_width(), mgr.popup.winfo_height()
        mgr._grip_press(SimpleNamespace(x_root=100, y_root=100))
        grip_drag(mgr, 80, 60)
        tk_root.update()
        outline = mgr._grip_outline
        assert (mgr.popup.winfo_width(), mgr.popup.winfo_height()) == (width, height)
        assert outline is not None and outline.winfo_ismapped()
        assert (outline.winfo_x(), outline.winfo_y()) == (mgr.popup.winfo_x(),
                                                          mgr.popup.winfo_y())
        assert (outline.winfo_width(), outline.winfo_height()) == (width + 80, height + 60)
        assert config.saved == (None, None)
        mgr._grip_release()

    def test_no_motion_lays_the_popup_out_the_release_does(self, sized, tk_root, no_pause,
                                                           layouts):
        mgr, _ = sized
        put_up(mgr, tk_root, cases.case('G'))
        layouts.clear()
        mgr._grip_press(SimpleNamespace(x_root=100, y_root=100))
        for step in range(1, 21):
            grip_drag(mgr, 4 * step, 3 * step)
            tk_root.update()
        assert layouts == []
        mgr._grip_release()
        assert layouts == [mgr._user_size]

    def test_a_pause_shows_the_popup_at_the_outlines_size(self, sized, tk_root, monkeypatch,
                                                          layouts):
        monkeypatch.setattr(quick_translate, 'POPUP_GRIP_PREVIEW_MS', 20)
        mgr, config = sized
        put_up(mgr, tk_root, cases.case('C'))
        target = (mgr.popup.winfo_width() + 80, mgr.popup.winfo_height() + 60)
        mgr._grip_press(SimpleNamespace(x_root=100, y_root=100))
        grip_drag(mgr, 80, 60)
        run_until(tk_root, lambda: (mgr.popup.winfo_width(), mgr.popup.winfo_height()) == target)
        assert (mgr.popup.winfo_width(), mgr.popup.winfo_height()) == target
        assert mgr._grip_outline is not None        # the button is still held
        assert config.saved == (None, None)         # remembered on release only
        layouts.clear()
        mgr._grip_release()
        assert layouts == []                        # already laid out at that size
        assert config.saved == target
        assert mgr._grip_outline is None

    def test_the_preview_waits_for_the_motion_to_stop(self, sized, tk_root, monkeypatch,
                                                      layouts):
        monkeypatch.setattr(quick_translate, 'POPUP_GRIP_PREVIEW_MS', 100)
        mgr, _ = sized
        put_up(mgr, tk_root, cases.case('C'))
        layouts.clear()
        mgr._grip_press(SimpleNamespace(x_root=100, y_root=100))
        end, step = time.perf_counter() + 0.4, 0
        while time.perf_counter() < end:        # moving all along, for four pauses' time
            step += 1
            grip_drag(mgr, step, step)
            tk_root.update()
            time.sleep(0.005)
        assert layouts == []
        run_until(tk_root, lambda: layouts)     # then still: one preview
        assert layouts == [mgr._user_size]
        mgr._grip_release()

    def test_the_outline_is_a_frame_the_popup_shows_through(self, sized, tk_root, no_pause):
        mgr, _ = sized
        put_up(mgr, tk_root, cases.case('C'))
        mgr._grip_press(SimpleNamespace(x_root=100, y_root=100))
        grip_drag(mgr, 40, 30)
        tk_root.update()
        outline = mgr._grip_outline
        assert str(outline.attributes('-transparentcolor')) == str(outline.cget('bg'))
        assert int(outline.cget('highlightthickness')) == quick_translate.GRIP_OUTLINE_PX
        assert int(outline.attributes('-topmost')) == 1
        mgr._grip_release()

    def test_the_outline_never_takes_the_focus(self, sized, tk_root, no_pause):
        mgr, _ = sized
        put_up(mgr, tk_root, cases.case('C'))
        mgr.popup.focus_force()
        tk_root.update()
        user32 = ctypes.windll.user32
        active = user32.GetActiveWindow()
        mgr._grip_press(SimpleNamespace(x_root=100, y_root=100))
        grip_drag(mgr, 40, 30)
        tk_root.update()
        outline = mgr._grip_outline
        hwnd = user32.GetParent(outline.winfo_id()) or outline.winfo_id()
        assert user32.GetWindowLongW(hwnd, quick_translate.GWL_EXSTYLE) & \
            quick_translate.WS_EX_NOACTIVATE
        assert user32.GetActiveWindow() == active
        mgr._grip_release()

    def test_a_drag_step_costs_next_to_nothing(self, sized, tk_root, no_pause):
        mgr, _ = sized
        put_up(mgr, tk_root, cases.case('G'))
        mgr._grip_press(SimpleNamespace(x_root=100, y_root=100))
        times = []
        for step in range(1, 31):
            start = time.perf_counter()
            grip_drag(mgr, 4 * step, 3 * step)
            tk_root.update()
            times.append((time.perf_counter() - start) * 1000)
        mgr._grip_release()
        # Measured 1.5-2.1 ms a step on the private desktop (2026-10-19), against 181 ms
        # when every motion laid this case out. The bound leaves room for a slow runner.
        median = statistics.median(times)
        assert median < 25, f"median {median:.1f} ms a step: {[round(t, 1) for t in times]}"

    def test_a_double_click_takes_the_outline_away(self, sized, tk_root, no_pause):
        mgr, _ = sized
        put_up(mgr, tk_root, cases.case('C'))
        mgr._grip_press(SimpleNamespace(x_root=100, y_root=100))
        grip_drag(mgr, 40, 30)
        tk_root.update()
        outline = mgr._grip_outline
        mgr._grip_reset()
        tk_root.update()
        assert mgr._grip_outline is None and not outline.winfo_exists()
        assert mgr._grip_preview_after is None

    def test_closing_mid_drag_leaves_nothing_behind(self, sized, tk_root, monkeypatch):
        monkeypatch.setattr(quick_translate, 'POPUP_GRIP_PREVIEW_MS', 20)
        mgr, _ = sized
        put_up(mgr, tk_root, cases.case('C'))
        mgr._grip_press(SimpleNamespace(x_root=100, y_root=100))
        grip_drag(mgr, 40, 30)
        tk_root.update()
        outline = mgr._grip_outline
        mgr.close()
        assert mgr._grip_preview_after is None
        time.sleep(0.05)
        tk_root.update()
        assert not outline.winfo_exists()
        assert mgr._grip_outline is None and mgr.popup is None


class TestLoadingIndicator:
    """Placed by the same rules, so it never spills off the screen (TODO.md Q9)."""

    def test_at_the_bottom_right_corner_it_stays_on_the_screen(self, manager, tk_root):
        work = manager._work_area()
        manager._last_mouse_x, manager._last_mouse_y = work.right - 5, work.bottom - 5
        manager.show_loading("French")
        tk_root.update()
        popup = manager.popup
        assert work.left <= popup.winfo_x()
        assert popup.winfo_x() + popup.winfo_width() <= work.right
        assert work.top <= popup.winfo_y()
        assert popup.winfo_y() + popup.winfo_height() <= work.bottom
        manager.close()
