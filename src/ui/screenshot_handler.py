"""
Screenshot capture and vision translation handler for CrossTrans.

Handles the screenshot hotkey, region capture, vision API processing,
and translation display.
"""
import os
import re
import logging
import threading
from typing import Optional, Callable, Tuple

from src.core import lang_id

# What the popup and History show for a screenshot whose answer lost its sections.
OCR_FALLBACK_ORIGINAL = "[Screenshot]"

# `===ORIGINAL===`, `===SOURCE LANGUAGE===`, `===TRANSLATION===` - in any order.
_SECTION_RE = re.compile(r'===\s*(ORIGINAL|SOURCE LANGUAGE|TRANSLATION)\s*===')


def ocr_prompt(target_lang: str) -> str:
    """The vision prompt: OCR, the text's language (J8), and the translation.

    The language is asked for the same reason a text translation asks for it
    (Decision 22): text written only in kanji can be Japanese or Chinese, and
    the popup reads it only when it is Japanese. Neutral wording - no language
    is named as the likelier one (Decision 21).
    """
    return f"""Extract and translate ALL visible text from this image to {target_lang}.

Instructions:
1. Perform OCR - extract ALL text exactly as it appears
2. Name the language of the extracted text
3. Translate the extracted text
4. Return format:
===ORIGINAL===
[All extracted text]

===SOURCE LANGUAGE===
[The language of the extracted text, in English - one name, e.g. Japanese, Chinese,
Korean, English. Japanese and Chinese share many characters: decide from the text
itself. Write Unknown if you cannot tell.]

===TRANSLATION===
[Translated text in {target_lang}]

5. Do NOT censor, soften, mask, or replace ANY word - including offensive, vulgar, or sensitive words; render the faithful equivalent in {target_lang}."""


def parse_ocr_result(result: str) -> Tuple[str, Optional[str], str]:
    """(original, source language or None, translation) from a vision answer.

    Sections may come in any order. Without both ORIGINAL and TRANSLATION the
    whole answer is the translation and the original is OCR_FALLBACK_ORIGINAL,
    as before. The source language is the section's first line, normalized;
    "Unknown" or a missing section is None.
    """
    marks = list(_SECTION_RE.finditer(result or ""))
    sections = {}
    for i, mark in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(result)
        sections.setdefault(mark.group(1), result[mark.end():end].strip())
    if 'ORIGINAL' not in sections or 'TRANSLATION' not in sections:
        return OCR_FALLBACK_ORIGINAL, None, result
    source_lines = sections.get('SOURCE LANGUAGE', '').splitlines()
    source = lang_id.normalize_language(source_lines[0]) if source_lines else None
    return sections['ORIGINAL'], source, sections['TRANSLATION']


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
        self._run_translation: Optional[Callable] = None

    def configure_callbacks(self,
                           on_show_quick_translate: Optional[Callable] = None,
                           get_quick_translate_manager: Optional[Callable] = None,
                           on_show_settings_tab: Optional[Callable] = None,
                           get_selected_language: Optional[Callable] = None,
                           run_translation: Optional[Callable] = None):
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
        self._run_translation = run_translation

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
                prompt = ocr_prompt(target_lang)

                result = self.translation_service.api_manager.translate_multimodal(
                    prompt, [image_path], {}
                )

                # This path calls the API manager directly instead of going
                # through TranslationService._call_model, so the credit the
                # popup shows has to be carried over by hand. Without this the
                # note would name whatever model answered the *previous*
                # translation.
                self.translation_service._set_attribution(self.translation_service.api_manager.last_attribution)

                # Parse result
                original, source_language, translated = parse_ocr_result(result)
                ocr_text = original if original != OCR_FALLBACK_ORIGINAL else ""

                # The model's verdict for the OCR text, recorded before the popup
                # opens: the popup, its Dictionary and its chooser all read it (J8).
                if ocr_text:
                    self.translation_service._remember_source_verdict(ocr_text, source_language)
                    logging.info(f"[LangID] screenshot verdict={source_language or 'none'} "
                                 f"chars={len(ocr_text)}")

                # The OCR'd Japanese with its readings above the translation, as the
                # hotkey popup shows a selection (Q6). Evidence beats the verdict.
                furigana_text = None
                if ocr_text and self.config.get_furigana_enabled():
                    verdict = lang_id.resolve(ocr_text, model=source_language)
                    if verdict.language == lang_id.JAPANESE:
                        furigana_text = self.translation_service.generate_furigana(
                            ocr_text, lang_id.JAPANESE)

                # Get trial info
                trial_info = self.translation_service.get_trial_info()

                # Show result in popup (image path preserved for "Open Translator")
                if self._on_show_quick_translate and not self._run_translation:
                    self.root.after(0, lambda: self._on_show_quick_translate(
                        original, translated, target_lang, trial_info, furigana_text))

                # Save to history - the OCR text itself, so the entry says what was
                # read (Q6); the placeholder only when the answer lost its sections.
                self.translation_service.history_manager.add_entry(
                    ocr_text or "[Screenshot OCR]", translated, target_lang,
                    source_type="screenshot",
                    model_used=self.translation_service.last_attribution or 'Auto',
                    source_lang=source_language or '',
                    source_verdict=source_language or ''
                )
                return (original, translated, target_lang, trial_info, furigana_text,
                        self.translation_service.api_manager.last_attribution)

            except Exception as e:
                if self._run_translation:
                    raise
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

        if self._run_translation:
            def completed(result):
                if self._on_show_quick_translate:
                    self._on_show_quick_translate(*result[:5], model_info=result[5] or '')
            self._run_translation(process_screenshot, target_lang, completed)
        else:
            threading.Thread(target=process_screenshot, daemon=True).start()
