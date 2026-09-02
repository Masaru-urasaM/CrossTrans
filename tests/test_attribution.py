"""
Tests for the "Translated with <model> (<Provider>)" credit line.

The popup used to say nothing about where a result came from, which matters
here more than in most apps: the configured model is not necessarily the one
that answered. Auto-detection picks a model when the field is left blank, and
model rotation silently substitutes another when the first one fails, so a user
comparing two translations of the same text had no way to tell whether they
were comparing models or comparing runs.

Three things have to hold for the note to be worth showing:

* it names the model that *actually* answered, not the configured one;
* a failed call never gets credited - the note describes a result that exists;
* a cache hit credits whoever produced the stored entry, or says nothing at
  all. Crediting the model that merely ran most recently would be a lie, and a
  quiet one.
"""
import tkinter as tk
from unittest.mock import MagicMock

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.constants import TRIAL_MODEL
from src.core.api_manager import AIAPIManager
from src.core.history import HistoryManager
from src.core.translation import TranslationService
from src.ui.quick_translate import QuickTranslateManager, ATTRIBUTION_PX


class FakeConfig:
    """Dict-backed config, enough for HistoryManager."""

    def __init__(self, history=None):
        self._store = {'history': list(history or []), 'history_enabled': True}

    def get(self, key, default=None):
        return self._store.get(key, default)

    def set(self, key, value):
        self._store[key] = value

    def get_furigana_enabled(self):
        return False

    def get_quick_replace(self):
        return False


def entry(original, translated, target_lang, source_type='text', model_used='Auto'):
    return {
        'original': original,
        'translated': translated,
        'target_lang': target_lang,
        'source_type': source_type,
        'model_used': model_used,
    }


def make_manager(result="hello"):
    """An API manager whose provider dispatch is stubbed out."""
    manager = AIAPIManager()
    manager._route_generate_content = lambda *a, **k: result
    manager._route_generate_multimodal = lambda *a, **k: result
    return manager


def make_service(history=None, api_result="RESULT", attribution="m (P)"):
    """A TranslationService with only what the tested methods touch."""
    service = TranslationService.__new__(TranslationService)
    service._is_trial_mode = False
    service.trial_client = None
    service.last_attribution = None
    service.api_manager = MagicMock()
    service.api_manager.translate.return_value = api_result
    service.api_manager.last_attribution = attribution
    service.history_manager = HistoryManager(FakeConfig(history=history))
    return service


# --------------------------------------------------------------------------- #
# APIManager: who answered
# --------------------------------------------------------------------------- #
class TestApiManagerRecordsWhoAnswered:
    def test_nothing_is_credited_before_the_first_call(self):
        assert make_manager().last_attribution is None

    def test_a_successful_call_is_credited(self):
        manager = make_manager()
        manager._generate_content('Groq', 'key', 'llama-3.3-70b', 'prompt')
        assert manager.last_attribution == 'llama-3.3-70b (Groq)'

    def test_the_model_that_answered_wins_over_the_configured_one(self):
        # Rotation and auto-detect both call _generate_content with a different
        # model than the one in Settings; that is the whole point of the note.
        manager = make_manager()
        manager._generate_content('Google', 'key', 'gemini-2.0-flash', 'prompt')
        manager._generate_content('Google', 'key', 'gemini-2.5-pro', 'prompt')
        assert manager.last_attribution == 'gemini-2.5-pro (Google)'

    def test_a_failed_call_credits_nobody(self):
        manager = make_manager()
        manager._generate_content('Groq', 'key', 'llama-3.3-70b', 'prompt')

        def boom(*a, **k):
            raise Exception("503")

        manager._route_generate_content = boom
        with pytest.raises(Exception):
            manager._generate_content('Google', 'key', 'gemini-2.5-pro', 'prompt')
        assert manager.last_attribution == 'llama-3.3-70b (Groq)'

    def test_multimodal_is_credited_too(self):
        manager = make_manager()
        manager._generate_content_multimodal('Google', 'key', 'gemini-2.5-flash',
                                             'prompt', ['a.png'], {})
        assert manager.last_attribution == 'gemini-2.5-flash (Google)'

    def test_a_provider_less_credit_is_just_the_model(self):
        manager = make_manager()
        manager._record_attribution('some-model', '')
        assert manager.last_attribution == 'some-model'


# --------------------------------------------------------------------------- #
# TranslationService: one place records it
# --------------------------------------------------------------------------- #
class TestServiceRecordsTheCredit:
    def test_a_live_call_takes_the_managers_credit(self):
        service = make_service(attribution='gemini-2.0-flash (Google)')
        assert service._call_model('prompt') == "RESULT"
        assert service.last_attribution == 'gemini-2.0-flash (Google)'

    def test_trial_mode_names_the_proxy_model(self):
        service = make_service()
        service._is_trial_mode = True
        service.trial_client = object()
        service._translate_trial = lambda prompt: "TRIAL"
        assert service._call_model('prompt') == "TRIAL"
        assert service.last_attribution == f"{TRIAL_MODEL} (Trial mode)"

    def test_a_failed_call_leaves_the_previous_credit_alone(self):
        service = make_service(attribution='gemini-2.0-flash (Google)')
        service._call_model('prompt')
        service.api_manager.translate.side_effect = Exception("503")
        with pytest.raises(Exception):
            service._call_model('prompt')
        assert service.last_attribution == 'gemini-2.0-flash (Google)'


class TestCachedCredit:
    def test_a_stored_credit_is_reused_and_marked_cached(self):
        got = TranslationService._cached_attribution(
            entry("Hi", "Xin chao", "Vietnamese", model_used='gemini-2.0-flash (Google)'))
        assert got == 'gemini-2.0-flash (Google), cached'

    @pytest.mark.parametrize("stored", ['Auto', '', '   ', None])
    def test_an_entry_that_names_nothing_gets_no_note(self, stored):
        assert TranslationService._cached_attribution(
            entry("Hi", "Xin chao", "Vietnamese", model_used=stored)) is None

    def test_a_missing_field_gets_no_note(self):
        assert TranslationService._cached_attribution({'translated': 'x'}) is None


class TestTranslateTextEndToEnd:
    def test_a_cache_hit_credits_the_stored_model(self):
        service = make_service(
            history=[entry("Hi", "Xin chao", "Vietnamese",
                           model_used='gemini-2.0-flash (Google)')],
            attribution='llama-3.3-70b (Groq)')
        assert service.translate_text("Hi", "Vietnamese") == "Xin chao"
        # Not the Groq model, which is merely what ran most recently.
        assert service.last_attribution == 'gemini-2.0-flash (Google), cached'
        service.api_manager.translate.assert_not_called()

    def test_a_live_translation_credits_the_live_model(self):
        service = make_service(api_result="Xin chao",
                               attribution='llama-3.3-70b (Groq)')
        assert service.translate_text("Hi", "Vietnamese") == "Xin chao"
        assert service.last_attribution == 'llama-3.3-70b (Groq)'

    def test_the_credit_is_written_into_history(self):
        # This is what makes the *next* cache hit creditable.
        service = make_service(api_result="Xin chao",
                               attribution='llama-3.3-70b (Groq)')
        service.translate_text("Hi", "Vietnamese")
        stored = service.history_manager.get_history()[0]
        assert stored['model_used'] == 'llama-3.3-70b (Groq)'

    def test_a_second_run_of_the_same_text_reports_it_as_cached(self):
        service = make_service(api_result="Xin chao",
                               attribution='llama-3.3-70b (Groq)')
        service.translate_text("Hi", "Vietnamese")
        service.api_manager.last_attribution = 'gemini-2.0-flash (Google)'
        service.translate_text("Hi", "Vietnamese")
        assert service.last_attribution == 'llama-3.3-70b (Groq), cached'


# --------------------------------------------------------------------------- #
# The note itself
# --------------------------------------------------------------------------- #
def label_texts(widget):
    """Every label caption in the window, in creation order."""
    found = []
    for child in widget.winfo_children():
        try:
            text = str(child.cget('text'))
        except tk.TclError:
            text = ''
        if text and 'label' in child.winfo_class().lower():
            found.append(text)
        found.extend(label_texts(child))
    return found


@pytest.fixture
def popup(tk_root):
    created = []

    def _show(translated="Bonjour", target_lang="French", **kwargs):
        manager = QuickTranslateManager(tk_root, FakeConfig())
        manager._last_mouse_x, manager._last_mouse_y = 500, 300
        manager.show(translated, target_lang, **kwargs)
        tk_root.update()
        created.append(manager)
        return manager

    yield _show
    for manager in created:
        try:
            manager.close()
        except Exception:
            pass


class TestTheNoteOnThePopup:
    def test_it_names_the_model_and_provider(self, popup):
        manager = popup(model_info="gemini-2.0-flash (Google)")
        assert "Translated with gemini-2.0-flash (Google)" in label_texts(manager.popup)

    def test_it_is_the_top_line(self, popup):
        # Above the trial header, which is itself above everything else.
        manager = popup(model_info="gemini-2.0-flash (Google)",
                        trial_info={'is_trial': True, 'remaining': 30, 'daily_limit': 50})
        texts = label_texts(manager.popup)
        assert texts[0].startswith("Translated with")
        assert any(t.startswith("Trial Mode") for t in texts[1:])

    def test_no_credit_means_no_line(self, popup):
        manager = popup(model_info=None)
        assert manager.popup_attribution is None
        assert not any(t.startswith("Translated with") for t in label_texts(manager.popup))

    def test_a_failure_notice_is_never_credited(self, popup):
        manager = popup("Error: API request failed (503)",
                        model_info="gemini-2.0-flash (Google)")
        assert not any(t.startswith("Translated with") for t in label_texts(manager.popup))

    def test_a_grammar_fix_was_not_translated(self, popup):
        manager = popup("I have been there.", "Grammar", is_grammar=True,
                        model_info="gemini-2.0-flash (Google)")
        assert "Fixed with gemini-2.0-flash (Google)" in label_texts(manager.popup)

    def test_the_popup_grows_by_exactly_the_note(self, popup):
        # The box below must not lose a row to make room for the note.
        without = popup("Bonjour le monde")
        with_note = popup("Bonjour le monde", model_info="gemini-2.0-flash (Google)")
        assert (with_note.popup.winfo_height() - without.popup.winfo_height()
                == ATTRIBUTION_PX)

    def test_it_is_smaller_and_dimmer_than_the_translation(self, popup):
        manager = popup(model_info="gemini-2.0-flash (Google)")
        label = manager.popup_attribution
        assert 'italic' in str(label.cget('font'))
        assert str(label.cget('foreground')) != '#ffffff'

    def test_it_is_forgotten_when_the_popup_closes(self, popup):
        manager = popup(model_info="gemini-2.0-flash (Google)")
        manager.close()
        assert manager.popup_attribution is None
