"""What a translation prompt says about the source language, and the line a model answers with.

Decision 22: when the text itself cannot say whether kanji-only text is Japanese
or Chinese, the model that translates it is asked to say - in one marker line at
the top of its answer, which the app reads and removes before anyone sees it.
When the text does say (kana, or a glyph only one of the languages writes), the
prompt states it instead, and asks for nothing. Text that is not mostly CJK is
left exactly as it was: its prompt does not change by a byte.

    clause = source_clause(text)              # what to append to the prompt
    answer, verdict, found = parse_source_marker(model_output)

The marker is `[[SOURCE: Japanese]]`, `[[SOURCE: Chinese]]` or
`[[SOURCE: Unknown]]`. The wording never says which language is more common:
measured in J1, a "more common" tie-break turned gpt-oss-120b's 先生 into Chinese
"Mr." (Decision 21). A missing or garbled marker means "no verdict" - never an
error, and never shown.

Pure logic: no Tk, no config, no API.
"""
import re
from typing import NamedTuple, Optional, Tuple

from src.core.lang_id import (CHINESE, HAN_RE, JAPANESE, KANA_EVIDENCE_RE,
                              normalize_language, text_evidence)

# At least this share of the text's letters must be kanji or kana before the
# prompt says anything about Japanese or Chinese. "I love 你" is English with one
# Chinese word; telling the model "the text is Chinese" would be false.
CJK_SHARE = 0.5

# Hangul means Korean (Korean writes hanja too, rarely): leave it alone.
_HANGUL_RE = re.compile(r'[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F]')

MARKER_JAPANESE = "[[SOURCE: Japanese]]"
MARKER_CHINESE = "[[SOURCE: Chinese]]"
MARKER_UNKNOWN = "[[SOURCE: Unknown]]"

# `[[SOURCE: x]]` anywhere - the double brackets make it safe to remove wherever it is.
_MARKER_RE = re.compile(r'\[\[[ \t]*SOURCE[ \t]*[:\uFF1A][ \t]*([^\[\]\n]{0,40}?)[ \t]*\]\]',
                        re.IGNORECASE)
# `SOURCE: x` or `[SOURCE: x]` - only as the whole first line, where nothing else
# would put it.
_LINE_MARKER_RE = re.compile(
    r'\A[ \t]*\[?[ \t]*SOURCE[ \t]*[:\uFF1A][ \t]*([A-Za-z ()]{1,40}?)[ \t]*\]?[ \t]*\Z',
    re.IGNORECASE)


class SourceClause(NamedTuple):
    """What a translation prompt adds about the source language.

    Attributes:
        text: Appended to the prompt; "" leaves the prompt unchanged.
        stated: The language the clause states (from evidence), or None.
        asks: True when the clause asks the model for a marker line.
    """
    text: str
    stated: Optional[str]
    asks: bool


def cjk_dominant(text: Optional[str]) -> bool:
    """Whether kanji and kana make up at least CJK_SHARE of the text's letters,
    with no Hangul in it."""
    if not text or _HANGUL_RE.search(text):
        return False
    letters = sum(1 for ch in text if ch.isalpha())
    if not letters:
        return False
    cjk = len(HAN_RE.findall(text)) + len(KANA_EVIDENCE_RE.findall(text))
    return bool(HAN_RE.search(text)) and cjk / letters >= CJK_SHARE


def source_clause(text: Optional[str]) -> SourceClause:
    """The source-language clause for a translation prompt about `text`.

    - Not mostly CJK -> nothing (the prompt is unchanged).
    - Evidence in the text (kana, a Japanese-only or Chinese-only glyph) ->
      the language is stated, and nothing is asked.
    - Otherwise (kanji with nothing to tell the two apart) -> the model is asked
      to decide and to begin its answer with a marker line.
    """
    if not cjk_dominant(text):
        return SourceClause("", None, False)

    verdict = text_evidence(text)
    if verdict:
        language = JAPANESE if verdict.language == JAPANESE else "Chinese"
        return SourceClause(f"\n\nSOURCE LANGUAGE: the text above is {language}.",
                            verdict.language, False)

    return SourceClause(
        "\n\nSOURCE LANGUAGE - one extra line, the only exception to \"output only the result\":\n"
        "The text is written in Chinese characters without kana, so it may be Japanese or "
        "Chinese, and the same characters can mean different things in each (娘 is "
        "\"daughter\" in Japanese, \"mother\" in Chinese). Decide which language the text is, "
        "and read it with that language's meanings.\n"
        "Begin your response with exactly one of these lines:\n"
        f"{MARKER_JAPANESE}\n{MARKER_CHINESE}\n{MARKER_UNKNOWN}\n"
        "Use Unknown only when the text could equally be either. Then write the result on the "
        "next line.",
        None, True)


def _verdict(value: str) -> Optional[str]:
    """A marker's value as a language: Japanese, a Chinese variant, or None."""
    language = normalize_language(value)
    if language == JAPANESE or language in CHINESE:
        return language
    return None


def parse_source_marker(answer: str) -> Tuple[str, Optional[str], bool]:
    """Read and remove the marker line from a model's answer.

    Returns:
        (answer without the marker, verdict, found) - verdict is JAPANESE, a
        Chinese variant, or None (no marker, "Unknown", or anything else);
        `found` says whether a marker was there at all, for measuring compliance.
    """
    if not answer:
        return answer, None, False

    markers = list(_MARKER_RE.finditer(answer))
    if markers:
        verdict = _verdict(markers[0].group(1))
        lines = []
        for line in answer.split('\n'):
            stripped = _MARKER_RE.sub('', line)
            if stripped.strip() or not _MARKER_RE.search(line):
                lines.append(stripped.rstrip() if stripped != line else line)
        return '\n'.join(lines).strip(), verdict, True

    first, newline, rest = answer.lstrip().partition('\n')
    match = _LINE_MARKER_RE.match(first)
    if match:
        return rest.strip(), _verdict(match.group(1)), True

    return answer, None, False
