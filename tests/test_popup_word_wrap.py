"""Original and translation preserve whole words through native reflow."""
import re
import tkinter as tk
from tkinter import font

import pytest

from src.ui.quick_translate import QuickTranslateManager
from tests.test_popup_alignment import FakeConfig
from tools.popup_gallery import settle

PROSE = ('The translation preserves complete words across every line without changing '
         'the original content or adding any artificial line breaks. ' * 7).rstrip()


def split_words(box, plain):
    """Find words fitting the pane but broken across native display lines."""
    box.count('1.0', 'end', 'update', 'ypixels')
    starts, *_ = box.prepare_plain_map()
    measure = font.Font(font=box.cget('font')).measure
    available = box.winfo_width() - 2 * sum(int(box.cget(key)) for key in
                                          ('padx', 'borderwidth', 'highlightthickness'))
    broken = []
    for match in re.finditer(r'[A-Za-z]{3,}', plain):
        if measure(match.group()) > available:
            continue
        first = box.index(f'{starts[match.start()]} display linestart')
        last = box.index(f'{starts[match.end() - 1]} display linestart')
        if first != last:
            broken.append(match.group())
    return broken


@pytest.mark.parametrize('ruby', [False, True])
def test_popup_preserves_source_words_without_modifying_content(tk_root, ruby):
    manager = QuickTranslateManager(tk_root, FakeConfig(enabled=True, ruby=ruby))
    source = ('漢字 ' if ruby else '') + PROSE
    notation = '{漢字|かんじ} ' + PROSE if ruby else None
    manager._last_mouse_x, manager._last_mouse_y = 400, 300
    try:
        manager.show(PROSE, 'English', original=source, furigana_text=notation)
        settle(manager, tk_root, compose_s=0.01)
        assert manager.popup_furigana.get_plain() == source
        assert manager.popup_text.get_plain() == PROSE
        assert split_words(manager.popup_furigana, source) == []
        assert split_words(manager.popup_text, PROSE) == []
        assert manager.popup_furigana.ruby_pairs == int(ruby)

        # Reflow uses the same content offsets and linked-reading controller.
        controller = manager._linked_controller
        assert controller is not None
        controller.activate(0, 0)
        assert manager.popup_furigana.tag_ranges('linked_reading')
        assert manager.popup_text.tag_ranges('linked_reading')
        assert manager.popup_furigana.get_plain() == source
    finally:
        manager.close()


def test_show_all_and_resize_measure_actual_word_wrapped_height(tk_root):
    manager = QuickTranslateManager(tk_root, FakeConfig(enabled=False))
    try:
        manager.show(PROSE, 'English', original=PROSE)
        settle(manager, tk_root, compose_s=0.01)
        manager._toggle_original()
        settle(manager, tk_root, compose_s=0.01)
        for box, holder in ((manager.popup_furigana, manager._original_holder),
                            (manager.popup_text, manager._text_holder)):
            assert split_words(box, PROSE) == []
            assert manager._content_px(box) + manager._insets(box, 'y') <= holder.winfo_height()
        manager._toggle_original()
        settle(manager, tk_root, compose_s=0.01)
        manager._fit_boxes(size=(700, 500))
        tk_root.update()
        assert split_words(manager.popup_furigana, PROSE) == []
        assert manager.popup_furigana.get_plain() == PROSE
    finally:
        manager.close()


def test_long_unbroken_token_wraps_without_horizontal_overflow_or_data_loss(tk_root):
    manager = QuickTranslateManager(tk_root, FakeConfig(enabled=False))
    source = 'https://example.com/' + 'abcdefghij' * 100
    try:
        manager.show('A short result.', 'English', original=source)
        settle(manager, tk_root, compose_s=0.01)
        box = manager.popup_furigana
        assert str(box.cget('wrap')) == tk.WORD
        assert box.xview() == (0.0, 1.0)
        assert box.get_plain() == source
        assert manager._count(box, '1.0', 'end', 'update', 'displaylines') > 1
    finally:
        manager.close()
