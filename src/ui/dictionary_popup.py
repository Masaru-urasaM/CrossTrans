"""
Dictionary mode for CrossTrans - the one implementation of it.

Both Dictionary buttons open it: the main window's (on the input box text) and the
quick-translate popup's (on the popup's original text, beside the popup). It owns
the whole flow - NLP availability, language detection, the "Select Source
Language" dialog, the word window (WordButtonFrame + CustomWordBoxesFrame) and the
lookup. The result window is QuickTranslateManager.show_dictionary_result().

Until 2026-10-15 the popup carried a second copy of this flow (DEFERRED D13). The
copies had drifted: the popup's dialogs used the safe topmost pattern while these
used grab_set() (D15), and a failed lookup raised NameError in both instead of
showing its message (D14).
"""
import tkinter as tk
from tkinter import BOTH, X, LEFT, RIGHT
import threading
import logging
from typing import Optional, Callable, Tuple

try:
    import ttkbootstrap as ttk
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.core import lang_id
from src.core.dictionary_prompt import dictionary_source_language
from src.core.nlp_manager import AMBIGUOUS_CJK_CONFIDENCE, nlp_manager
from src.utils.ui_helpers import filter_dictionary_words, set_dark_title_bar

# (x, y, width, height) of a window, or (left, top, right, bottom) of a work area.
Rect = Tuple[int, int, int, int]

# Detection must be at least this sure for the word window to open without asking.
DETECTION_THRESHOLD = 0.7
# Below this the detected language is not even offered as the dialog's default.
SUGGESTION_FLOOR = 0.3

# The word window: normal and expanded size, the distance it keeps from the edges
# of the work area, and its gap from the quick-translate popup it opens beside.
WORD_WINDOW_SIZE = (700, 350)
WORD_WINDOW_EXPANDED_SIZE = (1000, 700)
WORD_WINDOW_MARGIN = 10
WORD_WINDOW_ANCHOR_GAP = 10

# Taskbar allowance when the monitor's work area cannot be read.
TASKBAR_FALLBACK_PX = 50


def word_window_geometry(size: Tuple[int, int], work_area: Rect,
                         anchor: Optional[Rect] = None) -> Rect:
    """Where the word window goes, as (width, height, x, y).

    Beside the quick-translate popup when there is one (`anchor` = its x, y,
    width and height): below it, above it when there is no room below, and
    pinned to the bottom of the work area when neither fits. Without an anchor,
    centred in the work area. Always shrunk to fit inside the work area.
    """
    left, top, right, bottom = work_area
    margin = WORD_WINDOW_MARGIN
    width = min(size[0], right - left - 2 * margin)
    height = min(size[1], bottom - top - 2 * margin)

    if anchor:
        anchor_x, anchor_y, _, anchor_h = anchor
        x = anchor_x
        y = anchor_y + anchor_h + WORD_WINDOW_ANCHOR_GAP
        if y + height > bottom - margin:
            y = anchor_y - height - WORD_WINDOW_ANCHOR_GAP
            if y < top + margin:
                y = bottom - margin - height
    else:
        x = left + (right - left - width) // 2
        y = top + (bottom - top - height) // 2

    x = max(left + margin, min(x, right - margin - width))
    y = max(top + margin, min(y, bottom - margin - height))
    return width, height, x, y


def dialog_geometry(size: Tuple[int, int], pointer: Tuple[int, int],
                    work_area: Rect) -> Rect:
    """A dialog centred on the mouse pointer and kept inside the work area:
    (width, height, x, y)."""
    width, height = size
    left, top, right, bottom = work_area
    x = max(left, min(pointer[0] - width // 2, right - width))
    y = max(top, min(pointer[1] - height // 2, bottom - height))
    return width, height, x, y


class DictionaryPopup:
    """Dictionary mode: pick words from a text, look them up, show the entries.

    Manages the complete flow for both Dictionary buttons:
    - NLP availability checking
    - Language detection and selection
    - Word button window for selection
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

    def _furigana_enabled(self) -> bool:
        """Whether word chips should carry readings (Settings toggle)."""
        return bool(self.config and self.config.get_furigana_enabled())

    def configure_callbacks(self,
                           on_show_settings_tab: Optional[Callable] = None,
                           get_selected_language: Optional[Callable] = None):
        """Configure callback functions.

        Args:
            on_show_settings_tab: Callback to open settings and navigate to a tab
            get_selected_language: Callback to get the main window's target
                language - the target when the caller names none
        """
        self._on_show_settings_tab = on_show_settings_tab
        self._get_selected_language = get_selected_language

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

    def open_from_text(self, original_text: str, *, target_language: Optional[str] = None,
                       anchor: Optional[tk.Misc] = None) -> None:
        """Open Dictionary mode on a text.

        Args:
            original_text: Text to analyze and tokenize
            target_language: Language to look the words up into; None = the main
                window's selected language
            anchor: The window to open beside (the quick-translate popup), or
                None to centre the word window under the mouse
        """
        # Checked live: a pack installed since the button was drawn counts.
        if not nlp_manager.is_any_installed():
            self._show_nlp_not_installed_dialog()
            return

        if not original_text:
            self.toast.show_warning("No text to analyze")
            return

        target_language = target_language or self._selected_language()

        # Detect language
        detected_lang, confidence = nlp_manager.detect_language(original_text)

        # Kanji that prove neither Japanese nor Chinese: the model's verdict for
        # this text, else the user (Decision 22).
        if detected_lang == "Unknown" and confidence >= AMBIGUOUS_CJK_CONFIDENCE:
            self._open_ambiguous_kanji(original_text, target_language=target_language,
                                       anchor=anchor)
            return

        # Check if detection is confident and NLP is installed for that language
        if confidence >= DETECTION_THRESHOLD and nlp_manager.is_installed(detected_lang):
            # Auto-proceed with detected language
            self._open_with_language(original_text, detected_lang,
                                     target_language=target_language, anchor=anchor)
        else:
            # Determine if language was detected but not installed
            detected_but_not_installed = (
                confidence >= DETECTION_THRESHOLD and
                detected_lang and
                not nlp_manager.is_installed(detected_lang)
            )
            # Show language selection dialog with context
            self._show_language_selection_dialog(
                original_text,
                detected_lang if confidence > SUGGESTION_FLOOR else None,
                detected_but_not_installed=detected_but_not_installed,
                target_language=target_language,
                anchor=anchor
            )

    def _open_ambiguous_kanji(self, text: str, *, target_language: str,
                              anchor: Optional[tk.Misc]) -> None:
        """Kanji-only text: open in the language a model reported for it, or ask.

        The verdict comes free when the text was translated - the popup's text
        always was, the main window's input when the user pressed Translate (J4).
        Untranslated main-window input goes straight to the user: one click,
        where an identification call would cost a request and, measured on a
        word alone, comes back confidently wrong 2 times in 10 and unsure 3-4
        (Decision 26).
        """
        verdict = self._model_verdict(text)
        if verdict:
            pack = self._installed_pack(verdict)
            if pack:
                logging.info(f"[Dictionary] open language={pack} via=model-verdict")
                self._open_with_language(text, pack, trusted=True,
                                         target_language=target_language, anchor=anchor)
                return
            # The model named a language whose pack is missing: offer to install it.
            self._show_language_selection_dialog(text, verdict, detected_but_not_installed=True,
                                                 target_language=target_language, anchor=anchor)
            return
        logging.info("[Dictionary] open language=ask via=kanji-only")
        self._show_language_selection_dialog(text, None, kanji_only=True,
                                             target_language=target_language, anchor=anchor)

    def _model_verdict(self, text: str) -> Optional[str]:
        """The Japanese / Chinese verdict a model reported for exactly this text."""
        finder = getattr(self.translation_service, 'source_verdict', None)
        verdict = lang_id.normalize_language(finder(text)) if finder else None
        return verdict if verdict == lang_id.JAPANESE or verdict in lang_id.CHINESE else None

    @staticmethod
    def _installed_pack(language: str) -> Optional[str]:
        """The NLP pack to tokenize `language` with: its own, or for Chinese the
        other variant's (both segment hanzi the same way), else None."""
        if nlp_manager.is_installed(language):
            return language
        if language in lang_id.CHINESE:
            other = next(c for c in lang_id.CHINESE if c != language)
            if nlp_manager.is_installed(other):
                return other
        return None

    def _selected_language(self) -> str:
        """The main window's target language."""
        return self._get_selected_language() if self._get_selected_language else "Vietnamese"

    def _pointer(self) -> Tuple[int, int]:
        return self.root.winfo_pointerx(), self.root.winfo_pointery()

    def _work_area(self, x: int, y: int) -> Rect:
        """Work area (left, top, right, bottom) of the monitor holding (x, y)."""
        from src.ui.quick_translate import get_monitor_work_area
        work_area = get_monitor_work_area(x, y)
        if work_area:
            return work_area
        return (0, 0, self.root.winfo_screenwidth(),
                self.root.winfo_screenheight() - TASKBAR_FALLBACK_PX)

    @staticmethod
    def _window_rect(window: Optional[tk.Misc]) -> Optional[Rect]:
        """(x, y, width, height) of a live window, or None."""
        if window is None:
            return None
        try:
            if not window.winfo_exists():
                return None
            return (window.winfo_x(), window.winfo_y(),
                    window.winfo_width(), window.winfo_height())
        except tk.TclError:
            return None

    def _new_dialog(self, title: str, size: Tuple[int, int]) -> tk.Toplevel:
        """A dialog next to the mouse, raised with topmost + lift + focus_force.

        Never transient() + grab_set() (D15): on a withdrawn root they leave an
        invisible modal window that locks the whole app (CLAUDE.md Known Issues).
        """
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.configure(bg='#2b2b2b')

        pointer = self._pointer()
        width, height, x, y = dialog_geometry(size, pointer, self._work_area(*pointer))
        dialog.geometry(f"{width}x{height}+{x}+{y}")

        dialog.update_idletasks()
        set_dark_title_bar(dialog)

        dialog.attributes('-topmost', True)
        dialog.lift()
        dialog.focus_force()
        dialog.after(100, lambda: dialog.attributes('-topmost', False) if dialog.winfo_exists() else None)
        return dialog

    def _show_nlp_not_installed_dialog(self) -> None:
        """Show dialog when no NLP language pack is installed."""
        dialog = self._new_dialog("No Language Pack Installed", (400, 220))

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
                                        detected_but_not_installed: bool = False, *,
                                        kanji_only: bool = False,
                                        target_language: Optional[str] = None,
                                        anchor: Optional[tk.Misc] = None) -> None:
        """Show dialog to select source language for dictionary mode.

        Args:
            original_text: Text to analyze
            suggested_lang: Suggested language from detection
            detected_but_not_installed: True if language was detected but pack not installed
            kanji_only: The text is kanji that could be Japanese or Chinese: say so,
                and list Japanese and Chinese first
            target_language: Passed on to the word window
            anchor: Passed on to the word window
        """
        installed_languages = nlp_manager.get_installed_languages()
        if not installed_languages:
            self._show_nlp_not_installed_dialog()
            return
        if kanji_only:
            first = [lang for lang in (lang_id.JAPANESE,) + lang_id.CHINESE
                     if lang in installed_languages]
            installed_languages = first + [lang for lang in installed_languages
                                           if lang not in first]

        # Taller if showing install prompt
        dialog = self._new_dialog("Select Source Language",
                                  (400, 340 if detected_but_not_installed else 280))

        # Content
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill=BOTH, expand=True)

        # Open Settings -> Dictionary tab
        def open_settings_dict():
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
        elif kanji_only:
            # Kanji the characters cannot place: the user knows, the app does not.
            ttk.Label(frame, text="🈶 Kanji-only text: Japanese or Chinese?",
                      font=('Segoe UI', 11, 'bold')).pack(pady=(0, 6))

            ttk.Label(frame, text="These characters are written the same way in both languages,\n"
                                  "and their meaning can differ.",
                      font=('Segoe UI', 9), foreground='#888888',
                      justify='left').pack(anchor='w', pady=(0, 8))
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
                dialog.destroy()
                # Delay for focus settle before opening dictionary popup
                self.root.after(50, lambda: self._open_with_language(
                    original_text, selected, trusted=True,
                    target_language=target_language, anchor=anchor))

        def cancel():
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

    def _window_title(self, language: str, target_language: str) -> str:
        """Word window title, with the trial quota when in trial mode."""
        title = f"Dictionary ({language} → {target_language})"
        try:
            trial_info = self.translation_service.get_trial_info()
        except Exception:
            trial_info = None
        if trial_info and trial_info.get('is_trial'):
            remaining = trial_info.get('remaining', 0)
            daily_limit = trial_info.get('daily_limit', 50)
            title += f" - Trial Mode ({remaining}/{daily_limit} left)"
        return title

    def _open_with_language(self, original: str, language: str,
                            trusted: bool = False, *,
                            target_language: Optional[str] = None,
                            anchor: Optional[tk.Misc] = None) -> None:
        """Open the word window with specified language for NLP tokenization.

        Args:
            original: Text to tokenize and display
            language: Source language for NLP processing
            trusted: True when the user picked `language` in the selection
                dialog or a model's verdict chose it. Then - or when detection
                proved Japanese or Chinese - it is stated to the lookup prompt
                as fact (dictionary_source_language).
            target_language: Language to look the words up into; None = the
                main window's selected language
            anchor: The window to open beside (the quick-translate popup), or
                None to centre the word window under the mouse
        """
        from src.ui.dictionary_mode import WordButtonFrame
        from src.ui.custom_word_boxes import CustomWordBoxesFrame

        target_language = target_language or self._selected_language()

        # Create popup window (ADDITIONAL - never replaces the quick translate popup)
        dict_popup = tk.Toplevel(self.root)
        dict_popup.title(self._window_title(language, target_language))
        dict_popup.configure(bg='#2b2b2b')
        dict_popup.attributes('-topmost', True)

        # Beside the popup when there is one, else centred under the mouse,
        # inside the work area of that monitor (excludes the taskbar).
        anchor_rect = self._window_rect(anchor)
        if anchor_rect:
            work_area = self._work_area(anchor_rect[0] + anchor_rect[2] // 2,
                                        anchor_rect[1] + anchor_rect[3] // 2)
        else:
            work_area = self._work_area(*self._pointer())
        width, height, x, y = word_window_geometry(WORD_WINDOW_SIZE, work_area, anchor_rect)
        normal_geometry = f"{width}x{height}+{x}+{y}"
        dict_popup.geometry(normal_geometry)

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

        # Expand/Collapse function
        def expand_dictionary():
            if expanded_state[0]:
                # Collapse: restore original size
                dict_popup.geometry(normal_geometry)
                dict_frame.expand_btn.configure(text="⛶ Expand")
            else:
                # Expand: larger, centred on the same work area
                w, h, cx, cy = word_window_geometry(WORD_WINDOW_EXPANDED_SIZE, work_area)
                dict_popup.geometry(f"{w}x{h}+{cx}+{cy}")
                dict_frame.expand_btn.configure(text="⛶ Collapse")
            expanded_state[0] = not expanded_state[0]

        # What the lookup prompt is told the words are, or None to let the model decide.
        lookup_source = dictionary_source_language(language, trusted)

        # Word button frame with language for NLP tokenization
        def on_lookup(selected_words):
            all_words = list(selected_words)
            all_words.extend(custom_boxes.get_all_phrases())
            if all_words:
                self._do_lookup(all_words, target_language,
                                source_language=lookup_source, context_text=original)

        def on_no_selection():
            box_phrases = custom_boxes.get_all_phrases()
            if box_phrases:
                self._do_lookup(box_phrases, target_language,
                                source_language=lookup_source, context_text=original)
            else:
                self.toast.show_warning_with_shake("Please select a word or enter a custom phrase")

        dict_frame = WordButtonFrame(
            main_frame,
            original,
            on_selection_change=lambda t: None,
            on_lookup=on_lookup,
            on_expand=expand_dictionary,
            on_no_selection=on_no_selection,
            language=language,  # Pass language for NLP tokenization
            furigana_enabled=self._furigana_enabled()
        )
        dict_frame.set_exit_callback(dict_popup.destroy)
        dict_frame.pack(fill=BOTH, expand=True)

        # Custom word boxes (between text area and action buttons)
        custom_boxes = CustomWordBoxesFrame(
            dict_frame.frame, language=language,
            furigana_enabled=self._furigana_enabled())
        dict_frame.insert_custom_widget(custom_boxes.frame)
        dict_frame.set_drop_target(custom_boxes)

        # Store reference for animation control (so stop_dictionary_animation() works)
        self.quick_translate_manager._dict_popup_frame = dict_frame

        # Close on Escape
        dict_popup.bind('<Escape>', lambda e: dict_popup.destroy())
        dict_popup.focus_force()

    def _do_lookup(self, words: list, target_lang: str,
                   source_language: Optional[str] = None,
                   context_text: Optional[str] = None) -> None:
        """Perform dictionary lookup for selected words.

        Uses batch lookup (single API call) for efficiency.

        Args:
            words: List of words to look up
            target_lang: Target language for translation
            source_language: Language to state in the prompt, or None to let the
                model decide
            context_text: The text the words were selected from
        """
        if not words:
            return

        # Filter out punctuation, symbols, and special characters
        words = filter_dictionary_words(words)
        if not words:
            self.quick_translate_manager.stop_dictionary_animation()
            self.toast.show_info("No valid words to look up (only punctuation/symbols)")
            return

        # Show loading toast
        display_text = ", ".join(words[:3]) + ("..." if len(words) > 3 else "")
        self.toast.show_info(f"Looking up {len(words)} word(s): {display_text}")

        # Perform lookup in background
        def do_lookup():
            try:
                # Single API call for all words (optimized batch lookup)
                result = self.translation_service.dictionary_lookup(
                    words, target_lang, source_language=source_language, context=context_text)
                # Get trial info after API call (quota may have changed)
                trial_info = self.translation_service.get_trial_info()
                # Show result in a separate window (pass words for highlighting)
                self.root.after(0, lambda: self._show_result(result, target_lang, trial_info, words,
                                                             source_language))
            except Exception as e:
                # Bind the message now: Python unbinds `e` when this block ends,
                # long before Tk runs the callback (D14 - it raised NameError).
                message = f"Lookup failed: {e}"
                logging.error(f"[Dictionary] {message}")
                self.root.after(0, lambda: self._lookup_failed(message))

        threading.Thread(target=do_lookup, daemon=True).start()

    def _lookup_failed(self, message: str) -> None:
        """Stop the Lookup button's animation and say what went wrong."""
        self.quick_translate_manager.stop_dictionary_animation()
        self.toast.show_error(message)

    def _show_result(self, result: str, target_lang: str, trial_info: dict = None,
                     looked_up_words: list = None, source_language: Optional[str] = None) -> None:
        """Show dictionary lookup result in SEPARATE window.

        Args:
            result: Dictionary lookup result text
            target_lang: Target language
            trial_info: Trial mode info
            looked_up_words: Words that were looked up
            source_language: The language the prompt was told the words are in,
                or None - the result window then trusts each entry's field 2
        """
        # Use quick translate manager to show result in SEPARATE dictionary window
        self.quick_translate_manager.capture_mouse_position()
        self.quick_translate_manager.show_dictionary_result(result, target_lang, trial_info,
                                                            looked_up_words,
                                                            source_lang=source_language)
