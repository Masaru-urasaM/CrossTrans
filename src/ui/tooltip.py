"""
Tooltip Manager for CrossTrans.
Handles translation result tooltips and loading indicators.
"""
import ctypes
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

        # Mouse position captured when hotkey was pressed
        self._last_mouse_x = 0
        self._last_mouse_y = 0

        # Drag state
        self._drag_x = 0
        self._drag_y = 0

        # Callbacks
        self._on_copy: Optional[Callable[[], None]] = None
        self._on_open_translator: Optional[Callable[[], None]] = None
        self._on_open_settings: Optional[Callable[[], None]] = None

    def configure_callbacks(self,
                            on_copy: Optional[Callable[[], None]] = None,
                            on_open_translator: Optional[Callable[[], None]] = None,
                            on_open_settings: Optional[Callable[[], None]] = None):
        """Configure callback functions for tooltip actions.

        Args:
            on_copy: Called when user clicks Copy button
            on_open_translator: Called when user clicks Open Translator
            on_open_settings: Called when user clicks Open Settings (error state)
        """
        self._on_copy = on_copy
        self._on_open_translator = on_open_translator
        self._on_open_settings = on_open_settings

    def capture_mouse_position(self):
        """Capture current mouse position for tooltip positioning."""
        self._last_mouse_x = self.root.winfo_pointerx()
        self._last_mouse_y = self.root.winfo_pointery()

    def show_loading(self, target_lang: str):
        """Show loading indicator tooltip.

        Args:
            target_lang: The target language for translation
        """
        self.close()

        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.overrideredirect(True)
        self.tooltip.configure(bg='#2b2b2b')
        self.tooltip.attributes('-topmost', True)

        frame = ttk.Frame(self.tooltip, padding=10)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text=f"Translating to {target_lang}...",
                  font=('Segoe UI', 10), foreground='#ffffff', background='#2b2b2b').pack()

        self.tooltip.geometry(f"+{self._last_mouse_x + 15}+{self._last_mouse_y + 20}")

    def calculate_size(self, text: str) -> Tuple[int, int]:
        """Calculate optimal tooltip dimensions based on text content.

        Args:
            text: The text to display

        Returns:
            Tuple of (width, height) in pixels
        """
        MAX_WIDTH = 800
        MIN_WIDTH = 320
        MIN_HEIGHT = 120

        # Get max height from current monitor's work area
        work_area = get_monitor_work_area(self._last_mouse_x, self._last_mouse_y)
        if work_area:
            mon_top, mon_bottom = work_area[1], work_area[3]
            MAX_HEIGHT = (mon_bottom - mon_top) - 80
        else:
            MAX_HEIGHT = self.root.winfo_screenheight() - 80

        # Padding configuration
        FRAME_PADDING = 30  # Total horizontal padding (15px * 2)
        TEXT_MARGIN = 10    # Extra margin for scrollbar/safety
        VERTICAL_PADDING = 100  # Header (20) + Footer (50) + Padding (30)

        # Create font object to measure text accurately
        try:
            ui_font = font.Font(family='Segoe UI', size=11)
        except tk.TclError:
            ui_font = font.Font(family='Arial', size=11)

        line_height = ui_font.metrics("linespace") + 2  # +2px for line spacing

        # 1. Calculate Optimal Width
        longest_line_width = 0
        for line in text.split('\n'):
            w = ui_font.measure(line)
            if w > longest_line_width:
                longest_line_width = w

        ideal_width = longest_line_width + FRAME_PADDING + TEXT_MARGIN
        width = max(MIN_WIDTH, min(ideal_width, MAX_WIDTH))

        # 2. Calculate Height (Simulate Word Wrapping)
        available_text_width = width - FRAME_PADDING - TEXT_MARGIN

        total_lines = 0
        for paragraph in text.split('\n'):
            if not paragraph:
                total_lines += 1
                continue

            if ui_font.measure(paragraph) <= available_text_width:
                total_lines += 1
                continue

            # Simulate word wrapping
            current_line_width = 0
            lines_in_para = 1
            words = paragraph.split(' ')
            space_width = ui_font.measure(' ')

            for word in words:
                word_width = ui_font.measure(word)

                if current_line_width + word_width <= available_text_width:
                    current_line_width += word_width + space_width
                else:
                    lines_in_para += 1

                    if word_width > available_text_width:
                        extra_lines = int(word_width / available_text_width)
                        lines_in_para += extra_lines
                        current_line_width = word_width % available_text_width
                    else:
                        current_line_width = word_width + space_width

            total_lines += lines_in_para

        height = (total_lines * line_height) + VERTICAL_PADDING

        return int(width), int(max(height, MIN_HEIGHT))

    def show(self, translated: str, target_lang: str, trial_info: dict = None):
        """Show tooltip with translation result.

        Args:
            translated: The translated text
            target_lang: The target language
            trial_info: Optional dict with trial mode info (from TranslationService.get_trial_info())
        """
        self.close()

        # Check if this is an error message
        is_error = translated.startswith("Error:") or translated.startswith("No text")

        # Calculate size
        width, height = self.calculate_size(translated)
        if is_error:
            height = max(height, 120)

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
            copy_btn_kwargs = {"text": "Copy", "command": self._handle_copy, "width": 8}
            if HAS_TTKBOOTSTRAP:
                copy_btn_kwargs["bootstyle"] = "primary"
            self.tooltip_copy_btn = ttk.Button(btn_frame, **copy_btn_kwargs)
            self.tooltip_copy_btn.pack(side=LEFT)

            # Open Translator button
            open_btn_kwargs = {"text": "Open Translator", "command": self._handle_open_translator, "width": 14}
            if HAS_TTKBOOTSTRAP:
                open_btn_kwargs["bootstyle"] = "success"
            ttk.Button(btn_frame, **open_btn_kwargs).pack(side=LEFT, padx=8)
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

        # Translation text
        text_height = max(1, (height - 80) // 26)
        text_fg = '#ff6b6b' if is_error else '#ffffff'

        self.tooltip_text = tk.Text(main_frame, wrap=tk.WORD,
                                    bg='#3d1f1f' if is_error else '#2b2b2b',
                                    fg=text_fg,
                                    font=('Segoe UI', 11), relief='flat',
                                    width=width // 9, height=text_height,
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

    def close(self):
        """Close the tooltip."""
        if self.tooltip:
            try:
                if self.tooltip.winfo_exists():
                    self.tooltip.destroy()
            except tk.TclError:
                pass
            self.tooltip = None
            self.tooltip_text = None
            self.tooltip_copy_btn = None

    @property
    def is_open(self) -> bool:
        """Check if tooltip is currently open."""
        return self.tooltip is not None
