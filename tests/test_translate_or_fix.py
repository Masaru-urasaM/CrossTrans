"""Unit tests for the merged Translate-or-Fix feature.

Covers TranslationService.translate_or_fix() (Phase 1) and, later phases,
do_translate_or_fix() routing. The merged path sends ONE prompt that tells the model to
grammar-fix text already in the target language or otherwise translate it, with BOTH
branches uncensored and meaning-preserving. Results live in a dedicated 'merged' cache
namespace so a minimal-change fix is never cross-served as a plain 'rephrase'.

NEVER put a real slur in these tests. A neutral placeholder token stands in for "any
word, including offensive ones must pass through verbatim".
"""
import os
import sys
import time
import queue
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import src.core BEFORE config so the config<->core circular import resolves cleanly.
from src.core.history import HistoryManager
from src.core.translation import TranslationService

# Neutral stand-in for "an arbitrary word that must survive verbatim" — never a real slur.
RAW_TOKEN = "ZZQ_RAW_TOKEN_42"


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


def _make_service(history=None, api_result="RESULT"):
    """Build a TranslationService with only the attributes translate_or_fix needs."""
    svc = TranslationService.__new__(TranslationService)
    svc._is_trial_mode = False
    svc.trial_client = None
    svc.api_manager = MagicMock()
    svc.api_manager.translate.return_value = api_result
    svc.history_manager = HistoryManager(FakeConfig(history=history or []))
    return svc


def _entry(original, translated, target_lang, source_type='text'):
    return {
        'original': original,
        'translated': translated,
        'target_lang': target_lang,
        'source_type': source_type,
    }


# --------------------------------------------------------------------------- #
# find_cached source_type namespace
# --------------------------------------------------------------------------- #
class TestFindCachedNamespace:
    def test_default_source_type_is_text(self):
        hm = HistoryManager(FakeConfig(history=[_entry("Hi", "OK", "English")]))
        assert hm.find_cached("Hi", "English") == "OK"

    def test_merged_entry_not_served_to_text_lookup(self):
        hm = HistoryManager(FakeConfig(history=[
            _entry("Hi", "FIXED", "English", source_type='merged')]))
        # Default (text) lookup must ignore a 'merged' entry.
        assert hm.find_cached("Hi", "English") is None

    def test_text_entry_not_served_to_merged_lookup(self):
        hm = HistoryManager(FakeConfig(history=[
            _entry("Hi", "REPHRASED", "English", source_type='text')]))
        # No cross-serve: a plain rephrase must NOT satisfy a merged lookup.
        assert hm.find_cached("Hi", "English", source_type='merged') is None

    def test_merged_lookup_returns_merged_entry(self):
        hm = HistoryManager(FakeConfig(history=[
            _entry("Hi", "FIXED", "English", source_type='merged')]))
        assert hm.find_cached("Hi", "English", source_type='merged') == "FIXED"


# --------------------------------------------------------------------------- #
# translate_or_fix — prompt content
# --------------------------------------------------------------------------- #
class TestMergedPrompt:
    def test_prompt_embeds_source_and_target_and_rules(self):
        svc = _make_service(api_result="OUT")
        svc.translate_or_fix("she go to school yesterday", "Japanese")
        prompt = svc.api_manager.translate.call_args[0][0]
        assert "she go to school yesterday" in prompt        # source embedded
        assert "Japanese" in prompt                          # target substituted
        assert "PREDOMINANTLY already in" in prompt          # tie-break: fix branch
        assert "Otherwise, TRANSLATE" in prompt              # tie-break: translate branch
        assert "Do NOT censor" in prompt                     # no-censor, both branches
        assert "keep every such word exactly" in prompt      # grammar-fix branch verbatim
        assert "faithful equivalent" in prompt               # translate branch faithful
        assert "Output ONLY the final result" in prompt      # no meta-text

    def test_preserves_arbitrary_token_verbatim(self):
        # Source token must reach the model untouched, and the model's output is returned as-is.
        svc = _make_service(api_result=RAW_TOKEN)
        out = svc.translate_or_fix(f"please keep {RAW_TOKEN} here", "English")
        prompt = svc.api_manager.translate.call_args[0][0]
        assert RAW_TOKEN in prompt      # not stripped/masked on the way in
        assert out == RAW_TOKEN         # not stripped/masked on the way out

    def test_empty_returns_empty_without_api_call(self):
        svc = _make_service()
        assert svc.translate_or_fix("", "English") == ""
        assert svc.translate_or_fix("   ", "English") == ""
        svc.api_manager.translate.assert_not_called()

    def test_strips_thinking_tags(self):
        svc = _make_service(api_result="<think>reasoning</think>Clean output")
        out = svc.translate_or_fix("input text", "English")
        assert "<think>" not in out
        assert "Clean output" in out

    def test_returns_api_result(self):
        svc = _make_service(api_result="TranslatedOrFixed")
        assert svc.translate_or_fix("input", "Vietnamese") == "TranslatedOrFixed"


# --------------------------------------------------------------------------- #
# translate_or_fix — merged cache namespace
# --------------------------------------------------------------------------- #
class TestMergedCache:
    def test_cache_hit_skips_api(self):
        svc = _make_service(history=[_entry("Hi", "CACHED", "English", source_type='merged')])
        assert svc.translate_or_fix("Hi", "English") == "CACHED"
        svc.api_manager.translate.assert_not_called()

    def test_cache_miss_calls_api_and_stores_as_merged(self):
        svc = _make_service(history=[], api_result="FRESH")
        assert svc.translate_or_fix("Hi", "English") == "FRESH"
        svc.api_manager.translate.assert_called_once()
        # Stored under 'merged' → a second identical call is served from cache.
        svc.api_manager.translate.reset_mock()
        assert svc.translate_or_fix("Hi", "English") == "FRESH"
        svc.api_manager.translate.assert_not_called()

    def test_plain_text_entry_not_cross_served(self):
        # A pre-existing plain 'text' translation must NOT satisfy the merged lookup.
        svc = _make_service(history=[_entry("Hi", "REPHRASED", "English", source_type='text')],
                            api_result="MINIMAL FIX")
        result = svc.translate_or_fix("Hi", "English")
        assert result == "MINIMAL FIX"
        svc.api_manager.translate.assert_called_once()  # API called, not served the rephrase

    def test_skip_cache_forces_api(self):
        svc = _make_service(history=[_entry("Hi", "CACHED", "English", source_type='merged')],
                            api_result="FRESH")
        assert svc.translate_or_fix("Hi", "English", skip_cache=True) == "FRESH"
        svc.api_manager.translate.assert_called_once()


# --------------------------------------------------------------------------- #
# do_translate_or_fix — orchestration / queue routing
# --------------------------------------------------------------------------- #
def _make_orchestrator(api_result="RESULT", selected="hello world",
                       furigana_enabled=False, trial_info=None):
    """TranslationService with the attributes do_translate_or_fix needs."""
    svc = TranslationService.__new__(TranslationService)
    svc._is_trial_mode = False
    svc.trial_client = None
    svc.api_manager = MagicMock()
    svc.api_manager.translate.return_value = api_result
    svc.history_manager = HistoryManager(FakeConfig())
    svc.translation_queue = queue.Queue()
    svc.last_translation_time = 0
    svc._configure_api = lambda: True
    svc.get_selected_text = lambda: selected
    svc.get_trial_info = lambda: trial_info
    svc.config = MagicMock()
    svc.config.get_furigana_enabled.return_value = furigana_enabled
    return svc


class TestDoTranslateOrFix:
    def test_queues_5tuple_shape(self):
        svc = _make_orchestrator(api_result="OUT", selected="bonjour")
        svc.do_translate_or_fix("Vietnamese")
        item = svc.translation_queue.get_nowait()
        # (original, result, target_lang, trial_info, furigana) — 5-tuple, is_grammar=False downstream
        assert len(item) == 5
        assert item[0] == "bonjour"        # original selection
        assert item[1] == "OUT"            # translated-or-fixed
        assert item[2] == "Vietnamese"     # target language (real, not "Grammar")
        assert item[4] is None             # furigana off

    def test_uses_merged_prompt(self):
        svc = _make_orchestrator(api_result="OUT")
        svc.do_translate_or_fix("Japanese")
        svc.api_manager.translate.assert_called_once()
        prompt = svc.api_manager.translate.call_args[0][0]
        assert "PREDOMINANTLY already in" in prompt   # merged decision rule present
        assert "Do NOT censor" in prompt

    def test_trial_info_at_index_3(self):
        info = {'used': 1, 'limit': 10}
        svc = _make_orchestrator(api_result="OUT", trial_info=info)
        svc.do_translate_or_fix("English")
        item = svc.translation_queue.get_nowait()
        assert item[3] == info

    def test_cooldown_blocks_rapid_repeat(self):
        svc = _make_orchestrator()
        svc.last_translation_time = time.time()  # just fired
        svc.do_translate_or_fix("English")
        svc.api_manager.translate.assert_not_called()
        item = svc.translation_queue.get_nowait()
        assert len(item) == 4
        assert "wait" in item[1].lower()

    def test_no_selection_queues_error(self):
        svc = _make_orchestrator(selected=None)
        svc.do_translate_or_fix("English")
        svc.api_manager.translate.assert_not_called()
        item = svc.translation_queue.get_nowait()
        assert len(item) == 4
        assert "No text selected" in item[1]

    def test_writes_merged_history_on_success(self):
        svc = _make_orchestrator(api_result="FIXED", selected="she go school")
        svc.do_translate_or_fix("English")
        history = svc.history_manager.get_history()
        assert len(history) == 1
        assert history[0]['source_type'] == 'merged'
        assert history[0]['translated'] == "FIXED"

    def test_furigana_none_for_non_japanese(self):
        svc = _make_orchestrator(api_result="OUT", selected="hello",
                                 furigana_enabled=True)
        svc.do_translate_or_fix("English")
        item = svc.translation_queue.get_nowait()
        assert item[4] is None  # source not Japanese → no furigana even when enabled


# --------------------------------------------------------------------------- #
# No-censor scope: plain translate_text prompts must also carry the rule
# --------------------------------------------------------------------------- #
class TestNoCensorScope:
    def test_plain_translation_prompt_has_no_censor_rule(self):
        svc = _make_service(api_result="OUT")
        svc.translate_text("hello", "Japanese")
        prompt = svc.api_manager.translate.call_args[0][0]
        assert "Do NOT censor" in prompt

    def test_custom_prompt_translation_has_no_censor_rule(self):
        svc = _make_service(api_result="OUT")
        svc.translate_text("hello", "Japanese", custom_prompt="be formal")
        prompt = svc.api_manager.translate.call_args[0][0]
        assert "Do NOT censor" in prompt
