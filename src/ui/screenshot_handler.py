"""
Screenshot capture and vision translation handler for CrossTrans.

Handles the screenshot hotkey, region capture, vision API processing,
and translation display.
"""
import os
import logging
import threading
from typing import Optional, Callable


class ScreenshotHandler:
    """Handles screenshot hotkey, capture, and vision translation.

    Manages the complete flow from hotkey press to translation display,
    including vision capability checking and error handling.
    """

    def __init__(self, root, config, translation_service, screenshot_capture, toast_manager):
        """Initialize the screenshot handler.

        Args:
            root: Root Tk window
            config: Config object
            translation_service: TranslationService instance
            screenshot_capture: ScreenshotCapture instance
            toast_manager: ToastManager for notifications
        """
        self.root = root
        self.config = config
        self.translation_service = translation_service
        self.screenshot_capture = screenshot_capture
        self.toast = toast_manager

        # State
        self._pending_screenshot_path: Optional[str] = None
        self._screenshot_target_language: Optional[str] = None

        # Callbacks
        self._on_show_quick_translate: Optional[Callable] = None
        self._get_quick_translate_manager: Optional[Callable] = None
        self._on_show_settings_tab: Optional[Callable] = None
        self._get_selected_language: Optional[Callable] = None

    def configure_callbacks(self,
                           on_show_quick_translate: Optional[Callable] = None,
                           get_quick_translate_manager: Optional[Callable] = None,
                           on_show_settings_tab: Optional[Callable] = None,
                           get_selected_language: Optional[Callable] = None):
        """Configure callback functions.

        Args:
            on_show_quick_translate: Callback to show translation popup
            get_quick_translate_manager: Callback to get the quick translate manager
            on_show_settings_tab: Callback to open settings and navigate to a tab
            get_selected_language: Callback to get the currently selected language
        """
        self._on_show_quick_translate = on_show_quick_translate
        self._get_quick_translate_manager = get_quick_translate_manager
        self._on_show_settings_tab = on_show_settings_tab
        self._get_selected_language = get_selected_language

    def handle_hotkey(self) -> None:
        """Handle screenshot hotkey press (Win+Alt+S).

        Checks if vision capability is available:
        - If NO vision API: Shows notification with guidance + clickable link to Settings
        - If vision API available: Opens screenshot crop overlay
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
            screenshot_lang = self._get_selected_language() if self._get_selected_language else "Vietnamese"

        # Store for later use in _on_screenshot_captured
        self._screenshot_target_language = screenshot_lang

        # Vision available - proceed with screenshot capture
        logging.info(f"Starting screenshot capture for {screenshot_lang} translation")
        self.screenshot_capture.capture_region(self._on_screenshot_captured)

    def get_pending_screenshot(self) -> Optional[str]:
        """Get path to pending screenshot if any.

        Returns:
            Path to the pending screenshot file, or None if no pending screenshot
        """
        return self._pending_screenshot_path

    def clear_pending_screenshot(self) -> None:
        """Clear pending screenshot reference (without deleting the file)."""
        self._pending_screenshot_path = None

    def cleanup_pending_screenshot(self) -> None:
        """Clean up pending screenshot file if exists."""
        if self._pending_screenshot_path:
            try:
                if os.path.exists(self._pending_screenshot_path):
                    os.unlink(self._pending_screenshot_path)
            except Exception:
                pass
            self._pending_screenshot_path = None

    def _show_vision_not_available_notification(self) -> None:
        """Show toast notification when vision capability is not available.

        Includes clickable link to open Settings -> API Key tab.
        """
        # Check if user has any API keys at all
        api_keys = self.config.get_api_keys()
        has_any_keys = any(k.get('api_key', '').strip() for k in api_keys)

        # Callback to open Settings -> API Key tab
        def open_api_key_settings():
            if self._on_show_settings_tab:
                self._on_show_settings_tab("API Key")

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

    def _on_screenshot_captured(self, image_path: str) -> None:
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

        # Get target language (saved in handle_hotkey)
        target_lang = self._screenshot_target_language
        if not target_lang:
            target_lang = self._get_selected_language() if self._get_selected_language else "Vietnamese"

        # Show loading indicator
        if self._get_quick_translate_manager:
            qt_manager = self._get_quick_translate_manager()
            if qt_manager:
                qt_manager.capture_mouse_position()
                qt_manager.show_loading(f"Screenshot -> {target_lang}")

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
[Translated text in {target_lang}]

4. Do NOT censor, soften, mask, or replace ANY word - including offensive, vulgar, or sensitive words; render the faithful equivalent in {target_lang}."""

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

                # Show result in popup (image path preserved for "Open Translator")
                if self._on_show_quick_translate:
                    self.root.after(0, lambda: self._on_show_quick_translate(original, translated, target_lang, trial_info))

                # Save to history
                self.translation_service.history_manager.add_entry(
                    "[Screenshot OCR]", translated, target_lang, source_type="screenshot"
                )

            except Exception as e:
                logging.error(f"Screenshot translation failed: {e}")
                # Close loading animation FIRST (must use after() - we're in background thread)
                if self._get_quick_translate_manager:
                    qt_manager = self._get_quick_translate_manager()
                    if qt_manager:
                        self.root.after(0, qt_manager.close)
                # Show error toast (50ms delay ensures close() executes first)
                error_msg = str(e)
                self.root.after(50, lambda: self.toast.show_error(f"Screenshot translation failed: {error_msg}"))
                # Cleanup on error
                self.cleanup_pending_screenshot()

        threading.Thread(target=process_screenshot, daemon=True).start()
