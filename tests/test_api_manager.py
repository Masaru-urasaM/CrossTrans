"""
Unit tests for api_manager.py - AI API communication.
"""
import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.api_manager import AIAPIManager


class TestProviderIdentification:
    """Tests for _identify_provider method."""

    def test_identify_google_gemini_model(self):
        """Test Google provider detection for Gemini models."""
        manager = AIAPIManager()

        assert manager._identify_provider('gemini-2.0-flash', '') == 'Google'
        assert manager._identify_provider('gemini-1.5-pro', '') == 'Google'
        assert manager._identify_provider('gemini-pro-vision', '') == 'Google'

    def test_identify_openai_models(self):
        """Test OpenAI provider detection."""
        manager = AIAPIManager()

        assert manager._identify_provider('gpt-4', '') == 'OpenAI'
        assert manager._identify_provider('gpt-4o', '') == 'OpenAI'
        assert manager._identify_provider('gpt-3.5-turbo', '') == 'OpenAI'
        assert manager._identify_provider('o1-preview', '') == 'OpenAI'

    def test_identify_anthropic_claude(self):
        """Test Anthropic provider detection for Claude models."""
        manager = AIAPIManager()

        assert manager._identify_provider('claude-3-opus', '') == 'Anthropic'
        assert manager._identify_provider('claude-3.5-sonnet', '') == 'Anthropic'

    def test_identify_by_api_key_pattern(self):
        """Test provider detection via API key prefix."""
        manager = AIAPIManager()

        # Groq key pattern
        assert manager._identify_provider('unknown-model', 'gsk_abc123') == 'Groq'

        # Anthropic key pattern
        assert manager._identify_provider('unknown-model', 'sk-ant-abc123') == 'Anthropic'

    def test_identify_groq_models(self):
        """Test Groq provider detection."""
        manager = AIAPIManager()

        assert manager._identify_provider('llama3-8b-8192', '') == 'Groq'
        assert manager._identify_provider('mixtral-8x7b-32768', '') == 'Groq'
        assert manager._identify_provider('gemma-7b-it', '') == 'Groq'

    def test_identify_deepseek(self):
        """Test DeepSeek provider detection."""
        manager = AIAPIManager()

        assert manager._identify_provider('deepseek-chat', '') == 'DeepSeek'
        assert manager._identify_provider('deepseek-coder', '') == 'DeepSeek'

    def test_identify_mistral(self):
        """Test Mistral provider detection."""
        manager = AIAPIManager()

        assert manager._identify_provider('mistral-large', '') == 'Mistral'
        assert manager._identify_provider('mistral-small', '') == 'Mistral'
        assert manager._identify_provider('codestral-latest', '') == 'Mistral'

    def test_identify_xai_grok(self):
        """Test xAI Grok provider detection."""
        manager = AIAPIManager()

        assert manager._identify_provider('grok-beta', '') == 'xAI'
        assert manager._identify_provider('grok-2', '') == 'xAI'

    def test_identify_openrouter_prefix(self):
        """Test OpenRouter explicit prefix."""
        manager = AIAPIManager()

        assert manager._identify_provider('openrouter/gpt-4', '') == 'OpenRouter'
        assert manager._identify_provider('openrouter/claude-3', '') == 'OpenRouter'

    def test_identify_together_prefix(self):
        """Test Together AI prefix."""
        manager = AIAPIManager()

        assert manager._identify_provider('together/llama-3', '') == 'Together'
        assert manager._identify_provider('meta-llama/Meta-Llama-3', '') == 'Together'

    def test_identify_siliconflow(self):
        """Test SiliconFlow provider detection."""
        manager = AIAPIManager()

        assert manager._identify_provider('Qwen/Qwen2-7B', '') == 'SiliconFlow'
        assert manager._identify_provider('deepseek-ai/DeepSeek-V2', '') == 'SiliconFlow'

    def test_identify_cerebras(self):
        """Test Cerebras provider detection."""
        manager = AIAPIManager()

        assert manager._identify_provider('llama3.1-8b', '') == 'Cerebras'
        assert manager._identify_provider('llama3.2-70b', '') == 'Cerebras'

    def test_identify_sambanova(self):
        """Test SambaNova provider detection."""
        manager = AIAPIManager()

        assert manager._identify_provider('Meta-Llama-3.1-8B', '') == 'SambaNova'

    def test_identify_perplexity(self):
        """Test Perplexity provider detection."""
        manager = AIAPIManager()

        assert manager._identify_provider('sonar-small-online', '') == 'Perplexity'
        assert manager._identify_provider('llama-3.1-sonar-large', '') == 'Perplexity'

    def test_fallback_to_google(self):
        """Test that unknown models fallback to Google."""
        manager = AIAPIManager()

        # Completely unknown model should default to google
        assert manager._identify_provider('some-random-model', '') == 'Google'


class TestConfiguration:
    """Tests for API configuration."""

    def test_configure_with_api_configs(self):
        """Test configuring manager with API configs."""
        manager = AIAPIManager()

        configs = [
            {'model_name': 'gpt-4', 'api_key': 'test-key', 'provider': 'openai'}
        ]
        callback = MagicMock()

        manager.configure(configs, callback)

        assert manager.api_configs == configs
        assert manager.notification_callback == callback

    def test_configure_empty(self):
        """Test configuring with empty list."""
        manager = AIAPIManager()
        manager.configure([])

        assert manager.api_configs == []


class TestTranslation:
    """Tests for translation methods."""

    def test_translate_no_config_raises(self):
        """Test that translate raises when not configured."""
        manager = AIAPIManager()

        with pytest.raises(Exception) as exc:
            manager.translate("Hello")

        assert "API not configured" in str(exc.value)

    def test_translate_no_valid_key_raises(self):
        """Test that translate raises when no valid key."""
        manager = AIAPIManager()
        manager.configure([{'model_name': '', 'api_key': ''}])

        with pytest.raises(Exception) as exc:
            manager.translate("Hello")

        assert "No valid API key" in str(exc.value)

    @patch('urllib.request.urlopen')
    def test_translate_google_success(self, mock_urlopen, mock_urllib_response):
        """Test successful Google translation (Gemini REST API)."""
        manager = AIAPIManager()
        manager.configure([
            {'model_name': 'gemini-2.0-flash', 'api_key': 'test-key', 'provider': 'Auto'}
        ])

        # Google REST response shape: candidates[0].content.parts[0].text
        mock_urlopen.return_value = mock_urllib_response({
            "candidates": [{"content": {"parts": [{"text": "Translated text"}]}}]
        })

        result = manager.translate("Hello world")

        assert result == "Translated text"

    @patch('urllib.request.urlopen')
    def test_translate_openai_style(self, mock_urlopen, mock_openai_response):
        """Test OpenAI-style API translation."""
        manager = AIAPIManager()
        manager.configure([
            {'model_name': 'gpt-4', 'api_key': 'sk-test', 'provider': 'Auto'}
        ])

        mock_urlopen.return_value = mock_openai_response

        result = manager.translate("Hello world")

        assert result == "Translated text here"


class TestRateLimitHandling:
    """Tests for rate limit and retry logic."""

    @patch('urllib.request.urlopen')
    @patch('time.sleep')
    def test_rate_limit_retry(self, mock_sleep, mock_urlopen, mock_openai_response):
        """Test exponential backoff on rate limit."""
        manager = AIAPIManager()
        manager.configure([
            {'model_name': 'gpt-4', 'api_key': 'sk-test', 'provider': 'Auto'}
        ])

        # First call: rate limit, second call: success
        rate_limit_error = MagicMock()
        rate_limit_error.code = 429
        rate_limit_error.__enter__ = MagicMock(side_effect=Exception("rate limit"))

        import urllib.error
        mock_urlopen.side_effect = [
            urllib.error.HTTPError(None, 429, "Rate Limited", {}, None),
            mock_openai_response
        ]

        result = manager.translate("Hello")

        assert result == "Translated text here"
        # Should have slept once (exponential backoff)
        mock_sleep.assert_called()


class TestMultimodal:
    """Tests for multimodal translation."""

    def test_translate_multimodal_no_config(self):
        """Test multimodal raises when not configured."""
        manager = AIAPIManager()

        with pytest.raises(Exception) as exc:
            manager.translate_multimodal("Test prompt")

        assert "API not configured" in str(exc.value)

    @patch('urllib.request.urlopen')
    def test_translate_multimodal_with_images(self, mock_urlopen, mock_urllib_response):
        """Test multimodal translation with images (Gemini REST API)."""
        import tempfile
        import os
        import base64

        manager = AIAPIManager()
        manager.configure([
            {'model_name': 'gemini-2.0-flash', 'api_key': 'test-key', 'provider': 'Auto'}
        ])

        # Create a valid 2x2 PNG so image base64 encoding succeeds
        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAE0lEQVR4nGP8//8/AwMDEwMYAAAkBgMBXaJOiAAAAABJRU5ErkJggg=="
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            f.write(base64.b64decode(png_b64))
            temp_path = f.name

        try:
            mock_urlopen.return_value = mock_urllib_response({
                "candidates": [{"content": {"parts": [{"text": "Image analysis result"}]}}]
            })

            result = manager.translate_multimodal(
                "Analyze this image",
                image_paths=[temp_path],
                file_contents={}
            )

            assert result == "Image analysis result"
        finally:
            os.unlink(temp_path)

    @patch('urllib.request.urlopen')
    def test_translate_multimodal_with_file_contents(self, mock_urlopen, mock_urllib_response):
        """Test multimodal translation with file contents (Gemini REST API)."""
        manager = AIAPIManager()
        manager.configure([
            {'model_name': 'gemini-2.0-flash', 'api_key': 'test-key', 'provider': 'Auto'}
        ])

        mock_urlopen.return_value = mock_urllib_response({
            "candidates": [{"content": {"parts": [{"text": "File translation result"}]}}]
        })

        result = manager.translate_multimodal(
            "Translate this file",
            image_paths=[],
            file_contents={'test.txt': 'Hello world'}
        )

        assert result == "File translation result"


class TestDisplayName:
    """Tests for provider display names."""

    def test_get_display_name(self):
        """Test getting display names for providers."""
        manager = AIAPIManager()

        assert manager.get_display_name('google') == 'Google (Gemini)'
        assert manager.get_display_name('openai') == 'OpenAI'
        assert manager.get_display_name('anthropic') == 'Anthropic (Claude)'
        assert manager.get_display_name('groq') == 'Groq'
        assert manager.get_display_name('unknown') == 'Unknown'


class TestConnectionTest:
    """Tests for connection testing."""

    @patch('urllib.request.urlopen')
    def test_connection_success(self, mock_urlopen, mock_urllib_response):
        """Test successful connection test (Gemini REST API)."""
        manager = AIAPIManager()

        mock_urlopen.return_value = mock_urllib_response({
            "candidates": [{"content": {"parts": [{"text": "OK"}]}}]
        })

        result = manager.test_connection('gemini-2.0-flash', 'test-key')

        assert result == True

    @patch('urllib.request.urlopen')
    def test_connection_failure(self, mock_urlopen):
        """Test failed connection test."""
        manager = AIAPIManager()

        # A non-HTTP/URL error propagates immediately (no retry/backoff)
        mock_urlopen.side_effect = Exception("Invalid API key")

        with pytest.raises(Exception):
            manager.test_connection('gemini-2.0-flash', 'invalid-key')
