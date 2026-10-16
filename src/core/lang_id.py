"""Which language a piece of CJK text is - from evidence, never from a guess.

Text written only in kanji cannot always be told from Chinese: 勉強, 手紙 and
東京大学 are valid Chinese strings too, and `nlp_manager.detect_language()` calls
every kanji-only text "Chinese (Simplified)". This module answers the question
in a fixed order (Decision 22) and says where its answer came from:

1. known    - the caller is authoritative (a translation's target language for
              its own output; a language the user picked in a dialog);
2. evidence in the text - kana proves Japanese; a kanji only Japanese writes
              (a shinjitai such as 経, 気, 読) proves Japanese; a
              hanzi Japanese cannot write (a simplified form such as 们, 这)
              proves Chinese; so do two Chinese function words in one
              punctuated sentence (這是我的書。, K6 - see grammar_evidence);
3. evidence in the context - the larger text the fragment came from, same rules;
4. model    - the language an AI model call reported for this exact text;
5. none     - unknown. A surface that needs a language asks the user; a passive
              one stays plain ("blank beats a wrong reading", Decision 8).

Evidence beats the model: kana in the text wins over a model that said Chinese.

Glyph sets (measured 2026-10-15, TODO.md F9 and J2):
- "Japanese-only" = in CP932 but in neither GB2312 nor Big5-HKSCS (571 code
  points). Not plain Big5: Hong Kong's standard forms 衆 裏 綫 衞 啓 峯 are
  outside Big5 but inside CP932, and Big5 called 12 of 13 Hong Kong strings
  (這裏, 公衆, 路綫 ...) Japanese. HKSCS also holds Japanese forms such as
  駅 発 円 県, so 22 of 311 Japanese test words lose their glyph evidence -
  the safe direction: they stay unknown, they are never called Chinese.
- "cannot be Japanese" = not in JIS X 0213 (`euc_jis_2004`). Not CP932: the
  2010 Jōyō kanji 剝 頰 塡 are outside CP932 but are Japanese, and in Big5.
- Simplified = in GB2312. Not GBK - GBK holds almost every ideograph,
  Traditional included.
Traditional Chinese is mostly ambiguous by glyph: its forms are largely the
kyūjitai JIS also carries.

Pure logic: no Tk, no config, no API. Must not import `furigana` - furigana
builds on this module.
"""
import codecs
import logging
import re
from functools import lru_cache
from typing import Dict, NamedTuple, Optional

JAPANESE = "Japanese"
CHINESE_SIMPLIFIED = "Chinese (Simplified)"     # nlp_manager's spelling is canonical
CHINESE_TRADITIONAL = "Chinese (Traditional)"
CHINESE = (CHINESE_SIMPLIFIED, CHINESE_TRADITIONAL)

# Kanji / hanzi: CJK Unified Ideographs + Extension A (the ranges furigana uses).
HAN_RE = re.compile(r'[\u4E00-\u9FFF\u3400-\u4DBF]')

# Kana that only Japanese writes: hiragana, katakana with the long-vowel mark ー,
# small katakana for Ainu, half-width katakana, and the marks 々 〆 (ヶ is
# katakana). Not U+30FB "・": Chinese text uses it as the dot in foreign names
# (列夫・托尔斯泰), so it proves nothing.
KANA_EVIDENCE_RE = re.compile(
    r'[\u3041-\u3096\u309D-\u309F\u30A1-\u30FA\u30FC-\u30FF'
    r'\u31F0-\u31FF\uFF66-\uFF9D\u3005\u3006]')

# A model verdict that names no language.
_NO_LANGUAGE = {'', 'unknown', 'none', 'n/a', 'na', 'undetermined', 'unsure', '?'}


class Verdict(NamedTuple):
    """A resolved language and the evidence it rests on.

    Attributes:
        language: Canonical name (JAPANESE, CHINESE_SIMPLIFIED, ... or another
            language's name), or None when unknown.
        evidence: 'known' | 'kana' | 'jp-glyph' | 'zh-glyph' | 'context' |
            'model' | 'none'.
    """
    language: Optional[str]
    evidence: str


# --------------------------------------------------------------------------- #
# Names
# --------------------------------------------------------------------------- #
_CJK_ALIASES = {
    'japanese': JAPANESE, 'ja': JAPANESE, 'jp': JAPANESE, 'ja-jp': JAPANESE, 'jpn': JAPANESE,
    'nihongo': JAPANESE, '日本語': JAPANESE, 'にほんご': JAPANESE,
    'chinese': CHINESE_SIMPLIFIED, 'chinese simplified': CHINESE_SIMPLIFIED,
    'chinese (simplified)': CHINESE_SIMPLIFIED, 'simplified chinese': CHINESE_SIMPLIFIED,
    'chinese, simplified': CHINESE_SIMPLIFIED, 'mandarin': CHINESE_SIMPLIFIED,
    'mandarin chinese': CHINESE_SIMPLIFIED, 'zh': CHINESE_SIMPLIFIED,
    'zh-cn': CHINESE_SIMPLIFIED, 'zh-hans': CHINESE_SIMPLIFIED, 'zh-sg': CHINESE_SIMPLIFIED,
    'zho': CHINESE_SIMPLIFIED, 'chi': CHINESE_SIMPLIFIED,
    '中文': CHINESE_SIMPLIFIED, '汉语': CHINESE_SIMPLIFIED, '中文简体': CHINESE_SIMPLIFIED,
    '简体中文': CHINESE_SIMPLIFIED, '中国語': CHINESE_SIMPLIFIED,
    'chinese traditional': CHINESE_TRADITIONAL, 'chinese (traditional)': CHINESE_TRADITIONAL,
    'traditional chinese': CHINESE_TRADITIONAL, 'chinese, traditional': CHINESE_TRADITIONAL,
    'zh-tw': CHINESE_TRADITIONAL, 'zh-hk': CHINESE_TRADITIONAL, 'zh-mo': CHINESE_TRADITIONAL,
    'zh-hant': CHINESE_TRADITIONAL, '中文繁體': CHINESE_TRADITIONAL, '繁體中文': CHINESE_TRADITIONAL,
    '繁体中文': CHINESE_TRADITIONAL,
}


@lru_cache(maxsize=1)
def _language_names() -> Dict[str, str]:
    """English name, code and native name of every app language -> its English name."""
    try:
        from src.constants import LANGUAGES
    except Exception:                      # names still normalize without the table
        return {}
    names: Dict[str, str] = {}
    for name, code, native in LANGUAGES:
        for alias in (name, code, native):
            names.setdefault(_fold(alias), name)
    return names


def _fold(name: str) -> str:
    return ' '.join(str(name).strip().lower().replace('_', '-').split())


def normalize_language(name: Optional[str]) -> Optional[str]:
    """The canonical name of a language, or None when it names none.

    Japanese and both Chinese variants in every spelling the app meets (the
    hotkey list's "Chinese Simplified", nlp_manager's "Chinese (Simplified)",
    codes, native names, what a model writes) map to JAPANESE /
    CHINESE_SIMPLIFIED / CHINESE_TRADITIONAL; a bare "Chinese" is Simplified.
    Other app languages map to their English name ('vi' -> 'Vietnamese'); any
    other non-empty name is returned stripped. "Unknown" and the like -> None.
    """
    if name is None:
        return None
    folded = _fold(name).strip(' .:;[]"\'')
    if folded.startswith('(') and folded.endswith(')'):
        folded = folded[1:-1].strip()
    if folded in _NO_LANGUAGE:
        return None
    if folded in _CJK_ALIASES:
        return _CJK_ALIASES[folded]
    known = _language_names().get(folded)
    if known in ('Chinese Simplified', 'Chinese Traditional'):
        return CHINESE_SIMPLIFIED if known.endswith('Simplified') else CHINESE_TRADITIONAL
    return known or str(name).strip()


def is_japanese(language: Optional[str]) -> bool:
    return normalize_language(language) == JAPANESE


def is_chinese(language: Optional[str]) -> bool:
    return normalize_language(language) in CHINESE


# --------------------------------------------------------------------------- #
# Evidence in the text
# --------------------------------------------------------------------------- #
# The character sets the glyph evidence is read from.
GLYPH_CODECS = ('euc_jis_2004', 'cp932', 'gb2312', 'big5hkscs')


def _encodes(ch: str, codec: str) -> bool:
    try:
        ch.encode(codec)
        return True
    except UnicodeEncodeError:
        return False


@lru_cache(maxsize=1)
def glyph_evidence_available() -> bool:
    """Whether this build has every codec the glyph sets come from.

    Without one, every glyph would be misread (no JIS X 0213 = "nothing is
    Japanese"), so glyph evidence switches off instead - kana still counts.
    """
    missing = []
    for codec in GLYPH_CODECS:
        try:
            codecs.lookup(codec)
        except LookupError:
            missing.append(codec)
    if missing:
        logging.warning(f"[LangID] glyph evidence disabled, missing codecs: {', '.join(missing)}")
        return False
    return True


@lru_cache(maxsize=None)
def glyph_class(ch: str) -> Optional[str]:
    """What one kanji proves: 'jp', 'zh-s' (simplified), 'zh-t', or None.

    'jp' - Japanese writes it (CP932) and no Chinese standard set has it
    (GB2312, Big5-HKSCS - which includes Big5).
    'zh-s' / 'zh-t' - Japanese cannot write it (outside JIS X 0213); simplified
    when GB2312 has it. Cached per character: the codec probes are the cost.
    """
    if not glyph_evidence_available():
        return None
    if not _encodes(ch, 'euc_jis_2004'):
        return 'zh-s' if _encodes(ch, 'gb2312') else 'zh-t'
    if (_encodes(ch, 'cp932') and not _encodes(ch, 'gb2312')
            and not _encodes(ch, 'big5hkscs')):
        return 'jp'
    return None


def has_kana(text: Optional[str]) -> bool:
    """Whether the text holds kana that only Japanese writes (not "・")."""
    return bool(text) and bool(KANA_EVIDENCE_RE.search(text))


def has_chinese_glyph(text: Optional[str]) -> bool:
    """Whether any kanji in the text is one Japanese cannot write."""
    if not text:
        return False
    return any(glyph_class(ch) in ('zh-s', 'zh-t') for ch in set(HAN_RE.findall(text)))


def han_evidence(text: Optional[str]) -> Optional[str]:
    """What the kanji alone prove: JAPANESE, a Chinese variant, or None.

    None when no kanji proves anything, and when they contradict each other (a
    Japanese-only glyph beside one Japanese cannot write). Between the Chinese
    variants the majority of the proving glyphs decides; a tie is Simplified.
    """
    if not text:
        return None
    jp = zh_s = zh_t = 0
    for ch in set(HAN_RE.findall(text)):
        kind = glyph_class(ch)
        if kind == 'jp':
            jp += 1
        elif kind == 'zh-s':
            zh_s += 1
        elif kind == 'zh-t':
            zh_t += 1
    if jp and (zh_s or zh_t):
        return None
    if jp:
        return JAPANESE
    if zh_s or zh_t:
        return CHINESE_TRADITIONAL if zh_t > zh_s else CHINESE_SIMPLIFIED
    return None


# Chinese function words Japanese does not write: two distinct ones in a
# punctuated sentence prove Chinese where the glyphs prove nothing - 這是我的書。
# holds no simplified form and no Japanese-only one. Measured 2026-10-16 on
# Tatoeba's Japanese and Chinese sentences, and on the 177 555 all-kanji words of
# pykakasi's dictionary as terms, as one-word sentences and as lists: no Japanese
# text called Chinese; 17% of the Chinese sentences the glyphs leave open settled.
# 的, 了 and 我 stay out on purpose: Japanese writes them in compounds (目的, 終了,
# 我慢), and with them two such compounds in one sentence came back Chinese 31% of
# the time.
CHINESE_FUNCTION_CHARS = frozenset('是很們這嗎呢吧麼你她它')
SENTENCE_PUNCTUATION_RE = re.compile(r'[。！？，；：.!?,;:]')


@lru_cache(maxsize=None)
def _chinese_script(ch: str) -> Optional[str]:
    """'zh-t' for a hanzi only Traditional sets hold (Big5-HKSCS, not GB2312),
    'zh-s' for one only GB2312 holds, else None."""
    big5, gb = _encodes(ch, 'big5hkscs'), _encodes(ch, 'gb2312')
    if big5 and not gb:
        return 'zh-t'
    if gb and not big5:
        return 'zh-s'
    return None


def grammar_evidence(text: Optional[str]) -> Optional[str]:
    """A Chinese variant when `text` is a punctuated sentence holding two distinct
    CHINESE_FUNCTION_CHARS and no kanji only Japanese writes; else None.

    The variant is the side more of its hanzi belong to (Big5-HKSCS without
    GB2312 is Traditional); a tie is Simplified, as in han_evidence(). Needs the
    same codecs as the glyph evidence, and is off without them.
    """
    if not text or not SENTENCE_PUNCTUATION_RE.search(text):
        return None
    if len(set(text) & CHINESE_FUNCTION_CHARS) < 2:
        return None
    if not glyph_evidence_available():
        return None
    han = set(HAN_RE.findall(text))
    if any(glyph_class(ch) == 'jp' for ch in han):
        return None
    scripts = [_chinese_script(ch) for ch in han]
    if scripts.count('zh-t') > scripts.count('zh-s'):
        return CHINESE_TRADITIONAL
    return CHINESE_SIMPLIFIED


def text_evidence(text: Optional[str]) -> Optional[Verdict]:
    """A verdict from the text itself, or None when it proves nothing."""
    if has_kana(text):
        return Verdict(JAPANESE, 'kana')
    language = han_evidence(text)
    if language == JAPANESE:
        return Verdict(JAPANESE, 'jp-glyph')
    if language:
        return Verdict(language, 'zh-glyph')
    language = grammar_evidence(text)
    if language:
        return Verdict(language, 'zh-grammar')
    return None


# --------------------------------------------------------------------------- #
# The resolver
# --------------------------------------------------------------------------- #
def resolve(text: Optional[str], *, known: Optional[str] = None,
            context: Optional[str] = None, model: Optional[str] = None) -> Verdict:
    """The language of `text`: known -> text evidence -> context evidence -> model.

    Args:
        text: The text to identify.
        known: A language the caller is authoritative about; wins outright.
        context: The larger text `text` was taken from, if any.
        model: The language a model call reported for exactly this text, if any.
            "Unknown" counts as no verdict.

    Returns:
        Verdict(language or None, evidence).
    """
    language = normalize_language(known)
    if language:
        return Verdict(language, 'known')

    verdict = text_evidence(text)
    if verdict:
        return verdict

    if context and context != text:
        from_context = text_evidence(context)
        if from_context:
            logging.debug(f"[LangID] evidence=context language={from_context.language} "
                          f"via={from_context.evidence} chars={len(text or '')}")
            return Verdict(from_context.language, 'context')

    language = normalize_language(model)
    if language:
        logging.debug(f"[LangID] evidence=model language={language} chars={len(text or '')}")
        return Verdict(language, 'model')

    return Verdict(None, 'none')


# --------------------------------------------------------------------------- #
# Hints for the ruby surfaces
# --------------------------------------------------------------------------- #
def ruby_hint(*languages: Optional[str]) -> Optional[str]:
    """JAPANESE when a text written in these languages can only be Japanese
    where it uses kanji - Japanese is among them and no Chinese variant is.

    The prompts restrict a result to its source and target language, so for a
    Japanese <-> English pair every kanji run in it is Japanese. A pair with
    Chinese on either side needs per-part hints instead, so it gets None here.
    """
    names = [normalize_language(language) for language in languages]
    if JAPANESE in names and not any(name in CHINESE for name in names):
        return JAPANESE
    return None


def output_hint(source: Optional[str], target: Optional[str]) -> Optional[str]:
    """The hint for a translation's output: its target when that is Japanese,
    otherwise the language-set rule over source and target."""
    if normalize_language(target) == JAPANESE:
        return JAPANESE
    return ruby_hint(source, target)
