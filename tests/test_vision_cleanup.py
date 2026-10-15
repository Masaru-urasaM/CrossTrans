"""
Reasoning tags are stripped on the vision paths too, not just on text.

`TranslationService` cleaned every text result it produced, but the three vision
callers never went through it: `app.py` (image/file translation),
`screenshot_handler.py` (Win+Alt+S) and `pdf_ocr.py` all call the API manager
directly. A reasoning model - DeepSeek-R1, Qwen3, gpt-oss, any of which the user
can select and model rotation can substitute - would have put its whole
<think>...</think> monologue on screen, or into the OCR text a scanned PDF is
translated from.

The cleanup now sits in `_generate_content` / `_generate_content_multimodal`,
the two dispatch points every call in the class funnels through - the same place
the model credit is recorded, and for the same reason: one site, not eight
return statements.
"""
import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.core.api_manager import AIAPIManager
from src.core.text_cleanup import strip_thinking_tags
from src.core.translation import TranslationService


THINKING = "<think>The user wants Japanese.\nLet me consider.</think>\nこんにちは"


def make_manager(result=THINKING):
    """An API manager whose provider dispatch is stubbed out."""
    manager = AIAPIManager()
    manager._route_generate_content = lambda *a, **k: result
    manager._route_generate_multimodal = lambda *a, **k: result
    return manager


def vision_manager(result=THINKING):
    """...and which believes it has one working vision-capable key."""
    manager = make_manager(result)
    manager.configure([{
        'model_name': 'qwen3-vl-235b',
        'api_key': 'test-key',
        'provider': 'Groq',
        'vision_capable': True,
    }])
    return manager


class TestTheCleanupItself:
    def test_it_removes_the_block(self):
        assert strip_thinking_tags(THINKING) == "こんにちは"

    def test_it_is_case_insensitive(self):
        assert strip_thinking_tags("<THINK>x</THINK>Hello") == "Hello"

    def test_it_spans_lines(self):
        assert strip_thinking_tags("<think>a\nb\nc</think>Bonjour") == "Bonjour"

    def test_it_removes_every_block(self):
        assert strip_thinking_tags("<think>a</think>One<think>b</think>Two") == "OneTwo"

    def test_it_is_idempotent(self):
        once = strip_thinking_tags(THINKING)
        assert strip_thinking_tags(once) == once

    def test_it_leaves_ordinary_text_alone(self):
        text = "The <b>bold</b> plan: think about it."
        assert strip_thinking_tags(text) == text

    @pytest.mark.parametrize('value', ['', None])
    def test_it_is_safe_on_nothing(self, value):
        assert strip_thinking_tags(value) == value

    def test_an_unclosed_tag_is_left_alone(self):
        # Better a visible oddity than swallowing the whole answer.
        text = "<think>never closed, and the answer follows"
        assert strip_thinking_tags(text) == text


class TestTheDispatchPoints:
    def test_text_dispatch_strips(self):
        manager = make_manager()

        assert manager._generate_content('Groq', 'k', 'm', 'prompt') == "こんにちは"

    def test_multimodal_dispatch_strips(self):
        manager = make_manager()

        result = manager._generate_content_multimodal('Groq', 'k', 'm', 'prompt', [], {})

        assert result == "こんにちは"

    def test_the_credit_is_still_recorded(self):
        # The strip wraps the same call the attribution reads; neither may lose.
        manager = make_manager()

        manager._generate_content('Groq', 'k', 'llama-4-scout', 'prompt')

        assert manager.last_model == 'llama-4-scout'
        assert manager.last_provider == 'Groq'
        assert manager.last_attribution == 'llama-4-scout (Groq)'

    def test_a_clean_answer_is_untouched(self):
        manager = make_manager(result="Plain answer")

        assert manager._generate_content('Groq', 'k', 'm', 'prompt') == "Plain answer"


class TestTheCallersThatNeededIt:
    def test_translate_image_returns_clean_text(self):
        # app.py image translation and pdf_ocr.py both land here.
        manager = vision_manager()

        assert manager.translate_image("Describe", "fake.png") == "こんにちは"

    def test_translate_multimodal_returns_clean_text(self):
        # screenshot_handler.py (Win+Alt+S) lands here.
        manager = vision_manager()

        result = manager.translate_multimodal("Translate", image_paths=["fake.png"])

        assert result == "こんにちは"

    def test_a_rotated_model_is_cleaned_too(self):
        # Rotation returns its result straight to the caller, bypassing the
        # normal return statement - but every candidate it tries goes through
        # _dispatch_call, so covering that covers rotation on both branches.
        manager = vision_manager()

        single = manager._dispatch_call('Groq', 'k', 'other-model', 'prompt',
                                        image_path='fake.png')
        multi = manager._dispatch_call('Groq', 'k', 'other-model', 'prompt',
                                       image_paths=['fake.png'])

        assert single == "こんにちは"
        assert multi == "こんにちは"


class TestTheServiceStillCleans:
    def test_the_method_delegates_to_the_shared_function(self):
        # The trial proxy does not go through the API manager, so this stays.
        service = TranslationService.__new__(TranslationService)

        assert service._strip_thinking_tags(THINKING) == "こんにちは"
