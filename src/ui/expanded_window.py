"""
Expanded fullscreen translation window for CrossTrans.

Provides a larger view for translation results with fullscreen toggle,
copy functionality, and character/word/line counts.
"""
import tkinter as tk
from tkinter import BOTH, X

import pyperclip

try:
    import ttkbootstrap as ttk
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.ui.ruby_text import RubyText, insert_output
from src.utils.ui_helpers import set_dark_title_bar


class ExpandedTranslationWindow:
    """Expanded view for translation with fullscreen toggle.

    Features:
    - 80% screen size by default, resizable
    - Fullscreen toggle (F11)
    - Copy button with visual feedback
    - Character/word/line count status bar
    - Keyboard shortcuts (Esc to close, Ctrl+C to copy)
    - Furigana for Japanese results (read-only, so I3 holds by construction)
    """

    def __init__(self, root: tk.Tk, toast_manager, config=None):
        """Initialize the expanded window manager.

        Args:
            root: Root Tk window
            toast_manager: ToastManager instance for notifications
            config: Config object, read for the furigana toggle
        """
        self.root = root
        self.toast = toast_manager
        self.config = config

    def show(self, translated: str, target_language: str) -> None:
        """Show the expanded translation window.

        Args:
            translated: The translated text to display
            target_language: The target language name for the title
        """
        if not translated:
            self.toast.show_warning("No translation to expand")
            return

        # Create expanded window
        expanded = tk.Toplevel(self.root)
        expanded.title(f"Translation - {target_language}")
        expanded.configure(bg='#1e1e1e')

        # Get screen dimensions for fullscreen
        screen_width = expanded.winfo_screenwidth()
        screen_height = expanded.winfo_screenheight()

        # Start with 80% of screen size, centered
        window_width = int(screen_width * 0.8)
        window_height = int(screen_height * 0.8)
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        expanded.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # Apply dark title bar (Windows 10/11)
        expanded.update_idletasks()
        set_dark_title_bar(expanded)

        # Allow resizing
        expanded.minsize(600, 400)

        # Main frame with padding
        main_frame = ttk.Frame(expanded, padding=15)
        main_frame.pack(fill=BOTH, expand=True)

        # Header with title and controls
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=X, pady=(0, 10))

        # Title
        title_text = f"Translation to {target_language}"
        ttk.Label(header_frame, text=title_text, font=('Segoe UI', 14, 'bold')).pack(side=tk.LEFT)

        # Window control buttons
        btn_frame = ttk.Frame(header_frame)
        btn_frame.pack(side=tk.RIGHT)

        # Fullscreen toggle button
        is_fullscreen = [False]  # Use list to allow modification in nested function

        def toggle_fullscreen():
            is_fullscreen[0] = not is_fullscreen[0]
            expanded.attributes('-fullscreen', is_fullscreen[0])
            if is_fullscreen[0]:
                fullscreen_btn.configure(text="⧉ Window")
            else:
                fullscreen_btn.configure(text="⛶ Fullscreen")

        fullscreen_kwargs = {"text": "⛶ Fullscreen", "command": toggle_fullscreen, "width": 12}
        if HAS_TTKBOOTSTRAP:
            fullscreen_kwargs["bootstyle"] = "info-outline"
        fullscreen_btn = ttk.Button(btn_frame, **fullscreen_kwargs)
        fullscreen_btn.pack(side=tk.LEFT, padx=5)

        # Copy button
        def copy_expanded():
            # get_plain(), never get(): an embedded ruby frame contributes no
            # characters to get(), so the clipboard would lose every annotated
            # word.
            text = expanded_text.get_plain().strip()
            if text:
                pyperclip.copy(text)
                copy_exp_btn.configure(text="✓ Copied!")
                self.toast.show_success("Copied to clipboard!")
                expanded.after(1500, lambda: copy_exp_btn.configure(text="📋 Copy"))

        copy_kwargs = {"text": "📋 Copy", "command": copy_expanded, "width": 10}
        if HAS_TTKBOOTSTRAP:
            copy_kwargs["bootstyle"] = "primary-outline"
        copy_exp_btn = ttk.Button(btn_frame, **copy_kwargs)
        copy_exp_btn.pack(side=tk.LEFT, padx=5)

        # Close button
        close_kwargs = {"text": "✕ Close", "command": expanded.destroy, "width": 10}
        if HAS_TTKBOOTSTRAP:
            close_kwargs["bootstyle"] = "secondary-outline"
        ttk.Button(btn_frame, **close_kwargs).pack(side=tk.LEFT, padx=5)

        # Text area (no scrollbar, use mouse wheel)
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=BOTH, expand=True)

        # Text widget - read-only. A disabled tk.Text still supports mouse
        # selection and Ctrl+C (verified), so nothing is lost, and read-only is
        # what lets the box hold furigana: typing beside a reading would leave
        # it describing text the user has already changed, and edit_undo()
        # cannot restore a destroyed embedded window.
        expanded_text = RubyText(text_frame, wrap=tk.WORD,
                                 bg='#2b2b2b', base_fg='#ffffff',
                                 kanji_fg='#ffffff',
                                 base_font=('Segoe UI', 14), relief='flat',
                                 spacing1=0, spacing3=0, cursor='xterm',
                                 padx=20, pady=20,
                                 insertbackground='white',
                                 selectbackground='#0d6efd',
                                 selectforeground='white')
        insert_output(expanded_text, '1.0', translated,
                      lang_hint=target_language,
                      enabled=bool(self.config
                                   and self.config.get_furigana_enabled()))
        expanded_text.config(state='disabled')
        expanded_text.pack(fill=BOTH, expand=True)

        # Mouse wheel scroll is bound by RubyText, including over ruby frames

        # Keyboard shortcuts
        expanded.bind('<Escape>', lambda e: expanded.destroy())
        expanded.bind('<F11>', lambda e: toggle_fullscreen())
        expanded.bind('<Control-c>', lambda e: copy_expanded())

        # Status bar
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=X, pady=(10, 0))

        # Character/word count. Counted from get_plain(), so the numbers
        # describe the real text rather than the gaps ruby leaves in get().
        def update_status(*args):
            text = expanded_text.get_plain()
            chars = len(text)
            words = len(text.split())
            lines = text.count('\n') + 1
            status_label.configure(text=f"Characters: {chars:,} | Words: {words:,} | Lines: {lines:,}")

        status_label = ttk.Label(status_frame, text="", font=('Segoe UI', 9))
        status_label.pack(side=tk.LEFT)
        update_status()

        # Shortcut hints
        ttk.Label(status_frame, text="F11: Fullscreen | Esc: Close | Ctrl+C: Copy",
                  font=('Segoe UI', 9), foreground='#888888').pack(side=tk.RIGHT)

        # No <KeyRelease> refresh: the box is read-only, so the counts computed
        # above cannot go stale.

        # Bring window to front and focus it
        expanded.lift()
        expanded.attributes('-topmost', True)
        expanded.update()
        expanded.attributes('-topmost', False)
        expanded.focus_force()
        expanded_text.focus_set()
