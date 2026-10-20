"""
Tests for the user's own answer about kanji-only text (the post-J12 follow-ups, K3-K5).

Decision 22 put the user last in line - evidence, then a model, then the user -
but only the popup's chooser ever kept the user's answer, and only because it
re-translated. K3 keeps the Dictionary dialog's answer too: as the text's verdict
for this session (`TranslationService.remember_user_source`) and on History's
entries of that exact text (`HistoryManager.set_source_verdict`), where it
replaces a model's, since the user's pick outranks it. K4 lets the user change a
term a model placed - 汽車 and 工作 come back Chinese, confidently - from the
popup: "Kanji-only text - read as Chinese. [Read as Japanese]".

The widget tests use the `tk_root` fixture, which skips without a display.
"""
import inspect
import logging
import tkinter as tk
from unittest.mock import MagicMock

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.core.history import HistoryManager
from src.core.lang_id import CHINESE_SIMPLIFIED, CHINESE_TRADITIONAL, JAPANESE
from src.core.source_marker import (ROW_ASK, ROW_CHANGE, language_label, other_language,
                                    source_row)
from src.core.translation import TranslationService
from src.ui.quick_translate import QuickTranslateManager


class HistoryConfig:
    def __init__(self, history=None):
        self._store = {'history': list(history or []), 'history_enabled': True}
        self.saves = 0

    def get(self, key, default=None):
        return self._store.get(key, default)

    def set(self, key, value):
        self.saves += 1
        self._store[key] = value


def entry(original, verdict=None, label="Unknown", target="English"):
    item = {'id': original + target, 'original': original, 'translated': "x",
            'target_lang': target, 'source_lang': label, 'source_type': 'text'}
    if verdict:
        item['source_verdict'] = verdict
    return item


def make_service(history=None):
    svc = TranslationService.__new__(TranslationService)
    svc.history_manager = HistoryManager(HistoryConfig(history))
    return svc


# --------------------------------------------------------------------------- #
# HistoryManager.set_source_verdict
# --------------------------------------------------------------------------- #
class TestHistory:
    def test_every_entry_of_the_text_gets_the_verdict_and_the_label(self):
        manager = HistoryManager(HistoryConfig([entry("勉強"), entry("勉強", target="French"),
                                                entry("工作")]))
        assert manager.set_source_verdict("勉強", JAPANESE) == 2
        rows = {(e['original'], e['target_lang']): e for e in manager.get_history()}
        assert rows[("勉強", "English")]['source_verdict'] == JAPANESE
        assert rows[("勉強", "French")]['source_lang'] == JAPANESE
        assert 'source_verdict' not in rows[("工作", "English")]

    def test_it_replaces_a_models_verdict(self):
        manager = HistoryManager(HistoryConfig([entry("汽車", CHINESE_SIMPLIFIED,
                                                      CHINESE_SIMPLIFIED)]))
        manager.set_source_verdict("汽車", JAPANESE)
        assert manager.find_source_verdict("汽車") == JAPANESE

    def test_only_the_exact_text_matches(self):
        manager = HistoryManager(HistoryConfig([entry("勉強する")]))
        assert manager.set_source_verdict("勉強", JAPANESE) == 0

    def test_nothing_changed_means_nothing_saved(self):
        config = HistoryConfig([entry("勉強", JAPANESE, JAPANESE)])
        manager = HistoryManager(config)
        assert manager.set_source_verdict("勉強", JAPANESE) == 0
        assert manager.set_source_verdict("", JAPANESE) == 0
        assert manager.set_source_verdict("勉強", "") == 0
        assert config.saves == 0

    def test_a_change_is_saved(self):
        config = HistoryConfig([entry("勉強")])
        HistoryManager(config).set_source_verdict("勉強", JAPANESE)
        assert config.saves == 1


# --------------------------------------------------------------------------- #
# TranslationService.remember_user_source
# --------------------------------------------------------------------------- #
class TestService:
    def test_the_answer_is_the_texts_verdict(self):
        svc = make_service()
        assert svc.remember_user_source("勉強", JAPANESE) == JAPANESE
        assert svc.source_verdict("勉強") == JAPANESE
        assert svc.source_language("勉強") == JAPANESE

    @pytest.mark.parametrize("given, kept", [
        ("Japanese", JAPANESE),
        ("Chinese (Simplified)", CHINESE_SIMPLIFIED),
        ("Chinese (Traditional)", CHINESE_TRADITIONAL),
        ("Chinese", CHINESE_SIMPLIFIED),
    ])
    def test_japanese_and_chinese_are_kept(self, given, kept):
        svc = make_service()
        assert svc.remember_user_source("工作", given) == kept
        assert svc.source_verdict("工作") == kept

    @pytest.mark.parametrize("given", ["English", "Korean", "", None, "Unknown"])
    def test_anything_else_says_nothing_about_the_kanji(self, given):
        svc = make_service([entry("勉強")])
        assert svc.remember_user_source("勉強", given) is None
        assert svc.source_verdict("勉強") is None
        assert 'source_verdict' not in svc.history_manager.get_history()[0]

    def test_no_text_keeps_nothing(self):
        svc = make_service()
        assert svc.remember_user_source("", JAPANESE) is None

    def test_it_reaches_history_and_survives_a_restart(self):
        history = [entry("勉強")]
        make_service(history).remember_user_source("勉強", JAPANESE)
        restarted = TranslationService.__new__(TranslationService)
        restarted.history_manager = HistoryManager(HistoryConfig(history))
        assert restarted.source_verdict("勉強") == JAPANESE

    def test_it_outranks_a_models_verdict(self):
        svc = make_service([entry("汽車", CHINESE_SIMPLIFIED, CHINESE_SIMPLIFIED)])
        svc._remember_source_verdict("汽車", CHINESE_SIMPLIFIED)       # the model, earlier
        svc.remember_user_source("汽車", JAPANESE)
        assert svc.source_verdict("汽車") == JAPANESE
        assert svc.history_manager.find_source_verdict("汽車") == JAPANESE

    def test_it_leaves_the_last_translations_verdict_alone(self):
        svc = make_service()
        svc._remember_source_verdict("先生", CHINESE_SIMPLIFIED)
        svc.remember_user_source("勉強", JAPANESE)
        assert svc.last_source_language == CHINESE_SIMPLIFIED

    def test_without_history_it_still_holds_for_the_session(self):
        svc = TranslationService.__new__(TranslationService)
        svc.history_manager = None
        assert svc.remember_user_source("勉強", JAPANESE) == JAPANESE
        assert svc._source_verdict_store()["勉強"] == JAPANESE

    def test_the_log_line_names_no_text(self, caplog):
        svc = make_service()
        with caplog.at_level(logging.INFO):
            svc.remember_user_source("秘密の勉強", JAPANESE)
        assert "[LangID] user settled source=Japanese chars=5" in caplog.text
        assert "秘密" not in caplog.text


# --------------------------------------------------------------------------- #
# The main window hears about it
# --------------------------------------------------------------------------- #
class TestApp:
    def make_app(self):
        from src.app import TranslatorApp
        app = TranslatorApp.__new__(TranslatorApp)
        app._schedule_reading_refresh = MagicMock()
        return app

    def test_the_reading_pane_reads_the_input_again(self):
        app = self.make_app()
        app._reading_pane_alive = lambda: True
        app._on_source_chosen("勉強")
        app._schedule_reading_refresh.assert_called_once_with(delay_ms=1)

    def test_nothing_happens_with_the_main_window_closed(self):
        app = self.make_app()
        app._reading_pane_alive = lambda: False
        app._on_source_chosen("勉強")
        app._schedule_reading_refresh.assert_not_called()

    def test_the_app_wires_the_dictionary(self):
        from src.app import TranslatorApp
        source = inspect.getsource(TranslatorApp.__init__)
        assert 'on_source_chosen=self._on_source_chosen' in source


# --------------------------------------------------------------------------- #
# K4 - which row a surface shows (pure)
# --------------------------------------------------------------------------- #
class TestSourceRow:
    @pytest.mark.parametrize("text, verdict, expected", [
        ("汽車", None, ROW_ASK),                       # nobody placed it
        ("汽車", "Unknown", ROW_ASK),                  # "Unknown" is no verdict
        ("汽車", "English", ROW_ASK),                  # nor is a language that is not CJK
        ("汽車", CHINESE_SIMPLIFIED, ROW_CHANGE),      # a model placed a term
        ("工作", CHINESE_TRADITIONAL, ROW_CHANGE),
        ("勉強", JAPANESE, ROW_CHANGE),
        ("東京大学", "Chinese", ROW_CHANGE),            # the marker's own spelling
        ("東京 大学", JAPANESE, None),                  # whitespace: a sentence
        ("東京、大阪", JAPANESE, None),                 # punctuation: a sentence
        ("這是我的書。", CHINESE_TRADITIONAL, None),
        ("東京、大阪", None, ROW_ASK),                  # an unplaced sentence still asks
        ("勉強します", None, None),                     # kana settles it
        ("我们", JAPANESE, None),                       # so does a Chinese-only glyph
        ("I love 東京", None, None),                    # not mostly CJK
        ("", None, None),
        (None, JAPANESE, None),
    ])
    def test_which_row(self, text, verdict, expected):
        assert source_row(text, verdict) == expected

    @pytest.mark.parametrize("language, other", [
        (JAPANESE, CHINESE_SIMPLIFIED), (CHINESE_SIMPLIFIED, JAPANESE),
        (CHINESE_TRADITIONAL, JAPANESE), ("Chinese", JAPANESE)])
    def test_the_other_language(self, language, other):
        assert other_language(language) == other

    @pytest.mark.parametrize("language, label", [
        (JAPANESE, "Japanese"), (CHINESE_SIMPLIFIED, "Chinese"),
        (CHINESE_TRADITIONAL, "Chinese")])
    def test_a_row_names_no_chinese_script(self, language, label):
        assert language_label(language) == label


# --------------------------------------------------------------------------- #
# K4 - the popup's row for a term a model placed
# --------------------------------------------------------------------------- #
class PopupConfig:
    def get_furigana_enabled(self):
        return True

    def get_quick_replace(self):
        return False


@pytest.fixture
def popup(tk_root):
    mgr = QuickTranslateManager(tk_root, PopupConfig())
    mgr._last_mouse_x, mgr._last_mouse_y = 500, 300
    mgr.choices = []
    mgr.configure_callbacks(on_choose_source=mgr.choices.append)
    yield mgr
    mgr.close()


def row_parts(row):
    labels = [child.cget('text') for child in row.winfo_children()
              if child.winfo_class() in ('TLabel', 'Label')]
    buttons = [child for child in row.winfo_children() if isinstance(child, tk.Button)]
    return labels, buttons


class TestPopupChangeRow:
    def test_a_chinese_verdict_offers_japanese(self, popup):
        popup.show("Car", "English", None, "汽車", source_lang=CHINESE_SIMPLIFIED)
        labels, buttons = row_parts(popup.popup_source_chooser)
        assert labels == ["Kanji-only text - read as Chinese."]
        assert [b.cget('text') for b in buttons] == ["Read as Japanese"]
        buttons[0].invoke()
        assert popup.choices == [JAPANESE]

    def test_a_japanese_verdict_offers_chinese(self, popup):
        popup.show("Study", "English", None, "勉強", source_lang=JAPANESE)
        labels, buttons = row_parts(popup.popup_source_chooser)
        assert labels == ["Kanji-only text - read as Japanese."]
        buttons[0].invoke()
        assert popup.choices == [CHINESE_SIMPLIFIED]

    def test_the_row_is_in_the_height_budget(self, popup, tk_root):
        def height():
            tk_root.update()      # the popup takes its height once laid out (Decision 34)
            return int(popup.popup.geometry().split('+')[0].split('x')[1])
        popup.show("Car", "English", None, "Kisha")
        without = height()
        popup.show("Car", "English", None, "汽車", source_lang=CHINESE_SIMPLIFIED)
        with_row = height()
        row = popup.popup_source_chooser.winfo_reqheight() + 8      # with its pady above
        assert with_row == without + row

    def test_a_sentence_a_model_placed_gets_no_row(self, popup):
        popup.show("This is my book.", "English", None, "這是我的書。",
                   source_lang=CHINESE_TRADITIONAL)
        assert popup.popup_source_chooser is None

    def test_a_grammar_fix_gets_no_row(self, popup):
        popup.show("汽車", "Grammar", None, "汽車", is_grammar=True,
                   source_lang=CHINESE_SIMPLIFIED)
        assert popup.popup_source_chooser is None

    def test_the_unplaced_row_is_unchanged(self, popup):
        popup.show("Teacher", "English", None, "先生")
        labels, buttons = row_parts(popup.popup_source_chooser)
        assert labels == ["Kanji-only text - read it as:"]
        assert [b.cget('text') for b in buttons] == ["Japanese", "Chinese"]


class _SyncThread:
    def __init__(self, target=None, daemon=None, **kwargs):
        self._target = target

    def start(self):
        self._target()


class TestPopupChoiceIsKept:
    def test_the_answer_is_kept_before_the_request(self, monkeypatch):
        from src.app import TranslatorApp
        monkeypatch.setattr('threading.Thread', _SyncThread)
        app = TranslatorApp.__new__(TranslatorApp)
        app.quick_translate_manager = MagicMock()
        app.root = MagicMock()
        app.translation_service = MagicMock()
        app.current_original, app.current_target_lang = "汽車", "English"
        app._on_quick_translate_choose_source(JAPANESE)
        names = [name for name, _args, _kwargs in app.translation_service.mock_calls]
        assert names == ['remember_user_source', 'redo_translation']
        app.translation_service.remember_user_source.assert_called_once_with("汽車", JAPANESE)


# --------------------------------------------------------------------------- #
# K5 - the main window's row, beside "Original:"
# --------------------------------------------------------------------------- #
def pump(root, ms=100):
    import time
    deadline = time.time() + ms / 1000
    while time.time() < deadline:
        root.update()
        time.sleep(0.01)


@pytest.fixture
def main_window(tk_root, monkeypatch):
    """The real main window (`show_popup`) on a TranslatorApp built with __new__ -
    __init__ would register hotkeys and a tray icon - with a real verdict memory."""
    from src.app import TranslatorApp
    from src.constants import LANGUAGES
    created = []

    def build(original, translated="", verdicts=None, furigana=True):
        app = TranslatorApp.__new__(TranslatorApp)
        app.root = tk_root
        app.popup = None
        config = MagicMock()
        config.has_any_vision_capable.return_value = False
        config.has_any_file_capable.return_value = False
        config.get_furigana_enabled.return_value = furigana
        config.get_furigana_reading_pane.return_value = True
        config.get_fix_grammar_enabled.return_value = True
        app.config = config
        app.translation_service = make_service()
        for text, verdict in (verdicts or {}).items():
            app.translation_service._remember_source_verdict(text, verdict)
        app.selected_language = "English"
        app.filtered_languages = LANGUAGES.copy()
        app.dictionary_popup = MagicMock()
        app.toast = MagicMock()
        app.drop_handler = MagicMock()
        app.show_popup(original, translated, "English", force_new=True)
        created.append(app)
        settle(app)
        return app

    yield build
    for app in created:
        try:
            app.popup.destroy()
        except (tk.TclError, AttributeError):
            pass


def settle(app, text=None):
    """Set the input (as typing would) and refresh what depends on it, now."""
    if text is not None:
        app.original_text.delete('1.0', tk.END)
        app.original_text.insert('1.0', text)
    app._refresh_reading_pane()
    app.root.update_idletasks()


def shown(app):
    """(label, [buttons]) of the row, or None when it is not shown."""
    if not app._source_row.winfo_manager():
        return None
    labels, buttons = row_parts(app._source_row)
    return labels[0], [b.cget('text') for b in buttons]


def click(app, text):
    _labels, buttons = row_parts(app._source_row)
    next(b for b in buttons if b.cget('text') == text).invoke()


class TestMainWindowRow:
    def test_it_sits_beside_original_without_growing_the_header(self, main_window, tk_root):
        app = main_window("汽車", verdicts={"汽車": CHINESE_SIMPLIFIED})
        tk_root.update()
        header = app._source_row.master
        assert header is app._original_header
        assert header.winfo_height() == app.dict_btn.winfo_height()

    def test_untranslated_unplaced_kanji_asks_nothing(self, main_window):
        app = main_window("汽車")
        assert shown(app) is None

    def test_a_translation_without_a_verdict_asks(self, main_window):
        # Open Translator hands over the popup's translation of exactly this text.
        app = main_window("汽車", "Car")
        assert shown(app) == ("Kanji-only text - read it as:", ["Japanese", "Chinese"])

    def test_a_placed_term_offers_the_other_language(self, main_window):
        app = main_window("汽車", verdicts={"汽車": CHINESE_SIMPLIFIED})
        assert shown(app) == ("Kanji-only text - read as Chinese.", ["Read as Japanese"])

    @pytest.mark.parametrize("text, verdict", [("這是我的書。", CHINESE_TRADITIONAL),
                                               ("勉強します", None), ("Hello", None)])
    def test_sentences_kana_and_latin_get_no_row(self, main_window, text, verdict):
        app = main_window(text, "x", verdicts={text: verdict} if verdict else None)
        assert shown(app) is None

    def test_other_text_drops_the_question(self, main_window):
        app = main_window("汽車", "Car")
        settle(app, "工作")
        assert shown(app) is None

    def test_it_shows_with_furigana_off(self, main_window):
        # The answer changes the meaning, not only the readings.
        app = main_window("汽車", verdicts={"汽車": CHINESE_SIMPLIFIED}, furigana=False)
        assert shown(app) == ("Kanji-only text - read as Chinese.", ["Read as Japanese"])

    def test_an_answer_is_kept_and_translates_again(self, main_window):
        app = main_window("汽車", "Car")
        app._do_retranslate = MagicMock()
        click(app, "Japanese")
        assert app.translation_service.source_verdict("汽車") == JAPANESE
        app._do_retranslate.assert_called_once_with(source_language=JAPANESE)
        settle(app)
        assert shown(app) == ("Kanji-only text - read as Japanese.", ["Read as Chinese"])

    def test_no_answer_while_a_translation_runs(self, main_window):
        app = main_window("汽車", "Car")
        app._do_retranslate = MagicMock()
        app.translate_btn.configure(state='disabled')
        click(app, "Japanese")
        assert app.translation_service.source_verdict("汽車") is None
        app._do_retranslate.assert_not_called()


class TestMainWindowTranslation:
    """`_do_retranslate(source_language=)` on the real window, the request faked."""

    @pytest.fixture
    def window(self, main_window, monkeypatch):
        monkeypatch.setattr('threading.Thread', _SyncThread)
        app = main_window("汽車")
        app.translation_service.translate_text = MagicMock(return_value="Steam train")
        return app

    def test_the_answer_is_stated_and_the_cache_skipped(self, window):
        window._do_retranslate(source_language=JAPANESE)
        pump(window.root)
        call = window.translation_service.translate_text.call_args
        assert call.args[0] == "汽車"
        assert call.kwargs == {'skip_cache': True, 'source_language': JAPANESE}
        assert window.trans_text.get_plain() == "Steam train"

    def test_a_plain_translate_states_nothing(self, window):
        window._do_retranslate()
        pump(window.root)
        assert window.translation_service.translate_text.call_args.kwargs == {
            'skip_cache': False, 'source_language': None}

    def test_a_finished_translation_is_of_the_input(self, window):
        window._do_retranslate()
        pump(window.root)
        assert window._translated_input == "汽車"
        assert shown(window) == ("Kanji-only text - read it as:", ["Japanese", "Chinese"])

    def test_a_failure_is_not_a_translation_of_it(self, window):
        window.translation_service.translate_text.return_value = "Error: quota exceeded"
        window._do_retranslate()
        pump(window.root)
        assert window._translated_input is None
        assert shown(window) is None
