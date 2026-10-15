"""
Tests for the translation History dialog.

The store itself was never broken - the config file holds its 100 entries and
`HistoryManager` reads and writes them fine. What did not work was the window:

* `bind_all("<MouseWheel>")` undone by a `<Destroy>` handler on the toplevel. A
  child's `<Destroy>` propagates up to its toplevel's bindtag, so the *first*
  list rebuild - one keystroke in the search box, one deleted entry, one
  focus-out that restores the placeholder - unbound the wheel from the whole
  application. With no scrollbar in the dialog, the list then could not be
  scrolled at all, and neither could anything else.
* `grab_set()`, which the project forbids (CLAUDE.md, Known Issues): it locks
  every other window behind a dialog, and the Clear All confirmation is itself a
  Toplevel that has to take input while this one is up.

These drive the real dialog against a live display.
"""
import time
import tkinter as tk

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.core import furigana as F
from src.core.furigana import RubySegment
from src.ui.history_dialog import LINE_CUT, HistoryDialog
from src.ui.ruby_text import RubyLine, truncate_segments

HAS_PROVIDER = pytest.mark.skipif(not F.is_available(),
                                  reason="requires a reading provider (fugashi or pykakasi)")


class FakeHistoryManager:
    """Only the three calls the dialog makes."""

    def __init__(self, entries):
        self.entries = list(entries)

    def get_history(self):
        return list(self.entries)

    def delete_entry(self, entry_id):
        self.entries = [e for e in self.entries if e.get('id') != entry_id]

    def clear_history(self):
        self.entries = []


def make_entries(count):
    return [{
        'id': 'id-%d' % i,
        'timestamp': 1_700_000_000 + i,
        'original': 'source text number %d' % i,
        'translated': 'translated text number %d' % i,
        'target_lang': 'English',
        'source_lang': 'Japanese',
        'source_type': 'text',
        'model_used': 'Auto',
    } for i in range(count)]


@pytest.fixture
def dialog(tk_root):
    """Open the real dialog over a real parent window; clean up afterwards."""
    opened = []

    def _open(count=40, entries=None, furigana_enabled=False):
        parent = tk.Toplevel(tk_root)
        parent.geometry('500x300')
        manager = FakeHistoryManager(make_entries(count) if entries is None else entries)
        loaded = []
        dlg = HistoryDialog(parent, manager, loaded.append, furigana_enabled=furigana_enabled)
        tk_root.update()
        opened.append((parent, dlg))
        return dlg, manager, loaded

    yield _open
    for parent, dlg in opened:
        for window in (dlg.window, parent):
            try:
                window.destroy()
            except tk.TclError:
                pass


def scrolls(dlg, widget):
    """Whether a wheel event on `widget` moves the list."""
    dlg.canvas.yview_moveto(0.0)
    dlg.window.update()
    before = dlg.canvas.yview()[0]
    widget.event_generate('<MouseWheel>', delta=-120, x=10, y=10)
    dlg.window.update()
    return dlg.canvas.yview()[0] > before


def rows_of(dlg):
    """The entry rows, excluding the separators between them."""
    return [w for w in dlg.scrollable_frame.winfo_children() if w.winfo_children()]


class TestScrolling:
    def test_the_wheel_scrolls_the_list(self, dialog):
        dlg, _manager, _loaded = dialog()
        if dlg.canvas.yview() == (0.0, 1.0):
            pytest.skip("content fits, nothing to scroll")
        assert scrolls(dlg, dlg.canvas)

    def test_the_wheel_works_over_a_row_too(self, dialog):
        # The rows cover the canvas, and a child consumes the event first.
        dlg, _manager, _loaded = dialog()
        assert scrolls(dlg, rows_of(dlg)[0])

    def test_scrolling_survives_a_search(self, dialog):
        # The regression: one keystroke used to unbind the wheel application-wide.
        dlg, _manager, _loaded = dialog()
        dlg.search_entry.delete(0, tk.END)
        dlg.search_entry.insert(0, "source")
        dlg.window.update()
        assert rows_of(dlg), "the search matched nothing"
        assert scrolls(dlg, dlg.canvas)
        assert scrolls(dlg, rows_of(dlg)[0])

    def test_scrolling_survives_a_delete(self, dialog):
        dlg, manager, _loaded = dialog()
        dlg._delete_item(manager.entries[0])
        dlg.window.update()
        assert scrolls(dlg, rows_of(dlg)[0])

    def test_no_application_wide_binding_is_left(self, dialog, tk_root):
        # bind_all() stole the wheel from the popup, the dictionary window and
        # the main window for as long as this dialog was open.
        dlg, _manager, _loaded = dialog()
        assert tk_root.bind_all("<MouseWheel>") in ('', None)
        dlg.window.destroy()
        tk_root.update()
        assert tk_root.bind_all("<MouseWheel>") in ('', None)


class TestNoModalGrab:
    def test_the_dialog_takes_no_grab(self, dialog):
        dlg, _manager, _loaded = dialog()
        assert dlg.window.grab_current() is None

    def test_two_dialogs_can_coexist(self, dialog):
        # A grab would have made the second one unreachable.
        first, _m1, _l1 = dialog()
        second, _m2, _l2 = dialog()
        assert first.window.winfo_exists()
        assert second.window.winfo_exists()
        assert second.window.grab_current() is None


class TestListBehaviour:
    def test_every_entry_gets_a_row(self, dialog):
        dlg, manager, _loaded = dialog(count=12)
        assert len(rows_of(dlg)) == len(manager.entries)

    def test_clicking_a_row_loads_it(self, dialog):
        dlg, manager, loaded = dialog(count=5)
        wanted = manager.entries[2]
        dlg._load_item(wanted)
        assert loaded == [wanted]

    def test_search_filters_the_list(self, dialog):
        dlg, _manager, _loaded = dialog(count=20)
        dlg.search_entry.delete(0, tk.END)
        dlg.search_entry.insert(0, "number 7")
        dlg.window.update()
        assert len(rows_of(dlg)) == 1

    def test_a_search_with_no_match_says_so(self, dialog):
        dlg, _manager, _loaded = dialog(count=5)
        dlg.search_entry.delete(0, tk.END)
        dlg.search_entry.insert(0, "zzzz-no-such-text")
        dlg.window.update()
        labels = dlg.scrollable_frame.winfo_children()
        assert len(labels) == 1
        assert "No results" in str(labels[0].cget('text'))

    def test_deleting_removes_the_row_and_the_entry(self, dialog):
        dlg, manager, _loaded = dialog(count=6)
        dlg._delete_item(manager.entries[0])
        dlg.window.update()
        assert len(manager.entries) == 5
        assert len(rows_of(dlg)) == 5

    def test_an_empty_history_says_so(self, dialog):
        dlg, _manager, _loaded = dialog(count=0)
        labels = dlg.scrollable_frame.winfo_children()
        assert len(labels) == 1
        assert "No history" in str(labels[0].cget('text'))


# --------------------------------------------------------------------------- #
# J9 - readings on the rows
# --------------------------------------------------------------------------- #
def entry(original, translated, verdict=None, target="English", entry_id="j"):
    item = {'id': entry_id, 'timestamp': 1_700_000_000, 'original': original,
            'translated': translated, 'target_lang': target, 'source_lang': "",
            'source_type': 'text', 'model_used': 'Auto'}
    if verdict:
        item['source_verdict'] = verdict
    return item


def ruby_lines(dlg):
    found = []

    def walk(widget):
        for child in widget.winfo_children():
            if isinstance(child, RubyLine):
                found.append(child)
            walk(child)
    walk(dlg.scrollable_frame)
    return found


class TestTruncateSegments:
    def test_short_text_is_kept_whole(self):
        segments = (RubySegment("東京", "とうきょう"), RubySegment("へ", None))
        assert truncate_segments(segments, 10) == (segments, False)

    def test_a_plain_run_is_cut_at_the_limit(self):
        segments = (RubySegment("abcdef", None),)
        assert truncate_segments(segments, 4) == ((RubySegment("abcd", None),), True)

    def test_a_ruby_pair_is_never_split(self):
        segments = (RubySegment("ab", None), RubySegment("東京", "とうきょう"), RubySegment("x", None))
        assert truncate_segments(segments, 3) == ((RubySegment("ab", None),), True)

    def test_a_pair_that_fits_exactly_is_kept(self):
        segments = (RubySegment("ab", None), RubySegment("東京", "とうきょう"), RubySegment("x", None))
        assert truncate_segments(segments, 4) == (segments[:2], True)


class TestReadings:
    @HAS_PROVIDER
    def test_a_japanese_row_carries_readings(self, dialog):
        dlg, _, _ = dialog(entries=[entry("毎日日本語を勉強しています。", "I study Japanese every day.")],
                           furigana_enabled=True)
        lines = ruby_lines(dlg)
        assert len(lines) == 1
        assert lines[0].get_plain() == "毎日日本語を勉強しています。"
        assert lines[0].has_ruby

    def test_furigana_off_keeps_the_plain_labels(self, dialog):
        dlg, _, _ = dialog(entries=[entry("毎日日本語を勉強しています。", "I study")],
                           furigana_enabled=False)
        assert ruby_lines(dlg) == []

    def test_unplaced_kanji_stays_plain(self, dialog):
        dlg, _, _ = dialog(entries=[entry("東京大学", "The University of Tokyo")],
                           furigana_enabled=True)
        assert ruby_lines(dlg) == []

    @HAS_PROVIDER
    def test_kanji_the_model_placed_is_read(self, dialog):
        dlg, _, _ = dialog(entries=[entry("東京大学", "The University of Tokyo", verdict="Japanese")],
                           furigana_enabled=True)
        assert [line.get_plain() for line in ruby_lines(dlg)] == ["東京大学"]

    def test_the_old_source_label_is_not_a_verdict(self, dialog):
        item = entry("東京大学", "The University of Tokyo")
        item['source_lang'] = "Japanese"           # a label, guessed or not: never trusted
        dlg, _, _ = dialog(entries=[item], furigana_enabled=True)
        assert ruby_lines(dlg) == []

    @HAS_PROVIDER
    def test_the_translation_line_is_read_by_the_language_set_rule(self, dialog):
        dlg, _, _ = dialog(entries=[entry("東京", "The word 東京 means Tokyo.", verdict="Japanese")],
                           furigana_enabled=True)
        plains = [line.get_plain() for line in ruby_lines(dlg)]
        assert "→ The word 東京 means Tokyo." in plains

    def test_a_chinese_source_leaves_the_translation_plain(self, dialog):
        dlg, _, _ = dialog(entries=[entry("我们", "我们 means we.", verdict="Japanese")],
                           furigana_enabled=True)
        assert ruby_lines(dlg) == []

    @HAS_PROVIDER
    def test_a_long_line_is_cut_without_splitting_a_pair(self, dialog):
        text = "毎日日本語を勉強しています。" * 8
        dlg, _, _ = dialog(entries=[entry(text, "I study")], furigana_enabled=True)
        line = ruby_lines(dlg)[0]
        assert line.get_plain().endswith("...")
        body = line.get_plain()[:-3]
        assert len(body) <= LINE_CUT and text.startswith(body)
        bases = [seg.base for seg in line.segments if seg.ruby]
        assert all(base in ("毎日", "日本語", "勉強") for base in bases)

    @HAS_PROVIDER
    def test_clicking_a_reading_loads_the_entry(self, dialog):
        item = entry("毎日日本語を勉強しています。", "I study Japanese every day.")
        dlg, _, loaded = dialog(entries=[item], furigana_enabled=True)
        line = ruby_lines(dlg)[0]
        line.event_generate('<Button-1>', x=5, y=2)          # on the reading row
        dlg.window.update() if dlg.window.winfo_exists() else None
        assert loaded == [item]

    @HAS_PROVIDER
    def test_the_wheel_works_over_a_line_with_readings(self, dialog):
        entries = [entry("毎日日本語を勉強しています。", "I study", entry_id=str(i)) for i in range(30)]
        dlg, _, _ = dialog(entries=entries, furigana_enabled=True)
        assert scrolls(dlg, ruby_lines(dlg)[0])

    @HAS_PROVIDER
    def test_search_still_filters_annotated_rows(self, dialog):
        entries = [entry("毎日日本語を勉強しています。", "I study", entry_id="a"),
                   entry("友達に手紙を書きました。", "I wrote a letter", entry_id="b")]
        dlg, _, _ = dialog(entries=entries, furigana_enabled=True)
        dlg.search_entry.delete(0, tk.END)
        dlg.search_entry.insert(0, "手紙")
        dlg.window.update()
        assert [line.get_plain() for line in ruby_lines(dlg)] == ["友達に手紙を書きました。"]

    @HAS_PROVIDER
    def test_a_wide_reading_never_overlaps_its_neighbour(self, tk_root):
        frame = tk.Frame(tk_root)
        try:
            line = RubyLine(frame, (RubySegment("東京", "とうきょう"), RubySegment("都", "と")))
            items = line.find_all()
            # Item order: reading, base for each pair; the pairs' slots must not overlap.
            first_reading, _first_base, second_reading, _second_base = items
            assert line.bbox(first_reading)[2] <= line.bbox(second_reading)[0] + 1
        finally:
            frame.destroy()

    @HAS_PROVIDER
    def test_a_hundred_japanese_rows_open_within_budget(self, dialog):
        """J9 measured ~0.95 s for this dialog WITHOUT readings (pre-existing, D17)
        and ~1.3 s with them; a RubyRow per line took 4.1 s. Bound generously so
        a slow CI machine does not flake, tight enough to catch a return of the
        per-segment widgets."""
        sentences = ["毎日日本語を勉強しています。", "友達に手紙を書きました。東京大学で会いましょう。",
                     "昔は汽車で旅行しました。", "体調はもう大丈夫です。"]
        entries = [entry(sentences[i % 4] * (1 + i % 3), "Translation 東京", verdict="Japanese",
                         entry_id=str(i)) for i in range(100)]
        start = time.perf_counter()
        dlg, _, _ = dialog(entries=entries, furigana_enabled=True)
        elapsed = time.perf_counter() - start
        assert len(ruby_lines(dlg)) >= 100
        assert elapsed < 8, f"History with 100 Japanese rows took {elapsed:.2f} s"


class TestRubyLineCost:
    def test_fonts_are_shared_between_lines(self, tk_root):
        """A Font per line made Tk redo its CJK fallback search on every measure
        (1.9 s of a 3.3 s open, J9). Lines share one Font per interpreter and size."""
        from src.ui import ruby_text
        frame = tk.Frame(tk_root)
        try:
            RubyLine(frame, (RubySegment("東京", "とうきょう"),), base_font=('Segoe UI', 10))
            after_first = dict(ruby_text._LINE_FONTS)
            assert (frame.tk, ('Segoe UI', 10)) in after_first
            for _ in range(3):
                RubyLine(frame, (RubySegment("東京", "とうきょう"),), base_font=('Segoe UI', 10))
            assert ruby_text._LINE_FONTS == after_first          # nothing new, same objects
        finally:
            frame.destroy()

    def test_the_app_passes_the_setting(self):
        import inspect
        from src.app import TranslatorApp
        assert 'furigana_enabled=self._ruby_enabled()' in inspect.getsource(TranslatorApp._open_history)
