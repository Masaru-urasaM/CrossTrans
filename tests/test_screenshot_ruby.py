"""
Tests for Phase J8 - a Japanese screenshot shows what it read, with readings (Q6).

The screenshot popup used to show only the translation, and History stored the
literal "[Screenshot OCR]" as the original. Now the vision prompt also asks for
the text's language (`===SOURCE LANGUAGE===`, the model's verdict - Decision 22),
the OCR'd text is shown with readings above the translation when it is Japanese
(evidence first, then that verdict), the verdict is recorded for the popup, its
Dictionary and its chooser, and History keeps the OCR text.

No display needed: the handler's thread runs inline and the popup is a recorder.
"""
from unittest.mock import MagicMock

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.core import furigana as F
from src.core.history import HistoryManager
from src.core.lang_id import CHINESE_SIMPLIFIED, JAPANESE
from src.core.translation import TranslationService
from src.ui.screenshot_handler import (OCR_FALLBACK_ORIGINAL, ScreenshotHandler, ocr_prompt,
                                       parse_ocr_result)

HAS_PROVIDER = pytest.mark.skipif(not F.is_available(),
                                  reason="requires a reading provider (fugashi or pykakasi)")


def answer(original, source, translation):
    return (f"===ORIGINAL===\n{original}\n\n===SOURCE LANGUAGE===\n{source}\n\n"
            f"===TRANSLATION===\n{translation}")


# --------------------------------------------------------------------------- #
# The prompt and its answer
# --------------------------------------------------------------------------- #
def test_the_prompt_asks_for_the_language_between_the_two_sections():
    prompt = ocr_prompt("English")
    assert prompt.index("===ORIGINAL===") < prompt.index("===SOURCE LANGUAGE===") \
        < prompt.index("===TRANSLATION===")
    assert "Write Unknown if you cannot tell" in prompt


def test_the_prompt_names_no_favourite():
    wording = ocr_prompt("English").lower()
    for leaning in ("more common", "frequent", "likely", "usually", "prefer"):
        assert leaning not in wording, leaning


@pytest.mark.parametrize("result, expected", [
    (answer("東京大学", "Japanese", "The University of Tokyo"),
     ("東京大学", JAPANESE, "The University of Tokyo")),
    (answer("我们", "Chinese", "we"), ("我们", CHINESE_SIMPLIFIED, "we")),
    (answer("先生", "Unknown", "teacher"), ("先生", None, "teacher")),
    (answer("Hello", "English", "Bonjour"), ("Hello", "English", "Bonjour")),
    ("===ORIGINAL===\n手紙\n===TRANSLATION===\nletter", ("手紙", None, "letter")),
    ("===ORIGINAL===\n床\n===TRANSLATION===\nfloor\n===SOURCE LANGUAGE===\nJapanese.",
     ("床", JAPANESE, "floor")),
    ("=== ORIGINAL === 汽車 === TRANSLATION === train", ("汽車", None, "train")),
    ("===ORIGINAL===\n手紙", (OCR_FALLBACK_ORIGINAL, None, "===ORIGINAL===\n手紙")),
    ("just a translation", (OCR_FALLBACK_ORIGINAL, None, "just a translation")),
    ("", (OCR_FALLBACK_ORIGINAL, None, "")),
])
def test_parse_ocr_result(result, expected):
    assert parse_ocr_result(result) == expected


# --------------------------------------------------------------------------- #
# The handler
# --------------------------------------------------------------------------- #
class _SyncThread:
    def __init__(self, target=None, daemon=None, **kwargs):
        self._target = target

    def start(self):
        self._target()


class FakeHistoryConfig:
    def __init__(self):
        self._store = {'history': [], 'history_enabled': True}

    def get(self, key, default=None):
        return self._store.get(key, default)

    def set(self, key, value):
        self._store[key] = value


@pytest.fixture
def run(monkeypatch):
    """Run one screenshot through the real handler; returns what the popup got."""
    monkeypatch.setattr('threading.Thread', _SyncThread)

    def _run(model_answer, furigana_enabled=True):
        service = TranslationService.__new__(TranslationService)
        service.api_manager = MagicMock()
        service.api_manager.translate_multimodal.return_value = model_answer
        service.api_manager.last_attribution = "vision-model (Test)"
        service.history_manager = HistoryManager(FakeHistoryConfig())
        service.get_trial_info = lambda: None
        config = MagicMock()
        config.get_furigana_enabled.return_value = furigana_enabled
        root = MagicMock()
        root.after.side_effect = lambda delay, callback: callback()
        handler = ScreenshotHandler(root, config, service, MagicMock(), MagicMock())
        shown = []
        handler.configure_callbacks(on_show_quick_translate=lambda *a: shown.append(a))
        handler._screenshot_target_language = "English"
        handler._on_screenshot_captured("shot.png")
        assert len(shown) == 1, shown
        original, translated, target, trial_info, furigana_text = shown[0]
        return {'original': original, 'translated': translated, 'furigana': furigana_text,
                'service': service, 'history': service.history_manager.get_history()}
    return _run


class TestHandler:
    @HAS_PROVIDER
    def test_japanese_with_kana_is_shown_with_readings(self, run):
        out = run(answer("毎日日本語を勉強します", "Japanese", "I study Japanese every day"))
        assert out['original'] == "毎日日本語を勉強します"
        assert "{勉強|べんきょう}" in out['furigana']

    @HAS_PROVIDER
    def test_kanji_the_model_called_japanese_is_read(self, run):
        out = run(answer("東京大学", "Japanese", "The University of Tokyo"))
        assert out['furigana'] == "{東京大学|とうきょうだいがく}"

    def test_kanji_the_model_called_chinese_is_not(self, run):
        assert run(answer("東京大学", "Chinese", "Tokyo University"))['furigana'] is None

    def test_unplaced_kanji_is_not(self, run):
        assert run(answer("先生", "Unknown", "teacher"))['furigana'] is None

    def test_a_chinese_glyph_beats_a_japanese_verdict(self, run):
        assert run(answer("我们在学习", "Japanese", "we are studying"))['furigana'] is None

    def test_an_answer_without_sections_shows_no_block(self, run):
        out = run("Some translated text")
        assert (out['original'], out['furigana']) == (OCR_FALLBACK_ORIGINAL, None)

    @HAS_PROVIDER
    def test_furigana_off_shows_no_block(self, run):
        out = run(answer("毎日日本語を勉強します", "Japanese", "I study"), furigana_enabled=False)
        assert out['furigana'] is None

    def test_the_verdict_is_recorded_for_the_popup(self, run):
        out = run(answer("先生", "Japanese", "teacher"))
        assert out['service'].source_verdict("先生") == JAPANESE
        assert out['service'].last_source_language == JAPANESE

    def test_history_keeps_the_ocr_text_and_its_verdict(self, run):
        entry = run(answer("先生", "Japanese", "teacher"))['history'][0]
        assert (entry['original'], entry['translated']) == ("先生", "teacher")
        assert entry['source_type'] == "screenshot"
        assert entry['source_verdict'] == JAPANESE

    def test_history_falls_back_to_the_placeholder(self, run):
        entry = run("Some translated text")['history'][0]
        assert entry['original'] == "[Screenshot OCR]"
        assert 'source_verdict' not in entry
