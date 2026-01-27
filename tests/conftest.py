"""
Shared pytest fixtures for CrossTrans tests.
"""
import os
import sys
import json
import tempfile
import pytest
from unittest.mock import MagicMock, patch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_config_dir():
    """Create temporary config directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_config():
    """Mock Config object with test values."""
    config = MagicMock()
    config.get_api_keys.return_value = [
        {
            'model_name': 'gemini-2.0-flash',
            'api_key': 'test-api-key-123',
            'provider': 'Auto',
            'vision_capable': True,
            'file_capable': True
        }
    ]
    config.get.return_value = None
    return config


@pytest.fixture
def sample_txt_file():
    """Create sample .txt file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write("Hello World\nThis is a test file.\nLine 3 here.")
        temp_path = f.name
    yield temp_path
    try:
        os.unlink(temp_path)
    except OSError:
        pass


@pytest.fixture
def sample_srt_file():
    """Create sample .srt subtitle file for testing."""
    content = """1
00:00:01,000 --> 00:00:04,000
Hello, this is subtitle one.

2
00:00:05,000 --> 00:00:08,000
And this is subtitle two.

3
00:00:09,000 --> 00:00:12,000
Final subtitle here.
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as f:
        f.write(content)
        temp_path = f.name
    yield temp_path
    try:
        os.unlink(temp_path)
    except OSError:
        pass


@pytest.fixture
def sample_config_json():
    """Sample config.json content."""
    return {
        "api_keys": [
            {
                "model_name": "gemini-2.0-flash",
                "api_key": "test-key-123",
                "provider": "Auto"
            }
        ],
        "hotkeys": {
            "Vietnamese": "win+alt+v",
            "English": "win+alt+e"
        },
        "autostart": False,
        "theme": "darkly"
    }


@pytest.fixture
def mock_urllib_response():
    """Mock urllib response for API tests."""
    def _create_response(json_data, status_code=200):
        response = MagicMock()
        response.read.return_value = json.dumps(json_data).encode('utf-8')
        response.status = status_code
        response.__enter__ = MagicMock(return_value=response)
        response.__exit__ = MagicMock(return_value=False)
        return response
    return _create_response


@pytest.fixture
def mock_openai_response(mock_urllib_response):
    """Mock OpenAI-style API response."""
    return mock_urllib_response({
        "choices": [
            {
                "message": {
                    "content": "Translated text here"
                }
            }
        ]
    })


@pytest.fixture
def mock_anthropic_response(mock_urllib_response):
    """Mock Anthropic API response."""
    return mock_urllib_response({
        "content": [
            {
                "text": "Translated text here"
            }
        ]
    })
