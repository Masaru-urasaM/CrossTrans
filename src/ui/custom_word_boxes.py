"""
Custom Word Boxes for Dictionary mode in CrossTrans.

Allows users to manually compose lookup phrases by typing or
dragging words from the tokenized word selection area.
Right-click drag tags within/between boxes to reorder them.
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

    def __init__(self, parent_text: tk.Text, word: str, on_remove: Callable,
                 on_drag_start: Optional[Callable] = None):
        self.word = word
        self.parent_text = parent_text
        self._on_remove = on_remove
        self._on_drag_start = on_drag_start

        self.frame = tk.Frame(parent_text, bg=TAG_BG, padx=1, pady=0)

        self.label = tk.Label(
            self.frame, text=word,
            font=TAG_FONT, bg=TAG_BG, fg=TAG_FG,
            padx=2, pady=1, cursor='hand2'
        )
        self.label.pack(side=LEFT)

        self.close_btn = tk.Label(
            self.frame, text='×', font=('Segoe UI', 9),
            bg=TAG_BG, fg='#ffddcc', padx=2, pady=0, cursor='hand2'
        )
        self.close_btn.pack(side=LEFT)
        self.close_btn.bind('<Button-1>', lambda e: self._remove())

        self.label.bind('<Button-3>', self._handle_drag_start)
        self.frame.bind('<Button-3>', self._handle_drag_start)

    def _handle_drag_start(self, event):
        if self._on_drag_start:
            self._on_drag_start(self, event)

    def _remove(self):
        self._on_remove(self)

    def destroy(self):
        self.frame.destroy()


class CustomWordBox:
    """A single input row with text widget for tags/text and +/- buttons."""

    def __init__(self, parent, index: int, is_first: bool,
                 on_add: Callable, on_remove: Callable,
                 on_tag_drag_start: Optional[Callable] = None):
        self.index = index
        self._tags: list[WordTag] = []
        self._on_tag_drag_start = on_tag_drag_start

        self.frame = tk.Frame(parent, bg='#2b2b2b')

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
        self.text_widget.bind('<Button-1>', self._on_click, add='+')

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

    def _on_click(self, event):
        """Ensure text widget gets focus for text selection."""
        self.text_widget.focus_set()

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
        tag = WordTag(self.text_widget, word, self._remove_tag,
                      on_drag_start=self._on_tag_drag_start)
        self._tags.append(tag)
        self.text_widget.window_create('insert', window=tag.frame)

    def insert_tag_at_position(self, word: str, tk_index: str):
        """Insert a tag at a specific text widget index."""
        tag = WordTag(self.text_widget, word, self._remove_tag,
                      on_drag_start=self._on_tag_drag_start)
        self._tags.append(tag)
        self.text_widget.window_create(tk_index, window=tag.frame)
        self._rebuild_tags_order()

    def remove_tag_for_drag(self, tag: WordTag):
        """Remove a tag for drag-move (destroys widget, caller recreates at destination)."""
        if tag in self._tags:
            self._tags.remove(tag)
            try:
                idx = self.text_widget.index(str(tag.frame))
                self.text_widget.delete(idx)
            except tk.TclError:
                pass
            tag.destroy()

    def _rebuild_tags_order(self):
        """Rebuild _tags list to match visual order in the text widget."""
        raw = self.text_widget.dump('1.0', 'end', window=True)
        tag_by_frame = {str(t.frame): t for t in self._tags}
        ordered = []
        for item_type, value, _index in raw:
            if item_type == 'window' and value in tag_by_frame:
                ordered.append(tag_by_frame[value])
        self._tags = ordered

    def get_insert_index_at_coords(self, x_root: int, y_root: int) -> str:
        """Convert screen coordinates to a text widget index for insertion."""
        local_x = x_root - self.text_widget.winfo_rootx()
        local_y = y_root - self.text_widget.winfo_rooty()
        return self.text_widget.index(f"@{local_x},{local_y}")

    def _remove_tag(self, tag: WordTag):
        """Remove a tag from this box."""
        if tag in self._tags:
            self._tags.remove(tag)
            tag.destroy()

    @staticmethod
    def _strip_surrogates(text: str) -> str:
        """Remove Unicode surrogate characters (U+D800-U+DFFF).

        Tkinter on Windows may emit surrogates as placeholders for
        embedded windows in Text widgets.
        """
        return ''.join(c for c in text if not ('\ud800' <= c <= '\udfff'))

    @staticmethod
    def _is_cjk(c: str) -> bool:
        """Check if a character is CJK (no word-space needed between them)."""
        cp = ord(c)
        return (0x2E80 <= cp <= 0x9FFF or 0x3040 <= cp <= 0x30FF or
                0xAC00 <= cp <= 0xD7AF or 0xF900 <= cp <= 0xFAFF)

    @classmethod
    def _smart_join(cls, parts: list) -> str:
        """Join parts with spaces only where needed.

        CJK tags join without space: [無礼][講] -> "無礼講"
        Latin tags join with space:  [custom][and] -> "custom and"
        Typed text preserves its own whitespace as-is.
        """
        if not parts:
            return ""
        result = parts[0]
        for i in range(1, len(parts)):
            right = parts[i]
            if not result or not right:
                result += right
                continue
            last_char = result[-1]
            first_char = right[0]
            if last_char.isspace() or first_char.isspace():
                result += right
            elif cls._is_cjk(last_char) and cls._is_cjk(first_char):
                result += right
            else:
                result += ' ' + right
        return result

    def get_content(self) -> str:
        """Get all content (tags + typed text) as a single phrase string.

        Smart joining: no space between CJK tags, space between Latin tags,
        typed text preserves its own whitespace.
        """
        parts = []
        raw_content = self._strip_surrogates(
            self.text_widget.get('1.0', END).strip())
        if not raw_content and not self._tags:
            return ""

        raw_text = self.text_widget.dump('1.0', END, text=True, window=True)
        for item_type, value, _index in raw_text:
            if item_type == 'text':
                text = self._strip_surrogates(value.rstrip('\n'))
                if text:
                    parts.append(text)
            elif item_type == 'window':
                for tag in self._tags:
                    try:
                        if str(tag.frame) == value:
                            parts.append(tag.word)
                            break
                    except tk.TclError:
                        pass

        return self._smart_join(parts).strip()

    def set_highlight(self, active: bool):
        """Highlight border when a drag hovers over this box."""
        color = HIGHLIGHT_BORDER if active else '#555555'
        self.text_widget.configure(highlightbackground=color)

    def get_drop_screen_coords(self, x_root: int, y_root: int):
        """Get screen coordinates for the insertion point indicator.

        Returns (screen_x, screen_y, height) or None if not available.
        """
        idx = self.get_insert_index_at_coords(x_root, y_root)
        self.text_widget.mark_set('insert', idx)
        bbox = self.text_widget.bbox(idx)
        if bbox:
            x, _y, _w, _h = bbox
            sx = self.text_widget.winfo_rootx() + x
            sy = self.text_widget.winfo_rooty()
            h = self.text_widget.winfo_height()
            return sx, sy, h
        return None

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
    """Container managing multiple CustomWordBox instances.

    Supports right-click drag to reorder tags within and between boxes.
    """

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

        self._drag_source_tag: Optional[WordTag] = None
        self._drag_source_box: Optional[CustomWordBox] = None
        self._drag_ghost: Optional[tk.Toplevel] = None
        self._drop_line: Optional[tk.Toplevel] = None
        self._drag_moved = False

        self._add_box_at(0, is_first=True)

    def _add_box_at(self, after_index: int, is_first: bool = False):
        """Add a new box after the given index."""
        if len(self._boxes) >= MAX_BOXES:
            return

        new_index = after_index + 1 if not is_first else 0
        box = CustomWordBox(
            self._boxes_container, new_index, is_first,
            on_add=self._on_add_clicked,
            on_remove=self._on_remove_clicked,
            on_tag_drag_start=self._on_tag_drag_start
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

    # --- Tag drag-reorder (right-click drag within/between boxes) ---

    def _dim_tag(self, tag: 'WordTag'):
        """Dim a tag to indicate it is being dragged."""
        try:
            tag.frame.configure(bg='#8B5A1A')
            tag.label.configure(bg='#8B5A1A', fg='#aaaaaa')
            tag.close_btn.configure(bg='#8B5A1A', fg='#777777')
        except tk.TclError:
            pass

    def _restore_tag(self, tag: 'WordTag'):
        """Restore a tag to normal appearance."""
        try:
            tag.frame.configure(bg=TAG_BG)
            tag.label.configure(bg=TAG_BG, fg=TAG_FG)
            tag.close_btn.configure(bg=TAG_BG, fg='#ffddcc')
        except tk.TclError:
            pass

    def _on_tag_drag_start(self, tag: 'WordTag', event):
        """Handle right-click drag start on a WordTag."""
        source_box = None
        for box in self._boxes:
            if tag in box._tags:
                source_box = box
                break
        if not source_box:
            return

        self._drag_source_tag = tag
        self._drag_source_box = source_box
        self._drag_moved = False

        self._dim_tag(tag)

        self._drag_ghost = tk.Toplevel(self.frame)
        self._drag_ghost.overrideredirect(True)
        self._drag_ghost.attributes('-topmost', True)
        self._drag_ghost.attributes('-alpha', 0.85)
        ghost_label = tk.Label(
            self._drag_ghost, text=tag.word,
            font=TAG_FONT, bg=TAG_BG, fg=TAG_FG,
            padx=4, pady=2
        )
        ghost_label.pack()
        self._drag_ghost.geometry(f"+{event.x_root + 12}+{event.y_root + 8}")

        self.frame.bind_all('<B3-Motion>', self._on_tag_drag_motion)
        self.frame.bind_all('<ButtonRelease-3>', self._on_tag_drag_end)

    def _show_drop_line(self, box: 'CustomWordBox', x_root: int, y_root: int):
        """Show a bright vertical line at the insertion point (Toplevel window)."""
        coords = box.get_drop_screen_coords(x_root, y_root)
        if not coords:
            self._hide_drop_line()
            return
        sx, sy, h = coords
        if not self._drop_line:
            self._drop_line = tk.Toplevel(self.frame)
            self._drop_line.overrideredirect(True)
            self._drop_line.attributes('-topmost', True)
            self._drop_line.configure(bg='#00d4ff')
        self._drop_line.geometry(f"3x{h - 4}+{sx - 1}+{sy + 2}")
        self._drop_line.deiconify()
        self._drop_line.lift()

    def _hide_drop_line(self):
        """Hide the drop indicator line."""
        if self._drop_line:
            try:
                self._drop_line.withdraw()
            except tk.TclError:
                self._drop_line = None

    def _on_tag_drag_motion(self, event):
        """Move ghost, highlight target box, and show drop line."""
        self._drag_moved = True
        if self._drag_ghost:
            self._drag_ghost.geometry(f"+{event.x_root + 12}+{event.y_root + 8}")

        self.clear_all_highlights()

        box = self.get_box_at_position(event.x_root, event.y_root)
        if box:
            box.set_highlight(True)
            self._show_drop_line(box, event.x_root, event.y_root)
        else:
            self._hide_drop_line()

    def _on_tag_drag_end(self, event):
        """Complete the drag -- move tag to target position."""
        try:
            self.frame.unbind_all('<B3-Motion>')
            self.frame.unbind_all('<ButtonRelease-3>')
        except tk.TclError:
            pass

        if self._drag_ghost:
            try:
                self._drag_ghost.destroy()
            except tk.TclError:
                pass
            self._drag_ghost = None
        self._hide_drop_line()
        self.clear_all_highlights()

        if not self._drag_moved or not self._drag_source_tag or not self._drag_source_box:
            if self._drag_source_tag:
                self._restore_tag(self._drag_source_tag)
            self._drag_source_tag = None
            self._drag_source_box = None
            return

        target_box = self.get_box_at_position(event.x_root, event.y_root)
        if not target_box:
            if self._drag_source_tag:
                self._restore_tag(self._drag_source_tag)
            self._drag_source_tag = None
            self._drag_source_box = None
            return

        word = self._drag_source_tag.word
        source_box = self._drag_source_box
        source_tag = self._drag_source_tag

        target_index = target_box.get_insert_index_at_coords(event.x_root, event.y_root)

        if target_box is source_box:
            try:
                source_idx = source_box.text_widget.index(str(source_tag.frame))
                if source_box.text_widget.compare(target_index, '>', source_idx):
                    target_index = source_box.text_widget.index(f"{target_index} - 1c")
            except tk.TclError:
                pass

        source_box.remove_tag_for_drag(source_tag)
        target_box.insert_tag_at_position(word, target_index)

        self._drag_source_tag = None
        self._drag_source_box = None

    # --- Public API ---

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
        if self._drop_line:
            try:
                self._drop_line.destroy()
            except tk.TclError:
                pass
            self._drop_line = None
        for box in self._boxes:
            box.destroy()
        self._boxes.clear()
        self.frame.destroy()
