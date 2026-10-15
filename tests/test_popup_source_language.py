"""
Tests for Phase J6 - the quick-translate popup reads kanji-only Japanese the model placed.

Before J6 a kanji-only selection never got its source block (no kana, no hint), a
grammar fix of kanji-only text never got readings, and Japanese quoted inside an
English translation stayed plain. Now the verdict a model gave for exactly that
text (J4) is the hint, and when the model could not place the text the popup asks
"Kanji-only text - read it as: [Japanese] [Chinese]" - answering re-translates
with that source, because an unplaced translation may carry the other language's
sense (Decision 27).

The service tests need no display; the popup tests use the `tk_root` fixture.
"""
import inspect
import queue
import tkinter as tk
from unittest.mock import MagicMock

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.core import furigana as F
from src.core.history import HistoryManager
from src.core.lang_id import CHINESE_SIMPLIFIED, JAPANESE
from src.core.source_marker import stated_clause
from src.core.translation import TranslationService
from src.ui.quick_translate import SOURCE_CHOOSER_PX, QuickTranslateManager

HAS_PROVIDER = pytest.mark.skipif(not F.is_available(),
                                  reason="requires a reading provider (fugashi or pykakasi)")


@pytest.fixture(autouse=True)
def _clear_cache():
    F.clear_cache()
    yield
    F.clear_cache()


# --------------------------------------------------------------------------- #
# The service: the source block's hint, and the chooser's re-translation
# --------------------------------------------------------------------------- #
class FakeHistoryConfig:
    def __init__(self):
        self._store = {'history': [], 'history_enabled': True}

    def get(self, key, default=None):
        return self._store.get(key, default)

    def set(self, key, value):
        self._store[key] = value


def make_service(answer, selection="勉強"):
    svc = TranslationService.__new__(TranslationService)
    svc._is_trial_mode = False
    svc.trial_client = None
    svc.api_manager = MagicMock()
    svc.api_manager.translate.return_value = answer
    svc.api_manager.last_attribution = "test-model (Test)"
    svc.history_manager = HistoryManager(FakeHistoryConfig())
    svc.config = MagicMock()
    svc.config.get_furigana_enabled.return_value = True
    svc.translation_queue = queue.Queue()
    svc.last_translation_time = 0
    svc._configure_api = lambda: True
    svc.get_selected_text = lambda: selection
    svc.get_trial_info = lambda: None
    return svc


def queued(svc):
    return svc.translation_queue.get_nowait()


class TestSourceBlock:
    @HAS_PROVIDER
    def test_kanji_only_that_the_model_called_japanese_gets_its_block(self):
        svc = make_service("[[SOURCE: Japanese]]\nStudy")
        svc.do_translate_or_fix("English")
        original, translated, _target, _trial, furigana_text = queued(svc)
        assert (original, translated) == ("勉強", "Study")
        assert furigana_text == "{勉強|べんきょう}"

    @pytest.mark.parametrize("answer", ["[[SOURCE: Unknown]]\nBed", "[[SOURCE: Chinese]]\nWork",
                                        "Study"])
    def test_no_japanese_verdict_no_block(self, answer):
        svc = make_service(answer)
        svc.do_translate_or_fix("English")
        assert queued(svc)[4] is None

    def test_a_chinese_selection_gets_no_block(self):
        svc = make_service("We are studying Chinese.", selection="我们在学习中文。")
        svc.do_translate_or_fix("English")
        assert queued(svc)[4] is None

    @HAS_PROVIDER
    def test_kana_still_gets_its_block(self):
        svc = make_service("I study.", selection="勉強します")
        svc.do_translate_or_fix("English")
        assert queued(svc)[4] == "{勉強|べんきょう}します"


class TestChoosingTheSource:
    def test_stated_clause(self):
        assert stated_clause("Japanese").text == "\n\nSOURCE LANGUAGE: the text above is Japanese."
        assert stated_clause("Chinese Simplified").text == \
            "\n\nSOURCE LANGUAGE: the text above is Chinese."
        assert stated_clause("zh-TW").stated == "Chinese (Traditional)"

    @HAS_PROVIDER
    def test_retranslating_with_japanese_states_it_and_reads_it(self):
        svc = make_service("Teacher")
        svc.redo_translation("先生", "English", source_language="Japanese")
        prompt = svc.api_manager.translate.call_args[0][0]
        assert prompt.endswith("SOURCE LANGUAGE: the text above is Japanese.")
        assert "[[SOURCE:" not in prompt
        original, translated, _target, _trial, furigana_text = queued(svc)
        assert (original, translated, furigana_text) == ("先生", "Teacher", "{先生|せんせい}")
        assert svc.source_verdict("先生") == JAPANESE
        assert svc.history_manager.get_history()[0]['source_verdict'] == JAPANESE

    def test_retranslating_with_chinese_reads_nothing(self):
        svc = make_service("Mr.")
        svc.redo_translation("先生", "English", source_language="Chinese (Simplified)")
        assert queued(svc)[4] is None
        assert svc.source_verdict("先生") == CHINESE_SIMPLIFIED

    def test_a_plain_retranslate_still_asks_the_model(self):
        svc = make_service("[[SOURCE: Japanese]]\nTeacher")
        svc.redo_translation("先生", "English")
        assert "[[SOURCE: Unknown]]" in svc.api_manager.translate.call_args[0][0]


# --------------------------------------------------------------------------- #
# The popup
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("target, is_grammar, original, source, expected", [
    ("English", False, "東京", JAPANESE, JAPANESE),          # quoted Japanese in English
    ("English", False, "東京", None, None),                  # unplaced: no guess
    ("English", False, "東京に行く", None, JAPANESE),        # kana settles it
    ("English", False, "我们", JAPANESE, None),              # a Chinese glyph beats a verdict
    ("Japanese", False, "Tokyo", None, JAPANESE),            # the target is authoritative
    ("Chinese Simplified", False, "東京", JAPANESE, None),   # Chinese output
    ("Grammar", True, "東京都", JAPANESE, JAPANESE),         # a fix keeps the source
    ("Grammar", True, "東京都", None, None),
    ("Grammar", True, "我们", JAPANESE, None),
    ("English", False, "", None, None),
])
def test_ruby_hint(target, is_grammar, original, source, expected):
    assert QuickTranslateManager._ruby_hint(target, is_grammar, original, source) == expected


@pytest.mark.parametrize("original, source, is_grammar, is_error, expected", [
    ("先生", None, False, False, True),
    ("先生", JAPANESE, False, False, False),
    ("先生", CHINESE_SIMPLIFIED, False, False, False),
    ("先生です", None, False, False, False),        # kana: placed
    ("我们", None, False, False, False),            # a Chinese glyph: placed
    ("Hello", None, False, False, False),
    ("先生", None, True, False, False),             # a grammar fix
    ("先生", None, False, True, False),             # a failure notice
    ("", None, False, False, False),
])
def test_asks_source(original, source, is_grammar, is_error, expected):
    assert QuickTranslateManager._asks_source(original, source, is_grammar, is_error) is expected


class FakeConfig:
    def __init__(self, furigana_enabled=True):
        self._furigana = furigana_enabled

    def get_furigana_enabled(self):
        return self._furigana

    def get_quick_replace(self):
        return False


@pytest.fixture
def manager(tk_root):
    mgr = QuickTranslateManager(tk_root, FakeConfig())
    mgr._last_mouse_x, mgr._last_mouse_y = 500, 300
    mgr.choices = []
    mgr.configure_callbacks(on_choose_source=mgr.choices.append)
    yield mgr
    mgr.close()


def popup_height(mgr, tk_root):
    tk_root.update_idletasks()
    return int(mgr.popup.geometry().split('+')[0].split('x')[1])


def buttons(widget):
    return [child for child in widget.winfo_children() if isinstance(child, tk.Button)]


class TestPopup:
    @HAS_PROVIDER
    def test_japanese_quoted_in_an_english_translation_is_read(self, manager):
        manager.show("The word 東京 means Tokyo.", "English", None, "東京",
                     source_lang=JAPANESE)
        assert manager.popup_text.has_ruby is True
        assert manager.popup_text.get_plain() == "The word 東京 means Tokyo."

    def test_without_a_verdict_it_stays_plain(self, manager):
        manager.show("The word 東京 means Tokyo.", "English", None, "東京")
        assert manager.popup_text.has_ruby is False

    @HAS_PROVIDER
    def test_a_grammar_fix_of_placed_kanji_is_read(self, manager):
        manager.show("東京都", "Grammar", None, "東京都", is_grammar=True,
                     source_lang=JAPANESE)
        assert manager.popup_text.has_ruby is True

    def test_the_chooser_appears_when_nobody_placed_the_kanji(self, manager):
        manager.show("Teacher", "English", None, "先生")
        assert manager.popup_source_chooser is not None
        labels = [b.cget('text') for b in buttons(manager.popup_source_chooser)]
        assert labels == ["Japanese", "Chinese"]

    @pytest.mark.parametrize("original, source", [("先生", JAPANESE), ("先生です", None),
                                                  ("Sensei", None)])
    def test_no_chooser_when_the_language_is_known(self, manager, original, source):
        manager.show("Teacher", "English", None, original, source_lang=source)
        assert manager.popup_source_chooser is None

    def test_no_chooser_on_a_grammar_fix_or_a_failure(self, manager):
        manager.show("先生", "Grammar", None, "先生", is_grammar=True)
        assert manager.popup_source_chooser is None
        manager.show("Error: quota", "English", None, "先生")
        assert manager.popup_source_chooser is None

    @pytest.mark.parametrize("index, expected", [(0, JAPANESE), (1, CHINESE_SIMPLIFIED)])
    def test_an_answer_reaches_the_app(self, manager, index, expected):
        manager.show("Teacher", "English", None, "先生")
        buttons(manager.popup_source_chooser)[index].invoke()
        assert manager.choices == [expected]

    def test_the_row_is_in_the_height_budget(self, manager, tk_root):
        manager.show("Teacher", "English", None, "Sensei")
        without = popup_height(manager, tk_root)
        manager.show("Teacher", "English", None, "先生")
        assert popup_height(manager, tk_root) == without + SOURCE_CHOOSER_PX

    def test_the_translation_is_not_clipped_by_the_row(self, manager, tk_root):
        manager.show("A translation long enough to wrap onto a second row of the box. " * 3,
                     "English", None, "先生")
        tk_root.update_idletasks()
        tk_root.update()
        content = manager.popup_text.count('1.0', 'end', 'ypixels')
        if not content:
            pytest.skip("Tk reported no laid-out pixels")
        assert manager.popup_text.winfo_height() >= content[0]

    @HAS_PROVIDER
    def test_custom_prompt_cancel_keeps_the_verdict(self, manager):
        manager.show("The word 東京 means Tokyo.", "English", None, "東京",
                     source_lang=JAPANESE)
        manager._enter_custom_prompt_mode()
        manager._handle_custom_prompt_cancel()
        assert manager.popup_text.has_ruby is True

    @HAS_PROVIDER
    def test_the_replace_preview_uses_the_same_hint(self, manager):
        manager.show("東京", "Grammar", None, "東京", is_grammar=True, source_lang=JAPANESE)
        manager._show_replace_preview()
        assert manager.popup_text.ruby_pairs > 0


# --------------------------------------------------------------------------- #
# The app
# --------------------------------------------------------------------------- #
class _SyncThread:
    def __init__(self, target=None, daemon=None, **kwargs):
        self._target = target

    def start(self):
        self._target()


def make_app():
    from src.app import TranslatorApp
    app = TranslatorApp.__new__(TranslatorApp)
    app.quick_translate_manager = MagicMock()
    app.translation_service = MagicMock()
    app.translation_service.last_attribution = None
    app.toast = MagicMock()
    return app


class TestApp:
    def test_the_popup_gets_the_texts_verdict(self):
        app = make_app()
        app.translation_service.source_verdict.return_value = JAPANESE
        app.show_quick_translate("先生", "Teacher", "English")
        app.translation_service.source_verdict.assert_called_once_with("先生")
        assert app.quick_translate_manager.show.call_args.kwargs['source_lang'] == JAPANESE

    def test_a_given_source_wins(self):
        app = make_app()
        app.show_quick_translate("先生", "Mr.", "English", source_lang=CHINESE_SIMPLIFIED)
        app.translation_service.source_verdict.assert_not_called()
        assert app.quick_translate_manager.show.call_args.kwargs['source_lang'] == \
            CHINESE_SIMPLIFIED

    def test_an_answer_retranslates_with_that_source(self, monkeypatch):
        monkeypatch.setattr('threading.Thread', _SyncThread)
        app = make_app()
        app.current_original, app.current_target_lang = "先生", "English"
        app._on_quick_translate_choose_source(JAPANESE)
        app.quick_translate_manager.show_loading.assert_called_once_with("English")
        app.translation_service.redo_translation.assert_called_once_with(
            "先生", "English", source_language=JAPANESE)

    def test_the_app_wires_the_chooser(self):
        from src.app import TranslatorApp
        source = inspect.getsource(TranslatorApp.__init__)
        assert 'on_choose_source=self._on_quick_translate_choose_source' in source
