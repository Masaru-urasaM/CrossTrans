"""
Custom widgets and helper functions for Settings window.
"""
import ctypes

import tkinter as tk

try:
    import ttkbootstrap as ttk
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.core.remote_config import get_config


def set_dark_title_bar(window):
    """Set dark title bar for Windows 10/11 windows."""
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()

        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_CAPTION_COLOR = 35
        dwmapi = ctypes.windll.dwmapi

        value = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                                     ctypes.byref(value), ctypes.sizeof(value))
        caption_color = ctypes.c_int(0x002b2b2b)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR,
                                     ctypes.byref(caption_color), ctypes.sizeof(caption_color))
    except Exception:
        pass


def get_all_models_list(provider: str = "Auto") -> list:
    """Get list of models for dropdown, filtered by provider and sorted alphabetically.

    Args:
        provider: Provider name or "Auto" for all models

    Returns:
        List of model names starting with "Auto", then sorted A-Z
    """
    models = []
    model_provider_map = get_config().model_provider_map

    if provider == "Auto":
        # Add all models from all providers
        for prov, model_list in model_provider_map.items():
            models.extend(model_list)
    else:
        # Add models for specific provider only (keys are Title Case)
        if provider in model_provider_map:
            models.extend(model_provider_map[provider])

    # Sort alphabetically (case-insensitive)
    models.sort(key=lambda x: x.lower())

    # "Auto" always first
    return ["Auto"] + models


class AutocompleteCombobox(ttk.Combobox):
    """Combobox with autocomplete filtering.

    As the user types, the dropdown list is filtered to show only
    matching options. Supports both selection and custom input.
    """

    def __init__(self, master, **kwargs):
        self._all_values = list(kwargs.pop('values', []))
        super().__init__(master, **kwargs)
        self['values'] = self._all_values

        # Bind key release for filtering
        self.bind('<KeyRelease>', self._on_key_release)
        self.bind('<FocusIn>', self._on_focus_in)

    def set_values(self, values):
        """Update the full list of values.

        Args:
            values: List of all possible values
        """
        self._all_values = list(values)
        self['values'] = self._all_values

    def _on_key_release(self, event):
        """Filter dropdown based on typed text."""
        # Ignore navigation and special keys
        if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Return', 'Tab',
                            'Escape', 'Shift_L', 'Shift_R', 'Control_L',
                            'Control_R', 'Alt_L', 'Alt_R', 'BackSpace'):
            if event.keysym == 'BackSpace':
                # Still filter on backspace
                pass
            else:
                return

        typed = self.get().strip().lower()
        if not typed or typed == 'auto':
            # Show all values when empty or "Auto"
            self['values'] = self._all_values
        else:
            # Filter values that contain the typed text
            filtered = [v for v in self._all_values if typed in v.lower()]
            self['values'] = filtered if filtered else self._all_values

    def _on_focus_in(self, event):
        """Show full list on focus."""
        self['values'] = self._all_values
