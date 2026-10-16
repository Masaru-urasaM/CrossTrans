"""
Integration tests for furigana in the main window and the expanded view (F3).

`TranslatorApp.__init__` registers global hotkeys, builds a tray icon and takes a
single-instance lock, so these tests build the instance with `__new__` and set
only the attributes the methods under test touch. That keeps the real methods
under test - `_create_translation_box`, `_update_translation_with_original`,
`_update_grammar_result`, `_open_expanded_translation`, `_copy_translation` -
without starting the application.

Skipped automatically when no display is available (see the `tk_root` fixture).
"""
import tkinter as tk
from unittest.mock import MagicMock

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.app import TranslatorApp
from src.core import furigana as F
from src.core.translation import TranslationService
from src.ui.expanded_window import ExpandedTranslationWindow
from src.ui.ruby_text import RubyText

HAS_PROVIDER = pytest.mark.skipif(
    not F.is_available(),
    reason="requires a reading provider (fugashi or pykakasi)"
)

JP_SENTENCE = "私は毎日日本語を勉強しています。"
JP_KANJI_ONLY = "東京都"
EN_SENTENCE = "I study Japanese every day."


class FakeConfig:
    def __init__(self, furigana_enabled=True):
        self._furigana = furigana_enabled

    def get_furigana_enabled(self):
        return self._furigana


class FakeToast:
    def __init__(self):
        self.messages = []

    def show_success(self, msg):
        self.messages.append(('success', msg))

    def show_warning(self, msg):
        self.messages.append(('warning', msg))


class FakeButton:
    """Stand-in for the ttk buttons these methods poke at."""

    def __init__(self):
        self.kwargs = {}

    def configure(self, **kwargs):
        self.kwargs.update(kwargs)


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
    yield holder
    holder.destroy()


def make_service(verdicts=None):
    """A real TranslationService with nothing but its verdict memory (J7).

    The main window reads the input's settled language through
    `source_language()`; real code, so the tests cover it, with `verdicts` as
    the texts a model has placed this session.
    """
    service = TranslationService.__new__(TranslationService)
    service.history_manager = MagicMock()
    service.history_manager.find_source_verdict.return_value = None
    for text, verdict in (verdicts or {}).items():
        service._remember_source_verdict(text, verdict)
    return service


@pytest.fixture
def app(tk_root, frame):
    """A TranslatorApp with just enough state for the output-box methods."""
    instance = TranslatorApp.__new__(TranslatorApp)
    instance.root = tk_root
    instance.config = FakeConfig(True)
    instance.toast = FakeToast()
    instance.popup = None                 # keeps title/animation helpers inert
    instance.selected_language = "Japanese"
    instance.translate_btn = FakeButton()
    instance.copy_btn = FakeButton()
    instance._test_frame = frame
    instance.original_text = tk.Text(frame, height=2)     # the input box: empty
    instance.translation_service = make_service()
    # Real methods that would need the full app; harmless no-ops here.
    instance._stop_translate_animation = lambda: None
    instance._update_popup_title_with_trial = lambda: None
    yield instance


# --------------------------------------------------------------------------- #
# Main window output box
# --------------------------------------------------------------------------- #
class TestTranslationBox:
    @HAS_PROVIDER
    def test_japanese_translation_is_annotated(self, app):
        box = app._create_translation_box(app._test_frame, JP_SENTENCE,
                                          "Japanese")
        assert isinstance(box, RubyText)
        assert box.has_ruby is True
        assert box.get_plain() == JP_SENTENCE

    @HAS_PROVIDER
    def test_kanji_only_uses_the_target_language(self, app):
        box = app._create_translation_box(app._test_frame, JP_KANJI_ONLY,
                                          "Japanese")
        assert box.has_ruby is True
        assert box.get_plain() == JP_KANJI_ONLY

    def test_kanji_only_with_a_chinese_target_stays_plain(self, app):
        box = app._create_translation_box(app._test_frame, JP_KANJI_ONLY,
                                          "Chinese (Simplified)")
        assert box.has_ruby is False

    def test_latin_translation_is_untouched(self, app):
        box = app._create_translation_box(app._test_frame, EN_SENTENCE,
                                          "English")
        assert box.has_ruby is False
        assert box.get_plain() == EN_SENTENCE

    def test_box_is_read_only(self, app):
        # I3 holds by construction for this box.
        box = app._create_translation_box(app._test_frame, EN_SENTENCE,
                                          "English")
        assert str(box.cget('state')) == 'disabled'

    @HAS_PROVIDER
    def test_toggle_off_disables_readings(self, app):
        app.config = FakeConfig(False)
        box = app._create_translation_box(app._test_frame, JP_SENTENCE,
                                          "Japanese")
        assert box.has_ruby is False
        assert box.get_plain() == JP_SENTENCE


class TestBoxUpdates:
    @HAS_PROVIDER
    def test_translation_update_replaces_and_annotates(self, app):
        app._create_translation_box(app._test_frame, EN_SENTENCE, "English")
        app._update_translation_with_original(JP_SENTENCE)
        assert app.trans_text.has_ruby is True
        assert app.trans_text.get_plain() == JP_SENTENCE
        # Still read-only after the update.
        assert str(app.trans_text.cget('state')) == 'disabled'

    @HAS_PROVIDER
    def test_repeated_updates_do_not_accumulate(self, app):
        app._create_translation_box(app._test_frame, EN_SENTENCE, "English")
        app._update_translation_with_original(JP_SENTENCE)
        first = app.trans_text.ruby_pairs
        app._update_translation_with_original(JP_SENTENCE)
        assert app.trans_text.ruby_pairs == first
        assert app.trans_text.get_plain() == JP_SENTENCE

    @HAS_PROVIDER
    def test_grammar_result_annotates_without_a_hint(self, app):
        # A grammar fix keeps the source language, which the app does not know;
        # kana-bearing Japanese still qualifies on its own.
        app._create_translation_box(app._test_frame, EN_SENTENCE, "English")
        app._update_grammar_result(JP_SENTENCE)
        assert app.trans_text.has_ruby is True
        assert app.trans_text.get_plain() == JP_SENTENCE

    def test_grammar_result_does_not_guess_on_kanji_only(self, app):
        app._create_translation_box(app._test_frame, EN_SENTENCE, "English")
        app._update_grammar_result(JP_KANJI_ONLY)
        assert app.trans_text.has_ruby is False
        assert app.trans_text.get_plain() == JP_KANJI_ONLY


class TestReadback:
    @HAS_PROVIDER
    def test_copy_takes_the_whole_translation(self, app, monkeypatch):
        copied = []
        monkeypatch.setattr('src.app.pyperclip.copy', copied.append)
        app.popup = app.root                      # for the after() reset
        app._create_translation_box(app._test_frame, JP_SENTENCE, "Japanese")
        assert app.trans_text.has_ruby is True
        app._copy_translation()
        # get() would have handed over a kanji-stripped string.
        assert copied == [JP_SENTENCE]

    @HAS_PROVIDER
    def test_expand_receives_the_whole_translation(self, app):
        received = []

        class Recorder:
            def show(self, translated, target_language, source_language=None):
                received.append((translated, target_language, source_language))

        app.expanded_window = Recorder()
        app._create_translation_box(app._test_frame, JP_SENTENCE, "Japanese")
        app._open_expanded_translation()
        assert received == [(JP_SENTENCE, "Japanese", None)]

    def test_copy_warns_when_empty(self, app, monkeypatch):
        copied = []
        monkeypatch.setattr('src.app.pyperclip.copy', copied.append)
        app._create_translation_box(app._test_frame, "", "English")
        app._copy_translation()
        assert copied == []
        assert app.toast.messages == [('warning', "No translation to copy")]


# --------------------------------------------------------------------------- #
# Expanded window
# --------------------------------------------------------------------------- #
class TestExpandedWindow:
    @staticmethod
    def _open(tk_root, text, language="Japanese", furigana_enabled=True):
        window = ExpandedTranslationWindow(tk_root, FakeToast(),
                                           FakeConfig(furigana_enabled))
        window.show(text, language)
        tk_root.update_idletasks()
        # The window is a Toplevel built inside show(); find its RubyText.
        top = tk_root.winfo_children()[-1]
        boxes = []

        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, RubyText):
                    boxes.append(child)
                walk(child)

        walk(top)
        assert len(boxes) == 1, f"expected one RubyText, found {len(boxes)}"
        return top, boxes[0]

    @HAS_PROVIDER
    def test_japanese_is_annotated_and_read_only(self, tk_root):
        top, box = self._open(tk_root, JP_SENTENCE)
        try:
            assert box.has_ruby is True
            assert box.get_plain() == JP_SENTENCE
            assert str(box.cget('state')) == 'disabled'
        finally:
            top.destroy()

    @HAS_PROVIDER
    def test_kanji_only_uses_the_language_argument(self, tk_root):
        top, box = self._open(tk_root, JP_KANJI_ONLY)
        try:
            assert box.has_ruby is True
        finally:
            top.destroy()

    @HAS_PROVIDER
    def test_toggle_off_disables_readings(self, tk_root):
        top, box = self._open(tk_root, JP_SENTENCE, furigana_enabled=False)
        try:
            assert box.has_ruby is False
            assert box.get_plain() == JP_SENTENCE
        finally:
            top.destroy()

    def test_latin_is_untouched(self, tk_root):
        top, box = self._open(tk_root, EN_SENTENCE, "English")
        try:
            assert box.has_ruby is False
            assert box.get_plain() == EN_SENTENCE
        finally:
            top.destroy()

    @HAS_PROVIDER
    def test_status_counts_the_real_characters(self, tk_root):
        top, box = self._open(tk_root, JP_SENTENCE)
        try:
            labels = []

            def walk(widget):
                for child in widget.winfo_children():
                    text = ''
                    try:
                        text = str(child.cget('text'))
                    except Exception:
                        pass
                    if 'Characters:' in text:
                        labels.append(text)
                    walk(child)

            walk(top)
            assert labels, "status bar not found"
            # Counted via get_plain(): get() would report the kanji missing.
            assert f"Characters: {len(JP_SENTENCE):,}" in labels[0]
        finally:
            top.destroy()

    @HAS_PROVIDER
    def test_copy_button_puts_the_whole_text_on_the_clipboard(self, tk_root,
                                                             monkeypatch):
        copied = []
        monkeypatch.setattr('src.ui.expanded_window.pyperclip.copy',
                            copied.append)
        top, box = self._open(tk_root, JP_SENTENCE)
        try:
            buttons = []

            def walk(widget):
                for child in widget.winfo_children():
                    text = ''
                    try:
                        text = str(child.cget('text'))
                    except Exception:
                        pass
                    if 'Copy' in text and hasattr(child, 'invoke'):
                        buttons.append(child)
                    walk(child)

            walk(top)
            assert buttons, "copy button not found"
            buttons[0].invoke()
            assert copied == [JP_SENTENCE]
        finally:
            top.destroy()

    def test_empty_translation_warns_and_opens_nothing(self, tk_root):
        toast = FakeToast()
        before = len(tk_root.winfo_children())
        ExpandedTranslationWindow(tk_root, toast, FakeConfig()).show("", "English")
        assert toast.messages == [('warning', "No translation to expand")]
        assert len(tk_root.winfo_children()) == before


# --------------------------------------------------------------------------- #
# J7 - the input's settled language reaches every output surface
# --------------------------------------------------------------------------- #
QUOTED = "The word 東京 means Tokyo."


def type_input(app, text, verdict=None):
    app.original_text.delete('1.0', tk.END)
    app.original_text.insert('1.0', text)
    if verdict:
        app.translation_service._remember_source_verdict(text, verdict)


class TestSettledSource:
    @HAS_PROVIDER
    def test_japanese_quoted_in_an_english_translation_is_read(self, app):
        type_input(app, "東京", "Japanese")
        box = app._create_translation_box(app._test_frame, QUOTED, "English")
        assert box.has_ruby is True
        assert box.get_plain() == QUOTED

    def test_without_a_verdict_it_stays_plain(self, app):
        type_input(app, "東京")
        box = app._create_translation_box(app._test_frame, QUOTED, "English")
        assert box.has_ruby is False

    @HAS_PROVIDER
    def test_a_translation_update_uses_the_settled_source(self, app):
        type_input(app, "東京", "Japanese")
        app.selected_language = "English"
        app._create_translation_box(app._test_frame, "", "English")
        app._update_translation_with_original(QUOTED)
        assert app.trans_text.has_ruby is True

    @HAS_PROVIDER
    def test_a_grammar_fix_of_placed_kanji_is_read(self, app):
        type_input(app, JP_KANJI_ONLY, "Japanese")
        app._create_translation_box(app._test_frame, "", "Japanese")
        app._update_grammar_result(JP_KANJI_ONLY)
        assert app.trans_text.has_ruby is True

    def test_a_grammar_fix_of_unplaced_kanji_stays_plain(self, app):
        type_input(app, JP_KANJI_ONLY)
        app._create_translation_box(app._test_frame, "", "Japanese")
        app._update_grammar_result(JP_KANJI_ONLY)
        assert app.trans_text.has_ruby is False

    def test_the_expanded_view_gets_the_settled_source(self, app):
        received = []

        class Recorder:
            def show(self, translated, target_language, source_language=None):
                received.append(source_language)

        type_input(app, "東京", "Japanese")
        app.selected_language = "English"
        app.expanded_window = Recorder()
        app._create_translation_box(app._test_frame, QUOTED, "English")
        app._open_expanded_translation()
        assert received == ["Japanese"]


class TestExpandedSource:
    @HAS_PROVIDER
    def test_a_japanese_source_reads_quoted_kanji(self, tk_root):
        window = ExpandedTranslationWindow(tk_root, FakeToast(), FakeConfig(True))
        before = set(tk_root.winfo_children())
        window.show(QUOTED, "English", source_language="Japanese")
        opened = [w for w in tk_root.winfo_children() if w not in before]
        try:
            boxes = [c for w in opened for c in _descendants(w) if isinstance(c, RubyText)]
            assert boxes and boxes[0].has_ruby is True
        finally:
            for w in opened:
                w.destroy()

    def test_no_source_no_readings_in_english(self, tk_root):
        window = ExpandedTranslationWindow(tk_root, FakeToast(), FakeConfig(True))
        before = set(tk_root.winfo_children())
        window.show(QUOTED, "English")
        opened = [w for w in tk_root.winfo_children() if w not in before]
        try:
            boxes = [c for w in opened for c in _descendants(w) if isinstance(c, RubyText)]
            assert boxes and boxes[0].has_ruby is False
        finally:
            for w in opened:
                w.destroy()


def _descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from _descendants(child)
