"""
Tests for the dictionary lookup prompt and its wiring (Phase J1).

The prompt used to carry only the target language, so a kanji-only Japanese
headword was looked up as whatever the model guessed - measured 2026-10-15, three
providers each read 汽車, 工作 and 床 as Chinese. It now states the source
language when the caller knows it, sends the sentences the words came from, and
asks for a pronunciation that suits the source.

These tests pin the parts other code depends on - the eight labels the result
window parses, the source-language rule, the context trimming - and the wiring
from BOTH Dictionary windows (main window and popup, which are separate copies of
the same flow) down to `dictionary_lookup()`. What real models answer is measured
separately by `tools/eval_dictionary_prompt.py`.

The wiring tests need a Tk display (see the `tk_root` fixture).
"""
import logging
import time
import tkinter as tk
from unittest.mock import MagicMock

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.core.dictionary_prompt import (DICTIONARY_CONTEXT_MAX_CHARS,
                                        build_dictionary_prompt,
                                        dictionary_source_language,
                                        extract_context, language_key)
from src.core.translation import TranslationService
from src.ui.dictionary_render import FIELD_RE, field_policy

JP_TEXT = "昨日は雨でした。友達に手紙を書きました。手紙は長かったです。"
LABELS = ['Translation', 'Source Language', 'Definition', 'Word Type',
          'Pronunciation', 'Synonyms', 'Antonyms', 'Examples']


def format_fields(prompt):
    """(number, label) of every `N. **Label**:` line in the OUTPUT FORMAT block."""
    block = prompt[prompt.index("OUTPUT FORMAT"):prompt.index("CRITICAL:")]
    fields = []
    for line in block.splitlines():
        match = FIELD_RE.match(line)
        if match:
            fields.append((int(match.group(1)), match.group(2)))
    return fields


def field_line(prompt, number):
    return next(line for line in prompt.splitlines() if line.startswith(f"{number}. **"))


# --------------------------------------------------------------------------- #
# Which language the prompt is told
# --------------------------------------------------------------------------- #
class TestDictionarySourceLanguage:
    def test_detected_japanese_is_stated(self):
        # detect_language() needs kana to say Japanese: that is proof.
        assert dictionary_source_language("Japanese") == "Japanese"

    @pytest.mark.parametrize("language", [
        "Chinese (Simplified)", "Chinese (Traditional)",
    ])
    def test_detected_chinese_is_left_to_the_model(self, language):
        # Every kanji-only text without kana is detected as Chinese (Simplified),
        # 勉強 included - a guess, so the model decides instead.
        assert dictionary_source_language(language) is None

    @pytest.mark.parametrize("language", ["English", "French", "Korean", "Vietnamese"])
    def test_other_detected_languages_are_left_to_the_model(self, language):
        # Latin text comes back as the first installed European pack.
        assert dictionary_source_language(language) is None

    @pytest.mark.parametrize("language", [
        "Chinese (Simplified)", "English", "Japanese", "Korean",
    ])
    def test_a_language_the_user_picked_is_stated(self, language):
        assert dictionary_source_language(language, user_chosen=True) == language

    @pytest.mark.parametrize("language", [None, "", "Unknown"])
    def test_no_language_is_never_stated(self, language):
        assert dictionary_source_language(language) is None
        assert dictionary_source_language(language, user_chosen=True) is None

    def test_language_key_unifies_the_two_spellings_of_chinese(self):
        assert language_key("Chinese (Simplified)") == language_key("Chinese Simplified")
        assert language_key("Japanese") != language_key("Chinese Simplified")


# --------------------------------------------------------------------------- #
# Context: the sentences the headwords came from
# --------------------------------------------------------------------------- #
class TestExtractContext:
    def test_keeps_only_sentences_that_contain_the_word(self):
        assert extract_context(JP_TEXT, ["手紙"]) == "友達に手紙を書きました。\n手紙は長かったです。"

    def test_several_words_keep_text_order(self):
        text = "犬が好きです。猫も好きです。鳥は嫌いです。"
        assert extract_context(text, ["鳥", "犬"]) == "犬が好きです。\n鳥は嫌いです。"

    def test_a_repeated_sentence_is_sent_once(self):
        text = "手紙を書きました。手紙を書きました。"
        assert extract_context(text, ["手紙"]) == "手紙を書きました。"

    def test_a_word_not_in_the_text_gets_no_context(self):
        # A custom-box phrase the user typed does not occur in the text.
        assert extract_context(JP_TEXT, ["勉強"]) == ""

    @pytest.mark.parametrize("text", ["勉強", "勉強。", " 勉強 \n", "「勉強」"])
    def test_a_context_that_is_just_the_headword_is_dropped(self, text):
        # The user selected the word alone: repeating it adds nothing.
        assert extract_context(text, ["勉強"]) == ""

    def test_latin_sentences_split_at_full_stops_and_ignore_case(self):
        text = "We met at noon. Study hard, he said. Then we left."
        assert extract_context(text, ["study"]) == "Study hard, he said."

    def test_a_decimal_point_does_not_end_a_sentence(self):
        text = "The rate rose to 3.5 percent this year. Nothing else changed."
        assert extract_context(text, ["rate"]) == "The rate rose to 3.5 percent this year."

    def test_line_breaks_end_a_sentence(self):
        text = "件名：会議\n明日の会議は手紙で連絡します\n以上"
        assert extract_context(text, ["手紙"]) == "明日の会議は手紙で連絡します"

    def test_the_cap_stops_before_a_sentence_that_would_exceed_it(self):
        sentence = "毎日日本語を勉強しています。"            # 14 characters
        context = extract_context(sentence * 100, ["勉強"])
        assert context == sentence                      # deduplicated
        text = "".join(f"{i}回目も勉強しています。" for i in range(200))
        context = extract_context(text, ["勉強"], max_chars=100)
        assert 0 < len(context) <= 100
        assert context.splitlines()[0] == "0回目も勉強しています。"
        assert all("勉強" in line for line in context.splitlines())

    def test_one_overlong_sentence_is_cut_around_the_headword(self):
        text = "あ" * 1000 + "手紙" + "い" * 1000 + "。"
        context = extract_context(text, ["手紙"])
        assert len(context) == DICTIONARY_CONTEXT_MAX_CHARS
        assert "手紙" in context
        assert context.startswith("あ") and context.endswith("い")

    @pytest.mark.parametrize("text, words", [(None, ["手紙"]), ("", ["手紙"]),
                                             (JP_TEXT, []), (JP_TEXT, ["", "  "])])
    def test_nothing_to_work_with_gives_no_context(self, text, words):
        assert extract_context(text, words) == ""


# --------------------------------------------------------------------------- #
# The prompt
# --------------------------------------------------------------------------- #
class TestPromptLanguages:
    def test_known_source_and_target_are_stated(self):
        prompt = build_dictionary_prompt(["手紙"], "English", "Japanese")
        assert "Source language: Japanese" in prompt
        assert "Target language: English" in prompt
        assert "HEADWORDS (look up each one as a Japanese word):" in prompt

    def test_kanji_only_japanese_is_never_taken_for_chinese(self):
        prompt = build_dictionary_prompt(["手紙"], "English", "Japanese")
        assert "A headword written only in kanji is still Japanese" in prompt
        assert "never treat it as Chinese because of its script" in prompt
        assert 'Japanese 手紙 means "letter"' in prompt

    def test_field_2_is_fixed_to_the_known_source(self):
        prompt = build_dictionary_prompt(["手紙"], "Vietnamese", "Japanese")
        assert field_line(prompt, 2) == "2. **Source Language**: Japanese"
        assert 'Field 2 is exactly "Japanese"' in prompt

    def test_chinese_source_is_never_taken_for_japanese(self):
        prompt = build_dictionary_prompt(["学习"], "English", "Chinese (Simplified)")
        assert "never treat it as Japanese because of its script" in prompt
        assert field_line(prompt, 2) == "2. **Source Language**: Chinese (Simplified)"

    def test_an_unknown_source_is_left_to_the_model(self):
        prompt = build_dictionary_prompt(["勉強"], "English")
        assert "Source language: not given" in prompt
        assert "Decide it for each headword" in prompt
        assert "It is Japanese when the context is Japanese" in prompt
        assert field_line(prompt, 2) == "2. **Source Language**: the language you decided"
        assert "HEADWORDS:" in prompt

    def test_no_tie_break_tells_the_model_which_language_is_likelier(self):
        # Measured 2026-10-15: "choose the language in which it is more commonly
        # written" turned gpt-oss-120b's bare 先生 from "teacher" into Chinese "Mr." -
        # Chinese text is more abundant, so "more common" means Chinese for every
        # shared spelling. Without context the model decides from the headword alone
        # (Decision 21); a Japanese lean would be the declined default (Decision 22).
        prompt = build_dictionary_prompt(["先生"], "English")
        assert "more common" not in prompt
        assert "Without such context, decide from the headword itself." in prompt

    def test_latin_sources_get_no_kanji_rule(self):
        prompt = build_dictionary_prompt(["study"], "Japanese", "English")
        assert "kanji" not in prompt.split("OUTPUT FORMAT")[0]
        assert "1. Every headword is English. Give its English meaning." in prompt

    def test_target_language_fields_are_named(self):
        prompt = build_dictionary_prompt(["手紙"], "Vietnamese", "Japanese")
        assert "Translation, Definition and Word Type are written in Vietnamese" in prompt
        assert field_line(prompt, 4).endswith("in Vietnamese")
        assert "   - Japanese sentence → Vietnamese translation" in prompt


class TestPromptPronunciation:
    def test_japanese_is_hiragana_only(self):
        # User's choice (2026-10-15): the reading, no romaji.
        prompt = build_dictionary_prompt(["勉強"], "English", "Japanese")
        assert field_line(prompt, 5) == "5. **Pronunciation**: reading in hiragana"
        rule = next(l for l in prompt.splitlines() if l.startswith("- Pronunciation:"))
        assert "hiragana only" in rule
        assert "No romaji, no IPA" in rule
        assert "べんきょう" in rule

    def test_chinese_is_pinyin(self):
        prompt = build_dictionary_prompt(["学习"], "English", "Chinese (Traditional)")
        assert field_line(prompt, 5) == "5. **Pronunciation**: pinyin"
        assert "pinyin with tone marks" in prompt

    def test_korean_is_revised_romanization(self):
        prompt = build_dictionary_prompt(["사랑"], "English", "Korean")
        assert "Revised Romanization" in prompt

    def test_other_sources_keep_ipa_and_a_target_phonetic(self):
        prompt = build_dictionary_prompt(["hello"], "Japanese", "English")
        assert "/IPA/ plus a phonetic spelling in Japanese" in prompt
        assert "hiragana" not in prompt

    def test_an_unknown_source_covers_each_script(self):
        prompt = build_dictionary_prompt(["勉強"], "English")
        rule = next(l for l in prompt.splitlines() if l.startswith("- Pronunciation:"))
        assert "hiragana only" in rule and "pinyin" in rule and "/IPA/" in rule


class TestPromptMonolingual:
    def test_same_source_and_target_is_a_monolingual_entry(self):
        prompt = build_dictionary_prompt(["勉強"], "Japanese", "Japanese")
        assert "This is a monolingual Japanese dictionary" in prompt
        assert field_line(prompt, 1) == "1. **Translation**: a simpler Japanese equivalent (REQUIRED)"
        assert "Japanese translation" not in prompt
        assert "   - Japanese sentence → simpler Japanese paraphrase" in prompt

    def test_synonyms_are_listed_without_arrows(self):
        prompt = build_dictionary_prompt(["勉強"], "Japanese", "Japanese")
        assert "→" not in field_line(prompt, 6)
        assert "→" not in field_line(prompt, 7)

    def test_the_two_spellings_of_chinese_are_one_language(self):
        prompt = build_dictionary_prompt(["学习"], "Chinese Simplified", "Chinese (Simplified)")
        assert "monolingual" in prompt

    def test_different_languages_are_bilingual(self):
        assert "monolingual" not in build_dictionary_prompt(["勉強"], "English", "Japanese")


class TestPromptStructure:
    @pytest.mark.parametrize("source, target", [
        ("Japanese", "English"), (None, "Vietnamese"), ("Japanese", "Japanese"),
        ("Chinese (Simplified)", "English"), ("English", "Japanese"),
    ])
    def test_the_eight_labels_are_unchanged(self, source, target):
        # _align_dictionary_text() and dictionary_render parse these exact labels.
        fields = format_fields(build_dictionary_prompt(["x"], target, source))
        assert fields == list(enumerate(LABELS, start=1))

    def test_the_renderer_reads_the_labels_as_before(self):
        fields = dict(format_fields(build_dictionary_prompt(["x"], "English", "Japanese")))
        assert field_policy(1, fields[1]) == (True, True)      # target-language text
        assert field_policy(3, fields[3]) == (True, True)
        assert field_policy(5, fields[5]) == (False, False)    # never annotated

    def test_headwords_are_numbered_in_order(self):
        prompt = build_dictionary_prompt(["手紙", "勉強", "新聞"], "English", "Japanese")
        assert "1. 手紙\n2. 勉強\n3. 新聞" in prompt
        assert "Provide an entry for all 3 headword(s)" in prompt

    def test_the_entry_header_is_still_required(self):
        prompt = build_dictionary_prompt(["手紙"], "English", "Japanese")
        assert "## [headword exactly as given]" in prompt
        assert 'Start every entry with the "## [headword]" line' in prompt

    def test_context_sits_between_delimiters(self):
        prompt = build_dictionary_prompt(["手紙"], "English", "Japanese", "友達に手紙を書きました。")
        start, end = prompt.index("===CONTEXT==="), prompt.index("===END OF CONTEXT===")
        assert start < prompt.index("友達に手紙を書きました。") < end
        assert end < prompt.index("HEADWORDS")
        assert "choose each headword's sense; do not translate it" in prompt

    def test_without_a_source_the_context_also_decides_the_language(self):
        prompt = build_dictionary_prompt(["手紙"], "English", None, "友達に手紙を書きました。")
        assert "choose each headword's language and sense" in prompt

    @pytest.mark.parametrize("context", [None, "", "   \n"])
    def test_no_context_leaves_the_block_out(self, context):
        prompt = build_dictionary_prompt(["手紙"], "English", "Japanese", context)
        assert "===CONTEXT===" not in prompt


# --------------------------------------------------------------------------- #
# TranslationService.dictionary_lookup
# --------------------------------------------------------------------------- #
@pytest.fixture
def service():
    """A service whose model call is recorded instead of sent."""
    svc = TranslationService.__new__(TranslationService)
    svc.prompts = []

    def fake_call(prompt):
        svc.prompts.append(prompt)
        return "## [手紙]\n\n1. **Translation**: letter"

    svc._call_model = fake_call
    return svc


class TestDictionaryLookup:
    def test_source_and_trimmed_context_reach_the_prompt(self, service):
        service.dictionary_lookup(["手紙"], "English", source_language="Japanese",
                                  context=JP_TEXT)
        prompt = service.prompts[0]
        assert "Source language: Japanese" in prompt
        assert "友達に手紙を書きました。" in prompt
        assert "昨日は雨でした。" not in prompt          # no headword in it

    def test_the_old_call_shape_still_works(self, service):
        result = service.dictionary_lookup(["手紙"], "English")
        assert result.startswith("## [手紙]")
        assert "Source language: not given" in service.prompts[0]
        assert "===CONTEXT===" not in service.prompts[0]

    def test_a_single_string_is_one_headword(self, service):
        service.dictionary_lookup("手紙", "English", source_language="Japanese")
        assert "1. 手紙\n" in service.prompts[0]

    def test_no_words_makes_no_call(self, service):
        assert service.dictionary_lookup([], "English") == ""
        assert service.prompts == []

    def test_a_failed_call_still_returns_an_error_string(self, service):
        def boom(prompt):
            raise RuntimeError("quota")
        service._call_model = boom
        assert service.dictionary_lookup(["手紙"], "English") == "Error: quota"

    def test_the_log_line_carries_counts_never_the_text(self, service, caplog):
        with caplog.at_level(logging.INFO):
            service.dictionary_lookup(["手紙"], "English", source_language="Japanese",
                                      context=JP_TEXT)
        lines = [r.getMessage() for r in caplog.records if "[Dictionary]" in r.getMessage()]
        assert lines == ["[Dictionary] lookup n=1 source=Japanese target=English "
                         f"context_chars={len(extract_context(JP_TEXT, ['手紙']))}"]
        assert "手紙" not in lines[0]


# --------------------------------------------------------------------------- #
# Wiring: both Dictionary windows pass the source language and the text
# --------------------------------------------------------------------------- #
class _FakeButton:
    def configure(self, **kwargs):
        pass


class _FakeWordFrame:
    """Stands in for WordButtonFrame: records the lookup callbacks it is given."""
    created = []

    def __init__(self, parent, text, **kwargs):
        self.text = text
        self.kwargs = kwargs
        self.frame = tk.Frame(parent)
        self.expand_btn = _FakeButton()
        _FakeWordFrame.created.append(self)

    def set_exit_callback(self, callback):
        pass

    def pack(self, **kwargs):
        pass

    def insert_custom_widget(self, widget):
        pass

    def set_drop_target(self, target):
        pass


class _FakeBoxes:
    """Stands in for CustomWordBoxesFrame: `phrases` is what the boxes hold."""
    phrases = []

    def __init__(self, parent, language=None, furigana_enabled=True):
        self.frame = tk.Frame(parent)

    def get_all_phrases(self):
        return list(_FakeBoxes.phrases)


class _SyncThread:
    """threading.Thread that runs its target on start(), so the call is visible."""

    def __init__(self, target=None, daemon=None, **kwargs):
        self._target = target

    def start(self):
        self._target()


@pytest.fixture
def fake_dictionary_ui(tk_root, monkeypatch):
    """Replace the word area and custom boxes; close every window a test opens."""
    _FakeWordFrame.created = []
    _FakeBoxes.phrases = []
    monkeypatch.setattr('src.ui.dictionary_mode.WordButtonFrame', _FakeWordFrame)
    monkeypatch.setattr('src.ui.custom_word_boxes.CustomWordBoxesFrame', _FakeBoxes)
    monkeypatch.setattr('src.ui.quick_translate.get_monitor_work_area', lambda x, y: None)
    monkeypatch.setattr('threading.Thread', _SyncThread)
    before = set(tk_root.winfo_children())
    yield _FakeWordFrame
    tk_root.update()                      # let scheduled result callbacks run
    for widget in set(tk_root.winfo_children()) - before:
        try:
            widget.destroy()
        except tk.TclError:
            pass


@pytest.fixture
def main_window_popup(tk_root, monkeypatch):
    from src.ui.dictionary_popup import DictionaryPopup
    monkeypatch.setattr('src.ui.dictionary_popup.set_dark_title_bar', lambda w: None)
    service = MagicMock()
    service.get_trial_info.return_value = None
    service.dictionary_lookup.return_value = "## [手紙]"
    config = MagicMock()
    config.get_furigana_enabled.return_value = True
    popup = DictionaryPopup(tk_root, config, service, MagicMock(), MagicMock())
    popup.configure_callbacks(get_selected_language=lambda: "English", get_popup=lambda: None)
    return popup


class TestMainWindowWiring:
    def test_detected_japanese_and_the_text_reach_the_lookup(self, fake_dictionary_ui,
                                                            main_window_popup):
        main_window_popup._open_with_language(JP_TEXT, "Japanese")
        fake_dictionary_ui.created[-1].kwargs['on_lookup'](["手紙"])
        main_window_popup.translation_service.dictionary_lookup.assert_called_once_with(
            ["手紙"], "English", source_language="Japanese", context=JP_TEXT)

    def test_detected_chinese_lets_the_model_decide(self, fake_dictionary_ui,
                                                    main_window_popup):
        main_window_popup._open_with_language("勉強", "Chinese (Simplified)")
        fake_dictionary_ui.created[-1].kwargs['on_lookup'](["勉強"])
        call = main_window_popup.translation_service.dictionary_lookup.call_args
        assert call.kwargs['source_language'] is None
        assert call.kwargs['context'] == "勉強"

    def test_a_language_the_user_picked_is_stated(self, fake_dictionary_ui,
                                                  main_window_popup):
        main_window_popup._open_with_language("勉強", "Chinese (Simplified)",
                                              user_chosen=True)
        fake_dictionary_ui.created[-1].kwargs['on_lookup'](["勉強"])
        call = main_window_popup.translation_service.dictionary_lookup.call_args
        assert call.kwargs['source_language'] == "Chinese (Simplified)"

    def test_custom_box_phrases_carry_the_same_language(self, fake_dictionary_ui,
                                                        main_window_popup):
        _FakeBoxes.phrases = ["手紙"]
        main_window_popup._open_with_language(JP_TEXT, "Japanese")
        fake_dictionary_ui.created[-1].kwargs['on_no_selection']()
        main_window_popup.translation_service.dictionary_lookup.assert_called_once_with(
            ["手紙"], "English", source_language="Japanese", context=JP_TEXT)

    def test_the_selection_dialog_marks_its_choice_as_the_users(
            self, tk_root, fake_dictionary_ui, main_window_popup, monkeypatch):
        monkeypatch.setattr(tk.Toplevel, 'grab_set', lambda self: None)
        monkeypatch.setattr('src.ui.dictionary_popup.nlp_manager.get_installed_languages',
                            lambda: ["Japanese", "Chinese (Simplified)"])
        opened = []
        monkeypatch.setattr(main_window_popup, '_open_with_language',
                            lambda *args, **kwargs: opened.append((args, kwargs)))
        main_window_popup._show_language_selection_dialog("勉強", "Japanese", parent=None)
        _invoke_button(tk_root, "Confirm")
        _pump(tk_root)
        assert opened == [(("勉強", "Japanese"), {'user_chosen': True})]


@pytest.fixture
def quick_popup(tk_root):
    from src.ui.quick_translate import QuickTranslateManager
    config = MagicMock()
    config.get_furigana_enabled.return_value = True
    mgr = QuickTranslateManager(tk_root, config)
    mgr._last_mouse_x, mgr._last_mouse_y = 500, 300
    mgr._current_target_lang = "English"
    mgr.calls = []
    mgr._on_dictionary_lookup = lambda *args, **kwargs: mgr.calls.append((args, kwargs))
    return mgr


class TestPopupWiring:
    def test_detected_japanese_and_the_text_reach_the_lookup(self, fake_dictionary_ui,
                                                            quick_popup):
        quick_popup._open_dictionary_with_language(JP_TEXT, "Japanese")
        fake_dictionary_ui.created[-1].kwargs['on_lookup'](["手紙"])
        assert quick_popup.calls == [((["手紙"], "English"),
                                      {'source_lang': "Japanese", 'context_text': JP_TEXT})]

    def test_detected_chinese_lets_the_model_decide(self, fake_dictionary_ui, quick_popup):
        quick_popup._open_dictionary_with_language("勉強", "Chinese (Simplified)")
        fake_dictionary_ui.created[-1].kwargs['on_lookup'](["勉強"])
        assert quick_popup.calls[0][1]['source_lang'] is None

    def test_a_language_the_user_picked_is_stated(self, fake_dictionary_ui, quick_popup):
        quick_popup._open_dictionary_with_language("勉強", "Chinese (Simplified)",
                                                   user_chosen=True)
        fake_dictionary_ui.created[-1].kwargs['on_lookup'](["勉強"])
        assert quick_popup.calls[0][1]['source_lang'] == "Chinese (Simplified)"

    def test_custom_box_phrases_carry_the_same_language(self, fake_dictionary_ui,
                                                        quick_popup):
        _FakeBoxes.phrases = ["手紙"]
        quick_popup._open_dictionary_with_language(JP_TEXT, "Japanese")
        fake_dictionary_ui.created[-1].kwargs['on_no_selection']()
        assert quick_popup.calls == [((["手紙"], "English"),
                                      {'source_lang': "Japanese", 'context_text': JP_TEXT})]

    def test_the_selection_dialog_marks_its_choice_as_the_users(
            self, tk_root, fake_dictionary_ui, quick_popup, monkeypatch):
        monkeypatch.setattr('src.ui.quick_translate.nlp_manager.get_installed_languages',
                            lambda: ["Japanese", "Chinese (Simplified)"])
        opened = []
        monkeypatch.setattr(quick_popup, '_open_dictionary_with_language',
                            lambda *args, **kwargs: opened.append((args, kwargs)))
        quick_popup._show_language_selection_dialog("勉強", "Japanese")
        _invoke_button(tk_root, "Confirm")
        _pump(tk_root)
        assert opened == [(("勉強", "Japanese", None), {'user_chosen': True})]

    def test_the_app_forwards_both_to_the_service(self, tk_root, monkeypatch):
        from src.app import TranslatorApp
        monkeypatch.setattr('threading.Thread', _SyncThread)
        app = TranslatorApp.__new__(TranslatorApp)
        app.root = tk_root
        app.toast = MagicMock()
        app.quick_translate_manager = MagicMock()
        app.translation_service = MagicMock()
        app.translation_service.dictionary_lookup.return_value = "## [手紙]"
        app.translation_service.get_trial_info.return_value = None
        app._on_quick_translate_dictionary_lookup(["手紙"], "English", source_lang="Japanese",
                                                  context_text=JP_TEXT)
        app.translation_service.dictionary_lookup.assert_called_once_with(
            ["手紙"], "English", source_language="Japanese", context=JP_TEXT)
        tk_root.update()


def _invoke_button(root, text):
    """Invoke the first button labelled `text` in any open window."""
    def walk(widget):
        for child in widget.winfo_children():
            try:
                if child.winfo_class() in ('TButton', 'Button') and child.cget('text') == text:
                    return child
            except tk.TclError:
                pass
            found = walk(child)
            if found is not None:
                return found
        return None

    button = walk(root)
    assert button is not None, f"no '{text}' button found"
    button.invoke()


def _pump(root, ms=300):
    """Run Tk's event loop long enough for an after(50) callback to fire."""
    deadline = time.time() + ms / 1000
    while time.time() < deadline:
        root.update()
        time.sleep(0.01)
