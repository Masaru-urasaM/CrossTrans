"""
Tests for the furigana engine (src/core/furigana.py).

Covers the detection gate, the reading aligner, invariant I1, the legacy notation
escaping, whitespace preservation and the provider chain. Pure logic only - no
Tkinter, no API calls.
"""
import pytest

from src.core import furigana as F


FUGASHI_ONLY = pytest.mark.skipif(
    not F._FUGASHI.is_available(),
    reason="requires the Japanese NLP pack (fugashi + unidic)"
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Annotation is memoized; keep tests independent."""
    F.clear_cache()
    yield
    F.clear_cache()


def notation(text, lang_hint="Japanese"):
    """Annotate and serialize, for compact assertions."""
    return F.to_notation(F.annotate(text, lang_hint))


# --------------------------------------------------------------------------- #
# Detection gate
# --------------------------------------------------------------------------- #
class TestShouldAnnotate:
    def test_japanese_with_kana(self):
        assert F.should_annotate("今日は雨が降る") is True

    def test_kanji_only_needs_a_hint(self):
        # nlp_manager.detect_language() reports Chinese for kanji-only strings,
        # so a caller that knows the language must say so.
        assert F.should_annotate("電源設定") is False
        assert F.should_annotate("電源設定", "Japanese") is True

    def test_chinese_is_not_annotated(self):
        assert F.should_annotate("你好世界") is False

    def test_kana_only_has_nothing_to_annotate(self):
        assert F.should_annotate("こんにちは") is False

    def test_latin_and_empty(self):
        assert F.should_annotate("hello world") is False
        assert F.should_annotate("") is False
        assert F.should_annotate("123") is False

    def test_is_japanese_stays_permissive(self):
        # Preserves the old _is_japanese_text() behaviour, which also matched hanzi.
        assert F.is_japanese("你好世界") is True
        assert F.is_japanese("こんにちは") is True
        assert F.is_japanese("hello") is False


# --------------------------------------------------------------------------- #
# Aligner
# --------------------------------------------------------------------------- #
class TestAlign:
    def test_interleaved_okurigana_is_split(self):
        # The old implementation stripped only a TRAILING kana suffix and produced
        # {取り消|とりけ}し, with the ruby wrongly covering the り.
        assert F.align("取り消し", "とりけし") == (
            F.RubySegment("取", "と"),
            F.RubySegment("り", None),
            F.RubySegment("消", "け"),
            F.RubySegment("し", None),
        )

    def test_all_kanji_takes_whole_reading(self):
        assert F.align("東京", "とうきょう") == (F.RubySegment("東京", "とうきょう"),)

    def test_leading_kana_is_kept_plain(self):
        assert F.align("お疲れ", "おつかれ") == (
            F.RubySegment("お", None),
            F.RubySegment("疲", "つか"),
            F.RubySegment("れ", None),
        )

    def test_katakana_reading_is_normalized_to_hiragana(self):
        assert F.align("東京", "トウキョウ") == (F.RubySegment("東京", "とうきょう"),)

    def test_token_without_kanji_is_plain(self):
        assert F.align("です", "です") == (F.RubySegment("です", None),)

    def test_missing_reading_fails_safe(self):
        assert F.align("東京", None) is None

    def test_unmatchable_kana_fails_safe(self):
        # The り in the surface does not appear where the reading requires it.
        assert F.align("取り消し", "まったくちがう") is None

    def test_leftover_reading_fails_safe(self):
        # Reading is longer than the surface can account for.
        assert F.align("消し", "けしすぎ") is None

    def test_empty_surface(self):
        assert F.align("", "とう") == ()

    def test_bases_always_rebuild_the_surface(self):
        for surface, reading in [("取り消し", "とりけし"), ("お疲れ様", "おつかれさま"),
                                 ("東京", "とうきょう"), ("生き物", "いきもの")]:
            segments = F.align(surface, reading)
            assert segments is not None
            assert "".join(s.base for s in segments) == surface


# --------------------------------------------------------------------------- #
# Invariant I1 - annotation never alters the text it describes
# --------------------------------------------------------------------------- #
I1_CORPUS = [
    "日本語を勉強しています",
    "今日は雨が降るでしょう",
    "彼は東京に行った",
    "お疲れ様です",
    "コンピューター",
    "1月2日",
    "Hello world 123",
    "設定{A|B}テスト",
    "日本|語",
    "バック\\スラッシュ",
    "今日は雨\n明日は晴れ",
    "今日は雨\n\n明日は晴れ\n",
    "  今日は雨  ",
    "今日は雨\r\n明日",
    "タブ\t区切り",
    "Hello 世界 です",
    "",
    " ",
    "。",
]


@pytest.mark.parametrize("text", I1_CORPUS)
def test_invariant_i1_holds(text):
    segments = F.annotate(text, "Japanese")
    assert "".join(s.base for s in segments) == text


@pytest.mark.parametrize("text", I1_CORPUS)
def test_notation_round_trips(text):
    segments = F.annotate(text, "Japanese")
    parsed = F.parse_notation(F.to_notation(segments))
    assert "".join(s.base for s in parsed) == text


class TestWhitespace:
    def test_newlines_survive(self):
        # Tokenizers normalize whitespace away; annotating around it is what keeps
        # a multi-line translation intact.
        segments = F.annotate("今日は雨\n明日は晴れ", "Japanese")
        assert "".join(s.base for s in segments) == "今日は雨\n明日は晴れ"
        assert any(s.ruby for s in segments)

    def test_multiline_still_gets_ruby_on_every_line(self):
        text = "今日は雨\n明日は晴れ"
        bases_with_ruby = [s.base for s in F.annotate(text, "Japanese") if s.ruby]
        assert "今日" in bases_with_ruby
        assert "明日" in bases_with_ruby


# --------------------------------------------------------------------------- #
# Legacy {kanji|reading} notation
# --------------------------------------------------------------------------- #
class TestNotation:
    def test_literal_delimiters_are_escaped(self):
        segments = (F.RubySegment("設定", "せってい"), F.RubySegment("{A|B}", None))
        assert F.to_notation(segments) == r"{設定|せってい}\{A\|B\}"

    def test_escaped_delimiters_parse_back_as_text(self):
        # The injection bug: an unescaped literal "{A|B}" used to be parsed as a
        # ruby pair and rendered as "A" with the reading "B".
        parsed = F.parse_notation(r"{設定|せってい}\{A\|B\}")
        assert parsed == (F.RubySegment("設定", "せってい"), F.RubySegment("{A|B}", None))

    def test_backslash_round_trips(self):
        segments = (F.RubySegment("a\\b", None),)
        assert F.parse_notation(F.to_notation(segments)) == segments

    def test_real_pair_parses(self):
        assert F.parse_notation("{漢字|かんじ}") == (F.RubySegment("漢字", "かんじ"),)

    def test_malformed_brace_is_literal_text(self):
        assert F.parse_notation("{unterminated") == (F.RubySegment("{unterminated", None),)
        assert F.parse_notation("{no-pipe}") == (F.RubySegment("{no-pipe}", None),)

    def test_adjacent_plain_runs_are_merged(self):
        parsed = F.parse_notation("abc{漢|か}def")
        assert parsed == (F.RubySegment("abc", None), F.RubySegment("漢", "か"),
                          F.RubySegment("def", None))

    def test_generate_notation_returns_none_without_ruby(self):
        assert F.generate_notation("hello world") is None
        assert F.generate_notation("こんにちは") is None
        assert F.generate_notation("") is None

    def test_generate_notation_returns_a_string_with_ruby(self):
        result = F.generate_notation("今日は雨", "Japanese")
        assert result is not None
        assert "|" in result

    def test_generate_notation_escapes_delimiters_in_the_source(self):
        # RubyText parses the notation with parse_notation(), which honors the
        # escapes, so text holding a delimiter still gets its readings and the
        # delimiter round-trips as literal text rather than a fake ruby pair.
        for source in ("設定{A|B}テスト", "日本|語", "設定\\パス"):
            result = F.generate_notation(source, "Japanese")
            assert result is not None, source
            assert F.to_notation(F.parse_notation(result)) == result
            rebuilt = ''.join(seg.base for seg in F.parse_notation(result))
            assert rebuilt == source
        assert F.generate_notation("設定を保存", "Japanese") is not None


# --------------------------------------------------------------------------- #
# Kana helpers
# --------------------------------------------------------------------------- #
class TestKanaHelpers:
    def test_katakana_becomes_hiragana(self):
        assert F._kata_to_hira("キョウ") == "きょう"

    def test_non_katakana_is_untouched(self):
        assert F._kata_to_hira("abc123あ。ー") == "abc123あ。ー"

    def test_split_runs(self):
        assert F._split_runs("取り消し") == [
            (True, "取"), (False, "り"), (True, "消"), (False, "し")
        ]
        assert F._split_runs("東京都") == [(True, "東京都")]


# --------------------------------------------------------------------------- #
# Safety / limits
# --------------------------------------------------------------------------- #
class TestSafety:
    def test_annotate_never_raises(self):
        for text in ["", " ", "\n", "\x00", "🎉", "a" * 5000, "。" * 100]:
            segments = F.annotate(text)
            assert "".join(s.base for s in segments) == text

    def test_plain_text_is_a_single_segment(self):
        assert F.annotate("hello world") == (F.RubySegment("hello world", None),)

    def test_pair_cap_falls_back_to_plain(self, monkeypatch):
        monkeypatch.setattr(F, "MAX_RUBY_PAIRS", 2)
        F.clear_cache()
        text = "猫が犬が鳥が魚が"
        segments = F.annotate(text, "Japanese")
        assert segments == (F.RubySegment(text, None),)

    def test_provider_chain_reports_a_name(self):
        # pykakasi is bundled, so at least one provider must always be available.
        assert F.is_available() is True
        assert F.active_provider_name() in ("fugashi", "pykakasi")

    def test_prewarm_is_safe_to_call(self):
        F.prewarm()
        F.prewarm()


# --------------------------------------------------------------------------- #
# Reading quality - the cases that justified the provider chain
# --------------------------------------------------------------------------- #
@FUGASHI_ONLY
class TestReadingQuality:
    def test_homograph_uses_context(self):
        # A transliteration dictionary matches greedily and returns こんにち here.
        assert notation("今日は雨が降る") == "{今日|きょう}は{雨|あめ}が{降|ふ}る"

    def test_okurigana_is_not_covered_by_ruby(self):
        assert notation("取り消し") == "{取|と}り{消|け}し"
        assert notation("話し合い") == "{話|はな}し{合|あ}い"
        assert notation("生き物") == "{生|い}き{物|もの}"

    def test_kanji_compound_keeps_its_compound_reading(self):
        # UniDic tags 日本 as a proper noun reading ニッポン, so splitting the
        # compound would give the wrong にっぽんご / にっぽんにん.
        assert notation("日本語") == "{日本語|にほんご}"
        assert notation("日本人") == "{日本人|にほんじん}"
        assert notation("東京駅") == "{東京駅|とうきょうえき}"

    def test_compound_rule_does_not_swallow_a_greeting_entry(self):
        # "今日は" is a dictionary entry for こんにちは; restricting the compound
        # rule to all-kanji spans is what keeps 今日 -> きょう here.
        assert notation("今日は雨") == "{今日|きょう}は{雨|あめ}"

    def test_counter_after_a_digit_is_suppressed(self):
        # "2日" is futsuka: the digit carries part of the reading and cannot take
        # ruby, so drawing カ over 日 alone would invite the misreading "ni-ka".
        assert notation("1月2日") == "1月2日"
        assert notation("2人で行く") == "2人で{行|い}く"

    def test_katakana_gets_no_ruby(self):
        assert notation("コンピューター") == "コンピューター"


class TestPipelineGate:
    """Locks in the documented consequence of the kana-evidence rule.

    The translation pipeline calls generate_furigana() with no language hint, so
    kanji-only text is deliberately left unannotated: the gate cannot tell
    Japanese kanji from Chinese hanzi, and a wrong reading is worse than none.
    Phase 2 threads a real hint from the surfaces that know the language.
    """

    def test_sentence_with_kana_is_annotated_without_a_hint(self):
        assert F.generate_notation("今日は雨が降る") is not None

    def test_kanji_only_needs_a_hint(self):
        assert F.generate_notation("電源設定") is None
        assert F.generate_notation("電源設定", "Japanese") is not None

    def test_chinese_is_never_annotated_without_a_hint(self):
        # Previously produced "{你|}{世界|せかい}" - note the empty reading.
        assert F.generate_notation("你好世界") is None
        assert F.generate_notation("我是中国人") is None

    def test_no_segment_ever_carries_an_empty_reading(self):
        for text in ["你好世界", "今日は雨", "電源設定", "日本語を勉強しています"]:
            for segment in F.annotate(text, "Japanese"):
                assert segment.ruby is None or segment.ruby != ""


class TestKakasiFallback:
    def test_kakasi_alone_still_splits_okurigana(self, monkeypatch):
        # With the morphological provider unavailable, the aligner must still fix
        # the okurigana span that the old implementation got wrong.
        monkeypatch.setattr(F._FUGASHI, "_unavailable", True)
        monkeypatch.setattr(F._FUGASHI, "_tagger", None)
        F.clear_cache()
        assert F._KAKASI.is_available() is True
        assert notation("取り消し") == "{取|と}り{消|け}し"


# --------------------------------------------------------------------------- #
# Per-token annotation (F6: dictionary word chips)
# --------------------------------------------------------------------------- #
class TestAnnotateTokens:
    """`annotate_tokens` hands out readings generated for the whole line.

    The caller's tokenizer and this module disagree about compounds, so the
    interesting cases are all about what happens at a token boundary.
    """

    SENTENCE = "\u4eca\u65e5\u306f\u65e5\u672c\u8a9e\u3092\u52c9\u5f37\u3057\u3066\u4f1a\u3044\u307e\u3059\u3002"

    def test_always_returns_one_entry_per_token(self):
        tokens = ["a", "", "b"]
        assert len(F.annotate_tokens(tokens, "ab", "English")) == 3

    def test_every_entry_reconstructs_its_token(self):
        # I1, per token.
        tokens = ["\u4eca\u65e5", "\u306f", "\u65e5\u672c", "\u8a9e", "\u3092", "\u52c9\u5f37",
                  "\u3057", "\u3066", "\u4f1a\u3044", "\u307e\u3059", "\u3002"]
        for token, segments in zip(tokens,
                                   F.annotate_tokens(tokens, self.SENTENCE, "Japanese")):
            assert ''.join(seg.base for seg in segments) == token

    @FUGASHI_ONLY
    def test_reading_comes_from_the_line_not_the_token(self):
        tokens = ["\u4eca\u65e5", "\u306f"]
        result = F.annotate_tokens(tokens, self.SENTENCE, "Japanese")
        assert result[0][0].ruby == "\u304d\u3087\u3046"        # kyou, not konnichi

    def test_a_token_cutting_a_compound_gets_no_reading(self):
        # The tokenizer splits the compound; a reading for half of it would be
        # wrong (nippon instead of nihon), so the chip stays bare.
        tokens = ["\u65e5\u672c", "\u8a9e"]
        result = F.annotate_tokens(tokens, "\u65e5\u672c\u8a9e\u3092\u52c9\u5f37", "Japanese")
        assert all(seg.ruby is None for segments in result for seg in segments)

    def test_a_plain_run_is_clipped_to_the_token(self):
        # The plain run beside a reading continues past the token; splitting text
        # that carries no reading cannot make it wrong, so the reading survives.
        tokens = ["\u4f1a\u3044", "\u307e\u3059"]
        result = F.annotate_tokens(tokens, "\u4f1a\u3044\u307e\u3059\u3002", "Japanese")
        assert result[0][0].ruby is not None
        assert ''.join(seg.base for seg in result[0]) == "\u4f1a\u3044"
        assert all(seg.ruby is None for seg in result[1])

    def test_no_hint_and_no_kana_means_no_readings(self):
        tokens = ["\u6771\u4eac", "\u90fd"]
        result = F.annotate_tokens(tokens, "\u6771\u4eac\u90fd", None)
        assert all(seg.ruby is None for segments in result for seg in segments)

    def test_latin_text_is_untouched(self):
        tokens = ["I", "study", "Japanese"]
        result = F.annotate_tokens(tokens, "I study Japanese", "English")
        assert [segments[0].base for segments in result] == tokens
        assert all(seg.ruby is None for segments in result for seg in segments)

    def test_a_token_absent_from_the_text_stays_plain(self):
        result = F.annotate_tokens(["\u52c9\u5f37", "zzz"], self.SENTENCE, "Japanese")
        assert result[1] == (F.RubySegment("zzz", None),)

    def test_repeated_tokens_advance_through_the_text(self):
        text = "\u52c9\u5f37\u3068\u52c9\u5f37"
        result = F.annotate_tokens(["\u52c9\u5f37", "\u3068", "\u52c9\u5f37"], text, "Japanese")
        assert [''.join(s.base for s in segs) for segs in result] == \
            ["\u52c9\u5f37", "\u3068", "\u52c9\u5f37"]

    def test_empty_inputs_are_safe(self):
        assert F.annotate_tokens([], "", None) == ()
        assert F.annotate_tokens(["x"], "", None) == ((F.RubySegment("x", None),),)
        assert F.annotate_tokens([""], "abc", None) == ((),)
