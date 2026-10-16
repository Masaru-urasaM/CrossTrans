"""
Tests for the user's own answer about kanji-only text (the post-J12 follow-ups, K3-K5).

Decision 22 put the user last in line - evidence, then a model, then the user -
but only the popup's chooser ever kept the user's answer, and only because it
re-translated. K3 keeps the Dictionary dialog's answer too: as the text's verdict
for this session (`TranslationService.remember_user_source`) and on History's
entries of that exact text (`HistoryManager.set_source_verdict`), where it
replaces a model's, since the user's pick outranks it.

Nothing here needs a display.
"""
import inspect
import logging
from unittest.mock import MagicMock

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.core.history import HistoryManager
from src.core.lang_id import CHINESE_SIMPLIFIED, CHINESE_TRADITIONAL, JAPANESE
from src.core.translation import TranslationService


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
