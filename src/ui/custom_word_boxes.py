"""
Custom Word Boxes for Dictionary mode in CrossTrans.

Allows users to manually compose lookup phrases by typing or
dragging words from the tokenized word selection area.
"""
import tkinter as tk
from tkinter import LEFT, RIGHT, BOTH, X, TOP, BOTTOM, END
from typing import Callable, Optional

try:
    import ttkbootstrap as ttk
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

TAG_BG = '#fd7e14'
TAG_FG = '#ffffff'
TAG_FONT = ('Segoe UI', 11, 'bold')
BOX_BG = '#1e1e1e'
BOX_FG = '#ffffff'
BOX_FONT = ('Segoe UI', 11)
HIGHLIGHT_BORDER = '#fd7e14'
MAX_BOXES = 5


class WordTag:
    """An orange tag inside a CustomWordBox, removable by clicking x."""

    def __init__(self, parent_text: tk.Text, word: str, on_remove: Callable):
        self.word = word
        self.parent_text = parent_text
        self._on_remove = on_remove

        self.frame = tk.Frame(parent_text, bg=TAG_BG, padx=1, pady=0)

        self.label = tk.Label(
            self.frame, text=word,
            font=TAG_FONT, bg=TAG_BG, fg=TAG_FG,
            padx=2, pady=1
        )
        self.label.pack(side=LEFT)

        self.close_btn = tk.Label(
            self.frame, text='×', font=('Segoe UI', 9),
            bg=TAG_BG, fg='#ffddcc', padx=2, pady=0, cursor='hand2'
        )
        self.close_btn.pack(side=LEFT)
        self.close_btn.bind('<Button-1>', lambda e: self._remove())

    def _remove(self):
        self._on_remove(self)

    def destroy(self):
        self.frame.destroy()


class CustomWordBox:
    """A single input row with text widget for tags/text and +/- buttons."""

    def __init__(self, parent, index: int, is_first: bool,
                 on_add: Callable, on_remove: Callable):
        self.index = index
        self._tags: list[WordTag] = []

        self.frame = tk.Frame(parent, bg='#2b2b2b')

        # Pack buttons FIRST so they claim space before text_widget expands
        btn_frame = tk.Frame(self.frame, bg='#2b2b2b')
        btn_frame.pack(side=RIGHT)

        self.text_widget = tk.Text(
            self.frame, height=1, wrap=tk.NONE,
            bg=BOX_BG, fg=BOX_FG, font=BOX_FONT,
            insertbackground='#ffffff',
            relief='solid', bd=1,
            highlightthickness=1,
            highlightbackground='#555555',
            highlightcolor='#888888',
            padx=4, pady=2
        )
        self.text_widget.pack(side=LEFT, fill=X, expand=True, padx=(0, 4))

        self.text_widget.bind('<Return>', self._on_enter)
        self.text_widget.bind('<BackSpace>', self._on_backspace)

        self.add_btn = tk.Button(
            btn_frame, text='+', command=lambda: on_add(self.index),
            bg='#3a3a3a', fg='#ffffff', activebackground='#4a4a4a',
            font=('Segoe UI', 10, 'bold'), width=2, relief='flat', cursor='hand2'
        )
        self.add_btn.pack(side=LEFT, padx=1)

        if not is_first:
            self.remove_btn = tk.Button(
                btn_frame, text='−', command=lambda: on_remove(self.index),
                bg='#3a3a3a', fg='#ff6666', activebackground='#4a4a4a',
                font=('Segoe UI', 10, 'bold'), width=2, relief='flat', cursor='hand2'
            )
            self.remove_btn.pack(side=LEFT, padx=1)
        else:
            self.remove_btn = None

    def _on_enter(self, event):
        """Convert typed text before cursor into a tag."""
        text = self.text_widget.get('1.0', 'insert').strip()
        if text:
            self.text_widget.delete('1.0', 'insert')
            self.add_word_tag(text)
        return 'break'

    def _on_backspace(self, event):
        """Remove adjacent tag on backspace if cursor is at tag boundary."""
        if not self._tags:
            return
        cursor_pos = self.text_widget.index('insert')
        col = int(cursor_pos.split('.')[1])
        if col == 0:
            text_before = self.text_widget.get('1.0', 'insert')
            if not text_before.strip():
                tag = self._tags[-1]
                self._remove_tag(tag)
                return 'break'

    def add_word_tag(self, word: str):
        """Insert an orange word tag at the current cursor position."""
        tag = WordTag(self.text_widget, word, self._remove_tag)
        self._tags.append(tag)
        self.text_widget.window_create('insert', window=tag.frame)

    def _remove_tag(self, tag: WordTag):
        """Remove a tag from this box."""
        if tag in self._tags:
            self._tags.remove(tag)
            tag.destroy()

    def get_content(self) -> str:
        """Get all content (tags + typed text) as a single phrase string."""
        parts = []
        content = self.text_widget.get('1.0', END).strip()
        if not content and not self._tags:
            return ""

        raw_text = self.text_widget.dump('1.0', END, text=True, window=True)
        for item_type, value, _index in raw_text:
            if item_type == 'text':
                cleaned = value.strip()
                if cleaned:
                    parts.append(cleaned)
            elif item_type == 'window':
                for tag in self._tags:
                    try:
                        if str(tag.frame) == value:
                            parts.append(tag.word)
                            break
                    except tk.TclError:
                        pass

        return ' '.join(parts)

    def set_highlight(self, active: bool):
        """Highlight border when a drag hovers over this box."""
        color = HIGHLIGHT_BORDER if active else '#555555'
        self.text_widget.configure(highlightbackground=color)

    def hide_add_button(self):
        self.add_btn.pack_forget()

    def show_add_button(self):
        self.add_btn.pack(side=LEFT, padx=1)

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def pack_forget(self):
        self.frame.pack_forget()

    def destroy(self):
        for tag in self._tags:
            tag.destroy()
        self._tags.clear()
        self.frame.destroy()


class CustomWordBoxesFrame:
    """Container managing multiple CustomWordBox instances."""

    def __init__(self, parent):
        self.parent = parent
        self._boxes: list[CustomWordBox] = []

        self.frame = tk.Frame(parent, bg='#2b2b2b')

        header = tk.Label(
            self.frame, text='Custom lookup:',
            font=('Segoe UI', 9), bg='#2b2b2b', fg='#999999'
        )
        header.pack(anchor='w', pady=(2, 3))

        self._boxes_container = tk.Frame(self.frame, bg='#2b2b2b')
        self._boxes_container.pack(fill=X)

        self._add_box_at(0, is_first=True)

    def _add_box_at(self, after_index: int, is_first: bool = False):
        """Add a new box after the given index."""
        if len(self._boxes) >= MAX_BOXES:
            return

        new_index = after_index + 1 if not is_first else 0
        box = CustomWordBox(
            self._boxes_container, new_index, is_first,
            on_add=self._on_add_clicked,
            on_remove=self._on_remove_clicked
        )

        if is_first:
            self._boxes.append(box)
        else:
            self._boxes.insert(new_index, box)

        self._repack_boxes()

    def _on_add_clicked(self, box_index: int):
        """Handle + button click."""
        actual_index = self._find_box_actual_index(box_index)
        if actual_index is not None:
            self._add_box_at(actual_index)

    def _on_remove_clicked(self, box_index: int):
        """Handle - button click."""
        actual_index = self._find_box_actual_index(box_index)
        if actual_index is not None and len(self._boxes) > 1:
            box = self._boxes.pop(actual_index)
            box.destroy()
            self._repack_boxes()

    def _find_box_actual_index(self, original_index: int) -> Optional[int]:
        """Find actual list index from box's stored index."""
        for i, box in enumerate(self._boxes):
            if box.index == original_index:
                return i
        return None

    def _repack_boxes(self):
        """Repack all boxes with updated indices."""
        for box in self._boxes:
            box.pack_forget()

        for i, box in enumerate(self._boxes):
            box.index = i
            box.pack(fill=X, pady=(0, 3))
            if len(self._boxes) >= MAX_BOXES:
                box.hide_add_button()
            else:
                box.show_add_button()

    def get_all_phrases(self) -> list[str]:
        """Get non-empty phrases from all boxes."""
        phrases = []
        for box in self._boxes:
            content = box.get_content()
            if content:
                phrases.append(content)
        return phrases

    def has_any_content(self) -> bool:
        """Check if any box has content."""
        return any(box.get_content() for box in self._boxes)

    def get_focused_box(self) -> Optional[CustomWordBox]:
        """Get the box that currently has focus, or the last box."""
        try:
            focused = self.frame.focus_get()
            for box in self._boxes:
                if focused == box.text_widget:
                    return box
        except (KeyError, tk.TclError):
            pass
        return self._boxes[-1] if self._boxes else None

    def add_word_to_box(self, word: str, box: Optional[CustomWordBox] = None):
        """Add a word tag to a specific box or the focused/last box."""
        target = box or self.get_focused_box()
        if target:
            target.add_word_tag(word)

    def get_box_at_position(self, x_root: int, y_root: int) -> Optional[CustomWordBox]:
        """Find which box is at the given screen coordinates."""
        for box in self._boxes:
            try:
                widget = box.text_widget
                wx = widget.winfo_rootx()
                wy = widget.winfo_rooty()
                ww = widget.winfo_width()
                wh = widget.winfo_height()
                if wx <= x_root <= wx + ww and wy <= y_root <= wy + wh:
                    return box
            except tk.TclError:
                pass
        return None

    def clear_all_highlights(self):
        """Remove highlight from all boxes."""
        for box in self._boxes:
            box.set_highlight(False)

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def pack_forget(self):
        self.frame.pack_forget()

    def destroy(self):
        for box in self._boxes:
            box.destroy()
        self._boxes.clear()
        self.frame.destroy()
