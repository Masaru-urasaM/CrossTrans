"""
Furigana engine for CrossTrans.

Produces ruby annotations (hiragana readings for kanji) as a structured segment
model instead of a hand-parsed string, so that any UI surface can render them.

Design (see DESIGN_DECISIONS.md):
- Generation happens at RENDER time, not inside the translation pipeline, so every
  surface that displays Japanese can annotate without new queue plumbing.
- Readings come from a provider chain: fugashi/UniDic (morphological, accurate) is
  preferred, pykakasi (bundled, always available) is the fallback.
- The aligner is FAIL-SAFE: when a reading cannot be mapped onto its kanji
  deterministically it returns None and the text is shown WITHOUT ruby. For a
  learner a wrong reading is worse than a blank one, because it is unfalsifiable
  at the point of use.

Invariant I1: ''.join(seg.base for seg in annotate(text)) == text
This makes the old {kanji|reading} injection class structurally impossible.
"""
import re
import logging
import threading
from functools import lru_cache
from typing import List, NamedTuple, Optional, Protocol, Sequence, Tuple

# --------------------------------------------------------------------------- #
# Character classes
# --------------------------------------------------------------------------- #
# Kanji: CJK Unified Ideographs + Extension A (same ranges the app used before).
KANJI_RE = re.compile(r'[\u4E00-\u9FFF\u3400-\u4DBF]')
# Kana evidence: hiragana or katakana. Distinguishes Japanese from Chinese hanzi.
KANA_RE = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')

# A span that is nothing but kanji. Compound readings (rendaku, onbin) only apply
# to kanji compounds, so this gates the compound-refinement rule below.
ALL_KANJI_RE = re.compile(r'\A[\u4E00-\u9FFF\u3400-\u4DBF]+\Z')

# UniDic pos2 tag for a numeral. Digits carry no reading of their own, so a kanji
# counter following one cannot be annotated in isolation.
NUMERAL_POS2 = '数詞'

# Whitespace runs are annotated around, never through: tokenizers normalize them
# away, which would silently drop newlines from a multi-line translation.
WHITESPACE_RE = re.compile(r'(\s+)')

# Rendering cost guard. Measured on Tk 8.6: 200 ruby pairs ~124 ms to build and
# lay out, 500 ~400 ms, 1000 ~626 ms. Above the cap we return plain text so a
# pasted document can never freeze the UI thread.
MAX_RUBY_PAIRS = 400

# Notation delimiters, kept only for backward compatibility with the legacy
# {kanji|reading} string format still consumed by the popup renderer.
_NOTATION_SPECIALS = '\\{}|'

_lock = threading.RLock()


class RubySegment(NamedTuple):
    """One run of text, optionally carrying a reading to draw above it.

    Attributes:
        base: The literal source characters. Never modified.
        ruby: Hiragana reading to render above `base`, or None for plain runs
            (kana, latin, digits, punctuation, whitespace).
    """
    base: str
    ruby: Optional[str]


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #
def has_kanji(text: str) -> bool:
    """Check whether text contains at least one kanji."""
    return bool(text) and bool(KANJI_RE.search(text))


def has_kana(text: str) -> bool:
    """Check whether text contains hiragana or katakana."""
    return bool(text) and bool(KANA_RE.search(text))


def is_japanese(text: str) -> bool:
    """Check whether text contains any Japanese script (kana or kanji).

    Kept as the permissive check the old _is_japanese_text() performed. Note it
    also matches Chinese hanzi; use should_annotate() to decide about ruby.
    """
    return has_kana(text) or has_kanji(text)


def should_annotate(text: str, lang_hint: Optional[str] = None) -> bool:
    """Decide whether ruby should be generated for this string.

    Requires kanji (nothing to annotate otherwise) AND positive evidence that the
    text is Japanese rather than Chinese: either kana somewhere in the string, or
    an explicit language hint from a caller that already knows.

    The hint matters: kanji-only strings such as "東京都" or "電源設定" are the
    normal case for a dictionary word chip, and nlp_manager.detect_language()
    reports Chinese for them (it forces a Chinese verdict when the hiragana count
    is zero), so detection alone would leave exactly those unannotated.

    Args:
        text: The string about to be displayed.
        lang_hint: Language name the caller already knows, e.g. "Japanese".

    Returns:
        True when ruby generation should be attempted.
    """
    if not has_kanji(text):
        return False
    return has_kana(text) or lang_hint == "Japanese"


# --------------------------------------------------------------------------- #
# Kana helpers
# --------------------------------------------------------------------------- #
def _kata_to_hira(text: str) -> str:
    """Convert katakana to hiragana, leaving everything else untouched.

    Reading providers return katakana (UniDic) or hiragana (pykakasi); ruby is
    conventionally hiragana, and matching needs one normalized form.
    """
    out: List[str] = []
    for ch in text:
        cp = ord(ch)
        if 0x30A1 <= cp <= 0x30F6:
            out.append(chr(cp - 0x60))
        else:
            out.append(ch)
    return ''.join(out)


def _split_runs(surface: str) -> List[Tuple[bool, str]]:
    """Split a surface form into consecutive (is_kanji, run) pairs."""
    runs: List[Tuple[bool, str]] = []
    for ch in surface:
        is_kanji = bool(KANJI_RE.match(ch))
        if runs and runs[-1][0] == is_kanji:
            runs[-1] = (is_kanji, runs[-1][1] + ch)
        else:
            runs.append((is_kanji, ch))
    return runs


# --------------------------------------------------------------------------- #
# Aligner — the correctness-critical part
# --------------------------------------------------------------------------- #
def align(surface: str, reading: Optional[str]) -> Optional[Tuple[RubySegment, ...]]:
    """Map a whole-token reading onto the kanji runs inside its surface form.

    Anchors on the kana already present in the surface. For surface "取り消し"
    with reading "とりけし": the kana runs り and し must appear in the reading in
    order, so 取 takes と (before り) and 消 takes け (between り and し), giving
    {取|と}り{消|け}し. The previous implementation only stripped a TRAILING kana
    suffix and produced {取り消|とりけ}し, with the ruby covering the り.

    Args:
        surface: The literal token text.
        reading: Whole-token reading (katakana or hiragana), or None.

    Returns:
        Segments whose bases concatenate back to `surface`, or None when the
        reading cannot be aligned deterministically (caller must then render
        `surface` plain rather than guess).
    """
    if not surface:
        return ()
    if not reading:
        return None

    reading = _kata_to_hira(reading)
    runs = _split_runs(surface)

    # Nothing to annotate: no kanji in this token.
    if not any(is_kanji for is_kanji, _ in runs):
        return (RubySegment(surface, None),)

    # Reading identical to the surface (already all kana) - nothing to add.
    if _kata_to_hira(surface) == reading:
        return (RubySegment(surface, None),)

    segments: List[RubySegment] = []
    pos = 0  # cursor into `reading`

    for idx, (is_kanji, run) in enumerate(runs):
        if not is_kanji:
            # A kana run must appear verbatim in the reading at the cursor.
            expected = _kata_to_hira(run)
            if not reading.startswith(expected, pos):
                return None
            segments.append(RubySegment(run, None))
            pos += len(expected)
            continue

        # Kanji run: its reading ends where the NEXT kana run begins.
        next_kana = None
        for later_is_kanji, later_run in runs[idx + 1:]:
            if not later_is_kanji:
                next_kana = _kata_to_hira(later_run)
                break

        if next_kana is None:
            # Last kanji run: it takes whatever reading remains.
            end = len(reading)
        else:
            # Each kanji needs at least one kana, so start searching past them.
            end = reading.find(next_kana, pos + len(run))
            if end < 0:
                return None

        chunk = reading[pos:end]
        if not chunk:
            return None
        segments.append(RubySegment(run, chunk))
        pos = end

    # Every kana of the reading must have been consumed.
    if pos != len(reading):
        return None

    if ''.join(s.base for s in segments) != surface:
        return None

    return tuple(segments)


def _merge_plain(segments: Sequence[RubySegment]) -> Tuple[RubySegment, ...]:
    """Collapse adjacent ruby-less segments so the renderer makes fewer widgets."""
    merged: List[RubySegment] = []
    for seg in segments:
        if seg.ruby is None and merged and merged[-1].ruby is None:
            merged[-1] = RubySegment(merged[-1].base + seg.base, None)
        else:
            merged.append(seg)
    return tuple(merged)


# --------------------------------------------------------------------------- #
# Reading providers
# --------------------------------------------------------------------------- #
class ReadingProvider(Protocol):
    """Produces per-token (surface, reading) pairs for Japanese text."""

    name: str

    def is_available(self) -> bool:
        """Check whether this provider can run right now."""
        ...

    def tokens(self, text: str) -> Optional[List[Tuple[str, Optional[str]]]]:
        """Return (surface, reading) pairs covering `text`, or None on failure."""
        ...


def _token_reading(word) -> Optional[str]:
    """Read the kana field off a fugashi token across UniDic feature layouts.

    unidic-lite exposes UnidicFeatures17 (which carries `pron`), full unidic
    exposes UnidicFeatures26 (which carries `kana`); try both plus the lemma
    form so either dictionary works.
    """
    feature = getattr(word, 'feature', None)
    if feature is None:
        return None
    for attr in ('kana', 'pron', 'reading', 'lForm'):
        value = getattr(feature, attr, None)
        if value and value != '*':
            return value
    return None


class FugashiProvider:
    """Morphological readings via fugashi + UniDic (the app's Japanese NLP pack).

    Preferred provider: it disambiguates homographs that a dictionary-matching
    transliterator gets wrong (今日 -> きょう not こんにち, 一日 -> いちにち not
    ついたち). Availability depends on the user having installed the Japanese
    language pack via Settings -> Dictionary.
    """

    name = "fugashi"

    def __init__(self) -> None:
        self._tagger = None
        self._unavailable = False

    def _get_tagger(self):
        """Build the Tagger once (init is ~3 ms; construction per call is not)."""
        if self._tagger is not None or self._unavailable:
            return self._tagger
        with _lock:
            if self._tagger is None and not self._unavailable:
                try:
                    import fugashi
                    self._tagger = fugashi.Tagger()
                    logging.info("Furigana: fugashi provider ready")
                except Exception as e:
                    self._unavailable = True
                    logging.info(f"Furigana: fugashi unavailable ({e})")
        return self._tagger

    def is_available(self) -> bool:
        return self._get_tagger() is not None

    def tokens(self, text: str) -> Optional[List[Tuple[str, Optional[str]]]]:
        tagger = self._get_tagger()
        if tagger is None:
            return None
        try:
            words = list(tagger(text))
        except Exception as e:
            logging.warning(f"Furigana: fugashi tokenize failed: {e}")
            return None

        result: List[Tuple[str, Optional[str]]] = []
        for i, word in enumerate(words):
            reading = _token_reading(word)

            # A counter after a digit carries only PART of the combined reading:
            # "2日" is futsu-ka, so drawing just カ over 日 invites the misreading
            # "ni-ka". The digit holds the rest and cannot take ruby, so suppress
            # the whole pair. Also filters real errors here: 2人 is futari, not
            # ni-NIN, and standalone 1月 reports ツキ instead of ガツ.
            if reading and i > 0:
                previous = getattr(words[i - 1], 'feature', None)
                if (previous is not None
                        and getattr(previous, 'pos2', '') == NUMERAL_POS2
                        and not _token_reading(words[i - 1])):
                    reading = None

            result.append((word.surface, reading))
        return result


class KakasiProvider:
    """Readings via pykakasi (bundled in the EXE, so always available).

    Dictionary-matching transliteration with no part-of-speech context, so some
    homograph readings are wrong. The aligner still fixes its okurigana spans,
    and rejects anything it cannot map, so wrong-span ruby never reaches the UI.
    """

    name = "pykakasi"

    def __init__(self) -> None:
        self._kks = None
        self._unavailable = False

    def _get_kks(self):
        """Build the kakasi instance once.

        Construction measured at ~175 ms versus ~0.3 ms per conversion; the old
        code constructed it on every call.
        """
        if self._kks is not None or self._unavailable:
            return self._kks
        with _lock:
            if self._kks is None and not self._unavailable:
                try:
                    from pykakasi import kakasi
                    self._kks = kakasi()
                    logging.info("Furigana: pykakasi provider ready")
                except Exception as e:
                    self._unavailable = True
                    # Covers both a missing package and missing bundled dictionary
                    # data (kanwadict4.db), which raises FileNotFoundError here.
                    logging.warning(f"Furigana: pykakasi unavailable ({e})")
        return self._kks

    def is_available(self) -> bool:
        return self._get_kks() is not None

    def tokens(self, text: str) -> Optional[List[Tuple[str, Optional[str]]]]:
        kks = self._get_kks()
        if kks is None:
            return None
        try:
            return [(item['orig'], item.get('hira')) for item in kks.convert(text)]
        except Exception as e:
            logging.warning(f"Furigana: pykakasi convert failed: {e}")
            return None


_FUGASHI = FugashiProvider()
_KAKASI = KakasiProvider()
_PROVIDERS: List[ReadingProvider] = [_FUGASHI, _KAKASI]


def _token_spans(tokens: Sequence[Tuple[str, Optional[str]]]
                 ) -> List[Tuple[int, int, str, Optional[str]]]:
    """Annotate tokens with their (start, end) character offsets."""
    spans: List[Tuple[int, int, str, Optional[str]]] = []
    pos = 0
    for surface, reading in tokens:
        spans.append((pos, pos + len(surface), surface, reading))
        pos += len(surface)
    return spans


def _refine_compounds(tokens: List[Tuple[str, Optional[str]]], text: str
                      ) -> List[Tuple[str, Optional[str]]]:
    """Restore whole-compound readings that morphological splitting destroys.

    A morphological analyser splits compounds into their parts, and the parts'
    dictionary readings do not always concatenate to the compound's real reading:
    UniDic tags 日本 as a proper noun reading ニッポン, so 日本語 comes out
    "nippon-go" instead of nihon-go, and 日本人 "nippon-nin" instead of nihon-jin.
    A transliteration dictionary keeps such compounds whole and has the right
    reading for them.

    So when the fallback dictionary holds a single ALL-KANJI entry spanning two or
    more of our tokens, its compound reading wins. The all-kanji restriction is
    what makes this safe: it is also why 今日 keeps the analyser's correct きょう
    instead of being swallowed by the greedy 今日は -> こんにちは greeting entry.

    Args:
        tokens: (surface, reading) pairs from the primary provider.
        text: The original string the tokens cover.

    Returns:
        Tokens with all-kanji compounds merged where a better reading exists.
    """
    fallback = _KAKASI.tokens(text)
    if not fallback:
        return tokens

    primary_spans = _token_spans(tokens)
    fallback_spans = _token_spans(fallback)

    refined: List[Tuple[str, Optional[str]]] = []
    index = 0
    while index < len(primary_spans):
        start = primary_spans[index][0]
        merge: Optional[Tuple[str, str, int]] = None

        for f_start, f_end, f_surface, f_reading in fallback_spans:
            if f_start != start or not f_reading:
                continue
            if not ALL_KANJI_RE.match(f_surface):
                continue
            covered = [s for s in primary_spans if s[0] >= f_start and s[1] <= f_end]
            # Require an exact span match over at least two primary tokens.
            if len(covered) >= 2 and covered[-1][1] == f_end:
                merge = (f_surface, f_reading, len(covered))
                break

        if merge:
            refined.append((merge[0], merge[1]))
            index += merge[2]
        else:
            _, _, surface, reading = primary_spans[index]
            refined.append((surface, reading))
            index += 1

    return refined


def active_provider_name() -> Optional[str]:
    """Name of the provider that would be used now, or None if none can run."""
    for provider in _PROVIDERS:
        if provider.is_available():
            return provider.name
    return None


def is_available() -> bool:
    """Check whether any reading provider can run."""
    return active_provider_name() is not None


def prewarm() -> None:
    """Build the reading engine off the UI thread.

    Call from the app's background startup path so the first annotation does not
    pay dictionary-load cost on the Tk main loop.
    """
    try:
        active_provider_name()
    except Exception as e:
        logging.debug(f"Furigana prewarm failed: {e}")


# --------------------------------------------------------------------------- #
# Public annotation API
# --------------------------------------------------------------------------- #
def _annotate_chunk(chunk: str) -> Tuple[RubySegment, ...]:
    """Annotate one whitespace-free chunk using the first provider that works.

    Falls back through the provider chain, then to plain text. A provider whose
    tokens do not reassemble into `chunk` is rejected rather than trusted.
    """
    for provider in _PROVIDERS:
        tokens = provider.tokens(chunk)
        if tokens is None:
            continue

        if provider is _FUGASHI:
            tokens = _refine_compounds(tokens, chunk)

        segments: List[RubySegment] = []
        for surface, reading in tokens:
            if not surface:
                continue
            if not has_kanji(surface):
                segments.append(RubySegment(surface, None))
                continue
            aligned = align(surface, reading)
            if aligned is None:
                # Fail-safe: keep the text, drop the reading we cannot trust.
                segments.append(RubySegment(surface, None))
            else:
                segments.extend(aligned)

        if ''.join(seg.base for seg in segments) != chunk:
            logging.warning(
                f"Furigana: {provider.name} did not round-trip a chunk, "
                "trying the next provider"
            )
            continue

        return tuple(segments)

    return (RubySegment(chunk, None),)


def _annotate_uncached(text: str, lang_hint: Optional[str]) -> Tuple[RubySegment, ...]:
    """Annotate without caching. Never raises; falls back to plain text."""
    plain = (RubySegment(text, None),)

    if not text:
        return ()
    if not should_annotate(text, lang_hint):
        return plain

    # Tokenizers normalize away whitespace, which would break invariant I1 for any
    # multi-line translation. Annotate the whitespace-free chunks and re-insert the
    # separators verbatim, so newlines and spaces always survive untouched.
    segments: List[RubySegment] = []
    for chunk in WHITESPACE_RE.split(text):
        if not chunk:
            continue
        if has_kanji(chunk):
            segments.extend(_annotate_chunk(chunk))
        else:
            segments.append(RubySegment(chunk, None))

    merged = _merge_plain(segments)

    # Invariant I1: annotation must never alter the text it describes.
    if ''.join(seg.base for seg in merged) != text:
        logging.error("Furigana: annotation did not round-trip, rendering plain")
        return plain

    pair_count = sum(1 for seg in merged if seg.ruby)
    if pair_count == 0:
        return plain
    if pair_count > MAX_RUBY_PAIRS:
        logging.info(
            f"Furigana: {pair_count} pairs exceeds MAX_RUBY_PAIRS "
            f"({MAX_RUBY_PAIRS}), rendering plain"
        )
        return plain
    return merged


@lru_cache(maxsize=256)
def _annotate_cached(text: str, lang_hint: Optional[str]) -> Tuple[RubySegment, ...]:
    return _annotate_uncached(text, lang_hint)


def annotate(text: str, lang_hint: Optional[str] = None) -> Tuple[RubySegment, ...]:
    """Annotate text with ruby readings.

    Safe to call on ANY string: non-Japanese, empty, Chinese-only and
    provider-less cases all return a single plain segment, so callers need no
    branching. Guarantees invariant I1 - the segment bases always concatenate
    back to `text` exactly.

    Args:
        text: The string about to be displayed.
        lang_hint: Language name the caller already knows, e.g. "Japanese".
            Required to annotate kanji-only strings (see should_annotate).

    Returns:
        Tuple of RubySegment. Empty tuple only for empty input.
    """
    try:
        return _annotate_cached(text, lang_hint)
    except Exception as e:
        logging.error(f"Furigana annotation failed: {e}")
        return (RubySegment(text, None),) if text else ()


def annotate_tokens(tokens: Sequence[str], text: str,
                    lang_hint: Optional[str] = None
                    ) -> Tuple[Tuple[RubySegment, ...], ...]:
    """Annotate a tokenization *in context*, one segment tuple per token.

    Readings are generated for the whole `text` once and then handed out to the
    tokens that contain them, rather than annotating each token on its own.
    That matters because the caller's tokenizer and this module disagree about
    compounds: a dictionary tokenizer splits 日本語 into 日本 + 語, and 日本 read
    alone is にっぽん while inside 日本語 it is にほん.

    A token that cuts through a *reading* gets no reading at all - blank beats
    wrong, and a fragment of a compound is exactly the case where a per-token
    reading would be wrong. Plain runs are clipped to the token instead, since
    splitting text that carries no reading cannot make it wrong: the tokenizer's
    会い keeps 会[あ] even though the plain run beside it continues past the
    token.

    Args:
        tokens: Tokens in the order they appear in `text`.
        text: The full string the tokens came from; the annotation context.
        lang_hint: Language name the caller knows, e.g. "Japanese".

    Returns:
        One tuple of RubySegment per input token, always the same length as
        `tokens`. Each tuple's bases concatenate back to its token (I1).
    """
    plain = tuple((RubySegment(token, None),) if token else () for token in tokens)
    if not tokens or not text or not should_annotate(text, lang_hint):
        return plain

    segments = annotate(text, lang_hint)
    if not any(seg.ruby for seg in segments):
        return plain

    # Absolute span of every segment within `text`.
    spans: List[Tuple[int, int, RubySegment]] = []
    position = 0
    for segment in segments:
        spans.append((position, position + len(segment.base), segment))
        position += len(segment.base)

    result: List[Tuple[RubySegment, ...]] = []
    cursor = 0
    for token in tokens:
        if not token:
            result.append(())
            continue
        start = text.find(token, cursor)
        if start < 0:
            result.append((RubySegment(token, None),))
            continue
        end = start + len(token)
        cursor = end
        covering = [span for span in spans if span[0] < end and start < span[1]]
        pieces: List[RubySegment] = []
        for span_start, span_end, segment in covering:
            if segment.ruby:
                # Never clipped: a reading belongs to the whole run it was
                # aligned to, so half of 日本語/にほんご is not 日本/にほんご. An
                # overhanging run makes the join below fail, which is what
                # leaves the token bare.
                pieces.append(segment)
            else:
                clipped = segment.base[max(0, start - span_start):
                                       len(segment.base) - max(0, span_end - end)]
                if clipped:
                    pieces.append(RubySegment(clipped, None))
        # The join is the decision: it is invariant I1 applied per token, and it
        # is what rejects a token that cuts through a reading.
        if pieces and ''.join(piece.base for piece in pieces) == token:
            result.append(tuple(pieces))
        else:
            result.append((RubySegment(token, None),))
    return tuple(result)


def clear_cache() -> None:
    """Drop the annotation cache (used by tests and after a provider change)."""
    _annotate_cached.cache_clear()


# --------------------------------------------------------------------------- #
# Legacy {kanji|reading} notation
# --------------------------------------------------------------------------- #
def to_notation(segments: Sequence[RubySegment]) -> str:
    """Serialize segments to the legacy {kanji|reading} string format.

    Escapes the delimiters so source text containing braces or pipes cannot be
    mistaken for a ruby pair on the way back in. Kept only for the popup
    renderer that still parses this format; new code should use segments.
    """
    def esc(value: str) -> str:
        for ch in _NOTATION_SPECIALS:
            value = value.replace(ch, '\\' + ch)
        return value

    parts: List[str] = []
    for base, ruby in segments:
        if ruby:
            parts.append('{' + esc(base) + '|' + esc(ruby) + '}')
        else:
            parts.append(esc(base))
    return ''.join(parts)


def parse_notation(notation: str) -> Tuple[RubySegment, ...]:
    """Parse the legacy {kanji|reading} format back into segments.

    Honors the backslash escapes written by to_notation(), so a literal "{a|b}"
    in the source round-trips as text instead of becoming a ruby pair.
    """
    segments: List[RubySegment] = []
    buf: List[str] = []
    i = 0
    length = len(notation)

    def flush() -> None:
        if buf:
            segments.append(RubySegment(''.join(buf), None))
            buf.clear()

    while i < length:
        ch = notation[i]

        if ch == '\\' and i + 1 < length and notation[i + 1] in _NOTATION_SPECIALS:
            buf.append(notation[i + 1])
            i += 2
            continue

        if ch == '{':
            base: List[str] = []
            ruby: List[str] = []
            target = base
            j = i + 1
            closed = False
            while j < length:
                cj = notation[j]
                if cj == '\\' and j + 1 < length and notation[j + 1] in _NOTATION_SPECIALS:
                    target.append(notation[j + 1])
                    j += 2
                    continue
                if cj == '|' and target is base:
                    target = ruby
                    j += 1
                    continue
                if cj == '}':
                    closed = True
                    j += 1
                    break
                target.append(cj)
                j += 1

            if closed and base and ruby:
                flush()
                segments.append(RubySegment(''.join(base), ''.join(ruby)))
                i = j
                continue
            # Unterminated or malformed - treat the brace as literal text.
            buf.append(ch)
            i += 1
            continue

        buf.append(ch)
        i += 1

    flush()
    return _merge_plain(segments)


def generate_notation(text: str, lang_hint: Optional[str] = None) -> Optional[str]:
    """Annotate text and return it in the legacy notation, or None if no ruby.

    Compatibility helper for the translation pipeline, which still ships a
    notation string through the queue.

    Delimiters in the source text are escaped by to_notation() and unescaped by
    parse_notation(), which is what the renderer uses, so a literal "{A|B}"
    survives as text instead of becoming a fake ruby pair.
    """
    segments = annotate(text, lang_hint)
    if not any(seg.ruby for seg in segments):
        return None
    return to_notation(segments)
