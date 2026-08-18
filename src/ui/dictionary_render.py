"""Render model for the dictionary result window (furigana + word highlighting).

The dictionary result is one pre-aligned block of text whose parts need very
different treatment:

* **Label columns must not move.** `_align_dictionary_text()` pads
  `N. **Label**:` with spaces so every value starts at the same column in a
  monospace font. Labels are ASCII and are never annotated, so a reading inside
  a *value* cannot shift them - but a reading inside a label would.
* **Pronunciation must stay bare.** That field holds IPA plus a target-language
  phonetic (`/həˈloʊ/, /ハロー/`); hiragana above katakana is redundant and
  invites reading it as a different word.
* **Looked-up words are colour-coded**, and the old implementation found them
  with `Text.search()` *after* insertion. That silently stops working once ruby
  is involved: an embedded window contributes no characters, so an annotated
  word can no longer be found and loses its colour.

Order matters. Readings are generated for a **whole line at once** and the
colours are painted onto the result, never the other way round: cutting a
sentence at the looked-up word first would hand the tokenizer isolated
fragments, and an all-kanji fragment (which is exactly what a looked-up word
often is - 勉強, 東京) cannot be annotated on its own at all. Painting is safe
because a plain run can be split anywhere, and a ruby pair is coloured whole.

`split_dictionary_text()` returns runs covering the text exactly once, so
`''.join(run.base for run in runs)` is the input string - the same "annotation
never alters text" guarantee the engine gives (I1).
"""
import re
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

from src.core import furigana
from src.core.furigana import RubySegment
from src.ui.ruby_text import MAX_ANNOTATE_CHARS, measure_px, tk_layout_model

# `1. **Translation**:` plus the alignment padding that follows it. The padding
# belongs to the label: it is what holds the value column in place.
FIELD_RE = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*:[ \t]*')

# `## [Word]` starts a new entry. Multi-word lookups return several.
ENTRY_PREFIX = '## '

# Fields the prompt requires to be written in the target language, so the target
# language is an authoritative hint there. It is what lets a kanji-only
# translation such as 犬 get a reading at all.
TARGET_LANGUAGE_FIELDS = (1, 3)
TARGET_LANGUAGE_LABELS = ('translation', 'definition')

# Field holding a phonetic transcription; see the module docstring.
PRONUNCIATION_FIELD = 5
PRONUNCIATION_LABELS = ('pronunciation',)

# The field where the model names the source language. Parsing it is what lets
# the source-language fields annotate kanji-only text: without a hint, kanji
# with no kana is indistinguishable from Chinese and is left plain.
SOURCE_LANGUAGE_LABELS = ('source language',)
JAPANESE_MARKERS = ('japanese', '日本語', 'nihongo')


class DictRun(NamedTuple):
    """One run of the result text, ready to insert.

    Attributes:
        base: The characters, verbatim.
        ruby: Reading to draw above `base`, or None for a plain run.
        color: Highlight colour of a looked-up word, or None.
    """
    base: str
    ruby: Optional[str] = None
    color: Optional[str] = None


def field_policy(number: int, label: str) -> Tuple[bool, bool]:
    """Decide how a numbered field's value is rendered.

    Both the number and the label are consulted: the number is what the prompt
    fixes, the label is what the model actually wrote, and models do renumber.

    Args:
        number: Leading field number.
        label: Label text between the `**` markers.

    Returns:
        (annotate, use_target_hint)
    """
    key = label.strip().lower()
    if number == PRONUNCIATION_FIELD or any(w in key for w in PRONUNCIATION_LABELS):
        return False, False
    if (number in TARGET_LANGUAGE_FIELDS
            or any(w in key for w in TARGET_LANGUAGE_LABELS)):
        return True, True
    return True, False


def source_language_hint(lines: Sequence[str]) -> Optional[str]:
    """Read the entry's declared source language, if it is one we can annotate.

    Returns "Japanese" when the **Source Language** field says so, else None.
    Only Japanese matters - it is the only language the engine annotates - and
    an unrecognized value degrades to no hint, i.e. today's behaviour.
    """
    for line in lines:
        match = FIELD_RE.match(line)
        if not match:
            continue
        if not any(w in match.group(2).strip().lower()
                   for w in SOURCE_LANGUAGE_LABELS):
            continue
        value = line[match.end():].strip().lower()
        if any(marker in value for marker in JAPANESE_MARKERS):
            return 'Japanese'
        return None
    return None


def _line_policy(line: str) -> Tuple[int, bool, bool]:
    """Return (label_length, annotate_value, use_target_hint) for one line.

    `label_length` is 0 unless the line is a numbered field, in which case that
    many leading characters are the label column and stay plain.
    """
    match = FIELD_RE.match(line)
    if not match:
        stripped = line.strip()
        if not stripped or stripped == '---':
            return 0, False, False
        # `## [Word]` headers, example lines and continuations are in the source
        # language.
        return 0, True, False
    annotate, use_target = field_policy(int(match.group(1)), match.group(2))
    return match.end(), annotate, use_target


def _match_ranges(text: str, words: Sequence[str],
                  colors: Sequence[str]) -> List[Tuple[int, int, str]]:
    """Character ranges of looked-up words, with their palette colour.

    Matching is case-insensitive, like the `Text.search(nocase=True)` it
    replaces. Where two words match at the same position the longer one wins, so
    a one-letter word cannot mask the phrase containing it. Ranges never
    overlap.
    """
    if not text or not words:
        return []
    ordered = sorted(
        ((word, colors[i % len(colors)]) for i, word in enumerate(words)
         if word and colors),
        key=lambda pair: len(pair[0]), reverse=True)
    if not ordered:
        return []

    lowered = text.lower()
    ranges: List[Tuple[int, int, str]] = []
    i = 0
    while i < len(text):
        for word, color in ordered:
            if lowered.startswith(word.lower(), i):
                ranges.append((i, i + len(word), color))
                i += len(word)
                break
        else:
            i += 1
    return ranges


def _color_at(start: int, end: int,
              ranges: Sequence[Tuple[int, int, str]]) -> Optional[str]:
    """Colour of the first highlighted range overlapping [start, end)."""
    for r_start, r_end, color in ranges:
        if r_start < end and start < r_end:
            return color
    return None


def _paint(segments: Sequence[RubySegment], ranges: Sequence[Tuple[int, int, str]],
           offset: int) -> List[DictRun]:
    """Apply highlight colours to already-annotated segments.

    Plain segments are split at colour boundaries; a ruby segment is atomic and
    takes the colour of any range it overlaps.

    Args:
        segments: Segments for one line part, in order.
        ranges: Highlight ranges, in coordinates of the whole line.
        offset: Index of `segments[0]` within that line.
    """
    runs: List[DictRun] = []
    position = offset
    for base, ruby in segments:
        end = position + len(base)
        if ruby:
            runs.append(DictRun(base, ruby, _color_at(position, end, ranges)))
            position = end
            continue

        # Cut the plain run at every colour boundary that falls inside it.
        cuts = {position, end}
        for r_start, r_end, _color in ranges:
            for edge in (r_start, r_end):
                if position < edge < end:
                    cuts.add(edge)
        previous = position
        for cut in sorted(cuts)[1:]:
            piece = base[previous - position:cut - position]
            if piece:
                runs.append(DictRun(piece, None,
                                    _color_at(previous, cut, ranges)))
            previous = cut
        position = end
    return runs


def _annotate(text: str, hint: Optional[str],
              allow: bool) -> Tuple[RubySegment, ...]:
    """Segments for one line part - annotated only when allowed and affordable."""
    if not allow or not text or len(text) > MAX_ANNOTATE_CHARS:
        return (RubySegment(text, None),) if text else ()
    return furigana.annotate(text, hint)


def _entry_hints(lines: Sequence[str]) -> Dict[int, Optional[str]]:
    """Per-line source-language hint, resolved per `## [Word]` entry.

    A multi-word lookup returns several entries and each declares its own source
    language, so the hint cannot be global.
    """
    hints: Dict[int, Optional[str]] = {}
    start = 0
    for index, line in enumerate(lines):
        if index and line.startswith(ENTRY_PREFIX):
            hint = source_language_hint(lines[start:index])
            for i in range(start, index):
                hints[i] = hint
            start = index
    hint = source_language_hint(lines[start:])
    for i in range(start, len(lines)):
        hints[i] = hint
    return hints


def split_dictionary_text(display_text: str, target_lang: Optional[str] = None,
                          looked_up_words: Optional[Sequence[str]] = None,
                          colors: Sequence[str] = (),
                          annotate: bool = True) -> Tuple[DictRun, ...]:
    """Turn an aligned dictionary result into coloured, annotated runs.

    Args:
        display_text: Output of `_align_dictionary_text()`.
        target_lang: Target language - the authoritative hint for the fields the
            prompt writes in it.
        looked_up_words: Words to colour-code, in the order their colours were
            assigned.
        colors: Palette indexed by word position.
        annotate: False disables furigana entirely (Settings toggle), leaving
            the highlighting intact.

    Returns:
        Runs whose `base` concatenates back to `display_text` exactly.
    """
    words = [w for w in (looked_up_words or []) if w]
    lines = display_text.split('\n')
    hints = _entry_hints(lines) if annotate else {}
    runs: List[DictRun] = []

    for index, line in enumerate(lines):
        if index:
            runs.append(DictRun('\n'))
        ranges = _match_ranges(line, words, colors)
        label_len, annotate_value, use_target = _line_policy(line)

        if label_len:
            runs.extend(_paint((RubySegment(line[:label_len], None),), ranges, 0))

        value = line[label_len:]
        if not value:
            continue
        hint = target_lang if use_target else hints.get(index)
        segments = _annotate(value, hint, annotate and annotate_value)
        runs.extend(_paint(segments, ranges, label_len))

    return tuple(runs)


def runs_to_segments(runs: Sequence[DictRun]) -> Tuple[RubySegment, ...]:
    """Flatten runs to segments, for measurement."""
    return tuple(RubySegment(run.base, run.ruby) for run in runs)


def overhead_px(runs: Sequence[DictRun], available_px: int,
                base_font=None, ruby_font=None,
                line_spacing: Optional[int] = None) -> int:
    """Extra pixels the readings in `runs` need beyond the plain text.

    Returns 0 when nothing is annotated, so the caller can add it blind. The
    window is sized before the widget exists (as in the quick-translate popup),
    hence a measurement rather than a query.
    """
    segments = runs_to_segments(runs)
    if not any(seg.ruby for seg in segments):
        return 0
    model = tk_layout_model(base_font, ruby_font, line_spacing)
    plain = RubySegment(''.join(run.base for run in runs), None)
    return max(0, measure_px(segments, available_px, model)
               - measure_px((plain,), available_px, model))
