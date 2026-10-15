"""The dictionary lookup prompt: which language a headword is from, and what it is read in.

A headword written only in kanji is ambiguous on its own - 手紙 is "letter" in
Japanese and "toilet paper" in Chinese - and the prompt used to send it with
neither its source language nor the sentence it came from. Measured on
2026-10-15 (`tools/eval_dictionary_prompt.py`, ten such false friends, no
context): gemini-2.5-flash, gpt-oss-120b and the trial model's llama-3.3-70b each
read 汽車, 工作 and 床 as Chinese - 3 of 10, all three providers. A model that
decides "Chinese" writes a Chinese entry, and the result window then leaves the
whole entry without readings.

So the prompt states the source language whenever the caller knows it, and
sends the sentences the headwords were selected from. When the source is not
known, the model is told so and asked to decide - and to say what it decided in
field 2, which the result window reads.

Pure logic: no Tk, no config, no API - everything here is unit-tested directly.
"""
import re
from typing import List, Optional, Sequence, Tuple

# Upper bound on the context sent with a lookup. An educated guess (TODO.md Q3):
# a few sentences, enough to settle the sense of a word, without sending a whole
# pasted document - every character costs tokens, latency and trial quota.
DICTIONARY_CONTEXT_MAX_CHARS = 600

# A sentence ends after CJK or Latin terminal punctuation, or at a line break.
# A Latin full stop only ends one when whitespace follows, so "3.5" survives.
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[。！？!?])|(?<=\.)\s+|\n+')

# Stripped before checking whether a context says anything beyond the headword.
_EDGE_PUNCTUATION = ' \t\u3000。、，,.!?！？「」『』()（）"\''


def language_key(name: Optional[str]) -> str:
    """Letters only, lowercase: 'Chinese (Simplified)' and 'Chinese Simplified'
    are the same language spelled two ways (nlp_manager vs. the hotkey list)."""
    return re.sub(r'[^a-z]', '', (name or '').lower())


def dictionary_source_language(language: Optional[str],
                               user_chosen: bool = False) -> Optional[str]:
    """The source language to state in the prompt, or None to let the model decide.

    A Dictionary window always has a language, but it is not always evidence.
    `nlp_manager.detect_language()` only *proves* Japanese - it needs kana to say
    it. Its other answers are guesses: every kanji-only text without kana comes
    back "Chinese (Simplified)" (勉強 included), and any Latin-script text comes
    back as the first installed European pack. Stating a guess to the model as a
    fact would make it follow the guess, which is worse than asking it to
    decide. A language the user picked in the selection dialog is a fact.

    Args:
        language: The Dictionary window's language (nlp_manager's spelling).
        user_chosen: True when the user picked it in the selection dialog.
    """
    if not language or language == 'Unknown':
        return None
    if user_chosen:
        return language
    return language if language_key(language) == 'japanese' else None


def _split_sentences(text: str) -> List[str]:
    return [part.strip() for part in _SENTENCE_SPLIT_RE.split(text)
            if part and part.strip()]


def _window_around(sentence: str, needles: Sequence[str], max_chars: int) -> str:
    """`max_chars` of an over-long sentence, centred on the first headword in it."""
    folded = sentence.lower()
    hits = [(folded.find(n), n) for n in needles if folded.find(n) >= 0]
    pos, needle = min(hits) if hits else (0, '')
    start = max(0, pos - max(0, max_chars - len(needle)) // 2)
    start = max(0, min(start, len(sentence) - max_chars))
    return sentence[start:start + max_chars]


def extract_context(text: Optional[str], words: Sequence[str],
                    max_chars: int = DICTIONARY_CONTEXT_MAX_CHARS) -> str:
    """The sentences of `text` that contain a headword, for the prompt's context.

    Only those sentences are sent: the rest of a long selection costs tokens
    without helping. They are de-duplicated, kept in text order and cut to
    `max_chars` (a single over-long sentence is cut around its first headword, so
    the headword is never what gets cut off). Matching ignores case.

    A phrase that does not occur in the text - one the user typed into a custom
    box - finds no sentence, and a context that is nothing but the headword
    itself (the user selected just 勉強) is dropped as saying nothing new.

    Returns:
        The context, sentences joined by newlines, or "" for none.
    """
    if not text or not words or max_chars <= 0:
        return ""
    needles = [w.strip().lower() for w in words if w and w.strip()]
    if not needles:
        return ""

    picked: List[str] = []
    for sentence in _split_sentences(text):
        if sentence not in picked and any(n in sentence.lower() for n in needles):
            picked.append(sentence)
    if not picked:
        return ""
    if all(s.strip(_EDGE_PUNCTUATION).lower() in needles for s in picked):
        return ""

    context = ""
    for sentence in picked:
        candidate = f"{context}\n{sentence}" if context else sentence
        if len(candidate) > max_chars:
            if not context:
                context = _window_around(sentence, needles, max_chars)
            break
        context = candidate
    return context


def _pronunciation_rule(source: Optional[str], target: str) -> Tuple[str, str]:
    """(short form for the field line, full rule for the CRITICAL list).

    Japanese gets its reading in hiragana and nothing else (user's choice,
    2026-10-15: no romaji). Field 5 is never annotated by the result window, so
    this is where a learner reads the word.
    """
    key = language_key(source)
    if key == 'japanese':
        return ("reading in hiragana",
                "the reading in hiragana only, long vowels written out as the word has them "
                "(勉強 → べんきょう, 東京 → とうきょう); a word written in katakana keeps its "
                "katakana (コーヒー). No romaji, no IPA.")
    if key.startswith('chinese'):
        return ("pinyin", "pinyin with tone marks (学习 → xuéxí).")
    if key == 'korean':
        return ("romanization", "Revised Romanization (사랑 → sarang).")
    if not key:
        return ("as the headword's language needs",
                "for a Japanese headword, its reading in hiragana only (no romaji); for a "
                "Chinese one, pinyin with tone marks; for a Korean one, Revised Romanization; "
                f"otherwise /IPA/ plus a phonetic spelling in {target}.")
    return (f"/IPA/, phonetic spelling in {target}",
            f"/IPA/ plus a phonetic spelling in {target} "
            "(hello → /həˈloʊ/, /ハロー/ when the target is Japanese).")


def _script_clause(source: str) -> str:
    """Rule 1's warning against judging a CJK headword by its script."""
    key = language_key(source)
    if key == 'japanese':
        return (" A headword written only in kanji is still Japanese: never treat it as "
                "Chinese because of its script. The same characters can mean something else "
                "in Chinese - Japanese 手紙 means \"letter\", not the Chinese \"toilet paper\".")
    if key.startswith('chinese'):
        return (" A headword written only in hanzi is still Chinese: never treat it as "
                "Japanese because of its script, even where the same characters mean "
                "something else in Japanese.")
    return ""


def build_dictionary_prompt(words: Sequence[str], target_language: str,
                            source_language: Optional[str] = None,
                            context: Optional[str] = None) -> str:
    """The full dictionary prompt for one or more headwords.

    The eight numbered labels are fixed: `_align_dictionary_text()` aligns on them
    and `dictionary_render` reads fields by number and label (Translation and
    Definition as target-language text, Pronunciation never annotated, Source
    Language as the hint for everything else).

    Args:
        words: Headwords, in display order.
        target_language: Language of the translation and the explanations.
        source_language: The headwords' language when the caller knows it; None
            asks the model to decide per headword and name it in field 2.
        context: Text to show the model as the headwords' context - already
            trimmed by `extract_context()`; empty or None leaves the block out.
    """
    source = (source_language or '').strip() or None
    target = target_language
    monolingual = source is not None and language_key(source) == language_key(target)
    pron_short, pron_rule = _pronunciation_rule(source, target)
    headwords = "\n".join(f"{i + 1}. {word}" for i, word in enumerate(words))

    parts = ["You are a professional dictionary.", ""]
    if source:
        parts.append(f"Source language: {source}")
    else:
        parts.append("Source language: not given - decide it for each headword "
                     "(see LANGUAGE RULES)")
    parts += [f"Target language: {target}", ""]

    if context and context.strip():
        purpose = "sense" if source else "language and sense"
        parts += [
            f"The headwords were selected from the text below. Use it only to choose each "
            f"headword's {purpose}; do not translate it.",
            "===CONTEXT===",
            context.strip(),
            "===END OF CONTEXT===",
            "",
        ]

    parts.append(f"HEADWORDS (look up each one as a {source} word):" if source else "HEADWORDS:")
    parts += [headwords, "", "LANGUAGE RULES (most important - follow them exactly):"]

    if source is None:
        parts += [
            "1. The source language is not given. Decide it for each headword from the "
            "headword itself and the context, if any.",
            "2. A headword written only in kanji/hanzi can be Japanese or Chinese, and the "
            "meaning can differ (Japanese 手紙 means \"letter\", Chinese \"toilet paper\"). It "
            "is Japanese when the context is Japanese (it contains hiragana or katakana) and "
            "Chinese when the context is Chinese. Without such context, decide from the "
            "headword itself.",
            "3. Write the language you decided in field 2 - one language, never two - and "
            "give the meaning it has in that language.",
            f"4. Translation, Definition and Word Type are written in {target}, and so is "
            "everything after \"→\".",
            "5. Synonyms, Antonyms and each example sentence before \"→\" are written in the "
            "headword's language.",
        ]
    elif monolingual:
        parts += [
            f"1. Every headword is {source}.{_script_clause(source)}",
            f"2. This is a monolingual {source} dictionary: write every field in {source}.",
            f"3. Field 1 is a simpler {source} word or phrase with the same meaning; field 3 "
            f"explains the headword in {source}.",
            f"4. Synonyms and Antonyms are {source} words, comma-separated, without \"→\".",
            f"5. Each example is a {source} sentence → the same sentence said more simply in "
            f"{source}.",
        ]
    else:
        parts += [
            f"1. Every headword is {source}.{_script_clause(source)} Give its {source} meaning.",
            f"2. Only exception: a headword that is clearly not {source} - for example a word "
            "in another script that the user typed. Identify its real language and write "
            "that in field 2.",
            f"3. Field 2 is exactly \"{source}\" unless rule 2 applies.",
            f"4. Translation, Definition and Word Type are written in {target}, and so is "
            "everything after \"→\".",
            f"5. Synonyms, Antonyms and each example sentence before \"→\" are written in "
            f"{source}.",
        ]

    field2 = source if source else "the language you decided"
    if monolingual:
        translation = f"a simpler {source} equivalent (REQUIRED)"
        definition = f"explanation in {source} (REQUIRED)"
        word_type = f"noun/verb/adjective/adverb/etc., in {source}"
        synonyms = "synonym, synonym, ... (write \"None\" if there are none)"
        antonyms = "antonym, antonym, ... (write \"None\" if there are none)"
        example = f"{source} sentence → simpler {source} paraphrase"
    else:
        translation = f"{target} translation (REQUIRED)"
        definition = f"explanation in {target} (REQUIRED)"
        word_type = f"noun/verb/adjective/adverb/etc., in {target}"
        synonyms = (f"synonym → {target} translation, synonym → {target} translation "
                    "(write \"None\" if there are none)")
        antonyms = (f"antonym → {target} translation, antonym → {target} translation "
                    "(write \"None\" if there are none)")
        example = f"{source or 'Source-language'} sentence → {target} translation"

    parts += [
        "",
        "OUTPUT FORMAT - one entry per headword, in the order given:",
        "",
        "## [headword exactly as given]",
        "",
        f"1. **Translation**: {translation}",
        f"2. **Source Language**: {field2}",
        f"3. **Definition**: {definition}",
        f"4. **Word Type**: {word_type}",
        f"5. **Pronunciation**: {pron_short}",
        f"6. **Synonyms**: {synonyms}",
        f"7. **Antonyms**: {antonyms}",
        "8. **Examples**:",
        f"   - {example}",
        f"   - {example}",
        "",
        "---",
        "",
        "CRITICAL:",
        "- Start every entry with the \"## [headword]\" line exactly as shown - it is used to "
        "highlight the word.",
        "- Fill in every field; never leave a field blank after the colon.",
        f"- Provide an entry for all {len(words)} headword(s), in the order given.",
        f"- Pronunciation: {pron_rule}",
    ]
    return "\n".join(parts)
