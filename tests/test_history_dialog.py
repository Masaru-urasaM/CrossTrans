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
import tkinter as tk

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.ui.history_dialog import HistoryDialog


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

    def _open(count=40):
        parent = tk.Toplevel(tk_root)
        parent.geometry('500x300')
        manager = FakeHistoryManager(make_entries(count))
        loaded = []
        dlg = HistoryDialog(parent, manager, loaded.append)
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
