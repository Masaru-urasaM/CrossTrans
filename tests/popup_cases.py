"""
The quick-translate popup's measurement corpus (TODO.md §4 and Appendix).

Thirteen cases, A-M - one word up to a long Japanese source with readings - and
the popup's other states, as plain data. Shared by `tools/popup_gallery.py`
(images and metrics) and the popup geometry tests, so a number in TODO.md, an
image in the gallery and a test assertion all describe the same popup.

Not a test module: nothing here runs on import. No Vietnamese, by the project
rule - French with accents stands in for Latin text with diacritics.
"""
from dataclasses import dataclass
from typing import Optional

MODEL = "gemini-2.5-flash (Google)"

RESULT = 'result'
GRAMMAR = 'grammar'
ERROR = 'error'
REPLACE_PREVIEW = 'replace_preview'
CUSTOM_PROMPT = 'custom_prompt'
STATES = (RESULT, GRAMMAR, ERROR, REPLACE_PREVIEW, CUSTOM_PROMPT)

PARA_EN = ("Machine translation has improved dramatically over the past decade. Neural models "
           "now capture context across whole sentences, handle idioms far better than "
           "phrase-based systems, and can even adapt their tone to the audience. Still, they "
           "make mistakes that a careful reader would never make: they may drop a negation, "
           "confuse two similar names, or translate a technical term inconsistently within the "
           "same document. For important texts, a quick human review remains essential.")
PARA_FR = ("La traduction automatique s'est considérablement améliorée au cours de la dernière "
           "décennie. Les modèles neuronaux saisissent désormais le contexte de phrases "
           "entières, gèrent les expressions idiomatiques bien mieux que les systèmes à base de "
           "segments et peuvent même adapter leur ton au public. Ils commettent pourtant des "
           "erreurs qu'un lecteur attentif ne ferait jamais : ils peuvent omettre une négation, "
           "confondre deux noms proches ou traduire un terme technique de manière incohérente "
           "au sein d'un même document. Pour les textes importants, une relecture humaine "
           "rapide reste indispensable.")
PARA_ZH = ("机器翻译在过去十年中有了显著进步。神经网络模型现在能够理解整句话的上下文，处理习语的能力远超"
           "基于短语的系统，甚至可以根据受众调整语气。然而，它们仍会犯细心的读者绝不会犯的错误：可能漏掉"
           "否定词，混淆两个相似的名字，或在同一文档中对同一术语的翻译前后不一致。对于重要文本，快速的人工"
           "审校仍然必不可少。")
JP_PARA = ("昨日は友達と一緒に京都へ行きました。朝早く出発したので、電車はまだ空いていました。清水寺では"
           "紅葉がとても綺麗で、たくさんの写真を撮りました。昼ご飯には湯豆腐を食べて、午後は嵐山の竹林を"
           "散歩しました。帰りの電車は混んでいましたが、楽しい一日でした。")
JP_PARA_EN = ("Yesterday I went to Kyoto with a friend. We left early in the morning, so the train "
              "was still empty. At Kiyomizu-dera the autumn leaves were beautiful, and we took "
              "lots of photos. For lunch we had simmered tofu, and in the afternoon we walked "
              "through the bamboo grove in Arashiyama. The train home was crowded, but it was a "
              "fun day.")
JP_WORK = ("来週の会議について、資料の準備状況を確認させてください。前回の打ち合わせで決まった内容を"
           "踏まえて、予算案と日程表を更新する必要があります。担当者が変更になった件については、"
           "関係部署へ早めに連絡しておいた方が良いと思います。")
JP_WORK_EN = ("Let me check how the materials for next week's meeting are coming along. Based on "
              "what we decided at the last meeting, the draft budget and the schedule need to be "
              "updated. As for the change of the person in charge, I think it would be better to "
              "let the departments concerned know early.")
SENTENCE_EN = "The quick brown fox jumps over the lazy dog near the riverbank this morning."
SENTENCE_FR = "Le renard brun rapide saute par-dessus le chien paresseux près de la rive ce matin."
REQUEST_EN = ("Please check the attached document and reply by Friday. If you have any questions, "
              "feel free to contact me.")
REQUEST_JA = ("添付の資料をご確認の上、金曜日までにご返信ください。ご不明な点がございましたら、"
              "お気軽にご連絡ください。")
URL = ("https://example.com/docs/api/v2/reference/translation/endpoints/quick-translate"
       "?lang=fr&format=json&verbose=true")
ERROR_TEXT = ("Error: All API keys failed.\nKey #1: 429 Too Many Requests - quota exceeded for "
              "gemini-2.5-flash\nKey #2: 401 Unauthorized - invalid API key")


@dataclass(frozen=True)
class PopupCase:
    """One popup, as the app would show it - no API call involved."""

    key: str                         # 'A'..'M', or a case key plus its state ('B-grammar')
    name: str
    original: str
    translated: str
    target: str
    source: Optional[str] = None     # the settled source; 'Japanese' adds the readings block
    model: Optional[str] = MODEL     # the credit line; None leaves it off
    trial: Optional[dict] = None     # trial-mode header info, as get_trial_info() returns it
    state: str = RESULT


CASES = (
    PopupCase('A', 'one word', "Hello", "Bonjour", 'French'),
    PopupCase('B', 'one sentence', SENTENCE_EN, SENTENCE_FR, 'French'),
    PopupCase('C', 'paragraph', PARA_EN, PARA_FR, 'French'),
    PopupCase('D', 'four paragraphs', "\n\n".join([PARA_EN] * 4), "\n\n".join([PARA_FR] * 4),
              'French'),
    PopupCase('E', 'Japanese sentence + readings', "私は毎日日本語を勉強しています。",
              "I study Japanese every day.", 'English', source='Japanese'),
    PopupCase('F', 'Japanese paragraph + readings', JP_PARA, JP_PARA_EN, 'English',
              source='Japanese'),
    PopupCase('G', 'long Japanese + readings', "\n".join([JP_PARA, JP_WORK] * 3),
              "\n".join([JP_PARA_EN, JP_WORK_EN] * 3), 'English', source='Japanese'),
    PopupCase('H', 'English to Japanese, readings in the box', REQUEST_EN, REQUEST_JA, 'Japanese'),
    PopupCase('I', '10-line list',
              "Shopping list:\n- Milk\n- Eggs\n- Bread\n- Butter\n- Apples\n- Coffee beans\n"
              "- Rice\n- Soy sauce\n- Green tea",
              "Liste de courses :\n- Lait\n- Oeufs\n- Pain\n- Beurre\n- Pommes\n"
              "- Grains de cafe\n- Riz\n- Sauce soja\n- The vert", 'French'),
    PopupCase('J', 'long URL', f"See {URL} for details.", f"Voir {URL} pour plus de détails.",
              'French'),
    PopupCase('K', 'error', "Hello", ERROR_TEXT, 'French', model=None, state=ERROR),
    PopupCase('L', 'kanji term, trial line + chooser row', "汽車", "Car", 'English',
              source='Chinese (Simplified)', model="llama-3.3-70b (Trial mode)",
              trial={'is_trial': True, 'remaining': 15, 'daily_limit': 20}),
    PopupCase('M', 'English to Chinese paragraph', PARA_EN, PARA_ZH, 'Chinese (Simplified)'),
)

# The popup's other states, on texts from the cases above.
STATE_CASES = (
    PopupCase('B-grammar', 'grammar fix', SENTENCE_EN.replace("jumps", "jump"), SENTENCE_EN,
              'Grammar', state=GRAMMAR),
    PopupCase('C-replace', 'replace preview of a paragraph', PARA_EN, PARA_FR, 'French',
              state=REPLACE_PREVIEW),
    PopupCase('H-replace', 'replace preview with readings', REQUEST_EN, REQUEST_JA, 'Japanese',
              state=REPLACE_PREVIEW),
    PopupCase('C-prompt', 'Custom Prompt edit mode', PARA_EN, PARA_FR, 'French',
              state=CUSTOM_PROMPT),
)

ALL_CASES = CASES + STATE_CASES


def case(key: str) -> PopupCase:
    """The case with this key."""
    return next(c for c in ALL_CASES if c.key == key)


class FakeConfig:
    """The two getters the popup calls: readings on, Manual Replace (the preview)."""

    def get_furigana_enabled(self):
        return True

    def get_quick_replace(self):
        return False


def show_case(manager, popup_case: PopupCase) -> None:
    """Put `popup_case` up in `manager` the way the app would - no API call.

    The readings block is the notation the app builds for a Japanese source
    (`TranslationService.generate_furigana`); the replace preview and Custom
    Prompt are entered through the handlers their buttons call.
    """
    from src.core import furigana
    notation = (furigana.generate_notation(popup_case.original, popup_case.source)
                if popup_case.source == 'Japanese' else None)
    manager.show(popup_case.translated, popup_case.target, popup_case.trial, popup_case.original,
                 furigana_text=notation, is_grammar=popup_case.state == GRAMMAR,
                 model_info=popup_case.model, source_lang=popup_case.source)
    if popup_case.state == REPLACE_PREVIEW:
        manager._show_replace_preview()
    elif popup_case.state == CUSTOM_PROMPT:
        manager._enter_custom_prompt_mode()
