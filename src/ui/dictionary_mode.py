"""
Dictionary mode UI for word-by-word lookup in CrossTrans.

Provides interactive word selection with click, drag, and shift+drag support.
Words flow like a paragraph with automatic line wrapping.
Uses NLP tokenization for smart compound word recognition when available.
"""
import re
import tkinter as tk
from tkinter import LEFT, RIGHT, BOTH, X, TOP, BOTTOM, W
from typing import Callable, Optional

try:
    import ttkbootstrap as ttk
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

# Dictionary button colors (dark red)
DICT_BUTTON_COLOR = "#822312"  # Dark red (main color)
DICT_BUTTON_ACTIVE = '#9A3322'  # Lighter red (hover/active)
DICT_BUTTON_PULSE_COLORS = ["#822312", '#923322', '#A24332', '#923322']  # Pulse animation


class WordLabel:
    """Individual clickable word label that flows in text."""

    def __init__(self, parent_text: tk.Text, word: str, index: int,
                 on_click: Callable, on_drag_enter: Callable):
        """Initialize word label.

        Args:
            parent_text: Parent Text widget to embed in
            word: The word text to display
            index: Index of this word in the sentence
            on_click: Callback when clicked (index, event)
            on_drag_enter: Callback when mouse drags over (index)
        """
        self.word = word
        self.index = index
        self.selected = False
        self.on_click = on_click
        self.on_drag_enter = on_drag_enter
        self.parent_text = parent_text

        # Create label (will be embedded in Text widget)
        self.label = tk.Label(
            parent_text, text=word,
            font=('Segoe UI', 11),
            bg='#2b2b2b', fg='#ffffff',
            padx=2, pady=1, cursor='hand2'
        )

        # Bind events
        self.label.bind('<Button-1>', self._handle_click)
        self.label.bind('<Enter>', self._handle_enter)
        self.label.bind('<Leave>', self._handle_leave)

    def _handle_click(self, event):
        """Handle mouse click on word."""
        self.on_click(self.index, event)

    def _handle_enter(self, event):
        """Handle mouse entering word area."""
        # Check if left mouse button is pressed (dragging)
        if event.state & 0x100:  # Button1 pressed
            self.on_drag_enter(self.index)
        elif not self.selected:
            # Hover effect - underline
            self.label.configure(font=('Segoe UI', 11, 'underline'))

    def _handle_leave(self, event):
        """Handle mouse leaving word area."""
        if not self.selected:
            self.label.configure(font=('Segoe UI', 11))

    def set_selected(self, selected: bool):
        """Set selection state with visual feedback."""
        self.selected = selected
        if selected:
            self.label.configure(bg='#fd7e14', fg='#ffffff',
                               font=('Segoe UI', 11, 'bold'))  # Orange highlight
        else:
            self.label.configure(bg='#2b2b2b', fg='#ffffff',
                               font=('Segoe UI', 11))  # Default

    def destroy(self):
        """Destroy the label widget."""
        self.label.destroy()


class WordButtonFrame:
    """Container displaying text as clickable words with selection support.

    Words flow like a paragraph with automatic line wrapping.
    Uses NLP tokenization for smart compound word recognition when available.
    """

    def __init__(self, parent, text: str, on_selection_change: Callable[[str], None],
                 on_lookup: Optional[Callable[[str], None]] = None,
                 on_expand: Optional[Callable[[], None]] = None,
                 on_no_selection: Optional[Callable[[], None]] = None,
                 language: Optional[str] = None):
        """Initialize word button frame.

        Args:
            parent: Parent widget
            text: Text to split into word buttons
            on_selection_change: Callback when selection changes (selected_text)
            on_lookup: Callback when lookup is triggered (selected_text)
            on_expand: Callback when expand button is clicked
            on_no_selection: Callback when lookup clicked but no words selected
            language: Language for NLP tokenization (e.g., "Vietnamese", "Japanese")
        """
        self.parent = parent
        self.on_selection_change = on_selection_change
        self.on_lookup = on_lookup
        self.on_expand = on_expand
        self.on_no_selection = on_no_selection
        self.language = language
        self.word_labels: list[WordLabel] = []
        self.selected_indices: set[int] = set()
        self.anchor_index: Optional[int] = None
        self.drag_start_index: Optional[int] = None

        # Main container frame
        self.frame = ttk.Frame(parent)

        # === ACTION BUTTONS FRAME (pack FIRST at BOTTOM to ensure always visible) ===
        self.action_frame = ttk.Frame(self.frame)
        self.action_frame.pack(side=BOTTOM, fill=X, pady=(5, 5), padx=5)

        # === TEXT WIDGET (pack AFTER action_frame to fill remaining space) ===
        # No fixed height - expands to fit all content
        self.text_widget = tk.Text(
            self.frame,
            wrap=tk.WORD,
            bg='#2b2b2b',
            fg='#ffffff',
            font=('Segoe UI', 11),
            relief='flat',
            padx=10, pady=10,
            cursor='arrow',
            borderwidth=0,
            highlightthickness=0
        )
        self.text_widget.pack(side=TOP, fill=BOTH, expand=True, padx=5, pady=5)

        # Make text widget read-only but allow selection via embedded labels
        self.text_widget.configure(state='disabled')

        # Parse text and create word labels
        self._create_word_labels(text)

        # Dictionary Lookup button - reddish-brown background
        self.lookup_btn = tk.Button(
            self.action_frame,
            text="Dictionary Lookup",
            command=self._trigger_lookup,
            autostyle=False,  # Prevent ttkbootstrap from overriding colors
            bg=DICT_BUTTON_COLOR,
            fg='#ffffff',
            activebackground=DICT_BUTTON_ACTIVE,
            activeforeground='#ffffff',
            font=('Segoe UI', 10),
            relief='flat',
            padx=12, pady=4,
            cursor='hand2'
        )
        self.lookup_btn.pack(side=LEFT, padx=2)

        # Clear selection button - gray-white background with black text
        self.clear_btn = tk.Button(
            self.action_frame,
            text="Clear",
            command=self.clear_selection,
            bg='#d0d0d0',      # Gray-white background
            fg='#000000',      # Black text
            activebackground='#e0e0e0',
            activeforeground='#000000',
            font=('Segoe UI', 10),
            relief='flat',
            padx=8, pady=4,
            cursor='hand2',
            width=6
        )
        self.clear_btn.pack(side=LEFT, padx=2)

        # Expand button
        expand_kwargs = {"text": "⛶ Expand", "command": self._trigger_expand, "width": 10}
        if HAS_TTKBOOTSTRAP:
            expand_kwargs["bootstyle"] = "info-outline"
        self.expand_btn = ttk.Button(self.action_frame, **expand_kwargs)
        self.expand_btn.pack(side=LEFT, padx=2)

        # Exit button
        exit_kwargs = {"text": "Exit", "command": self._trigger_exit, "width": 6}
        if HAS_TTKBOOTSTRAP:
            exit_kwargs["bootstyle"] = "secondary-outline"
        self.exit_btn = ttk.Button(self.action_frame, **exit_kwargs)
        self.exit_btn.pack(side=RIGHT, padx=2)

        # Callbacks (set by parent)
        self._on_exit: Optional[Callable] = None

        # Animation state for lookup button
        self._lookup_animation_running = False
        self._lookup_animation_step = 0
        self._original_lookup_text = "Dictionary Lookup"
        self._original_lookup_bg = DICT_BUTTON_COLOR

    def _create_word_labels(self, text: str):
        """Parse text into words and create embedded labels.

        Uses NLP tokenization if available for the language, otherwise
        falls back to simple whitespace-based tokenization.
        """
        # Enable text widget temporarily for editing
        self.text_widget.configure(state='normal')
        self.text_widget.delete('1.0', tk.END)

        # Tokenize text using NLP if available
        words = self._tokenize_text(text)

        # Create a label for each word and embed in text widget
        for i, word in enumerate(words):
            label = WordLabel(
                self.text_widget, word, i,
                on_click=self._on_word_click,
                on_drag_enter=self._on_word_drag_enter
            )
            self.word_labels.append(label)

            # Insert the label as a window in the text widget
            self.text_widget.window_create(tk.END, window=label.label)

            # Add space after each word (except last)
            if i < len(words) - 1:
                self.text_widget.insert(tk.END, " ")

        # Disable text widget again
        self.text_widget.configure(state='disabled')

    def _tokenize_text(self, text: str) -> list:
        """Tokenize text using NLP or fallback to simple split.

        Args:
            text: Text to tokenize

        Returns:
            List of tokens/words
        """
        import logging
        logging.info(f"[DICT_TOKENIZE] language={self.language}, text_len={len(text)}")

        # Check for hyphenated words - if present, use simple split to preserve them
        # NLP tokenizers often split "auto-update" into ["auto", "-", "update"]
        has_hyphenated = re.search(r'\w+-\w+', text)
        if has_hyphenated:
            logging.info(f"[DICT_TOKENIZE] Found hyphenated words, using simple split")
            return re.findall(r'\S+', text)

        if self.language:
            try:
                from src.core.nlp_manager import nlp_manager
                # Vietnamese now uses subprocess isolation to handle potential native code crashes
                is_inst = nlp_manager.is_installed(self.language)
                logging.info(f"[DICT_TOKENIZE] is_installed({self.language})={is_inst}")
                if is_inst:
                    result = nlp_manager.tokenize(text, self.language)
                    logging.info(f"[DICT_TOKENIZE] NLP result: {len(result)} tokens, first 5: {result[:5]}")
                    return result
            except Exception as e:
                logging.error(f"[DICT_TOKENIZE] Exception: {e}", exc_info=True)

        # Simple fallback: split on whitespace, keeping hyphenated words together
        logging.info(f"[DICT_TOKENIZE] Using whitespace fallback")
        return re.findall(r'\S+', text)

    def _tokenize_simple(self, text: str) -> list:
        """Simple tokenizer that keeps hyphenated words together."""
        # Split by whitespace, preserving hyphenated compounds
        return re.findall(r'\S+', text)

    def _merge_hyphenated_tokens(self, tokens: list) -> list:
        """Merge tokens that were split by hyphens.

        UDPipe often splits "auto-update" into ["auto", "-", "update"].
        This merges them back into ["auto-update"].

        Also handles chained hyphens like "state-of-the-art" ->
        ["state", "-", "of", "-", "the", "-", "art"] -> "state-of-the-art"

        Args:
            tokens: List of tokens from NLP tokenizer

        Returns:
            List with hyphenated words merged
        """
        if len(tokens) < 3:
            return tokens

        result = []
        i = 0

        while i < len(tokens):
            # Check for pattern: word + hyphen + word (+ hyphen + word)*
            if (i + 2 < len(tokens) and
                tokens[i + 1] == '-' and
                tokens[i].isalnum() and
                tokens[i + 2].isalnum()):
                # Start building merged token
                merged = tokens[i]
                i += 1

                # Keep merging while we see hyphen + word pattern
                while (i + 1 < len(tokens) and
                       tokens[i] == '-' and
                       tokens[i + 1].isalnum()):
                    merged += '-' + tokens[i + 1]
                    i += 2

                result.append(merged)
            else:
                result.append(tokens[i])
                i += 1

        return result

    def _on_word_click(self, index: int, event):
        """Handle word label click."""
        # Check for Shift key (range selection)
        if event.state & 0x1:  # Shift pressed
            if self.anchor_index is not None:
                self._select_range(self.anchor_index, index)
            else:
                self._toggle_word(index)
                self.anchor_index = index
        else:
            # Normal click - toggle selection
            self._toggle_word(index)
            self.anchor_index = index

        # Start potential drag
        self.drag_start_index = index
        self._notify_selection_change()

    def _on_word_drag_enter(self, index: int):
        """Handle mouse drag entering a word."""
        if self.drag_start_index is not None:
            self._select_range(self.drag_start_index, index)
            self._notify_selection_change()

    def _toggle_word(self, index: int):
        """Toggle selection state of a single word."""
        if index in self.selected_indices:
            self.selected_indices.remove(index)
        else:
            self.selected_indices.add(index)
        self.word_labels[index].set_selected(index in self.selected_indices)

    def _select_range(self, start: int, end: int):
        """Select all words in a range (inclusive)."""
        # Clear existing selection
        for idx in list(self.selected_indices):
            self.word_labels[idx].set_selected(False)
        self.selected_indices.clear()

        # Select range
        min_idx, max_idx = min(start, end), max(start, end)
        for i in range(min_idx, max_idx + 1):
            self.selected_indices.add(i)
            self.word_labels[i].set_selected(True)

    def clear_selection(self):
        """Clear all selected words."""
        for idx in list(self.selected_indices):
            self.word_labels[idx].set_selected(False)
        self.selected_indices.clear()
        self.anchor_index = None
        self.drag_start_index = None
        self._notify_selection_change()

    def get_selected_text(self) -> str:
        """Get selected words as concatenated text."""
        if not self.selected_indices:
            return ""
        sorted_indices = sorted(self.selected_indices)
        return " ".join(self.word_labels[i].word for i in sorted_indices)

    def get_selected_words(self) -> list[str]:
        """Get selected words as a list of individual words."""
        if not self.selected_indices:
            return []
        sorted_indices = sorted(self.selected_indices)
        return [self.word_labels[i].word for i in sorted_indices]

    def _notify_selection_change(self):
        """Notify parent of selection change."""
        if self.on_selection_change:
            self.on_selection_change(self.get_selected_text())

    def _trigger_lookup(self):
        """Trigger dictionary lookup for selected words with animation.

        Each selected word is looked up separately (not as a combined phrase).
        If no words selected, calls on_no_selection callback.
        """
        words = self.get_selected_words()
        if words and self.on_lookup:
            self.start_lookup_animation()
            # Pass list of words for individual lookup
            self.on_lookup(words)
        elif not words and self.on_no_selection:
            # No words selected - notify parent to show warning
            self.on_no_selection()

    def start_lookup_animation(self):
        """Start the lookup button animation."""
        self._lookup_animation_running = True
        self._lookup_animation_step = 0
        self._animate_lookup_button()

    def stop_lookup_animation(self):
        """Stop the lookup button animation and restore original state."""
        self._lookup_animation_running = False
        try:
            self.lookup_btn.configure(
                text=self._original_lookup_text,
                bg=self._original_lookup_bg
            )
        except tk.TclError:
            pass  # Widget destroyed

    def _animate_lookup_button(self):
        """Animate the lookup button with dots and pulse effect."""
        if not self._lookup_animation_running:
            return

        try:
            # Dots animation pattern (fixed width to prevent shifting)
            dots_patterns = [
                "\u23f3 Looking up   ",  # 0 dots + 3 spaces
                "\u23f3 Looking up.  ",  # 1 dot + 2 spaces
                "\u23f3 Looking up.. ",  # 2 dots + 1 space
                "\u23f3 Looking up...",  # 3 dots + 0 spaces
            ]
            text = dots_patterns[self._lookup_animation_step % 4]
            self.lookup_btn.configure(text=text)

            # Pulse color effect (darken/lighten the reddish-brown)
            color = DICT_BUTTON_PULSE_COLORS[self._lookup_animation_step % 4]
            self.lookup_btn.configure(bg=color)

            self._lookup_animation_step += 1

            # Schedule next frame (500ms)
            self.frame.after(500, self._animate_lookup_button)

        except tk.TclError:
            # Widget destroyed
            self._lookup_animation_running = False

    def _trigger_expand(self):
        """Trigger expand callback."""
        if self.on_expand:
            self.on_expand()

    def _trigger_exit(self):
        """Trigger exit callback."""
        if self._on_exit:
            self._on_exit()

    def set_lookup_callback(self, callback: Callable[[str], None]):
        """Set the lookup button callback."""
        self.on_lookup = callback

    def set_expand_callback(self, callback: Callable):
        """Set the expand button callback."""
        self.on_expand = callback

    def set_exit_callback(self, callback: Callable):
        """Set the exit button callback."""
        self._on_exit = callback

    def pack(self, **kwargs):
        """Pack the main frame."""
        self.frame.pack(**kwargs)

    def pack_forget(self):
        """Remove the main frame from layout."""
        self.frame.pack_forget()

    def destroy(self):
        """Destroy all widgets."""
        for label in self.word_labels:
            label.destroy()
        self.word_labels.clear()
        self.frame.destroy()
