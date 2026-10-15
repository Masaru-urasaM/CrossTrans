"""
Tests for Phase J5 - one rule for Japanese vs Chinese across the app's detectors.

Before J5 three detectors gave three answers (TODO.md F5): `nlp_manager.detect_language()`
called every kanji-only text "Chinese (Simplified)" and scored ordinary Japanese
sentences below the Dictionary's 0.7 threshold (F4), History labelled 勉強 "Chinese",
and `furigana.should_annotate()` let a Japanese hint put readings on 我们. All three
now ask `lang_id`: kana is Japanese, a glyph only one language writes is that
language, and kanji that prove nothing are unknown.

Pure logic - no display.
"""
import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.core import furigana
from src.core.history import HistoryManager
from src.core.nlp_manager import AMBIGUOUS_CJK_CONFIDENCE, nlp_manager


# --------------------------------------------------------------------------- #
# nlp_manager.detect_language - the F4 table, re-measured
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text, expected", [
    ("勉強", ("Unknown", AMBIGUOUS_CJK_CONFIDENCE)),
    ("手紙", ("Unknown", AMBIGUOUS_CJK_CONFIDENCE)),
    ("東京大学", ("Unknown", AMBIGUOUS_CJK_CONFIDENCE)),
    ("大丈夫", ("Unknown", AMBIGUOUS_CJK_CONFIDENCE)),
    ("経済", ("Japanese", 0.9)),
    ("私は学生です。", ("Japanese", 1.0)),
    ("「勉強」という言葉", ("Japanese", 1.0)),
    ("Pythonで開発する", ("Japanese", 1.0)),
    ("友達に手紙を書きました。", ("Japanese", 1.0)),
    ("毎日日本語を勉強しています。", ("Japanese", 1.0)),
    ("我们在学习中文。", ("Chinese (Simplified)", 0.9)),
    ("說話", ("Chinese (Traditional)", 0.9)),
])
def test_detect_language_on_the_f4_table(text, expected):
    assert nlp_manager.detect_language(text) == expected


@pytest.mark.parametrize("text", ["這是我的書。", "這裏的人很多。", "公衆", "我們明天見。"])
def test_traditional_chinese_is_never_japanese(text):
    language, _confidence = nlp_manager.detect_language(text)
    assert language != "Japanese"


def test_kana_always_clears_the_dictionarys_threshold():
    """DoD4: Japanese with kana never lands in "Cannot detect language"."""
    for text in ("私は学生です。", "これ", "コーヒー", "日本語を話します"):
        assert nlp_manager.detect_language(text) == ("Japanese", 1.0), text


def test_ambiguity_is_above_zero_and_below_the_threshold():
    assert 0 < AMBIGUOUS_CJK_CONFIDENCE < 0.7


@pytest.mark.parametrize("text, expected_language", [
    ("안녕하세요", "Korean"),
    ("สวัสดีครับ", "Thai"),
    ("Привет, как дела?", "Russian"),
])
def test_other_scripts_are_untouched(text, expected_language):
    assert nlp_manager.detect_language(text)[0] == expected_language


def test_latin_text_still_prefers_the_installed_european_pack(monkeypatch):
    monkeypatch.setattr(nlp_manager, 'is_installed', lambda lang: lang == "German")
    assert nlp_manager.detect_language("Guten Morgen") == ("German", 0.85)


@pytest.mark.parametrize("text", ["", "   ", "!!!"])
def test_nothing_readable_is_unknown_with_no_confidence(text):
    assert nlp_manager.detect_language(text) == ("Unknown", 0.0)


# --------------------------------------------------------------------------- #
# History's label
# --------------------------------------------------------------------------- #
class FakeConfig:
    def get(self, key, default=None):
        return default

    def set(self, key, value):
        pass


@pytest.mark.parametrize("text, label", [
    ("勉強", "Unknown"),                 # was "Chinese" (F5)
    ("東京大学", "Unknown"),
    ("経済", "Japanese"),
    ("私は学生です。", "Japanese"),
    ("我们在学习中文。", "Chinese (Simplified)"),
    ("說話", "Chinese (Traditional)"),
    ("列夫・托尔斯泰", "Chinese (Simplified)"),   # ・ is not kana
    ("안녕하세요", "Korean"),
    ("Hello there", "English"),
    ("Привет", "Russian"),
])
def test_history_labels_follow_the_evidence(text, label):
    assert HistoryManager(FakeConfig())._detect_language(text) == label


# --------------------------------------------------------------------------- #
# should_annotate: a Japanese hint never overrides a Chinese-only glyph
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text, hint, expected", [
    ("勉強", "Japanese", True),
    ("勉強", None, False),
    ("我们", "Japanese", False),
    ("说话", "Japanese", False),
    ("私は学生", None, True),
    ("习近平が来日した", None, True),       # kana outweighs a Chinese name
    ("列夫・托尔斯泰", None, False),        # ・ alone is not kana
    ("列夫・托尔斯泰", "Japanese", False),
    ("東京・大阪", "Japanese", True),
    ("Hello", "Japanese", False),
])
def test_should_annotate_guard(text, hint, expected):
    assert furigana.should_annotate(text, hint) is expected


def test_a_chinese_glyph_under_a_japanese_hint_gets_no_reading():
    assert furigana.generate_notation("我们", "Japanese") is None
