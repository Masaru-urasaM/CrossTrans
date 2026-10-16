"""
Translation Service for CrossTrans.
Handles text translation using AI APIs with clipboard integration.
"""
import time
import queue
import logging
import threading
from collections import OrderedDict
from typing import Optional, Callable, Tuple, Dict

import keyboard

from src.constants import COOLDOWN, TRIAL_MODE_ENABLED, TRIAL_MODEL, TRIAL_PROXY_URL
from src.core import furigana
from src.core.text_cleanup import strip_thinking_tags
from src.core.clipboard import ClipboardManager
from src.core.dictionary_prompt import build_dictionary_prompt, extract_context
from src.core import lang_id
from src.core.source_marker import (parse_source_marker, source_clause, stated_clause,
                                    strip_stray_markers)
from src.core.api_manager import AIAPIManager
from src.core.history import HistoryManager
from src.core.provider_health import ProviderHealthManager
from src.core.quota_manager import QuotaManager
from src.core.trial_api import TrialAPIClient, TrialAPIError
from config import Config


class TranslationService:
    """Handles all translation-related operations."""

    # The language a model reported for the most recent translation of ambiguous
    # kanji-only text (its [[SOURCE: ...]] line, Decision 22), or None. Like
    # last_attribution: read it right after the call it belongs to. Class-level
    # defaults, because tests and tools build the service with __new__.
    last_source_language: Optional[str] = None
    # Verdicts for the texts translated this session, newest last; History keeps
    # them across restarts (source_verdict()).
    SOURCE_VERDICTS_MAX = 64
    _source_verdicts_lock = threading.Lock()

    def __init__(self, config: Config,
                 notification_callback: Optional[Callable[[str], None]] = None) -> None:
        self.config: Config = config
        self.api_manager: AIAPIManager = AIAPIManager()
        self.last_translation_time: float = 0
        self.last_grammar_fix_time: float = 0
        self.translation_queue: queue.Queue[Tuple[str, str, str, Optional[Dict]]] = queue.Queue()
        self.notification_callback: Optional[Callable[[str], None]] = notification_callback
        self.history_manager: HistoryManager = HistoryManager(config)
        self.health_manager: ProviderHealthManager = ProviderHealthManager(config)
        self.quota_manager: QuotaManager = QuotaManager(config)
        self.trial_client: Optional[TrialAPIClient] = None
        self._is_trial_mode: bool = False
        # Who produced the most recent result: "model (Provider)", the trial
        # proxy, or a cache hit's stored credit. The popup shows it as a note;
        # None means "nothing worth naming" and the note is left off entirely.
        self.last_attribution: Optional[str] = None
        self._configure_api()

    def _configure_api(self) -> bool:
        """Configure the AI API with all keys and health manager.

        Returns:
            bool: True if valid API key exists or trial mode is available.
        """
        api_keys = self.config.get_api_keys()
        model_rotation = self.config.get_model_rotation()
        self.api_manager.configure(api_keys, self.notification_callback, self.health_manager,
                                   model_rotation_enabled=model_rotation)

        # Check if there's at least one valid (non-empty) API key
        has_valid_key = False
        for config in api_keys:
            key = config.get('api_key', '').strip()
            if key:
                # Check cache - if cached as True or never tested, assume valid
                cached = self.config.api_status_cache.get(key)
                if cached is True or cached is None:
                    has_valid_key = True
                    break

        # Check if trial mode is forced by user
        trial_forced = self.config.get_trial_mode_forced()

        # Check trial availability with debug logging
        trial_available = self._is_trial_available()
        logging.info(f"[Trial] has_valid_key={has_valid_key}, trial_forced={trial_forced}, trial_available={trial_available}")
        logging.info(f"[Trial] TRIAL_MODE_ENABLED={TRIAL_MODE_ENABLED}, TRIAL_PROXY_URL='{TRIAL_PROXY_URL}'")

        # Determine if trial mode should be used:
        # 1. No valid key AND trial available (auto-detect)
        # 2. OR trial forced by user
        self._is_trial_mode = (not has_valid_key and trial_available) or (trial_forced and trial_available)

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

    @staticmethod
    def _is_japanese_text(text: str) -> bool:
        """Check if text contains Japanese characters (hiragana, katakana, or kanji)."""
        return furigana.is_japanese(text)

    @staticmethod
    def generate_furigana(text: str, lang_hint: Optional[str] = None) -> Optional[str]:
        """Generate furigana annotations for Japanese text (offline).

        Delegates to src.core.furigana, which aligns each reading onto the kanji
        runs inside its token (so okurigana is never covered by the ruby) and
        suppresses any reading it cannot map deterministically.

        Args:
            text: Source text to annotate.
            lang_hint: Language name the caller already knows, e.g. "Japanese".
                Needed for kanji-only text, which has no kana to prove it is
                Japanese rather than Chinese.

        Returns:
            String with {kanji|reading} notation, or None when no ruby applies.
        """
        return furigana.generate_notation(text, lang_hint)

    def _strip_thinking_tags(self, text: str) -> str:
        """Remove AI thinking/reasoning tags from response.

        The API manager already strips its own results; this still covers the
        trial-proxy path, which does not go through it.

        Args:
            text: Raw API response text

        Returns:
            Cleaned text with thinking tags removed
        """
        return strip_thinking_tags(text)

    def translate_text(self, text: str, target_language: str,
                       custom_prompt: Optional[str] = None,
                       skip_cache: bool = False,
                       source_language: Optional[str] = None) -> str:
        """Translate text to target language using AI API.

        Args:
            text: Source text to translate.
            target_language: Target language name.
            custom_prompt: Optional extra instructions (disables caching for this call).
            skip_cache: When True, bypass the history-backed cache and always call the
                API (used by the popup "Re-translate" button to force a fresh result).
            source_language: A source language the user settled (the popup's
                Japanese / Chinese chooser): stated to the model, and recorded as
                this text's verdict.
        """
        has_custom_prompt = custom_prompt and custom_prompt.strip()

        # Cache lookup: plain translations only (no custom prompt) and only when not
        # explicitly skipped. Reuses the translation history as an exact-match cache so
        # identical input is not re-sent to the API. On a hit we return early WITHOUT
        # re-adding to history (avoids duplicate entries). See redo_translation() for the
        # forced-refresh path.
        if not has_custom_prompt and not skip_cache:
            cached = self.history_manager.find_cached_entry(text, target_language)
            if cached is not None:
                logging.info("Cache hit - returning stored translation, skipping API call")
                self.last_attribution = self._cached_attribution(cached)
                self.last_source_language = cached.get('source_verdict') or None
                return cached['translated']
        self.last_source_language = None

        if has_custom_prompt:
            # Has custom prompt → follow custom prompt, more flexible.
            # The source text MUST be embedded so the model has something to act on
            # (this was previously omitted — see R2-bug fix).
            base_prompt = f"""Translate the text below to {target_language}.

===TEXT TO TRANSLATE===
{text}
===END OF TEXT===

Only return the translation, no explanations or additional text.
If the text is already in {target_language}, still provide a natural rephrasing.
Do NOT censor, soften, mask, or replace ANY word - including offensive, vulgar, or sensitive words; render the faithful equivalent.

Additional instructions from user: {custom_prompt}"""
        else:
            # No custom prompt (quick hotkey translation) → enforce target language
            # Structure: text first with delimiters, then rules at end
            base_prompt = f"""Translate the text below to {target_language}.

===TEXT TO TRANSLATE===
{text}
===END OF TEXT===

Rules (DO NOT include these in your response):
1. Output ONLY the translation in {target_language}
2. No explanations, no meta-text, no repetition of these rules
3. If already in {target_language}, return as-is or rephrase naturally
4. Do NOT censor, soften, mask, or replace ANY word - including offensive, vulgar, or sensitive words; render the faithful equivalent in {target_language}."""

        prompt = base_prompt

        try:
            if has_custom_prompt:
                # The user's own instructions are sent exactly as written.
                result, verdict = self._strip_thinking_tags(self._call_model(prompt)), None
            else:
                result, verdict = self._call_with_source(prompt, text, source_language)
            self._remember_source_verdict(text, verdict)

            # Save to history on success. Custom-prompt results are tagged 'custom' so the
            # R1 cache (find_cached) never serves them in place of a plain translation,
            # while still keeping them visible in the history viewer.
            self.history_manager.add_entry(
                text, result, target_language,
                source_type='custom' if has_custom_prompt else 'text',
                model_used=self.last_attribution or 'Auto',
                source_lang=verdict or '', source_verdict=verdict or '')
            return result
        except TrialAPIError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            error_msg = str(e)
            if "API_KEY_INVALID" in error_msg or "API key not valid" in error_msg:
                return "Error: Invalid API key. Please check your API key in Settings."
            return f"Error: {error_msg}"

    def translate_or_fix(self, text: str, target_language: str,
                         skip_cache: bool = False) -> str:
        """Translate text to target_language, OR grammar-fix it in place when it is
        already in that language — the model decides via ONE merged prompt.

        Used by the language hotkeys (Win+Alt+V/E/J/C and any custom language hotkey):
        pressing a language hotkey on text already in that language is a pointless
        translation, so the model instead corrects grammar/spelling/punctuation in place
        (minimal changes, same language). BOTH branches are uncensored and
        meaning-preserving — offensive words survive (faithful equivalent when
        translating, verbatim when fixing).

        Results are cached/stored under source_type='merged' so a minimal-change fix is
        never cross-served as a plain 'rephrase' translation, or vice versa.

        Args:
            text: Source text.
            target_language: The hotkey's target language name.
            skip_cache: When True, always call the API (bypass the merged cache).

        Returns:
            The translated-or-corrected text, or an "Error: ..." string.
        """
        if not text or not text.strip():
            return ""

        # Merged cache namespace: never mixes with plain translations (see find_cached).
        if not skip_cache:
            cached = self.history_manager.find_cached_entry(text, target_language,
                                                            source_type='merged')
            if cached is not None:
                logging.info("Merged cache hit - returning stored result, skipping API call")
                self.last_attribution = self._cached_attribution(cached)
                self.last_source_language = cached.get('source_verdict') or None
                return cached['translated']
        self.last_source_language = None

        prompt = f"""You are a translation-and-grammar fixer tool. Decide automatically between two modes based on the
language of the text below, then output ONLY the result.

===TEXT===
{text}
===END OF TEXT===

DECISION RULE:
- If the text is ENTIRELY or PREDOMINANTLY already in {target_language}, do NOT translate it.
  Instead, correct ONLY its grammar, spelling, and punctuation, keeping the SAME language and the
  SAME meaning (minimal changes; if it is already correct, return it unchanged).
- Otherwise, TRANSLATE the text into {target_language}, preserving the full meaning and tone.

STRICT RULES (DO NOT include these rules in your response):
1. Output ONLY the final result - no explanations, no labels, no quotes, no meta-text, no notes
   about which mode you chose.
2. Never change the meaning. In grammar-fix mode make the minimal changes needed for correctness;
   do not paraphrase, restyle, or change vocabulary/tone. In translate mode, translate faithfully.
3. Do NOT add or remove information. Every piece of the original text is important and must be preserved in the output.
4. Do NOT censor, soften, mask, euphemize, or replace ANY word - including offensive, vulgar,
   slur, or sensitive words. In grammar-fix mode keep every such word exactly as written; in
   translate mode render its faithful equivalent in {target_language}. Never omit or asterisk them.
5. In grammar-fix mode, output the corrected text in the EXACT SAME language as the input; never
   translate it. In translate mode, output ONLY {target_language}."""

        try:
            result, verdict = self._call_with_source(prompt, text)
            self._remember_source_verdict(text, verdict)

            # Store under the 'merged' namespace so repeat requests are cached but never
            # served in place of (or served) a plain translation.
            self.history_manager.add_entry(
                text, result, target_language, source_type='merged',
                model_used=self.last_attribution or 'Auto',
                source_lang=verdict or '', source_verdict=verdict or '')
            return result
        except TrialAPIError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            error_msg = str(e)
            if "API_KEY_INVALID" in error_msg or "API key not valid" in error_msg:
                return "Error: Invalid API key. Please check your API key in Settings."
            return f"Error: {error_msg}"

    def dictionary_lookup(self, text, target_language: str,
                          source_language: Optional[str] = None,
                          context: Optional[str] = None) -> str:
        """Perform dictionary lookup for one or more words.

        Accepts either a single word/phrase (str) or a list of words.
        For multiple words, makes a single optimized API call.

        Args:
            text: Word/phrase (str) or list of words to look up
            target_language: Target language for definitions/translations
            source_language: The words' language when the caller knows it - see
                `dictionary_prompt.dictionary_source_language()`. None lets the model
                decide, and it names its decision in field 2.
            context: The text the words were selected from. Only the sentences that
                contain a word are sent (`dictionary_prompt.extract_context()`).

        Returns:
            Dictionary-formatted response with translation, definition, etc.
        """
        # Normalize input: convert string to single-item list
        if isinstance(text, str):
            words = [text]
        else:
            words = list(text)

        if not words:
            return ""

        context_text = extract_context(context, words)
        # Counts and language names only - never the user's text.
        logging.info(f"[Dictionary] lookup n={len(words)} source={source_language or 'auto'} "
                     f"target={target_language} context_chars={len(context_text)}")
        prompt = build_dictionary_prompt(words, target_language, source_language, context_text)

        try:
            result = self._call_model(prompt)

            # Clean up AI thinking tags from result
            result = self._strip_thinking_tags(result)
            return result
        except TrialAPIError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            error_msg = str(e)
            if "API_KEY_INVALID" in error_msg or "API key not valid" in error_msg:
                return "Error: Invalid API key. Please check your API key in Settings."
            return f"Error: {error_msg}"

    def fix_grammar(self, text: str) -> str:
        """Correct grammar, spelling, and punctuation of text WITHOUT translating it.

        The output is the SAME text in the SAME language with only grammatical errors
        fixed. It does NOT paraphrase, change vocabulary/meaning/tone, add or remove
        information, or censor any word (including offensive ones). If the text is already
        correct it is returned unchanged. Used by the Fix Grammar hotkey and the main
        window "Fix Grammar" button. The result is NOT written to history.

        Args:
            text: Source text whose grammar should be corrected.

        Returns:
            The grammar-corrected text in the same language, or an "Error: ..." string.
        """
        if not text or not text.strip():
            return ""

        # Strict prompt: fix only grammar, never translate, never censor, never rephrase.
        prompt = f"""You are a grammar correction tool. Correct ONLY the grammar, spelling, and punctuation of the text below.

===TEXT===
{text}
===END OF TEXT===

STRICT RULES (DO NOT include these rules in your response):
1. Output the corrected text in the EXACT SAME LANGUAGE as the input. NEVER translate it.
2. Fix ONLY grammar, spelling, punctuation, subject-verb agreement, verb tense, articles, prepositions, and word order.
3. Make the MINIMAL changes needed for grammatical correctness.
4. Do NOT paraphrase, improve style, change vocabulary, or alter the meaning or tone.
5. Do NOT add or remove information.
6. Do NOT censor, soften, mask, or replace ANY word - including offensive, vulgar, or sensitive words. Keep every word exactly as written.
7. If the text is already grammatically correct, return it unchanged.
8. Output ONLY the corrected text - no explanations, no quotes, no labels, no meta-text."""

        try:
            result = self._call_model(prompt)

            # Clean up AI thinking tags from result
            result = self._strip_thinking_tags(result)
            return result
        except TrialAPIError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            error_msg = str(e)
            if "API_KEY_INVALID" in error_msg or "API key not valid" in error_msg:
                return "Error: Invalid API key. Please check your API key in Settings."
            return f"Error: {error_msg}"

    def _call_with_source(self, prompt: str, text: str,
                          source_language: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """Call the model about `text` with its source-language clause appended.

        Mostly-CJK text gets its language stated when the characters prove it, or
        the model is asked to name it on a marker line, which is read and removed
        here (Decision 22, `source_marker`). Any other text is sent unchanged.
        A `source_language` the user settled is stated instead, and is the verdict.

        Returns:
            (result without the marker, the verdict or None)
        """
        if source_language:
            clause = stated_clause(source_language)
            result = self._strip_thinking_tags(self._call_model(prompt + clause.text))
            logging.info(f"[LangID] translation verdict={clause.stated} via=user "
                         f"chars={len(text)}")
            return strip_stray_markers(result), clause.stated
        clause = source_clause(text)
        result = self._strip_thinking_tags(self._call_model(prompt + clause.text))
        if not clause.asks:
            return strip_stray_markers(result), None
        result, verdict, found = parse_source_marker(result)
        # Counts and language names only - never the user's text.
        logging.info(f"[LangID] translation verdict={verdict or 'none'} "
                     f"marker={'found' if found else 'missing'} chars={len(text)}")
        return result, verdict

    def _source_verdict_store(self) -> "OrderedDict[str, str]":
        store = self.__dict__.get('_source_verdicts')
        if store is None:
            with self._source_verdicts_lock:
                store = self.__dict__.setdefault('_source_verdicts', OrderedDict())
        return store

    def _remember_source_verdict(self, text: str, verdict: Optional[str]) -> None:
        """Record a call's verdict: as `last_source_language`, and for the text."""
        self.last_source_language = verdict
        if not verdict or not text:
            return
        self._store_source_verdict(text, verdict)

    def _store_source_verdict(self, text: str, verdict: str) -> None:
        store = self._source_verdict_store()
        with self._source_verdicts_lock:
            store[text] = verdict
            store.move_to_end(text)
            while len(store) > self.SOURCE_VERDICTS_MAX:
                store.popitem(last=False)

    def remember_user_source(self, text: str, language: str) -> Optional[str]:
        """Record the language the user settled for `text` outside a translation -
        the Dictionary's "Kanji-only text: Japanese or Chinese?" dialog, or before
        a re-translation the user asked for (K3).

        Kept like a model's verdict: for this session, and on History's entries
        of exactly this text so it survives a restart - where it replaces a
        model's, since the user's pick outranks it (Decision 22). It leaves
        `last_source_language` alone: that belongs to the last translation.

        Returns:
            The verdict recorded, or None when `language` is neither Japanese nor
            Chinese (a pick of another pack says nothing about the kanji).
        """
        verdict = lang_id.normalize_language(language)
        if not text or not (verdict == lang_id.JAPANESE or verdict in lang_id.CHINESE):
            return None
        self._store_source_verdict(text, verdict)
        setter = getattr(getattr(self, 'history_manager', None), 'set_source_verdict', None)
        if setter:
            setter(text, verdict)
        # Counts and language names only - never the user's text.
        logging.info(f"[LangID] user settled source={verdict} chars={len(text)}")
        return verdict

    def source_language(self, text: str) -> Optional[str]:
        """The language of a source text as far as it is settled: its characters
        first, else the verdict for exactly this text (Decision 22), else None.
        Never a guess, and never a request."""
        if not text or not text.strip():
            return None
        return lang_id.resolve(text, model=self.source_verdict(text.strip())).language

    def _source_hint(self, text: str) -> Optional[str]:
        """The reading hint for a source text: "Japanese" when source_language()
        says so, else None."""
        return lang_id.JAPANESE if self.source_language(text) == lang_id.JAPANESE else None

    def source_verdict(self, text: str) -> Optional[str]:
        """The language a model reported for exactly this text, or None.

        This session's translations first, then History, which keeps verdicts
        across restarts. Only ever a model's verdict - never a label guessed from
        the characters (History's `source_lang` is often that).
        """
        if not text:
            return None
        store = self._source_verdict_store()
        with self._source_verdicts_lock:
            verdict = store.get(text)
        if verdict:
            return verdict
        finder = getattr(self.history_manager, 'find_source_verdict', None)
        return finder(text) if finder else None

    def _call_model(self, prompt: str) -> str:
        """Send one prompt to whichever backend is active and record who answered.

        Every live call in this class goes through here, so `last_attribution`
        is set in exactly one place. A normal call names whatever the API
        manager actually reached - not necessarily the configured model, since
        auto-detection and model rotation substitute one silently. Trial mode
        names its fixed proxy model instead.

        Failures propagate: the attribution is only touched on success, so a
        failed call never credits a model with a result it did not produce.
        """
        if self._is_trial_mode and self.trial_client:
            result = self._translate_trial(prompt)
            self.last_attribution = f"{TRIAL_MODEL} (Trial mode)"
            return result
        result = self.api_manager.translate(prompt)
        self.last_attribution = self.api_manager.last_attribution
        return result

    @staticmethod
    def _cached_attribution(entry: Dict) -> Optional[str]:
        """Credit for a cache hit: whoever produced the stored entry.

        Entries written before the credit was recorded carry the placeholder
        'Auto', which names nothing - those get no note at all rather than a
        made-up one. Crediting the model that merely ran most recently would be
        worse than saying nothing.
        """
        stored = (entry.get('model_used') or '').strip()
        if not stored or stored == 'Auto':
            return None
        return f"{stored}, cached"

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

        Queue item format: (original_text, translated_text, target_language, trial_info, furigana_text)
        trial_info is a dict if in trial mode, None otherwise.
        furigana_text is a string with {kanji|reading} notation if furigana enabled, None otherwise.
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

                # Normal translation (always)
                translated = self.translate_text(selected_text, target_language, custom_prompt)

                # Generate furigana offline if enabled and source is Japanese
                furigana_text = None
                if (not custom_prompt and self.config.get_furigana_enabled()
                        and self._is_japanese_text(selected_text)):
                    logging.info("Japanese text detected, generating furigana offline")
                    furigana_text = self.generate_furigana(selected_text)

                logging.info("Translation complete!")

                # Include trial info if in trial mode
                trial_info = self.get_trial_info()
                self.translation_queue.put((selected_text, translated, target_language, trial_info, furigana_text))
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

    def do_translate_or_fix(self, target_language: str) -> None:
        """Merged translate-or-fix for the language hotkeys (Win+Alt+V/E/J/C + custom).

        Mirrors do_translation() (captures the live selection via Ctrl+C, honors the
        shared translation cooldown, surfaces trial info, generates furigana for Japanese
        source) but calls translate_or_fix() so the model auto-decides between translating
        and grammar-fixing text already in target_language. The result is queued as the
        same 5-tuple as do_translation() (is_grammar stays False downstream) because the
        output is always genuinely in target_language in both branches.
        """
        current_time = time.time()
        if current_time - self.last_translation_time < COOLDOWN:
            logging.info("Cooldown active, please wait...")
            self.translation_queue.put(("", "Please wait a moment...", target_language, None))
            return

        self.last_translation_time = current_time
        logging.info(f"Translate-or-fix for {target_language}...")

        try:
            if not self._configure_api():
                error_msg = "Error: No API key configured.\n\nPlease add your AI API key in Settings.\n\nGo to Settings > Guide tab for instructions on getting a free API key."
                logging.warning(error_msg)
                self.translation_queue.put(("", error_msg, target_language, None))
                return

            selected_text = self.get_selected_text()

            if selected_text:
                logging.info(f"Selected text: {selected_text[:50]}...")

                # One merged prompt: translate, or grammar-fix if already in target_language.
                result = self.translate_or_fix(selected_text, target_language)

                # Generate furigana offline if enabled and source is Japanese. The
                # hint lets kanji-only text the model called Japanese be read (J6).
                furigana_text = None
                if (self.config.get_furigana_enabled()
                        and self._is_japanese_text(selected_text)):
                    logging.info("Japanese text detected, generating furigana offline")
                    furigana_text = self.generate_furigana(selected_text,
                                                           self._source_hint(selected_text))

                logging.info("Translate-or-fix complete!")

                # Include trial info if in trial mode
                trial_info = self.get_trial_info()
                self.translation_queue.put((selected_text, result, target_language, trial_info, furigana_text))
            else:
                error_msg = "No text selected. Please select text and try again."
                logging.warning(error_msg)
                self.translation_queue.put(("", error_msg, target_language, None))
        except TrialAPIError as e:
            error_msg = f"Error: {str(e)}"
            logging.error(error_msg)
            trial_info = self.get_trial_info()
            if trial_info:
                if "exhausted" in str(e).lower() or "quota" in str(e).lower():
                    trial_info['is_exhausted'] = True
            self.translation_queue.put(("", error_msg, target_language, trial_info))
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            logging.error(error_msg)
            self.translation_queue.put(("", error_msg, target_language, None))

    def redo_translation(self, text: str, target_language: str,
                         source_language: Optional[str] = None) -> None:
        """Force a fresh API translation of already-known text (bypass cache).

        Used by the Quick Translate popup "Re-translate" button when a cached or
        previous result is bad, so the user is never stuck with it. Unlike
        do_translation(), this does NOT capture the selection again and does NOT apply
        COOLDOWN — it operates on text already obtained. The result is pushed to
        translation_queue in the same 5-tuple format as do_translation().

        `source_language` is the popup chooser's answer for kanji-only text the
        model could not place (J6): stated to the model, and recorded.
        """
        logging.info(f"Re-translating to {target_language} (forced, skip cache)...")

        try:
            if not self._configure_api():
                error_msg = "Error: No API key configured.\n\nPlease add your AI API key in Settings.\n\nGo to Settings > Guide tab for instructions on getting a free API key."
                logging.warning(error_msg)
                self.translation_queue.put(("", error_msg, target_language, None))
                return

            if not text:
                error_msg = "No text to re-translate."
                logging.warning(error_msg)
                self.translation_queue.put(("", error_msg, target_language, None))
                return

            # Force a real API call, bypassing the history-backed cache.
            translated = self.translate_text(text, target_language, skip_cache=True,
                                             source_language=source_language)

            # Generate furigana offline if enabled and source is Japanese (plain path).
            furigana_text = None
            if self.config.get_furigana_enabled() and self._is_japanese_text(text):
                logging.info("Japanese text detected, generating furigana offline")
                furigana_text = self.generate_furigana(text, self._source_hint(text))

            logging.info("Re-translation complete!")

            trial_info = self.get_trial_info()
            self.translation_queue.put((text, translated, target_language, trial_info, furigana_text))
        except TrialAPIError as e:
            error_msg = f"Error: {str(e)}"
            logging.error(error_msg)
            trial_info = self.get_trial_info()
            if trial_info:
                if "exhausted" in str(e).lower() or "quota" in str(e).lower():
                    trial_info['is_exhausted'] = True
            self.translation_queue.put(("", error_msg, target_language, trial_info))
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            logging.error(error_msg)
            self.translation_queue.put(("", error_msg, target_language, None))

    def do_grammar_fix(self) -> None:
        """Fix the grammar of the currently selected text and queue the result.

        Mirrors do_translation() (captures the live selection via Ctrl+C, honors a
        cooldown, surfaces trial info) but calls fix_grammar() instead of translating.
        The result is pushed to translation_queue as a 6-tuple
        (original, corrected, "Grammar", trial_info, None, True) so the queue checker can
        route it to the grammar popup (Copy/Replace only). Not saved to history.
        """
        current_time = time.time()
        if current_time - self.last_grammar_fix_time < COOLDOWN:
            logging.info("Grammar-fix cooldown active, please wait...")
            self.translation_queue.put(("", "Please wait a moment...", "Grammar", None, None, True))
            return

        self.last_grammar_fix_time = current_time
        logging.info("Fixing grammar of selected text...")

        try:
            if not self._configure_api():
                error_msg = "Error: No API key configured.\n\nPlease add your AI API key in Settings.\n\nGo to Settings > Guide tab for instructions on getting a free API key."
                logging.warning(error_msg)
                self.translation_queue.put(("", error_msg, "Grammar", None, None, True))
                return

            selected_text = self.get_selected_text()

            if selected_text:
                logging.info(f"Selected text for grammar fix: {selected_text[:50]}...")

                corrected = self.fix_grammar(selected_text)

                logging.info("Grammar fix complete!")

                # Include trial info if in trial mode
                trial_info = self.get_trial_info()
                self.translation_queue.put((selected_text, corrected, "Grammar", trial_info, None, True))
            else:
                error_msg = "No text selected. Please select text and try again."
                logging.warning(error_msg)
                self.translation_queue.put(("", error_msg, "Grammar", None, None, True))
        except TrialAPIError as e:
            error_msg = f"Error: {str(e)}"
            logging.error(error_msg)
            trial_info = self.get_trial_info()
            if trial_info:
                if "exhausted" in str(e).lower() or "quota" in str(e).lower():
                    trial_info['is_exhausted'] = True
            self.translation_queue.put(("", error_msg, "Grammar", trial_info, None, True))
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            logging.error(error_msg)
            self.translation_queue.put(("", error_msg, "Grammar", None, None, True))

    def ask_freeform(self, raw_prompt: str, target_language: str) -> None:
        """Send a raw user-authored prompt to the AI verbatim (freeform ask).

        Used by the Quick Translate popup "Custom Prompt" mode: the entire editable-box
        content IS the prompt — there is NO translate wrapper, so this does not depend on
        the custom_prompt branch of translate_text(). Freeform asks are one-offs: the
        result is NOT written to history and is never served from / written to the R1
        cache. The result is pushed to translation_queue in the same 5-tuple format as
        do_translation() (furigana off for freeform).

        Args:
            raw_prompt: The exact prompt text to send to the model.
            target_language: Target language (used only for trial info / display context).
        """
        logging.info("Freeform custom-prompt request...")

        try:
            if not self._configure_api():
                error_msg = "Error: No API key configured.\n\nPlease add your AI API key in Settings.\n\nGo to Settings > Guide tab for instructions on getting a free API key."
                logging.warning(error_msg)
                self.translation_queue.put(("", error_msg, target_language, None))
                return

            if not raw_prompt or not raw_prompt.strip():
                error_msg = "No prompt provided."
                logging.warning(error_msg)
                self.translation_queue.put(("", error_msg, target_language, None))
                return

            # Raw path: send the prompt verbatim, bypassing the translate wrapper.
            result = self._call_model(raw_prompt)

            result = self._strip_thinking_tags(result)

            logging.info("Freeform custom-prompt complete!")

            # Intentionally NOT saved to history (one-off ask, not a reusable translation).
            trial_info = self.get_trial_info()
            self.translation_queue.put((raw_prompt, result, target_language, trial_info, None))
        except TrialAPIError as e:
            error_msg = f"Error: {str(e)}"
            logging.error(error_msg)
            trial_info = self.get_trial_info()
            if trial_info:
                if "exhausted" in str(e).lower() or "quota" in str(e).lower():
                    trial_info['is_exhausted'] = True
            self.translation_queue.put(("", error_msg, target_language, trial_info))
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            logging.error(error_msg)
            self.translation_queue.put(("", error_msg, target_language, None))
