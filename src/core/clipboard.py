"""
Clipboard management for CrossTrans.
Handles saving, restoring, and manipulating clipboard content.
"""
import logging
import time
from typing import Optional, Dict, Any

import pyperclip

# Windows-specific imports
try:
    import win32clipboard
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


class ClipboardManager:
    """Manages clipboard operations with proper preservation of content."""

    @staticmethod
    def save_clipboard() -> Optional[Dict[int, Any]]:
        """Save current clipboard content including files/images."""
        if not HAS_WIN32:
            try:
                return {'text': pyperclip.paste()}
            except Exception:
                return None

        try:
            # Retry opening clipboard (it might be locked by another app)
            for _ in range(5):
                try:
                    win32clipboard.OpenClipboard()
                    break
                except Exception:
                    time.sleep(0.01)
            else:
                # Failed after retries
                return None

            formats = []
            fmt = win32clipboard.EnumClipboardFormats(0)
            while fmt:
                formats.append(fmt)
                fmt = win32clipboard.EnumClipboardFormats(fmt)

            saved = {}
            for fmt in formats:
                try:
                    saved[fmt] = win32clipboard.GetClipboardData(fmt)
                except Exception:
                    pass  # Skip unsupported formats
            return saved
        except Exception as e:
            logging.warning(f"Failed to save clipboard: {e}")
            return None
        finally:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass  # Clipboard may not be open

    @staticmethod
    def restore_clipboard(saved: Optional[Dict[int, Any]]):
        """Restore saved clipboard content."""
        if not saved:
            return

        if not HAS_WIN32:
            if 'text' in saved:
                try:
                    pyperclip.copy(saved['text'])
                except Exception:
                    pass  # Clipboard unavailable
            return

        try:
            for _ in range(5):
                try:
                    win32clipboard.OpenClipboard()
                    break
                except Exception:
                    time.sleep(0.01)
            else:
                return

            win32clipboard.EmptyClipboard()
            for fmt, data in saved.items():
                try:
                    win32clipboard.SetClipboardData(fmt, data)
                except Exception:
                    pass  # Skip unsupported formats
        except Exception as e:
            logging.warning(f"Failed to restore clipboard: {e}")
        finally:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass  # Clipboard may not be open

    @staticmethod
    def set_text(text: str):
        """Set clipboard to text."""
        if HAS_WIN32:
            try:
                for _ in range(5):
                    try:
                        win32clipboard.OpenClipboard()
                        break
                    except Exception:
                        time.sleep(0.01)
                else:
                    # Fallback if open fails
                    pyperclip.copy(text)
                    return

                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32con.CF_UNICODETEXT)
            except Exception:
                pyperclip.copy(text)  # Fallback to pyperclip
            finally:
                try:
                    win32clipboard.CloseClipboard()
                except Exception:
                    pass  # Clipboard may not be open
        else:
            pyperclip.copy(text)

    @staticmethod
    def get_text() -> str:
        """Get text from clipboard."""
        try:
            return pyperclip.paste()
        except Exception:
            return ""  # Return empty on clipboard error
