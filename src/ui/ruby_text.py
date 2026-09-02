"""Reusable furigana-capable text widget for CrossTrans.

`RubyText` is a `tk.Text` subclass that renders kanji together with their
hiragana readings as inline two-row frames (reading on top, base below),
embedded with `align='baseline'` so the base characters stay level with the
surrounding plain text no matter how different the two font sizes are.

Why a widget instead of a helper function:

* **Plain-text readback.** `Text.get()` contributes zero characters for an
  embedded window while still consuming one index, so any Copy / Replace /
  re-send path that reads a ruby-annotated widget with `get()` silently loses
  every annotated word. `get_plain()` reconstructs the true source text from
  `Text.dump(text=True, window=True)`.
* **Correct sizing.** A display row that contains ruby is much taller than a
  plain one (measured on Tk 8.6 at Yu Gothic 11/7: 47 px vs 28 px), while the
  `height` option counts rows of the *base* font. Asking for one `height` unit
  per logical line therefore under-allocates by 19 px per annotated row.
  `fit_height()` simulates the `wrap='char'` layout and converts the real pixel
  requirement into `height` units.
* **Scrolling over ruby.** An embedded frame swallows `<MouseWheel>`, leaving
  dead zones exactly where the interesting text is. Every frame and label
  created here is bound to the same wheel handler as the widget itself.

The appearance constants match the popup renderer this code was extracted
from, so existing surfaces look unchanged.
"""
import logging
import math
import tkinter as tk
from contextlib import contextmanager
from tkinter import font
from typing import (Callable, Dict, List, NamedTuple, Optional, Sequence,
                    Set, Tuple)

from src.core import furigana
from src.core.furigana import RubySegment

try:
    import ttkbootstrap  # noqa: F401  (imported for the side effect below)
    # ttkbootstrap re-themes standard tk widgets at construction and DISCARDS
    # explicit colour kwargs: a tk.Label asked for fg='#80b8ff' comes back
    # '#ffffff'. Measured, not assumed. The ruby plate and reading must keep the
    # colours they were given - the whole point of the reading is that it looks
    # different from the base text - so they opt out, the same way the existing
    # tk.Button call sites in quick_translate.py do. The Text widget itself does
    # NOT opt out: it should keep matching the themed frame around it. Public so
    # every module that must keep a colour uses the same guarded constant.
    NO_AUTOSTYLE = {'autostyle': False}
except ImportError:
    NO_AUTOSTYLE = {}

# --------------------------------------------------------------------------- #
# Appearance - identical to the original popup renderer.
# Values live in src/constants.py (the FURIGANA section, alongside the engine's
# caps) and are aliased here to the short names this module reads best with.
# --------------------------------------------------------------------------- #
from src.constants import (  # noqa: E402  (grouped with the names it defines)
    FURIGANA_BASE_FG as BASE_FG,
    FURIGANA_BASE_FONT_SIZE as BASE_FONT_SIZE,
    FURIGANA_DEFAULT_BG as DEFAULT_BG,
    FURIGANA_DEFAULT_MAX_ROWS as DEFAULT_MAX_ROWS,
    FURIGANA_FONT_FAMILY as CJK_FONT_FAMILY,
    FURIGANA_KANJI_FG as KANJI_FG,
    FURIGANA_LINE_SPACING as LINE_SPACING,
    FURIGANA_MAX_ANNOTATE_CHARS as MAX_ANNOTATE_CHARS,
    FURIGANA_RUBY_BG as RUBY_BG,
    FURIGANA_RUBY_FG as RUBY_FG,
    FURIGANA_RUBY_FONT_SIZE as RUBY_FONT_SIZE,
    FURIGANA_RUBY_PAD_X as RUBY_PAD_X,
    FURIGANA_RUBY_PAD_Y as RUBY_PAD_Y,
    FURIGANA_WHEEL_UNITS as WHEEL_UNITS,
)


class LayoutModel(NamedTuple):
    """Everything `layout_rows()` needs to simulate a wrap='char' layout.

    Split out from the widget so the wrap arithmetic can be tested without a
    display: a test injects fixed-width measurers and asserts row counts.

    `line_spacing` is charged per *logical* line, not per display row: Tk
    applies spacing1 above the first display row of a logical line and spacing3
    below the last one, with spacing2 (0 here) between wrapped rows.

    Attributes:
        content_plain: Pixel height of a display row with no ruby, bare.
        content_ruby: Pixel height of a display row holding a pair, bare.
        line_spacing: spacing1 + spacing3, added once per logical line.
        char_width: Pixel advance of a single base character.
        ruby_width: Pixel width of the embedded frame for (base, reading).
        lift: Pixels plain text is raised on a logical line that carries ruby,
            so its baseline meets the base characters inside the frames. A row
            of lifted plain text is that much taller; a row that has ruby on it
            is not, the frame already dominates its height.
    """
    content_plain: int
    content_ruby: int
    line_spacing: int
    char_width: Callable[[str], int]
    ruby_width: Callable[[str, str], int]
    lift: int = 0

    @property
    def row_plain(self) -> int:
        """Height of one `height` unit - the Text option counts base-font rows."""
        return self.content_plain + self.line_spacing

    @property
    def content_lifted(self) -> int:
        """Height of a plain display row that shares its line with ruby."""
        return self.content_plain + self.lift

    @property
    def row_ruby(self) -> int:
        """Height of a standalone logical line that carries ruby."""
        return self.content_ruby + self.line_spacing


class RowCounts(NamedTuple):
    """Display rows produced by a wrap simulation.

    `lifted_rows` are plain rows that happen to sit on a logical line which
    carries ruby somewhere else - a wrapped Japanese sentence whose tail lands
    on its own row. They are taller than `plain_rows` by the model's lift.
    """
    plain_rows: int
    ruby_rows: int
    logical_lines: int
    lifted_rows: int = 0


# Used when no Tk display is available (headless tests, early startup). The
# numbers are the measured Yu Gothic 11/7 values.
FALLBACK_LAYOUT = LayoutModel(
    content_plain=20,
    content_ruby=34,
    line_spacing=2 * LINE_SPACING,
    char_width=lambda ch: 11,
    ruby_width=lambda base, ruby: (max(len(base) * 20, len(ruby) * 8)
                                   + 2 * RUBY_PAD_X),
    lift=5 + RUBY_PAD_Y,          # Yu Gothic 11 descent, measured
)


def _as_font_tuple(spec, default_size: int) -> Tuple[str, int]:
    """Normalize a font spec to a (family, size) tuple."""
    if spec is None:
        return (CJK_FONT_FAMILY, default_size)
    if isinstance(spec, str):
        return (spec, default_size)
    return (spec[0], int(spec[1]))


def tk_layout_model(base_font=None, ruby_font=None,
                    line_spacing: Optional[int] = None) -> LayoutModel:
    """Build a LayoutModel from real font metrics.

    Falls back to FALLBACK_LAYOUT when there is no usable Tk interpreter, so
    callers never have to guard the call.

    Args:
        base_font: Font of the base text, (family, size) or family.
        ruby_font: Font of the readings.
        line_spacing: spacing1 + spacing3 of the target widget. Defaults to this
            module's own default; pass the widget's real values when it was
            configured differently, or every measurement is off by the
            difference on every line.

    The row heights are derived, not guessed:
        frame  = ruby linespace + base linespace + 2 * RUBY_PAD_Y
        ruby   = frame                     (align='baseline' hangs it above)
        plain  = base linespace
        lift   = base descent + RUBY_PAD_Y
        lifted = plain + lift
    plus line_spacing once per logical line. Verified against Text.dlineinfo()
    and Text.count(..., 'ypixels') on Tk 8.6: 42 px for a standalone ruby line,
    28 px plain, 76 px for a ruby line wrapped across two display rows.

    A ruby row is the bare frame, with nothing below the baseline. It used to be
    `frame + base descent`: the plain text on the row hung its descent under the
    baseline the frame was sitting on. Lifting that text removes the overhang,
    which is why annotated lines came out 5px shorter when the lift landed.

    `lift` is what `align='baseline'` costs. Tk puts the *bottom of the frame*
    on the line's baseline, so the base characters inside it end up exactly one
    descent (plus the frame's bottom padding) above the baseline that the plain
    text around them sits on - measured at 6 px with Yu Gothic 11, and plainly
    visible as text that does not line up. RubyText cancels it by raising the
    plain runs on that line by the same amount, which makes those runs' rows
    taller. A row that carries ruby absorbs it (the frame is taller anyway); a
    row of plain text on the same logical line does not, hence content_lifted.
    """
    base_spec = _as_font_tuple(base_font, BASE_FONT_SIZE)
    ruby_spec = _as_font_tuple(ruby_font, RUBY_FONT_SIZE)
    if line_spacing is None:
        line_spacing = 2 * LINE_SPACING

    try:
        base = font.Font(family=base_spec[0], size=base_spec[1])
        ruby = font.Font(family=ruby_spec[0], size=ruby_spec[1])
        base_line = int(base.metrics('linespace'))
        base_descent = int(base.metrics('descent'))
        ruby_line = int(ruby.metrics('linespace'))
    except Exception:
        return FALLBACK_LAYOUT._replace(line_spacing=line_spacing)

    frame_height = ruby_line + base_line + 2 * RUBY_PAD_Y
    char_cache: Dict[str, int] = {}

    def char_width(ch: str) -> int:
        width = char_cache.get(ch)
        if width is None:
            width = int(base.measure(ch))
            char_cache[ch] = width
        return width

    def ruby_width(base_text: str, ruby_text: str) -> int:
        return max(int(base.measure(base_text)),
                   int(ruby.measure(ruby_text))) + 2 * RUBY_PAD_X

    return LayoutModel(
        content_plain=base_line,
        content_ruby=frame_height,
        line_spacing=line_spacing,
        char_width=char_width,
        ruby_width=ruby_width,
        lift=base_descent + RUBY_PAD_Y,
    )


def layout_rows(segments: Sequence[RubySegment], available_px: int,
                model: LayoutModel) -> RowCounts:
    """Count the display rows `segments` will occupy, split by row kind.

    Simulates `wrap='char'`: an atom (one character, or one whole ruby frame)
    that does not fit moves to the next row. An atom wider than the whole line
    still gets a row of its own rather than looping forever.

    Args:
        segments: Segments as returned by the furigana engine.
        available_px: Usable content width in pixels.
        model: Measurement model (see tk_layout_model).

    Returns:
        RowCounts. Always at least one row and one logical line.
    """
    available_px = max(int(available_px), 40)

    rows: List[bool] = []          # True when the row carries ruby
    lifted = 0                     # plain rows sharing a line with ruby
    line_rows: List[bool] = []     # rows of the logical line being built
    logical_lines = 1
    row_width = 0
    row_has_ruby = False

    def close_row() -> None:
        nonlocal row_width, row_has_ruby
        rows.append(row_has_ruby)
        line_rows.append(row_has_ruby)
        row_width = 0
        row_has_ruby = False

    def close_line() -> None:
        """Charge the lift once the whole logical line is known.

        It cannot be decided per row: the ruby may arrive after the plain run
        that shares its line, and the lift is a property of the line.
        """
        nonlocal lifted
        if any(line_rows):
            lifted += sum(1 for has_ruby in line_rows if not has_ruby)
        line_rows.clear()

    for base, ruby in segments:
        if ruby:
            atoms: List[Tuple[int, bool]] = [(model.ruby_width(base, ruby), True)]
        else:
            atoms = []
            for ch in base:
                if ch == '\n':
                    atoms.append((-1, False))       # sentinel: hard break
                else:
                    atoms.append((model.char_width(ch), False))

        for width, is_ruby in atoms:
            if width < 0:
                close_row()
                close_line()
                logical_lines += 1
                continue
            if row_width and row_width + width > available_px:
                close_row()
            row_width += width
            row_has_ruby = row_has_ruby or is_ruby

    close_row()
    close_line()

    ruby_rows = sum(1 for has_ruby in rows if has_ruby)
    return RowCounts(len(rows) - ruby_rows - lifted, ruby_rows,
                     logical_lines, lifted)


def measure_px(segments: Sequence[RubySegment], available_px: int,
               model: Optional[LayoutModel] = None,
               base_font=None, ruby_font=None) -> int:
    """Pixel height `segments` need when laid out at `available_px` wide."""
    if model is None:
        model = tk_layout_model(base_font, ruby_font)
    counts = layout_rows(segments, available_px, model)
    return (counts.plain_rows * model.content_plain
            + counts.lifted_rows * model.content_lifted
            + counts.ruby_rows * model.content_ruby
            + counts.logical_lines * model.line_spacing)


def estimate_notation_px(notation: str, available_px: int,
                         max_rows: int = DEFAULT_MAX_ROWS,
                         model: Optional[LayoutModel] = None) -> int:
    """Height budget for a legacy {kanji|reading} string, capped at max_rows.

    Lets a caller size its window *before* creating the widget, which the
    quick-translate popup must do because an overrideredirect Toplevel gets its
    geometry exactly once.
    """
    if not notation:
        return 0
    if model is None:
        model = tk_layout_model()
    segments = furigana.parse_notation(notation)
    needed = measure_px(segments, available_px, model)
    return min(needed, max_rows * model.row_ruby)


def estimate_ruby_overhead_px(text: str, available_px: int,
                              lang_hint: Optional[str] = None,
                              max_rows: int = DEFAULT_MAX_ROWS,
                              model: Optional[LayoutModel] = None,
                              base_font=None, ruby_font=None,
                              line_spacing: Optional[int] = None) -> int:
    """Extra pixels annotating `text` needs beyond rendering it plain.

    A caller that already sized its window for plain text adds this to make
    room for the readings, instead of re-deriving the whole height with a
    different wrap model than it used originally.

    Returns 0 when nothing would be annotated, so it is safe to call blind.
    """
    if not text or len(text) > MAX_ANNOTATE_CHARS:
        return 0
    if not furigana.should_annotate(text, lang_hint):
        return 0
    segments = furigana.annotate(text, lang_hint)
    if not any(seg.ruby for seg in segments):
        return 0
    if model is None:
        model = tk_layout_model(base_font, ruby_font, line_spacing)
    ruby_px = min(measure_px(segments, available_px, model),
                  max_rows * model.row_ruby)
    plain_px = measure_px((RubySegment(text, None),), available_px, model)
    return max(0, ruby_px - plain_px)


def insert_output(widget: 'RubyText', index, text: str,
                  lang_hint: Optional[str] = None, enabled: bool = True,
                  tags=None, kanji_fg: Optional[str] = None) -> None:
    """Insert display text into a RubyText, annotating only when `enabled`.

    The one place every surface routes result text through, so the Settings
    toggle behaves identically everywhere and no call site repeats the branch.
    `enabled` stays a caller decision: only the caller knows whether its widget
    is showing a result, an error, or something the user is about to edit.
    """
    if enabled:
        widget.insert_ruby(index, text, lang_hint, tags, kanji_fg)
    else:
        widget.insert_plain(index, text, tags)


class RubyRow:
    """A standalone two-row ruby chip: readings on top, bases below.

    For surfaces that are not a `Text` widget - the dictionary word chips, the
    drag ghosts that preview them - where `RubyText` cannot be used but the same
    alignment is needed. A grid keeps every base on one line no matter how many
    readings the word carries (取り消し needs two, and concatenating them into
    one label would print the nonsense reading とけ).

    Attributes:
        frame: The container to embed or pack.
        bases: Labels holding the text itself.
        readings: Labels holding the readings, in the same order.
        widgets: frame + every label, for binding and recolouring.
    """

    def __init__(self, parent, segments: Sequence[RubySegment], *,
                 base_font=None, ruby_font=None, bg: str = DEFAULT_BG,
                 base_fg: str = KANJI_FG, ruby_fg: str = RUBY_FG,
                 padx: int = 2, pady: int = 1, cursor: Optional[str] = None):
        self.base_font = _as_font_tuple(base_font, BASE_FONT_SIZE)
        self.ruby_font = _as_font_tuple(ruby_font, RUBY_FONT_SIZE)
        self.bases: List[tk.Label] = []
        self.readings: List[tk.Label] = []

        extra = {'cursor': cursor} if cursor else {}
        self.frame = tk.Frame(parent, bg=bg, padx=padx, pady=pady, bd=0,
                              highlightthickness=0, **extra, **NO_AUTOSTYLE)
        for column, (base, ruby) in enumerate(segments):
            reading = tk.Label(self.frame, text=ruby or '', font=self.ruby_font,
                               bg=bg, fg=ruby_fg, padx=0, pady=0, **extra,
                               **NO_AUTOSTYLE)
            reading.grid(row=0, column=column, sticky='s')
            label = tk.Label(self.frame, text=base, font=self.base_font,
                             bg=bg, fg=base_fg, padx=0, pady=0, **extra,
                             **NO_AUTOSTYLE)
            label.grid(row=1, column=column, sticky='n')
            self.readings.append(reading)
            self.bases.append(label)

        self.widgets: List[tk.Misc] = [self.frame]
        for reading, label in zip(self.readings, self.bases):
            self.widgets.extend((reading, label))

    @property
    def has_ruby(self) -> bool:
        """True when at least one reading is displayed."""
        return any(label.cget('text') for label in self.readings)

    def bind_all_parts(self, sequence: str, handler) -> None:
        """Bind an event on the frame and every label inside it.

        Needed for both input and scrolling: a click or wheel event over a child
        label never reaches the frame, let alone the Text widget behind it.
        """
        for widget in self.widgets:
            widget.bind(sequence, handler)

    def set_colors(self, bg: Optional[str] = None, base_fg: Optional[str] = None,
                   ruby_fg: Optional[str] = None, base_font=None) -> None:
        """Recolour the chip, e.g. on selection."""
        if bg is not None:
            for widget in self.widgets:
                widget.configure(bg=bg)
        for label in self.bases:
            if base_fg is not None:
                label.configure(fg=base_fg)
            if base_font is not None:
                label.configure(font=base_font)
        if ruby_fg is not None:
            for label in self.readings:
                label.configure(fg=ruby_fg)

    def destroy(self) -> None:
        self.frame.destroy()


class RubyText(tk.Text):
    """A tk.Text that can render furigana inline and read its text back.

    Insertion methods accept plain text (`insert_ruby`, annotating on the way
    in) or the legacy notation (`insert_notation`). Both work while the widget
    is `state='disabled'`, so read-only surfaces need no state juggling.
    """

    PLAIN_TAG = 'ruby_plain'
    LIFT_TAG = 'ruby_lift'
    _INSERT_MARK = 'ruby_insert'

    def __init__(self, parent, *, base_font=None, ruby_font=None,
                 bg: str = DEFAULT_BG, base_fg: str = BASE_FG,
                 kanji_fg: str = KANJI_FG, ruby_fg: str = RUBY_FG,
                 ruby_bg: Optional[str] = None, wheel_units: int = WHEEL_UNITS,
                 **kwargs):
        self.base_font = _as_font_tuple(base_font, BASE_FONT_SIZE)
        self.ruby_font = _as_font_tuple(ruby_font, RUBY_FONT_SIZE)
        self._base_fg = base_fg
        self._kanji_fg = kanji_fg
        self._ruby_fg = ruby_fg
        self._wheel_units = wheel_units

        kwargs.setdefault('wrap', tk.CHAR)
        kwargs.setdefault('relief', 'flat')
        kwargs.setdefault('borderwidth', 0)
        kwargs.setdefault('highlightthickness', 0)
        kwargs.setdefault('spacing1', LINE_SPACING)
        kwargs.setdefault('spacing3', LINE_SPACING)
        kwargs.setdefault('cursor', 'arrow')
        kwargs.setdefault('font', self.base_font)
        kwargs.setdefault('fg', base_fg)

        super().__init__(parent, bg=bg, **kwargs)

        # A ruby pair carries no plate of its own: it takes the widget's real
        # background, read back after construction so a ttkbootstrap re-theme is
        # picked up too. That is the Word look - an annotated word is ordinary
        # text with a reading over it, not a tinted chip. RUBY_BG remains the
        # fallback, and a caller can still pass one to get a deliberate plate.
        if ruby_bg is None:
            try:
                ruby_bg = str(self.cget('bg'))
            except tk.TclError:
                ruby_bg = RUBY_BG
        self._ruby_bg = ruby_bg

        self.tag_configure(self.PLAIN_TAG, font=self.base_font,
                           foreground=base_fg)

        self._segments: List[RubySegment] = []
        self._frames: List[tk.Frame] = []
        self._window_base: Dict[str, str] = {}
        self._window_colors: Dict[str, Tuple[str, str, str]] = {}
        self._selected_frames: Set[str] = set()
        self._lifted_lines: Set[int] = set()
        self._layout: Optional[LayoutModel] = None

        # Cancels what align='baseline' costs: see tk_layout_model. Applied to
        # whole logical lines that carry ruby, never to the widget at large -
        # lifting a line with no frames on it would only make it taller.
        self.tag_configure(self.LIFT_TAG, offset=self.layout.lift)

        self.bind('<MouseWheel>', self._on_wheel)
        self.bind('<<Copy>>', self._on_copy)
        self.bind('<<Selection>>', self._on_selection)

    # ------------------------------------------------------------------ #
    # Insertion
    # ------------------------------------------------------------------ #
    @contextmanager
    def _editable(self):
        """Temporarily allow programmatic edits on a disabled widget."""
        previous = str(self.cget('state'))
        if previous != tk.NORMAL:
            self.config(state=tk.NORMAL)
        try:
            yield
        finally:
            if previous != tk.NORMAL:
                self.config(state=previous)

    def _advancing_index(self, index):
        """Return an index that moves along as successive runs are inserted.

        Segments must be inserted one run at a time, but a fixed index such as
        `'1.0'` would put every run *before* the previous one and silently
        reverse the text. `tk.END` already advances on its own; anything else
        gets a right-gravity mark that Tk pushes past each insertion.

        Returns:
            (index_to_use, mark_name_or_None) - the caller unsets the mark.
        """
        if str(index) in (tk.END, 'end', 'end-1c'):
            return tk.END, None
        self.mark_set(self._INSERT_MARK, index)
        self.mark_gravity(self._INSERT_MARK, 'right')
        return self._INSERT_MARK, self._INSERT_MARK

    def insert_segments(self, index, segments: Sequence[RubySegment],
                        tags=None, kanji_fg: Optional[str] = None) -> None:
        """Insert engine segments, drawing a ruby frame for each annotated run.

        Args:
            index: Text index to insert at, e.g. `tk.END`.
            segments: Segments from `furigana.annotate()` / `parse_notation()`.
            tags: Tag or tags applied to the plain runs. Defaults to PLAIN_TAG;
                pass an explicit tag to keep a caller's own colours.
            kanji_fg: Base-character colour for this insertion. Pass it
                whenever `tags` carries its own foreground, or the annotated
                words would keep the widget's default colour while the plain
                text around them changes.
        """
        if tags is None:
            tags = self.PLAIN_TAG

        with self._editable():
            at, mark = self._advancing_index(index)
            try:
                for base, ruby in segments:
                    if ruby:
                        self._insert_pair(at, base, ruby, kanji_fg)
                    elif base:
                        self.insert(at, base, tags)
            finally:
                if mark:
                    self.mark_unset(mark)
        self._segments.extend(segments)
        self._refresh_lift()

    def _insert_pair(self, index, base: str, ruby: str,
                     kanji_fg: Optional[str] = None) -> None:
        """Embed one reading-over-base frame at `index`."""
        frame = tk.Frame(self, bg=self._ruby_bg, bd=0, highlightthickness=0,
                         padx=0, pady=0, **NO_AUTOSTYLE)
        reading_label = tk.Label(frame, text=ruby, font=self.ruby_font,
                                 fg=self._ruby_fg, bg=self._ruby_bg, bd=0,
                                 padx=RUBY_PAD_X, pady=0, anchor='center',
                                 **NO_AUTOSTYLE)
        reading_label.pack(side='top', fill='x', pady=(RUBY_PAD_Y, 0))
        base_label = tk.Label(frame, text=base, font=self.base_font,
                              fg=kanji_fg or self._kanji_fg, bg=self._ruby_bg,
                              bd=0, padx=RUBY_PAD_X, pady=0, anchor='center',
                              **NO_AUTOSTYLE)
        base_label.pack(side='top', fill='x', pady=(0, RUBY_PAD_Y))

        # An embedded window would otherwise swallow the wheel event.
        for widget in (frame, reading_label, base_label):
            widget.bind('<MouseWheel>', self._on_wheel)

        self.window_create(index, window=frame, align='baseline')
        self._frames.append(frame)
        self._window_base[str(frame)] = base
        # Remembered, not read back later: selection overwrites them, and a
        # caller's kanji_fg (the dictionary's highlight colours) would be lost.
        self._window_colors[str(frame)] = (self._ruby_bg,
                                           kanji_fg or self._kanji_fg,
                                           self._ruby_fg)

        # An embedded window can be addressed by its path name, so this is the
        # frame's real line rather than a guess from the insertion index.
        try:
            self._lifted_lines.add(int(str(self.index(frame)).split('.')[0]))
        except (tk.TclError, ValueError):      # pragma: no cover - defensive
            pass

    def _refresh_lift(self) -> None:
        """Re-apply the baseline lift to every logical line that carries ruby.

        Re-applied rather than applied once, because a Tk tag does not grow into
        text inserted after its range: the dictionary window builds a line one
        run at a time, and a plain run added after the ruby would otherwise keep
        the unlifted baseline and sit 6px low next to the word before it.

        Line numbers are recorded when a frame is embedded. Every call site
        appends, so they stay valid; a line that has gone away is dropped.
        """
        for line in tuple(self._lifted_lines):
            try:
                # '+1c' takes in the newline that ends the line. It is a
                # character like any other: left unlifted it keeps its full
                # descent below the baseline and adds it to whichever display
                # row it lands on, which is the last one - measured as 5px of
                # slack under the final row of every annotated paragraph.
                self.tag_add(self.LIFT_TAG, f'{line}.0', f'{line}.end +1c')
            except tk.TclError:                # pragma: no cover - defensive
                self._lifted_lines.discard(line)

    def insert_ruby(self, index, text: str, lang_hint: Optional[str] = None,
                    tags=None, kanji_fg: Optional[str] = None) -> None:
        """Annotate `text` and insert it, falling back to plain when needed.

        Safe for any string: non-Japanese text, text with no available reading
        provider, and text past the render budget all insert as plain text.
        """
        if not text:
            return
        if (len(text) > MAX_ANNOTATE_CHARS
                or not furigana.should_annotate(text, lang_hint)):
            self.insert_plain(index, text, tags)
            return
        self.insert_segments(index, furigana.annotate(text, lang_hint), tags,
                             kanji_fg)

    def insert_notation(self, index, notation: str, tags=None,
                        kanji_fg: Optional[str] = None) -> None:
        """Insert a legacy {kanji|reading} string, honoring its escapes."""
        if not notation:
            return
        self.insert_segments(index, furigana.parse_notation(notation), tags,
                             kanji_fg)

    def insert_plain(self, index, text: str, tags=None) -> None:
        """Insert text with no annotation, keeping segment bookkeeping honest."""
        if not text:
            return
        if tags is None:
            tags = self.PLAIN_TAG
        with self._editable():
            self.insert(index, text, tags)
        self._segments.append(RubySegment(text, None))
        self._refresh_lift()

    def set_ruby(self, text: str, lang_hint: Optional[str] = None,
                 tags=None) -> None:
        """Replace all content with `text`, annotated."""
        self.clear()
        self.insert_ruby(tk.END, text, lang_hint, tags)

    def set_notation(self, notation: str, tags=None) -> None:
        """Replace all content with a legacy {kanji|reading} string."""
        self.clear()
        self.insert_notation(tk.END, notation, tags)

    def set_plain(self, text: str, tags=None) -> None:
        """Replace all content with unannotated text.

        Used to satisfy I3 (editable implies plain) before handing a widget to
        the user for typing: `edit_undo()` cannot restore destroyed embedded
        windows, so ruby must be gone before the first keystroke.
        """
        self.clear()
        self.insert_plain(tk.END, text, tags)

    def clear(self) -> None:
        """Delete all content. Tk destroys the embedded frames for us."""
        with self._editable():
            self.delete('1.0', tk.END)
        self._segments.clear()
        self._frames.clear()
        self._window_base.clear()
        self._window_colors.clear()
        self._selected_frames.clear()
        self._lifted_lines.clear()

    # ------------------------------------------------------------------ #
    # Readback
    # ------------------------------------------------------------------ #
    def get_plain(self, start='1.0', end='end-1c') -> str:
        """Return the real text, substituting each ruby frame for its base.

        Use this instead of `get()` anywhere the content is copied, pasted,
        re-sent to the model, or compared - `get()` drops every annotated word.
        """
        try:
            dumped = self.dump(start, end, text=True, window=True)
        except tk.TclError:
            return self.get(start, end)

        parts: List[str] = []
        for key, value, _index in dumped:
            if key == 'text':
                parts.append(value)
            elif key == 'window':
                parts.append(self._window_base.get(value, ''))
        return ''.join(parts)

    def _on_copy(self, _event=None):
        """Put the selection on the clipboard with its annotated words intact.

        Tk's own <<Copy>> exports the selected *characters*, and an embedded
        window has none - so every word carrying a reading silently vanished
        from anything the user selected and copied by hand, while the Copy
        buttons (which go through get_plain) were fine. Readings are left out
        on purpose: what is copied is the text, 日本語, not 日本語(にほんご).
        """
        try:
            first, last = self.index('sel.first'), self.index('sel.last')
        except tk.TclError:
            return None                        # nothing selected - let Tk be
        text = self.get_plain(first, last)
        if not text:
            return None
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except tk.TclError as e:               # pragma: no cover - defensive
            logging.debug(f"RubyText copy failed: {e}")
            return None
        return 'break'

    def _selection_colors(self) -> Tuple[Optional[str], Optional[str]]:
        """The widget's own selection colours, or (None, None) if unusable."""
        try:
            background = str(self.cget('selectbackground')) or None
            foreground = str(self.cget('selectforeground')) or None
        except tk.TclError:                    # pragma: no cover - defensive
            return None, None
        return background, foreground

    def _on_selection(self, _event=None) -> None:
        """Paint the ruby frames that fall inside the selection.

        An embedded window is not text, so Tk's `sel` tag draws straight past
        it: dragging across a sentence highlighted everything *except* the words
        carrying a reading, leaving holes exactly where the readings were - and
        making it look as though those words were not selected, which is also
        what they were not being copied for.

        The reading is recoloured with the base: `#80b8ff` on the selection
        background is unreadable, the same reason the word chips repaint theirs.
        """
        if not self._frames:
            return
        try:
            first, last = self.index('sel.first'), self.index('sel.last')
        except tk.TclError:
            first = last = None

        selected = set()
        if first is not None:
            for frame in self._frames:
                try:
                    index = self.index(frame)
                except tk.TclError:            # pragma: no cover - defensive
                    continue
                if self.compare(index, '>=', first) and self.compare(index, '<', last):
                    selected.add(str(frame))

        if selected == self._selected_frames:
            return                             # a drag fires this constantly
        self._selected_frames = selected

        select_bg, select_fg = self._selection_colors()
        if select_bg is None:                  # pragma: no cover - defensive
            return
        for frame in self._frames:
            key = str(frame)
            colors = self._window_colors.get(key)
            if colors is None:                 # pragma: no cover - defensive
                continue
            background, base_fg, ruby_fg = colors
            if key in selected:
                background = select_bg
                if select_fg:
                    base_fg = ruby_fg = select_fg
            try:
                reading, base = frame.winfo_children()
                frame.configure(bg=background)
                reading.configure(bg=background, fg=ruby_fg)
                base.configure(bg=background, fg=base_fg)
            except (tk.TclError, ValueError):  # pragma: no cover - defensive
                continue

    # ------------------------------------------------------------------ #
    # Sizing
    # ------------------------------------------------------------------ #
    @property
    def layout(self) -> LayoutModel:
        """Cached measurement model for this widget's fonts and line spacing."""
        if self._layout is None:
            try:
                spacing = int(self.cget('spacing1')) + int(self.cget('spacing3'))
            except (tk.TclError, ValueError):
                spacing = 2 * LINE_SPACING
            self._layout = tk_layout_model(self.base_font, self.ruby_font,
                                           line_spacing=spacing)
        return self._layout

    @property
    def ruby_pairs(self) -> int:
        """Number of ruby frames currently embedded."""
        return len(self._frames)

    @property
    def has_ruby(self) -> bool:
        """True when at least one reading is displayed."""
        return bool(self._frames)

    def required_px(self, available_px: Optional[int] = None) -> int:
        """Pixel height the current content needs at `available_px` wide."""
        if available_px is None:
            available_px = self.winfo_width()
            if available_px <= 1:
                available_px = int(self.cget('width')) * self.layout.row_plain
        return measure_px(self._segments, available_px, self.layout)

    def fit_height(self, available_px: Optional[int] = None,
                   max_rows: int = DEFAULT_MAX_ROWS,
                   min_rows: int = 1) -> int:
        """Set `height` so the content is not clipped, and return the pixels.

        `height` counts rows of the base font, but an annotated row is taller,
        so the pixel requirement is converted rather than passed through as a
        line count.

        Args:
            available_px: Wrap width. Defaults to the widget's current width.
            max_rows: Stop growing past this many ruby rows; the rest scrolls.
            min_rows: Floor, for callers that already computed a row count with
                a different wrap model (the popup measures word wrap, this
                class simulates character wrap) and must not shrink below it.
        """
        layout = self.layout
        needed = min(self.required_px(available_px), max_rows * layout.row_ruby)
        rows = max(1, min_rows, math.ceil(needed / layout.row_plain))
        try:
            self.config(height=rows)
        except tk.TclError as e:
            logging.debug(f"RubyText.fit_height failed: {e}")
        return needed

    # ------------------------------------------------------------------ #
    # Scrolling
    # ------------------------------------------------------------------ #
    def _on_wheel(self, event):
        """Scroll the widget, including when the pointer is over a ruby frame."""
        try:
            self.yview_scroll(int(-self._wheel_units * (event.delta / 120)), 'units')
        except tk.TclError:
            pass
        return 'break'
