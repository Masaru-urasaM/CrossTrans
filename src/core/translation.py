"""
Translation Service for CrossTrans.
Handles text translation using AI APIs with clipboard integration.
"""
import time
import queue
import logging
from typing import Optional, Callable, Tuple, Any, Dict

import keyboard

from src.constants import COOLDOWN, TRIAL_MODE_ENABLED, TRIAL_PROXY_URL
from src.core.clipboard import ClipboardManager
from src.core.api_manager import AIAPIManager
from src.core.history import HistoryManager
from src.core.provider_health import ProviderHealthManager
from src.core.quota_manager import QuotaManager
from src.core.trial_api import TrialAPIClient, TrialAPIError
from config import Config


class TranslationService:
    """Handles all translation-related operations."""

    def __init__(self, config: Config,
                 notification_callback: Optional[Callable[[str], None]] = None) -> None:
        self.config: Config = config
        self.api_manager: AIAPIManager = AIAPIManager()
        self.last_translation_time: float = 0
        self.translation_queue: queue.Queue[Tuple[str, str, str, Optional[Dict]]] = queue.Queue()
        self.notification_callback: Optional[Callable[[str], None]] = notification_callback
        self.history_manager: HistoryManager = HistoryManager(config)
        self.health_manager: ProviderHealthManager = ProviderHealthManager(config)
        self.quota_manager: QuotaManager = QuotaManager(config)
        self.trial_client: Optional[TrialAPIClient] = None
        self._is_trial_mode: bool = False
        self._configure_api()

    def _configure_api(self) -> bool:
        """Configure the AI API with all keys and health manager.

        Returns:
            bool: True if valid API key exists or trial mode is available.
        """
        api_keys = self.config.get_api_keys()
        self.api_manager.configure(api_keys, self.notification_callback, self.health_manager)

        # Check if there's at least one valid (non-empty) API key
        has_valid_key = False
        for config in api_keys:
            if config.get('api_key', '').strip():
                has_valid_key = True
                break

        # Check trial availability with debug logging
        trial_available = self._is_trial_available()
        logging.info(f"[Trial] has_valid_key={has_valid_key}, trial_available={trial_available}")
        logging.info(f"[Trial] TRIAL_MODE_ENABLED={TRIAL_MODE_ENABLED}, TRIAL_PROXY_URL='{TRIAL_PROXY_URL}'")

        # Determine if trial mode should be used
        self._is_trial_mode = not has_valid_key and trial_available

        if self._is_trial_mode and self.trial_client is None:
            self.trial_client = TrialAPIClient(self.quota_manager.device_id)
            logging.info("Trial mode activated - using proxy for translations")

        result = has_valid_key or self._is_trial_mode
        logging.info(f"[Trial] _is_trial_mode={self._is_trial_mode}, _configure_api returning={result}")
        return result

    def _is_trial_available(self) -> bool:
        """Check if trial mode is available and configured."""
        return bool(TRIAL_MODE_ENABLED and TRIAL_PROXY_URL)

    def is_trial_mode(self) -> bool:
        """Check if currently operating in trial mode."""
        return self._is_trial_mode

    def get_trial_info(self) -> Optional[Dict]:
        """Get trial mode information for display.

        Returns:
            Dict with trial info if in trial mode, None otherwise.
        """
        if not self._is_trial_mode:
            return None

        quota_info = self.quota_manager.get_quota_info()
        return {
            'is_trial': True,
            'remaining': quota_info['remaining'],
            'daily_limit': quota_info['daily_limit'],
            'is_exhausted': quota_info['is_exhausted'],
            'message': self.quota_manager.get_quota_message()
        }

    def reconfigure(self):
        """Reconfigure API (call after API key change)."""
        self._configure_api()

    def _is_dictionary_query(self, text: str) -> bool:
        """Check if text looks like a dictionary lookup (single word/short phrase)."""
        words = text.strip().split()
        # 1-3 words, no sentence punctuation
        return 1 <= len(words) <= 4 and not any(c in text for c in '.!?;:')

    def translate_text(self, text: str, target_language: str,
                       custom_prompt: Optional[str] = None) -> str:
        """Translate text to target language using AI API."""
        has_custom_prompt = custom_prompt and custom_prompt.strip()

        if has_custom_prompt:
            # Has custom prompt → follow custom prompt, more flexible
            base_prompt = f"""Translate the following text to {target_language}.
Only return the translation, no explanations or additional text.
If the text is already in {target_language}, still provide a natural rephrasing.

Additional instructions from user: {custom_prompt}"""
        elif self._is_dictionary_query(text):
            # Dictionary Mode
            base_prompt = f"""You are a dictionary. For the input text, provide:

1. **Translation to {target_language}**: [translation]
2. **Definition**: [meaning in {target_language}]
3. **Word Type**: [noun/verb/adjective/adverb/etc.]
4. **Pronunciation**: [IPA if available]
5. **Example Sentences**:
   - [Example 1] -> [Translation]
   - [Example 2] -> [Translation]

Format with markdown. Keep explanations concise."""
        else:
            # No custom prompt (quick hotkey translation) → enforce target language
            base_prompt = f"""Translate the following text to {target_language}.

IMPORTANT: Your response MUST be in {target_language} only.
- Return ONLY the translation, no explanations or additional text
- If text is already in {target_language}, return it as-is or rephrase naturally IN {target_language}
- NEVER output in any language other than {target_language}
"""

        prompt = f"{base_prompt}\n\nText to translate:\n{text}"

        try:
            # Use trial mode if active
            if self._is_trial_mode and self.trial_client:
                result = self._translate_trial(prompt)
            else:
                result = self.api_manager.translate(prompt)

            # Save to history on success
            self.history_manager.add_entry(text, result, target_language)
            return result
        except TrialAPIError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            error_msg = str(e)
            if "API_KEY_INVALID" in error_msg or "API key not valid" in error_msg:
                return "Error: Invalid API key. Please check your API key in Settings."
            return f"Error: {error_msg}"

    def _translate_trial(self, prompt: str) -> str:
        """Translate using trial mode API.

        Args:
            prompt: Translation prompt.

        Returns:
            str: Translated text.

        Raises:
            TrialAPIError: If trial translation fails.
        """
        # Check quota first
        if not self.quota_manager.is_quota_available():
            raise TrialAPIError(self.quota_manager.get_exhausted_message())

        # Make translation request
        result = self.trial_client.translate(prompt)

        # Decrement quota on success
        self.quota_manager.use_quota()

        return result

    def get_selected_text(self) -> Optional[str]:
        """Get currently selected text by simulating Ctrl+C."""
        original_clipboard = ClipboardManager.save_clipboard()

        for attempt in range(3):
            try:
                ClipboardManager.set_text("")
                time.sleep(0.05)

                keyboard.press_and_release('ctrl+c')
                time.sleep(0.15 + (attempt * 0.1))

                new_text = ClipboardManager.get_text()
                if new_text and new_text.strip():
                    return new_text

            except Exception as e:
                logging.warning(f"Attempt {attempt + 1} failed: {e}")

        ClipboardManager.restore_clipboard(original_clipboard)
        return None

    def do_translation(self, target_language: str,
                        callback: Optional[Callable[[], None]] = None,
                        custom_prompt: str = "") -> None:
        """Perform translation and put result in queue.

        Queue item format: (original_text, translated_text, target_language, trial_info)
        trial_info is a dict if in trial mode, None otherwise.
        """
        current_time = time.time()
        if current_time - self.last_translation_time < COOLDOWN:
            logging.info("Cooldown active, please wait...")
            self.translation_queue.put(("", "Please wait a moment...", target_language, None))
            return

        self.last_translation_time = current_time
        logging.info(f"Translating to {target_language}...")

        try:
            if not self._configure_api():
                error_msg = "Error: No API key configured.\n\nPlease add your AI API key in Settings.\n\nGo to Settings > Guide tab for instructions on getting a free API key."
                logging.warning(error_msg)
                self.translation_queue.put(("", error_msg, target_language, None))
                return

            selected_text = self.get_selected_text()

            if selected_text:
                logging.info(f"Selected text: {selected_text[:50]}...")
                translated = self.translate_text(selected_text, target_language, custom_prompt)
                logging.info("Translation complete!")

                # Include trial info if in trial mode
                trial_info = self.get_trial_info()
                self.translation_queue.put((selected_text, translated, target_language, trial_info))
            else:
                error_msg = "No text selected. Please select text and try again."
                logging.warning(error_msg)
                self.translation_queue.put(("", error_msg, target_language, None))
        except TrialAPIError as e:
            # Include trial info for trial mode errors (especially quota exhausted)
            error_msg = f"Error: {str(e)}"
            logging.error(error_msg)
            trial_info = self.get_trial_info()
            if trial_info:
                # Mark as exhausted if this is a quota error
                if "exhausted" in str(e).lower() or "quota" in str(e).lower():
                    trial_info['is_exhausted'] = True
            self.translation_queue.put(("", error_msg, target_language, trial_info))
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            logging.error(error_msg)
            self.translation_queue.put(("", error_msg, target_language, None))
