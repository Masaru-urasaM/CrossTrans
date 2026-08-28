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
from tkinter import BOTH, X, LEFT, RIGHT, TOP, BOTTOM
from tkinter import font
from typing import Tuple, Optional, Callable

try:
    import ttkbootstrap as ttk
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.core.furigana import RubySegment
from src.core.nlp_manager import nlp_manager
from src.ui.dictionary_render import overhead_px, split_dictionary_text
from src.ui.ruby_text import (RubyText, estimate_notation_px,
                              estimate_ruby_overhead_px, insert_output)
from src.ui.toast import ToastManager

# Popup padding - SINGLE SOURCE OF TRUTH, shared by calculate_size() and the
# furigana height estimate (both need the same wrap width).
HORIZONTAL_PADDING = 50  # frame(30) + scrollbar(20)

# Height taken by the rule drawn between the furigana block and the
# translation: 1px line plus its 8px padding above and below.
FURIGANA_SEPARATOR_PX = 17

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
        self.popup_copy_btn: Optional[ttk.Button] = None
        self.popup_dict_btn: Optional[ttk.Button] = None
        self.toast = ToastManager(root)  # For shake notifications

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
        self._on_open_settings_dictionary_tab: Optional[Callable[[], None]] = None
        self._on_dictionary_lookup: Optional[Callable[[list, str], None]] = None
        self.popup_replace_btn: Optional[tk.Button] = None
        self.popup_retranslate_btn: Optional[tk.Button] = None
        self.popup_custom_prompt_btn: Optional[tk.Button] = None
        self._replace_gear_btn: Optional[tk.Button] = None
        self._btn_frame: Optional[ttk.Frame] = None
        self._on_open_settings_hotkeys_tab: Optional[Callable[[], None]] = None

    def configure_callbacks(self,
                            on_copy: Optional[Callable[[], None]] = None,
                            on_copy_and_replace: Optional[Callable[[], None]] = None,
                            on_open_translator: Optional[Callable[[], None]] = None,
                            on_open_settings: Optional[Callable[[], None]] = None,
                            on_open_settings_dictionary_tab: Optional[Callable[[], None]] = None,
                            on_dictionary_lookup: Optional[Callable[[list, str], None]] = None,
                            on_open_settings_hotkeys_tab: Optional[Callable[[], None]] = None,
                            on_re_translate: Optional[Callable[[], None]] = None,
                            on_custom_prompt_send: Optional[Callable[[str], None]] = None):
        """Configure callback functions for quick translate actions.

        Args:
            on_copy: Called when user clicks Copy button
            on_copy_and_replace: Called when user clicks Replace button (copy + paste into source app)
            on_open_translator: Called when user clicks Open Translator
            on_open_settings: Called when user clicks Open Settings (error state)
            on_open_settings_dictionary_tab: Called to open Settings directly to Dictionary tab
            on_dictionary_lookup: Called when user performs dictionary lookup (words_list, target_lang)
            on_open_settings_hotkeys_tab: Called to open Settings directly to Hotkeys tab
            on_re_translate: Called when user clicks Re-translate button (force fresh API call)
            on_custom_prompt_send: Called with the edit-box content when user clicks Send in custom-prompt mode
        """
        self._on_copy = on_copy
        self._on_copy_and_replace = on_copy_and_replace
        self._on_open_translator = on_open_translator
        self._on_open_settings = on_open_settings
        self._on_open_settings_dictionary_tab = on_open_settings_dictionary_tab
        self._on_dictionary_lookup = on_dictionary_lookup
        self._on_open_settings_hotkeys_tab = on_open_settings_hotkeys_tab
        self._on_re_translate = on_re_translate
        self._on_custom_prompt_send = on_custom_prompt_send

    def _apply_noactivate(self):
        """Apply WS_EX_NOACTIVATE to popup window so it doesn't steal focus from source app."""
        if not self.popup:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.popup.winfo_id())
            if not hwnd:
                hwnd = self.popup.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_NOACTIVATE)
        except Exception:
            pass  # Non-critical - popup still works, just may steal focus

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
        self._loading_label.pack()

        self.popup.geometry(f"+{self._last_mouse_x + 15}+{self._last_mouse_y + 20}")

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

        # Safety timeout: auto-close after 15s to prevent infinite animation
        LOADING_TIMEOUT_SECONDS = 15
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
                self.popup.after(400, self._animate_loading)

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
             furigana_text: str = None, is_grammar: bool = False):
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
        """
        self.close()

        # Check if this is an error message
        is_error = translated.startswith("Error:") or translated.startswith("No text")

        # Calculate size (MIN_HEIGHT already handled in calculate_size)
        width, height = self.calculate_size(translated)

        # Add extra height for trial mode header
        if trial_info and trial_info.get('is_trial') and not is_error:
            height += 35  # Extra space for trial header row

        # Add extra height for the furigana section. Measured from real font
        # metrics at the wrap width the block will actually get: an annotated
        # display row is far taller than a plain one (47px vs 28px on Tk 8.6),
        # so a per-paragraph guess clips multi-line Japanese.
        if furigana_text and not is_error:
            height += estimate_notation_px(furigana_text, width - HORIZONTAL_PADDING)
            height += FURIGANA_SEPARATOR_PX

        # Same for the translation box, which now carries readings too.
        if not is_error and self._ruby_enabled():
            height += estimate_ruby_overhead_px(
                translated, width - HORIZONTAL_PADDING,
                lang_hint=self._ruby_hint(target_lang, is_grammar),
                base_font=('Segoe UI', 11), line_spacing=0)

        # Create popup window
        self.popup = tk.Toplevel(self.root)
        self.popup.overrideredirect(True)
        self._apply_noactivate()

        def on_popup_close():
            self.close()

        self.popup.protocol("WM_DELETE_WINDOW", on_popup_close)

        # Color based on error status
        if is_error:
            self.popup.configure(bg='#3d1f1f')
        else:
            self.popup.configure(bg='#2b2b2b')

        # Set topmost initially, then remove so it can go behind other windows
        self.popup.attributes('-topmost', True)
        self.popup.after(100, lambda: self.popup.attributes('-topmost', False) if self.popup else None)

        # Main frame
        main_frame = ttk.Frame(self.popup, padding=15)
        main_frame.pack(fill=BOTH, expand=True)
        self._main_frame = main_frame

        # Store original and translation for dictionary mode
        self._current_original = original
        self._current_translation = translated
        self._current_target_lang = target_lang
        self._current_trial_info = trial_info  # Store for dictionary title bar
        self._current_furigana = furigana_text  # Store for restoring after custom-prompt cancel
        self._is_grammar = is_grammar  # Grammar-fix result: hide translation-only buttons

        # Bind dragging events
        main_frame.bind("<Button-1>", self._start_move)
        main_frame.bind("<B1-Motion>", self._on_drag)

        # Trial mode warning header (if applicable)
        if trial_info and trial_info.get('is_trial') and not is_error:
            trial_frame = ttk.Frame(main_frame)
            trial_frame.pack(side=TOP, fill=X, pady=(0, 8))

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

            guide_btn_kwargs = {"text": "Get Free API Key", "command": open_guide, "width": 14}
            if HAS_TTKBOOTSTRAP:
                guide_btn_kwargs["bootstyle"] = "link"
            ttk.Button(trial_frame, **guide_btn_kwargs).pack(side=RIGHT)

        # Button frame (Create FIRST to ensure it stays at BOTTOM)
        self._btn_frame = ttk.Frame(main_frame)
        self._btn_frame.pack(side=BOTTOM, fill=X, pady=(12, 0))

        self._btn_frame.bind("<Button-1>", self._start_move)
        self._btn_frame.bind("<B1-Motion>", self._on_drag)

        if not is_error:
            # Copy button
            self.popup_copy_btn = tk.Button(
                self._btn_frame,
                text="Copy",
                command=self._handle_copy,
                autostyle=False,
                bg='#0d6efd',  # Bootstrap primary blue
                fg='#ffffff',
                activebackground='#0b5ed7',
                activeforeground='#ffffff',
                font=('Segoe UI', 10),
                relief='flat',
                padx=12, pady=4,
                cursor='hand2'
            )
            self.popup_copy_btn.pack(side=LEFT)

            # Replace button (copy translated text + paste into source app)
            self.popup_replace_btn = tk.Button(
                self._btn_frame,
                text="Replace",
                command=self._handle_copy_and_replace,
                autostyle=False,
                bg='#6f42c1',  # Bootstrap purple/indigo
                fg='#ffffff',
                activebackground='#5a32a3',
                activeforeground='#ffffff',
                font=('Segoe UI', 10),
                relief='flat',
                padx=12, pady=4,
                cursor='hand2'
            )
            self.popup_replace_btn.pack(side=LEFT, padx=(4, 0))

            # Replace settings gear icon (opens Hotkeys tab in Settings)
            self._replace_gear_btn = tk.Button(
                self._btn_frame,
                text="\u2699",  # ⚙ gear icon
                command=self._handle_open_replace_settings,
                autostyle=False,
                bg='#495057',       # Dark grey (subtle)
                fg='#ffffff',
                activebackground='#5a6268',
                activeforeground='#ffffff',
                font=('Segoe UI', 10),
                relief='flat',
                padx=4, pady=4,
                cursor='hand2'
            )
            self._replace_gear_btn.pack(side=LEFT, padx=(0, 4))

            # Re-translate + Dictionary are translation-only — skip them for grammar results
            # (Re-translate would "translate to Grammar"; Dictionary expects a target language).
            if not is_grammar:
                # Re-translate button - force a fresh API call, bypassing the cache
                self.popup_retranslate_btn = tk.Button(
                    self._btn_frame,
                    text="Re-translate",
                    command=self._handle_re_translate,
                    autostyle=False,
                    bg='#fd7e14',  # Bootstrap orange (signals redo/refresh)
                    fg='#ffffff',
                    activebackground='#e8590c',
                    activeforeground='#ffffff',
                    font=('Segoe UI', 10),
                    relief='flat',
                    padx=12, pady=4,
                    cursor='hand2'
                )
                self.popup_retranslate_btn.pack(side=LEFT, padx=4)

                # Dictionary button - opens popup for original text
                self.popup_dict_btn = tk.Button(
                    self._btn_frame,
                    text="Dictionary",
                    command=self._open_dictionary_popup,
                    autostyle=False,
                    bg=DICT_BUTTON_COLOR,
                    fg='#ffffff',
                    activebackground=DICT_BUTTON_ACTIVE,
                    activeforeground='#ffffff',
                    font=('Segoe UI', 10),
                    relief='flat',
                    padx=12, pady=4,
                    cursor='hand2'
                )
                self.popup_dict_btn.pack(side=LEFT, padx=4)

                # Update Dictionary button state based on NLP availability
                self._update_dict_button_state()

            # Open Translator button
            self.popup_open_btn = tk.Button(
                self._btn_frame,
                text="Open Translator",
                command=self._handle_open_translator,
                autostyle=False,
                bg='#198754',  # Bootstrap success green
                fg='#ffffff',
                activebackground='#157347',
                activeforeground='#ffffff',
                font=('Segoe UI', 10),
                relief='flat',
                padx=12, pady=4,
                cursor='hand2'
            )
            self.popup_open_btn.pack(side=LEFT, padx=4)

            # Custom Prompt button - make the box editable and ask the AI a freeform question
            # (translation-only; skipped for grammar results)
            if not is_grammar:
                self.popup_custom_prompt_btn = tk.Button(
                    self._btn_frame,
                    text="Custom Prompt",
                    command=self._handle_custom_prompt,
                    autostyle=False,
                    bg='#20c997',  # Bootstrap teal
                    fg='#ffffff',
                    activebackground='#1aa179',
                    activeforeground='#ffffff',
                    font=('Segoe UI', 10),
                    relief='flat',
                    padx=12, pady=4,
                    cursor='hand2'
                )
                self.popup_custom_prompt_btn.pack(side=LEFT, padx=4)
        else:
            # For errors, show "API Settings" button (opens Settings → API Key tab)
            settings_btn_kwargs = {"text": "API Settings", "command": self._handle_open_settings, "width": 14}
            if HAS_TTKBOOTSTRAP:
                settings_btn_kwargs["bootstyle"] = "warning"
            ttk.Button(self._btn_frame, **settings_btn_kwargs).pack(side=LEFT, padx=8)

        # Close button
        close_btn_kwargs = {"text": "\u2715", "command": self.close, "width": 3}
        if HAS_TTKBOOTSTRAP:
            close_btn_kwargs["bootstyle"] = "secondary"
        ttk.Button(self._btn_frame, **close_btn_kwargs).pack(side=RIGHT)

        # Furigana section (if available)
        if furigana_text and not is_error:
            self._render_furigana(main_frame, furigana_text,
                                  width - HORIZONTAL_PADDING)
            # Separator between furigana and translation
            sep_frame = tk.Frame(main_frame, bg='#555555', height=1)
            sep_frame.pack(fill=X, pady=(8, 8))

        # Translation text - USE FONT METRICS for correct sizing on all machines
        text_fg = '#ff6b6b' if is_error else '#ffffff'

        # SAME constants as calculate_size() for consistency
        try:
            ui_font = font.Font(family='Segoe UI', size=11)
            base_line_height = ui_font.metrics("linespace")
            avg_char_width = ui_font.measure("m")
        except tk.TclError:
            base_line_height = 20
            avg_char_width = 8

        VERTICAL_PADDING = 100  # Must match calculate_size()
        LINE_HEIGHT = int(base_line_height)

        text_height = max(1, (height - VERTICAL_PADDING) // LINE_HEIGHT)
        text_width = max(30, width // avg_char_width)

        self.popup_text = RubyText(main_frame, wrap=tk.WORD,
                                    bg='#3d1f1f' if is_error else '#2b2b2b',
                                    base_fg=text_fg, kanji_fg=text_fg,
                                    base_font=('Segoe UI', 11),
                                    spacing1=0, spacing3=0, cursor='xterm',
                                    width=text_width, height=text_height)
        # Readings on the translation itself, not just the source block. The
        # target language is a reliable hint here, so a kanji-only translation
        # ("東京都") annotates where the source block cannot.
        # Error text is excluded, matching the height budget above: a diagnostic
        # needs no readings, and annotating it would overflow the box.
        insert_output(self.popup_text, '1.0', translated,
                      lang_hint=self._ruby_hint(target_lang, is_grammar),
                      enabled=self._ruby_enabled() and not is_error)
        self.popup_text.config(state='disabled')
        self.popup_text.pack(side=TOP, fill=BOTH, expand=True)

        # Grow the box for the taller annotated rows, but never below the row
        # count calculate_size() derived from word wrap.
        if self.popup_text.has_ruby:
            self.popup_text.fit_height(width - HORIZONTAL_PADDING,
                                       min_rows=text_height)

        # Mouse wheel scroll is bound by RubyText, including over ruby frames

        # Position near mouse
        x, y, height = self._calculate_position(width, height)
        self.popup.geometry(f"{width}x{height}+{int(x)}+{int(y)}")

        # Bindings
        self.popup.bind('<Escape>', lambda e: on_popup_close())

    def _ruby_enabled(self) -> bool:
        """Whether popup output should carry readings.

        The Settings toggle now governs every annotated surface, because the
        popup annotates at render time instead of relying on the pipeline
        having shipped a notation string.
        """
        return bool(self.config and self.config.get_furigana_enabled())

    @staticmethod
    def _ruby_hint(target_lang: str, is_grammar: bool = False) -> Optional[str]:
        """Language hint for annotating output text, or None when unknown.

        The target language is authoritative for a translation. A grammar fix
        returns the *source* language, which nobody in this class knows, so it
        gets no hint - Japanese with kana still annotates on its own evidence,
        and kanji-only output stays plain rather than guessing.
        """
        return None if is_grammar else target_lang

    def _render_furigana(self, parent, furigana_text: str, available_px: int):
        """Render the read-only furigana guide above the translation.

        RubyText owns the ruby layout, the plain-text readback and the wheel
        handling; the notation escapes are honored, so source text containing
        a literal "{a|b}" shows as itself instead of a fake reading.

        Args:
            parent: Parent frame to pack into
            furigana_text: Text with {kanji|reading} notation
            available_px: Content width the block wraps at, used for sizing
        """
        self.popup_furigana = RubyText(parent, bg='#2b2b2b')
        self.popup_furigana.insert_notation(tk.END, furigana_text)
        self.popup_furigana.config(state='disabled')
        self.popup_furigana.fit_height(available_px)
        self.popup_furigana.pack(side=TOP, fill=BOTH, expand=True, pady=(0, 0))

    def _calculate_position(self, width: int, height: int) -> Tuple[int, int, int]:
        """Calculate popup position and adjust height if needed.

        Supports multi-monitor setups by detecting which monitor the mouse is on
        and positioning the popup within that monitor's work area.

        Args:
            width: Popup width
            height: Popup height

        Returns:
            Tuple of (x, y, adjusted_height)
        """
        mouse_x = self._last_mouse_x
        mouse_y = self._last_mouse_y

        # Get work area of the monitor containing the mouse cursor
        work_area = get_monitor_work_area(mouse_x, mouse_y)

        if work_area:
            # Multi-monitor: use actual monitor bounds
            mon_left, mon_top, mon_right, mon_bottom = work_area
        else:
            # Fallback: use primary monitor (legacy behavior)
            mon_left = 0
            mon_top = 0
            mon_right = self.root.winfo_screenwidth()
            mon_bottom = self.root.winfo_screenheight() - 50  # taskbar margin

        # Safe margins within the monitor
        margin = 10
        safe_left = mon_left + margin
        safe_top = mon_top + margin
        safe_right = mon_right - margin
        safe_bottom = mon_bottom - margin

        # Calculate X position
        x = mouse_x + 15
        if x + width > safe_right:
            x = mouse_x - width - 15
        x = max(safe_left, min(x, safe_right - width))

        # Calculate Y position and adjust height
        y = mouse_y + 20
        max_safe_height = safe_bottom - safe_top

        if height >= max_safe_height:
            height = max_safe_height
            y = safe_top
        else:
            space_below = safe_bottom - y

            if height <= space_below:
                pass  # Fits below perfectly
            else:
                # Try above
                y_above = mouse_y - height - 20
                if y_above >= safe_top:
                    y = y_above
                else:
                    # Pin to bottom of safe area
                    y = safe_bottom - height
                    if y < safe_top:
                        y = safe_top
                        height = max_safe_height

        return x, y, height

    def _start_move(self, event):
        """Record start position for dragging."""
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
        if not self.popup:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.popup.winfo_id())
            if not hwnd:
                hwnd = self.popup.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style & ~WS_EX_NOACTIVATE)
        except Exception:
            pass  # Non-critical - editing still works in most cases

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

        close_btn_kwargs = {"text": "✕", "command": self.close, "width": 3}
        if HAS_TTKBOOTSTRAP:
            close_btn_kwargs["bootstyle"] = "secondary"
        ttk.Button(self._btn_frame, **close_btn_kwargs).pack(side=RIGHT)

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
                  furigana_text=self._current_furigana)

    def _show_replace_preview(self):
        """Transform popup to show replace preview with strikethrough original and translated text."""
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
            lang_hint=self._ruby_hint(self._current_target_lang, self._is_grammar),
            enabled=self._ruby_enabled(), tags='translated', kanji_fg='#4ec9b0')

        self.popup_text.config(state='disabled')

        # --- Replace button bar ---
        for widget in self._btn_frame.winfo_children():
            widget.destroy()

        # Agree button (green - confirms replace)
        tk.Button(
            self._btn_frame,
            text="\u2713 Agree",
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
            text="\u2717 Cancel",
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

        # Close button (X) - still available
        close_btn_kwargs = {"text": "\u2715", "command": self.close, "width": 3}
        if HAS_TTKBOOTSTRAP:
            close_btn_kwargs["bootstyle"] = "secondary"
        ttk.Button(self._btn_frame, **close_btn_kwargs).pack(side=RIGHT)

        # --- Resize popup to fit preview content ---
        combined_text = original + '\n\n\u2192\n\n' + translated
        new_width, new_height = self.calculate_size(combined_text)

        # Room for the readings on the translated half, if it has any.
        if self.popup_text.has_ruby:
            new_height += estimate_ruby_overhead_px(
                translated, new_width - HORIZONTAL_PADDING,
                lang_hint=self._ruby_hint(self._current_target_lang, self._is_grammar),
                base_font=('Segoe UI', 11), line_spacing=0)

        if self.popup:
            current_geo = self.popup.geometry()
            parts = current_geo.split('+')
            current_wh = parts[0].split('x')
            final_width = max(int(current_wh[0]), new_width)
            final_height = max(int(current_wh[1]), new_height)

            # Update text widget height
            try:
                ui_font = font.Font(family='Segoe UI', size=11)
                line_height = int(ui_font.metrics("linespace"))
            except tk.TclError:
                line_height = 20
            VERTICAL_PADDING = 100
            new_text_height = max(1, (final_height - VERTICAL_PADDING) // line_height)
            if self.popup_text.has_ruby:
                self.popup_text.fit_height(final_width - HORIZONTAL_PADDING,
                                           min_rows=new_text_height)
            else:
                self.popup_text.config(height=new_text_height)

            # Reposition to stay within screen
            x, y, adjusted_height = self._calculate_position(final_width, final_height)
            self.popup.geometry(f"{final_width}x{adjusted_height}+{int(x)}+{int(y)}")

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
        """Handle open translator button click."""
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
        """Open dictionary popup window with word buttons for original text.

        Opens as ADDITIONAL window - does NOT close the quick translate popup.
        """
        # Check if button is enabled (NLP installed)
        if hasattr(self, '_dict_btn_enabled') and not self._dict_btn_enabled:
            self._show_nlp_required_message()
            return

        # Double-check NLP is installed
        if not nlp_manager.is_any_installed():
            self._show_nlp_required_message()
            return

        # Use original text if available, otherwise fall back to translation
        text_to_analyze = self._current_original if self._current_original else self._current_translation
        if not text_to_analyze:
            return

        # Detect language
        detected_lang, confidence = nlp_manager.detect_language(text_to_analyze)
        CONFIDENCE_THRESHOLD = 0.7

        # Check if detection is confident and NLP is installed for that language
        if confidence >= CONFIDENCE_THRESHOLD and nlp_manager.is_installed(detected_lang):
            # Auto-proceed with detected language
            self._open_dictionary_with_language(text_to_analyze, detected_lang, self._current_trial_info)
        else:
            # Determine if language was detected but not installed
            detected_but_not_installed = (
                confidence >= CONFIDENCE_THRESHOLD and
                detected_lang and
                not nlp_manager.is_installed(detected_lang)
            )
            # Show language selection dialog with context
            self._show_language_selection_dialog(
                text_to_analyze,
                detected_lang if confidence > 0.3 else None,
                detected_but_not_installed=detected_but_not_installed
            )

    def _show_nlp_required_message(self):
        """Show message that NLP pack is required with Install link."""
        msg_popup = tk.Toplevel(self.root)
        msg_popup.title("No Language Pack Installed")
        msg_popup.configure(bg='#2b2b2b')
        msg_popup.attributes('-topmost', True)

        # Center and size - increased for better button visibility
        w, h = 400, 220
        x = self._last_mouse_x - w // 2
        y = self._last_mouse_y - h // 2
        msg_popup.geometry(f"{w}x{h}+{x}+{y}")

        frame = ttk.Frame(msg_popup, padding=20)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text="⚠️ No Language Pack Installed",
                  font=('Segoe UI', 12, 'bold')).pack(pady=(0, 10))
        ttk.Label(frame, text="Dictionary mode requires NLP language packs",
                  font=('Segoe UI', 10)).pack()
        ttk.Label(frame, text="to tokenize text for word selection.",
                  font=('Segoe UI', 10)).pack(pady=(0, 15))

        # Open Settings button (same as main window)
        def open_settings_dict(e=None):
            msg_popup.destroy()
            if self._on_open_settings_dictionary_tab:
                self._on_open_settings_dictionary_tab()
            elif self._on_open_settings:
                self._on_open_settings()
                self.root.after(300, self._try_open_dictionary_tab)

        # Button frame
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=X, pady=(5, 0))

        open_kwargs = {"text": "Open Dictionary Settings", "command": open_settings_dict, "width": 22}
        if HAS_TTKBOOTSTRAP:
            open_kwargs["bootstyle"] = "primary"
        ttk.Button(btn_frame, **open_kwargs).pack(side=LEFT, padx=5)

        close_kwargs = {"text": "Close", "command": msg_popup.destroy, "width": 10}
        if HAS_TTKBOOTSTRAP:
            close_kwargs["bootstyle"] = "secondary"
        ttk.Button(btn_frame, **close_kwargs).pack(side=RIGHT, padx=5)

        msg_popup.bind('<Escape>', lambda e: msg_popup.destroy())
        msg_popup.bind('<Return>', lambda e: open_settings_dict())

    def _show_language_selection_dialog(self, text_to_analyze: str, suggested_lang: str = None,
                                         detected_but_not_installed: bool = False):
        """Show dialog to select source language for dictionary mode.

        Args:
            text_to_analyze: Text to analyze
            suggested_lang: Suggested language from detection
            detected_but_not_installed: True if language was detected but pack not installed
        """
        installed_languages = nlp_manager.get_installed_languages()
        if not installed_languages:
            self._show_nlp_required_message()
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Select Source Language")
        dialog.configure(bg='#2b2b2b')
        dialog.attributes('-topmost', True)
        dialog.lift()
        dialog.focus_force()
        dialog.after(100, lambda: dialog.attributes('-topmost', False) if dialog.winfo_exists() else None)

        # Center on mouse position - taller if showing install prompt
        w = 400
        h = 340 if detected_but_not_installed else 300
        x = self._last_mouse_x - w // 2
        y = self._last_mouse_y - h // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        # Content
        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill=BOTH, expand=True)

        def open_settings_dict():
            dialog.destroy()
            if self._on_open_settings_dictionary_tab:
                self.root.after(50, self._on_open_settings_dictionary_tab)

        if detected_but_not_installed and suggested_lang:
            # Case: Language detected but not installed - show prominent install option
            ttk.Label(frame, text=f"📖 Detected: {suggested_lang}",
                      font=('Segoe UI', 11, 'bold')).pack(pady=(0, 5))

            # Warning that pack not installed
            warning_frame = ttk.Frame(frame)
            warning_frame.pack(fill=X, pady=(0, 10))
            ttk.Label(warning_frame, text=f"⚠️ {suggested_lang} language pack is not installed.",
                      font=('Segoe UI', 10), foreground='#ffaa00').pack(anchor='w')

            # Install button - prominent
            install_frame = ttk.Frame(frame)
            install_frame.pack(fill=X, pady=(0, 10))

            install_btn_kwargs = {
                "text": f"📥 Install {suggested_lang} Pack",
                "command": open_settings_dict,
                "width": 25
            }
            if HAS_TTKBOOTSTRAP:
                install_btn_kwargs["bootstyle"] = "info"
            ttk.Button(install_frame, **install_btn_kwargs).pack(pady=5)

            # Separator
            ttk.Separator(frame, orient='horizontal').pack(fill=X, pady=5)

            # Alternative: select from installed
            ttk.Label(frame, text="Or select from installed languages:",
                      font=('Segoe UI', 10), foreground='#888888').pack(anchor='w', pady=(5, 5))
        else:
            # Case: Cannot detect language - show generic message
            ttk.Label(frame, text="⚠️ Cannot detect language",
                      font=('Segoe UI', 11, 'bold')).pack(pady=(0, 5))

            # Explanation with link to Settings
            explain_frame = ttk.Frame(frame)
            explain_frame.pack(anchor='w', pady=(0, 8))
            ttk.Label(explain_frame, text="Only installed language packs are shown.",
                      font=('Segoe UI', 9), foreground='#888888').pack(side=LEFT, anchor='w')

            link_label = tk.Label(explain_frame, text="Install more →",
                                  font=('Segoe UI', 9, 'underline'), fg='#4da6ff',
                                  bg='#2b2b2b', cursor='hand2')
            link_label.pack(side=LEFT, padx=(5, 0))
            link_label.bind('<Button-1>', lambda e: open_settings_dict())

            ttk.Label(frame, text="Select source language:",
                      font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 5))

        # Combobox for language selection
        lang_var = tk.StringVar()
        lang_combo = ttk.Combobox(frame, textvariable=lang_var, values=installed_languages,
                                  font=('Segoe UI', 10), state='readonly')
        lang_combo.pack(fill=X, pady=(0, 10))

        # Set default selection
        if suggested_lang and suggested_lang in installed_languages:
            lang_var.set(suggested_lang)
        elif installed_languages:
            lang_var.set(installed_languages[0])

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=X)

        def confirm():
            selected = lang_var.get()
            if selected:
                dialog.destroy()
                self.root.after(50, lambda: self._open_dictionary_with_language(
                    text_to_analyze, selected, self._current_trial_info))

        def cancel():
            dialog.destroy()

        confirm_kwargs = {"text": "Confirm", "command": confirm, "width": 10}
        if HAS_TTKBOOTSTRAP:
            confirm_kwargs["bootstyle"] = "primary"
        ttk.Button(btn_frame, **confirm_kwargs).pack(side=LEFT, padx=5)

        cancel_kwargs = {"text": "Cancel", "command": cancel, "width": 10}
        if HAS_TTKBOOTSTRAP:
            cancel_kwargs["bootstyle"] = "secondary"
        ttk.Button(btn_frame, **cancel_kwargs).pack(side=RIGHT, padx=5)

        dialog.bind('<Escape>', lambda e: cancel())
        dialog.bind('<Return>', lambda e: confirm())

    def _open_dictionary_with_language(self, text_to_analyze: str, language: str,
                                        trial_info: dict = None):
        """Open dictionary popup with specified language for NLP tokenization.

        Args:
            text_to_analyze: Original text to analyze
            language: Language for NLP tokenization
            trial_info: Optional trial mode info dict for title bar display
        """
        from src.ui.dictionary_mode import WordButtonFrame

        # Create popup window (ADDITIONAL - not replacing quick translate popup)
        dict_popup = tk.Toplevel(self.root)

        # Get target language for title
        target_lang = self._current_target_lang or "Unknown"

        # Set title with trial quota if in trial mode
        if trial_info and trial_info.get('is_trial'):
            remaining = trial_info.get('remaining', 0)
            daily_limit = trial_info.get('daily_limit', 50)
            dict_popup.title(f"Dictionary ({language} → {target_lang}) - Trial Mode ({remaining}/{daily_limit} left)")
        else:
            dict_popup.title(f"Dictionary ({language} → {target_lang})")
        dict_popup.configure(bg='#2b2b2b')
        dict_popup.attributes('-topmost', True)
        dict_popup.lift()
        dict_popup.focus_force()
        dict_popup.after(100, lambda: dict_popup.attributes('-topmost', False) if dict_popup.winfo_exists() else None)

        # Calculate size and position - offset from popup
        popup_width = 650
        popup_height = 350

        # Get work area (excludes taskbar) for proper positioning
        work_area = get_monitor_work_area(self._last_mouse_x, self._last_mouse_y)
        if work_area:
            work_left, work_top, work_right, work_bottom = work_area
        else:
            # Fallback
            work_left, work_top = 0, 0
            work_right = self.root.winfo_screenwidth()
            work_bottom = self.root.winfo_screenheight() - 50

        # Position below or beside the popup
        if self.popup and self.popup.winfo_exists():
            popup_x = self.popup.winfo_x()
            popup_y = self.popup.winfo_y()
            popup_h = self.popup.winfo_height()
            x = popup_x
            y = popup_y + popup_h + 10  # Below popup
        else:
            x = self._last_mouse_x + 20
            y = self._last_mouse_y + 100

        # Ensure within work area (respects taskbar)
        margin = 10
        if x + popup_width > work_right - margin:
            x = work_right - popup_width - margin
        if x < work_left + margin:
            x = work_left + margin

        if y + popup_height > work_bottom - margin:
            # Try positioning above popup instead
            if self.popup and self.popup.winfo_exists():
                y = self.popup.winfo_y() - popup_height - 10
            if y < work_top + margin:
                # Pin to bottom of work area
                y = work_bottom - popup_height - margin
                # Reduce height if still too tall
                max_height = work_bottom - work_top - 2 * margin
                if popup_height > max_height:
                    popup_height = max_height
                    y = work_top + margin

        dict_popup.geometry(f"{popup_width}x{popup_height}+{x}+{y}")

        # Apply dark title bar (Windows 10/11)
        dict_popup.update_idletasks()
        try:
            hwnd = ctypes.windll.user32.GetParent(dict_popup.winfo_id())
            if not hwnd:
                hwnd = dict_popup.winfo_id()
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value), ctypes.sizeof(value))
        except Exception:
            pass

        # Main frame
        main_frame = ttk.Frame(dict_popup, padding=15)
        main_frame.pack(fill=BOTH, expand=True)

        # Header with language info
        ttk.Label(main_frame, text=f"Select words to look up ({language} NLP):",
                  font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 8))

        # Track expanded state for toggle
        expanded_state = [False]
        original_geometry = [f"{popup_width}x{popup_height}+{x}+{y}"]

        # Expand/Collapse function
        def expand_dictionary():
            if expanded_state[0]:
                # Collapse: restore original size
                dict_popup.geometry(original_geometry[0])
                expanded_state[0] = False
                dict_frame.expand_btn.configure(text="⛶ Expand")
            else:
                # Expand: larger size
                expanded_state[0] = True
                dict_popup.geometry("900x600")
                # Center on work area
                dict_popup.update_idletasks()
                w = dict_popup.winfo_width()
                h = dict_popup.winfo_height()
                cx = work_left + (work_right - work_left - w) // 2
                cy = work_top + (work_bottom - work_top - h) // 2
                dict_popup.geometry(f"{w}x{h}+{cx}+{cy}")
                dict_frame.expand_btn.configure(text="⛶ Collapse")

        # Word button frame with language for NLP tokenization
        def on_lookup(selected_words):
            """Lookup callback receives list of individual words + custom box phrases."""
            all_words = list(selected_words)
            all_words.extend(custom_boxes.get_all_phrases())
            if all_words and self._on_dictionary_lookup:
                self._on_dictionary_lookup(all_words, self._current_target_lang)

        def on_no_selection():
            """Check custom boxes before showing warning."""
            box_phrases = custom_boxes.get_all_phrases()
            if box_phrases and self._on_dictionary_lookup:
                self._on_dictionary_lookup(box_phrases, self._current_target_lang)
            else:
                self.toast.show_warning_with_shake("Please select a word or enter a custom phrase")

        dict_frame = WordButtonFrame(
            main_frame,
            text_to_analyze,
            on_selection_change=lambda t: None,
            on_lookup=on_lookup,
            on_expand=expand_dictionary,
            on_no_selection=on_no_selection,
            language=language,  # Pass language for NLP tokenization
            furigana_enabled=self._ruby_enabled()
        )
        dict_frame.set_exit_callback(dict_popup.destroy)
        dict_frame.pack(fill=BOTH, expand=True)

        # Custom word boxes (between text area and action buttons)
        from src.ui.custom_word_boxes import CustomWordBoxesFrame
        custom_boxes = CustomWordBoxesFrame(
            dict_frame.frame, language=language,
            furigana_enabled=self._ruby_enabled())
        dict_frame.insert_custom_widget(custom_boxes.frame)
        dict_frame.set_drop_target(custom_boxes)

        # Store reference for animation control
        self._dict_popup_frame = dict_frame

        # Close on Escape
        dict_popup.bind('<Escape>', lambda e: dict_popup.destroy())

    def _try_open_dictionary_tab(self):
        """Try to open Dictionary tab in Settings window.

        This is called after settings window opens to switch to Dictionary tab.
        """
        # Find settings window and call open_dictionary_tab
        for widget in self.root.winfo_children():
            if isinstance(widget, tk.Toplevel) and 'Settings' in widget.title():
                # Found settings window, look for notebook
                for child in widget.winfo_children():
                    if hasattr(child, 'winfo_children'):
                        for subchild in child.winfo_children():
                            if hasattr(subchild, 'select') and hasattr(subchild, 'tab'):
                                # This is a notebook
                                for i in range(subchild.index('end')):
                                    if 'Dictionary' in subchild.tab(i, 'text'):
                                        subchild.select(i)
                                        return
                break

    def close(self):
        """Close the popup."""
        # Stop loading animation
        self._loading_animation_running = False
        self._loading_label = None
        self._loading_start_time = 0

        # Clean up dictionary mode first
        if self._dict_frame:
            self._dict_frame.destroy()
            self._dict_frame = None
        self._dict_mode_active = False

        if self.popup:
            try:
                if self.popup.winfo_exists():
                    self.popup.destroy()
            except tk.TclError:
                pass
            self.popup = None
            self.popup_text = None
            self.popup_furigana = None
            self.popup_copy_btn = None
            self.popup_replace_btn = None
            self._replace_gear_btn = None
            self.popup_dict_btn = None
            self._btn_frame = None
            self._main_frame = None

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
                               looked_up_words: list = None):
        """Show dictionary lookup result in a SEPARATE window.

        This creates an independent window flagged as 'Dictionary' result,
        separate from the quick translate popup.
        Both can appear simultaneously.

        Args:
            result: The dictionary lookup result text
            target_lang: The target language
            trial_info: Optional trial mode info dict for title bar display
            looked_up_words: List of words that were looked up (for highlighting)
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
                                     annotate=self._ruby_enabled())

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

        # Set title with trial quota if in trial mode
        if trial_info and trial_info.get('is_trial'):
            remaining = trial_info.get('remaining', 0)
            daily_limit = trial_info.get('daily_limit', 50)
            dict_result.title(f"Dictionary - {target_lang} ({remaining}/{daily_limit})")
        else:
            dict_result.title(f"Dictionary - {target_lang}")
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
