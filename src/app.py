"""
Main Application for CrossTrans.
"""
import os
import re
import sys
import time
import ctypes
import queue
import logging
import threading
from typing import Dict, Tuple

import pyperclip
import tkinter as tk
from tkinter import BOTH, X, LEFT, RIGHT, END, BOTTOM, TOP

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.dialogs import Messagebox
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False
    DND_FILES = None

# windnd for Windows drag-and-drop (works better with Toplevel)
try:
    import windnd
    HAS_WINDND = True
except ImportError:
    HAS_WINDND = False

from config import Config
from src.constants import VERSION, LANGUAGES, FEEDBACK_URL
from src.core.translation import TranslationService
from src.core.api_manager import AIAPIManager
from src.core.hotkey import HotkeyManager
from src.core.drop_handler import DropHandler
from src.ui.settings import SettingsWindow
from src.ui.dialogs import APIErrorDialog, TrialExhaustedDialog, TrialFeatureDialog
from src.ui.history_dialog import HistoryDialog
from src.ui.toast import ToastManager, ToastType
from src.ui.quick_translate import QuickTranslateManager
from src.ui.tray import TrayManager
from src.utils.updates import (
    AutoUpdater,
    STARTUP_UPDATE_DELAY,
    UPDATE_TOAST_DURATION,
    THREAD_NAMES
)
from src.core.file_processor import FileProcessor
from src.ui.attachments import AttachmentArea
from src.core.multimodal import MultimodalProcessor
from src.core.screenshot import ScreenshotCapture
from src.utils.ui_helpers import set_dark_title_bar, filter_dictionary_words
from src.ui.expanded_window import ExpandedTranslationWindow
from src.core.update_ui_manager import UpdateUIManager
from src.core.trial_manager import TrialManager
from src.ui.screenshot_handler import ScreenshotHandler
from src.ui.dictionary_popup import DictionaryPopup


class TranslatorApp:
    """Main application class."""

    def __init__(self):
        # Initialize configuration
        self.config = Config()

        # Check for version upgrade and clear cache if needed
        if self._check_version_upgrade():
            return  # App will restart after cache clear

        # Fetch remote model/provider config in background
        from src.core.remote_config import get_config
        get_config().fetch_remote_async()

        # Log DnD library availability
        logging.info(f"DnD libraries: tkinterdnd2={HAS_DND}, windnd={HAS_WINDND}")

        # Create root window
        if HAS_TTKBOOTSTRAP:
            # If DND is available, we need to use TkinterDnD.Tk
            # ttkbootstrap.Window inherits from tk.Tk, so we can't easily mix them inheritance-wise
            # But we can use TkinterDnD.Tk and apply style manually
            if HAS_DND:
                self.root = TkinterDnD.Tk()
                self.style = ttk.Style(theme="darkly")
            else:
                self.root = ttk.Window(themename="darkly")
        else:
            self.root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
        self.root.withdraw()

        # Handle root window close
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)

        # Initialize services
        self.translation_service = TranslationService(self.config)
        self.hotkey_manager = HotkeyManager(self.config, self._on_hotkey_translate)
        self.file_processor = FileProcessor(self.translation_service.api_manager)

        # UI state
        self.popup = None
        self.running = True
        self.selected_language = "Vietnamese"
        self.filtered_languages = LANGUAGES.copy()

        # Current translation data
        self.current_original = ""
        self.current_translated = ""
        self.current_target_lang = ""
        self.settings_window = None

        # Toast notification manager
        self.toast = ToastManager(self.root)

        # Expanded translation window
        self.expanded_window = ExpandedTranslationWindow(self.root, self.toast)

        # Update UI manager (check previous update status)
        self.update_manager = UpdateUIManager(self.root, self.config, self.toast)
        self.update_manager.check_update_status()

        # Trial mode manager
        self.trial_manager = TrialManager(self.root, self.config, self.translation_service, self.toast)
        self.trial_manager.configure_callbacks(on_show_settings_tab=self._show_settings_tab)

        # Screenshot capture for vision/OCR translation
        self.screenshot_capture = ScreenshotCapture(self.root)

        # Quick Translate manager
        self.quick_translate_manager = QuickTranslateManager(self.root, self.config)
        self.quick_translate_manager.configure_callbacks(
            on_copy=self._on_quick_translate_copy,
            on_copy_and_replace=self._on_quick_translate_copy_and_replace,
            on_open_translator=self._on_quick_translate_open_translator,
            on_open_settings=lambda: self._show_settings_tab("API Key"),
            on_open_settings_dictionary_tab=self._show_settings_dictionary_tab,
            on_dictionary_lookup=self._on_quick_translate_dictionary_lookup,
            on_open_settings_hotkeys_tab=self._show_settings_hotkeys_tab
        )

        # Screenshot handler
        self.screenshot_handler = ScreenshotHandler(
            self.root, self.config, self.translation_service,
            self.screenshot_capture, self.toast
        )
        self.screenshot_handler.configure_callbacks(
            on_show_quick_translate=self.show_quick_translate,
            get_quick_translate_manager=lambda: self.quick_translate_manager,
            on_show_settings_tab=self._show_settings_tab,
            get_selected_language=lambda: self.selected_language
        )

        # Dictionary popup manager
        self.dictionary_popup = DictionaryPopup(
            self.root, self.config, self.translation_service,
            self.toast, self.quick_translate_manager
        )
        self.dictionary_popup.configure_callbacks(
            on_show_settings_tab=self._show_settings_tab,
            get_selected_language=lambda: self.selected_language,
            get_popup=lambda: self.popup
        )

        # Tray manager
        self.tray_manager = TrayManager(self.config)
        self.tray_manager.configure_callbacks(
            on_show_main_window=self.show_main_window,
            on_show_settings=self.show_settings,
            on_quit=self.quit_app
        )

        # Drop handler
        self.drop_handler = DropHandler(self.root)
        self.drop_handler.configure(on_open_settings_tab=self._show_settings_tab)

        # Translation animation state
        self._translate_animation_running = False
        self._translate_animation_step = 0
        self._translate_pulse_direction = 1  # 1 = brightening, -1 = dimming
        self._translate_pulse_level = 0

        # Check for updates on startup if enabled
        if self.config.get_auto_check_updates():
            self.update_manager.startup_update_check()

        # Schedule daily API key re-check if trial mode is forced
        self.trial_manager.schedule_recheck()

        # Show any pending update dialogs (success/failure from previous update)
        self.update_manager.show_pending_dialogs()

    def _check_version_upgrade(self) -> bool:
        """Check if app version changed since last run and clear cache if needed.

        Returns:
            True if app will restart (caller should return early)
            False if no restart needed
        """
        from src.constants import VERSION

        last_version = self.config.get_last_run_version()

        if last_version and last_version != VERSION:
            logging.info(f"Version upgrade detected: {last_version} -> {VERSION}")
            self._clear_caches_and_restart()
            return True

        # Update stored version (first run or same version)
        if last_version != VERSION:
            self.config.set_last_run_version(VERSION)

        return False

    def _clear_caches_and_restart(self):
        """Clear Python caches and restart app after version upgrade."""
        import shutil
        import sys
        import os

        from src.constants import VERSION

        logging.info("Clearing caches after version upgrade...")

        # Get base directory (where src folder is)
        base_dir = os.path.dirname(os.path.abspath(__file__))

        # List of __pycache__ directories to clear
        cache_dirs = [
            os.path.join(base_dir, '__pycache__'),
            os.path.join(base_dir, 'core', '__pycache__'),
            os.path.join(base_dir, 'ui', '__pycache__'),
            os.path.join(base_dir, 'ui', 'settings', '__pycache__'),
            os.path.join(base_dir, 'utils', '__pycache__'),
            os.path.join(base_dir, 'assets', '__pycache__'),
        ]

        cleared_count = 0
        for cache_dir in cache_dirs:
            if os.path.exists(cache_dir):
                try:
                    shutil.rmtree(cache_dir)
                    logging.info(f"Cleared cache: {cache_dir}")
                    cleared_count += 1
                except Exception as e:
                    logging.warning(f"Failed to clear {cache_dir}: {e}")

        logging.info(f"Cleared {cleared_count} cache directories")

        # Update version in config before restart
        self.config.set_last_run_version(VERSION)

        # Restart app
        logging.info("Restarting app after cache clear...")
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def _on_hotkey_translate(self, language: str):
        """Handle hotkey translation request.

        Args:
            language: Target language name, or "__screenshot__" for screenshot OCR
        """
        # Check for special screenshot hotkey
        if language == "__screenshot__":
            self.root.after(0, self._on_screenshot_hotkey)
            return

        # Capture source window HWND before any UI interaction
        # This must happen BEFORE showing loading popup, while source app is still foreground
        try:
            self._source_hwnd = ctypes.windll.user32.GetForegroundWindow()
        except Exception:
            self._source_hwnd = None

        # Normal language translation
        # Capture mouse position immediately when hotkey is pressed
        self.quick_translate_manager.capture_mouse_position()

        self.root.after(0, lambda: self.quick_translate_manager.show_loading(language))
        self.translation_service.do_translation(language)

    def _on_screenshot_hotkey(self):
        """Handle screenshot hotkey press (Win+Alt+S)."""
        self.screenshot_handler.handle_hotkey()

    def _cleanup_pending_screenshot(self):
        """Clean up pending screenshot file if exists."""
        self.screenshot_handler.cleanup_pending_screenshot()

    def show_quick_translate(self, original: str, translated: str, target_lang: str, trial_info: dict = None):
        """Show compact popup near mouse cursor with translation result.

        Args:
            original: Original text
            translated: Translated text
            target_lang: Target language
            trial_info: Optional trial mode info dict
        """
        self.current_original = original
        self.current_translated = translated
        self.current_target_lang = target_lang

        # Check if trial quota is exhausted - show dialog instead of popup
        if trial_info and trial_info.get('is_exhausted'):
            self._show_trial_exhausted()
            return

        self.quick_translate_manager.show(translated, target_lang, trial_info, original)

    def close_quick_translate(self):
        """Close the quick translate popup."""
        self.quick_translate_manager.close()

    def _on_quick_translate_copy(self):
        """Handle copy from quick translate popup."""
        pyperclip.copy(self.current_translated)
        self.quick_translate_manager.set_copy_button_text("Copied!")
        self.toast.show_success("Copied to clipboard!")
        # Reset button text after 1 second
        self.root.after(1000, lambda: self.quick_translate_manager.set_copy_button_text("Copy"))

    def _on_quick_translate_copy_and_replace(self):
        """Copy translated text and paste it into the source application.

        With WS_EX_NOACTIVATE on popup, source app keeps focus + selection.
        Just copy to clipboard, close popup, and simulate Ctrl+V.
        """
        translated_text = self.current_translated
        if not translated_text:
            self.toast.show_warning("No translation to replace")
            return

        # Preserve trailing newline from original selection
        # When user selects a full line, the selection includes the trailing newline.
        # Without preserving it, the next line would jump up after replace.
        original_text = self.current_original
        if original_text and original_text.endswith('\n') and not translated_text.endswith('\n'):
            if original_text.endswith('\r\n'):
                translated_text += '\r\n'
            else:
                translated_text += '\n'

        # Always copy to clipboard first (fallback if paste fails)
        pyperclip.copy(translated_text)

        # Close popup (source app still has focus due to WS_EX_NOACTIVATE)
        self.quick_translate_manager.close()

        # Paste in background thread (needs small delay for popup to fully close)
        def do_paste():
            try:
                time.sleep(0.15)
                import keyboard
                keyboard.press_and_release('ctrl+v')
                time.sleep(0.1)
                self.root.after(0, lambda: self.toast.show_success("Replaced!"))
            except Exception as e:
                logging.error(f"Replace paste failed: {e}")
                self.root.after(0, lambda: self.toast.show_warning(
                    "Replace failed. Text copied to clipboard."))

        threading.Thread(target=do_paste, daemon=True).start()

    def _on_quick_translate_open_translator(self):
        """Handle open translator from quick translate popup."""
        self.close_quick_translate()

        # Check if there's a pending screenshot to load into attachments
        pending_image = self.screenshot_handler.get_pending_screenshot()

        self.show_popup(
            self.current_original,
            self.current_translated,
            self.current_target_lang,
            pending_attachment=pending_image
        )

        # Clear pending screenshot (will be managed by AttachmentArea now)
        self.screenshot_handler.clear_pending_screenshot()

    def _on_quick_translate_dictionary_lookup(self, words: list, target_lang: str):
        """Handle dictionary lookup from quick translate popup.

        Uses batch lookup (single API call) for efficiency.
        """
        if not words:
            return

        # Filter out punctuation, symbols, and special characters
        filtered_words = filter_dictionary_words(words)
        if not filtered_words:
            self.toast.show_info("No valid words to look up (only punctuation/symbols)")
            return

        display_text = ", ".join(filtered_words[:3]) + ("..." if len(filtered_words) > 3 else "")
        self.toast.show_info(f"Looking up {len(filtered_words)} word(s): {display_text}")

        def do_lookup():
            try:
                # Single API call for all words (optimized batch lookup)
                result = self.translation_service.dictionary_lookup(filtered_words, target_lang)
                # Get trial info after API call (quota may have changed)
                trial_info = self.translation_service.get_trial_info()
                # Show result in a new popup at mouse position (pass words for highlighting)
                self.root.after(0, lambda: self._show_quick_translate_dictionary_result(result, target_lang, trial_info, filtered_words))
            except Exception as e:
                # Stop animation on error
                self.root.after(0, lambda: self.quick_translate_manager.stop_dictionary_animation())
                self.root.after(0, lambda: self.toast.show_error(f"Lookup failed: {str(e)}"))

        import threading
        threading.Thread(target=do_lookup, daemon=True).start()

    def _show_quick_translate_dictionary_result(self, result: str, target_lang: str, trial_info: dict = None,
                                               looked_up_words: list = None):
        """Show dictionary result in a SEPARATE window (not replacing quick translate)."""
        # Create a new SEPARATE dictionary result window
        self.quick_translate_manager.capture_mouse_position()
        self.quick_translate_manager.show_dictionary_result(result, target_lang, trial_info, looked_up_words)

    def show_main_window(self, icon=None, item=None):
        """Show main translator window from tray."""
        # Ensure runs on main thread
        if threading.current_thread() is not threading.main_thread():
            self.root.after(0, lambda: self.show_main_window(icon, item))
            return

        # If popup already exists, bring it to front instead of creating new one
        if self.popup:
            try:
                if self.popup.winfo_exists():
                    # Restore from minimized/iconified state
                    self.popup.deiconify()
                    # Force window to top using topmost trick
                    self.popup.attributes('-topmost', True)
                    self.popup.update()
                    self.popup.attributes('-topmost', False)
                    # Additional methods to ensure focus
                    self.popup.lift()
                    self.popup.focus_force()
                    return
            except tk.TclError:
                pass  # Window was destroyed, create new one

        # Prevent double-calling by checking if popup is being shown
        if hasattr(self, '_showing_popup') and self._showing_popup:
            return
        self._showing_popup = True
        try:
            self.show_popup("", "", self.selected_language)
        finally:
            # Reset after a short delay
            self.root.after(500, lambda: setattr(self, '_showing_popup', False))

    def show_popup(self, original: str, translated: str, target_lang: str,
                   force_new: bool = False, pending_attachment: str = None):
        """Show the full translator popup window.

        Args:
            original: Original text to display
            translated: Translated text to display
            target_lang: Target language
            force_new: If False and popup exists with content, just bring to front
            pending_attachment: Optional file path to add to attachments (e.g., screenshot)
        """
        # If popup exists with content and we're not forcing new, just bring it to front
        if not force_new and self.popup:
            try:
                if self.popup.winfo_exists():
                    # Check if there's existing content we shouldn't destroy
                    has_content = False
                    if hasattr(self, 'original_text') and self.original_text:
                        try:
                            existing_text = self.original_text.get('1.0', 'end-1c').strip()
                            has_content = bool(existing_text)
                        except:
                            pass
                    if hasattr(self, 'attachment_area') and self.attachment_area:
                        try:
                            has_content = has_content or len(self.attachment_area.get_attachments()) > 0
                        except:
                            pass

                    # If popup has content and we're just opening (empty params), bring to front
                    if has_content and not original and not translated:
                        self.popup.deiconify()
                        self.popup.attributes('-topmost', True)
                        self.popup.update()
                        self.popup.attributes('-topmost', False)
                        self.popup.lift()
                        self.popup.focus_force()
                        return
            except tk.TclError:
                pass

        # Destroy existing popup if present
        if self.popup:
            try:
                self.popup.destroy()
            except tk.TclError:
                pass  # Window already destroyed
            self.popup = None

        # Use tk.Toplevel for better compatibility
        self.popup = tk.Toplevel(self.root)
        self.popup.title("CrossTrans")
        self.popup.configure(bg='#2b2b2b')

        # Focus handlers for topmost behavior
        def on_popup_focus_in(e):
            self.popup.attributes('-topmost', True)
            self.popup.after(100, lambda: self.popup.attributes('-topmost', False) if self.popup else None)

        self.popup.bind('<FocusIn>', on_popup_focus_in)

        # Handle close button properly
        def on_popup_close():
            try:
                if self.popup and self.popup.winfo_exists():
                    self.popup.destroy()
            except tk.TclError:
                pass  # Window already destroyed
            self.popup = None

        self.popup.protocol("WM_DELETE_WINDOW", on_popup_close)
        self.popup.bind('<Escape>', lambda e: on_popup_close())

        # Window size and position
        screen_width = self.popup.winfo_screenwidth()
        screen_height = self.popup.winfo_screenheight()
        window_width = 1400
        window_height = 850
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.popup.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # Apply dark title bar (Windows 10/11)
        self.popup.update_idletasks()  # Ensure window is created
        set_dark_title_bar(self.popup)

        if HAS_TTKBOOTSTRAP:
            main_frame = ttk.Frame(self.popup, padding=20)
        else:
            main_frame = ttk.Frame(self.popup)
        main_frame.pack(fill=BOTH, expand=True, padx=20, pady=20)

        # ===== BUTTONS (Pack FIRST with side=BOTTOM to ensure always visible) =====
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(side=BOTTOM, fill=X, pady=(15, 0))

        # Define on_popup_close reference for buttons
        def on_popup_close_btn():
            try:
                if self.popup and self.popup.winfo_exists():
                    self.popup.destroy()
            except tk.TclError:
                pass  # Window already destroyed
            self.popup = None

        # Translate button
        if HAS_TTKBOOTSTRAP:
            self.translate_btn = ttk.Button(btn_frame,
                                            text=f"Translate → {self.selected_language}",
                                            command=self._do_retranslate,
                                            bootstyle="success", width=25)
        else:
            self.translate_btn = ttk.Button(btn_frame,
                                            text=f"Translate → {self.selected_language}",
                                            command=self._do_retranslate, width=25)
        self.translate_btn.pack(side=LEFT)

        # Copy button
        if HAS_TTKBOOTSTRAP:
            self.copy_btn = ttk.Button(btn_frame, text="Copy",
                                       command=self._copy_translation,
                                       bootstyle="primary", width=12)
        else:
            self.copy_btn = ttk.Button(btn_frame, text="Copy",
                                       command=self._copy_translation, width=12)
        self.copy_btn.pack(side=LEFT, padx=10)

        # History button
        if HAS_TTKBOOTSTRAP:
            ttk.Button(btn_frame, text="History", command=self._open_history,
                       bootstyle="warning-outline", width=10).pack(side=LEFT, padx=10)
        else:
            ttk.Button(btn_frame, text="History", command=self._open_history,
                       width=10).pack(side=LEFT, padx=10)

        # Close button
        if HAS_TTKBOOTSTRAP:
            ttk.Button(btn_frame, text="Close", command=on_popup_close_btn,
                       bootstyle="secondary", width=12).pack(side=RIGHT)
        else:
            ttk.Button(btn_frame, text="Close", command=on_popup_close_btn,
                       width=12).pack(side=RIGHT)

        # ===== CONTENT FRAME (Pack after buttons to fill remaining space) =====
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(side=TOP, fill=BOTH, expand=True)
        self._content_frame = content_frame  # Save reference for dynamic attachment refresh

        # ===== ATTACHMENT AREA =====
        # Show if ANY API has vision or file capabilities (check flags set during API test)
        has_vision = self.config.has_any_vision_capable()
        has_file = self.config.has_any_file_capable()

        if has_vision or has_file:
            try:
                # Ensure popup window is fully realized before creating DnD widgets
                self.popup.update_idletasks()
                self.attachment_area = AttachmentArea(content_frame, self.config, on_change=None,
                                                     on_open_settings_tab=self._show_settings_tab)
                self.attachment_area.pack(fill=X, pady=(0, 10))

                # Load pending attachment (e.g., from screenshot hotkey)
                if pending_attachment and os.path.exists(pending_attachment):
                    try:
                        import shutil
                        import tempfile
                        import time

                        # Create persistent copy in temp directory
                        temp_dir = tempfile.gettempdir()
                        filename = f"screenshot_{int(time.time())}.png"
                        persistent_path = os.path.join(temp_dir, filename)
                        shutil.copy2(pending_attachment, persistent_path)

                        # Add to attachments
                        self.attachment_area.add_file(persistent_path, show_warning=False)
                        logging.info(f"Loaded screenshot into attachments: {persistent_path}")

                        # Delete original temp file
                        try:
                            os.unlink(pending_attachment)
                        except Exception:
                            pass
                    except Exception as e:
                        logging.error(f"Failed to load screenshot into attachments: {e}")

            except Exception as e:
                logging.error(f"Error initializing AttachmentArea: {e}")
                self.attachment_area = None
        else:
            self.attachment_area = None

        # ===== ORIGINAL TEXT =====
        original_header = ttk.Frame(content_frame)
        self._original_header = original_header  # Save reference for attachment pack positioning
        original_header.pack(fill=X, anchor='w')

        ttk.Label(original_header, text="Original:", font=('Segoe UI', 10)).pack(side=LEFT)

        # Dictionary button - opens popup with word buttons for original text
        # Use tk.Button for consistent reddish-brown color
        self.dict_btn = tk.Button(
            original_header,
            text="Dictionary",
            command=self._open_dictionary_popup,
            autostyle=False,  # Prevent ttkbootstrap from overriding colors
            bg="#822312",  # Dark red (main color)
            fg='#ffffff',
            activebackground='#9A3322',  # Lighter red (hover/active)
            activeforeground='#ffffff',
            font=('Segoe UI', 9),
            relief='flat',
            padx=8, pady=2,
            cursor='hand2',
            width=10
        )
        self.dict_btn.pack(side=RIGHT)

        # Update Dictionary button state based on NLP availability
        self._update_dict_button_state()

        self.original_text = tk.Text(content_frame, height=6, wrap=tk.WORD,
                                     bg='#2b2b2b', fg='#cccccc',
                                     font=('Segoe UI', 11), relief='flat',
                                     padx=10, pady=10, insertbackground='white',
                                     undo=True, maxundo=-1)
        self.original_text.insert('1.0', original)
        self.original_text.pack(fill=X, pady=(5, 15))
        self.original_text.bind('<MouseWheel>',
            lambda e: self.original_text.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Undo/Redo bindings
        self.original_text.bind('<Control-z>', lambda e: self.original_text.edit_undo() or "break")
        self.original_text.bind('<Control-Z>', lambda e: self.original_text.edit_undo() or "break")
        self.original_text.bind('<Control-Shift-z>', lambda e: self.original_text.edit_redo() or "break")
        self.original_text.bind('<Control-Shift-Z>', lambda e: self.original_text.edit_redo() or "break")

        # ===== LANGUAGE SELECTOR =====
        ttk.Label(content_frame, text="Translate to:", font=('Segoe UI', 10)).pack(anchor='w')

        # Search box
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(content_frame, textvariable=self.search_var,
                                      font=('Segoe UI', 10))
        self.search_entry.pack(fill=X, pady=(5, 5))
        self.search_entry.insert(0, "Search language...")
        self.search_entry.bind('<FocusIn>', self._on_search_focus_in)
        self.search_entry.bind('<FocusOut>', self._on_search_focus_out)
        self.search_var.trace_add('write', self._filter_languages)

        # Language listbox (no visible scrollbar)
        list_frame = ttk.Frame(content_frame)
        list_frame.pack(fill=X, pady=(0, 15))

        self.lang_listbox = tk.Listbox(list_frame, height=2, bg='#2b2b2b', fg='#ffffff',
                                       font=('Segoe UI', 10), relief='flat',
                                       selectbackground='#0d6efd', selectforeground='white',
                                       activestyle='none', highlightthickness=0,
                                       borderwidth=0)
        self.lang_listbox.pack(fill=X)
        self.lang_listbox.bind('<MouseWheel>',
            lambda e: self.lang_listbox.yview_scroll(int(-1*(e.delta/120)), "units"))

        self._populate_language_list()
        self.lang_listbox.bind('<<ListboxSelect>>', self._on_language_select)
        self._select_language_in_list(target_lang)

        # ===== CUSTOM PROMPT =====
        ttk.Label(content_frame, text="Custom prompt (optional):",
                  font=('Segoe UI', 10)).pack(anchor='w')

        self.custom_prompt_text = tk.Text(content_frame, height=2, wrap=tk.WORD,
                                          bg='#2b2b2b', fg='#cccccc',
                                          font=('Segoe UI', 10), relief='flat',
                                          padx=10, pady=10, insertbackground='white',
                                          undo=True, maxundo=-1)
        self.custom_prompt_text.pack(fill=X, pady=(5, 15))
        self.custom_prompt_text.bind('<MouseWheel>',
            lambda e: self.custom_prompt_text.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Undo/Redo bindings for custom prompt
        self.custom_prompt_text.bind('<Control-z>', lambda e: self.custom_prompt_text.edit_undo() or "break")
        self.custom_prompt_text.bind('<Control-Z>', lambda e: self.custom_prompt_text.edit_undo() or "break")
        self.custom_prompt_text.bind('<Control-Shift-z>', lambda e: self.custom_prompt_text.edit_redo() or "break")
        self.custom_prompt_text.bind('<Control-Shift-Z>', lambda e: self.custom_prompt_text.edit_redo() or "break")

        # Placeholder for custom prompt
        placeholder = "E.g., 'Make it formal' or 'Use casual tone'"
        self.custom_prompt_text.insert('1.0', placeholder)
        self.custom_prompt_text.config(fg='#666666')

        def on_custom_focus_in(e):
            if self.custom_prompt_text.get('1.0', 'end-1c') == placeholder:
                self.custom_prompt_text.delete('1.0', tk.END)
                self.custom_prompt_text.config(fg='#cccccc')

        def on_custom_focus_out(e):
            if not self.custom_prompt_text.get('1.0', 'end-1c').strip():
                self.custom_prompt_text.insert('1.0', placeholder)
                self.custom_prompt_text.config(fg='#666666')

        self.custom_prompt_text.bind('<FocusIn>', on_custom_focus_in)
        self.custom_prompt_text.bind('<FocusOut>', on_custom_focus_out)

        # ===== TRANSLATION OUTPUT =====
        trans_header = ttk.Frame(content_frame)
        trans_header.pack(fill=tk.X, anchor='w')

        ttk.Label(trans_header, text="Translation:", font=('Segoe UI', 10)).pack(side=tk.LEFT)

        # Expand button
        expand_kwargs = {"text": "⛶ Expand", "command": self._open_expanded_translation, "width": 10}
        if HAS_TTKBOOTSTRAP:
            expand_kwargs["bootstyle"] = "info-outline"
        self.expand_btn = ttk.Button(trans_header, **expand_kwargs)
        self.expand_btn.pack(side=tk.RIGHT)

        self.trans_text = tk.Text(content_frame, height=10, wrap=tk.WORD,
                                  bg='#2b2b2b', fg='#ffffff',
                                  font=('Segoe UI', 12), relief='flat',
                                  padx=10, pady=10)
        self.trans_text.insert('1.0', translated)
        self.trans_text.config(state='disabled')  # Make read-only
        self.trans_text.pack(fill=BOTH, expand=True, pady=(5, 0))
        self.trans_text.bind('<MouseWheel>',
            lambda e: self.trans_text.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Enable DnD for popup window - delay to ensure window is fully realized
        self.popup.after(300, lambda: self._setup_drop_handling(self.popup))

        # Update title with trial info if in trial mode
        self._update_popup_title_with_trial()

        self.popup.focus_force()

    def _populate_language_list(self):
        """Populate language listbox."""
        if not hasattr(self, 'lang_listbox'):
            return
        self.lang_listbox.delete(0, tk.END)
        for lang_name, lang_code, _ in self.filtered_languages:
            self.lang_listbox.insert(tk.END, f"{lang_name} ({lang_code})")

    def _filter_languages(self, *args):
        """Filter language list based on search."""
        if not hasattr(self, 'lang_listbox'):
            return

        search_term = self.search_var.get().lower()
        if search_term in ("", "search language..."):
            self.filtered_languages = LANGUAGES.copy()
        else:
            self.filtered_languages = []
            for lang_name, lang_code, lang_aliases in LANGUAGES:
                searchable = f"{lang_name} {lang_code} {lang_aliases}".lower()
                if search_term in searchable:
                    self.filtered_languages.append((lang_name, lang_code, lang_aliases))

        self._populate_language_list()

        if self.filtered_languages:
            self.lang_listbox.selection_set(0)
            self.selected_language = self.filtered_languages[0][0]
            self._update_translate_button()

    def _on_search_focus_in(self, event):
        """Handle search box focus in."""
        if self.search_entry.get() == "Search language...":
            self.search_entry.delete(0, tk.END)

    def _on_search_focus_out(self, event):
        """Handle search box focus out."""
        if not self.search_entry.get():
            self.search_entry.insert(0, "Search language...")

    def _on_language_select(self, event):
        """Handle language selection."""
        selection = self.lang_listbox.curselection()
        if selection:
            index = selection[0]
            if index < len(self.filtered_languages):
                self.selected_language = self.filtered_languages[index][0]
                self._update_translate_button()

    def _select_language_in_list(self, lang_name: str):
        """Select a language in the listbox."""
        if not hasattr(self, 'lang_listbox'):
            return
        for i, (name, _, _) in enumerate(self.filtered_languages):
            if name == lang_name:
                self.lang_listbox.selection_clear(0, tk.END)
                self.lang_listbox.selection_set(i)
                self.lang_listbox.see(i)
                self.selected_language = name
                break
        self._update_translate_button()

    def _update_translate_button(self):
        """Update translate button text."""
        if hasattr(self, 'translate_btn'):
            self.translate_btn.configure(text=f"Translate → {self.selected_language}")

    def _do_retranslate(self):
        """Perform translation from popup."""
        original = self.original_text.get('1.0', tk.END).strip()

        # Check for attachments
        attachments = self.attachment_area.get_attachments() if (hasattr(self, 'attachment_area') and self.attachment_area) else []
        has_attachments = len(attachments) > 0

        # Check if in trial mode and trying to use file/image translation
        if has_attachments and self.is_trial_mode():
            self._show_trial_feature_blocked("File/Image translation")
            return

        if not original and not has_attachments:
            self.toast.show_warning("No content to translate")
            return

        # Get custom prompt
        custom_prompt = self.custom_prompt_text.get('1.0', tk.END).strip()
        placeholder = "E.g., 'Make it formal' or 'Use casual tone'"
        if custom_prompt == placeholder:
            custom_prompt = ""

        self.translate_btn.configure(state='disabled')
        self._start_translate_animation()

        def translate_thread():
            translated = ""
            extracted_original = ""

            if has_attachments:
                # Collect all attachments for single API call
                image_paths = []
                file_contents = {}  # {filename: content}
                image_filenames = []  # Track image filenames for response format

                for att in attachments:
                    path = att['path']
                    filename = os.path.basename(path)

                    # Skip missing files
                    if not os.path.exists(path):
                        logging.warning(f"Skipping missing file: {path}")
                        continue

                    if att['type'] == 'image':
                        image_paths.append(path)
                        image_filenames.append(filename)
                    elif att['type'] == 'file':
                        try:
                            content = self.file_processor.extract_text(path)
                            file_contents[filename] = content
                        except Exception as e:
                            file_contents[filename] = f"[Error reading file: {str(e)}]"

                # Build prompt for multimodal translation
                try:
                    # Build file list for prompt
                    file_list_text = ""
                    if image_filenames:
                        file_list_text += "Images: " + ", ".join(image_filenames) + "\n"
                    if file_contents:
                        file_list_text += "Text files: " + ", ".join(file_contents.keys()) + "\n"

                    base_instruction = f"Translate to {self.selected_language}."
                    if custom_prompt:
                        base_instruction += f" {custom_prompt}"

                    prompt = f"""{base_instruction}

You have received the following files:
{file_list_text}
{f'Additional context from user: {original}' if original else ''}

CRITICAL INSTRUCTIONS:
1. For IMAGES: Perform OCR - extract ALL visible text EXACTLY as it appears.
   - Do NOT describe the image
   - Do NOT say "The image shows..." or "This appears to be..."
   - ONLY output the actual text you can read
   - Preserve the original formatting, line breaks, and structure

2. For TEXT FILES: Use the provided content directly.

3. Then translate all extracted text.

=== EXAMPLE (CORRECT) ===
If image shows a restaurant menu:
**[menu.jpg]:**
Today's Special
Grilled Salmon $18.99
Caesar Salad $12.50
---
NOT: "The image shows a restaurant menu with prices listed."

=== EXAMPLE (CORRECT) ===
If image shows a business document:
**[document.png]:**
Meeting Notes - January 15, 2026
Attendees: John, Mary, Bob
Action Items:
1. Review budget proposal
2. Schedule follow-up
---
NOT: "This is a business document containing meeting notes."

Return your response in this EXACT format:

===ORIGINAL===
**[filename1]:**
[For images: ALL text extracted via OCR, exactly as written]
[For text files: the original content]

**[filename2]:**
[extracted text]

===TRANSLATION===
**[filename1]:**
[translated text in {self.selected_language}]

**[filename2]:**
[translated text in {self.selected_language}]

IMPORTANT: Translate ALL text to {self.selected_language}. Process ALL files. Extract actual text from images (OCR), do not describe them."""

                    # Single API call with all images + file contents
                    result = self.translation_service.api_manager.translate_multimodal(
                        prompt, image_paths, file_contents
                    )

                    # Parse result to separate Original and Translation sections
                    if "===ORIGINAL===" in result and "===TRANSLATION===" in result:
                        try:
                            # Split by the markers
                            parts = result.split("===TRANSLATION===")
                            original_section = parts[0].replace("===ORIGINAL===", "").strip()
                            translation_section = parts[1].strip() if len(parts) > 1 else ""

                            extracted_original = original_section
                            translated = translation_section
                        except (IndexError, ValueError):
                            # If parsing fails, put everything in translation
                            translated = result
                    else:
                        # AI didn't follow format, use full result as translation
                        translated = result

                    # Save to history for multimodal translations
                    source_text = original if original else f"[{len(attachments)} attachment(s)]"
                    self.translation_service.history_manager.add_entry(
                        source_text, translated, self.selected_language, source_type="multimodal"
                    )

                except Exception as e:
                    translated = f"Error processing attachments: {str(e)}"
            else:
                # Standard text translation (no attachments)
                translated = self.translation_service.translate_text(
                    original, self.selected_language, custom_prompt)

            if self.popup:
                self.popup.after(0, lambda: self._update_translation_with_original(translated, extracted_original))

        threading.Thread(target=translate_thread, daemon=True).start()

    def _update_translation(self, translated: str):
        """Update translation result in popup."""
        self._update_translation_with_original(translated, "")

    def _update_popup_title_with_trial(self):
        """Update popup title to show trial mode quota if in trial mode."""
        if not self.popup or not self.popup.winfo_exists():
            return

        try:
            trial_info = self.translation_service.get_trial_info()
            if trial_info and trial_info.get('is_trial'):
                remaining = trial_info.get('remaining', 0)
                daily_limit = trial_info.get('daily_limit', 50)
                self.popup.title(f"CrossTrans - Trial Mode ({remaining}/{daily_limit} left)")
            else:
                self.popup.title("CrossTrans")
        except Exception:
            self.popup.title("CrossTrans")

    def _update_translation_with_original(self, translated: str, extracted_original: str = ""):
        """Update translation result and optionally the original text in popup."""
        # Stop animation
        self._stop_translate_animation()

        # Update original text box if extracted_original is provided
        if extracted_original:
            self.original_text.delete('1.0', tk.END)
            self.original_text.insert('1.0', extracted_original)

        # Update translation text box
        self.trans_text.config(state='normal')  # Enable to update
        self.trans_text.delete('1.0', tk.END)
        self.trans_text.insert('1.0', translated)
        self.trans_text.config(state='disabled')  # Make read-only again
        self.translate_btn.configure(text=f"Translate → {self.selected_language}",
                                     state='normal')

        # Update title with trial info after each translation
        self._update_popup_title_with_trial()

    def _start_translate_animation(self):
        """Start the translation button animation (dots + pulse)."""
        self._translate_animation_running = True
        self._translate_animation_step = 0
        self._translate_pulse_level = 0
        self._translate_pulse_direction = 1
        self._animate_translate_button()

    def _stop_translate_animation(self):
        """Stop the translation button animation."""
        self._translate_animation_running = False
        # Reset button style
        if hasattr(self, 'translate_btn') and self.translate_btn:
            try:
                if HAS_TTKBOOTSTRAP:
                    self.translate_btn.configure(bootstyle="success")
            except tk.TclError:
                pass

    def _animate_translate_button(self):
        """Animate the translate button with dots and pulse effect."""
        if not self._translate_animation_running:
            return

        if not hasattr(self, 'translate_btn') or not self.translate_btn:
            return

        try:
            # Dots animation: use fixed-width patterns to prevent text shifting
            # Each pattern has same visual width (dots + spaces)
            dots_patterns = [
                "⏳ Translating   ",  # 0 dots + 3 spaces
                "⏳ Translating.  ",  # 1 dot + 2 spaces
                "⏳ Translating.. ",  # 2 dots + 1 space
                "⏳ Translating...",  # 3 dots + 0 spaces
            ]
            text = dots_patterns[self._translate_animation_step % 4]
            self.translate_btn.configure(text=text)

            # Pulse effect using bootstyle colors (runs faster than dots)
            if HAS_TTKBOOTSTRAP:
                # Cycle through different green shades
                pulse_styles = ["success", "success", "info", "success"]
                style_idx = (self._translate_pulse_level // 2) % len(pulse_styles)
                self.translate_btn.configure(bootstyle=pulse_styles[style_idx])

                # Update pulse level
                self._translate_pulse_level += self._translate_pulse_direction
                if self._translate_pulse_level >= 6:
                    self._translate_pulse_direction = -1
                elif self._translate_pulse_level <= 0:
                    self._translate_pulse_direction = 1

            # Increment step
            self._translate_animation_step += 1

            # Schedule next frame (500ms for dots - slower animation)
            if self.popup and self.popup.winfo_exists():
                self.popup.after(500, self._animate_translate_button)

        except tk.TclError:
            # Widget destroyed
            self._translate_animation_running = False

    def _open_expanded_translation(self):
        """Open translation in expanded fullscreen window."""
        translated = self.trans_text.get('1.0', tk.END).strip()
        self.expanded_window.show(translated, self.selected_language)

    def _copy_translation(self):
        """Copy translation to clipboard."""
        translated = self.trans_text.get('1.0', tk.END).strip()
        if not translated:
            self.toast.show_warning("No translation to copy")
            return
        pyperclip.copy(translated)
        self.copy_btn.configure(text="Copied!")
        self.toast.show_success("Copied to clipboard!")
        self.popup.after(1000, lambda: self.copy_btn.configure(text="Copy"))

    def _update_dict_button_state(self):
        """Update Dictionary button state based on NLP availability."""
        if hasattr(self, 'dict_btn') and self.dict_btn:
            self.dictionary_popup.update_button_state(self.dict_btn)

    def _open_dictionary_popup(self):
        """Open dictionary popup window with word buttons for original text."""
        original = self.original_text.get('1.0', tk.END).strip()
        self.dictionary_popup.open_from_text(original, self.popup)

    def _show_settings_hotkeys_tab(self):
        """Open settings window at Hotkeys tab.

        Used by popup gear icon to quickly access Replace mode toggle.
        """
        self._show_settings_tab("Hotkeys")

    def _show_settings_dictionary_tab(self):
        """Open settings window and navigate directly to Dictionary tab.

        Used by popup "Install now" link to open Dictionary tab directly.
        """
        self.show_settings()
        # Use multiple attempts with increasing delays to ensure window is ready
        def try_open_tab(attempts=3):
            if attempts <= 0:
                return
            if self.settings_window and hasattr(self.settings_window, 'open_dictionary_tab'):
                self.settings_window.open_dictionary_tab()
                # Focus the settings window after opening tab
                self._focus_settings_window()
            else:
                # Retry with longer delay
                self.root.after(200, lambda: try_open_tab(attempts - 1))
        self.root.after(100, try_open_tab)

    def _focus_settings_window(self):
        """Bring Settings window to front and focus it."""
        if self.settings_window and hasattr(self.settings_window, 'window'):
            try:
                win = self.settings_window.window
                if win and win.winfo_exists():
                    win.deiconify()  # Restore if minimized
                    win.attributes('-topmost', True)
                    win.update()
                    win.attributes('-topmost', False)
                    win.lift()
                    win.focus_force()
            except tk.TclError:
                pass  # Window destroyed

    def _open_settings_dictionary_tab(self):
        """Switch to Dictionary tab in already-open settings window."""
        if self.settings_window and hasattr(self.settings_window, 'open_dictionary_tab'):
            self.settings_window.open_dictionary_tab()
            # Re-focus window after switching tab
            self._focus_settings_window()

    def _open_history(self):
        """Open history dialog."""
        if self.popup:
            HistoryDialog(self.popup, self.translation_service.history_manager, self._load_history_item)

    def _load_history_item(self, item):
        """Load a history item into the translator."""
        if not self.popup:
            return
            
        self.original_text.delete('1.0', tk.END)
        self.original_text.insert('1.0', item.get('original', ''))
        
        self._select_language_in_list(item.get('target_lang', 'English'))
        
        self._update_translation(item.get('translated', ''))

    def _setup_drop_handling(self, popup_window):
        """Setup drag-and-drop handling for the popup window."""
        # Configure drop handler with current popup and attachment area
        self.drop_handler.set_popup(popup_window)
        self.drop_handler.set_attachment_area(
            self.attachment_area if hasattr(self, 'attachment_area') else None
        )

        # Use tkinterdnd2 if available (built into root window), otherwise use windnd
        # NOTE: Only use ONE drop method to avoid conflicts that can break keyboard input
        if HAS_DND:
            # tkinterdnd2 is already set up on AttachmentArea, just need queue checker
            logging.info("Using tkinterdnd2 for drag-and-drop (via AttachmentArea)")
        elif HAS_WINDND:
            # Use windnd as fallback for Toplevel windows
            self.drop_handler.setup_windnd(popup_window)
            logging.info("Using windnd for drag-and-drop")
        else:
            logging.warning("No drag-and-drop library available")

        # Start queue checker for windnd (processes drops from Windows thread)
        self.drop_handler.start_queue_checker()

    def show_settings(self, icon=None, item=None):
        """Show settings window."""
        # Ensure runs on main thread
        if threading.current_thread() is not threading.main_thread():
            self.root.after(0, lambda: self.show_settings(icon, item))
            return

        # Check if already open
        if self.settings_window and self.settings_window.window.winfo_exists():
            # Restore from minimized state
            self.settings_window.window.deiconify()
            # Force window to top using topmost trick
            self.settings_window.window.attributes('-topmost', True)
            self.settings_window.window.update()
            self.settings_window.window.attributes('-topmost', False)
            # Additional methods to ensure focus
            self.settings_window.window.lift()
            self.settings_window.window.focus_force()
            return

        def on_settings_save():
            self.translation_service.reconfigure()
            self.hotkey_manager.unregister_all()  # Restarts thread with new hotkeys
            self._refresh_tray_menu()

            if HAS_TTKBOOTSTRAP:
                Messagebox.show_info("Settings saved successfully!", title="Saved", parent=self.settings_window.window)
            else:
                from tkinter import messagebox
                messagebox.showinfo("Saved", "Settings saved successfully!", parent=self.settings_window.window)

        def on_api_change():
            """Called when API keys change - reconfigure to update trial mode status."""
            self.translation_service.reconfigure()
            # Refresh attachment area in case API capabilities changed
            self._refresh_attachment_area()
            # Refresh tray menu to show/hide screenshot hotkey based on vision capability
            self._refresh_tray_menu()

        self.settings_window = SettingsWindow(self.root, self.config, on_settings_save, on_api_change)

        # Ensure new window appears on top (same pattern as re-focusing existing window)
        self.settings_window.window.attributes('-topmost', True)
        self.settings_window.window.update()
        self.settings_window.window.attributes('-topmost', False)
        self.settings_window.window.lift()
        self.settings_window.window.focus_force()

    def _refresh_tray_menu(self):
        """Refresh tray menu to reflect updated hotkeys."""
        self.tray_manager.refresh_menu()

    def _refresh_attachment_area(self):
        """Refresh attachment area based on current API capabilities.

        Called when API keys are saved to immediately show/hide attachments icon
        without requiring user to close and reopen the main window.
        """
        # Only refresh if popup window exists and is visible
        if not hasattr(self, 'popup') or not self.popup or not self.popup.winfo_exists():
            return

        # Check current API capabilities
        has_vision = self.config.has_any_vision_capable()
        has_file = self.config.has_any_file_capable()

        if has_vision or has_file:
            # Should show attachment area
            if not self.attachment_area:
                try:
                    # Create new AttachmentArea
                    from src.ui.attachments import AttachmentArea
                    self.popup.update_idletasks()
                    self.attachment_area = AttachmentArea(
                        self._content_frame, self.config, on_change=None,
                        on_open_settings_tab=self._show_settings_tab
                    )
                    # Pack before the original_header (after content_frame top)
                    self.attachment_area.pack(fill=X, pady=(0, 10), before=self._original_header)
                except Exception as e:
                    logging.error(f"Error creating AttachmentArea during refresh: {e}")
                    self.attachment_area = None
        else:
            # Should hide attachment area
            if self.attachment_area:
                try:
                    self.attachment_area.pack_forget()
                    self.attachment_area.destroy()
                except Exception:
                    pass
                self.attachment_area = None

    def _create_tray_icon(self):
        """Create system tray icon."""
        self.tray_icon = self.tray_manager.create()
        return self.tray_icon

    def quit_app(self, icon=None, item=None):
        """Quit the application with proper cleanup."""
        logging.info("Quitting application...")
        self.running = False

        # Cleanup hotkeys
        try:
            self.hotkey_manager.cleanup()
        except Exception as e:
            logging.error(f"Error cleaning up hotkeys: {e}")

        # Stop drop handler
        try:
            self.drop_handler.stop()
        except Exception as e:
            logging.warning(f"Error stopping drop handler: {e}")

        # Close quick translate popup
        self.close_quick_translate()

        # Close popup
        if self.popup:
            try:
                if self.popup.winfo_exists():
                    self.popup.destroy()
            except Exception as e:
                logging.warning(f"Error destroying popup: {e}")

        # Stop tray icon
        try:
            self.tray_manager.stop()
        except Exception as e:
            logging.warning(f"Error stopping tray: {e}")

        # Quit root window
        try:
            if self.root.winfo_exists():
                self.root.quit()
        except Exception as e:
            logging.warning(f"Error quitting root: {e}")

        logging.info("Application shutdown complete")
        os._exit(0)

    def _check_queue(self):
        """Check translation queue for results with error handling."""
        try:
            while True:
                # Queue item format: (original, translated, target_lang, trial_info)
                result = self.translation_service.translation_queue.get_nowait()
                if len(result) == 4:
                    original, translated, target_lang, trial_info = result
                else:
                    # Backward compatibility
                    original, translated, target_lang = result
                    trial_info = None
                if self.running:
                    self.show_quick_translate(original, translated, target_lang, trial_info)
        except queue.Empty:
            pass
        except Exception as e:
            logging.error(f"Error processing queue: {e}")

        # Schedule next check if still running
        if self.running:
            try:
                if self.root.winfo_exists():
                    self.root.after(100, self._check_queue)
            except Exception as e:
                logging.error(f"Error scheduling queue check: {e}")

    def _watchdog_check(self):
        """Lightweight watchdog to monitor app health."""
        if not self.running:
            return

        try:
            # Log heartbeat every 5 minutes
            current_time = time.time()
            if not hasattr(self, '_last_heartbeat'):
                self._last_heartbeat = current_time

            if current_time - self._last_heartbeat >= 300:  # 5 minutes
                logging.info(f"Heartbeat: App running for {int((current_time - self._app_start_time) / 60)} minutes")
                self._last_heartbeat = current_time

            # Schedule next watchdog check (every 60 seconds)
            self.root.after(60000, self._watchdog_check)
        except Exception as e:
            logging.error(f"Watchdog error: {e}")


    def _show_settings_tab(self, tab_name: str):
        """Open settings window and navigate to a specific tab.

        Args:
            tab_name: Name of the tab to open (e.g., "API Key", "Dictionary", "General")
        """
        self.show_settings()

        def try_open_tab(attempts=3):
            if attempts <= 0:
                return
            if self.settings_window and hasattr(self.settings_window, 'open_tab'):
                self.settings_window.open_tab(tab_name)
                self._focus_settings_window()
            else:
                self.root.after(200, lambda: try_open_tab(attempts - 1))

        self.root.after(100, try_open_tab)

    def _show_api_error(self):
        """Show API error dialog."""
        APIErrorDialog(self.root, on_open_settings_tab=self._show_settings_tab)

    def _show_trial_exhausted(self):
        """Show trial quota exhausted dialog."""
        self.trial_manager.show_trial_exhausted()

    def _show_trial_feature_blocked(self, feature_name: str):
        """Show dialog when user tries to use a feature disabled in trial mode."""
        self.trial_manager.show_feature_blocked(feature_name)

    def is_trial_mode(self) -> bool:
        """Check if currently in trial mode."""
        return self.trial_manager.is_trial_mode()

    def _startup_api_check(self):
        """Perform a one-time API check on startup and cache results."""
        try:
            has_working_api = False
            has_vision_api = False
            
            api_keys = self.config.get_api_keys()
            manager = AIAPIManager()
            
            for config in api_keys:
                key = config.get('api_key', '').strip()
                model = config.get('model_name', '').strip()
                provider = config.get('provider', 'Auto')
                
                if key:
                    try:
                        manager.test_connection(model, key, provider)
                        self.config.api_status_cache[key] = True
                        has_working_api = True

                        # Check vision capability: use stored flag from Test, heuristic fallback
                        vision_flag = config.get('vision_capable')
                        if vision_flag is True:
                            has_vision_api = True
                        elif vision_flag is None:
                            target_provider = manager._identify_provider(model, key) if provider == 'Auto' else provider.lower()
                            if MultimodalProcessor.is_vision_capable(model, target_provider):
                                has_vision_api = True

                    except Exception as e:
                        logging.debug(f"API check failed for {model}: {e}")
                        self.config.api_status_cache[key] = False
            
            # Update runtime capabilities
            self.config.runtime_capabilities['file'] = has_working_api # Any working API can handle text files
            self.config.runtime_capabilities['vision'] = has_vision_api
            
            logging.info(f"Startup Check Results - Vision Capable: {has_vision_api}, File Capable: {has_working_api}")
            
        except Exception as e:
            logging.error(f"Startup API check failed: {e}")
            # Keep defaults (False) if check fails

    def run(self):
        """Run the application."""
        print("=" * 50)
        logging.info(f"CrossTrans v{VERSION}")
        print(f"CrossTrans v{VERSION}")
        print("=" * 50)
        print()
        print("Hotkeys:")
        for lang, hotkey in self.config.get_hotkeys().items():
            print(f"  {hotkey} → {lang}")
            logging.info(f"Hotkey: {hotkey} -> {lang}")
        print()
        print("Select any text, then press a hotkey to translate!")
        print()
        print("Listening...")
        print("-" * 50)

        # Track app start time for watchdog
        self._app_start_time = time.time()

        # Don't show API error on startup if trial mode is available
        # Trial mode provides 50 free translations/day without API key

        # Start hotkey manager thread (registers hotkeys internally)
        self.hotkey_manager.start()
        self.hotkey_manager._ready_event.wait(timeout=2.0)  # Wait for hotkeys to be registered

        # Setup tray icon - use non-blocking approach
        self._create_tray_icon()

        # Run tray icon on separate thread with proper exception handling
        def run_tray_safe():
            try:
                self.tray_icon.run()
            except Exception as e:
                logging.error(f"Tray icon error: {e}")

        tray_thread = threading.Thread(target=run_tray_safe, daemon=True)
        tray_thread.start()

        # Pre-warm NLP manager in background (non-blocking)
        # This populates cache so Dictionary tab opens instantly
        def prewarm_nlp():
            try:
                from src.core.nlp_manager import nlp_manager
                languages = nlp_manager.get_installed_languages()
                logging.info(f"NLP pre-warming complete: {len(languages)} languages cached")
            except Exception as e:
                logging.debug(f"NLP prewarm failed (non-critical): {e}")

        prewarm_thread = threading.Thread(target=prewarm_nlp, daemon=True, name="NLPPrewarm")
        prewarm_thread.start()

        # Note: Update check is already triggered in __init__ via _startup_update_check()

        # Run one-time startup API check (temporarily disabled)
        # threading.Thread(target=self._startup_api_check, daemon=True).start()

        # Start queue checker
        self.root.after(100, self._check_queue)

        # Start watchdog
        self.root.after(60000, self._watchdog_check)

        # Run main loop
        try:
            logging.info("Starting main loop")
            self.root.mainloop()
        except KeyboardInterrupt:
            logging.info("Keyboard interrupt received")
        except Exception as e:
            logging.critical(f"Main loop error: {e}", exc_info=True)
        finally:
            self.quit_app()
