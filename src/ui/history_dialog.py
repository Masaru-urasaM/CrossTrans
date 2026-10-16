"""
History Dialog for CrossTrans.
"""
import ctypes
import tkinter as tk
from tkinter import BOTH, X, Y, LEFT, RIGHT, TOP, BOTTOM, W, E, NW
from datetime import datetime
from typing import Optional

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.dialogs import Messagebox
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.core import furigana, lang_id
from src.core.furigana import RubySegment
from src.ui.ruby_text import RubyLine, fit_segments

# A line is cut to the row's width in pixels, "..." included (K7). By character
# count (60, cut to 57) a Japanese line ran 685 px into a 560 px row, clipped,
# and its "..." never showed, while a Latin line was cut with room to spare.
LIST_WIDTH = 580            # the list's width before the window is first laid out
ROW_PADDING = 10            # each row frame's padding, on either side
LABEL_PADDING_PX = 4        # a ttk.Label's own, around its text (measured)
# No row shows more than this many characters of a line; only these are measured.
LINE_SCAN_CHARS = 200
# Readings are generated for this much of a line - more than is shown, so a word
# that straddles the cut is read in its context - but never for a whole document.
LINE_ANNOTATE_CHARS = 120
# The rows' text, as before J9.
ROW_FONT = ('Segoe UI', 10)
# The first rows are built before the dialog shows, the rest in batches while it
# is on screen (D17): built at once, 100 entries kept it blank for 1.2-1.9 s.
FIRST_ROWS = 12
ROW_BATCH = 10


def set_dark_title_bar(window):
    """Set dark title bar for Windows 10/11 windows."""
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_CAPTION_COLOR = 35
        dwmapi = ctypes.windll.dwmapi
        value = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                                     ctypes.byref(value), ctypes.sizeof(value))
        caption_color = ctypes.c_int(0x002b2b2b)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR,
                                     ctypes.byref(caption_color), ctypes.sizeof(caption_color))
    except Exception:
        pass


class HistoryDialog:
    """Dialog to view and manage translation history."""

    def __init__(self, parent, history_manager, on_load_callback, furigana_enabled=False):
        self.history_manager = history_manager
        self.on_load_callback = on_load_callback
        # Readings on the rows (J9) - the Settings toggle, read when the dialog opens.
        self.furigana_enabled = furigana_enabled
        self.search_var = None
        self.all_history = []  # Cache for filtering
        self._pending_rows = []     # entries still to be drawn (D17)
        self._row_job = None

        # Use tk.Toplevel
        self.window = tk.Toplevel(parent)
        self.window.title("Translation History")
        self.window.geometry("600x700")
        self.window.configure(bg='#2b2b2b')

        # Center
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - 600) // 2
        y = (self.window.winfo_screenheight() - 700) // 2
        self.window.geometry(f"+{x}+{y}")

        # Apply dark title bar (Windows 10/11)
        set_dark_title_bar(self.window)

        # No grab_set(): see CLAUDE.md "Never use grab_set() on popups". A modal
        # grab here locks every other window of the app behind a dialog the user
        # may not even see, and the Clear All confirmation is itself a Toplevel
        # that has to take input while this one is up.
        self.window.transient(parent)
        self.window.attributes('-topmost', True)
        self.window.lift()
        self.window.focus_force()
        self.window.after(100, lambda: self.window.attributes('-topmost', False)
                          if self.window.winfo_exists() else None)

        self._create_widgets()
        # Stop drawing rows into a closed window. Only the toplevel's own
        # <Destroy>: a child's propagates here too (CLAUDE.md Known Issues).
        self.window.bind('<Destroy>', self._on_destroy, add='+')
        self._refresh_list()

    def _on_destroy(self, event):
        if event.widget is self.window:
            self._cancel_rows()

    def _create_widgets(self):
        """Create UI elements."""
        # Header
        header_frame = ttk.Frame(self.window, padding=15)
        header_frame.pack(fill=X)

        ttk.Label(header_frame, text="Recent Translations", font=('Segoe UI', 14, 'bold')).pack(side=LEFT)

        if HAS_TTKBOOTSTRAP:
            ttk.Button(header_frame, text="Clear All", command=self._clear_all,
                       bootstyle="danger-outline", width=10).pack(side=RIGHT)
        else:
            ttk.Button(header_frame, text="Clear All", command=self._clear_all,
                       width=10).pack(side=RIGHT)

        # Search Frame
        search_frame = ttk.Frame(self.window, padding=(15, 0, 15, 10))
        search_frame.pack(fill=X)

        ttk.Label(search_frame, text="🔍", font=('Segoe UI', 11)).pack(side=LEFT, padx=(0, 5))

        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var,
                                      font=('Segoe UI', 10))
        self.search_entry.pack(side=LEFT, fill=X, expand=True)
        self.search_entry.insert(0, "Search history...")
        self.search_entry.bind('<FocusIn>', self._on_search_focus_in)
        self.search_entry.bind('<FocusOut>', self._on_search_focus_out)
        self.search_var.trace_add('write', self._on_search_change)

        # Clear search button
        if HAS_TTKBOOTSTRAP:
            self.clear_search_btn = ttk.Button(search_frame, text="✕", width=3,
                                               command=self._clear_search,
                                               bootstyle="secondary-outline")
        else:
            self.clear_search_btn = ttk.Button(search_frame, text="✕", width=3,
                                               command=self._clear_search)
        self.clear_search_btn.pack(side=LEFT, padx=(5, 0))
        self.clear_search_btn.pack_forget()  # Initially hidden

        # List Container (Canvas only, no scrollbar)
        list_container = ttk.Frame(self.window)
        list_container.pack(fill=BOTH, expand=True, padx=10, pady=(0, 10))

        self.canvas = tk.Canvas(list_container, bg='#2b2b2b', highlightthickness=0)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw",
                                  width=LIST_WIDTH)
        self.canvas.pack(fill=BOTH, expand=True)

        # Mousewheel scrolling only - there is no scrollbar, so this binding is
        # the only way to reach entry 11 and beyond.
        #
        # It used to be bind_all() undone by a <Destroy> handler on this window,
        # which was wrong twice over. bind_all() is interpreter-wide: it stole
        # the wheel from the popup, the dictionary window and the main window
        # for as long as the dialog was open. And a child's <Destroy> propagates
        # up to its toplevel's bindtag, so the *first* list rebuild - one
        # keystroke in the search box, one deleted entry, one focus-out that
        # restores the placeholder - destroyed a row, fired the handler and
        # unbound the wheel from the whole application. From then on the list
        # could not be scrolled at all, and neither could anything else.
        #
        # Bound per widget instead, and re-bound on every row as it is built.
        self._bind_wheel(self.canvas)
        self._bind_wheel(self.scrollable_frame)

        # Resize handler for canvas width
        def _configure_canvas(event):
            self.canvas.itemconfig(self.canvas.find_withtag("all")[0], width=event.width)
        self.canvas.bind('<Configure>', _configure_canvas)

    def _on_mousewheel(self, event):
        """Scroll the list. Bound per widget, never with bind_all()."""
        try:
            self.canvas.yview_scroll(int(-3 * (event.delta / 120)), "units")
        except tk.TclError:                    # dialog closing
            pass
        return "break"

    def _bind_wheel(self, widget):
        """Bind the wheel on `widget` and everything already inside it.

        Every row has to carry it: the rows cover the canvas, and a child widget
        consumes the event before the canvas under it ever sees it.
        """
        widget.bind("<MouseWheel>", self._on_mousewheel)
        for child in widget.winfo_children():
            self._bind_wheel(child)

    def _on_search_focus_in(self, event):
        """Clear placeholder on focus."""
        if self.search_entry.get() == "Search history...":
            self.search_entry.delete(0, tk.END)
            self.search_entry.configure(foreground='#ffffff')

    def _on_search_focus_out(self, event):
        """Restore placeholder if empty."""
        if not self.search_entry.get():
            self.search_entry.insert(0, "Search history...")
            self.search_entry.configure(foreground='#888888')

    def _on_search_change(self, *args):
        """Handle search text change."""
        search_text = self.search_var.get()

        # Show/hide clear button
        if search_text and search_text != "Search history...":
            self.clear_search_btn.pack(side=LEFT, padx=(5, 0))
        else:
            self.clear_search_btn.pack_forget()

        # Filter and refresh
        self._filter_and_display()

    def _clear_search(self):
        """Clear search and show all history."""
        self.search_entry.delete(0, tk.END)
        self.search_entry.insert(0, "Search history...")
        self.search_entry.configure(foreground='#888888')
        self.clear_search_btn.pack_forget()
        self._filter_and_display()

    def _refresh_list(self):
        """Load history and display."""
        self.all_history = self.history_manager.get_history()
        self._filter_and_display()

    def _filter_and_display(self):
        """Filter history based on search and display."""
        # Clear existing - rows still waiting to be drawn included
        self._cancel_rows()
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        search_text = self.search_var.get() if self.search_var else ""
        if search_text == "Search history...":
            search_text = ""
        search_text = search_text.lower().strip()

        # Filter history
        if search_text:
            filtered = [
                item for item in self.all_history
                if (search_text in item.get('original', '').lower() or
                    search_text in item.get('translated', '').lower() or
                    search_text in item.get('target_lang', '').lower() or
                    search_text in item.get('source_lang', '').lower())
            ]
        else:
            filtered = self.all_history

        if not filtered:
            if search_text:
                msg = f"No results for \"{search_text}\""
            else:
                msg = "No history yet."
            empty = ttk.Label(self.scrollable_frame, text=msg,
                              foreground='#888888', font=('Segoe UI', 10))
            empty.pack(pady=20)
            self._bind_wheel(empty)
            return

        self._pending_rows = list(filtered)
        self._build_rows(FIRST_ROWS)

    def _build_rows(self, count: int):
        """Draw the next `count` waiting rows, and schedule the rest (D17)."""
        self._row_job = None
        try:
            if not self.window.winfo_exists():
                return
        except tk.TclError:
            return
        batch, self._pending_rows = self._pending_rows[:count], self._pending_rows[count:]
        for item in batch:
            self._create_history_item(item)
        if self._pending_rows:
            self._row_job = self.window.after(1, lambda: self._build_rows(ROW_BATCH))

    def _cancel_rows(self):
        """Forget the rows still waiting to be drawn."""
        job, self._row_job = self._row_job, None
        self._pending_rows = []
        if job:
            try:
                self.window.after_cancel(job)
            except tk.TclError:
                pass

    def _line_px(self) -> int:
        """How wide a row's text may be: the list's width inside a row's padding."""
        try:
            width = self.canvas.winfo_width()
        except tk.TclError:
            width = 0
        return (width if width > 1 else LIST_WIDTH) - 2 * ROW_PADDING

    def _create_history_item(self, item):
        """Create a single history row."""
        frame = ttk.Frame(self.scrollable_frame, padding=ROW_PADDING)
        frame.pack(fill=X, pady=2)

        # Separator line at bottom
        separator = ttk.Separator(self.scrollable_frame)
        separator.pack(fill=X, padx=10)

        # Top row: Lang + Time
        top_row = ttk.Frame(frame)
        top_row.pack(fill=X, pady=(0, 5))

        source_lang = item.get('source_lang', '')
        target_lang = item.get('target_lang', 'Unknown')
        ts = item.get('timestamp', 0)
        time_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')

        # Language display: Source → Target
        if source_lang and source_lang != 'Unknown':
            lang_text = f"{source_lang} → {target_lang}"
        else:
            lang_text = f"→ {target_lang}"

        if HAS_TTKBOOTSTRAP:
            ttk.Label(top_row, text=lang_text, bootstyle="info", font=('Segoe UI', 9, 'bold')).pack(side=LEFT)
        else:
            ttk.Label(top_row, text=lang_text, foreground='#17a2b8', font=('Segoe UI', 9, 'bold')).pack(side=LEFT)

        ttk.Label(top_row, text=time_str, foreground='#888888', font=('Segoe UI', 8)).pack(side=RIGHT)

        # Content - with readings when it is Japanese (J9): the original by its
        # own evidence, else the verdict a model gave for it (never History's
        # source_lang label, which has always been a guess from the characters);
        # the translation by the language-set rule.
        original = item.get('original', '')
        source = lang_id.resolve(original, model=item.get('source_verdict')).language
        clickable = [frame]
        clickable += self._content_line(frame, original,
                                        lang_id.JAPANESE if source == lang_id.JAPANESE else None,
                                        fg='#cccccc')
        clickable += self._content_line(frame, item.get('translated', ''),
                                        lang_id.output_hint(source, item.get('target_lang')),
                                        prefix="→ ", fg='#ffffff', pady=(2, 0))

        # Click to load - on every part: a reading label is a grandchild of the
        # row, and a click on it never reaches the row's own binding.
        for widget in clickable + [top_row]:
            widget.bind("<Button-1>", lambda e, i=item: self._load_item(i))

        # Delete button (small 'x' on right, but tricky with layout, let's put it in top row)
        del_btn = ttk.Label(top_row, text="✕", foreground='#dc3545', cursor="hand2")
        del_btn.pack(side=RIGHT, padx=(0, 10))
        del_btn.bind("<Button-1>", lambda e, i=item: self._delete_item(i))

        # The wheel, on this row's widgets as they are made - rows arrive in
        # batches, after the list was last bound (D17)
        self._bind_wheel(frame)
        self._bind_wheel(separator)

    def _content_line(self, parent, text: str, hint: Optional[str], prefix: str = "",
                      fg: str = '#cccccc', pady=(0, 0)) -> list:
        """One line of a row - a RubyLine when it carries a reading, else the plain
        label it always was. Returns the widgets a click must reach.

        Cut to the row's width in pixels with "..." (`fit_segments`, K7), never
        through a ruby pair.
        """
        line = text.replace('\n', ' ')
        segments = ()
        if self.furigana_enabled and furigana.should_annotate(line[:LINE_ANNOTATE_CHARS], hint):
            segments = furigana.annotate(line[:LINE_ANNOTATE_CHARS], hint)
        if any(segment.ruby for segment in segments):
            if prefix:
                segments = (RubySegment(prefix, None),) + segments
            segments, _cut = fit_segments(parent, segments, self._line_px(),
                                          base_font=ROW_FONT,
                                          more=len(line) > LINE_ANNOTATE_CHARS)
            line_widget = RubyLine(parent, segments,
                                   base_font=ROW_FONT, bg=self._row_bg(), base_fg=fg)
            line_widget.pack(anchor=W, pady=pady)
            return [line_widget]

        shown, _cut = fit_segments(parent, (RubySegment(prefix + line[:LINE_SCAN_CHARS], None),),
                                   self._line_px() - LABEL_PADDING_PX, base_font=ROW_FONT,
                                   more=len(line) > LINE_SCAN_CHARS)
        label = ttk.Label(parent, text=''.join(segment.base for segment in shown),
                          font=ROW_FONT, foreground=fg)
        label.pack(anchor=W, pady=pady)
        return [label]

    def _row_bg(self) -> str:
        """The rows' background, for the canvas a RubyLine is drawn on
        (ttkbootstrap would re-theme it, so it takes it explicitly)."""
        try:
            return ttk.Style().lookup('TFrame', 'background') or '#2b2b2b'
        except tk.TclError:
            return '#2b2b2b'

    def _load_item(self, item):
        """Load item into main translator."""
        self.on_load_callback(item)
        self.window.destroy()

    def _delete_item(self, item):
        """Delete item."""
        self.history_manager.delete_entry(item.get('id'))
        self.all_history = [h for h in self.all_history if h.get('id') != item.get('id')]
        self._filter_and_display()

    def _clear_all(self):
        """Clear all history."""
        if HAS_TTKBOOTSTRAP:
            if Messagebox.yesno("Clear all history?", parent=self.window) != "Yes": return
        else:
            from tkinter import messagebox
            if not messagebox.askyesno("Confirm", "Clear all history?", parent=self.window): return

        self.history_manager.clear_history()
        self.all_history = []
        self._filter_and_display()
