"""
Tests for Dictionary mode's flow - the one implementation both buttons use.

Until 2026-10-15 the main window (`src/ui/dictionary_popup.py`) and the
quick-translate popup (`src/ui/quick_translate.py`) each carried a copy of this
flow (DEFERRED D13). The copies had drifted: the main window's dialogs used
transient() + grab_set() (D15), and a failed lookup raised NameError in both
instead of showing its message (D14). The popup now hands its text, its target
language and itself - the window to open beside - to `DictionaryPopup`.

Covered here:
- wiring from either button down to `TranslationService.dictionary_lookup()`,
  with the source language and the text the words came from (Phase J1);
- where the word window and the dialogs go (pure geometry);
- D14: a failed lookup shows its message and stops the Lookup animation;
- D15: no dialog grabs or goes transient.

Everything but the geometry needs a Tk display (see the `tk_root` fixture).
"""
import inspect
import re
import time
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.core.nlp_manager import nlp_manager
from src.ui import dictionary_popup as flow_module
from src.ui.dictionary_popup import (WORD_WINDOW_ANCHOR_GAP, WORD_WINDOW_EXPANDED_SIZE,
                                     WORD_WINDOW_MARGIN, WORD_WINDOW_SIZE, DictionaryPopup,
                                     dialog_geometry, word_window_geometry)

JP_TEXT = "昨日は雨でした。友達に手紙を書きました。手紙は長かったです。"
WORK_AREA = (0, 0, 1920, 1040)


# --------------------------------------------------------------------------- #
# Placement (pure)
# --------------------------------------------------------------------------- #
class TestWordWindowGeometry:
    def test_without_an_anchor_it_is_centred_in_the_work_area(self):
        assert word_window_geometry(WORD_WINDOW_SIZE, WORK_AREA) == (
            700, 350, (1920 - 700) // 2, (1040 - 350) // 2)

    def test_it_opens_below_the_popup(self):
        anchor = (300, 100, 600, 200)                       # x, y, width, height
        assert word_window_geometry(WORD_WINDOW_SIZE, WORK_AREA, anchor) == (
            700, 350, 300, 100 + 200 + WORD_WINDOW_ANCHOR_GAP)

    def test_it_goes_above_the_popup_when_there_is_no_room_below(self):
        anchor = (300, 600, 600, 300)                       # popup ends at y=900
        _, _, _, y = word_window_geometry(WORD_WINDOW_SIZE, WORK_AREA, anchor)
        assert y == 600 - 350 - WORD_WINDOW_ANCHOR_GAP

    def test_it_is_pinned_to_the_bottom_when_neither_side_fits(self):
        anchor = (300, 200, 600, 700)                       # no room above or below
        _, _, _, y = word_window_geometry(WORD_WINDOW_SIZE, WORK_AREA, anchor)
        assert y == 1040 - WORD_WINDOW_MARGIN - 350

    def test_it_stays_inside_the_right_edge(self):
        anchor = (1700, 100, 200, 200)
        _, _, x, _ = word_window_geometry(WORD_WINDOW_SIZE, WORK_AREA, anchor)
        assert x == 1920 - WORD_WINDOW_MARGIN - 700

    def test_it_stays_on_a_second_monitor(self):
        area = (1920, 0, 3840, 1040)
        _, _, x, y = word_window_geometry(WORD_WINDOW_SIZE, area)
        assert 1920 + WORD_WINDOW_MARGIN <= x <= 3840 - WORD_WINDOW_MARGIN - 700
        assert WORD_WINDOW_MARGIN <= y

    def test_a_small_screen_shrinks_the_expanded_window(self):
        area = (0, 0, 1280, 680)
        assert word_window_geometry(WORD_WINDOW_EXPANDED_SIZE, area) == (
            1000, 680 - 2 * WORD_WINDOW_MARGIN, (1280 - 1000) // 2, WORD_WINDOW_MARGIN)


class TestDialogGeometry:
    def test_a_dialog_is_centred_on_the_pointer(self):
        assert dialog_geometry((400, 280), (900, 500), WORK_AREA) == (400, 280, 700, 360)

    def test_a_dialog_near_a_corner_stays_inside_the_work_area(self):
        assert dialog_geometry((400, 280), (10, 1030), WORK_AREA) == (400, 280, 0, 760)


# --------------------------------------------------------------------------- #
# Fakes and fixtures
# --------------------------------------------------------------------------- #
class _FakeButton:
    def configure(self, **kwargs):
        pass


class _FakeWordFrame:
    """Stands in for WordButtonFrame: records the lookup callbacks it is given."""
    created = []

    def __init__(self, parent, text, **kwargs):
        self.text = text
        self.kwargs = kwargs
        self.frame = tk.Frame(parent)
        self.expand_btn = _FakeButton()
        _FakeWordFrame.created.append(self)

    def set_exit_callback(self, callback):
        pass

    def pack(self, **kwargs):
        pass

    def insert_custom_widget(self, widget):
        pass

    def set_drop_target(self, target):
        pass


class _FakeBoxes:
    """Stands in for CustomWordBoxesFrame: `phrases` is what the boxes hold."""
    phrases = []

    def __init__(self, parent, language=None, furigana_enabled=True):
        self.frame = tk.Frame(parent)

    def get_all_phrases(self):
        return list(_FakeBoxes.phrases)


class _SyncThread:
    """threading.Thread that runs its target on start(), so the call is visible."""

    def __init__(self, target=None, daemon=None, **kwargs):
        self._target = target

    def start(self):
        self._target()


@pytest.fixture
def fake_ui(tk_root, monkeypatch):
    """Replace the word area and custom boxes; close every window a test opens."""
    _FakeWordFrame.created = []
    _FakeBoxes.phrases = []
    monkeypatch.setattr('src.ui.dictionary_mode.WordButtonFrame', _FakeWordFrame)
    monkeypatch.setattr('src.ui.custom_word_boxes.CustomWordBoxesFrame', _FakeBoxes)
    monkeypatch.setattr('src.ui.quick_translate.get_monitor_work_area', lambda x, y: WORK_AREA)
    monkeypatch.setattr(flow_module, 'set_dark_title_bar', lambda window: None)
    monkeypatch.setattr('threading.Thread', _SyncThread)
    before = set(tk_root.winfo_children())
    yield _FakeWordFrame
    tk_root.update()                      # let scheduled result callbacks run
    for widget in set(tk_root.winfo_children()) - before:
        try:
            widget.destroy()
        except tk.TclError:
            pass


@pytest.fixture
def nlp(monkeypatch):
    """What detection answers and which packs are installed, per test."""
    state = SimpleNamespace(detected=("Japanese", 1.0),
                            installed=["Japanese", "Chinese (Simplified)", "English"])
    monkeypatch.setattr(nlp_manager, 'detect_language', lambda text: state.detected)
    monkeypatch.setattr(nlp_manager, 'is_any_installed', lambda: bool(state.installed))
    monkeypatch.setattr(nlp_manager, 'is_installed', lambda lang: lang in state.installed)
    monkeypatch.setattr(nlp_manager, 'get_installed_languages', lambda: list(state.installed))
    return state


@pytest.fixture
def dictionary(tk_root, fake_ui):
    """The one Dictionary-mode flow; the main window's language is English."""
    service = MagicMock()
    service.get_trial_info.return_value = None
    service.dictionary_lookup.return_value = "## [手紙]"
    config = MagicMock()
    config.get_furigana_enabled.return_value = True
    flow = DictionaryPopup(tk_root, config, service, MagicMock(), MagicMock())
    flow.settings_tabs = []
    flow.configure_callbacks(on_show_settings_tab=flow.settings_tabs.append,
                             get_selected_language=lambda: "English")
    return flow


@pytest.fixture
def popup(tk_root, dictionary):
    """The quick-translate popup, its Dictionary button wired as TranslatorApp wires it.

    Its target language is French - not the main window's English - so a test can
    tell whose language reached the lookup.
    """
    from src.app import TranslatorApp
    from src.ui.quick_translate import QuickTranslateManager
    config = MagicMock()
    config.get_furigana_enabled.return_value = True
    mgr = QuickTranslateManager(tk_root, config)
    app = TranslatorApp.__new__(TranslatorApp)
    app.dictionary_popup = dictionary
    mgr.configure_callbacks(on_open_dictionary=app._on_quick_translate_open_dictionary)
    mgr._current_original = JP_TEXT
    mgr._current_target_lang = "French"
    return mgr


def _toplevels(root, title_prefix):
    return [w for w in root.winfo_children()
            if isinstance(w, tk.Toplevel) and w.winfo_exists()
            and w.title().startswith(title_prefix)]


def _invoke_button(root, text):
    """Invoke the first button labelled `text` in any open window."""
    def walk(widget):
        for child in widget.winfo_children():
            try:
                if child.winfo_class() in ('TButton', 'Button') and child.cget('text') == text:
                    return child
            except tk.TclError:
                pass
            found = walk(child)
            if found is not None:
                return found
        return None

    button = walk(root)
    assert button is not None, f"no '{text}' button found"
    button.invoke()


def _pump(root, ms=300):
    """Run Tk's event loop long enough for an after(50) callback to fire."""
    deadline = time.time() + ms / 1000
    while time.time() < deadline:
        root.update()
        time.sleep(0.01)


# --------------------------------------------------------------------------- #
# Wiring: the main window's button
# --------------------------------------------------------------------------- #
class TestMainWindowWiring:
    def test_the_input_text_is_looked_up_in_the_selected_language(self, dictionary, nlp):
        dictionary.open_from_text(JP_TEXT)
        _FakeWordFrame.created[-1].kwargs['on_lookup'](["手紙"])
        dictionary.translation_service.dictionary_lookup.assert_called_once_with(
            ["手紙"], "English", source_language="Japanese", context=JP_TEXT)

    def test_detected_japanese_and_the_text_reach_the_lookup(self, dictionary):
        dictionary._open_with_language(JP_TEXT, "Japanese")
        _FakeWordFrame.created[-1].kwargs['on_lookup'](["手紙"])
        dictionary.translation_service.dictionary_lookup.assert_called_once_with(
            ["手紙"], "English", source_language="Japanese", context=JP_TEXT)

    def test_detected_chinese_lets_the_model_decide(self, dictionary):
        dictionary._open_with_language("勉強", "Chinese (Simplified)")
        _FakeWordFrame.created[-1].kwargs['on_lookup'](["勉強"])
        lookup = dictionary.translation_service.dictionary_lookup.call_args
        assert lookup.kwargs['source_language'] is None
        assert lookup.kwargs['context'] == "勉強"

    def test_a_language_the_user_picked_is_stated(self, dictionary):
        dictionary._open_with_language("勉強", "Chinese (Simplified)", user_chosen=True)
        _FakeWordFrame.created[-1].kwargs['on_lookup'](["勉強"])
        lookup = dictionary.translation_service.dictionary_lookup.call_args
        assert lookup.kwargs['source_language'] == "Chinese (Simplified)"

    def test_custom_box_phrases_carry_the_same_language(self, dictionary):
        _FakeBoxes.phrases = ["手紙"]
        dictionary._open_with_language(JP_TEXT, "Japanese")
        _FakeWordFrame.created[-1].kwargs['on_no_selection']()
        dictionary.translation_service.dictionary_lookup.assert_called_once_with(
            ["手紙"], "English", source_language="Japanese", context=JP_TEXT)

    def test_the_selection_dialog_marks_its_choice_as_the_users(
            self, tk_root, dictionary, nlp, monkeypatch):
        nlp.installed = ["Japanese", "Chinese (Simplified)"]
        opened = []
        monkeypatch.setattr(dictionary, '_open_with_language',
                            lambda *args, **kwargs: opened.append((args, kwargs)))
        dictionary._show_language_selection_dialog("勉強", "Japanese")
        _invoke_button(tk_root, "Confirm")
        _pump(tk_root)
        assert opened == [(("勉強", "Japanese"),
                           {'user_chosen': True, 'target_language': None, 'anchor': None})]

    def test_the_word_window_is_centred_without_an_anchor(self, dictionary, monkeypatch):
        seen = []
        real = flow_module.word_window_geometry
        monkeypatch.setattr(flow_module, 'word_window_geometry',
                            lambda size, area, anchor=None: seen.append(anchor)
                            or real(size, area, anchor))
        dictionary._open_with_language(JP_TEXT, "Japanese")
        assert seen == [None]


# --------------------------------------------------------------------------- #
# Wiring: the quick-translate popup's button goes through the same flow (D13)
# --------------------------------------------------------------------------- #
class TestPopupWiring:
    def test_detected_japanese_and_the_text_reach_the_lookup(self, popup, dictionary, nlp):
        popup._open_dictionary_popup()
        _FakeWordFrame.created[-1].kwargs['on_lookup'](["手紙"])
        dictionary.translation_service.dictionary_lookup.assert_called_once_with(
            ["手紙"], "French", source_language="Japanese", context=JP_TEXT)

    def test_detected_chinese_lets_the_model_decide(self, popup, dictionary, nlp):
        popup._current_original = "勉強"
        nlp.detected = ("Chinese (Simplified)", 1.0)
        popup._open_dictionary_popup()
        _FakeWordFrame.created[-1].kwargs['on_lookup'](["勉強"])
        lookup = dictionary.translation_service.dictionary_lookup.call_args
        assert lookup.kwargs['source_language'] is None
        assert lookup.kwargs['context'] == "勉強"

    def test_a_language_the_user_picked_is_stated(self, tk_root, popup, dictionary, nlp):
        popup._current_original = "勉強"
        nlp.detected = ("", 0.0)
        nlp.installed = ["Chinese (Simplified)", "Japanese"]
        popup._open_dictionary_popup()
        _invoke_button(tk_root, "Confirm")                  # the first installed pack
        _pump(tk_root)
        _FakeWordFrame.created[-1].kwargs['on_lookup'](["勉強"])
        dictionary.translation_service.dictionary_lookup.assert_called_once_with(
            ["勉強"], "French", source_language="Chinese (Simplified)", context="勉強")

    def test_custom_box_phrases_carry_the_same_language(self, popup, dictionary, nlp):
        _FakeBoxes.phrases = ["手紙"]
        popup._open_dictionary_popup()
        _FakeWordFrame.created[-1].kwargs['on_no_selection']()
        dictionary.translation_service.dictionary_lookup.assert_called_once_with(
            ["手紙"], "French", source_language="Japanese", context=JP_TEXT)

    def test_the_original_is_analysed_not_the_translation(self, popup, nlp):
        popup._current_translation = "I wrote a letter to a friend."
        popup._open_dictionary_popup()
        assert _FakeWordFrame.created[-1].text == JP_TEXT

    def test_without_an_original_the_translation_is_analysed(self, popup, dictionary, nlp):
        popup._current_original = ""
        popup._current_translation = JP_TEXT
        popup._open_dictionary_popup()
        assert _FakeWordFrame.created[-1].text == JP_TEXT

    def test_the_word_window_opens_beside_the_popup(self, tk_root, popup, nlp, monkeypatch):
        popup.popup = tk.Toplevel(tk_root)
        popup.popup.geometry("600x200+300+100")
        tk_root.update()
        seen = []
        real = flow_module.word_window_geometry
        monkeypatch.setattr(flow_module, 'word_window_geometry',
                            lambda size, area, anchor=None: seen.append(anchor)
                            or real(size, area, anchor))
        popup._open_dictionary_popup()
        window = popup.popup
        assert seen == [(window.winfo_x(), window.winfo_y(),
                         window.winfo_width(), window.winfo_height())]

    def test_the_selection_dialog_keeps_the_popups_target_and_anchor(
            self, tk_root, popup, dictionary, nlp, monkeypatch):
        nlp.detected = ("", 0.0)
        opened = []
        monkeypatch.setattr(dictionary, '_open_with_language',
                            lambda *args, **kwargs: opened.append((args, kwargs)))
        popup._open_dictionary_popup()
        _invoke_button(tk_root, "Confirm")
        _pump(tk_root)
        assert opened[0][1] == {'user_chosen': True, 'target_language': "French",
                                'anchor': popup.popup}


class TestOneImplementation:
    def test_the_popup_keeps_no_copy_of_the_flow(self):
        from src.ui.quick_translate import QuickTranslateManager
        for name in ('_show_nlp_required_message', '_show_language_selection_dialog',
                     '_open_dictionary_with_language', '_try_open_dictionary_tab'):
            assert not hasattr(QuickTranslateManager, name), name

    def test_the_app_wires_the_popup_button_to_the_shared_flow(self):
        from src.app import TranslatorApp
        source = inspect.getsource(TranslatorApp.__init__)
        assert 'on_open_dictionary=self._on_quick_translate_open_dictionary' in source
        app = TranslatorApp.__new__(TranslatorApp)
        app.dictionary_popup = MagicMock()
        anchor = object()
        app._on_quick_translate_open_dictionary("勉強", "French", anchor)
        app.dictionary_popup.open_from_text.assert_called_once_with(
            "勉強", target_language="French", anchor=anchor)


# --------------------------------------------------------------------------- #
# The lookup: result, and D14 - a failure shows its message
# --------------------------------------------------------------------------- #
class TestLookup:
    @pytest.fixture
    def callback_errors(self, tk_root, monkeypatch):
        """Exceptions raised inside Tk callbacks - the D14 NameError surfaced here."""
        errors = []
        monkeypatch.setattr(tk_root, 'report_callback_exception',
                            lambda exc, val, tb: errors.append(val))
        return errors

    def test_a_result_opens_the_result_window(self, tk_root, dictionary, callback_errors):
        dictionary._do_lookup(["手紙"], "English", source_language="Japanese",
                              context_text=JP_TEXT)
        _pump(tk_root, 100)
        dictionary.quick_translate_manager.show_dictionary_result.assert_called_once_with(
            "## [手紙]", "English", None, ["手紙"], source_lang="Japanese")
        assert callback_errors == []

    def test_an_unstated_source_reaches_the_result_window_as_none(self, tk_root, dictionary):
        dictionary._do_lookup(["勉強"], "English")
        _pump(tk_root, 100)
        result = dictionary.quick_translate_manager.show_dictionary_result.call_args
        assert result.kwargs['source_lang'] is None

    def test_the_word_windows_source_reaches_the_result_window(self, tk_root, dictionary):
        dictionary._open_with_language(JP_TEXT, "Japanese")
        _FakeWordFrame.created[-1].kwargs['on_lookup'](["手紙"])
        _pump(tk_root, 100)
        result = dictionary.quick_translate_manager.show_dictionary_result.call_args
        assert result.kwargs['source_lang'] == "Japanese"

    def test_a_failed_lookup_shows_its_message(self, tk_root, dictionary, callback_errors):
        dictionary.translation_service.dictionary_lookup.side_effect = RuntimeError("quota")
        dictionary._do_lookup(["手紙"], "English")
        _pump(tk_root, 100)
        assert dictionary.toast.show_error.call_args_list == [call("Lookup failed: quota")]
        assert callback_errors == []

    def test_a_failed_lookup_stops_the_lookup_animation(self, tk_root, dictionary,
                                                         callback_errors):
        dictionary.translation_service.dictionary_lookup.side_effect = RuntimeError("quota")
        dictionary._do_lookup(["手紙"], "English")
        _pump(tk_root, 100)
        dictionary.quick_translate_manager.stop_dictionary_animation.assert_called_once_with()

    def test_a_failure_after_the_call_is_reported_too(self, tk_root, dictionary,
                                                       callback_errors):
        dictionary.translation_service.get_trial_info.side_effect = RuntimeError("trial")
        dictionary._do_lookup(["手紙"], "English")
        _pump(tk_root, 100)
        assert dictionary.toast.show_error.call_args_list == [call("Lookup failed: trial")]
        assert callback_errors == []

    def test_words_that_filter_to_nothing_stop_the_animation(self, dictionary):
        dictionary._do_lookup(["...", "!!"], "English")
        dictionary.translation_service.dictionary_lookup.assert_not_called()
        dictionary.quick_translate_manager.stop_dictionary_animation.assert_called_once_with()
        assert "No valid words" in dictionary.toast.show_info.call_args.args[0]


# --------------------------------------------------------------------------- #
# Dialogs: D15 - never transient() + grab_set()
# --------------------------------------------------------------------------- #
class TestDialogs:
    @pytest.fixture
    def modal_calls(self, monkeypatch):
        calls = []
        monkeypatch.setattr(tk.Misc, 'grab_set', lambda self: calls.append('grab_set'))
        monkeypatch.setattr(tk.Wm, 'transient', lambda self, master=None: calls.append('transient'))
        monkeypatch.setattr(tk.Wm, 'wm_transient',
                            lambda self, master=None: calls.append('wm_transient'))
        return calls

    def test_the_no_pack_dialog_does_not_grab(self, tk_root, dictionary, nlp, modal_calls):
        nlp.installed = []
        dictionary.open_from_text(JP_TEXT)
        assert _toplevels(tk_root, "No Language Pack Installed")
        assert modal_calls == []

    def test_the_selection_dialog_does_not_grab(self, tk_root, dictionary, nlp, modal_calls):
        nlp.detected = ("", 0.0)
        dictionary.open_from_text("勉強")
        assert _toplevels(tk_root, "Select Source Language")
        assert modal_calls == []

    def test_a_dialog_is_raised_then_lets_go_of_topmost(self, tk_root, dictionary, nlp):
        nlp.detected = ("", 0.0)
        dictionary.open_from_text("勉強")
        dialog = _toplevels(tk_root, "Select Source Language")[0]
        assert dialog.attributes('-topmost')
        _pump(tk_root, 300)
        assert not dialog.attributes('-topmost')

    def test_the_module_calls_neither(self):
        source = inspect.getsource(flow_module)
        assert not re.search(r'\.(grab_set|transient|wm_transient)\(', source)

    def test_the_no_pack_dialog_opens_dictionary_settings(self, tk_root, popup, dictionary,
                                                          nlp):
        nlp.installed = []
        popup._open_dictionary_popup()                       # from the popup's button too
        _invoke_button(tk_root, "Open Dictionary Settings")
        assert dictionary.settings_tabs == ["Dictionary"]
