"""
Unit tests for the R2 custom-prompt feature.

Covers:
- R2-bug fix: translate_text() custom_prompt branch now embeds the source text
- ask_freeform(): raw prompt sent verbatim, not cached/historied, pushed to queue
"""
import os
import sys
import queue
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.history import HistoryManager
from src.core.translation import TranslationService


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


def _make_service(history=None, api_result="ANSWER"):
    """Build a TranslationService with only the attributes the tested methods need."""
    svc = TranslationService.__new__(TranslationService)
    svc._is_trial_mode = False
    svc.trial_client = None
    svc.api_manager = MagicMock()
    svc.api_manager.translate.return_value = api_result
    svc.history_manager = HistoryManager(FakeConfig(history=history or []))
    svc.translation_queue = queue.Queue()
    # ask_freeform calls _configure_api() up front; stub it as a no-op success.
    svc._configure_api = lambda: True
    return svc


# --------------------------------------------------------------------------- #
# R2-bug fix: custom_prompt branch must embed the source text
# --------------------------------------------------------------------------- #
class TestCustomPromptEmbedsText:
    def test_custom_prompt_includes_source_text(self):
        svc = _make_service(api_result="OUT")
        svc.translate_text("SECRET_SOURCE_TEXT", "Vietnamese",
                           custom_prompt="make it formal")
        sent_prompt = svc.api_manager.translate.call_args[0][0]
        assert "SECRET_SOURCE_TEXT" in sent_prompt
        assert "make it formal" in sent_prompt

    def test_custom_prompt_bypasses_cache(self):
        # Even with a cached entry, a custom prompt must hit the API.
        svc = _make_service(history=[{
            'original': "SECRET_SOURCE_TEXT",
            'translated': "CACHED",
            'target_lang': "Vietnamese",
        }], api_result="OUT")
        result = svc.translate_text("SECRET_SOURCE_TEXT", "Vietnamese",
                                    custom_prompt="make it formal")
        assert result == "OUT"
        svc.api_manager.translate.assert_called_once()


# --------------------------------------------------------------------------- #
# ask_freeform(): verbatim raw prompt, no history/cache write
# --------------------------------------------------------------------------- #
class TestAskFreeform:
    def test_sends_prompt_verbatim(self):
        svc = _make_service(api_result="42")
        svc.ask_freeform("What is 6 times 7?", "Vietnamese")
        svc.api_manager.translate.assert_called_once_with("What is 6 times 7?")

    def test_pushes_result_to_queue(self):
        svc = _make_service(api_result="42")
        svc.ask_freeform("What is 6 times 7?", "Vietnamese")
        item = svc.translation_queue.get_nowait()
        # Format: (original, translated, target_lang, trial_info, furigana_text)
        assert len(item) == 5
        assert item[0] == "What is 6 times 7?"  # original = raw prompt
        assert item[1] == "42"                   # translated = result
        assert item[2] == "Vietnamese"
        assert item[4] is None                   # furigana off for freeform

    def test_does_not_write_history(self):
        svc = _make_service(api_result="42")
        svc.ask_freeform("What is 6 times 7?", "Vietnamese")
        assert len(svc.history_manager.get_history()) == 0

    def test_empty_prompt_pushes_error_without_api_call(self):
        svc = _make_service()
        svc.ask_freeform("   ", "Vietnamese")
        svc.api_manager.translate.assert_not_called()
        item = svc.translation_queue.get_nowait()
        assert item[1].startswith("No prompt") or item[1].startswith("Error:")

    def test_strips_thinking_tags(self):
        svc = _make_service(api_result="<think>reasoning</think>FINAL")
        svc.ask_freeform("question?", "Vietnamese")
        item = svc.translation_queue.get_nowait()
        assert item[1] == "FINAL"
