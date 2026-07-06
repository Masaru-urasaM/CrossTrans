"""
Unit tests for the Fix Grammar feature (G1).

Covers:
- fix_grammar(): strict correction prompt (never translate, never censor, same language),
  empty-input guard, thinking-tag stripping, verbatim preservation of arbitrary tokens
- do_grammar_fix(): queues a 6-tuple with is_grammar=True, cooldown, error path, no history
- Config defaults + getter fallbacks
- HotkeyManager registers the __fix_grammar__ hotkey gated by the toggle
"""
import os
import sys
import time
import queue
import inspect
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import src.core first so the config<->core circular import resolves cleanly.
from src.core.history import HistoryManager
from src.core.translation import TranslationService
from src.core.hotkey import HotkeyManager
from config import Config


class FakeConfig:
    """Minimal dict-backed config compatible with HistoryManager."""

    def __init__(self, history=None, history_enabled=True):
        self._store = {
            'history': list(history or []),
            'history_enabled': history_enabled,
        }

    def get(self, key, default=None):
        return self._store.get(key, default)

    def set(self, key, value):
        self._store[key] = value


def _make_service(api_result="CORRECTED", selected="she go to school yesterday"):
    """Build a TranslationService with only the attributes the tested methods need."""
    svc = TranslationService.__new__(TranslationService)
    svc._is_trial_mode = False
    svc.trial_client = None
    svc.api_manager = MagicMock()
    svc.api_manager.translate.return_value = api_result
    svc.history_manager = HistoryManager(FakeConfig())
    svc.translation_queue = queue.Queue()
    svc.last_grammar_fix_time = 0
    # do_grammar_fix calls these; stub them.
    svc._configure_api = lambda: True
    svc.get_selected_text = lambda: selected
    svc.get_trial_info = lambda: None
    return svc


# --------------------------------------------------------------------------- #
# fix_grammar(): prompt content + behavior
# --------------------------------------------------------------------------- #
class TestFixGrammar:
    def test_empty_returns_empty_without_api_call(self):
        svc = _make_service()
        assert svc.fix_grammar("") == ""
        assert svc.fix_grammar("   ") == ""
        svc.api_manager.translate.assert_not_called()

    def test_prompt_embeds_source_and_enforces_rules(self):
        svc = _make_service(api_result="OUT")
        svc.fix_grammar("she go to school yesterday")
        prompt = svc.api_manager.translate.call_args[0][0]
        assert "she go to school yesterday" in prompt      # source embedded
        assert "NEVER translate" in prompt                 # never translate
        assert "SAME LANGUAGE" in prompt                   # same language out
        assert "Do NOT censor" in prompt                   # no censoring
        assert "Do NOT paraphrase" in prompt               # no rephrasing

    def test_preserves_arbitrary_token_verbatim(self):
        # A placeholder stands in for any word the user may not want sanitized.
        # The pipeline must pass it through untouched (the model echoes the input here).
        token = "ZZQ_RAW_TOKEN_42"
        svc = _make_service(api_result=token)
        out = svc.fix_grammar(f"this is {token} ok")
        prompt = svc.api_manager.translate.call_args[0][0]
        assert token in prompt          # sent to the model unmodified
        assert out == token             # returned unmodified

    def test_strips_thinking_tags(self):
        svc = _make_service(api_result="<think>reasoning</think>She went to school.")
        assert svc.fix_grammar("she go to school") == "She went to school."

    def test_returns_api_result(self):
        svc = _make_service(api_result="She went to school yesterday.")
        assert svc.fix_grammar("she go to school yesterday") == "She went to school yesterday."


# --------------------------------------------------------------------------- #
# do_grammar_fix(): hotkey entry - queue format, cooldown, errors, no history
# --------------------------------------------------------------------------- #
class TestDoGrammarFix:
    def test_queues_6tuple_with_is_grammar_flag(self):
        svc = _make_service(api_result="She went to school yesterday.")
        svc.do_grammar_fix()
        item = svc.translation_queue.get_nowait()
        # Format: (original, corrected, label, trial_info, furigana, is_grammar)
        assert len(item) == 6
        assert item[0] == "she go to school yesterday"      # original selection
        assert item[1] == "She went to school yesterday."   # corrected
        assert item[2] == "Grammar"                          # label
        assert item[4] is None                               # furigana off
        assert item[5] is True                               # is_grammar flag

    def test_no_selection_queues_error_6tuple(self):
        svc = _make_service()
        svc.get_selected_text = lambda: None
        svc.do_grammar_fix()
        item = svc.translation_queue.get_nowait()
        assert len(item) == 6
        assert item[5] is True
        assert item[1].startswith("No text") or item[1].startswith("Error:")

    def test_cooldown_blocks_rapid_repeat(self):
        svc = _make_service()
        svc.last_grammar_fix_time = time.time()  # just fired
        svc.do_grammar_fix()
        svc.api_manager.translate.assert_not_called()
        item = svc.translation_queue.get_nowait()
        assert len(item) == 6
        assert item[5] is True
        assert "wait" in item[1].lower()

    def test_does_not_write_history(self):
        svc = _make_service(api_result="She went to school yesterday.")
        svc.do_grammar_fix()
        assert len(svc.history_manager.get_history()) == 0


# --------------------------------------------------------------------------- #
# Config defaults + getter fallbacks (no file I/O)
# --------------------------------------------------------------------------- #
class TestConfigDefaults:
    def test_class_constants(self):
        assert Config.FIX_GRAMMAR_HOTKEY_DEFAULT == "win+alt+g"
        assert Config.DEFAULT_CONFIG["fix_grammar_hotkey"] == "win+alt+g"
        assert Config.DEFAULT_CONFIG["fix_grammar_enabled"] is True
        # Global hotkey is OFF by default (collides with Xbox Game Bar).
        assert Config.DEFAULT_CONFIG["fix_grammar_hotkey_enabled"] is False

    def test_getter_fallbacks(self):
        cfg = Config.__new__(Config)
        cfg._config = {}
        assert cfg.get_fix_grammar_hotkey() == "win+alt+g"
        assert cfg.get_fix_grammar_enabled() is True
        assert cfg.get_fix_grammar_hotkey_enabled() is False

    def test_setter_roundtrip(self):
        cfg = Config.__new__(Config)
        cfg._config = {}
        cfg.save = lambda: None  # avoid disk write
        cfg.set_fix_grammar_hotkey("win+alt+x")
        cfg.set_fix_grammar_enabled(False)
        cfg.set_fix_grammar_hotkey_enabled(True)
        assert cfg.get_fix_grammar_hotkey() == "win+alt+x"
        assert cfg.get_fix_grammar_enabled() is False
        assert cfg.get_fix_grammar_hotkey_enabled() is True


# --------------------------------------------------------------------------- #
# Hotkey registration wiring
# --------------------------------------------------------------------------- #
class TestHotkeyRegistration:
    def test_registers_fix_grammar_marker_gated_by_hotkey_toggle(self):
        src = inspect.getsource(HotkeyManager.register_hotkeys)
        assert "__fix_grammar__" in src
        # Registration is gated by the dedicated hotkey flag (off by default), not the
        # button flag, so a fresh install never fights Xbox Game Bar for Win+Alt+G.
        assert "get_fix_grammar_hotkey_enabled" in src
        assert "get_fix_grammar_hotkey(" in src
