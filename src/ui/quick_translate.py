"""
Quick Translate Manager for CrossTrans.
Handles translation result popups and loading indicators.
"""
import ctypes
import logging
import math
import re
import time
import tkinter as tk
from tkinter import BOTH, X, Y, LEFT, RIGHT, TOP, BOTTOM
from tkinter import font
from typing import Tuple, Optional, Callable

try:
    import ttkbootstrap as ttk
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.constants import (POPUP_COLLAPSED_ORIGINAL_ROWS, POPUP_FRONT_MS,
                           POPUP_GRIP_PREVIEW_MS, POPUP_LAYOUT_WATCHDOG_MS,
                           POPUP_MIN_BOX_ROWS, POPUP_REVEAL_DELAY_MS, POPUP_SCREEN_MARGIN,
                           POPUP_TOOLTIP_DELAY_MS, POPUP_USER_MIN_ROWS)
from src.core import lang_id
from src.core.furigana import RubySegment
from src.core.nlp_manager import nlp_manager
from src.core.source_marker import (ROW_CHANGE, language_label, other_language,
                                    source_row)
from src.ui import popup_layout
from src.ui.dictionary_render import overhead_px, split_dictionary_text
from src.ui.ruby_text import NO_AUTOSTYLE, RubyText, insert_output
from src.ui.linked_reading import LinkedReadingController
from src.core.translation_alignment import validate_metadata, reading_result

# The dictionary result window's padding, which calculate_size() still sizes it with.
# The quick-translate popup measures itself instead (Decision 34).
HORIZONTAL_PADDING = 50  # frame(30) + scrollbar(20)

# The quick-translate popup's frame padding, each side.
POPUP_FRAME_PADDING = 15

# The "Translated with ..." credit at the top of the popup. A footnote, so it is
# deliberately small and dim: it must be readable when looked for and invisible
# when not. It shares the header row with the close button and is cut with an
# ellipsis rather than ever crowding that button out.
ATTRIBUTION_FONT = ('Segoe UI', 8, 'italic')
ATTRIBUTION_FG = '#8a8a8a'
HEADER_CREDIT_MIN_PX = 120    # what the credit keeps, at least, before it is cut

# Glyphs by code point: the tooling mangles both the escapes and the characters.
CLOSE_GLYPH = chr(0x2715)     # the close button - top right, in every popup state
GEAR_GLYPH = chr(0x2699)      # Replace's settings menu
GRIP_GLYPH = chr(0x25E2)      # the resize grip - bottom right
CHECK_GLYPH = chr(0x2713)
CROSS_GLYPH = chr(0x2717)

CLOSE_FG = '#9a9a9a'
CLOSE_ACTIVE_BG = '#c42b1c'   # the Windows close-button red, on hover

# The action bar's secondary actions are icons with a tooltip (Decision 34, TODO.md
# Q1): Windows 11's icon font, else Windows 10's; with neither, the words come back.
ICON_FONTS = ('Segoe Fluent Icons', 'Segoe MDL2 Assets')
ICON_SIZE = 12
ICON_GLYPHS = {
    'retranslate': chr(0xE72C),   # Refresh
    'dictionary': chr(0xE82D),    # Dictionary
    'open': chr(0xE8A7),          # OpenInNewWindow
    'prompt': chr(0xE70F),        # Edit
    'linked': chr(0xE71B),        # Link
}
ICON_BG = '#3a3f44'               # neutral; an icon takes its action's colour on hover
TOOLTIP_FONT = ('Segoe UI', 9)
TOOLTIP_BG = '#111111'

# The frame a grip drag moves instead of the popup: laying the popup out costs up to
# ~190 ms a step on a long text, moving this ~1.5 ms (measured 2026-10-19). Its inside
# is GRIP_OUTLINE_KEY, made transparent, so the popup shows through.
GRIP_OUTLINE_COLOR = '#3498db'
GRIP_OUTLINE_PX = 2
GRIP_OUTLINE_KEY = '#000001'

# The popup resizes from every edge and corner, like a window (Decision 35): the outer
# RESIZE_EDGE_PX of the main frame's padding (POPUP_FRAME_PADDING), so no text and no
# button is in the way; along a side, RESIZE_CORNER_PX from a corner is the corner. The
# grip (GRIP_GLYPH) stays as the visible hint; its double-click resets.
RESIZE_EDGE_PX = 6
RESIZE_CORNER_PX = 14
RESIZE_CURSORS = {'n': 'size_ns', 's': 'size_ns', 'e': 'size_we', 'w': 'size_we',
                  'nw': 'size_nw_se', 'se': 'size_nw_se', 'ne': 'size_ne_sw',
                  'sw': 'size_ne_sw'}

# The small header that names the original block, and its "Show all" toggle.
ORIGINAL_HEADER_FONT = ('Segoe UI', 8)
ORIGINAL_TOGGLE_FG = '#80b8ff'

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000


def is_error_text(translated: str) -> str:
    """Whether a result string is a failure notice rather than a translation.

    Module level because `app.py` needs the same answer: the popup decides which
    buttons to draw with it, and the main window must not paste a failure notice
    into its output box when the user opens it from a failed popup.
    """
    return bool(translated) and (translated.startswith("Error:")
                                 or translated.startswith("No text"))


def icon_font_family(families) -> Optional[str]:
    """The first of ICON_FONTS this system has, or None (the words come back)."""
    available = set(families)
    return next((family for family in ICON_FONTS if family in available), None)


def set_noactivate(window, on: bool = True) -> None:
    """Give `window` WS_EX_NOACTIVATE, or take it away. With it, clicking the window
    never takes the focus from the user's app - which Replace relies on."""
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_NOACTIVATE) if on else (style & ~WS_EX_NOACTIVATE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception:
        pass  # Non-critical: the window still works, it may just take the focus


def _pad_pair(widget, value) -> Tuple[int, int]:
    """A pack padding as (before, after): 4 -> (4, 4), (0, 4) -> (0, 4)."""
    if isinstance(value, (tuple, list)):
        parts = [int(float(part)) for part in value]
    elif isinstance(value, (int, float)):
        parts = [int(value)]
    else:
        parts = [int(float(part)) for part in widget.tk.splitlist(value)]
    return (parts[0], parts[-1]) if parts else (0, 0)


def packed_row_width(frame) -> int:
    """The width a row of side-by-side packed widgets asks for, read off the widgets.

    Each child's requested width, its internal padding and its pack padding on both
    sides - the sum the packer makes. Known as soon as the widgets are configured,
    before the popup is shown (Tk lays out only the children of a mapped window, but
    requested sizes are there from the start), so the popup can be made wide enough
    for its rows. A constant did this before - MIN_WIDTH 670 - and drifted as buttons
    were added; the close button, packed last, was the one squeezed out (TODO.md S1).
    """
    total = 0
    for child in frame.pack_slaves():
        info = child.pack_info()
        total += (child.winfo_reqwidth()
                  + sum(_pad_pair(frame, info.get('ipadx', 0)))
                  + sum(_pad_pair(frame, info.get('padx', 0))))
    return total


class Tooltip:
    """The name of an icon button, shown over it after a pause.

    A Toplevel of its own, `WS_EX_NOACTIVATE` once mapped, so it can never take the
    keyboard from the user's app. Hidden on leave and on click.
    """

    def __init__(self, widget, text: str, delay_ms: int = POPUP_TOOLTIP_DELAY_MS):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self.window: Optional[tk.Toplevel] = None
        self._pending = None
        widget.bind('<Enter>', self._schedule, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<ButtonPress>', self.hide, add='+')

    def _schedule(self, _event=None):
        self._cancel()
        try:
            self._pending = self.widget.after(self.delay_ms, self.show)
        except tk.TclError:
            self._pending = None

    def _cancel(self):
        if self._pending is not None:
            try:
                self.widget.after_cancel(self._pending)
            except tk.TclError:
                pass
            self._pending = None

    def show(self):
        self._pending = None
        try:
            if self.window is not None or not self.widget.winfo_exists():
                return
            window = tk.Toplevel(self.widget)
            window.overrideredirect(True)
            window.attributes('-topmost', True)
            label = tk.Label(window, text=self.text, font=TOOLTIP_FONT, bg=TOOLTIP_BG,
                             fg='#ffffff', padx=6, pady=2, autostyle=False)
            label.pack()
            x = self.widget.winfo_rootx()
            y = self.widget.winfo_rooty() - label.winfo_reqheight() - 4
            window.geometry(f"+{x}+{y}")
            # Tk creates the window that carries the style only when it maps it: set
            # before, the bit lands on the inner window and is lost (measured).
            window.bind('<Map>', lambda _event: set_noactivate(window), add='+')
            self.window = window
        except tk.TclError:
            self.window = None

    def hide(self, _event=None):
        self._cancel()
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None


# The "Kanji-only text - read it as: [Japanese] [Chinese]" row (J6), shown when a
# translation of kanji-only text came back without a source language.
SOURCE_CHOOSER_FONT = ('Segoe UI', 9)


def fill_source_row(row, mode: str, verdict: Optional[str],
                    on_choose: Callable[[str], None]) -> None:
    """The label and buttons of a Japanese / Chinese row - the popup's and the
    main window's (`source_marker.source_row` decides which):

    - ROW_ASK: "Kanji-only text - read it as: [Japanese] [Chinese]" (J6).
    - ROW_CHANGE: "Kanji-only text - read as Chinese. [Read as Japanese]" (K4):
      what a model - or the user, earlier - settled, and the way to the other.

    `on_choose` gets lang_id.JAPANESE or lang_id.CHINESE_SIMPLIFIED.
    """
    if mode == ROW_CHANGE:
        text = f"Kanji-only text - read as {language_label(verdict)}."
        other = other_language(verdict)
        choices = ((other, f"Read as {language_label(other)}"),)
    else:
        text = "Kanji-only text - read it as:"
        choices = ((lang_id.JAPANESE, "Japanese"), (lang_id.CHINESE_SIMPLIFIED, "Chinese"))
    ttk.Label(row, text=text, font=SOURCE_CHOOSER_FONT, foreground='#bbbbbb').pack(side=LEFT)
    for language, label in choices:
        tk.Button(row, text=label, command=lambda chosen=language: on_choose(chosen),
                  autostyle=False, bg='#495057', fg='#ffffff',
                  activebackground='#5a6268', activeforeground='#ffffff',
                  font=SOURCE_CHOOSER_FONT, relief='flat', padx=10, pady=2,
                  cursor='hand2').pack(side=LEFT, padx=(6, 0))

# Dictionary result window font. Monospace is load-bearing: _align_dictionary_text
# pads the labels with spaces so every value starts at the same column.
DICT_RESULT_FONT = ('Consolas', 10)

# Everything in the dictionary result window that is not the text box: the main
# frame's 15px padding top and bottom, plus the button row (29px) and the 12px
# gap above it. Measured, and much smaller than the popup's 100px because this
# window has no header, no furigana block and no second button row.
DICT_RESULT_CHROME_PX = 71

# Dictionary button colors (dark red) - consistent with dictionary_mode.py
DICT_BUTTON_COLOR = "#822312"  # Dark red (main color)
DICT_BUTTON_ACTIVE = '#9A3322'  # Lighter red (hover/active)

# 20 professional highlight colors for dictionary word entries
HIGHLIGHT_COLORS = [
    "#F4A261", "#2EC4B6", "#E76F51", "#90BE6D", "#9D4EDD",
    "#F9C74F", "#4CC9F0", "#FF6B6B", "#43AA8B", "#FFB703",
    "#7B68EE", "#FF9F1C", "#00B4D8", "#E9C46A", "#80ED99",
    "#F72585", "#48CAE4", "#FFAFCC", "#A8DADC", "#CDB4DB",
]


def _align_dictionary_text(result: str) -> str:
    """Align dictionary result text so labels and values form clean columns.

    Transforms:
        1. **Translation**: value
        2. **Source Language**: value

    Into tab-aligned format where all values start at the same column:
        1. **Translation**:      value
        2. **Source Language**:   value

    Only aligns numbered field lines (N. **Label**: value).
    Other lines (headers, examples, separators) pass through unchanged.
    """
    lines = result.split('\n')
    output = []

    # Process in chunks per word entry (between ## headers)
    chunk = []  # Lines in current entry

    def _align_chunk(chunk_lines):
        """Align numbered field lines within a single word entry."""
        if not chunk_lines:
            return []

        # Find max label width among numbered lines in this chunk
        max_label_len = 0
        for line in chunk_lines:
            m = re.match(r'^(\d+\.\s+\*\*.+?\*\*:)\s*', line)
            if m:
                max_label_len = max(max_label_len, len(m.group(1)))

        if max_label_len == 0:
            return chunk_lines  # No numbered fields found

        # Pad to nearest multiple of 4 + 2 for clean spacing
        pad_to = max_label_len + 2

        aligned = []
        for line in chunk_lines:
            m = re.match(r'^(\d+\.\s+\*\*.+?\*\*:)\s*(.*)', line)
            if m:
                label_part = m.group(1)
                value_part = m.group(2)
                # Pad label to align values
                aligned.append(label_part.ljust(pad_to) + value_part)
            else:
                aligned.append(line)
        return aligned

    for line in lines:
        if line.strip().startswith('## '):
            # Flush previous chunk
            output.extend(_align_chunk(chunk))
            chunk = [line]
        elif line.strip() == '---':
            # Flush chunk before separator
            output.extend(_align_chunk(chunk))
            chunk = []
            output.append(line)
        else:
            chunk.append(line)

    # Flush last chunk
    output.extend(_align_chunk(chunk))

    return '\n'.join(output)


def get_monitor_work_area(x: int, y: int) -> Tuple[int, int, int, int]:
    """Get the work area (excluding taskbar) of the monitor containing point (x, y).

    Uses Windows API MonitorFromPoint and GetMonitorInfo.

    Args:
        x: X coordinate (virtual screen)
        y: Y coordinate (virtual screen)

    Returns:
        Tuple of (left, top, right, bottom) representing the work area
    """
    try:
        # Define POINT structure
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        # Define RECT structure
        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long)
            ]

        # Define MONITORINFO structure
        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", ctypes.c_ulong)
            ]

        # Get monitor handle from point
        # MONITOR_DEFAULTTONEAREST = 2 (return nearest monitor if point is not on any)
        user32 = ctypes.windll.user32
        pt = POINT(x, y)
        monitor = user32.MonitorFromPoint(pt, 2)

        if monitor:
            # Get monitor info
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
                # Return work area (excludes taskbar)
                return (
                    mi.rcWork.left,
                    mi.rcWork.top,
                    mi.rcWork.right,
                    mi.rcWork.bottom
                )
    except Exception:
        pass

    # Fallback: return None to indicate failure
    return None


class QuickTranslateManager:
    """Manages popup display for translation results."""

    def __init__(self, root: tk.Tk, config=None):
        """Initialize quick translate manager.

        Args:
            root: The root Tk window for screen info and scheduling
            config: Config object for reading settings (e.g., replace mode)
        """
        self.root = root
        self.config = config
        self.popup: Optional[tk.Toplevel] = None
        self.popup_text: Optional[RubyText] = None  # Read with get_plain(), not get()
        self.popup_furigana: Optional[RubyText] = None  # Read-only reading guide
        self.popup_attribution: Optional[ttk.Label] = None  # "Translated with ..." note
        self.popup_copy_btn: Optional[ttk.Button] = None
        self.popup_dict_btn: Optional[ttk.Button] = None
        self.popup_source_chooser: Optional[ttk.Frame] = None  # Japanese / Chinese row
        self.popup_linked_btn = None
        self._linked_status = None
        self._linked_setting_binding = None
        self._linked_tooltip = None
        self._linked_paused = False
        self._linked_controller = None

        # Mouse position captured when hotkey was pressed
        self._last_mouse_x = 0
        self._last_mouse_y = 0

        # Drag state
        self._drag_x = 0
        self._drag_y = 0

        # Grammar-fix result flag (hides translation-only buttons in the popup)
        self._is_grammar = False

        # Dictionary mode state
        self._dict_mode_active = False
        self._dict_frame = None  # WordButtonFrame instance
        self._current_original = ""  # Store original text for dictionary
        self._current_translation = ""
        self._current_target_lang = ""
        self._current_trial_info = None  # Store trial info for title bar
        self._current_furigana = None  # Store furigana for restoring after custom-prompt cancel
        self._current_source_lang = None  # Verdict for the original text (Decision 22)
        self._main_frame = None  # Reference to main frame for dictionary mode
        self._dict_popup_frame = None  # Reference to dict popup's WordButtonFrame for animation

        # Loading animation state
        self._loading_animation_running = False
        self._loading_animation_step = 0
        self._loading_label = None
        self._loading_target_lang = ""
        self._loading_base_text = ""  # Base phrase for loading animation (e.g. "Translating to X")
        self._loading_start_time = 0

        # Callbacks
        self._on_copy: Optional[Callable[[], None]] = None
        self._on_copy_and_replace: Optional[Callable[[], None]] = None
        self._on_re_translate: Optional[Callable[[], None]] = None
        self._on_custom_prompt_send: Optional[Callable[[str], None]] = None
        self._on_open_translator: Optional[Callable[[], None]] = None
        self._on_open_settings: Optional[Callable[[], None]] = None
        self._on_open_dictionary: Optional[Callable[[str, str, Optional[tk.Misc]], None]] = None
        self._on_choose_source: Optional[Callable[[str], None]] = None
        self.popup_replace_btn: Optional[tk.Button] = None
        self.popup_retranslate_btn: Optional[tk.Button] = None
        self.popup_custom_prompt_btn: Optional[tk.Button] = None
        self._replace_gear_btn: Optional[tk.Button] = None
        self._btn_frame: Optional[ttk.Frame] = None
        self._on_open_settings_hotkeys_tab: Optional[Callable[[], None]] = None

        # Layout (Decision 34): built at alpha 0, measured, then shown
        self._generation = 0               # bumped per popup; a stale step 2 sees it
        self._layout: Optional[dict] = None
        self.popup_close_btn: Optional[tk.Button] = None
        self.popup_open_btn: Optional[tk.Button] = None
        self.popup_original_toggle: Optional[tk.Label] = None
        self._original_header: Optional[ttk.Frame] = None
        self._original_holder: Optional[tk.Frame] = None
        self._original_scrollbar = None
        self._original_collapsed = True
        self._expanded_restore = None
        self._text_holder: Optional[tk.Frame] = None
        self._text_scrollbar = None
        self._trial_frame: Optional[ttk.Frame] = None
        self._attribution_text: Optional[str] = None
        self._tooltips = []
        self._icon_family_cache = None     # (family or None,), looked up once
        self._grip: Optional[tk.Label] = None
        self._grip_start: Optional[dict] = None
        self._grip_outline: Optional[tk.Toplevel] = None
        self._grip_preview_after = None
        self._user_size: Optional[Tuple[int, int]] = None
        self._user_rect: Optional[Tuple[int, int, int, int]] = None

    def configure_callbacks(self,
                            on_copy: Optional[Callable[[], None]] = None,
                            on_copy_and_replace: Optional[Callable[[], None]] = None,
                            on_open_translator: Optional[Callable[[], None]] = None,
                            on_open_settings: Optional[Callable[[], None]] = None,
                            on_open_dictionary: Optional[Callable[[str, str, Optional[tk.Misc]], None]] = None,
                            on_open_settings_hotkeys_tab: Optional[Callable[[], None]] = None,
                            on_re_translate: Optional[Callable[[], None]] = None,
                            on_custom_prompt_send: Optional[Callable[[str], None]] = None,
                            on_choose_source: Optional[Callable[[str], None]] = None,
                            on_dismiss: Optional[Callable[[], None]] = None):
        """Configure callback functions for quick translate actions.

        Args:
            on_copy: Called when user clicks Copy button
            on_copy_and_replace: Called when user clicks Replace button (copy + paste into source app)
            on_open_translator: Called when user clicks Open Translator
            on_open_settings: Called when user clicks Open Settings (error state)
            on_open_dictionary: Called by the Dictionary button with (text, target_lang,
                popup window) - the shared Dictionary-mode flow
                (DictionaryPopup.open_from_text), which opens beside the popup
            on_open_settings_hotkeys_tab: Called to open Settings directly to Hotkeys tab
            on_re_translate: Called when user clicks Re-translate button (force fresh API call)
            on_custom_prompt_send: Called with the edit-box content when user clicks Send in custom-prompt mode
            on_choose_source: Called with "Japanese" or "Chinese (Simplified)" when the user
                answers the kanji-only chooser - re-translate with that source (J6)
        """
        self._on_copy = on_copy
        self._on_copy_and_replace = on_copy_and_replace
        self._on_open_translator = on_open_translator
        self._on_open_settings = on_open_settings
        self._on_open_dictionary = on_open_dictionary
        self._on_open_settings_hotkeys_tab = on_open_settings_hotkeys_tab
        self._on_re_translate = on_re_translate
        self._on_custom_prompt_send = on_custom_prompt_send
        self._on_choose_source = on_choose_source
        self._on_dismiss = on_dismiss

    def _apply_noactivate(self):
        """Apply WS_EX_NOACTIVATE to popup window so it doesn't steal focus from source app."""
        if self.popup:
            set_noactivate(self.popup)

    def capture_mouse_position(self):
        """Capture current mouse position for popup positioning."""
        self._last_mouse_x = self.root.winfo_pointerx()
        self._last_mouse_y = self.root.winfo_pointery()

    def show_loading(self, target_lang: str, loading_text: str = None):
        """Show loading indicator popup with animation.

        Args:
            target_lang: The target language for translation
            loading_text: Optional base phrase to show instead of "Translating to <lang>"
                (e.g. "Fixing grammar" for the Fix Grammar action)
        """
        self.close()

        self._loading_target_lang = target_lang
        self._loading_base_text = loading_text if loading_text else f"Translating to {target_lang}"

        self.popup = tk.Toplevel(self.root)
        self.popup.overrideredirect(True)
        self._apply_noactivate()
        self.popup.configure(bg='#2b2b2b')
        self.popup.attributes('-topmost', True)

        frame = ttk.Frame(self.popup, padding=12)
        frame.pack(fill=BOTH, expand=True)

        # Create loading label with initial text
        self._loading_label = tk.Label(
            frame,
            text=f"⏳ {self._loading_base_text}   ",
            font=('Segoe UI', 10),
            fg='#ffffff',
            bg='#2b2b2b',
            padx=8,
            pady=4
        )
        self._loading_label.pack(side=LEFT)
        cancel_button = tk.Button(frame, text=CLOSE_GLYPH, command=self.dismiss,
                                  relief='flat', bd=0, padx=6, bg='#2b2b2b', fg=CLOSE_FG,
                                  activebackground=CLOSE_ACTIVE_BG, activeforeground='#ffffff',
                                  **NO_AUTOSTYLE)
        cancel_button.pack(side=RIGHT)
        self.popup.bind('<Escape>', lambda _event: self.dismiss())
        self.popup.protocol('WM_DELETE_WINDOW', self.dismiss)

        # Placed by the result's rules (Decision 34): beside the cursor and on the
        # screen, so the result then opens at the same corner.
        width = self._loading_label.winfo_reqwidth() + cancel_button.winfo_reqwidth() + 2 * 12
        height = self._loading_label.winfo_reqheight() + 2 * 12
        x, y, _ = popup_layout.place(self._anchor(), width, height, self._work_area(),
                                     min_height=height)
        self.popup.geometry(f"+{x}+{y}")

        # Start loading animation
        self._loading_animation_running = True
        self._loading_animation_step = 0
        self._loading_start_time = time.time()
        self._animate_loading()

    def _animate_loading(self):
        """Animate the loading popup with dots and pulse effect."""
        if not self._loading_animation_running:
            return

        if not self.popup or not self._loading_label:
            self._loading_animation_running = False
            return

        # The request runner owns the error message at the shared deadline.
        from src.constants import TRANSLATION_TIMEOUT_SECONDS
        LOADING_TIMEOUT_SECONDS = TRANSLATION_TIMEOUT_SECONDS
        if self._loading_start_time and time.time() - self._loading_start_time > LOADING_TIMEOUT_SECONDS:
            logging.warning(f"Loading animation timed out after {LOADING_TIMEOUT_SECONDS}s, auto-closing")
            self._loading_animation_running = False
            self.close()
            return

        try:
            # Dots animation pattern (fixed width to prevent shifting)
            base = self._loading_base_text or f"Translating to {self._loading_target_lang}"
            dots_patterns = [
                f"⏳ {base}   ",  # 0 dots + 3 spaces
                f"⏳ {base}.  ",  # 1 dot + 2 spaces
                f"⏳ {base}.. ",  # 2 dots + 1 space
                f"⏳ {base}...",  # 3 dots + 0 spaces
            ]
            text = dots_patterns[self._loading_animation_step % 4]
            self._loading_label.configure(text=text)

            # Pulse color effect (cycle through colors)
            pulse_colors = ['#ffffff', '#88aaff', '#aaccff', '#88aaff']
            color = pulse_colors[self._loading_animation_step % 4]
            self._loading_label.configure(fg=color)

            self._loading_animation_step += 1

            # Schedule next frame (400ms)
            if self.popup and self.popup.winfo_exists():
                self._loading_job = self.popup.after(400, self._animate_loading)

        except tk.TclError:
            # Widget destroyed
            self._loading_animation_running = False

    def calculate_size(self, text: str, base_font: Tuple[str, int] = ('Segoe UI', 11),
                       vertical_padding: int = 100) -> Tuple[int, int]:
        """Calculate optimal popup dimensions based on text content.

        Uses 20% safety margin on line height for cross-machine font rendering
        compatibility (handles DPI, ClearType, font substitution differences).

        Args:
            text: The text to display
            base_font: The font the text will actually be rendered in. The
                defaults are the popup's own, so existing callers are unchanged;
                a caller that renders in anything else MUST say so, or the row
                height is measured against the wrong font. The dictionary result
                window renders in DICT_RESULT_FONT, whose rows are 5px shorter
                than Segoe UI 11's - it used to reserve a line's worth of empty
                space per line because of exactly that.
            vertical_padding: Pixels this window spends on everything that is not
                the text box. The default describes the popup (header, furigana
                block, button row); the dictionary window passes its own.

        Returns:
            Tuple of (width, height) in pixels
        """
        MAX_WIDTH = 800
        MIN_WIDTH = 670  # Ensure all action buttons + close fit in one row (incl. Custom Prompt)
        MIN_HEIGHT = 130  # Unified minimum height

        # Get max height from current monitor's work area
        work_area = get_monitor_work_area(self._last_mouse_x, self._last_mouse_y)
        if work_area:
            MAX_HEIGHT = (work_area[3] - work_area[1]) - 80
        else:
            MAX_HEIGHT = self.root.winfo_screenheight() - 80

        # Padding - HORIZONTAL_PADDING lives at module scope (shared with the
        # furigana height estimate)
        VERTICAL_PADDING = vertical_padding   # header + footer + margins

        # Font with 20% safety margin for cross-machine compatibility
        try:
            ui_font = font.Font(family=base_font[0], size=base_font[1])
        except tk.TclError:
            ui_font = font.Font(family='Arial', size=base_font[1])

        base_line_height = ui_font.metrics("linespace")
        LINE_HEIGHT = int(base_line_height)

        # Width calculation
        longest_line = max((ui_font.measure(line) for line in text.split('\n')), default=0)
        ideal_width = longest_line + HORIZONTAL_PADDING
        width = max(MIN_WIDTH, min(ideal_width, MAX_WIDTH))

        # Height with CEILING division (always round UP)
        available_width = width - HORIZONTAL_PADDING

        total_lines = 0
        for para in text.split('\n'):
            if not para:
                total_lines += 1
                continue

            para_width = ui_font.measure(para)
            if para_width <= available_width:
                total_lines += 1
            else:
                # Ceiling division - never underestimate wrap lines
                total_lines += math.ceil(para_width / available_width)

        # Add 1 line buffer for edge cases
        total_lines += 1

        height = (total_lines * LINE_HEIGHT) + VERTICAL_PADDING

        return int(width), int(max(MIN_HEIGHT, min(height, MAX_HEIGHT)))

    def show(self, translated: str, target_lang: str, trial_info: dict = None, original: str = "",
             furigana_text: str = None, is_grammar: bool = False,
             model_info: str = None, source_lang: str = None):
        """Show popup with translation result.

        Args:
            translated: The translated text
            target_lang: The target language
            trial_info: Optional dict with trial mode info (from TranslationService.get_trial_info())
            original: The original text (for dictionary lookup)
            furigana_text: Optional furigana-annotated text with {kanji|reading} notation
            is_grammar: True when showing a Fix Grammar result. Hides the translation-only
                buttons (Re-translate, Dictionary, Custom Prompt) since they assume a real
                target language; keeps Copy / Replace / Open Translator for fixing in place.
            model_info: "model (Provider)" credit for the result, shown as a small note at
                the very top. None leaves the note off entirely - which is what happens for
                a cache hit whose stored entry predates the credit being recorded, because
                naming the model that merely ran most recently would be a lie.
            source_lang: The language a model (or the user) settled for `original`,
                or None. Decides the readings on kanji-only text (J6), and whether
                the Japanese / Chinese chooser is offered.

        Sized in two steps (Decision 34). Here everything is built at alpha 0 and given
        its width - the rows that must fit whole are measured, the text is wrapped for
        reading. Once Tk has laid the popup out at that width, `_finish_layout()` reads
        what each box really needs, gives it exactly that up to the cap, places the
        popup beside the cursor and makes it visible.
        """
        self.close()

        # Check if this is an error message
        is_error = is_error_text(translated)

        # One hint for the box and its measurement alike
        ruby_hint = self._ruby_hint(target_lang, is_grammar, original, source_lang)
        source_mode = self._source_row(original, source_lang, is_grammar, is_error)

        # Store original and translation for dictionary mode
        self._current_original = original
        self._current_translation = translated
        self._current_target_lang = target_lang
        self._current_trial_info = trial_info  # Store for restoring after custom-prompt cancel
        self._current_furigana = furigana_text  # Store for restoring after custom-prompt cancel
        self._current_source_lang = source_lang
        self._current_alignment = (validate_metadata(getattr(translated, 'alignment', None),
                                   original, translated, target_lang)
                                   if not is_error and not is_grammar else None)
        self._is_grammar = is_grammar  # Grammar-fix result: hide translation-only buttons
        self._linked_paused = False
        self._original_collapsed = True
        self._generation += 1

        # Create popup window - invisible until it has been measured and placed
        self.popup = tk.Toplevel(self.root)
        self.popup.overrideredirect(True)
        self.popup.configure(bg='#3d1f1f' if is_error else '#2b2b2b')
        try:
            self.popup.attributes('-alpha', 0.0)
        except tk.TclError:
            pass
        self.popup.protocol("WM_DELETE_WINDOW", self.dismiss)

        # On top while it is measured and for POPUP_FRONT_MS once it appears (`_reveal`),
        # then free to go behind other windows. Counted from here, the 100 ms it used to
        # be could run out before the invisible popup appeared, and the app the text came
        # from rose over it meanwhile (seen 2026-10-19: under a maximized VS Code).
        self.popup.attributes('-topmost', True)
        self._apply_noactivate()

        # Main frame
        main_frame = ttk.Frame(self.popup, padding=POPUP_FRAME_PADDING)
        main_frame.pack(fill=BOTH, expand=True)
        self._main_frame = main_frame
        self._bind_edges(main_frame)

        # The header: the credit, and the close button - shown at every width
        self._build_header(main_frame, None if is_error else model_info, is_grammar)

        # Trial mode warning header (if applicable)
        if trial_info and trial_info.get('is_trial') and not is_error:
            self._build_trial_line(main_frame, trial_info)

        # Button frame (Create FIRST to ensure it stays at BOTTOM)
        self._btn_frame = ttk.Frame(main_frame)
        self._btn_frame.pack(side=BOTTOM, fill=X, pady=(12, 0))
        self._bind_drag(self._btn_frame)
        if is_error:
            self._build_error_bar()
        else:
            self._build_action_bar(is_grammar)

        # Above the buttons: kanji-only text whose language nobody settled, or
        # a term someone did - and the way to the other language (K4)
        if source_mode:
            self._build_source_chooser(main_frame, source_mode, source_lang)

        # Source visibility is independent of optional readings and sentence links.
        if (furigana_text or (original and not is_grammar)) and not is_error:
            self._render_furigana(main_frame, furigana_text)
            # Separator between furigana and translation
            sep_frame = tk.Frame(main_frame, bg='#555555', height=1)
            sep_frame.pack(fill=X, pady=(8, 8))

        # Translation text, in a holder whose height step 2 sets in pixels
        text_fg = '#ff6b6b' if is_error else '#ffffff'
        self._text_holder, self.popup_text, self._text_scrollbar = self._make_box(
            main_frame, expand=True, wrap=tk.WORD, bg='#3d1f1f' if is_error else '#2b2b2b',
            base_fg=text_fg, kanji_fg=text_fg, base_font=('Segoe UI', 11),
            spacing1=0, spacing3=0, cursor='xterm')
        # Readings on the translation itself, not just the source block. The
        # target language is a reliable hint here, so a kanji-only translation
        # ("東京都") annotates where the source block cannot.
        # Error text is excluded: a diagnostic needs no readings.
        insert_output(self.popup_text, '1.0', translated,
                      lang_hint=ruby_hint,
                      enabled=self._ruby_enabled() and not is_error)
        self.popup_text.config(state='disabled')
        self._sync_linked_reading()
        self._linked_setting_binding = self.root.bind(
            '<<LinkedReadingChanged>>', self._sync_linked_reading, add='+')
        self.popup.bind('<Destroy>', lambda event:
                        self._unbind_linked_setting() if event.widget is self.popup else None, add='+')

        # Mouse wheel scroll is bound by RubyText, including over ruby frames

        self._build_grip()
        self._start_layout()

        # Bindings
        self.popup.bind('<Escape>', lambda e: self.dismiss())

    # ------------------------------------------------------------------ #
    # Building the popup (Decision 34)
    # ------------------------------------------------------------------ #
    def _bind_drag(self, widget) -> None:
        """Drag the popup by `widget`."""
        widget.bind("<Button-1>", self._start_move)
        widget.bind("<B1-Motion>", self._on_drag)

    def _bind_edges(self, frame) -> None:
        """The main frame's padding is the popup's border: within RESIZE_EDGE_PX of a side
        it resizes the popup (Decision 35), anywhere else it moves it, as it always did.
        No widgets of their own: eight edge widgets made every popup ~11 ms slower to
        build (measured 2026-10-19)."""
        frame.bind('<Motion>', self._edge_hover)
        frame.bind('<Leave>', self._edge_leave)
        frame.bind('<Button-1>', self._frame_press)
        frame.bind('<B1-Motion>', self._frame_drag)
        frame.bind('<ButtonRelease-1>', self._frame_release)

    @staticmethod
    def _edge_under(event) -> str:
        frame = event.widget
        return popup_layout.edge_at(event.x, event.y, frame.winfo_width(),
                                    frame.winfo_height(), RESIZE_EDGE_PX, RESIZE_CORNER_PX)

    @staticmethod
    def _set_cursor(frame, cursor: str) -> None:
        # Set only when it changes: <Motion> comes many times a second.
        if str(frame.cget('cursor')) != cursor:
            frame.configure(cursor=cursor)

    def _edge_hover(self, event) -> None:
        if self._grip_start is None:
            self._set_cursor(event.widget, RESIZE_CURSORS.get(self._edge_under(event), ''))

    def _edge_leave(self, event) -> None:
        # Children inherit a frame's cursor: left set, it would show over the text.
        if self._grip_start is None:
            self._set_cursor(event.widget, '')

    def _frame_press(self, event):
        edge = self._edge_under(event)
        if edge:
            return self._grip_press(event, edge)
        self._start_move(event)

    def _frame_drag(self, event):
        if self._grip_start is not None:
            return self._grip_drag(event)
        self._on_drag(event)

    def _frame_release(self, event):
        if self._grip_start is not None:
            self._grip_release(event)
            self._set_cursor(event.widget, '')
            return 'break'

    def _frame_bg(self) -> str:
        """The theme's frame background - what a plain tk widget on it must match."""
        try:
            return ttk.Style().lookup('TFrame', 'background') or '#2b2b2b'
        except Exception:
            return '#2b2b2b'

    def _icon_family(self) -> Optional[str]:
        """The icon font for the action bar, looked up once per manager."""
        if self._icon_family_cache is None:
            try:
                families = font.families(self.root)
            except tk.TclError:
                families = ()
            self._icon_family_cache = (icon_font_family(families),)
        return self._icon_family_cache[0]

    def _build_header(self, parent, model_info: Optional[str], is_grammar: bool) -> None:
        """The top row: "Translated with <model> (<Provider>)" on the left, the close
        button on the right. The button is packed first, so a long credit is what gets
        cut (`_fit_header`), never the button (TODO.md S1). A drag handle, like the
        rest of the frame; the credit is not a control."""
        header = ttk.Frame(parent)
        header.pack(side=TOP, fill=X, pady=(0, 6))
        self._bind_drag(header)
        self.popup_close_btn = tk.Button(
            header, text=CLOSE_GLYPH, command=self.dismiss, autostyle=False,
            bg=self._frame_bg(), fg=CLOSE_FG, activebackground=CLOSE_ACTIVE_BG,
            activeforeground='#ffffff', font=('Segoe UI', 9), relief='flat', bd=0,
            padx=6, pady=0, cursor='hand2')
        self.popup_close_btn.pack(side=RIGHT)
        self._attribution_text = None
        if model_info:
            verb = "Fixed" if is_grammar else "Translated"
            self._attribution_text = f"{verb} with {model_info}"
            attribution = ttk.Label(header, text=self._attribution_text,
                                    font=ATTRIBUTION_FONT, foreground=ATTRIBUTION_FG)
            attribution.pack(side=LEFT)
            self._bind_drag(attribution)
            self.popup_attribution = attribution

    def _build_trial_line(self, parent, trial_info: dict) -> None:
        """The trial-mode line under the header: quota left, and the way to a key."""
        trial_frame = ttk.Frame(parent)
        trial_frame.pack(side=TOP, fill=X, pady=(0, 8))
        self._trial_frame = trial_frame

        # Trial mode indicator
        remaining = trial_info.get('remaining', 0)
        daily_limit = trial_info.get('daily_limit', 50)

        if remaining <= 0:
            trial_text = "Trial quota exhausted - Add your API key"
            trial_color = '#ff6b6b'  # Red
        elif remaining <= 10:
            trial_text = f"Trial Mode ({remaining}/{daily_limit} left) - Low quota!"
            trial_color = '#ffaa00'  # Orange
        else:
            trial_text = f"Trial Mode ({remaining}/{daily_limit} left)"
            trial_color = '#88aaff'  # Light blue

        ttk.Label(trial_frame, text=trial_text,
                  font=('Segoe UI', 9, 'italic'),
                  foreground=trial_color).pack(side=LEFT)

        # "Get API Key" link button
        def open_guide():
            self.close()
            if self._on_open_settings:
                self._on_open_settings()

        # Sized to its label: a 14-character width cut "Get Free API Key" (TODO.md S2)
        guide_btn_kwargs = {"text": "Get Free API Key", "command": open_guide}
        if HAS_TTKBOOTSTRAP:
            guide_btn_kwargs["bootstyle"] = "link"
        ttk.Button(trial_frame, **guide_btn_kwargs).pack(side=RIGHT)

    def _text_button(self, parent, text: str, command, bg: str, active: str) -> tk.Button:
        return tk.Button(parent, text=text, command=command, autostyle=False,
                         bg=bg, fg='#ffffff', activebackground=active,
                         activeforeground='#ffffff', font=('Segoe UI', 10),
                         relief='flat', padx=12, pady=4, cursor='hand2')

    def _icon_button(self, parent, key: str, name: str, command, color: str,
                     tooltip: bool = True) -> tk.Button:
        """A secondary action: its icon on a neutral face that takes the action's colour
        on hover, named by a tooltip - or, without an icon font, its words as before.
        `action_name` carries the name either way."""
        family = self._icon_family()
        if family:
            button = tk.Button(parent, text=ICON_GLYPHS[key], command=command,
                               autostyle=False, bg=ICON_BG, fg='#ffffff',
                               activebackground=color, activeforeground='#ffffff',
                               font=(family, ICON_SIZE), relief='flat', borderwidth=0, padx=8, pady=4,
                               cursor='hand2')
            if tooltip:
                self._tooltips.append(Tooltip(button, name))
        else:
            button = self._text_button(parent, name, command, color, color)
        button.action_name = name
        return button

    def _build_action_bar(self, is_grammar: bool) -> None:
        """Copy and Replace as words - the two actions used most - and the rest as
        icons (Decision 34, TODO.md Q1 (c)): the bar no longer holds every popup at
        735 px. A grammar fix keeps Copy, Replace and Open Translator."""
        bar = self._btn_frame

        # Copy button
        self.popup_copy_btn = self._text_button(bar, "Copy", self._handle_copy,
                                                '#0d6efd', '#0b5ed7')  # Bootstrap primary blue
        self.popup_copy_btn.pack(side=LEFT, fill=Y)

        # Replace button (copy translated text + paste into source app)
        self.popup_replace_btn = self._text_button(bar, "Replace", self._handle_copy_and_replace,
                                                   '#6f42c1', '#5a32a3')  # Bootstrap purple
        self.popup_replace_btn.pack(side=LEFT, fill=Y, padx=(4, 0))

        # Replace settings gear icon (opens Hotkeys tab in Settings)
        self._replace_gear_btn = tk.Button(
            bar, text=GEAR_GLYPH, command=self._handle_open_replace_settings,
            autostyle=False, bg='#495057', fg='#ffffff', activebackground='#5a6268',
            activeforeground='#ffffff', font=('Segoe UI', 10), relief='flat',
            padx=4, pady=4, cursor='hand2')
        self._replace_gear_btn.pack(side=LEFT, fill=Y, padx=(0, 4))

        # Re-translate + Dictionary are translation-only — skip them for grammar results
        # (Re-translate would "translate to Grammar"; Dictionary expects a target language).
        if not is_grammar:
            # Re-translate - force a fresh API call, bypassing the cache
            self.popup_retranslate_btn = self._icon_button(
                bar, 'retranslate', "Re-translate", self._handle_re_translate, '#fd7e14')
            self.popup_retranslate_btn.pack(side=LEFT, fill=Y, padx=(4, 0))

            # Dictionary - opens Dictionary mode for the original text
            self.popup_dict_btn = self._icon_button(
                bar, 'dictionary', "Dictionary", self._open_dictionary_popup,
                DICT_BUTTON_COLOR, tooltip=False)
            self.popup_dict_btn.pack(side=LEFT, fill=Y, padx=(4, 0))
            # Update Dictionary button state based on NLP availability. It unbinds
            # <Enter> / <Leave>, so the tooltip is attached after it.
            self._update_dict_button_state()
            if self._icon_family():
                self._tooltips.append(Tooltip(self.popup_dict_btn, "Dictionary"))

        # Open Translator
        self.popup_open_btn = self._icon_button(
            bar, 'open', "Open Translator", self._handle_open_translator, '#198754')
        self.popup_open_btn.pack(side=RIGHT, fill=Y, padx=(16, 0))

        # Custom Prompt - make the box editable and ask the AI a freeform question
        # (translation-only; skipped for grammar results)
        if not is_grammar:
            self.popup_custom_prompt_btn = self._icon_button(
                bar, 'prompt', "Custom Prompt", self._handle_custom_prompt, '#20c997')
            self.popup_custom_prompt_btn.pack(side=LEFT, fill=Y, padx=(4, 0))
            self.popup_linked_btn = self._icon_button(
                bar, 'linked', 'Linked reading', self._toggle_linked_reading,
                '#3a5557', tooltip=False)
            self.popup_linked_btn.pack(side=LEFT, fill=Y, padx=(4, 0))
            self._linked_tooltip = Tooltip(self.popup_linked_btn, '')
            self._tooltips.append(self._linked_tooltip)

    def _build_error_bar(self) -> None:
        """A failure notice's bar: the way to the keys, and a way out."""
        # For errors, show "API Settings" button (opens Settings → API Key tab)
        settings_btn_kwargs = {"text": "API Settings", "command": self._handle_open_settings, "width": 14}
        if HAS_TTKBOOTSTRAP:
            settings_btn_kwargs["bootstyle"] = "warning"
        ttk.Button(self._btn_frame, **settings_btn_kwargs).pack(side=LEFT, padx=8)

        # ...and next to it, a way out of the popup entirely. A failed quick
        # translate often just needs a different model, a longer prompt or a
        # second attempt, all of which are quicker to do in the main window
        # than through this popup. It opens with the source text already in
        # the input box and an empty output, ready to translate.
        open_btn_kwargs = {"text": "Open Translator",
                           "command": self._handle_open_translator, "width": 16}
        if HAS_TTKBOOTSTRAP:
            open_btn_kwargs["bootstyle"] = "success"
        ttk.Button(self._btn_frame, **open_btn_kwargs).pack(side=RIGHT, padx=8)

    def _make_box(self, parent, expand: bool, **text_options):
        """A text box in a holder of its own. The holder's height is set in pixels
        (step 2), so no two boxes share leftover space - they used to, both packed to
        expand - and the scrollbar is packed beside the text only when the box is
        capped. Returns (holder, box, scrollbar)."""
        holder = tk.Frame(parent, height=1, bg=text_options.get('bg', '#2b2b2b'))
        holder.pack_propagate(False)
        holder.pack(side=TOP, fill=BOTH if expand else X, expand=expand)
        box = RubyText(holder, **text_options)
        box.pack(side=LEFT, fill=BOTH, expand=True)
        scroll_options = {'orient': 'vertical', 'command': box.yview}
        if HAS_TTKBOOTSTRAP:
            scroll_options['bootstyle'] = 'round'
        scrollbar = ttk.Scrollbar(holder, **scroll_options)
        return holder, box, scrollbar

    def _build_grip(self) -> None:
        """A resize grip in the bottom-right corner (Decision 34, TODO.md P4). The size
        the user drags the popup to is remembered and becomes the next popup's reading
        width and height cap; a double-click returns to automatic sizing. A drag moves
        an outline, not the popup, and every edge and corner can be dragged
        (`_bind_edges`, Decision 35)."""
        grip = tk.Label(self.popup, text=GRIP_GLYPH, font=('Segoe UI', 8), fg='#6c757d',
                        bg=self._frame_bg(), cursor='size_nw_se', padx=0, pady=0,
                        autostyle=False)
        grip.place(relx=1.0, rely=1.0, anchor='se', x=-2, y=-2)
        grip.bind('<ButtonPress-1>', self._grip_press)
        grip.bind('<B1-Motion>', self._grip_drag)
        grip.bind('<ButtonRelease-1>', self._grip_release)
        grip.bind('<Double-Button-1>', self._grip_reset)
        self._grip = grip

    # ------------------------------------------------------------------ #
    # Measuring and placing (Decision 34)
    # ------------------------------------------------------------------ #
    def _anchor(self) -> Tuple[int, int]:
        """The cursor at hotkey time - what the popup opens beside and never covers."""
        return self._last_mouse_x, self._last_mouse_y

    def _work_area(self) -> popup_layout.WorkArea:
        """The work area of the monitor holding the cursor (the taskbar left out)."""
        area = get_monitor_work_area(self._last_mouse_x, self._last_mouse_y)
        if area:
            return popup_layout.WorkArea(*area)
        return popup_layout.WorkArea(0, 0, self.root.winfo_screenwidth(),
                                     self.root.winfo_screenheight() - 50)

    def _saved_size(self) -> Tuple[Optional[int], Optional[int]]:
        """The size the user last dragged a popup to, or (None, None)."""
        getter = getattr(self.config, 'get_quick_popup_size', None)
        if not callable(getter):
            return None, None
        try:
            width, height = getter()
        except Exception:
            return None, None
        return width, height

    def _remember_size(self, width: Optional[int], height: Optional[int]) -> None:
        setter = getattr(self.config, 'set_quick_popup_size', None)
        if callable(setter):
            try:
                setter(width, height)
            except Exception as e:
                logging.warning(f"[Popup] could not remember the popup size: {e}")

    @staticmethod
    def _count(box, *args) -> int:
        """Text.count() returns a tuple, a bare int or None depending on the Tk build."""
        value = box.count(*args)
        if isinstance(value, tuple):
            return value[0]
        return value or 0

    @staticmethod
    def _insets(box, axis: str) -> int:
        """A Text widget's border, highlight and padding, both sides of one axis."""
        pad = 'pady' if axis == 'y' else 'padx'
        return 2 * sum(int(float(str(box.cget(option))))
                       for option in ('borderwidth', 'highlightthickness', pad))

    def _content_px(self, box) -> int:
        """Pixels `box`'s content needs, laid out at the box's present width."""
        return self._count(box, '1.0', 'end', 'update', 'ypixels')

    def _rows_px(self, box, rows: int) -> int:
        """Pixels of the first `rows` display lines - all of it when there are fewer."""
        # Tk clamps a display-line index past the content to end. Counting all
        # wrapped lines first is quadratic on very long logical paragraphs.
        return self._count(box, '1.0', f'1.0 + {rows} display lines', 'update', 'ypixels')

    def _required_width(self) -> int:
        """The popup width the rows that must fit whole ask for - the action bar, the
        trial line, the chooser row, the original's header, the close button with the
        least of the credit - plus the frame padding. Read off the widgets
        (`packed_row_width`), never a constant (TODO.md S1)."""
        rows = (self._btn_frame, self._trial_frame, self.popup_source_chooser,
                self._original_header)
        widest = max((packed_row_width(row) for row in rows if row is not None), default=0)
        header = self.popup_close_btn.winfo_reqwidth() if self.popup_close_btn else 0
        if self.popup_attribution is not None:
            header += HEADER_CREDIT_MIN_PX
        return max(widest, header) + 2 * POPUP_FRAME_PADDING

    def _automatic_width(self, saved_width: Optional[int] = None) -> int:
        """The text's natural width, wrapped for reading (70 Latin / 36 CJK characters
        a line) or at the width the user dragged a popup to; never narrower than the
        rows ask for (`popup_layout.popup_width`)."""
        insets = 2 * POPUP_FRAME_PADDING + self._insets(self.popup_text, 'x')
        base = self.popup_text.base_font
        measure = font.Font(family=base[0], size=base[1]).measure
        natural = popup_layout.natural_width(self._current_translation, measure)
        readable = popup_layout.reading_width(self._current_translation, measure)
        if self.popup_furigana is not None:
            # Both texts wrap at one width: the narrower of their reading widths keeps
            # each within its own (an English line under a Japanese original at 36 CJK
            # characters' width would otherwise run past 70 characters).
            base = self.popup_furigana.base_font
            original = font.Font(family=base[0], size=base[1]).measure
            natural = max(natural, popup_layout.natural_width(self._current_original, original))
            readable_original = popup_layout.reading_width(self._current_original, original)
            if readable_original:
                readable = min(readable, readable_original) if readable else readable_original
        if saved_width:
            readable = max(1, saved_width - insets)
        return popup_layout.popup_width(natural, readable, insets, self._required_width(),
                                        self._work_area().width)

    def _fit_header(self, width: int) -> None:
        """Cut the credit with an ellipsis where it would crowd the close button."""
        if self.popup_attribution is None or not self._attribution_text:
            return
        available = (width - 2 * POPUP_FRAME_PADDING
                     - self.popup_close_btn.winfo_reqwidth() - 8)
        measure = font.Font(font=ATTRIBUTION_FONT).measure
        self.popup_attribution.configure(
            text=popup_layout.elide(self._attribution_text, measure, available))

    def _start_layout(self) -> None:
        """Step 1: the width now, the popup placed at the height cap - still invisible.
        Step 2 (`_finish_layout`) follows when the translation box has been laid out at
        that width (its <Configure>), or after POPUP_LAYOUT_WATCHDOG_MS should that
        never come.

        The cap, not a guess: a guess shorter than the chrome had the packer squeeze the
        translation box out altogether, so it never got its width and step 2 never came
        (measured on the trial line + chooser row case). Never less than the automatic
        cap either: a height the user dragged a popup down to can be shorter than the
        next popup's chrome - the same squeeze. Nobody sees this height."""
        saved_width, saved_height = self._saved_size()
        work = self._work_area()
        width = self._automatic_width(saved_width)
        self._fit_header(width)
        cap = popup_layout.height_cap(work, saved_height)
        provisional = max(cap, popup_layout.height_cap(work))
        x, y, height = popup_layout.place(self._anchor(), width, provisional, work,
                                          min_height=min(provisional, 120))
        self.popup.geometry(f"{width}x{height}+{x}+{y}")
        generation = self._generation
        self._layout = {'generation': generation, 'width': width, 'work': work,
                        'cap': cap, 'done': False}
        self.popup_text.bind('<Configure>',
                             lambda _event, g=generation: self._finish_layout(g), add='+')
        # On the root, not the popup: destroying the popup deletes the commands of its
        # timers but not the timers, which later fire into whatever command reuses the
        # name (seen 2026-10-19: a resize handler called with no event).
        self.root.after(POPUP_LAYOUT_WATCHDOG_MS,
                        lambda g=generation: self._finish_layout(g, forced=True))

    def _finish_layout(self, generation: int, forced: bool = False) -> None:
        """Step 2: measure each box, give it exactly what it needs up to the cap, place
        the popup and make it visible. Once per popup; a popup closed or replaced
        meanwhile is left alone. Whatever goes wrong, the popup is shown."""
        layout = self._layout
        if (layout is None or layout['done'] or generation != self._generation
                or self.popup is None or self.popup_text is None):
            return
        expected = layout['width'] - 2 * POPUP_FRAME_PADDING
        laid_out = abs(self.popup_text.winfo_width() - expected) <= 2
        if not laid_out and not forced:
            return                      # an intermediate size; the next <Configure> follows
        layout['done'] = True
        try:
            if self.popup_text.winfo_width() > 1:
                self._fit_boxes(reposition=True)
                # Seen only once Tk has redrawn it at its final size: revealed in the same
                # breath, the first frame still carried the drawing at the provisional
                # size, cut to the new one (caught by the gallery's screenshots).
                self.root.after(POPUP_REVEAL_DELAY_MS,
                                lambda g=generation: self._reveal(g))
                return
            logging.warning("[Popup] not laid out in time - shown at its estimated size")
        except Exception as e:
            logging.warning(f"[Popup] measuring failed - shown at its estimated size: {e}")
        self._reveal(generation)

    def _reveal(self, generation: Optional[int] = None) -> None:
        """Make the popup visible - its pending redraws flushed first."""
        if self.popup is None or (generation is not None and generation != self._generation):
            return
        try:
            self.popup.update_idletasks()
            self.popup.attributes('-alpha', 1.0)
            self.popup.attributes('-topmost', True)
            self.root.after(POPUP_FRONT_MS, lambda popup=self.popup: self._end_front(popup))
        except tk.TclError:
            pass
        if self._layout is not None:
            self._layout['revealed'] = True

    def _end_front(self, popup) -> None:
        """POPUP_FRONT_MS after it appeared: the popup may go behind other windows."""
        if popup is self.popup and popup is not None:
            try:
                popup.attributes('-topmost', False)
            except tk.TclError:
                pass

    def _fit_boxes(self, reposition: bool = True,
                   size: Optional[Tuple[int, int]] = None,
                   position: Optional[Tuple[int, int]] = None) -> None:
        """Measure the boxes and give each its height; place the popup or keep it.

        `reposition`: place the popup beside the cursor (a new popup); otherwise its
        corner stays (the replace preview, the original's toggle) unless that would
        run off the screen. `size`: the (width, height) the user dragged the popup to;
        the boxes then share that height, the translation taking the rest, and keep
        POPUP_USER_MIN_ROWS each. `position`: where the user's drag put its corner (a
        drag by the left or top edge moves it); without it the corner stays.
        """
        layout = self._layout
        work = layout['work']
        if size is not None:
            corner = f"+{position[0]}+{position[1]}" if position is not None else ""
            self.popup.geometry(f"{size[0]}x{size[1]}{corner}")
        self.popup.update_idletasks()

        rows = POPUP_MIN_BOX_ROWS if size is None else POPUP_USER_MIN_ROWS
        text_insets = self._insets(self.popup_text, 'y')
        need_t = self._content_px(self.popup_text) + text_insets
        min_t = min(need_t, self._rows_px(self.popup_text, rows) + text_insets)
        need_o = min_o = 0
        limit_o = None
        original_share = popup_layout.ORIGINAL_SHARE
        if self.popup_furigana is not None:
            original_insets = self._insets(self.popup_furigana, 'y')
            need_o = self._content_px(self.popup_furigana) + original_insets
            collapsed_o = min(need_o, self._rows_px(self.popup_furigana,
                                                    POPUP_COLLAPSED_ORIGINAL_ROWS)
                              + original_insets)
            collapsible = need_o > collapsed_o
            self._show_original_toggle(collapsible)
            if collapsible and self._original_collapsed:
                limit_o = collapsed_o
            # The least it keeps: its collapsed rows - at a size the user chose, `rows`.
            min_o = collapsed_o if size is None else min(
                need_o, self._rows_px(self.popup_furigana, rows) + original_insets)
            self.popup.update_idletasks()
        shown_o = need_o if limit_o is None else min(need_o, limit_o)
        chrome = (self._main_frame.winfo_reqheight() - self._text_holder.winfo_reqheight()
                  - (self._original_holder.winfo_reqheight()
                     if self._original_holder is not None else 0))

        if size is not None:
            width, height = size
            x, y = position if position is not None else (self.popup.winfo_x(),
                                                          self.popup.winfo_y())
        else:
            width = layout['width']
            desired = min(chrome + need_t + shown_o, layout['cap'])
            if reposition:
                x, y, height = popup_layout.place(self._anchor(), width, desired, work,
                                                  min_height=chrome + min_t + min_o)
            else:
                # The edge nearest the cursor stays; the popup grows away from it, so
                # it still never covers the cursor - and stays on the screen.
                x, y = self.popup.winfo_x(), self.popup.winfo_y()
                bottom_edge = y + self.popup.winfo_height()
                if bottom_edge <= self._anchor()[1]:
                    height = min(desired, bottom_edge - (work.top + POPUP_SCREEN_MARGIN))
                    y = bottom_edge - height
                else:
                    height = min(desired, work.bottom - POPUP_SCREEN_MARGIN - y)
                height = max(height, chrome + min_t + min(min_o, shown_o))

        room = height - chrome
        if not self._original_collapsed:
            heights = popup_layout.allocate_expanded(room, need_t, need_o,
                                                    min_translation=min_t, min_original=min_o)
        else:
            heights = popup_layout.allocate(room, need_t, need_o, min_translation=min_t,
                                            min_original=min_o, original_limit=limit_o,
                                            original_share=original_share)
        self._show_original_toggle(bool(limit_o is not None or need_o > min_o
                                        or heights.translation_capped or not self._original_collapsed))
        if size is not None:
            # The user's size: the translation takes whatever the original leaves.
            translation = max(heights.translation, room - heights.original)
            heights = popup_layout.Heights(translation, heights.original,
                                           need_t > translation, heights.original_capped)
        gutter = self._text_scrollbar.winfo_reqwidth() if heights.any_capped or not self._original_collapsed else 0
        self._fit_box(self._text_holder, self.popup_text, self._text_scrollbar,
                      heights.translation, heights.translation_capped, gutter)
        if self._original_holder is not None:
            self._fit_box(self._original_holder, self.popup_furigana, self._original_scrollbar,
                          heights.original, heights.original_capped, gutter)

        if size is None:
            # The scrollbar sits beside the text, not on it: the text keeps its width
            # and does not re-wrap under the measurement just made.
            width += gutter
            height = chrome + heights.translation + heights.original
            if reposition and gutter:
                x = popup_layout.place(self._anchor(), width, height, work,
                                       min_height=height)[0]
        self.popup.geometry(f"{width}x{height}+{x}+{y}")
        layout.update(chrome=chrome, heights=heights, size=(width, height), position=(x, y))

    def _fit_box(self, holder, box, scrollbar, height: int, capped: bool,
                 gutter: int) -> None:
        """Give a box its height, and a scrollbar when it is capped. A box that is not
        capped while the other one is gets a spacer as wide as the scrollbar, so both
        texts keep one width and nothing re-wraps."""
        holder.configure(height=max(1, height))
        spacer = getattr(holder, 'gutter_spacer', None)
        if capped:
            if spacer is not None:
                spacer.pack_forget()
            scrollbar.pack(side=RIGHT, fill=Y, before=box)
            box.configure(yscrollcommand=scrollbar.set)
            if getattr(self, '_linked_controller', None):
                self._linked_controller.watch_scroll(box)
            return
        scrollbar.pack_forget()
        box.configure(yscrollcommand='')
        if getattr(self, '_linked_controller', None):
            self._linked_controller.watch_scroll(box)
        if gutter:
            if spacer is None:
                spacer = tk.Frame(holder, width=gutter, bg=str(holder.cget('bg')))
                holder.gutter_spacer = spacer
            spacer.configure(width=gutter)
            spacer.pack(side=RIGHT, fill=Y, before=box)
        elif spacer is not None:
            spacer.pack_forget()

    # ------------------------------------------------------------------ #
    # The grip: a size the user chooses (Decision 34, TODO.md P4)
    # ------------------------------------------------------------------ #
    def _grip_press(self, event, edge: str = 'se') -> str:
        """A drag starts on `edge` (popup_layout.EDGES). The least it may shrink to is
        read now: the rows that must fit whole across, and a row of each box down."""
        self._user_rect = None              # set by this drag's motions, if it has any
        if getattr(self, '_linked_controller', None):
            self._linked_controller.clear()
        if self.popup is not None and self._layout is not None:
            least = self._layout.get('chrome', 0)
            for box in (self.popup_text, self.popup_furigana):
                if box is not None:
                    least += (self._rows_px(box, POPUP_USER_MIN_ROWS)
                              + self._insets(box, 'y'))
            self._grip_start = {
                'pointer': (event.x_root, event.y_root), 'edge': edge,
                'rect': (self.popup.winfo_x(), self.popup.winfo_y(),
                         self.popup.winfo_width(), self.popup.winfo_height()),
                'min_width': self._required_width(), 'min_height': least}
        return 'break'

    def _screen_at(self, x: int, y: int) -> popup_layout.WorkArea:
        """The work area of the monitor under (x, y), or the nearest one."""
        area = get_monitor_work_area(x, y)
        return popup_layout.WorkArea(*area) if area else self._layout['work']

    def _grip_drag(self, event) -> str:
        """Move the outline to the rectangle being dragged to. The popup itself is laid
        out only when the drag pauses (POPUP_GRIP_PREVIEW_MS) and on release: laying it
        out on every motion cost 14-190 ms a step, so a long text followed the mouse at
        a few frames a second (Decision 35). A moving edge stops at the screen under the
        pointer - not the one the popup opened on, which it may have been dragged off."""
        if self.popup is None or self._grip_start is None or self._layout is None:
            return 'break'
        start = self._grip_start
        start_x, start_y = start['pointer']
        rect = popup_layout.resize(start['rect'], start['edge'], event.x_root - start_x,
                                   event.y_root - start_y, min_width=start['min_width'],
                                   min_height=start['min_height'],
                                   bounds=self._screen_at(event.x_root, event.y_root))
        self._user_rect = tuple(int(value) for value in rect)
        self._user_size = self._user_rect[2:]
        try:
            self._show_grip_outline(*self._user_rect)
        except tk.TclError:
            pass
        self._cancel_grip_preview()
        self._grip_preview_after = self.root.after(POPUP_GRIP_PREVIEW_MS, self._grip_preview)
        return 'break'

    def _show_grip_outline(self, x: int, y: int, width: int, height: int) -> None:
        """The size being dragged to, as a frame over the popup: transparent inside,
        topmost, and `WS_EX_NOACTIVATE` once mapped, like a tooltip. A child of the
        popup, so closing the popup takes it too."""
        outline = self._grip_outline
        if outline is None:
            outline = tk.Toplevel(self.popup)
            outline.overrideredirect(True)
            outline.attributes('-topmost', True)
            # Coloured after construction: ttkbootstrap re-themes it while it is built.
            outline.configure(bg=GRIP_OUTLINE_KEY, highlightthickness=GRIP_OUTLINE_PX,
                              highlightbackground=GRIP_OUTLINE_COLOR,
                              highlightcolor=GRIP_OUTLINE_COLOR)
            try:
                outline.attributes('-transparentcolor', GRIP_OUTLINE_KEY)
            except tk.TclError:
                outline.attributes('-alpha', 0.35)  # no colour key: see the popup through
            outline.bind('<Map>', lambda _event: set_noactivate(outline), add='+')
            self._grip_outline = outline
        outline.geometry(f"{width}x{height}+{x}+{y}")

    def _hide_grip_outline(self) -> None:
        if self._grip_outline is not None:
            try:
                self._grip_outline.destroy()
            except tk.TclError:
                pass
            self._grip_outline = None

    def _cancel_grip_preview(self) -> None:
        if self._grip_preview_after is not None:
            try:
                self.root.after_cancel(self._grip_preview_after)
            except tk.TclError:
                pass
            self._grip_preview_after = None

    def _grip_preview(self) -> None:
        """The drag has paused: the popup takes the outline's size while the button is
        still held, so the user sees the text re-wrapped before letting go."""
        self._grip_preview_after = None
        if self._grip_start is not None:
            self._apply_user_size()

    def _apply_user_size(self) -> None:
        """Lay the popup out at the rectangle the user dragged it to - unless it already
        is (a pause laid it out, and the release came at the same place and size)."""
        rect = self._user_rect
        if (self.popup is None or self._layout is None or not rect
                or (self._layout.get('position'), self._layout.get('size'))
                == (rect[:2], rect[2:])):
            return
        try:
            self._fit_boxes(reposition=False, size=rect[2:], position=rect[:2])
        except tk.TclError:
            pass

    def _grip_release(self, _event=None) -> str:
        self._cancel_grip_preview()
        if self._grip_start is not None and self._user_rect:
            # Laid out before the outline goes, so the popup is never seen at neither.
            self._apply_user_size()
            self._remember_size(*self._user_size)
        self._hide_grip_outline()
        self._grip_start = None
        return 'break'

    def _grip_reset(self, _event=None) -> str:
        """Double-click on the grip: forget the dragged size, back to automatic."""
        self._cancel_grip_preview()
        self._hide_grip_outline()
        self._user_size = None
        self._user_rect = None
        self._grip_start = None
        self._remember_size(None, None)
        if self.popup is not None and self._layout is not None:
            width = self._automatic_width(None)
            self._layout['width'] = width
            self._layout['cap'] = popup_layout.height_cap(self._layout['work'])
            self.popup.geometry(f"{width}x{self.popup.winfo_height()}")
            self._fit_boxes(reposition=False)
        return 'break'

    def _ruby_enabled(self) -> bool:
        """Whether popup output should carry readings.

        The Settings toggle now governs every annotated surface, because the
        popup annotates at render time instead of relying on the pipeline
        having shipped a notation string.
        """
        return bool(self.config and self.config.get_furigana_enabled())

    @staticmethod
    def _ruby_hint(target_lang: str, is_grammar: bool = False, original: str = "",
                   source_lang: Optional[str] = None) -> Optional[str]:
        """Language hint for annotating output text, or None when unknown.

        A translation is in its target language - and, by the language-set rule
        (`lang_id.output_hint`), Japanese quoted in, say, English output is
        Japanese when the source was. A grammar fix keeps the source's language:
        Japanese when the original's characters or its verdict say so (J6), else
        no hint - kanji-only output then stays plain rather than guessing.
        """
        source = lang_id.resolve(original, model=source_lang).language if original else None
        if is_grammar:
            return lang_id.JAPANESE if source == lang_id.JAPANESE else None
        return lang_id.output_hint(source, target_lang)

    @staticmethod
    def _source_row(original: str, source_lang: Optional[str], is_grammar: bool,
                    is_error: bool) -> Optional[str]:
        """Which Japanese / Chinese row to offer (`source_marker.source_row`):
        ROW_ASK for kanji that neither the characters nor a model settled
        (Decision 22), ROW_CHANGE for a term a model or the user did (K4) -
        never on a grammar fix or a failure notice."""
        if is_grammar or is_error or not original:
            return None
        return source_row(original, source_lang)

    def _build_source_chooser(self, parent, mode: str, verdict: Optional[str]) -> None:
        """The Japanese / Chinese row, above the buttons (`fill_source_row`).

        A row, not a dialog: the translation is already on screen, and nothing
        is blocked while the question stands. Answering re-translates with the
        chosen source - a translation the model could not place may carry the
        other language's sense (先生 came back "Mr."), so readings alone would sit
        above the wrong meaning.
        """
        row = ttk.Frame(parent)
        row.pack(side=BOTTOM, fill=X, pady=(8, 0))
        row.bind("<Button-1>", self._start_move)
        row.bind("<B1-Motion>", self._on_drag)
        fill_source_row(row, mode, verdict, self._handle_choose_source)
        self.popup_source_chooser = row

    def _handle_choose_source(self, language: str) -> None:
        if self._on_choose_source:
            self._on_choose_source(language)

    def _linked_enabled(self):
        getter = getattr(self.config, 'get_linked_reading_enabled', None)
        return getter is not None and getter() is True

    def _stop_linked_reading(self):
        controller = getattr(self, '_linked_controller', None)
        if controller is not None:
            controller.close()
            self._linked_controller = None

    def _toggle_linked_reading(self):
        self.config.set_linked_reading_enabled(not self._linked_enabled())
        self._sync_linked_reading()
        self.root.event_generate('<<LinkedReadingChanged>>', when='tail')

    def _sync_linked_reading(self, _event=None):
        """Apply the shared preference without regenerating or replacing text."""
        if self.popup is None or not self.popup.winfo_exists() or self._linked_paused:
            return
        enabled = self._linked_enabled()
        if (enabled and not self._current_alignment and not self._is_grammar
                and not is_error_text(self._current_translation)):
            value = reading_result(self._current_translation, None, self._current_original,
                                   self._current_target_lang)
            self._current_alignment = getattr(value, 'alignment', None)
        if self.popup_linked_btn is not None:
            self.popup_linked_btn.configure(
                bg='#2e4446' if enabled else ICON_BG,
                fg='#b7e3dc' if enabled else '#c4cbd4',
                activebackground='#3a5557' if enabled else '#495057',
                activeforeground='#ffffff')
        status = ''
        if enabled:
            status = (('Approximate links' if self._current_alignment.get('method') == 'structure'
                       else 'Hover to link sentences') if self._current_alignment else 'No reliable links')
        if self._linked_status is not None:
            self._linked_status.configure(text=status)
        if self._linked_tooltip is not None:
            self._linked_tooltip.text = (
                ('Linked reading: On. ' + status + '.') if enabled else
                'Linked reading: Off. Click to enable saved or local links.')
        if not enabled:
            self._stop_linked_reading()
        elif (getattr(self, '_linked_controller', None) is None
              and self._current_alignment and self.popup_furigana is not None
              and self.popup_text is not None
              and self.popup_furigana.get_plain() == self._current_original
              and self.popup_text.get_plain() == self._current_translation):
            self._linked_controller = LinkedReadingController(
                self.root, self.popup_furigana, self.popup_text, self._current_alignment,
                suspended=lambda: not self._linked_enabled() or self._grip_start is not None)

    def _unbind_linked_setting(self):
        if self._linked_setting_binding is not None:
            self.root.unbind('<<LinkedReadingChanged>>', self._linked_setting_binding)
            self._linked_setting_binding = None

    def _render_furigana(self, parent, furigana_text: str):
        """The original, with its readings, above the translation - read-only, under a
        small header that names it and, when it runs longer than
        POPUP_COLLAPSED_ORIGINAL_ROWS rows, collapses or opens it (Decision 34, TODO.md
        Q5: collapsed by default - the translation is what was asked for).

        RubyText owns the ruby layout, the plain-text readback and the wheel
        handling; the notation escapes are honored, so source text containing
        a literal "{a|b}" shows as itself instead of a fake reading.

        Args:
            parent: Parent frame to pack into
            furigana_text: Text with {kanji|reading} notation
        """
        header = ttk.Frame(parent)
        header.pack(side=TOP, fill=X, pady=(0, 2))
        self._bind_drag(header)
        known = self._current_source_lang or (lang_id.JAPANESE if furigana_text else None)
        language = language_label(known) if known else None
        name = ttk.Label(header, text=f"Original ({language})" if language else 'Original', font=ORIGINAL_HEADER_FONT,
                         foreground=ATTRIBUTION_FG)
        name.pack(side=LEFT)
        self._bind_drag(name)
        self._linked_status = ttk.Label(header, text='', font=ORIGINAL_HEADER_FONT,
                                        foreground=ATTRIBUTION_FG)
        self._linked_status.pack(side=LEFT, padx=(12, 0))
        # Packed by step 2, and only when the original is longer than its collapsed rows
        toggle = tk.Label(header, text="Show all", font=ORIGINAL_HEADER_FONT,
                          fg=ORIGINAL_TOGGLE_FG, bg=self._frame_bg(), cursor='hand2',
                          autostyle=False)
        toggle.bind('<Button-1>', self._toggle_original)
        self.popup_original_toggle = toggle
        self._original_header = header

        self._original_holder, self.popup_furigana, self._original_scrollbar = self._make_box(
            parent, expand=False, wrap=tk.WORD, bg='#2b2b2b')
        if furigana_text:
            self.popup_furigana.insert_notation(tk.END, furigana_text)
        else:
            insert_output(self.popup_furigana, tk.END, self._current_original,
                          lang_hint=self._current_source_lang, enabled=self._ruby_enabled())
        self.popup_furigana.config(state='disabled')

    def _show_original_toggle(self, collapsible: bool) -> None:
        """"Show all" / "Show less" on the original's header - only when it is long."""
        toggle = self.popup_original_toggle
        if toggle is None:
            return
        if collapsible:
            toggle.configure(text="Show all" if self._original_collapsed else "Show less")
            toggle.pack(side=RIGHT)
        else:
            toggle.pack_forget()

    def _toggle_original(self, _event=None) -> str:
        """Fit both full texts using measured width/height, or restore compact mode."""
        if self.popup is None or self._layout is None or not self._layout['done']:
            return 'break'
        if getattr(self, '_linked_controller', None):
            self._linked_controller.clear()
        if self._original_collapsed:
            self._expand_pair()
        else:
            self._original_collapsed = True
            saved = self._expanded_restore
            self._expanded_restore = None
            if saved:
                width, height, x, y, layout_width, cap = saved
                self._layout.update(width=layout_width, cap=cap)
                self._fit_header(width)
                self._fit_boxes(reposition=False, size=(width, height), position=(x, y))
            else:
                self._fit_boxes(reposition=False, size=self._user_size)
        return 'break'

    def _expand_pair(self):
        current = self.popup.winfo_width()
        self._expanded_restore = (current, self.popup.winfo_height(), self.popup.winfo_x(),
                                  self.popup.winfo_y(), self._layout['width'], self._layout['cap'])
        area = get_monitor_work_area(self.popup.winfo_rootx(), self.popup.winfo_rooty())
        work = popup_layout.WorkArea(*area) if area else self._layout['work']
        self._layout['work'] = work
        cap = max(1, min(round(work.height * 0.9), work.height - 2 * POPUP_SCREEN_MARGIN))
        chrome = self._layout['chrome']
        gutter = self._text_scrollbar.winfo_reqwidth()
        # Reserve one consistent gutter during all probes; scrollbar insertion
        # cannot change the width after the text has been measured.
        for holder, box, scrollbar in ((self._text_holder, self.popup_text, self._text_scrollbar),
                                        (self._original_holder, self.popup_furigana, self._original_scrollbar)):
            if box is not None:
                self._fit_box(holder, box, scrollbar, holder.winfo_height(), False, gutter)
        measurements = []
        for width in popup_layout.expansion_widths(current, self._required_width(), work):
            self.popup.geometry(f'{width}x{cap}')
            self.popup.update_idletasks()
            need_t = self._content_px(self.popup_text) + self._insets(self.popup_text, 'y')
            need_o = (self._content_px(self.popup_furigana) + self._insets(self.popup_furigana, 'y')
                      if self.popup_furigana is not None else 0)
            measurements.append((width, need_t, need_o))
            if chrome + need_t + need_o <= cap:
                break
        width, height = popup_layout.choose_expansion(measurements, cap, chrome, round(current * 1.7))
        x = min(max(work.left + POPUP_SCREEN_MARGIN, self._expanded_restore[2]),
                work.right - POPUP_SCREEN_MARGIN - width)
        y = min(max(work.top + POPUP_SCREEN_MARGIN, self._expanded_restore[3]),
                work.bottom - POPUP_SCREEN_MARGIN - height)
        self._original_collapsed = False
        self._layout.update(width=width, cap=cap)
        self._fit_header(width)
        self._fit_boxes(reposition=False, size=(width, height), position=(x, y))

    def _start_move(self, event):
        """Record start position for dragging."""
        if getattr(self, '_linked_controller', None):
            self._linked_controller.clear()
        self._drag_x = event.x_root
        self._drag_y = event.y_root

    def _on_drag(self, event):
        """Handle dragging of the popup."""
        if not self.popup:
            return

        deltax = event.x_root - self._drag_x
        deltay = event.y_root - self._drag_y

        self._drag_x = event.x_root
        self._drag_y = event.y_root

        x = self.popup.winfo_x() + deltax
        y = self.popup.winfo_y() + deltay
        self.popup.geometry(f"+{x}+{y}")

    def _handle_copy(self):
        """Handle copy button click."""
        if self._on_copy:
            self._on_copy()

    def _handle_copy_and_replace(self):
        """Handle replace button - Quick or Manual mode based on config."""
        is_quick = self.config and self.config.get_quick_replace()

        if is_quick or not self._current_original:
            # Quick Replace mode OR no original text → immediate replace
            if self._on_copy_and_replace:
                self._on_copy_and_replace()
            return

        self._show_replace_preview()

    def _handle_re_translate(self):
        """Handle Re-translate button - force a fresh API call, bypassing the cache."""
        if self._on_re_translate:
            self._on_re_translate()

    def _clear_noactivate(self):
        """Remove WS_EX_NOACTIVATE so the popup can receive keyboard focus (edit mode)."""
        if self.popup:
            set_noactivate(self.popup, False)

    def _handle_custom_prompt(self):
        """Handle Custom Prompt button - switch the box to editable freeform-ask mode."""
        self._enter_custom_prompt_mode()

    def _enter_custom_prompt_mode(self):
        """Make the translation box editable and swap the button bar to [Send][Cancel].

        Keeps the current translation as the starting prompt so the user can append or
        edit freely. The entire box content is sent verbatim on Send (no translate
        wrapper). Furigana, if shown, stays as a read-only guide above the box.
        """
        if not self.popup_text or not self._btn_frame:
            return

        self._linked_paused = True
        self._stop_linked_reading()

        # I3 - an editable widget never holds ruby. edit_undo() cannot restore a
        # destroyed embedded window, and typing next to one would leave the
        # readings describing text the user has already changed. The source
        # block above the box keeps its readings.
        if self.popup_text.has_ruby:
            self.popup_text.set_plain(self.popup_text.get_plain())

        # Make the box editable and visually mark edit mode (teal border).
        self.popup_text.config(state='normal',
                               highlightthickness=1,
                               highlightbackground='#20c997',
                               highlightcolor='#20c997')

        # The popup was created WS_EX_NOACTIVATE (so it won't steal focus from the source
        # app). Editing needs keyboard focus, so drop that bit and force focus now.
        self._clear_noactivate()
        try:
            self.popup.attributes('-topmost', True)
            self.popup.lift()
            self.popup.focus_force()
        except Exception:
            pass
        self.popup_text.focus_set()
        self.popup_text.mark_set('insert', 'end')
        self.popup_text.see('end')

        # Swap button bar to [Send] [Cancel] + close.
        for widget in self._btn_frame.winfo_children():
            widget.destroy()

        tk.Button(
            self._btn_frame,
            text="Send",
            command=self._handle_custom_prompt_send,
            autostyle=False,
            bg='#20c997',
            fg='#ffffff',
            activebackground='#1aa179',
            activeforeground='#ffffff',
            font=('Segoe UI', 10, 'bold'),
            relief='flat',
            padx=16, pady=4,
            cursor='hand2'
        ).pack(side=LEFT)

        tk.Button(
            self._btn_frame,
            text="Cancel",
            command=self._handle_custom_prompt_cancel,
            autostyle=False,
            bg='#6c757d',
            fg='#ffffff',
            activebackground='#5a6268',
            activeforeground='#ffffff',
            font=('Segoe UI', 10),
            relief='flat',
            padx=16, pady=4,
            cursor='hand2'
        ).pack(side=LEFT, padx=4)

        # The close button is in the header, as in every other state.

    def _handle_custom_prompt_send(self):
        """Read the entire edit-box content and dispatch it as a freeform prompt."""
        if not self.popup_text:
            return
        # get_plain(), never get(): an embedded ruby frame contributes no
        # characters to get(), so the model would receive text with every
        # annotated word deleted. Editing already flattened the box, but this
        # must stay correct regardless of how the content got there.
        content = self.popup_text.get_plain()
        if self._on_custom_prompt_send:
            self._on_custom_prompt_send(content)

    def _handle_custom_prompt_cancel(self):
        """Cancel custom-prompt mode - restore the normal result popup."""
        self.show(self._current_translation, self._current_target_lang,
                  self._current_trial_info, self._current_original,
                  furigana_text=self._current_furigana,
                  source_lang=self._current_source_lang)

    def _show_replace_preview(self):
        """Transform popup to show replace preview with strikethrough original and translated text."""
        self._linked_paused = True
        self._stop_linked_reading()
        original = self._current_original
        translated = self._current_translation

        if not self.popup_text or not self._btn_frame:
            return

        # --- Update text content ---
        # clear() rather than delete(): it also drops the ruby bookkeeping, so a
        # later get_plain() cannot resurrect words from the previous content.
        self.popup_text.clear()

        # Configure tags
        self.popup_text.tag_configure('strikethrough',
                                         font=('Segoe UI', 11, 'overstrike'),
                                         foreground='#888888')
        self.popup_text.tag_configure('arrow',
                                         font=('Segoe UI', 11),
                                         foreground='#666666')
        self.popup_text.tag_configure('translated',
                                         font=('Segoe UI', 11),
                                         foreground='#4ec9b0')

        # Insert: strikethrough original → translated.
        # The original stays plain: it is being discarded, and Tk cannot strike
        # through an embedded frame, so ruby there would render un-struck.
        self.popup_text.insert_plain('1.0', original, 'strikethrough')
        self.popup_text.insert_plain(tk.END, '\n\n→\n\n', 'arrow')
        insert_output(
            self.popup_text, tk.END, translated,
            lang_hint=self._ruby_hint(self._current_target_lang, self._is_grammar,
                                      self._current_original, self._current_source_lang),
            enabled=self._ruby_enabled(), tags='translated', kanji_fg='#4ec9b0')

        self.popup_text.config(state='disabled')

        # --- Replace button bar ---
        for widget in self._btn_frame.winfo_children():
            widget.destroy()

        # Agree button (green - confirms replace)
        tk.Button(
            self._btn_frame,
            text=f"{CHECK_GLYPH} Agree",
            command=self._handle_replace_agree,
            autostyle=False,
            bg='#198754',
            fg='#ffffff',
            activebackground='#157347',
            activeforeground='#ffffff',
            font=('Segoe UI', 10, 'bold'),
            relief='flat',
            padx=16, pady=4,
            cursor='hand2'
        ).pack(side=LEFT)

        # Cancel button (grey - cancels replace)
        tk.Button(
            self._btn_frame,
            text=f"{CROSS_GLYPH} Cancel",
            command=self._handle_replace_cancel,
            autostyle=False,
            bg='#6c757d',
            fg='#ffffff',
            activebackground='#5a6268',
            activeforeground='#ffffff',
            font=('Segoe UI', 10),
            relief='flat',
            padx=16, pady=4,
            cursor='hand2'
        ).pack(side=LEFT, padx=4)

        # The close button stays in the header. The bar's icons are gone, and so are
        # their tooltips.
        for tip in self._tooltips:
            tip.hide()
        self._tooltips = []

        # --- Fit the box to the preview: measured, the popup's corner kept ---
        # Before step 2 has run (the popup not yet shown), step 2 measures this content.
        if self.popup is not None and self._layout is not None and self._layout['done']:
            self._fit_boxes(reposition=False, size=self._user_size)

    def _handle_replace_agree(self):
        """User confirmed replace - execute the actual copy+paste."""
        if self._on_copy_and_replace:
            self._on_copy_and_replace()

    def _handle_replace_cancel(self):
        """User cancelled replace - close popup, original text unchanged."""
        self.close()

    def _handle_open_replace_settings(self):
        """Show dropdown menu with Replace settings options."""
        menu = tk.Menu(self.root, tearoff=0,
                       bg='#2b2b2b', fg='#ffffff',
                       activebackground='#495057', activeforeground='#ffffff',
                       font=('Segoe UI', 10), relief='flat', bd=1)
        menu.add_command(
            label="\u2699 Hotkey Settings",
            command=self._goto_hotkey_settings
        )
        # Position menu below the gear button
        if self._replace_gear_btn:
            x = self._replace_gear_btn.winfo_rootx()
            y = self._replace_gear_btn.winfo_rooty() + self._replace_gear_btn.winfo_height()
            menu.post(x, y)

    def _goto_hotkey_settings(self):
        """Navigate to Hotkeys tab in Settings."""
        self.close()
        if self._on_open_settings_hotkeys_tab:
            self._on_open_settings_hotkeys_tab()

    def _handle_open_translator(self):
        """Handle open translator button click.

        The callback closes this popup itself (it has to: the main window is
        positioned over it), so there is nothing to close here.
        """
        if self._on_open_translator:
            self._on_open_translator()

    def _handle_open_settings(self):
        """Handle open settings button click (from error state)."""
        self.close()
        if self._on_open_settings:
            self._on_open_settings()

    def set_copy_button_text(self, text: str):
        """Set copy button text (e.g., for 'Copied!' feedback)."""
        if self.popup_copy_btn:
            try:
                self.popup_copy_btn.configure(text=text)
            except tk.TclError:
                pass

    def set_replace_button_text(self, text: str):
        """Set replace button text (e.g., for 'Replaced!' feedback)."""
        if self.popup_replace_btn:
            try:
                self.popup_replace_btn.configure(text=text)
            except tk.TclError:
                pass

    def _update_dict_button_state(self):
        """Update Dictionary button state based on NLP availability.

        Button keeps same visual appearance (reddish-brown color) whether
        enabled or disabled. Only interaction changes.
        Note: We don't use state='disabled' because it forces grey color.
        Instead, we track state manually and block clicks in handler.
        """
        if not self.popup_dict_btn:
            return

        self._dict_btn_enabled = nlp_manager.is_any_installed()

        try:
            if self._dict_btn_enabled:
                self.popup_dict_btn.configure(cursor='hand2')
            else:
                self.popup_dict_btn.configure(cursor='arrow')
            # Unbind any previous hover handlers
            self.popup_dict_btn.unbind('<Enter>')
            self.popup_dict_btn.unbind('<Leave>')
        except tk.TclError:
            pass  # Widget destroyed

    def _open_dictionary_popup(self):
        """Open Dictionary mode on the popup's text, beside the popup.

        Opens as ADDITIONAL window - does NOT close the quick translate popup.
        The flow itself is DictionaryPopup's, shared with the main window's
        Dictionary button (DEFERRED D13 - this used to be a second copy of it).
        """
        # Use original text if available, otherwise fall back to translation
        text_to_analyze = self._current_original if self._current_original else self._current_translation
        if not text_to_analyze or not self._on_open_dictionary:
            return
        self._on_open_dictionary(text_to_analyze, self._current_target_lang, self.popup)

    def dismiss(self):
        callback = getattr(self, '_on_dismiss', None)
        if callback:
            callback()
        self.close()

    def close(self):
        job = getattr(self, '_loading_job', None)
        if job:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass
        self._loading_job = None
        """Close the popup."""
        self._stop_linked_reading()
        self._unbind_linked_setting()
        self.popup_linked_btn = None
        self._linked_status = None
        self._linked_tooltip = None
        # Stop loading animation
        self._loading_animation_running = False
        self._loading_label = None
        self._loading_start_time = 0

        # Clean up dictionary mode first
        if self._dict_frame:
            self._dict_frame.destroy()
            self._dict_frame = None
        self._dict_mode_active = False

        for tip in self._tooltips:
            tip.hide()
        self._tooltips = []
        self._cancel_grip_preview()
        self._hide_grip_outline()

        if self.popup:
            try:
                if self.popup.winfo_exists():
                    self.popup.destroy()
            except tk.TclError:
                pass
            self.popup = None
            self.popup_text = None
            self.popup_furigana = None
            self.popup_attribution = None
            self.popup_copy_btn = None
            self.popup_replace_btn = None
            self._replace_gear_btn = None
            self.popup_dict_btn = None
            self.popup_source_chooser = None
            self._btn_frame = None
            self._main_frame = None
            self.popup_close_btn = None
            self.popup_open_btn = None
            self.popup_retranslate_btn = None
            self.popup_custom_prompt_btn = None
            self.popup_original_toggle = None
            self._original_header = None
            self._original_holder = None
            self._original_scrollbar = None
            self._text_holder = None
            self._text_scrollbar = None
            self._trial_frame = None
            self._grip = None
        self._layout = None
        self._expanded_restore = None
        self._grip_start = None
        self._user_size = None
        self._user_rect = None

    @property
    def is_open(self) -> bool:
        """Check if popup is currently open."""
        return self.popup is not None

    def stop_dictionary_animation(self):
        """Stop the dictionary lookup animation if running."""
        if self._dict_popup_frame:
            try:
                self._dict_popup_frame.stop_lookup_animation()
            except Exception:
                pass  # Frame might be destroyed

    def show_dictionary_result(self, result: str, target_lang: str, trial_info: dict = None,
                               looked_up_words: list = None, source_lang: str = None):
        """Show dictionary lookup result in a SEPARATE window.

        This creates an independent window flagged as 'Dictionary' result,
        separate from the quick translate popup.
        Both can appear simultaneously.

        Args:
            result: The dictionary lookup result text
            target_lang: The target language
            trial_info: Optional trial mode info dict for title bar display
            looked_up_words: List of words that were looked up (for highlighting)
            source_lang: The source language the lookup stated, or None. It
                decides the readings over the model's own field 2 and is named
                in the title.
        """
        # Stop lookup animation first
        self.stop_dictionary_animation()

        # Align dictionary fields for clean column display
        display_text = _align_dictionary_text(result)

        # Decide furigana and word highlighting up front: the window is sized
        # before the widget exists, and an annotated word can no longer be found
        # by Text.search() afterwards (an embedded window has no characters).
        runs = split_dictionary_text(display_text, target_lang, looked_up_words,
                                     HIGHLIGHT_COLORS,
                                     annotate=self._ruby_enabled(),
                                     source_lang=source_lang)

        # Calculate size based on result text (MIN_HEIGHT already in calculate_size).
        # This window renders in DICT_RESULT_FONT and has far less chrome than the
        # popup, so it must say so - measuring it as a popup reserved 139px of empty
        # space on a 12-line result and 199px on a 24-line one. There is no title-bar
        # compensation here: geometry() sets the client area, so the title bar is
        # already outside the number.
        width, height = self.calculate_size(display_text, base_font=DICT_RESULT_FONT,
                                            vertical_padding=DICT_RESULT_CHROME_PX)
        height += overhead_px(runs, width - HORIZONTAL_PADDING,
                              base_font=DICT_RESULT_FONT, line_spacing=0)

        # Create SEPARATE dictionary result window
        dict_result = tk.Toplevel(self.root)

        # Title: the language pair when the source is known, with the trial quota
        languages = f"{source_lang} → {target_lang}" if source_lang else f"{target_lang}"
        if trial_info and trial_info.get('is_trial'):
            remaining = trial_info.get('remaining', 0)
            daily_limit = trial_info.get('daily_limit', 50)
            dict_result.title(f"Dictionary - {languages} ({remaining}/{daily_limit})")
        else:
            dict_result.title(f"Dictionary - {languages}")
        dict_result.configure(bg='#2b2b2b')
        dict_result.attributes('-topmost', True)
        dict_result.after(100, lambda: dict_result.attributes('-topmost', False) if dict_result.winfo_exists() else None)

        # Get work area (excludes taskbar) for proper positioning
        work_area = get_monitor_work_area(self._last_mouse_x, self._last_mouse_y)
        if work_area:
            work_left, work_top, work_right, work_bottom = work_area
        else:
            # Fallback
            work_left, work_top = 0, 0
            work_right = self.root.winfo_screenwidth()
            work_bottom = self.root.winfo_screenheight() - 50

        # Position offset from existing popup or mouse
        if self.popup and self.popup.winfo_exists():
            popup_x = self.popup.winfo_x()
            popup_y = self.popup.winfo_y()
            x = popup_x + 50  # Offset to the right
            y = popup_y + 50  # Offset down
        else:
            x = self._last_mouse_x + 30
            y = self._last_mouse_y + 50

        # Ensure within work area (respects taskbar)
        margin = 10
        if x + width > work_right - margin:
            x = work_right - width - margin
        if x < work_left + margin:
            x = work_left + margin

        if y + height > work_bottom - margin:
            y = work_bottom - height - margin
            # Reduce height if still too tall
            max_height = work_bottom - work_top - 2 * margin
            if height > max_height:
                height = max_height
                y = work_top + margin

        dict_result.geometry(f"{width}x{height}+{x}+{y}")

        # Apply dark title bar (Windows 10/11)
        dict_result.update_idletasks()
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(dict_result.winfo_id())
            if not hwnd:
                hwnd = dict_result.winfo_id()
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

        # Main frame
        main_frame = ttk.Frame(dict_result, padding=15)
        main_frame.pack(fill=BOTH, expand=True)

        # Button frame at bottom
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(side=BOTTOM, fill=X, pady=(12, 0))

        # Copy button
        def copy_result():
            import pyperclip
            pyperclip.copy(result)
            copy_btn.configure(text="Copied!")
            dict_result.after(1000, lambda: copy_btn.configure(text="Copy") if dict_result.winfo_exists() else None)

        copy_btn_kwargs = {"text": "Copy", "command": copy_result, "width": 8}
        if HAS_TTKBOOTSTRAP:
            copy_btn_kwargs["bootstyle"] = "primary"
        copy_btn = ttk.Button(btn_frame, **copy_btn_kwargs)
        copy_btn.pack(side=LEFT)

        # Close button
        close_btn_kwargs = {"text": "✕", "command": dict_result.destroy, "width": 3}
        if HAS_TTKBOOTSTRAP:
            close_btn_kwargs["bootstyle"] = "secondary"
        ttk.Button(btn_frame, **close_btn_kwargs).pack(side=RIGHT)

        # Result text with monospace font for aligned columns
        try:
            ui_font = font.Font(family=DICT_RESULT_FONT[0], size=DICT_RESULT_FONT[1])
            base_line_height = ui_font.metrics("linespace")
            avg_char_width = ui_font.measure("m")
        except tk.TclError:
            base_line_height = 18
            avg_char_width = 8

        LINE_HEIGHT = int(base_line_height)
        text_height = max(1, (height - DICT_RESULT_CHROME_PX) // LINE_HEIGHT)
        text_width = max(30, width // avg_char_width)

        result_text = RubyText(main_frame, wrap=tk.WORD,
                               bg='#2b2b2b', base_fg='#ffffff',
                               kanji_fg='#ffffff',
                               base_font=DICT_RESULT_FONT, relief='flat',
                               spacing1=0, spacing3=0, cursor='xterm',
                               width=text_width, height=text_height,
                               borderwidth=0, highlightthickness=0)

        # One pass: each run already knows its reading and its highlight colour,
        # so a colour-coded word keeps its colour even when annotated.
        bold_font = (DICT_RESULT_FONT[0], DICT_RESULT_FONT[1], 'bold')
        for run in runs:
            tag = None
            if run.color:
                tag = f"lookup_{run.color.lstrip('#')}"
                result_text.tag_configure(tag, foreground=run.color,
                                          font=bold_font)
            if run.ruby:
                result_text.insert_segments(tk.END,
                                           (RubySegment(run.base, run.ruby),),
                                           tag, kanji_fg=run.color)
            else:
                result_text.insert_plain(tk.END, run.base, tag)

        result_text.config(state='disabled')
        result_text.pack(side=TOP, fill=BOTH, expand=True)
        # RubyText binds the wheel itself, including over the ruby frames that
        # would otherwise swallow the event.

        # Close on Escape
        dict_result.bind('<Escape>', lambda e: dict_result.destroy())
