"""
Tests for Phase J4 - the translation prompts learn the source language (Decision 22, Q7).

Mostly-CJK text whose characters prove its language gets that language stated in
the prompt; kanji-only text that proves nothing makes the prompt ask the model to
name the language on a `[[SOURCE: ...]]` line, which the service reads, removes,
remembers (`last_source_language`, `source_verdict()`) and stores in History as
`source_verdict`. Every other text is sent exactly as before.

Measured on real models before this was wired (2026-10-15, tools/eval_dictionary_prompt.py
--mode translate, ten kanji-only false friends, target English): gemini-2.5-flash and
gpt-oss-120b each wrote the marker 10/10 times, it never leaked into a result, and they
answered Unknown 3 and 4 times.

Pure logic and a service built with __new__ - no display, no network.
"""
import logging
from unittest.mock import MagicMock

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
import src.core.translation as translation_module
from src.core.history import HistoryManager
from src.core.lang_id import CHINESE_SIMPLIFIED, JAPANESE
from src.core.source_marker import (MARKER_CHINESE, MARKER_JAPANESE, MARKER_UNKNOWN,
                                    SourceClause, cjk_dominant, parse_source_marker,
                                    source_clause)
from src.core.translation import TranslationService


# --------------------------------------------------------------------------- #
# Which texts get a clause
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text", ["勉強", "東京大学", "友達に手紙を書きました。", "我们在学习中文。",
                                  "経済 2026"])
def test_mostly_cjk_text(text):
    assert cjk_dominant(text)


@pytest.mark.parametrize("text", ["", None, "Hello", "I love 你 so much", "12345",
                                  "한국어 漢字", "大韓民國의 憲法", "Python と Django と Flask framework"])
def test_text_that_is_not_mostly_cjk(text):
    assert not cjk_dominant(text)


def test_latin_text_leaves_the_prompt_unchanged():
    assert source_clause("Hello, how are you?") == SourceClause("", None, False)


def test_kana_states_japanese_and_asks_nothing():
    clause = source_clause("友達に手紙を書きました。")
    assert clause.stated == JAPANESE and not clause.asks
    assert clause.text == "\n\nSOURCE LANGUAGE: the text above is Japanese."


def test_a_chinese_glyph_states_chinese_and_asks_nothing():
    clause = source_clause("我们在学习中文。")
    assert clause.stated == CHINESE_SIMPLIFIED and not clause.asks
    assert clause.text == "\n\nSOURCE LANGUAGE: the text above is Chinese."


def test_ambiguous_kanji_asks_for_the_marker():
    clause = source_clause("勉強")
    assert clause.asks and clause.stated is None
    for marker in (MARKER_JAPANESE, MARKER_CHINESE, MARKER_UNKNOWN):
        assert marker in clause.text
    assert "Begin your response with exactly one of these lines" in clause.text


def test_the_question_names_no_favourite():
    """J1 measured a "more common" tie-break turning 先生 into Chinese (Decision 21)."""
    wording = source_clause("勉強").text.lower()
    for leaning in ("common", "frequent", "likely", "usually", "prefer", "default to"):
        assert leaning not in wording, leaning


def test_the_example_is_not_one_of_the_measured_words():
    """An example word in the prompt would tell the eval its own answer."""
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'tools'))
    from eval_dictionary_prompt import EVAL_WORDS
    wording = source_clause("勉強").text
    assert not any(word in wording for word, *_ in EVAL_WORDS)


# --------------------------------------------------------------------------- #
# Reading the marker
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("answer, expected", [
    ("[[SOURCE: Japanese]]\nStudy", ("Study", JAPANESE, True)),
    ("[[SOURCE: Chinese]]\nWork", ("Work", CHINESE_SIMPLIFIED, True)),
    ("[[SOURCE: Unknown]]\nBed", ("Bed", None, True)),
    ("[[ source : japanese ]]\n\nStudy", ("Study", JAPANESE, True)),
    ("[[SOURCE： Japanese]]\nStudy", ("Study", JAPANESE, True)),
    ("[[SOURCE: Japanese]] Study", ("Study", JAPANESE, True)),
    ("Study\n[[SOURCE: Japanese]]", ("Study", JAPANESE, True)),
    ("SOURCE: Japanese\nStudy", ("Study", JAPANESE, True)),
    ("[SOURCE: Chinese]\nWork", ("Work", CHINESE_SIMPLIFIED, True)),
    ("[[SOURCE: Klingon]]\nStudy", ("Study", None, True)),
    ("[[SOURCE: Japanese.]]\nStudy", ("Study", JAPANESE, True)),
    ("Study", ("Study", None, False)),
    ("", ("", None, False)),
])
def test_parse_source_marker(answer, expected):
    assert parse_source_marker(answer) == expected


def test_the_rest_of_the_answer_keeps_its_lines():
    answer = "[[SOURCE: Japanese]]\nLine one\n\n  Line two"
    assert parse_source_marker(answer)[0] == "Line one\n\n  Line two"


def test_a_source_line_later_in_the_text_is_the_text():
    answer = "The report lists:\nSOURCE: the 2025 census"
    assert parse_source_marker(answer) == (answer, None, False)


# --------------------------------------------------------------------------- #
# The service
# --------------------------------------------------------------------------- #
class FakeConfig:
    def __init__(self, history=None, history_enabled=True):
        self._store = {'history': list(history or []), 'history_enabled': history_enabled}

    def get(self, key, default=None):
        return self._store.get(key, default)

    def set(self, key, value):
        self._store[key] = value


def make_service(answer="RESULT", history=None, history_enabled=True):
    svc = TranslationService.__new__(TranslationService)
    svc._is_trial_mode = False
    svc.trial_client = None
    svc.api_manager = MagicMock()
    svc.api_manager.translate.return_value = answer
    svc.api_manager.last_attribution = "test-model (Test)"
    svc.history_manager = HistoryManager(FakeConfig(history, history_enabled))
    return svc


def sent_prompt(svc):
    return svc.api_manager.translate.call_args[0][0]


@pytest.fixture(params=["merged", "plain"])
def translate(request):
    """Both entry points: the hotkeys' translate_or_fix and the main window's translate_text."""
    if request.param == "merged":
        return lambda svc, text, target="English", **kw: svc.translate_or_fix(text, target, **kw)
    return lambda svc, text, target="English", **kw: svc.translate_text(text, target, **kw)


class TestServiceAsksAndReads:
    def test_the_marker_is_asked_read_and_removed(self, translate):
        svc = make_service("[[SOURCE: Japanese]]\nStudy")
        assert translate(svc, "勉強") == "Study"
        assert MARKER_UNKNOWN in sent_prompt(svc)
        assert svc.last_source_language == JAPANESE

    def test_the_verdict_is_stored_in_history(self, translate):
        svc = make_service("[[SOURCE: Japanese]]\nStudy")
        translate(svc, "勉強")
        entry = svc.history_manager.get_history()[0]
        assert entry['translated'] == "Study"
        assert entry['source_verdict'] == JAPANESE
        assert entry['source_lang'] == JAPANESE

    def test_a_missing_marker_is_no_verdict_and_no_error(self, translate):
        svc = make_service("Study")
        assert translate(svc, "勉強") == "Study"
        assert svc.last_source_language is None
        assert 'source_verdict' not in svc.history_manager.get_history()[0]

    def test_unknown_is_no_verdict(self, translate):
        svc = make_service("[[SOURCE: Unknown]]\nBed")
        assert translate(svc, "床") == "Bed"
        assert svc.last_source_language is None

    def test_evidence_is_stated_and_nothing_is_parsed(self, translate):
        svc = make_service("I wrote a letter.")
        translate(svc, "友達に手紙を書きました。")
        prompt = sent_prompt(svc)
        assert prompt.endswith("SOURCE LANGUAGE: the text above is Japanese.")
        assert MARKER_JAPANESE not in prompt
        assert svc.last_source_language is None

    def test_other_text_is_sent_byte_for_byte_as_before(self, translate, monkeypatch):
        svc = make_service("Bonjour")
        translate(svc, "Hello there", "French")
        with_j4 = sent_prompt(svc)
        monkeypatch.setattr(translation_module, 'source_clause',
                            lambda text: SourceClause("", None, False))
        translate(svc, "Hello there", "French", skip_cache=True)
        assert with_j4 == sent_prompt(svc)

    def test_a_failed_call_leaves_no_stale_verdict(self, translate):
        svc = make_service("[[SOURCE: Japanese]]\nStudy")
        translate(svc, "勉強")
        svc.api_manager.translate.side_effect = RuntimeError("503")
        assert translate(svc, "手紙", skip_cache=True).startswith("Error:")
        assert svc.last_source_language is None

    def test_the_log_line_has_no_text(self, translate, caplog):
        svc = make_service("[[SOURCE: Japanese]]\nStudy")
        with caplog.at_level(logging.INFO):
            translate(svc, "勉強")
        lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[LangID]")]
        assert lines == ["[LangID] translation verdict=Japanese marker=found chars=2"]


class TestCacheAndMemory:
    def test_a_cache_hit_restores_the_stored_verdict(self):
        svc = make_service("[[SOURCE: Japanese]]\nStudy")
        svc.translate_or_fix("勉強", "English")
        svc.last_source_language = None
        assert svc.translate_or_fix("勉強", "English") == "Study"
        assert svc.api_manager.translate.call_count == 1
        assert svc.last_source_language == JAPANESE

    def test_an_entry_from_before_j4_has_no_verdict(self):
        old = {'original': "勉強", 'translated': "Study", 'target_lang': "English",
               'source_type': 'text', 'source_lang': "Chinese", 'model_used': 'Auto'}
        svc = make_service(history=[old])
        assert svc.translate_text("勉強", "English") == "Study"
        assert svc.last_source_language is None

    def test_source_verdict_remembers_this_sessions_texts(self):
        svc = make_service("[[SOURCE: Japanese]]\nStudy", history_enabled=False)
        svc.translate_or_fix("勉強", "English")
        svc.last_source_language = None
        assert svc.source_verdict("勉強") == JAPANESE
        assert svc.source_verdict("手紙") is None

    def test_source_verdict_survives_a_restart_through_history(self):
        first = make_service("[[SOURCE: Chinese]]\nWork")
        first.translate_or_fix("工作", "English")
        restarted = make_service(history=first.history_manager.get_history())
        assert restarted.source_verdict("工作") == CHINESE_SIMPLIFIED

    def test_a_detected_label_is_never_taken_for_a_verdict(self):
        detected = {'original': "勉強", 'translated': "Study", 'target_lang': "English",
                    'source_type': 'text', 'source_lang': "Chinese"}
        assert make_service(history=[detected]).source_verdict("勉強") is None

    def test_the_session_memory_is_bounded(self):
        svc = make_service("[[SOURCE: Japanese]]\nX", history_enabled=False)
        texts = [f"漢字{i}" for i in range(TranslationService.SOURCE_VERDICTS_MAX + 1)]
        for text in texts:
            svc.translate_or_fix(text, "English")
        assert svc.source_verdict(texts[0]) is None
        assert svc.source_verdict(texts[-1]) == JAPANESE

    def test_a_custom_prompt_is_sent_as_written(self):
        svc = make_service("[[SOURCE: Japanese]]\nStudy")
        svc.translate_text("勉強", "English", custom_prompt="Be formal.")
        assert "SOURCE LANGUAGE" not in sent_prompt(svc)
        assert svc.last_source_language is None


class TestHistory:
    def test_add_entry_stores_a_verdict_only_when_there_is_one(self):
        hm = HistoryManager(FakeConfig())
        hm.add_entry("勉強", "Study", "English")
        hm.add_entry("手紙", "Letter", "English", source_lang=JAPANESE, source_verdict=JAPANESE)
        newest, oldest = hm.get_history()
        assert newest['source_verdict'] == JAPANESE
        assert 'source_verdict' not in oldest

    def test_find_source_verdict_takes_the_newest_whatever_the_target(self):
        hm = HistoryManager(FakeConfig())
        hm.add_entry("先生", "Mr.", "English", source_verdict=CHINESE_SIMPLIFIED)
        hm.add_entry("先生", "Professeur", "French", source_verdict=JAPANESE)
        assert hm.find_source_verdict("先生") == JAPANESE
        assert hm.find_source_verdict("床") is None
        assert hm.find_source_verdict("") is None


class TestStrayMarkers:
    """Smoke-tested 2026-10-15: a model told the language could still write the
    marker, and nothing removed it - it reached the popup as the first line."""

    @pytest.mark.parametrize("answer, expected", [
        ("[[SOURCE: Unknown]]\nMr.", "Mr."),
        ("Teacher\n[[SOURCE: Japanese]]", "Teacher"),
        ("Source: English\nThe report", "Source: English\nThe report"),  # bare form: the text
        ("Teacher", "Teacher"),
        ("", ""),
    ])
    def test_strip_stray_markers(self, answer, expected):
        from src.core.source_marker import strip_stray_markers
        assert strip_stray_markers(answer) == expected

    def test_a_stated_source_never_shows_a_marker(self):
        svc = make_service("[[SOURCE: Unknown]]\nTeacher")
        assert svc.translate_text("先生", "English", source_language="Japanese") == "Teacher"
        assert svc.last_source_language == JAPANESE        # the user's answer, not the line

    def test_evidence_stated_never_shows_a_marker(self, translate):
        svc = make_service("[[SOURCE: Chinese]]\nI wrote a letter.")
        assert translate(svc, "友達に手紙を書きました。") == "I wrote a letter."
        assert svc.last_source_language is None

    def test_other_text_never_shows_a_marker(self, translate):
        svc = make_service("[[SOURCE: Japanese]]\nBonjour")
        assert translate(svc, "Hello there", "French") == "Bonjour"
