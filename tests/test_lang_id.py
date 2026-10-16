"""
Tests for src/core/lang_id.py - which language CJK text is, from evidence only (Phase J2).

The hard rule: evidence never calls Chinese text Japanese, and never calls
Japanese text Chinese. Ambiguous text (most kanji-only Japanese, most Traditional
Chinese) comes back unknown, and is settled later by context, a model's verdict
or the user (Decision 22) - never by a guess here.

The fixtures are word lists: 311 kanji-only Japanese words (the 54 measured in
TODO.md F9, JLPT-level nouns, all 47 prefectures' and big cities' names,
ministries, company and paperwork terms, and the 2010 Jōyō kanji 剝 頰 塡 that
CP932 lacks), 149 Simplified and 162 Traditional Chinese words - including Hong
Kong's standard forms 衆 裏 綫 衞 啓 峯, which plain Big5 lacks and which a first
version of the rule took for Japanese. Coverage is written to
logs/lang_id_coverage.json so later sessions can compare.

Pure logic - no display needed.
"""
import json
import logging
import os
import time

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.core import lang_id
from src.core.lang_id import (CHINESE_SIMPLIFIED, CHINESE_TRADITIONAL, JAPANESE, Verdict,
                              han_evidence, has_chinese_glyph, has_kana, is_chinese,
                              is_japanese, normalize_language, output_hint, resolve,
                              ruby_hint, text_evidence)

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
F9_JAPANESE = """勉強 手紙 東京大学 大丈夫 株式会社 電源設定 経済 図書館 天気 発表 説明 準備 問題 学生
中国 日本 便利 時間 写真 電車 会社 駅前 料理 先生 結構 新聞 研究 東京都 営業 円高 売上 気温 広告 単語
変更 関係 検索 戦争 鉄道 歩道 読書 楽器 様式 処理 価格 帰国 覚悟 剣道 県庁 権利 拠点 栄養 挙手 込""".split()

JAPANESE_WORDS = F9_JAPANESE + """学校 銀行 病院 郵便局 大学 教室 食堂 映画 音楽 宿題 試験 授業 漢字 言葉
文化 世界 社会 経験 意見 理由 練習 旅行 運動 散歩 洗濯 掃除 野菜 果物 牛肉 豚肉 鶏肉 牛乳 食事 朝食 昼食
夕食 弁当 紅茶 番号 住所 電話 地図 交通 道路 空港 新幹線 地下鉄 自転車 自動車 会議 会話 質問 返事 約束
予定 予約 用意 注意 心配 安心 失敗 成功 必要 大切 簡単 複雑 有名 親切 丁寧 元気 病気 季節 台風 地震 火事
事故 警察 消防署 市役所 美術館 博物館 動物園 公園 神社 歴史 地理 数学 物理 化学 生物 英語 日本語 外国人
留学生 先輩 後輩 同僚 上司 部長 課長 社長 社員 従業員 給料 残業 休日 祝日 週末 毎日 今朝 今晩 明日 昨日
来週 先週 来月 来年 去年 今年 午前 午後 時計 眼鏡 財布 携帯電話 冷蔵庫 掃除機 辞書 雑誌 小説 手帳 封筒
切手 葉書 荷物 大阪 京都 北海道 沖縄 名古屋 横浜 神戸 福岡 札幌 仙台 広島 長崎 鹿児島 熊本 新宿 渋谷 池袋
秋葉原 浅草 銀座 品川 上野 奈良 金沢 静岡 千葉 埼玉 神奈川 茨城 栃木 群馬 富山 石川 福井 山梨 長野 岐阜
愛知 三重 滋賀 兵庫 和歌山 鳥取 島根 岡山 山口 徳島 香川 愛媛 高知 佐賀 大分 宮崎 青森 岩手 宮城 秋田 山形
福島 新潟 有限会社 合同会社 内閣府 総務省 財務省 外務省 法務省 文部科学省 厚生労働省 経済産業省 国土交通省
防衛省 環境省 警察庁 国税庁 最高裁判所 衆議院 参議院 国会 内閣総理大臣 都道府県 市区町村 住民票 確定申告
年金 健康保険 雇用保険 消費税 所得税 運転免許証 在留資格 日本銀行 取締役 代表取締役 人事部 営業部 総務部
経理部 情報 技術 開発 設計 製造 品質管理 顧客 取引先 見積書 請求書 領収書 納品書 契約書 会議室 議事録
報告書 企画書 汽車 愛人 工作 床 剝離 頰骨 補塡""".split()

SIMPLIFIED_WORDS = """我们 这个 说话 学习 时间 问题 电脑 飞机 经济 银行 今天天气很好 你好 谢谢 没有 为什么
东西 汉语 车站 图书馆 发表 医院 医生 护士 学校 大学生 工作 公司 经理 会议 电话 手机 电视 电影 音乐 运动
足球 篮球 游泳 跑步 旅游 飞机场 火车站 地铁 公共汽车 出租车 自行车 汽车 马路 红绿灯 信用卡 现金 价格 便宜
商店 超市 饭馆 餐厅 菜单 米饭 面条 饺子 包子 鸡蛋 牛奶 咖啡 茶叶 水果 苹果 香蕉 西瓜 葡萄 蔬菜 猪肉 牛肉
羊肉 早饭 午饭 晚饭 厨房 卧室 客厅 卫生间 洗手间 空调 冰箱 洗衣机 电梯 楼梯 窗户 门口 认识 知道 觉得 喜欢
希望 应该 可以 已经 还是 或者 因为 所以 虽然 但是 如果 那么 怎么样 什么 哪里 这里 那里 时候 现在 以后 以前
昨天 明天 今天 星期一 周末 晚上 早上 中午 下午 上午 年级 班级 作业 考试 成绩 答案 意思 语法 词典 汉字 拼音
声调 发音 练习 复习 预习 准备 参加 开始 结束 离开 回来 进去 出来""".split()

HONG_KONG_FORMS = "衆人 這裏 哪裏 路綫 衞生 啓示 山峯 公衆 群衆 綫上 衞星 裏面 着手".split()

TRADITIONAL_WORDS = """我們 這個 說話 學習 時間 問題 電腦 飛機 經濟 銀行 今天天氣很好 謝謝 沒有 為什麼 東西
漢語 車站 圖書館 發表 醫院 醫生 護士 學校 大學生 工作 公司 經理 會議 電話 手機 電視 電影 音樂 運動 足球
籃球 游泳 跑步 旅遊 飛機場 火車站 地鐵 公共汽車 計程車 腳踏車 汽車 馬路 紅綠燈 信用卡 現金 價格 便宜 商店
超市 飯館 餐廳 菜單 米飯 麵條 餃子 包子 雞蛋 牛奶 咖啡 茶葉 水果 蘋果 香蕉 西瓜 葡萄 蔬菜 豬肉 牛肉 羊肉
早飯 午飯 晚飯 廚房 臥室 客廳 衛生間 洗手間 空調 冰箱 洗衣機 電梯 樓梯 窗戶 門口 認識 知道 覺得 喜歡 希望
應該 可以 已經 還是 或者 因為 所以 雖然 但是 如果 那麼 怎麼樣 什麼 哪裡 這裡 那裡 時候 現在 以後 以前 昨天
明天 今天 星期一 週末 晚上 早上 中午 下午 上午 年級 班級 作業 考試 成績 答案 意思 語法 詞典 漢字 拼音 聲調
發音 練習 複習 預習 準備 參加 開始 結束 離開 回來 進去 出來 台灣 香港 臺北""".split() + HONG_KONG_FORMS

CHINESE_SENTENCES = ["這是我的書。", "我们在学习中文。", "今天天气很好，我们去公园吧。", "他昨天去了北京。",
                     "我不知道他在哪里。", "這本書很有意思，你看過嗎？", "我們明天見。", "你吃饭了吗？",
                     "中华人民共和国成立于一九四九年。", "學而時習之，不亦說乎？",
                     "列夫・托尔斯泰是俄国作家。", "這裏的人很多。"]

# Kana is the stronger evidence: a Chinese name inside a Japanese sentence.
JAPANESE_SENTENCES_WITH_CHINESE_NAMES = ["习近平国家主席が来日した。", "王さんは北京から来ました。",
                                        "劉備は蜀の皇帝である。", "毛泽东の写真を見た。"]


def test_fixture_sizes():
    """The sizes TODO.md J2 asks for, and no kana smuggled into a kanji-only list."""
    assert len(set(JAPANESE_WORDS)) >= 300
    assert len(set(SIMPLIFIED_WORDS)) >= 100
    assert len(set(TRADITIONAL_WORDS)) >= 100
    for word in JAPANESE_WORDS + SIMPLIFIED_WORDS + TRADITIONAL_WORDS:
        assert not has_kana(word), word


# --------------------------------------------------------------------------- #
# Names
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name, expected", [
    ("Japanese", JAPANESE), ("japanese", JAPANESE), ("ja", JAPANESE), ("日本語", JAPANESE),
    ("nihongo", JAPANESE), ("[Japanese]", JAPANESE), ("(Japanese)", JAPANESE),
    (" Japanese. ", JAPANESE),
    ("Chinese", CHINESE_SIMPLIFIED), ("Chinese Simplified", CHINESE_SIMPLIFIED),
    ("Chinese (Simplified)", CHINESE_SIMPLIFIED), ("zh-CN", CHINESE_SIMPLIFIED),
    ("zh_CN", CHINESE_SIMPLIFIED), ("中文简体", CHINESE_SIMPLIFIED), ("Mandarin", CHINESE_SIMPLIFIED),
    ("Chinese Traditional", CHINESE_TRADITIONAL), ("Chinese (Traditional)", CHINESE_TRADITIONAL),
    ("zh-TW", CHINESE_TRADITIONAL), ("zh-HK", CHINESE_TRADITIONAL), ("中文繁體", CHINESE_TRADITIONAL),
    ("vi", "Vietnamese"), ("english", "English"), ("ko", "Korean"), ("한국어", "Korean"),
    ("Klingon", "Klingon"),
])
def test_normalize_language(name, expected):
    assert normalize_language(name) == expected


@pytest.mark.parametrize("name", [None, "", "  ", "Unknown", "unknown", "UNKNOWN.", "n/a", "?"])
def test_names_that_name_no_language(name):
    assert normalize_language(name) is None


def test_is_japanese_and_is_chinese():
    assert is_japanese("ja") and not is_japanese("Chinese")
    assert is_chinese("Chinese Simplified") and is_chinese("zh-TW") and not is_chinese("Japanese")
    assert not is_japanese(None) and not is_chinese(None)


# --------------------------------------------------------------------------- #
# Evidence in the text
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text", ["勉強します", "コーヒー", "ｶﾀｶﾅ", "人々", "〆切", "三ヶ月", "Pythonで開発する"])
def test_kana_is_japanese(text):
    assert text_evidence(text) == Verdict(JAPANESE, 'kana')


def test_the_middle_dot_is_not_kana():
    """Chinese writes ・ between the parts of a foreign name."""
    assert not has_kana("列夫・托尔斯泰")
    assert text_evidence("列夫・托尔斯泰") == Verdict(CHINESE_SIMPLIFIED, 'zh-glyph')
    assert text_evidence("東京・大阪") is None


@pytest.mark.parametrize("text", ["経済", "天気", "読書", "図書館", "楽器", "変更", "拠点"])
def test_a_japanese_only_glyph_is_japanese(text):
    assert text_evidence(text) == Verdict(JAPANESE, 'jp-glyph')


@pytest.mark.parametrize("text, language", [
    ("我们", CHINESE_SIMPLIFIED), ("这个", CHINESE_SIMPLIFIED), ("说话", CHINESE_SIMPLIFIED),
    ("說話", CHINESE_TRADITIONAL),
])
def test_a_glyph_japanese_cannot_write_is_chinese(text, language):
    assert text_evidence(text) == Verdict(language, 'zh-glyph')
    assert has_chinese_glyph(text)


def test_contradicting_glyphs_prove_nothing():
    assert han_evidence("経济") is None          # 経 Japanese-only, 济 simplified
    assert text_evidence("経济") is None


@pytest.mark.parametrize("text", ["剝離", "頰骨", "補塡"])
def test_2010_joyo_kanji_outside_cp932_are_not_chinese(text):
    """The CP932 trap (TODO.md F9): these are Japanese, and in JIS X 0213."""
    assert han_evidence(text) is None
    assert not has_chinese_glyph(text)


@pytest.mark.parametrize("text", HONG_KONG_FORMS)
def test_hong_kong_forms_are_never_japanese(text):
    """The Big5 trap: 衆 裏 綫 衞 啓 峯 are outside Big5 but standard in Hong Kong."""
    assert han_evidence(text) != JAPANESE


# 這是我的書 without its full stop: the punctuated sentence is Chinese by its
# function words since K6 (test_function_words_in_a_sentence_are_chinese).
@pytest.mark.parametrize("text", ["勉強", "手紙", "東京大学", "先生", "這是我的書", "學生", ""])
def test_shared_spellings_stay_unknown(text):
    assert text_evidence(text) is None


def test_no_japanese_word_is_called_chinese():
    wrong = [w for w in JAPANESE_WORDS if (text_evidence(w) or Verdict(None, '')).language in
             (CHINESE_SIMPLIFIED, CHINESE_TRADITIONAL)]
    assert wrong == []


@pytest.mark.parametrize("words", [SIMPLIFIED_WORDS, TRADITIONAL_WORDS, CHINESE_SENTENCES],
                         ids=["simplified", "traditional", "sentences"])
def test_no_chinese_text_is_called_japanese(words):
    wrong = [w for w in words if (text_evidence(w) or Verdict(None, '')).language == JAPANESE]
    assert wrong == []


def test_a_chinese_verdict_names_the_right_variant():
    simplified = {text_evidence(w).language for w in SIMPLIFIED_WORDS if text_evidence(w)}
    traditional = {text_evidence(w).language for w in TRADITIONAL_WORDS if text_evidence(w)}
    assert simplified == {CHINESE_SIMPLIFIED}
    assert traditional == {CHINESE_TRADITIONAL}


@pytest.mark.parametrize("text", JAPANESE_SENTENCES_WITH_CHINESE_NAMES)
def test_kana_outweighs_a_chinese_name(text):
    assert text_evidence(text) == Verdict(JAPANESE, 'kana')


def test_coverage_is_recorded():
    """How much evidence alone settles - the rest waits for context, a model or the user.

    Lower bounds pin what was measured on 2026-10-15 (55, 80, 3); the actual
    numbers go to logs/lang_id_coverage.json for later sessions.
    """
    def resolved(words, language_test):
        return sum(1 for w in words if text_evidence(w) and language_test(text_evidence(w).language))

    report = {
        "japanese_words": len(JAPANESE_WORDS),
        "japanese_by_glyph": resolved(JAPANESE_WORDS, lambda lang: lang == JAPANESE),
        "f9_japanese_words": len(F9_JAPANESE),
        "f9_japanese_by_glyph": resolved(F9_JAPANESE, lambda lang: lang == JAPANESE),
        "simplified_words": len(SIMPLIFIED_WORDS),
        "simplified_by_glyph": resolved(SIMPLIFIED_WORDS, lambda lang: lang in lang_id.CHINESE),
        "traditional_words": len(TRADITIONAL_WORDS),
        "traditional_by_glyph": resolved(TRADITIONAL_WORDS, lambda lang: lang in lang_id.CHINESE),
    }
    os.makedirs("logs", exist_ok=True)
    with open(os.path.join("logs", "lang_id_coverage.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    assert report["japanese_by_glyph"] >= 55, report
    assert report["simplified_by_glyph"] >= 80, report
    assert report["traditional_by_glyph"] >= 3, report


# --------------------------------------------------------------------------- #
# The resolver
# --------------------------------------------------------------------------- #
def test_known_wins_outright():
    assert resolve("我们", known="Japanese") == Verdict(JAPANESE, 'known')
    assert resolve("勉強", known="Chinese Simplified") == Verdict(CHINESE_SIMPLIFIED, 'known')


def test_unknown_known_is_ignored():
    assert resolve("勉強します", known="Unknown") == Verdict(JAPANESE, 'kana')


def test_evidence_beats_the_model():
    assert resolve("勉強します", model="Chinese") == Verdict(JAPANESE, 'kana')
    assert resolve("我们", model="Japanese") == Verdict(CHINESE_SIMPLIFIED, 'zh-glyph')
    assert resolve("経済", model="Chinese") == Verdict(JAPANESE, 'jp-glyph')


def test_context_settles_a_fragment():
    assert resolve("勉強", context="毎日日本語を勉強しています。") == Verdict(JAPANESE, 'context')
    assert resolve("学习", context="我们在学习中文。") == Verdict(CHINESE_SIMPLIFIED, 'zh-glyph')
    assert resolve("学生", context="我们是学生。") == Verdict(CHINESE_SIMPLIFIED, 'context')


def test_context_never_overrides_the_texts_own_evidence():
    assert resolve("习近平", context="习近平国家主席が来日した。") == Verdict(CHINESE_SIMPLIFIED,
                                                                         'zh-glyph')


def test_context_beats_the_model():
    assert resolve("勉強", context="勉強しています。", model="Chinese") == Verdict(JAPANESE, 'context')


def test_the_model_settles_what_evidence_cannot():
    assert resolve("勉強", model="Japanese") == Verdict(JAPANESE, 'model')
    assert resolve("勉強", model="chinese") == Verdict(CHINESE_SIMPLIFIED, 'model')
    assert resolve("勉強", context="勉強", model="Japanese") == Verdict(JAPANESE, 'model')


@pytest.mark.parametrize("model", [None, "", "Unknown", "unknown"])
def test_no_verdict_is_unknown(model):
    assert resolve("勉強", model=model) == Verdict(None, 'none')


@pytest.mark.parametrize("text", [None, "", "Hello", "12345"])
def test_text_without_cjk_has_no_evidence(text):
    assert resolve(text) == Verdict(None, 'none')


def test_borrowed_verdicts_are_logged_without_the_text(caplog):
    with caplog.at_level(logging.DEBUG):
        resolve("勉強", context="毎日日本語を勉強しています。")
        resolve("手紙", model="Japanese")
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[LangID]")]
    assert lines == ["[LangID] evidence=context language=Japanese via=kana chars=2",
                     "[LangID] evidence=model language=Japanese chars=2"]


# --------------------------------------------------------------------------- #
# Hints
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("languages, expected", [
    (("Japanese", "English"), JAPANESE),
    (("Japanese",), JAPANESE),
    (("ja", "Vietnamese"), JAPANESE),
    ((None, "Japanese"), JAPANESE),
    (("Japanese", "Chinese Simplified"), None),
    (("Chinese (Traditional)", "Japanese"), None),
    (("English", "Vietnamese"), None),
    ((None, None), None),
    ((), None),
])
def test_ruby_hint(languages, expected):
    assert ruby_hint(*languages) == expected


@pytest.mark.parametrize("source, target, expected", [
    ("English", "Japanese", JAPANESE),
    ("Chinese Simplified", "Japanese", JAPANESE),     # the output is Japanese
    (None, "Japanese", JAPANESE),
    ("Japanese", "English", JAPANESE),                # quoted Japanese in English output
    ("Japanese", "Chinese Simplified", None),         # the output is Chinese
    ("Chinese Simplified", "English", None),
    (None, "English", None),
])
def test_output_hint(source, target, expected):
    assert output_hint(source, target) == expected


# --------------------------------------------------------------------------- #
# Cost and robustness
# --------------------------------------------------------------------------- #
def test_classifying_3000_kanji_is_cheap():
    """TODO.md J2 budget: < 5 ms once warm. Asserted at 25 ms so a busy CI
    machine does not flake; the measured figure goes into the failure message."""
    text = ("".join(JAPANESE_WORDS + SIMPLIFIED_WORDS + TRADITIONAL_WORDS) * 4)
    kanji = "".join(lang_id.HAN_RE.findall(text))[:3000]
    assert len(kanji) == 3000
    han_evidence(kanji)                                   # warm the per-glyph cache
    start = time.perf_counter()
    han_evidence(kanji)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 25, f"han_evidence(3000 kanji) took {elapsed_ms:.2f} ms"


def test_a_missing_codec_switches_glyph_evidence_off(monkeypatch):
    real_lookup = lang_id.codecs.lookup

    def lookup(name):
        if name == 'big5hkscs':
            raise LookupError(name)
        return real_lookup(name)

    monkeypatch.setattr(lang_id.codecs, 'lookup', lookup)
    lang_id.glyph_evidence_available.cache_clear()
    lang_id.glyph_class.cache_clear()
    try:
        assert han_evidence("経済") is None
        assert han_evidence("我们") is None
        assert text_evidence("勉強します") == Verdict(JAPANESE, 'kana')   # kana still counts
    finally:
        monkeypatch.undo()
        lang_id.glyph_evidence_available.cache_clear()
        lang_id.glyph_class.cache_clear()
    assert han_evidence("経済") == JAPANESE


def test_the_module_stays_pure():
    """lang_id must not import Tk, config or furigana (furigana builds on it)."""
    import inspect
    source = inspect.getsource(lang_id)
    for forbidden in ("import tkinter", "from tkinter", "import config", "from config",
                      "furigana import", "import furigana"):
        assert forbidden not in source, forbidden


# --------------------------------------------------------------------------- #
# K6 - two Chinese function words in a sentence
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text, language", [
    ("這是我的書。", CHINESE_TRADITIONAL),      # the case that asked "Japanese or Chinese?"
    ("你是學生嗎？", CHINESE_TRADITIONAL),
    ("她是我的朋友。", CHINESE_SIMPLIFIED),      # no script-only hanzi: a tie is Simplified
    ("它很好。", CHINESE_SIMPLIFIED),
    ("你好嗎?", CHINESE_TRADITIONAL),            # ASCII punctuation counts too
    ("這本書很好，你呢？", CHINESE_TRADITIONAL),
])
def test_function_words_in_a_sentence_are_chinese(text, language):
    assert lang_id.grammar_evidence(text) == language
    assert text_evidence(text) == Verdict(language, 'zh-grammar')


@pytest.mark.parametrize("text", [
    "這是我的書",            # no punctuation: a term, the model's to place
    "我是學生。",            # one listed word (我 is not listed)
    "是正完了。",            # Japanese: 是正 + 完了 - 了 is not listed
    "目的完了。",
    "我慢終了。",
    "了解。",
    "社是、是非。",          # the same listed word twice
    "国是。",
    "東京大学。",
])
def test_one_function_word_or_none_proves_nothing(text):
    assert lang_id.grammar_evidence(text) is None
    assert text_evidence(text) is None


def test_a_japanese_only_glyph_wins_over_function_words():
    # 気 is a shinjitai Chinese never writes: the glyph rule, unchanged.
    assert lang_id.grammar_evidence("這是気嗎？") is None
    assert text_evidence("這是気嗎？") == Verdict(JAPANESE, 'jp-glyph')


def test_kana_wins_over_function_words():
    assert text_evidence("這是本です。") == Verdict(JAPANESE, 'kana')


def test_grammar_evidence_beats_a_models_verdict():
    assert resolve("這是我的書。", model=JAPANESE) == Verdict(CHINESE_TRADITIONAL, 'zh-grammar')


def test_the_excluded_words_are_ones_japanese_writes():
    # 的, 了 and 我 are left out on purpose (目的, 終了, 我慢): a stress test of two
    # Japanese compounds in one sentence came back Chinese 31% of the time with them.
    assert not {'的', '了', '我'} & lang_id.CHINESE_FUNCTION_CHARS


def test_no_word_of_a_japanese_dictionary_is_called_chinese():
    """Every all-kanji word of pykakasi's dictionary (SKK-JISYO, ~200 000), as a
    term and as a one-word sentence - measured at 0 when the rule was chosen."""
    kanji = pytest.importorskip("pykakasi.kanji")
    words = [w for table in kanji.Kanwa()._jisyo_table.values() for w in table
             if len(w) >= 2 and all(lang_id.HAN_RE.match(ch) for ch in w)]
    assert len(words) > 100000
    called = [w for w in words
              if lang_id.grammar_evidence(w) or lang_id.grammar_evidence(w + '。')]
    assert called == []


def test_without_the_codecs_grammar_evidence_is_off(monkeypatch):
    monkeypatch.setattr(lang_id, 'glyph_evidence_available', lambda: False)
    assert lang_id.grammar_evidence("這是我的書。") is None


def test_the_rest_of_the_app_hears_it():
    from src.core.history import HistoryManager
    from src.core.nlp_manager import nlp_manager
    from src.core.source_marker import source_clause
    clause = source_clause("這是我的書。")
    assert clause.asks is False and clause.stated == CHINESE_TRADITIONAL
    assert "the text above is Chinese" in clause.text
    assert nlp_manager.detect_language("這是我的書。") == (CHINESE_TRADITIONAL, 0.9)
    assert HistoryManager(None)._detect_language("這是我的書。") == CHINESE_TRADITIONAL
