"""
Main Application for CrossTrans.
"""
import os
import re
import sys
import time
import queue
import logging
import threading
import webbrowser
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
from src.ui.tooltip import TooltipManager
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
from src.core.nlp_manager import nlp_manager
from src.core.screenshot import ScreenshotCapture


def set_dark_title_bar(window):
    """Set dark title bar for Windows 10/11 windows.

    Uses Windows DWM API to enable dark mode for the title bar.
    This makes the title bar match the dark theme of the app.

    Args:
        window: Tkinter window (Tk or Toplevel)
    """
    try:
        import ctypes
        from ctypes import wintypes

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


def filter_dictionary_words(words: list) -> list:
    """Filter out punctuation, symbols, and special characters from words list.

    Args:
        words: List of words to filter

    Returns:
        Filtered list containing only valid words (at least one letter/digit)
    """
    if not words:
        return []

    filtered = []
    for word in words:
        if not word or not isinstance(word, str):
            continue
        # Strip leading/trailing punctuation and whitespace
        cleaned = word.strip()
        # Remove leading/trailing punctuation (keep internal ones like don't, e-mail)
        cleaned = re.sub(r'^[^\w]+|[^\w]+$', '', cleaned, flags=re.UNICODE)
        # Check if the cleaned word has at least one letter or CJK character
        # This allows words like "日本語" but filters out pure punctuation like "-", "...", "!!!"
        if cleaned and re.search(r'[\w\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', cleaned, re.UNICODE):
            filtered.append(cleaned)

    return filtered


class TranslatorApp:
    """Main application class."""

    def __init__(self):
        # Initialize configuration
        self.config = Config()

        # Check for version upgrade and clear cache if needed
        if self._check_version_upgrade():
            return  # App will restart after cache clear

        # Check for update status from previous run (success/failure)
        self._check_update_status()

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

        # Screenshot capture for vision/OCR translation
        self.screenshot_capture = ScreenshotCapture(self.root)

        # Tooltip manager
        self.tooltip_manager = TooltipManager(self.root)
        self.tooltip_manager.configure_callbacks(
            on_copy=self._on_tooltip_copy,
            on_open_translator=self._on_tooltip_open_translator,
            on_open_settings=self.show_settings,
            on_open_settings_dictionary_tab=self._show_settings_dictionary_tab,
            on_dictionary_lookup=self._on_tooltip_dictionary_lookup
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

        # Translation animation state
        self._translate_animation_running = False
        self._translate_animation_step = 0
        self._translate_pulse_direction = 1  # 1 = brightening, -1 = dimming
        self._translate_pulse_level = 0

        # Pending screenshot for "Open Translator" feature
        self._pending_screenshot_path: str = None
        self._screenshot_target_language: str = None

        # Check for updates on startup if enabled
        if self.config.get_auto_check_updates():
            self._startup_update_check()

        # Schedule daily API key re-check if trial mode is forced
        self._schedule_trial_recheck()

        # Show any pending update dialogs (success/failure from previous update)
        self._show_pending_update_dialogs()

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

    def _check_update_status(self) -> None:
        """Check if previous update succeeded or failed.

        Reads status files created by the update batch script:
        - crosstrans_update_error.txt: Update failed, shows error dialog
        - crosstrans_update_success.txt: Update completed
        - crosstrans_update_expected.txt: Expected version number
        - crosstrans_update_pending.txt: Path to pending update file (for reboot fallback)

        Shows appropriate feedback to user and offers MoveFileEx fallback if update failed.
        """
        temp = os.environ.get('TEMP', os.environ.get('TMP', ''))
        if not temp:
            return

        error_file = os.path.join(temp, 'crosstrans_update_error.txt')
        success_file = os.path.join(temp, 'crosstrans_update_success.txt')
        expected_file = os.path.join(temp, 'crosstrans_update_expected.txt')
        pending_file = os.path.join(temp, 'crosstrans_update_pending.txt')

        status_files = [error_file, success_file, expected_file, pending_file]

        try:
            if os.path.exists(error_file):
                # Update failed - offer reboot fallback
                error_msg = ""
                pending_path = None

                try:
                    with open(error_file, 'r') as f:
                        error_msg = f.read().strip()
                except Exception:
                    error_msg = "Unknown error"

                if os.path.exists(pending_file):
                    try:
                        with open(pending_file, 'r') as f:
                            pending_path = f.read().strip()
                    except Exception:
                        pass

                logging.warning(f"Previous update failed: {error_msg}")

                # Schedule dialog to show after UI is initialized
                self._pending_update_error = error_msg
                self._pending_update_path = pending_path

                # Cleanup status files (but keep pending for MoveFileEx if needed)
                for f in [error_file, success_file, expected_file]:
                    if os.path.exists(f):
                        try:
                            os.remove(f)
                        except Exception:
                            pass

            elif os.path.exists(success_file):
                # Check if version matches expected
                expected_ver = None
                if os.path.exists(expected_file):
                    try:
                        with open(expected_file, 'r') as f:
                            expected_ver = f.read().strip()
                    except Exception:
                        pass

                if expected_ver:
                    if VERSION == expected_ver:
                        # Success! Schedule toast after UI initialized
                        logging.info(f"Update to v{expected_ver} successful!")
                        self._pending_update_success_version = expected_ver
                    else:
                        # Version mismatch - update failed silently
                        logging.error(f"Update verification failed: Expected v{expected_ver} but running v{VERSION}")
                        self._pending_update_error = f"Expected v{expected_ver} but running v{VERSION}"
                        self._pending_update_path = None

                # Cleanup all status files
                for f in status_files:
                    if os.path.exists(f):
                        try:
                            os.remove(f)
                        except Exception:
                            pass

        except Exception as e:
            logging.warning(f"Error checking update status: {e}")

    def _show_pending_update_dialogs(self) -> None:
        """Show any pending update dialogs after main window is ready.

        Called after the main UI components are initialized.
        """
        # Show update success toast
        if hasattr(self, '_pending_update_success_version'):
            version = self._pending_update_success_version
            del self._pending_update_success_version
            self.root.after(2000, lambda: self._show_update_success_toast(version))

        # Show update failed dialog
        if hasattr(self, '_pending_update_error'):
            error_msg = self._pending_update_error
            pending_path = getattr(self, '_pending_update_path', None)
            del self._pending_update_error
            if hasattr(self, '_pending_update_path'):
                del self._pending_update_path
            self.root.after(1000, lambda: self._show_update_failed_dialog(error_msg, pending_path))

    def _show_update_success_toast(self, version: str) -> None:
        """Show success toast after update.

        Args:
            version: The version that was successfully installed
        """
        self.toast.show(
            "Update Successful",
            f"CrossTrans has been updated to v{version}",
            duration=5000
        )

    def _show_update_failed_dialog(self, error_msg: str, pending_path: str = None) -> None:
        """Show dialog when update failed, offering reboot fallback.

        Args:
            error_msg: Error message from the failed update
            pending_path: Path to the pending update file (for MoveFileEx fallback)
        """
        from src.ui.dialogs import UpdateFailedDialog

        dialog = UpdateFailedDialog(
            self.root,
            error_msg,
            pending_path,
            current_exe=sys.executable
        )

        if dialog.result == 'reboot' and pending_path:
            # User chose to schedule update for reboot
            from src.utils.updates import AutoUpdater
            updater = AutoUpdater()
            result = updater.schedule_update_on_reboot(pending_path, sys.executable)

            if result['success']:
                self.toast.show(
                    "Update Scheduled",
                    "Update will be applied when you restart Windows.",
                    duration=5000
                )
                # Clean up pending file marker
                pending_file = os.path.join(
                    os.environ.get('TEMP', ''),
                    'crosstrans_update_pending.txt'
                )
                if os.path.exists(pending_file):
                    try:
                        os.remove(pending_file)
                    except Exception:
                        pass
            else:
                self.toast.show(
                    "Scheduling Failed",
                    result.get('message', 'Could not schedule update'),
                    duration=5000,
                    toast_type=ToastType.ERROR
                )

        elif dialog.result == 'manual':
            # Open GitHub releases page
            import webbrowser
            from src.constants import GITHUB_REPO
            webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases/latest")

    def _schedule_trial_recheck(self):
        """Schedule re-check of API keys when in forced trial mode."""
        if not self.config.get_trial_mode_forced():
            return

        # Check if we need to re-test (24h since last check)
        last_check = self.config.get_trial_last_api_check()
        if last_check:
            try:
                from datetime import datetime, timedelta
                last_dt = datetime.fromisoformat(last_check)
                if datetime.now() - last_dt >= timedelta(hours=24):
                    # Time to re-check
                    self.root.after(5000, self._recheck_api_keys_for_trial)
            except Exception as e:
                logging.warning(f"Failed to parse last API check time: {e}")

        # Schedule next check in 1 hour
        self.root.after(3600000, self._schedule_trial_recheck)  # 1 hour

    def _recheck_api_keys_for_trial(self):
        """Re-check API keys and disable trial mode if any works."""
        from datetime import datetime
        from src.core.api_manager import AIAPIManager

        logging.info("Re-checking API keys for trial mode...")

        api_keys = self.config.get_api_keys()
        if not api_keys:
            return

        manager = AIAPIManager()
        any_working = False

        for key_config in api_keys:
            key = key_config.get('api_key', '').strip()
            if not key:
                continue

            model = key_config.get('model_name', '').strip() or 'Auto'
            provider = key_config.get('provider', 'Auto')

            try:
                if manager.test_connection(model, key, provider):
                    any_working = True
                    self.config.api_status_cache[key] = True
                    logging.info(f"API key now working: {key[:8]}...")
                    break
            except Exception:
                self.config.api_status_cache[key] = False

        # Update last check time
        self.config.set_trial_last_api_check(datetime.now().isoformat())

        if any_working:
            # Disable trial mode
            self.config.set_trial_mode_forced(False)
            logging.info("API key now working - disabled forced trial mode")

            # Show toast notification
            self.toast.show(
                "API Key Restored",
                "Your API key is now working. Trial mode disabled.",
                duration=5000
            )

    def _startup_update_check(self) -> None:
        """Silent update check on startup (non-intrusive).

        Checks for updates in background thread after app initialization.
        Shows toast notification if update available.
        """
        def check_updates():
            import time
            time.sleep(STARTUP_UPDATE_DELAY)  # Wait for app to fully load

            logging.info("Auto-checking for updates on startup...")
            updater = AutoUpdater()
            result = updater.check_update()

            if result.get('has_update'):
                new_version = result['version']
                logging.info(f"Update available: {new_version}")
                # Show non-intrusive toast notification
                self.root.after(0, lambda: self._show_update_toast(new_version))
            else:
                logging.info("No update available on startup check")

        threading.Thread(
            target=check_updates,
            daemon=True,
            name=THREAD_NAMES['startup']
        ).start()

    def _show_update_toast(self, new_version: str) -> None:
        """Show non-intrusive update notification as toast.

        Args:
            new_version: Version number of the available update (e.g., "1.9.7")
        """
        from src.ui.toast import show_toast
        show_toast(
            self.root,
            "Update Available",
            f"CrossTrans v{new_version} is available!\nOpen Settings to update.",
            duration=UPDATE_TOAST_DURATION
        )

    def _on_hotkey_translate(self, language: str):
        """Handle hotkey translation request.

        Args:
            language: Target language name, or "__screenshot__" for screenshot OCR
        """
        # Check for special screenshot hotkey
        if language == "__screenshot__":
            self.root.after(0, self._on_screenshot_hotkey)
            return

        # Normal language translation
        # Capture mouse position immediately when hotkey is pressed
        self.tooltip_manager.capture_mouse_position()

        self.root.after(0, lambda: self.tooltip_manager.show_loading(language))
        self.translation_service.do_translation(language)

    def _on_screenshot_hotkey(self):
        """Handle screenshot hotkey press (Win+Alt+S).

        Checks if vision capability is available:
        - If NO vision API → Shows notification with guidance + clickable link to Settings
        - If vision API available → Opens screenshot crop overlay
        """
        # Check if any API has vision capability
        has_vision = self.config.has_any_vision_capable()

        if not has_vision:
            # Show notification explaining the situation with action link
            self._show_vision_not_available_notification()
            return

        # Get screenshot target language from settings
        screenshot_lang = self.config.get_screenshot_target_language()
        if screenshot_lang == "Auto":
            screenshot_lang = self.selected_language

        # Store for later use in _on_screenshot_captured
        self._screenshot_target_language = screenshot_lang

        # Vision available - proceed with screenshot capture
        logging.info(f"Starting screenshot capture for {screenshot_lang} translation")
        self.screenshot_capture.capture_region(self._on_screenshot_captured)

    def _show_vision_not_available_notification(self):
        """Show toast notification when vision capability is not available.

        Includes clickable link to open Settings → API Key tab.
        """
        # Check if user has any API keys at all
        api_keys = self.config.get_api_keys()
        has_any_keys = any(k.get('api_key', '').strip() for k in api_keys)

        # Callback to open Settings → API Key tab
        def open_api_key_settings():
            self._show_settings_tab("API Key")

        if not has_any_keys:
            # No API keys at all - using Trial Mode
            self.toast.show_warning_with_action(
                "Screenshot translation requires an API key.\n"
                "Trial Mode does not support image processing.\n"
                "Add a vision-capable API key (GPT-4o, Gemini Pro Vision, Claude 3, etc.)",
                "Open API Key Settings",
                open_api_key_settings
            )
        else:
            # Has API keys but none support vision
            self.toast.show_warning_with_action(
                "No vision-capable API key found.\n"
                "Your current API keys don't support image processing.\n"
                "Add a vision model: GPT-4o, Gemini Pro Vision, Claude 3 Sonnet, etc.",
                "Open API Key Settings",
                open_api_key_settings
            )

        logging.info("Screenshot hotkey pressed but no vision capability available")

    def _on_screenshot_captured(self, image_path: str):
        """Handle captured screenshot image.

        Args:
            image_path: Path to captured screenshot PNG file, or None if cancelled
        """
        if not image_path:
            logging.info("Screenshot capture cancelled by user")
            return

        logging.info(f"Screenshot captured: {image_path}")

        # Save image path for "Open Translator" feature (DON'T delete immediately)
        self._pending_screenshot_path = image_path

        # Get target language (saved in _on_screenshot_hotkey)
        target_lang = self._screenshot_target_language or self.selected_language

        # Show loading indicator
        self.tooltip_manager.capture_mouse_position()
        self.tooltip_manager.show_loading(f"Screenshot → {target_lang}")

        # Process in background thread
        def process_screenshot():
            try:
                # Use multimodal translation with the captured image
                prompt = f"""Extract and translate ALL visible text from this image to {target_lang}.

Instructions:
1. Perform OCR - extract ALL text exactly as it appears
2. Translate the extracted text
3. Return format:
===ORIGINAL===
[All extracted text]

===TRANSLATION===
[Translated text in {target_lang}]"""

                result = self.translation_service.api_manager.translate_multimodal(
                    prompt, [image_path], {}
                )

                # Parse result
                if "===ORIGINAL===" in result and "===TRANSLATION===" in result:
                    parts = result.split("===TRANSLATION===")
                    original = parts[0].replace("===ORIGINAL===", "").strip()
                    translated = parts[1].strip() if len(parts) > 1 else ""
                else:
                    original = "[Screenshot]"
                    translated = result

                # Get trial info
                trial_info = self.translation_service.get_trial_info()

                # Show result in tooltip (image path preserved for "Open Translator")
                self.root.after(0, lambda: self.show_tooltip(original, translated, target_lang, trial_info))

                # Save to history
                self.translation_service.history_manager.add_entry(
                    "[Screenshot OCR]", translated, target_lang, source_type="screenshot"
                )

            except Exception as e:
                logging.error(f"Screenshot translation failed: {e}")
                self.root.after(0, lambda: self.toast.show_error(f"Screenshot translation failed: {str(e)}"))
                # Cleanup on error
                self._cleanup_pending_screenshot()

        import threading
        threading.Thread(target=process_screenshot, daemon=True).start()

    def _cleanup_pending_screenshot(self):
        """Clean up pending screenshot file if exists."""
        if self._pending_screenshot_path:
            try:
                if os.path.exists(self._pending_screenshot_path):
                    os.unlink(self._pending_screenshot_path)
            except Exception:
                pass
            self._pending_screenshot_path = None

    def show_tooltip(self, original: str, translated: str, target_lang: str, trial_info: dict = None):
        """Show compact tooltip near mouse cursor with translation result.

        Args:
            original: Original text
            translated: Translated text
            target_lang: Target language
            trial_info: Optional trial mode info dict
        """
        self.current_original = original
        self.current_translated = translated
        self.current_target_lang = target_lang

        # Check if trial quota is exhausted - show dialog instead of tooltip
        if trial_info and trial_info.get('is_exhausted'):
            self._show_trial_exhausted()
            return

        self.tooltip_manager.show(translated, target_lang, trial_info, original)

    def close_tooltip(self):
        """Close the tooltip."""
        self.tooltip_manager.close()

    def _on_tooltip_copy(self):
        """Handle copy from tooltip."""
        pyperclip.copy(self.current_translated)
        self.tooltip_manager.set_copy_button_text("Copied!")
        self.toast.show_success("Copied to clipboard!")
        # Reset button text after 1 second
        self.root.after(1000, lambda: self.tooltip_manager.set_copy_button_text("Copy"))

    def _on_tooltip_open_translator(self):
        """Handle open translator from tooltip."""
        self.close_tooltip()

        # Check if there's a pending screenshot to load into attachments
        pending_image = self._pending_screenshot_path

        self.show_popup(
            self.current_original,
            self.current_translated,
            self.current_target_lang,
            pending_attachment=pending_image
        )

        # Clear pending screenshot (will be managed by AttachmentArea now)
        self._pending_screenshot_path = None

    def _on_tooltip_dictionary_lookup(self, words: list, target_lang: str):
        """Handle dictionary lookup from tooltip.

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
                # Show result in a new tooltip at mouse position (pass words for highlighting)
                self.root.after(0, lambda: self._show_tooltip_dictionary_result(result, target_lang, trial_info, filtered_words))
            except Exception as e:
                # Stop animation on error
                self.root.after(0, lambda: self.tooltip_manager.stop_dictionary_animation())
                self.root.after(0, lambda: self.toast.show_error(f"Lookup failed: {str(e)}"))

        import threading
        threading.Thread(target=do_lookup, daemon=True).start()

    def _show_tooltip_dictionary_result(self, result: str, target_lang: str, trial_info: dict = None,
                                        looked_up_words: list = None):
        """Show dictionary result in a SEPARATE window (not replacing quick translate)."""
        # Create a new SEPARATE dictionary result window
        self.tooltip_manager.capture_mouse_position()
        self.tooltip_manager.show_dictionary_result(result, target_lang, trial_info, looked_up_words)

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

        # Open Gemini button
        if HAS_TTKBOOTSTRAP:
            self.gemini_btn = ttk.Button(btn_frame, text="✦ Open Gemini",
                                         command=self._open_in_gemini,
                                         bootstyle="info", width=15)
        else:
            self.gemini_btn = ttk.Button(btn_frame, text="✦ Open Gemini",
                                         command=self._open_in_gemini, width=15)
        self.gemini_btn.pack(side=LEFT)

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
                self.attachment_area = AttachmentArea(content_frame, self.config, on_change=None)
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
        if not translated:
            self.toast.show_warning("No translation to expand")
            return

        # Create expanded window
        expanded = tk.Toplevel(self.root)
        expanded.title(f"Translation - {self.selected_language}")
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
        header_frame.pack(fill=tk.X, pady=(0, 10))

        # Title
        title_text = f"Translation to {self.selected_language}"
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
            text = expanded_text.get('1.0', tk.END).strip()
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

        # Text widget - editable for selection/copy
        expanded_text = tk.Text(text_frame, wrap=tk.WORD,
                                bg='#2b2b2b', fg='#ffffff',
                                font=('Segoe UI', 14), relief='flat',
                                padx=20, pady=20,
                                insertbackground='white',
                                selectbackground='#0d6efd',
                                selectforeground='white')
        expanded_text.insert('1.0', translated)
        expanded_text.pack(fill=BOTH, expand=True)

        # Mouse wheel scroll only
        expanded_text.bind('<MouseWheel>',
            lambda e: expanded_text.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Keyboard shortcuts
        expanded.bind('<Escape>', lambda e: expanded.destroy())
        expanded.bind('<F11>', lambda e: toggle_fullscreen())
        expanded.bind('<Control-c>', lambda e: copy_expanded())

        # Status bar
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=(10, 0))

        # Character/word count
        def update_status(*args):
            text = expanded_text.get('1.0', 'end-1c')
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

        # Update status on text change
        expanded_text.bind('<KeyRelease>', update_status)

        # Bring window to front and focus it
        expanded.lift()
        expanded.attributes('-topmost', True)
        expanded.update()
        expanded.attributes('-topmost', False)
        expanded.focus_force()
        expanded_text.focus_set()

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
        """Update Dictionary button state based on NLP availability.

        Button keeps same visual appearance (reddish-brown color) whether
        enabled or disabled. Only interaction changes.
        """
        if not hasattr(self, 'dict_btn') or not self.dict_btn:
            return

        self._dict_btn_enabled = nlp_manager.is_any_installed()

        try:
            if self._dict_btn_enabled:
                self.dict_btn.configure(cursor='hand2')
            else:
                self.dict_btn.configure(cursor='arrow')
            # Unbind any previous tooltips
            self.dict_btn.unbind('<Enter>')
            self.dict_btn.unbind('<Leave>')
        except tk.TclError:
            pass  # Widget destroyed

    def _open_dictionary_popup(self):
        """Open dictionary popup window with word buttons for original text."""
        # Check if button is enabled (NLP installed)
        if hasattr(self, '_dict_btn_enabled') and not self._dict_btn_enabled:
            self._show_nlp_not_installed_dialog()
            return

        original = self.original_text.get('1.0', tk.END).strip()
        if not original:
            self.toast.show_warning("No text to analyze")
            return

        # Double-check NLP is installed
        if not nlp_manager.is_any_installed():
            self._show_nlp_not_installed_dialog()
            return

        # Detect language
        detected_lang, confidence = nlp_manager.detect_language(original)
        CONFIDENCE_THRESHOLD = 0.7

        # Check if detection is confident and NLP is installed for that language
        if confidence >= CONFIDENCE_THRESHOLD and nlp_manager.is_installed(detected_lang):
            # Auto-proceed with detected language
            self._open_dictionary_with_language(original, detected_lang)
        else:
            # Determine if language was detected but not installed
            detected_but_not_installed = (
                confidence >= CONFIDENCE_THRESHOLD and
                detected_lang and
                not nlp_manager.is_installed(detected_lang)
            )
            # Show language selection dialog with context
            self._show_language_selection_dialog(
                original,
                detected_lang if confidence > 0.3 else None,
                detected_but_not_installed=detected_but_not_installed
            )

    def _show_nlp_not_installed_dialog(self):
        """Show dialog when no NLP language pack is installed."""
        dialog = tk.Toplevel(self.popup)
        dialog.title("No Language Pack Installed")
        dialog.configure(bg='#2b2b2b')
        dialog.transient(self.popup)
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
            self._show_settings_tab("Dictionary")

        open_btn_kwargs = {"text": "Open Dictionary Settings", "command": open_settings, "width": 22}
        if HAS_TTKBOOTSTRAP:
            open_btn_kwargs["bootstyle"] = "primary"
        ttk.Button(btn_frame, **open_btn_kwargs).pack(side=LEFT, padx=5)

        cancel_kwargs = {"text": "Cancel", "command": dialog.destroy, "width": 10}
        if HAS_TTKBOOTSTRAP:
            cancel_kwargs["bootstyle"] = "secondary"
        ttk.Button(btn_frame, **cancel_kwargs).pack(side=RIGHT, padx=5)

        dialog.bind('<Escape>', lambda e: dialog.destroy())

    def _show_settings_dictionary_tab(self):
        """Open settings window and navigate directly to Dictionary tab.

        Used by tooltip "Install now" link to open Dictionary tab directly.
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

    def _show_language_selection_dialog(self, original_text: str, suggested_lang: str = None,
                                         detected_but_not_installed: bool = False):
        """Show dialog to select source language for dictionary mode.

        Args:
            original_text: Text to analyze
            suggested_lang: Suggested language from detection
            detected_but_not_installed: True if language was detected but pack not installed
        """
        installed_languages = nlp_manager.get_installed_languages()
        if not installed_languages:
            self._show_nlp_not_installed_dialog()
            return

        dialog = tk.Toplevel(self.popup)
        dialog.title("Select Source Language")
        dialog.configure(bg='#2b2b2b')
        dialog.transient(self.popup)
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

        # Open Settings → Dictionary tab
        def open_settings_dict():
            dialog.grab_release()  # Release grab before destroying
            dialog.destroy()
            # Delay for focus settle, then open settings
            self.root.after(50, self.show_settings)
            self.root.after(550, lambda: self._open_settings_dictionary_tab())

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
                self.root.after(50, lambda: self._open_dictionary_with_language(original_text, selected))

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

    def _open_dictionary_with_language(self, original: str, language: str):
        """Open dictionary popup with specified language for NLP tokenization."""
        from src.ui.dictionary_mode import WordButtonFrame
        from src.ui.tooltip import get_monitor_work_area

        # Get current target language from UI selection (not config)
        target_language = self.selected_language

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
            self._do_dictionary_lookup(selected_words)

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
        self.tooltip_manager._dict_popup_frame = dict_frame

        # Close on Escape
        dict_popup.bind('<Escape>', lambda e: dict_popup.destroy())
        dict_popup.focus_force()

    def _do_dictionary_lookup(self, words: list):
        """Perform dictionary lookup for selected words.

        Uses batch lookup (single API call) for efficiency.
        """
        if not words:
            return

        # Get target language
        target_lang = self.selected_language

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
                # Show result in tooltip (pass words for highlighting)
                self.popup.after(0, lambda: self._show_dictionary_result(result, target_lang, trial_info, words))
            except Exception as e:
                self.popup.after(0, lambda: self.toast.show_error(f"Lookup failed: {str(e)}"))

        import threading
        threading.Thread(target=do_lookup, daemon=True).start()

    def _show_dictionary_result(self, result: str, target_lang: str, trial_info: dict = None,
                                looked_up_words: list = None):
        """Show dictionary lookup result in SEPARATE window."""
        # Use tooltip manager to show result in SEPARATE dictionary window
        self.tooltip_manager.capture_mouse_position()
        self.tooltip_manager.show_dictionary_result(result, target_lang, trial_info, looked_up_words)

    def _open_in_gemini(self):
        """Open Gemini web with translation prompt."""
        original = self.original_text.get('1.0', tk.END).strip()
        if not original:
            self.toast.show_warning("No content to translate")
            return

        prompt = f"Translate the following text to {self.selected_language}:\n\n{original}"
        pyperclip.copy(prompt)
        self.gemini_btn.configure(text="Copied! Opening...")
        self.toast.show_info("Prompt copied! Opening Gemini...")
        webbrowser.open("https://gemini.google.com/app")
        self.popup.after(2000, lambda: self.gemini_btn.configure(text="✦ Open Gemini"))

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

    def _open_settings_from_error(self):
        """Open settings from error tooltip."""
        self.close_tooltip()
        self.show_settings()

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
                        self._content_frame, self.config, on_change=None
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

        # Close tooltip
        self.close_tooltip()

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
                    self.show_tooltip(original, translated, target_lang, trial_info)
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
        TrialExhaustedDialog(self.root, on_open_settings_tab=self._show_settings_tab)

    def _show_trial_feature_blocked(self, feature_name: str):
        """Show dialog when user tries to use a feature disabled in trial mode."""
        TrialFeatureDialog(self.root, feature_name=feature_name, on_open_settings_tab=self._show_settings_tab)

    def is_trial_mode(self) -> bool:
        """Check if currently in trial mode."""
        return self.translation_service.is_trial_mode()

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

                        # Check vision capability for this working key
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
