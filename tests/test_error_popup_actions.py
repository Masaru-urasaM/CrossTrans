"""
Tests for the action buttons on a *failed* Quick Translate popup.

A failed quick translate used to offer one way forward - API Settings - even
when the key was fine and the model had simply refused, timed out or returned
nothing useful. Those are all quicker to retry in the main window, so the error
bar now carries "Open Translator" next to it.

The one thing it must not do is carry the failure notice into the main window's
output box: what the user wants there is their source text and an empty result,
ready to translate.
"""
import tkinter as tk

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.app import TranslatorApp
from src.ui.quick_translate import QuickTranslateManager, is_error_text

ERROR = "Error: API request failed (503)"
NO_TEXT = "No text selected"
GOOD = "Bonjour le monde"


class FakeConfig:
    def get_furigana_enabled(self):
        return True

    def get_quick_replace(self):
        return False


@pytest.fixture
def popup(tk_root):
    """A manager whose popups are closed on teardown, plus a callback log."""
    created = []

    def _show(translated, target_lang="English"):
        manager = QuickTranslateManager(tk_root, FakeConfig())
        manager._last_mouse_x, manager._last_mouse_y = 500, 300
        fired = []
        manager._on_open_translator = lambda: fired.append('translator')
        manager._on_open_settings = lambda: fired.append('settings')
        manager.show(translated, target_lang)
        tk_root.update()
        created.append(manager)
        return manager, fired

    yield _show
    for manager in created:
        try:
            manager.close()
        except Exception:
            pass


def button_labels(widget):
    """Every button caption in the window, in creation order."""
    found = []
    for child in widget.winfo_children():
        try:
            text = str(child.cget('text'))
        except tk.TclError:
            text = ''
        if text and 'button' in child.winfo_class().lower():
            found.append(text)
        found.extend(button_labels(child))
    return found


def find_button(widget, label):
    for child in widget.winfo_children():
        try:
            if str(child.cget('text')) == label:
                return child
        except tk.TclError:
            pass
        hit = find_button(child, label)
        if hit is not None:
            return hit
    return None


class TestErrorPredicate:
    @pytest.mark.parametrize("text", [ERROR, NO_TEXT, "Error: quota exceeded"])
    def test_failures_are_recognised(self, text):
        assert is_error_text(text) is True

    @pytest.mark.parametrize("text", [GOOD, "", "An error occurred yesterday"])
    def test_translations_are_not(self, text):
        assert is_error_text(text) is False


class TestErrorButtonBar:
    def test_a_failure_offers_both_ways_forward(self, popup):
        manager, _fired = popup(ERROR)
        labels = button_labels(manager.popup)
        assert "API Settings" in labels
        assert "Open Translator" in labels

    def test_open_translator_sits_next_to_api_settings(self, popup):
        manager, _fired = popup(ERROR)
        labels = button_labels(manager.popup)
        assert labels.index("Open Translator") == labels.index("API Settings") + 1

    def test_clicking_it_calls_back(self, popup):
        manager, fired = popup(ERROR)
        find_button(manager.popup, "Open Translator").invoke()
        assert fired == ['translator']

    def test_the_no_text_case_gets_it_too(self, popup):
        manager, _fired = popup(NO_TEXT)
        assert "Open Translator" in button_labels(manager.popup)

    def test_a_successful_popup_is_unchanged(self, popup):
        manager, _fired = popup(GOOD)
        labels = button_labels(manager.popup)
        assert "API Settings" not in labels
        assert "Open Translator" in labels        # it always had this one
        assert "Copy" in labels and "Re-translate" in labels


class TestHandOverToTheMainWindow:
    """`_on_quick_translate_open_translator` decides what crosses over."""

    @staticmethod
    def _app(translated):
        app = TranslatorApp.__new__(TranslatorApp)
        app.current_original = "Guten Morgen"
        app.current_translated = translated
        app.current_target_lang = "English"
        app.close_quick_translate = lambda: None
        app.screenshot_handler = type('S', (), {
            'get_pending_screenshot': lambda self: None,
            'clear_pending_screenshot': lambda self: None,
        })()
        captured = {}
        app.show_popup = lambda original, trans, lang, **kw: captured.update(
            original=original, translated=trans, lang=lang)
        return app, captured

    def test_a_failure_notice_does_not_cross_over(self):
        app, captured = self._app(ERROR)
        app._on_quick_translate_open_translator()
        assert captured['original'] == "Guten Morgen"
        assert captured['translated'] == ""

    def test_a_real_translation_still_does(self):
        app, captured = self._app(GOOD)
        app._on_quick_translate_open_translator()
        assert captured['translated'] == GOOD

    def test_the_source_text_always_crosses_over(self):
        for translated in (ERROR, NO_TEXT, GOOD):
            app, captured = self._app(translated)
            app._on_quick_translate_open_translator()
            assert captured['original'] == "Guten Morgen"
            assert captured['lang'] == "English"
