"""
Tooltip Manager for CrossTrans.
Handles translation result tooltips and loading indicators.
"""
import ctypes
import math
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

from src.core.nlp_manager import nlp_manager
from src.ui.toast import ToastManager

# Dictionary button colors (dark red) - consistent with dictionary_mode.py
DICT_BUTTON_COLOR = "#822312"  # Dark red (main color)
DICT_BUTTON_ACTIVE = '#9A3322'  # Lighter red (hover/active)


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


class TooltipManager:
    """Manages tooltip display for translation results."""

    def __init__(self, root: tk.Tk):
        """Initialize tooltip manager.

        Args:
            root: The root Tk window for screen info and scheduling
        """
        self.root = root
        self.tooltip: Optional[tk.Toplevel] = None
        self.tooltip_text: Optional[tk.Text] = None
        self.tooltip_copy_btn: Optional[ttk.Button] = None
        self.tooltip_dict_btn: Optional[ttk.Button] = None
        self.toast = ToastManager(root)  # For shake notifications

        # Mouse position captured when hotkey was pressed
        self._last_mouse_x = 0
        self._last_mouse_y = 0

        # Drag state
        self._drag_x = 0
        self._drag_y = 0

        # Dictionary mode state
        self._dict_mode_active = False
        self._dict_frame = None  # WordButtonFrame instance
        self._current_original = ""  # Store original text for dictionary
        self._current_translation = ""
        self._current_target_lang = ""
        self._current_trial_info = None  # Store trial info for title bar
        self._main_frame = None  # Reference to main frame for dictionary mode
        self._dict_popup_frame = None  # Reference to dict popup's WordButtonFrame for animation

        # Loading animation state
        self._loading_animation_running = False
        self._loading_animation_step = 0
        self._loading_label = None
        self._loading_target_lang = ""

        # Callbacks
        self._on_copy: Optional[Callable[[], None]] = None
        self._on_open_translator: Optional[Callable[[], None]] = None
        self._on_open_settings: Optional[Callable[[], None]] = None
        self._on_open_settings_dictionary_tab: Optional[Callable[[], None]] = None
        self._on_dictionary_lookup: Optional[Callable[[list, str], None]] = None

    def configure_callbacks(self,
                            on_copy: Optional[Callable[[], None]] = None,
                            on_open_translator: Optional[Callable[[], None]] = None,
                            on_open_settings: Optional[Callable[[], None]] = None,
                            on_open_settings_dictionary_tab: Optional[Callable[[], None]] = None,
                            on_dictionary_lookup: Optional[Callable[[list, str], None]] = None):
        """Configure callback functions for tooltip actions.

        Args:
            on_copy: Called when user clicks Copy button
            on_open_translator: Called when user clicks Open Translator
            on_open_settings: Called when user clicks Open Settings (error state)
            on_open_settings_dictionary_tab: Called to open Settings directly to Dictionary tab
            on_dictionary_lookup: Called when user performs dictionary lookup (words_list, target_lang)
        """
        self._on_copy = on_copy
        self._on_open_translator = on_open_translator
        self._on_open_settings = on_open_settings
        self._on_open_settings_dictionary_tab = on_open_settings_dictionary_tab
        self._on_dictionary_lookup = on_dictionary_lookup

    def capture_mouse_position(self):
        """Capture current mouse position for tooltip positioning."""
        self._last_mouse_x = self.root.winfo_pointerx()
        self._last_mouse_y = self.root.winfo_pointery()

    def show_loading(self, target_lang: str):
        """Show loading indicator tooltip with animation.

        Args:
            target_lang: The target language for translation
        """
        self.close()

        self._loading_target_lang = target_lang

        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.overrideredirect(True)
        self.tooltip.configure(bg='#2b2b2b')
        self.tooltip.attributes('-topmost', True)

        frame = ttk.Frame(self.tooltip, padding=12)
        frame.pack(fill=BOTH, expand=True)

        # Create loading label with initial text
        self._loading_label = tk.Label(
            frame,
            text=f"⏳ Translating to {target_lang}   ",
            font=('Segoe UI', 10),
            fg='#ffffff',
            bg='#2b2b2b',
            padx=8,
            pady=4
        )
        self._loading_label.pack()

        self.tooltip.geometry(f"+{self._last_mouse_x + 15}+{self._last_mouse_y + 20}")

        # Start loading animation
        self._loading_animation_running = True
        self._loading_animation_step = 0
        self._animate_loading()

    def _animate_loading(self):
        """Animate the loading tooltip with dots and pulse effect."""
        if not self._loading_animation_running:
            return

        if not self.tooltip or not self._loading_label:
            self._loading_animation_running = False
            return

        try:
            # Dots animation pattern (fixed width to prevent shifting)
            dots_patterns = [
                f"⏳ Translating to {self._loading_target_lang}   ",  # 0 dots + 3 spaces
                f"⏳ Translating to {self._loading_target_lang}.  ",  # 1 dot + 2 spaces
                f"⏳ Translating to {self._loading_target_lang}.. ",  # 2 dots + 1 space
                f"⏳ Translating to {self._loading_target_lang}...",  # 3 dots + 0 spaces
            ]
            text = dots_patterns[self._loading_animation_step % 4]
            self._loading_label.configure(text=text)

            # Pulse color effect (cycle through colors)
            pulse_colors = ['#ffffff', '#88aaff', '#aaccff', '#88aaff']
            color = pulse_colors[self._loading_animation_step % 4]
            self._loading_label.configure(fg=color)

            self._loading_animation_step += 1

            # Schedule next frame (400ms)
            if self.tooltip and self.tooltip.winfo_exists():
                self.tooltip.after(400, self._animate_loading)

        except tk.TclError:
            # Widget destroyed
            self._loading_animation_running = False

    def calculate_size(self, text: str) -> Tuple[int, int]:
        """Calculate optimal tooltip dimensions based on text content.

        Uses 20% safety margin on line height for cross-machine font rendering
        compatibility (handles DPI, ClearType, font substitution differences).

        Args:
            text: The text to display

        Returns:
            Tuple of (width, height) in pixels
        """
        MAX_WIDTH = 800
        MIN_WIDTH = 320
        MIN_HEIGHT = 130  # Unified minimum height

        # Get max height from current monitor's work area
        work_area = get_monitor_work_area(self._last_mouse_x, self._last_mouse_y)
        if work_area:
            MAX_HEIGHT = (work_area[3] - work_area[1]) - 80
        else:
            MAX_HEIGHT = self.root.winfo_screenheight() - 80

        # Padding - SINGLE SOURCE OF TRUTH
        HORIZONTAL_PADDING = 50  # frame(30) + scrollbar(20)
        VERTICAL_PADDING = 100   # header + footer + margins

        # Font with 20% safety margin for cross-machine compatibility
        try:
            ui_font = font.Font(family='Segoe UI', size=11)
        except tk.TclError:
            ui_font = font.Font(family='Arial', size=11)

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

    def show(self, translated: str, target_lang: str, trial_info: dict = None, original: str = ""):
        """Show tooltip with translation result.

        Args:
            translated: The translated text
            target_lang: The target language
            trial_info: Optional dict with trial mode info (from TranslationService.get_trial_info())
            original: The original text (for dictionary lookup)
        """
        self.close()

        # Check if this is an error message
        is_error = translated.startswith("Error:") or translated.startswith("No text")

        # Calculate size (MIN_HEIGHT already handled in calculate_size)
        width, height = self.calculate_size(translated)

        # Add extra height for trial mode header
        if trial_info and trial_info.get('is_trial') and not is_error:
            height += 35  # Extra space for trial header row

        # Create tooltip window
        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.overrideredirect(True)

        def on_tooltip_close():
            self.close()

        self.tooltip.protocol("WM_DELETE_WINDOW", on_tooltip_close)

        # Color based on error status
        if is_error:
            self.tooltip.configure(bg='#3d1f1f')
        else:
            self.tooltip.configure(bg='#2b2b2b')

        # Set topmost initially, then remove so it can go behind other windows
        self.tooltip.attributes('-topmost', True)
        self.tooltip.after(100, lambda: self.tooltip.attributes('-topmost', False) if self.tooltip else None)

        # Main frame
        main_frame = ttk.Frame(self.tooltip, padding=15)
        main_frame.pack(fill=BOTH, expand=True)
        self._main_frame = main_frame

        # Store original and translation for dictionary mode
        self._current_original = original
        self._current_translation = translated
        self._current_target_lang = target_lang
        self._current_trial_info = trial_info  # Store for dictionary title bar

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
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(side=BOTTOM, fill=X, pady=(12, 0))

        btn_frame.bind("<Button-1>", self._start_move)
        btn_frame.bind("<B1-Motion>", self._on_drag)

        if not is_error:
            # Copy button
            self.tooltip_copy_btn = tk.Button(
                btn_frame,
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
            self.tooltip_copy_btn.pack(side=LEFT)

            # Dictionary button - opens popup for original text
            self.tooltip_dict_btn = tk.Button(
                btn_frame,
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
            self.tooltip_dict_btn.pack(side=LEFT, padx=4)

            # Update Dictionary button state based on NLP availability
            self._update_dict_button_state()

            # Open Translator button
            self.tooltip_open_btn = tk.Button(
                btn_frame,
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
            self.tooltip_open_btn.pack(side=LEFT, padx=4)
        else:
            # For errors, show "Open Settings" button
            settings_btn_kwargs = {"text": "Open Settings", "command": self._handle_open_settings, "width": 14}
            if HAS_TTKBOOTSTRAP:
                settings_btn_kwargs["bootstyle"] = "warning"
            ttk.Button(btn_frame, **settings_btn_kwargs).pack(side=LEFT, padx=8)

        # Close button
        close_btn_kwargs = {"text": "\u2715", "command": self.close, "width": 3}
        if HAS_TTKBOOTSTRAP:
            close_btn_kwargs["bootstyle"] = "secondary"
        ttk.Button(btn_frame, **close_btn_kwargs).pack(side=RIGHT)

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

        self.tooltip_text = tk.Text(main_frame, wrap=tk.WORD,
                                    bg='#3d1f1f' if is_error else '#2b2b2b',
                                    fg=text_fg,
                                    font=('Segoe UI', 11), relief='flat',
                                    width=text_width, height=text_height,
                                    borderwidth=0, highlightthickness=0)
        self.tooltip_text.insert('1.0', translated)
        self.tooltip_text.config(state='disabled')
        self.tooltip_text.pack(side=TOP, fill=BOTH, expand=True)

        # Mouse wheel scroll
        self.tooltip_text.bind('<MouseWheel>',
                               lambda e: self.tooltip_text.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        # Position near mouse
        x, y, height = self._calculate_position(width, height)
        self.tooltip.geometry(f"{width}x{height}+{int(x)}+{int(y)}")

        # Bindings
        self.tooltip.bind('<Escape>', lambda e: on_tooltip_close())

    def _calculate_position(self, width: int, height: int) -> Tuple[int, int, int]:
        """Calculate tooltip position and adjust height if needed.

        Supports multi-monitor setups by detecting which monitor the mouse is on
        and positioning the tooltip within that monitor's work area.

        Args:
            width: Tooltip width
            height: Tooltip height

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
        """Handle dragging of the tooltip."""
        if not self.tooltip:
            return

        deltax = event.x_root - self._drag_x
        deltay = event.y_root - self._drag_y

        self._drag_x = event.x_root
        self._drag_y = event.y_root

        x = self.tooltip.winfo_x() + deltax
        y = self.tooltip.winfo_y() + deltay
        self.tooltip.geometry(f"+{x}+{y}")

    def _handle_copy(self):
        """Handle copy button click."""
        if self._on_copy:
            self._on_copy()

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
        if self.tooltip_copy_btn:
            try:
                self.tooltip_copy_btn.configure(text=text)
            except tk.TclError:
                pass

    def _update_dict_button_state(self):
        """Update Dictionary button state based on NLP availability.

        Button keeps same visual appearance (reddish-brown color) whether
        enabled or disabled. Only interaction changes.
        Note: We don't use state='disabled' because it forces grey color.
        Instead, we track state manually and block clicks in handler.
        """
        if not self.tooltip_dict_btn:
            return

        self._dict_btn_enabled = nlp_manager.is_any_installed()

        try:
            if self._dict_btn_enabled:
                self.tooltip_dict_btn.configure(cursor='hand2')
            else:
                self.tooltip_dict_btn.configure(cursor='arrow')
            # Unbind any previous tooltips
            self.tooltip_dict_btn.unbind('<Enter>')
            self.tooltip_dict_btn.unbind('<Leave>')
        except tk.TclError:
            pass  # Widget destroyed

    def _open_dictionary_popup(self):
        """Open dictionary popup window with word buttons for original text.

        Opens as ADDITIONAL window - does NOT close the quick translate tooltip.
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
        dialog.transient(self.root)  # Make child of root window
        dialog.grab_set()            # Modal: block parent interaction

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
            dialog.grab_release()  # Release grab before destroying
            dialog.destroy()
            if self._on_open_settings_dictionary_tab:
                self.root.after(50, self._on_open_settings_dictionary_tab)  # Delay for focus settle

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
                dialog.grab_release()  # Release grab before destroying
                dialog.destroy()
                # Delay for focus settle before opening dictionary popup
                self.root.after(50, lambda: self._open_dictionary_with_language(
                    text_to_analyze, selected, self._current_trial_info))

        def cancel():
            dialog.grab_release()
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

        # Create popup window (ADDITIONAL - not replacing tooltip)
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

        # Calculate size and position - offset from tooltip
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

        # Position below or beside the tooltip
        if self.tooltip and self.tooltip.winfo_exists():
            tooltip_x = self.tooltip.winfo_x()
            tooltip_y = self.tooltip.winfo_y()
            tooltip_height = self.tooltip.winfo_height()
            x = tooltip_x
            y = tooltip_y + tooltip_height + 10  # Below tooltip
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
            # Try positioning above tooltip instead
            if self.tooltip and self.tooltip.winfo_exists():
                y = self.tooltip.winfo_y() - popup_height - 10
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
            """Lookup callback receives list of individual words."""
            if self._on_dictionary_lookup:
                self._on_dictionary_lookup(selected_words, self._current_target_lang)

        def on_no_selection():
            """Show shake toast when no word selected."""
            self.toast.show_warning_with_shake("Please select a word first")

        dict_frame = WordButtonFrame(
            main_frame,
            text_to_analyze,
            on_selection_change=lambda t: None,
            on_lookup=on_lookup,
            on_expand=expand_dictionary,
            on_no_selection=on_no_selection,
            language=language  # Pass language for NLP tokenization
        )
        dict_frame.set_exit_callback(dict_popup.destroy)
        dict_frame.pack(fill=BOTH, expand=True)

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
        """Close the tooltip."""
        # Stop loading animation
        self._loading_animation_running = False
        self._loading_label = None

        # Clean up dictionary mode first
        if self._dict_frame:
            self._dict_frame.destroy()
            self._dict_frame = None
        self._dict_mode_active = False

        if self.tooltip:
            try:
                if self.tooltip.winfo_exists():
                    self.tooltip.destroy()
            except tk.TclError:
                pass
            self.tooltip = None
            self.tooltip_text = None
            self.tooltip_copy_btn = None
            self.tooltip_dict_btn = None
            self._main_frame = None

    @property
    def is_open(self) -> bool:
        """Check if tooltip is currently open."""
        return self.tooltip is not None

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
        separate from the quick translate tooltip (QuickTranslate).
        Both can appear simultaneously.

        Args:
            result: The dictionary lookup result text
            target_lang: The target language
            trial_info: Optional trial mode info dict for title bar display
            looked_up_words: List of words that were looked up (for highlighting)
        """
        # Stop lookup animation first
        self.stop_dictionary_animation()
        # Calculate size based on result text (MIN_HEIGHT already in calculate_size)
        width, height = self.calculate_size(result)
        height = height + 30  # Title bar compensation for Toplevel window

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

        # Position offset from existing tooltip or mouse
        if self.tooltip and self.tooltip.winfo_exists():
            tooltip_x = self.tooltip.winfo_x()
            tooltip_y = self.tooltip.winfo_y()
            x = tooltip_x + 50  # Offset to the right
            y = tooltip_y + 50  # Offset down
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

        # Result text - SAME calculation as Normal mode for consistency
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

        result_text = tk.Text(main_frame, wrap=tk.WORD,
                              bg='#2b2b2b', fg='#ffffff',
                              font=('Segoe UI', 11), relief='flat',
                              width=text_width, height=text_height,
                              borderwidth=0, highlightthickness=0)
        result_text.insert('1.0', result)

        # Highlight looked-up words with distinct colors for each word
        if looked_up_words:
            # 20 professional colors - easy to distinguish, not too bright/dark
            # Arranged so adjacent colors are visually distinct
            HIGHLIGHT_COLORS = [
                "#F4A261",  # Sandy orange
                "#2EC4B6",  # Teal
                "#E76F51",  # Coral red
                "#90BE6D",  # Sage green
                "#9D4EDD",  # Purple
                "#F9C74F",  # Soft yellow
                "#4CC9F0",  # Sky blue
                "#FF6B6B",  # Soft red
                "#43AA8B",  # Mint
                "#FFB703",  # Amber
                "#7B68EE",  # Medium slate blue
                "#FF9F1C",  # Orange peel
                "#00B4D8",  # Pacific cyan
                "#E9C46A",  # Gold
                "#80ED99",  # Light green
                "#F72585",  # Pink
                "#48CAE4",  # Light blue
                "#FFAFCC",  # Light pink
                "#A8DADC",  # Powder blue
                "#CDB4DB",  # Soft lavender
            ]

            # Create a tag for each word with its own color
            for i, word in enumerate(looked_up_words):
                if not word:
                    continue
                # Cycle through colors if more words than colors
                color = HIGHLIGHT_COLORS[i % len(HIGHLIGHT_COLORS)]
                tag_name = f"lookup_word_{i}"

                result_text.tag_configure(tag_name,
                                          foreground=color,
                                          font=('Segoe UI', 11, 'bold'))

                # Find and highlight this word
                start_idx = "1.0"
                while True:
                    pos = result_text.search(word, start_idx, stopindex="end", nocase=True)
                    if not pos:
                        break
                    end_pos = f"{pos}+{len(word)}c"
                    result_text.tag_add(tag_name, pos, end_pos)
                    start_idx = end_pos

        result_text.config(state='disabled')
        result_text.pack(side=TOP, fill=BOTH, expand=True)

        # Mouse wheel scroll
        result_text.bind('<MouseWheel>',
                        lambda e: result_text.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        # Close on Escape
        dict_result.bind('<Escape>', lambda e: dict_result.destroy())
