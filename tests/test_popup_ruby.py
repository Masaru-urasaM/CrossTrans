"""
Integration tests for furigana in the Quick Translate popup (Phase F2).

These drive the real `QuickTranslateManager.show()` against a live Tk display, so
they cover the wiring the unit tests cannot: which language hint reaches the
engine, whether the Settings toggle is honored, that the custom-prompt box is
flattened before the user can type in it, and that Send transmits the whole text
rather than the kanji-stripped `get()` view.

Skipped automatically when no display is available (see the `tk_root` fixture).
"""
import tkinter as tk

import pytest

from src.core import furigana as F
from src.ui.quick_translate import QuickTranslateManager

HAS_PROVIDER = pytest.mark.skipif(
    not F.is_available(),
    reason="requires a reading provider (fugashi or pykakasi)"
)

JP_SENTENCE = "私は毎日日本語を勉強しています。"
JP_KANJI_ONLY = "東京都"          # no kana: indistinguishable from Chinese
EN_SENTENCE = "I study Japanese every day."


class FakeConfig:
    """Only the two getters the popup actually calls."""

    def __init__(self, furigana_enabled=True, quick_replace=False):
        self._furigana = furigana_enabled
        self._quick_replace = quick_replace

    def get_furigana_enabled(self):
        return self._furigana

    def get_quick_replace(self):
        return self._quick_replace


@pytest.fixture
def make_manager(tk_root):
    """Factory for a manager whose popups are closed on teardown."""
    created = []

    def _make(furigana_enabled=True):
        mgr = QuickTranslateManager(tk_root, FakeConfig(furigana_enabled))
        mgr._last_mouse_x, mgr._last_mouse_y = 500, 300
        created.append(mgr)
        return mgr

    yield _make
    for mgr in created:
        try:
            mgr.close()
        except Exception:
            pass


@pytest.fixture
def manager(make_manager):
    return make_manager()


@pytest.fixture(autouse=True)
def _clear_cache():
    """Annotation is memoized; keep tests independent."""
    F.clear_cache()
    yield
    F.clear_cache()


# --------------------------------------------------------------------------- #
# Which text gets readings
# --------------------------------------------------------------------------- #
class TestOutputAnnotation:
    @HAS_PROVIDER
    def test_japanese_translation_is_annotated(self, manager):
        manager.show(JP_SENTENCE, "Japanese", None, EN_SENTENCE)
        assert manager.popup_text.has_ruby is True
        assert manager.popup_text.get_plain() == JP_SENTENCE

    @HAS_PROVIDER
    def test_kanji_only_translation_uses_the_target_language(self, manager):
        # The Phase 0 coverage gap: no kana, so only the target language can
        # tell this apart from Chinese.
        manager.show(JP_KANJI_ONLY, "Japanese", None, "Tokyo Metropolis")
        assert manager.popup_text.has_ruby is True
        assert manager.popup_text.get_plain() == JP_KANJI_ONLY

    def test_kanji_only_with_a_chinese_target_stays_plain(self, manager):
        manager.show(JP_KANJI_ONLY, "Chinese (Simplified)", None, "Tokyo")
        assert manager.popup_text.has_ruby is False
        assert manager.popup_text.get_plain() == JP_KANJI_ONLY

    def test_latin_translation_is_untouched(self, manager):
        manager.show(EN_SENTENCE, "English", None, JP_SENTENCE)
        assert manager.popup_text.has_ruby is False
        assert manager.popup_text.get_plain() == EN_SENTENCE

    def test_error_text_is_never_annotated(self, manager):
        manager.show("Error: 日本語の失敗です", "Japanese", None, "x")
        assert manager.popup_text.has_ruby is False

    @HAS_PROVIDER
    def test_settings_toggle_off_disables_readings(self, make_manager):
        mgr = make_manager(furigana_enabled=False)
        mgr.show(JP_SENTENCE, "Japanese", None, EN_SENTENCE)
        assert mgr.popup_text.has_ruby is False
        assert mgr.popup_text.get_plain() == JP_SENTENCE

    @HAS_PROVIDER
    def test_grammar_result_annotates_on_its_own_evidence(self, manager):
        # "Grammar" is a label, not a language, so it must not act as a hint.
        # Text with kana still qualifies by itself.
        manager.show(JP_SENTENCE, "Grammar", None, JP_SENTENCE, is_grammar=True)
        assert manager.popup_text.has_ruby is True

    def test_grammar_result_does_not_guess_on_kanji_only(self, manager):
        manager.show(JP_KANJI_ONLY, "Grammar", None, JP_KANJI_ONLY,
                     is_grammar=True)
        assert manager.popup_text.has_ruby is False

    @HAS_PROVIDER
    def test_source_block_renders_from_the_notation(self, manager):
        notation = F.generate_notation(JP_SENTENCE, "Japanese")
        assert notation
        manager.show(EN_SENTENCE, "English", None, JP_SENTENCE,
                     furigana_text=notation)
        assert manager.popup_furigana is not None
        assert manager.popup_furigana.has_ruby is True
        assert manager.popup_furigana.get_plain() == JP_SENTENCE

    def test_no_source_block_without_a_notation(self, manager):
        manager.show(EN_SENTENCE, "English", None, "Bonjour")
        assert manager.popup_furigana is None


# --------------------------------------------------------------------------- #
# Reading the box back
# --------------------------------------------------------------------------- #
class TestCustomPrompt:
    @HAS_PROVIDER
    def test_send_transmits_the_whole_text(self, manager):
        # Without get_plain() the model would receive the annotated words
        # deleted - the failure this test exists to prevent.
        manager.show(JP_SENTENCE, "Japanese", None, EN_SENTENCE)
        assert manager.popup_text.has_ruby is True

        sent = []
        manager._on_custom_prompt_send = sent.append
        manager._enter_custom_prompt_mode()
        manager._handle_custom_prompt_send()
        assert sent == [JP_SENTENCE]

    @HAS_PROVIDER
    def test_entering_edit_mode_flattens_the_box(self, manager):
        # I3: an editable widget never holds ruby.
        manager.show(JP_SENTENCE, "Japanese", None, EN_SENTENCE)
        manager._enter_custom_prompt_mode()
        assert manager.popup_text.ruby_pairs == 0
        assert str(manager.popup_text.cget('state')) == 'normal'
        # After flattening, even a plain get() is complete.
        assert manager.popup_text.get('1.0', 'end-1c') == JP_SENTENCE

    @HAS_PROVIDER
    def test_appended_text_reaches_the_callback(self, manager):
        manager.show(JP_SENTENCE, "Japanese", None, EN_SENTENCE)
        sent = []
        manager._on_custom_prompt_send = sent.append
        manager._enter_custom_prompt_mode()
        manager.popup_text.insert(tk.END, " Explain this.")
        manager._handle_custom_prompt_send()
        assert sent == [JP_SENTENCE + " Explain this."]

    @HAS_PROVIDER
    def test_source_block_keeps_its_readings_in_edit_mode(self, manager):
        notation = F.generate_notation(JP_SENTENCE, "Japanese")
        manager.show(EN_SENTENCE, "English", None, JP_SENTENCE,
                     furigana_text=notation)
        manager._enter_custom_prompt_mode()
        assert manager.popup_furigana.has_ruby is True


class TestReplacePreview:
    @HAS_PROVIDER
    def test_preview_readback_is_exact(self, manager):
        manager.show(JP_SENTENCE, "Japanese", None, EN_SENTENCE)
        manager._show_replace_preview()
        expected = EN_SENTENCE + "\n\n→\n\n" + JP_SENTENCE
        assert manager.popup_text.get_plain() == expected

    @HAS_PROVIDER
    def test_preview_annotates_only_the_translation(self, manager):
        # Both halves hold the SAME Japanese text, so if the struck-through
        # original were annotated too the pair count would double. It must not:
        # Tk cannot strike through an embedded frame.
        manager.show(JP_SENTENCE, "Japanese", None, JP_SENTENCE)
        translation_pairs = manager.popup_text.ruby_pairs
        assert translation_pairs > 0

        manager._show_replace_preview()
        assert manager.popup_text.ruby_pairs == translation_pairs

        plain_half, _, ruby_half = manager.popup_text.get_plain().partition(
            "\n\n→\n\n")
        assert plain_half == JP_SENTENCE
        assert ruby_half == JP_SENTENCE

    @HAS_PROVIDER
    def test_preview_base_colour_matches_the_surrounding_text(self, manager):
        manager.show(JP_SENTENCE, "Japanese", None, EN_SENTENCE)
        manager._show_replace_preview()
        expected = str(manager.popup_text.tag_cget('translated', 'foreground'))
        for frame in manager.popup_text._frames:
            _reading, base = frame.winfo_children()
            assert str(base.cget('fg')) == expected

    @HAS_PROVIDER
    def test_preview_is_not_clipped(self, manager, tk_root):
        manager.show(JP_SENTENCE, "Japanese", None, EN_SENTENCE)
        manager._show_replace_preview()
        tk_root.update_idletasks()
        tk_root.update()
        content = manager.popup_text.count('1.0', 'end', 'ypixels')
        if not content:
            pytest.skip("Tk reported no laid-out pixels")
        assert manager.popup_text.winfo_height() >= content[0]


class TestPopupSizing:
    @staticmethod
    def _popup_height(mgr, tk_root):
        # geometry() reports 1x1 until the request has been processed.
        tk_root.update_idletasks()
        return int(mgr.popup.geometry().split('+')[0].split('x')[1])

    @HAS_PROVIDER
    def test_popup_is_taller_with_readings(self, make_manager, tk_root):
        on, off = make_manager(True), make_manager(False)
        on.show(JP_SENTENCE, "Japanese", None, EN_SENTENCE)
        off.show(JP_SENTENCE, "Japanese", None, EN_SENTENCE)
        assert (self._popup_height(on, tk_root)
                > self._popup_height(off, tk_root))

    @HAS_PROVIDER
    def test_translation_box_is_not_clipped(self, manager, tk_root):
        manager.show(JP_SENTENCE * 3, "Japanese", None, EN_SENTENCE)
        tk_root.update_idletasks()
        tk_root.update()
        content = manager.popup_text.count('1.0', 'end', 'ypixels')
        if not content:
            pytest.skip("Tk reported no laid-out pixels")
        assert manager.popup_text.winfo_height() >= content[0]
