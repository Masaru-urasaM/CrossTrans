"""
Shared UI utility functions for CrossTrans.

This module contains utility functions used across multiple UI components
to maintain consistency and reduce code duplication.
"""
import re
import logging
from typing import List


def set_dark_title_bar(window) -> None:
    """Set dark title bar for Windows 10/11 windows.

    Uses Windows DWM API to enable dark mode for the title bar.
    This makes the title bar match the dark theme of the app.

    Args:
        window: Tkinter window (Tk or Toplevel)
    """
    try:
        import ctypes

        # Get window handle
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()

        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Windows 10 build 18985+, Windows 11)
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        # DWMWA_CAPTION_COLOR = 35 (Windows 11 only - custom caption color)
        DWMWA_CAPTION_COLOR = 35

        dwmapi = ctypes.windll.dwmapi

        # Enable dark mode for title bar
        value = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value)
        )

        # Try to set custom caption color (Windows 11)
        # Color format: 0x00BBGGRR (BGR, not RGB)
        # Using dark blue-gray: #1a1a2e -> 0x002e1a1a
        caption_color = ctypes.c_int(0x002b2b2b)  # Match app background
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_CAPTION_COLOR,
            ctypes.byref(caption_color),
            ctypes.sizeof(caption_color)
        )

    except Exception as e:
        logging.debug(f"Could not set dark title bar: {e}")


def filter_dictionary_words(words: List[str]) -> List[str]:
    """Filter out punctuation, symbols, numbers, and special characters from words list.

    Args:
        words: List of words to filter

    Returns:
        Filtered list containing only valid words (at least one Unicode letter)
    """
    if not words:
        return []

    filtered = []
    for word in words:
        if not word or not isinstance(word, str):
            continue
        # Strip leading/trailing punctuation and whitespace
        cleaned = word.strip()
        # Remove leading/trailing non-word characters (keep internal ones like don't, e-mail)
        cleaned = re.sub(r'^[^\w]+|[^\w]+$', '', cleaned, flags=re.UNICODE)
        # Require at least one Unicode letter (not just digits/underscore/symbols)
        # [^\W\d_] matches any Unicode letter: Latin, CJK, Cyrillic, Arabic, Thai, Korean, etc.
        if cleaned and re.search(r'[^\W\d_]', cleaned, re.UNICODE):
            filtered.append(cleaned)

    return filtered
