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

# Off the user's session before anything else is imported: the Tk thread moves to
# a private desktop, which only works while it owns no window yet, and the
# network, clipboard, keystrokes and the rest are refused (K12).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quiet_session  # noqa: E402

quiet_session.install()


@pytest.fixture(autouse=True)
def _stay_in_the_test_session(request):
    """Fail a test that reached outside the session - also when its code caught
    the SessionGuardError and carried on (quiet_session)."""
    quiet_session.CURRENT_TEST = request.node.nodeid
    first = len(quiet_session.BLOCKED)
    yield
    quiet_session.CURRENT_TEST = None
    reached = [what for _test, what in quiet_session.BLOCKED[first:]]
    if reached:
        pytest.fail("reached outside the test session:\n  " + "\n  ".join(reached),
                    pytrace=False)


def pytest_terminal_summary(terminalreporter):
    """Where this run's windows went, and anything refused outside a test."""
    terminalreporter.write_line(f"quiet session: {quiet_session.describe()}")
    for test, what in quiet_session.BLOCKED:
        if test is None:
            terminalreporter.write_line(f"quiet session: refused outside any test: {what}")


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


@pytest.fixture(scope="session")
def tk_root():
    """A hidden Tk root for widget tests, skipped when there is no display.

    Session-scoped because creating and tearing down interpreters repeatedly is
    slow and leaks Tcl state; individual tests should build their widgets in
    their own frame and destroy it.

    Its windows - and every Toplevel a test maps - are on this run's private
    desktop: real windows, on no screen (quiet_session, K12). Without that
    desktop, creating Tk skips the test rather than draw on the user's screen.
    """
    tkinter = pytest.importorskip("tkinter")
    try:
        root = tkinter.Tk()
    except Exception as e:  # TclError, or no display at all
        pytest.skip(f"no usable Tk display: {e}")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass


@pytest.fixture
def real_clipboard(tk_root):
    """The Windows clipboard itself, for the one test whose point is reaching it.

    Every other test gets Tk's in-memory clipboard (quiet_session). This one runs
    on CI, where no one's clipboard is there to lose, or when asked for with
    CROSSTRANS_TESTS_REAL_CLIPBOARD=1 - and then the user's content is saved first
    and put back after. Not by default: saving and restoring cannot put every
    format back (files copied in Explorer, some images), and a clipboard history
    records the test's text anyway (K12).
    """
    if not quiet_session.real_clipboard_allowed():
        pytest.skip(f"writes the user's clipboard - runs on CI, or locally with "
                    f"{quiet_session.REAL_CLIPBOARD_ENV}=1")
    from src.core.clipboard import ClipboardManager
    with quiet_session.real_clipboard(tk_root):
        saved = ClipboardManager.save_clipboard()
        if saved is None:
            pytest.skip("could not read the clipboard to save it, so it is left alone")
        try:
            yield
        finally:
            if saved:
                ClipboardManager.restore_clipboard(saved)
            else:                                   # it was empty: leave it empty
                import win32clipboard
                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                finally:
                    win32clipboard.CloseClipboard()
