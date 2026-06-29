"""
Unit tests for the R1 translation cache (history-backed) feature.

Covers:
- HistoryManager.find_cached() exact-match lookup semantics
- TranslationService.translate_text() cache hit / miss / skip_cache / custom_prompt bypass
"""
import os
import sys
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


def _entry(original, translated, target_lang):
    """Build a minimal history entry."""
    return {
        'original': original,
        'translated': translated,
        'target_lang': target_lang,
    }


# --------------------------------------------------------------------------- #
# HistoryManager.find_cached
# --------------------------------------------------------------------------- #
class TestFindCached:
    def test_exact_match_returns_translation(self):
        cfg = FakeConfig(history=[_entry("Hello", "Xin chao", "Vietnamese")])
        hm = HistoryManager(cfg)
        assert hm.find_cached("Hello", "Vietnamese") == "Xin chao"

    def test_target_lang_mismatch_returns_none(self):
        cfg = FakeConfig(history=[_entry("Hello", "Xin chao", "Vietnamese")])
        hm = HistoryManager(cfg)
        assert hm.find_cached("Hello", "Japanese") is None

    def test_original_mismatch_returns_none(self):
        cfg = FakeConfig(history=[_entry("Hello", "Xin chao", "Vietnamese")])
        hm = HistoryManager(cfg)
        assert hm.find_cached("Goodbye", "Vietnamese") is None

    def test_error_results_are_skipped(self):
        cfg = FakeConfig(history=[_entry("Hello", "Error: rate limited", "Vietnamese")])
        hm = HistoryManager(cfg)
        assert hm.find_cached("Hello", "Vietnamese") is None

    def test_most_recent_wins(self):
        # History inserts at front, so the first matching entry is the newest.
        cfg = FakeConfig(history=[
            _entry("Hello", "NEW", "Vietnamese"),
            _entry("Hello", "OLD", "Vietnamese"),
        ])
        hm = HistoryManager(cfg)
        assert hm.find_cached("Hello", "Vietnamese") == "NEW"

    def test_skips_error_then_returns_valid(self):
        cfg = FakeConfig(history=[
            _entry("Hello", "Error: bad", "Vietnamese"),
            _entry("Hello", "GOOD", "Vietnamese"),
        ])
        hm = HistoryManager(cfg)
        assert hm.find_cached("Hello", "Vietnamese") == "GOOD"

    def test_empty_inputs_return_none(self):
        cfg = FakeConfig(history=[_entry("Hello", "Xin chao", "Vietnamese")])
        hm = HistoryManager(cfg)
        assert hm.find_cached("", "Vietnamese") is None
        assert hm.find_cached("Hello", "") is None

    def test_empty_history_returns_none(self):
        hm = HistoryManager(FakeConfig(history=[]))
        assert hm.find_cached("Hello", "Vietnamese") is None

    def test_ignores_non_text_source_types(self):
        # Custom-prompt / screenshot / multimodal entries are never plain cache hits.
        cfg = FakeConfig(history=[
            {'original': 'Hello', 'translated': 'CUSTOM', 'target_lang': 'Vietnamese',
             'source_type': 'custom'},
            {'original': 'Hello', 'translated': 'SHOT', 'target_lang': 'Vietnamese',
             'source_type': 'screenshot'},
        ])
        hm = HistoryManager(cfg)
        assert hm.find_cached('Hello', 'Vietnamese') is None

    def test_missing_source_type_treated_as_text(self):
        # Legacy entries without source_type stay cacheable as plain text.
        cfg = FakeConfig(history=[
            {'original': 'Hello', 'translated': 'OK', 'target_lang': 'Vietnamese'},
        ])
        hm = HistoryManager(cfg)
        assert hm.find_cached('Hello', 'Vietnamese') == 'OK'


# --------------------------------------------------------------------------- #
# TranslationService.translate_text caching
# --------------------------------------------------------------------------- #
def _make_service(history=None, api_result="FRESH RESULT"):
    """Build a TranslationService with only the attributes translate_text needs.

    Bypasses the heavy __init__/_configure_api so the cache logic can be tested in
    isolation. api_manager.translate is mocked; history_manager is real (dict-backed).
    """
    svc = TranslationService.__new__(TranslationService)
    svc._is_trial_mode = False
    svc.trial_client = None
    svc.api_manager = MagicMock()
    svc.api_manager.translate.return_value = api_result
    svc.history_manager = HistoryManager(FakeConfig(history=history or []))
    return svc


class TestTranslateTextCache:
    def test_cache_hit_skips_api(self):
        svc = _make_service(history=[_entry("Hello", "CACHED", "Vietnamese")])
        result = svc.translate_text("Hello", "Vietnamese")
        assert result == "CACHED"
        svc.api_manager.translate.assert_not_called()

    def test_cache_hit_does_not_duplicate_history(self):
        svc = _make_service(history=[_entry("Hello", "CACHED", "Vietnamese")])
        before = len(svc.history_manager.get_history())
        svc.translate_text("Hello", "Vietnamese")
        after = len(svc.history_manager.get_history())
        assert after == before  # No new entry on a cache hit

    def test_cache_miss_calls_api_and_stores(self):
        svc = _make_service(history=[], api_result="FRESH RESULT")
        result = svc.translate_text("Hello", "Vietnamese")
        assert result == "FRESH RESULT"
        svc.api_manager.translate.assert_called_once()
        # Result is now stored, so a second identical call is served from cache.
        svc.api_manager.translate.reset_mock()
        second = svc.translate_text("Hello", "Vietnamese")
        assert second == "FRESH RESULT"
        svc.api_manager.translate.assert_not_called()

    def test_skip_cache_forces_api(self):
        svc = _make_service(history=[_entry("Hello", "CACHED", "Vietnamese")],
                            api_result="FRESH RESULT")
        result = svc.translate_text("Hello", "Vietnamese", skip_cache=True)
        assert result == "FRESH RESULT"
        svc.api_manager.translate.assert_called_once()

    def test_custom_prompt_bypasses_cache(self):
        svc = _make_service(history=[_entry("Hello", "CACHED", "Vietnamese")],
                            api_result="FRESH RESULT")
        result = svc.translate_text("Hello", "Vietnamese", custom_prompt="explain this")
        assert result == "FRESH RESULT"
        svc.api_manager.translate.assert_called_once()

    def test_custom_prompt_result_not_cached_as_plain(self):
        # Write-side guard: a custom-prompt translation must NOT later be served as a
        # plain-translation cache hit (it is tagged source_type='custom').
        svc = _make_service(history=[], api_result="CUSTOM ANSWER")
        svc.translate_text("Hello", "Vietnamese", custom_prompt="be very formal")
        assert svc.history_manager.find_cached("Hello", "Vietnamese") is None
        # A subsequent plain translation still calls the API (not served the custom result).
        svc.api_manager.translate.reset_mock()
        svc.api_manager.translate.return_value = "PLAIN ANSWER"
        result = svc.translate_text("Hello", "Vietnamese")
        assert result == "PLAIN ANSWER"
        svc.api_manager.translate.assert_called_once()
