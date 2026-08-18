"""
Integration tests for the main window's Reading pane (F4).

The input box must stay a plain `tk.Text` (I3: editable implies plain), so the
readings for what the user typed live in a read-only `RubyText` beneath it.
These tests drive the real methods - `_create_reading_pane`,
`_refresh_reading_pane`, `_toggle_reading_pane`, `_on_input_modified` - on a
`TranslatorApp` built with `__new__`, the same way `test_main_window_ruby.py`
does, because `__init__` would register global hotkeys and a tray icon.

Skipped automatically when no display is available (see the `tk_root` fixture).
"""
import time
import tkinter as tk

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.app import (
    READING_PANE_PLACEHOLDER,
    READING_PANE_PLACEHOLDER_TAG,
    TranslatorApp,
)
from src.core import furigana as F
from src.ui.ruby_text import MAX_ANNOTATE_CHARS, RubyText

HAS_PROVIDER = pytest.mark.skipif(
    not F.is_available(),
    reason="requires a reading provider (fugashi or pykakasi)"
)

JP_SENTENCE = "私は毎日日本語を勉強しています。"
JP_KANJI_ONLY = "東京都"
EN_SENTENCE = "I study Japanese every day."


class FakeConfig:
    def __init__(self, furigana_enabled=True, pane_expanded=True):
        self._furigana = furigana_enabled
        self._pane = pane_expanded
        self.saved = []

    def get_furigana_enabled(self):
        return self._furigana

    def get_furigana_reading_pane(self):
        return self._pane

    def set_furigana_reading_pane(self, expanded):
        self._pane = expanded
        self.saved.append(expanded)


@pytest.fixture(autouse=True)
def _clear_cache():
    F.clear_cache()
    yield
    F.clear_cache()


@pytest.fixture
def frame(tk_root):
    holder = tk.Frame(tk_root, width=700, height=400)
    holder.pack_propagate(False)
    holder.pack()
    tk_root.update_idletasks()
    yield holder
    holder.destroy()


def build(tk_root, frame, config, text=""):
    """Build an app with just the input box and its Reading pane."""
    app = TranslatorApp.__new__(TranslatorApp)
    app.root = tk_root
    app.popup = tk_root          # the pane schedules its refresh on the popup
    app.config = config

    app.original_text = tk.Text(frame, height=6, wrap=tk.WORD, undo=True,
                                maxundo=-1)
    app.original_text.pack(fill=tk.X)
    if text:
        app.original_text.insert('1.0', text)
    app._create_reading_pane(frame)
    tk_root.update_idletasks()
    return app


def refresh(app, text=None):
    """Set the input text (as any caller would) and render the pane now."""
    if text is not None:
        app.original_text.delete('1.0', tk.END)
        app.original_text.insert('1.0', text)
    app._refresh_reading_pane()
    app.root.update_idletasks()
    return app._reading_text


def is_packed(widget) -> bool:
    """True while the widget is managed by pack (survives pack_forget)."""
    return bool(widget.winfo_manager())


# --------------------------------------------------------------------------- #
# Construction
# --------------------------------------------------------------------------- #
class TestBuild:
    def test_pane_is_a_read_only_ruby_text(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig())
        assert isinstance(app._reading_text, RubyText)
        assert str(app._reading_text.cget('state')) == 'disabled'

    def test_input_box_stays_plain(self, tk_root, frame):
        # I3: an embedded ruby frame cannot survive edit_undo, so the box the
        # user types in must never be a RubyText.
        app = build(tk_root, frame, FakeConfig())
        assert not isinstance(app.original_text, RubyText)

    def test_shown_by_default(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig())
        assert is_packed(app._reading_block) is True
        assert is_packed(app._reading_text) is True
        assert app._reading_toggle.cget('text').startswith('▼')

    def test_remembered_collapse_is_honored_at_build(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig(pane_expanded=False))
        assert is_packed(app._reading_block) is True      # header still visible
        assert is_packed(app._reading_text) is False      # body collapsed
        assert app._reading_toggle.cget('text').startswith('▶')

    def test_hidden_entirely_when_furigana_is_off(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig(furigana_enabled=False),
                    text=JP_SENTENCE)
        # Never packed at all: packing it and hiding it on the first refresh
        # would flash an empty pane for one debounce interval.
        assert is_packed(app._reading_block) is False
        refresh(app)
        assert is_packed(app._reading_block) is False

    def test_appears_when_furigana_is_switched_back_on(self, tk_root, frame):
        config = FakeConfig(furigana_enabled=False)
        app = build(tk_root, frame, config, text=JP_SENTENCE)
        config._furigana = True                # as the Settings toggle would
        refresh(app)
        assert is_packed(app._reading_block) is True


# --------------------------------------------------------------------------- #
# Content
# --------------------------------------------------------------------------- #
class TestContent:
    @HAS_PROVIDER
    def test_japanese_input_gets_readings(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig())
        pane = refresh(app, JP_SENTENCE)
        assert pane.has_ruby is True
        assert pane.get_plain() == JP_SENTENCE

    def test_empty_input_shows_the_placeholder(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig())
        pane = refresh(app, "")
        assert pane.has_ruby is False
        assert pane.get_plain() == READING_PANE_PLACEHOLDER

    def test_latin_input_is_not_mirrored(self, tk_root, frame):
        # Repeating the box above would be noise, not information.
        app = build(tk_root, frame, FakeConfig())
        pane = refresh(app, EN_SENTENCE)
        assert pane.get_plain() == READING_PANE_PLACEHOLDER

    def test_kanji_only_input_is_not_guessed_at(self, tk_root, frame):
        # The source language is unknown here and a kanji-only string reads as
        # Chinese, so no hint is passed and nothing is annotated.
        app = build(tk_root, frame, FakeConfig())
        pane = refresh(app, JP_KANJI_ONLY)
        assert pane.has_ruby is False
        assert pane.get_plain() == READING_PANE_PLACEHOLDER

    def test_text_past_the_render_budget_is_not_mirrored(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig())
        pane = refresh(app, JP_SENTENCE * (MAX_ANNOTATE_CHARS // 4))
        assert pane.has_ruby is False
        assert pane.get_plain() == READING_PANE_PLACEHOLDER

    def test_placeholder_is_dimmed(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig())
        pane = refresh(app, EN_SENTENCE)
        assert READING_PANE_PLACEHOLDER_TAG in pane.tag_names('1.0')

    @HAS_PROVIDER
    def test_refreshing_does_not_accumulate(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig())
        first = refresh(app, JP_SENTENCE).ruby_pairs
        assert first > 0
        pane = refresh(app, JP_SENTENCE)
        assert pane.ruby_pairs == first
        assert pane.get_plain() == JP_SENTENCE

    @HAS_PROVIDER
    def test_japanese_replaced_by_latin_clears_the_readings(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig())
        assert refresh(app, JP_SENTENCE).has_ruby is True
        pane = refresh(app, EN_SENTENCE)
        assert pane.has_ruby is False
        assert pane.get_plain() == READING_PANE_PLACEHOLDER

    @HAS_PROVIDER
    def test_pane_grows_for_wrapped_japanese(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig())
        short = refresh(app, JP_SENTENCE).cget('height')
        tall = refresh(app, JP_SENTENCE * 6).cget('height')
        assert int(tall) > int(short)

    @HAS_PROVIDER
    def test_growth_is_capped(self, tk_root, frame):
        from src.app import READING_PANE_MAX_ROWS
        app = build(tk_root, frame, FakeConfig())
        pane = refresh(app, JP_SENTENCE * 40)
        layout = pane.layout
        cap_px = READING_PANE_MAX_ROWS * layout.row_ruby
        assert int(pane.cget('height')) * layout.row_plain <= cap_px + layout.row_plain


# --------------------------------------------------------------------------- #
# Refresh wiring
# --------------------------------------------------------------------------- #
class TestRefreshWiring:
    def test_programmatic_write_schedules_a_refresh(self, tk_root, frame):
        # <<Modified>> covers _update_translation_with_original and
        # _load_history_item without either having to call the pane.
        app = build(tk_root, frame, FakeConfig())
        app._reading_pane_job = None
        app.original_text.insert('1.0', JP_SENTENCE)
        tk_root.update()
        assert app._reading_pane_job is not None

    def test_delete_then_insert_schedules_one_job(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig(), text=EN_SENTENCE)
        tk_root.update()
        app.original_text.delete('1.0', tk.END)
        app.original_text.insert('1.0', JP_SENTENCE)
        tk_root.update()
        first = app._reading_pane_job
        app.original_text.insert(tk.END, "！")
        tk_root.update()
        # Re-armed, not stacked: the previous job was cancelled.
        assert app._reading_pane_job is not None
        assert app._reading_pane_job != first

    @HAS_PROVIDER
    def test_the_scheduled_refresh_renders(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig())
        app.original_text.insert('1.0', JP_SENTENCE)
        tk_root.update()
        deadline = time.time() + 5           # bounded: never hang the suite
        while app._reading_pane_job and time.time() < deadline:
            tk_root.update()
        assert app._reading_pane_job is None, "debounced refresh never fired"
        assert app._reading_text.has_ruby is True

    def test_refresh_after_close_is_a_no_op(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig())
        app._reading_text.destroy()
        app._refresh_reading_pane()        # must not raise
        app._apply_reading_pane_state()
        app._toggle_reading_pane()

    def test_modified_handler_survives_a_destroyed_box(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig())
        app.original_text.destroy()
        app._on_input_modified()           # must not raise


# --------------------------------------------------------------------------- #
# Collapse toggle
# --------------------------------------------------------------------------- #
class TestToggle:
    def test_collapse_hides_the_body_and_is_remembered(self, tk_root, frame):
        config = FakeConfig()
        app = build(tk_root, frame, config)
        app._toggle_reading_pane()
        tk_root.update_idletasks()
        assert is_packed(app._reading_text) is False
        assert is_packed(app._reading_block) is True
        assert app._reading_toggle.cget('text').startswith('▶')
        assert config.saved == [False]

    @HAS_PROVIDER
    def test_expanding_again_re_renders(self, tk_root, frame):
        config = FakeConfig()
        app = build(tk_root, frame, config)
        refresh(app, JP_SENTENCE)
        app._toggle_reading_pane()
        app._toggle_reading_pane()
        tk_root.update_idletasks()
        assert config.saved == [False, True]
        assert is_packed(app._reading_text) is True
        app._refresh_reading_pane()
        assert app._reading_text.has_ruby is True

    def test_collapsed_pane_does_not_render(self, tk_root, frame):
        app = build(tk_root, frame, FakeConfig(pane_expanded=False),
                    text=JP_SENTENCE)
        app._refresh_reading_pane()
        tk_root.update_idletasks()
        # Nothing was inserted, so no annotation work happened either.
        assert app._reading_text.get_plain() == ""
