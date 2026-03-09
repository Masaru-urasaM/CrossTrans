"""
Dictionary popup for word-by-word lookup in CrossTrans.

Handles dictionary mode UI including NLP language detection,
language selection dialogs, and word button popup.
"""
import tkinter as tk
from tkinter import BOTH, X, LEFT, RIGHT
import threading
import logging
from typing import Optional, Callable

try:
    import ttkbootstrap as ttk
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.core.nlp_manager import nlp_manager
from src.utils.ui_helpers import set_dark_title_bar


class DictionaryPopup:
    """Dictionary popup with word selection for lookup.

    Manages the complete dictionary mode flow including:
    - NLP availability checking
    - Language detection and selection
    - Word button popup for selection
    - Dictionary lookup execution
    """

    def __init__(self, root, config, translation_service, toast_manager, quick_translate_manager):
        """Initialize the dictionary popup manager.

        Args:
            root: Root Tk window
            config: Config object
            translation_service: TranslationService for lookups
            toast_manager: ToastManager for notifications
            quick_translate_manager: QuickTranslateManager for showing results
        """
        self.root = root
        self.config = config
        self.translation_service = translation_service
        self.toast = toast_manager
        self.quick_translate_manager = quick_translate_manager

        # State
        self._dict_btn_enabled = False

        # Callbacks
        self._on_show_settings_tab: Optional[Callable] = None
        self._get_selected_language: Optional[Callable] = None
        self._get_popup: Optional[Callable] = None

    def configure_callbacks(self,
                           on_show_settings_tab: Optional[Callable] = None,
                           get_selected_language: Optional[Callable] = None,
                           get_popup: Optional[Callable] = None):
        """Configure callback functions.

        Args:
            on_show_settings_tab: Callback to open settings and navigate to a tab
            get_selected_language: Callback to get the currently selected language
            get_popup: Callback to get the current popup window
        """
        self._on_show_settings_tab = on_show_settings_tab
        self._get_selected_language = get_selected_language
        self._get_popup = get_popup

    def check_nlp_availability(self) -> bool:
        """Check if NLP is available for dictionary mode.

        Returns:
            True if at least one NLP language pack is installed
        """
        return nlp_manager.is_any_installed()

    def update_button_state(self, button: tk.Button) -> None:
        """Update dictionary button state based on NLP availability.

        Button keeps same visual appearance (reddish-brown color) whether
        enabled or disabled. Only interaction changes.

        Args:
            button: The dictionary button widget
        """
        if not button:
            return

        self._dict_btn_enabled = nlp_manager.is_any_installed()

        try:
            if self._dict_btn_enabled:
                button.configure(cursor='hand2')
            else:
                button.configure(cursor='arrow')
            # Unbind any previous hover handlers
            button.unbind('<Enter>')
            button.unbind('<Leave>')
        except tk.TclError:
            pass  # Widget destroyed

    def is_enabled(self) -> bool:
        """Check if dictionary button is enabled."""
        return self._dict_btn_enabled

    def open_from_text(self, original_text: str, parent_window: tk.Toplevel) -> None:
        """Open dictionary popup for given text.

        Args:
            original_text: Text to analyze and tokenize
            parent_window: Parent window for dialogs
        """
        # Check if button is enabled (NLP installed)
        if not self._dict_btn_enabled:
            self._show_nlp_not_installed_dialog(parent_window)
            return

        if not original_text:
            self.toast.show_warning("No text to analyze")
            return

        # Double-check NLP is installed
        if not nlp_manager.is_any_installed():
            self._show_nlp_not_installed_dialog(parent_window)
            return

        # Detect language
        detected_lang, confidence = nlp_manager.detect_language(original_text)
        CONFIDENCE_THRESHOLD = 0.7

        # Check if detection is confident and NLP is installed for that language
        if confidence >= CONFIDENCE_THRESHOLD and nlp_manager.is_installed(detected_lang):
            # Auto-proceed with detected language
            self._open_with_language(original_text, detected_lang)
        else:
            # Determine if language was detected but not installed
            detected_but_not_installed = (
                confidence >= CONFIDENCE_THRESHOLD and
                detected_lang and
                not nlp_manager.is_installed(detected_lang)
            )
            # Show language selection dialog with context
            self._show_language_selection_dialog(
                original_text,
                detected_lang if confidence > 0.3 else None,
                detected_but_not_installed=detected_but_not_installed,
                parent=parent_window
            )

    def _show_nlp_not_installed_dialog(self, parent: tk.Toplevel) -> None:
        """Show dialog when no NLP language pack is installed.

        Args:
            parent: Parent window for the dialog
        """
        dialog = tk.Toplevel(parent)
        dialog.title("No Language Pack Installed")
        dialog.configure(bg='#2b2b2b')
        dialog.transient(parent)
        dialog.grab_set()

        # Center on screen - increased height for button visibility
        dialog.update_idletasks()
        w, h = 400, 220
        x = (dialog.winfo_screenwidth() - w) // 2
        y = (dialog.winfo_screenheight() - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        set_dark_title_bar(dialog)

        # Content
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text="⚠️ No Language Pack Installed",
                  font=('Segoe UI', 12, 'bold')).pack(pady=(0, 10))

        ttk.Label(frame, text="Dictionary mode requires at least one NLP language pack.\n"
                             "Install a language pack in Settings → Dictionary tab.",
                  font=('Segoe UI', 10), justify='center').pack(pady=(0, 15))

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=X)

        def open_settings():
            dialog.destroy()
            if self._on_show_settings_tab:
                self._on_show_settings_tab("Dictionary")

        open_btn_kwargs = {"text": "Open Dictionary Settings", "command": open_settings, "width": 22}
        if HAS_TTKBOOTSTRAP:
            open_btn_kwargs["bootstyle"] = "primary"
        ttk.Button(btn_frame, **open_btn_kwargs).pack(side=LEFT, padx=5)

        cancel_kwargs = {"text": "Cancel", "command": dialog.destroy, "width": 10}
        if HAS_TTKBOOTSTRAP:
            cancel_kwargs["bootstyle"] = "secondary"
        ttk.Button(btn_frame, **cancel_kwargs).pack(side=RIGHT, padx=5)

        dialog.bind('<Escape>', lambda e: dialog.destroy())

    def _show_language_selection_dialog(self, original_text: str, suggested_lang: str = None,
                                        detected_but_not_installed: bool = False,
                                        parent: tk.Toplevel = None) -> None:
        """Show dialog to select source language for dictionary mode.

        Args:
            original_text: Text to analyze
            suggested_lang: Suggested language from detection
            detected_but_not_installed: True if language was detected but pack not installed
            parent: Parent window for the dialog
        """
        installed_languages = nlp_manager.get_installed_languages()
        if not installed_languages:
            self._show_nlp_not_installed_dialog(parent)
            return

        dialog = tk.Toplevel(parent or self.root)
        dialog.title("Select Source Language")
        dialog.configure(bg='#2b2b2b')
        if parent:
            dialog.transient(parent)
        dialog.grab_set()

        # Center on screen - taller if showing install prompt
        dialog.update_idletasks()
        w = 400
        h = 340 if detected_but_not_installed else 280
        x = (dialog.winfo_screenwidth() - w) // 2
        y = (dialog.winfo_screenheight() - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        set_dark_title_bar(dialog)

        # Content
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=BOTH, expand=True)

        # Open Settings -> Dictionary tab
        def open_settings_dict():
            dialog.grab_release()  # Release grab before destroying
            dialog.destroy()
            # Delay for focus settle, then open settings
            if self._on_show_settings_tab:
                self.root.after(50, lambda: self._on_show_settings_tab("Dictionary"))

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
                      font=('Segoe UI', 11, 'bold')).pack(pady=(0, 10))

            ttk.Label(frame, text="Select the source language:",
                      font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 5))

        # Combobox for language selection
        lang_var = tk.StringVar()
        lang_combo = ttk.Combobox(frame, textvariable=lang_var, values=installed_languages,
                                  font=('Segoe UI', 10), state='readonly')
        lang_combo.pack(fill=X, pady=(0, 5))

        # Set default selection
        if suggested_lang and suggested_lang in installed_languages:
            lang_var.set(suggested_lang)
        elif installed_languages:
            lang_var.set(installed_languages[0])

        if not detected_but_not_installed:
            ttk.Label(frame, text="Only installed language packs are shown.",
                      font=('Segoe UI', 9), foreground='#888888').pack(anchor='w', pady=(0, 10))

            # Install more link
            install_link = tk.Label(frame, text="Install more languages →", fg='#4da6ff',
                                   bg='#2b2b2b', font=('Segoe UI', 9, 'underline'), cursor='hand2')
            install_link.pack(anchor='w')
            install_link.bind('<Button-1>', lambda e: open_settings_dict())

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=X, pady=(15, 0))

        def confirm():
            selected = lang_var.get()
            if selected:
                dialog.grab_release()  # Release grab before destroying
                dialog.destroy()
                # Delay for focus settle before opening dictionary popup
                self.root.after(50, lambda: self._open_with_language(original_text, selected))

        def cancel():
            dialog.grab_release()
            dialog.destroy()

        confirm_kwargs = {"text": "Confirm", "command": confirm, "width": 12}
        if HAS_TTKBOOTSTRAP:
            confirm_kwargs["bootstyle"] = "primary"
        ttk.Button(btn_frame, **confirm_kwargs).pack(side=LEFT, padx=5)

        cancel_kwargs = {"text": "Cancel", "command": cancel, "width": 10}
        if HAS_TTKBOOTSTRAP:
            cancel_kwargs["bootstyle"] = "secondary"
        ttk.Button(btn_frame, **cancel_kwargs).pack(side=RIGHT, padx=5)

        dialog.bind('<Escape>', lambda e: cancel())
        dialog.bind('<Return>', lambda e: confirm())

    def _open_with_language(self, original: str, language: str) -> None:
        """Open dictionary popup with specified language for NLP tokenization.

        Args:
            original: Text to tokenize and display
            language: Source language for NLP processing
        """
        from src.ui.dictionary_mode import WordButtonFrame
        from src.ui.quick_translate import get_monitor_work_area

        # Get current target language from callback
        target_language = self._get_selected_language() if self._get_selected_language else "Vietnamese"

        # Build title with trial info if applicable
        try:
            trial_info = self.translation_service.get_trial_info()
            if trial_info and trial_info.get('is_trial'):
                remaining = trial_info.get('remaining', 0)
                daily_limit = trial_info.get('daily_limit', 50)
                title = f"Dictionary ({language} → {target_language}) - Trial Mode ({remaining}/{daily_limit} left)"
            else:
                title = f"Dictionary ({language} → {target_language})"
        except Exception:
            title = f"Dictionary ({language} → {target_language})"

        # Create popup window
        dict_popup = tk.Toplevel(self.root)
        dict_popup.title(title)
        dict_popup.configure(bg='#2b2b2b')
        dict_popup.attributes('-topmost', True)

        # Get work area (excludes taskbar)
        mouse_x = self.root.winfo_pointerx()
        mouse_y = self.root.winfo_pointery()
        work_area = get_monitor_work_area(mouse_x, mouse_y)

        if work_area:
            work_left, work_top, work_right, work_bottom = work_area
        else:
            work_left, work_top = 0, 0
            work_right = self.root.winfo_screenwidth()
            work_bottom = self.root.winfo_screenheight() - 50

        # Window size and position (centered in work area)
        window_width = 700
        window_height = 350
        margin = 10

        # Ensure height fits in work area
        max_height = work_bottom - work_top - 2 * margin
        if window_height > max_height:
            window_height = max_height

        x = work_left + (work_right - work_left - window_width) // 2
        y = work_top + (work_bottom - work_top - window_height) // 2

        dict_popup.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # Apply dark title bar
        dict_popup.update_idletasks()
        set_dark_title_bar(dict_popup)

        # Bring to front and focus (after window fully configured)
        dict_popup.lift()
        dict_popup.focus_force()
        dict_popup.after(200, lambda: dict_popup.attributes('-topmost', False) if dict_popup.winfo_exists() else None)

        # Main frame
        main_frame = ttk.Frame(dict_popup, padding=15)
        main_frame.pack(fill=BOTH, expand=True)

        # Header with language info
        ttk.Label(main_frame, text=f"Select words to look up ({language} NLP):",
                  font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 10))

        # Track expanded state for toggle
        expanded_state = [False]
        original_geometry = [f"{window_width}x{window_height}+{x}+{y}"]

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
                dict_popup.geometry("1000x700")
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
            self._do_lookup(selected_words, target_language)

        def on_no_selection():
            self.toast.show_warning_with_shake("Please select a word first")

        dict_frame = WordButtonFrame(
            main_frame,
            original,
            on_selection_change=lambda t: None,
            on_lookup=on_lookup,
            on_expand=expand_dictionary,
            on_no_selection=on_no_selection,
            language=language  # Pass language for NLP tokenization
        )
        dict_frame.set_exit_callback(dict_popup.destroy)
        dict_frame.pack(fill=BOTH, expand=True)

        # Store reference for animation control (so stop_dictionary_animation() works)
        self.quick_translate_manager._dict_popup_frame = dict_frame

        # Close on Escape
        dict_popup.bind('<Escape>', lambda e: dict_popup.destroy())
        dict_popup.focus_force()

    def _do_lookup(self, words: list, target_lang: str) -> None:
        """Perform dictionary lookup for selected words.

        Uses batch lookup (single API call) for efficiency.

        Args:
            words: List of words to look up
            target_lang: Target language for translation
        """
        if not words:
            return

        # Filter out punctuation, symbols, and special characters
        from src.utils.ui_helpers import filter_dictionary_words
        words = filter_dictionary_words(words)
        if not words:
            self.toast.show_info("No valid words to look up")
            return

        # Show loading toast
        display_text = ", ".join(words[:3]) + ("..." if len(words) > 3 else "")
        self.toast.show_info(f"Looking up {len(words)} word(s): {display_text}")

        # Perform lookup in background
        def do_lookup():
            try:
                # Single API call for all words (optimized batch lookup)
                result = self.translation_service.dictionary_lookup(words, target_lang)
                # Get trial info after API call (quota may have changed)
                trial_info = self.translation_service.get_trial_info()
                # Show result in popup (pass words for highlighting)
                popup = self._get_popup() if self._get_popup else None
                if popup:
                    popup.after(0, lambda: self._show_result(result, target_lang, trial_info, words))
                else:
                    self.root.after(0, lambda: self._show_result(result, target_lang, trial_info, words))
            except Exception as e:
                popup = self._get_popup() if self._get_popup else None
                if popup:
                    popup.after(0, lambda: self.toast.show_error(f"Lookup failed: {str(e)}"))
                else:
                    self.root.after(0, lambda: self.toast.show_error(f"Lookup failed: {str(e)}"))

        threading.Thread(target=do_lookup, daemon=True).start()

    def _show_result(self, result: str, target_lang: str, trial_info: dict = None,
                     looked_up_words: list = None) -> None:
        """Show dictionary lookup result in SEPARATE window.

        Args:
            result: Dictionary lookup result text
            target_lang: Target language
            trial_info: Trial mode info
            looked_up_words: Words that were looked up
        """
        # Use quick translate manager to show result in SEPARATE dictionary window
        self.quick_translate_manager.capture_mouse_position()
        self.quick_translate_manager.show_dictionary_result(result, target_lang, trial_info, looked_up_words)
