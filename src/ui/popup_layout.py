"""
How big the quick-translate popup is and where it goes - the decisions, not the widgets.

Pure logic, no Tk: every input is a number `src/ui/quick_translate.py` measured on
the real widgets, every output a number it applies (Decision 34, TODO.md §5).

- **Width follows reading.** About 70 characters per line for Latin text and 36 for
  CJK (WCAG 1.4.8 asks for at most 80 / 40), never wider than the text needs, never
  narrower than the rows that must fit whole (the action bar, the header).
- **Height is the content's own**, up to a cap; beyond it a box scrolls. The
  translation comes first: when both do not fit, the original yields.
- **The popup never covers the cursor it was opened at** while either side of it has
  room; the boxes scroll instead.
"""
from typing import Callable, NamedTuple, Optional, Tuple

from src.constants import (
    POPUP_ANCHOR_OFFSET as ANCHOR_OFFSET,
    POPUP_HEIGHT_CAP_SHARE as HEIGHT_CAP_SHARE,
    POPUP_MAX_WIDTH_SHARE as MAX_WIDTH_SHARE,
    POPUP_ORIGINAL_SHARE as ORIGINAL_SHARE,
    POPUP_READING_CHARS_CJK as READING_CHARS_CJK,
    POPUP_READING_CHARS_LATIN as READING_CHARS_LATIN,
    POPUP_SCREEN_MARGIN as SCREEN_MARGIN,
)

Measure = Callable[[str], int]

# CJK ideographs, kana, Hangul and the fullwidth forms - written as code points, so
# the source holds no characters of those scripts.
_CJK_RANGES = ((0x2E80, 0x2FDF), (0x3000, 0x30FF), (0x3100, 0x31FF), (0x3400, 0x4DBF),
               (0x4E00, 0x9FFF), (0xAC00, 0xD7AF), (0xF900, 0xFAFF), (0xFF00, 0xFFEF))

ELLIPSIS = chr(0x2026)


class WorkArea(NamedTuple):
    """A monitor's work area (the screen less the taskbar), in screen pixels."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


class Heights(NamedTuple):
    """What each box gets, and whether it got less than its content needs."""

    translation: int
    original: int
    translation_capped: bool
    original_capped: bool

    @property
    def any_capped(self) -> bool:
        return self.translation_capped or self.original_capped


# --------------------------------------------------------------------------- #
# Width
# --------------------------------------------------------------------------- #
def is_cjk(character: str) -> bool:
    code = ord(character)
    return any(low <= code <= high for low, high in _CJK_RANGES)


def cjk_share(text: str) -> float:
    """The share of CJK characters among the visible ones, 0.0 to 1.0."""
    visible = [character for character in text if not character.isspace()]
    if not visible:
        return 0.0
    return sum(1 for character in visible if is_cjk(character)) / len(visible)


def reading_chars(text: str) -> float:
    """Characters per line that read comfortably for `text`: 70 for Latin text, 36 for
    CJK, in proportion for a mix."""
    return READING_CHARS_LATIN + (READING_CHARS_CJK - READING_CHARS_LATIN) * cjk_share(text)


def reading_width(text: str, measure: Measure, sample_chars: int = 2000) -> int:
    """Pixels for one comfortable line of `text`, in the font `measure` measures with:
    the text's own average character width times `reading_chars()`. 0 for no text."""
    sample = text.replace('\n', ' ')[:sample_chars]
    if not sample.strip():
        return 0
    return round(measure(sample) / len(sample) * reading_chars(text))


def natural_width(text: str, measure: Measure) -> int:
    """Pixels of the widest line of `text`, unwrapped."""
    return max((measure(line) for line in text.split('\n')), default=0)


def popup_width(natural: int, readable: int, insets: int, minimum: int,
                work_width: int) -> int:
    """The popup's width.

    The text gets its natural width, wrapped at the reading width; the popup adds
    `insets` (paddings, borders) around it. Never narrower than `minimum` - the rows
    that must fit whole - and, `minimum` permitting, never wider than
    `MAX_WIDTH_SHARE` of the work area.
    """
    text = min(natural, readable) if readable > 0 else natural
    ceiling = max(minimum, int(work_width * MAX_WIDTH_SHARE))
    return min(max(text + insets, minimum), ceiling)


def elide(text: str, measure: Measure, max_px: int) -> str:
    """`text` cut with an ellipsis so it measures at most `max_px` - unchanged when it
    already fits. The credit line's model names can be long; the close button must
    still be there."""
    if measure(text) <= max_px:
        return text
    for end in range(len(text) - 1, 0, -1):
        candidate = text[:end].rstrip() + ELLIPSIS
        if measure(candidate) <= max_px:
            return candidate
    return ELLIPSIS


# --------------------------------------------------------------------------- #
# Height
# --------------------------------------------------------------------------- #
def height_cap(work: WorkArea, saved: Optional[int] = None) -> int:
    """The tallest the popup may be: `HEIGHT_CAP_SHARE` of the work area, or the height
    the user dragged it to - inside the work area either way."""
    cap = saved if saved else int(work.height * HEIGHT_CAP_SHARE)
    return max(1, min(cap, work.height - 2 * SCREEN_MARGIN))


def allocate(room: int, translation: int, original: int = 0, *, min_translation: int,
             min_original: int = 0, original_limit: Optional[int] = None,
             original_share: float = ORIGINAL_SHARE) -> Heights:
    """Split `room` pixels between the translation box and the original block.

    `translation` / `original` are what each needs to show everything (0: no original
    block); `original_limit` is the collapsed block's height, when it is collapsed;
    `min_translation` / `min_original` the least a box squeezed by the cap keeps (its
    first rows). When both fit, both get what they need. Otherwise the original keeps
    at most `original_share` of the room and the translation gets the rest - the
    translation is what was asked for - and whatever the translation does not use goes
    back to the original. The minimums win over `room` on a screen too small for them.
    """
    wanted = original if original_limit is None else min(original, original_limit)
    if translation + wanted <= room:
        return Heights(translation, wanted, False, wanted < original)
    kept = 0
    if wanted:
        kept = min(wanted, max(min(min_original, wanted), int(room * original_share)))
    given = max(min(translation, room - kept), min(min_translation, translation))
    if kept < wanted and given + kept < room:
        kept = min(wanted, room - given)
    return Heights(given, kept, given < translation, kept < original)


# --------------------------------------------------------------------------- #
# Position
# --------------------------------------------------------------------------- #
def room_beside(anchor_y: int, work: WorkArea, offset_y: int = ANCHOR_OFFSET[1],
                margin: int = SCREEN_MARGIN) -> Tuple[int, int]:
    """Pixels free below and above the anchor, with the usual gap from it."""
    below = work.bottom - margin - (anchor_y + offset_y)
    above = (anchor_y - offset_y) - (work.top + margin)
    return max(0, below), max(0, above)


def place(anchor: Tuple[int, int], width: int, height: int, work: WorkArea, *,
          min_height: int, offset: Tuple[int, int] = ANCHOR_OFFSET,
          margin: int = SCREEN_MARGIN) -> Tuple[int, int, int]:
    """Where the popup goes: `(x, y, height)`.

    Right of the anchor, else left of it; below it, else above it - the first that
    holds the whole popup. When neither side holds it, the side with more room is
    taken and the height cut to that room (the boxes scroll): the popup does not
    cover the anchor. Only when neither side can hold even `min_height` is it pinned
    inside the work area wherever it fits.
    """
    anchor_x, anchor_y = anchor
    offset_x, offset_y = offset
    x = anchor_x + offset_x
    if x + width > work.right - margin:
        x = anchor_x - offset_x - width
    x = max(work.left + margin, min(x, work.right - margin - width))

    below, above = room_beside(anchor_y, work, offset_y, margin)
    if height <= below:
        return x, anchor_y + offset_y, height
    if height <= above:
        return x, anchor_y - offset_y - height, height
    if max(below, above) >= min_height:
        if below >= above:
            return x, anchor_y + offset_y, below
        return x, anchor_y - offset_y - above, above
    height = min(height, work.height - 2 * margin)
    y = max(work.top + margin, min(anchor_y + offset_y, work.bottom - margin - height))
    return x, y, height


def covers(x: int, y: int, width: int, height: int, point: Tuple[int, int]) -> bool:
    """Whether the rectangle covers `point`."""
    return x <= point[0] < x + width and y <= point[1] < y + height
