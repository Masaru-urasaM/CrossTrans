"""Exercise the real popup's linked-reading lifecycle on the private desktop."""
import json
from types import SimpleNamespace
import time
from unittest.mock import Mock

import pytest

from src.core.translation_alignment import AlignedText, make_metadata, parse_answer, segment_source
from src.ui.quick_translate import QuickTranslateManager
from src.ui import linked_reading


class FakeConfig:
    def __init__(self, enabled=True, ruby=False):
        self.enabled = enabled
        self.ruby = ruby

    def get_linked_reading_enabled(self):
        return self.enabled

    def set_linked_reading_enabled(self, enabled):
        self.enabled = enabled

    def get_furigana_enabled(self):
        return self.ruby

    def get_quick_replace(self):
        return False


def result(source='First. Second.', translated=None, target='English'):
    units = segment_source(source)
    rows = [{'source_ids': [u.id], 'text': translated or f'Result {u.id}.'} for u in units]
    parsed = parse_answer(json.dumps({'version': 1, 'segments': rows}), source, target)
    return AlignedText(parsed.text, parsed.metadata)


def settle(root):
    root.update()
    time.sleep(0.015)
    root.update()


@pytest.fixture
def manager(tk_root, monkeypatch):
    monkeypatch.setattr(linked_reading, 'LINKED_READING_DELAY_MS', 1)
    mgr = QuickTranslateManager(tk_root, FakeConfig())
    yield mgr
    mgr.close()
    settle(tk_root)


def show(manager, root, source='First. Second.', translated=None, target='English'):
    value = result(source, translated, target)
    manager.show(value, target, original=source)
    settle(root)
    return value, manager._linked_controller


def hit(box, offset):
    starts, *_ = box.prepare_plain_map()
    x, y, width, height = box.bbox(starts[offset])
    return box.winfo_rootx() + x + 1, box.winfo_rooty() + y + height // 2


def test_original_without_furigana_and_hover_both_directions(manager, tk_root):
    value, controller = show(manager, tk_root)
    assert manager.popup_furigana.get_plain() == 'First. Second.'
    controller.motion(0, *hit(manager.popup_furigana, 0))
    settle(tk_root)
    assert controller.active == (0, 0)
    assert manager.popup_text.tag_ranges('linked_reading')
    group = value.alignment['groups'][1]
    controller.motion(1, *hit(manager.popup_text, group['translated'][0]))
    settle(tk_root)
    assert controller.active == (1, 1)
    assert manager.popup_furigana.tag_ranges('linked_reading')
    assert manager.popup_furigana.get_plain(*manager.popup_furigana.tag_ranges('linked_reading')) == 'Second.'
    assert manager.popup_text.get_plain() == value


@pytest.mark.parametrize('ruby', [True, False])
def test_original_is_visible_with_linking_off_and_japanese_output(manager, tk_root, ruby):
    manager.config.enabled = False
    manager.config.ruby = ruby
    source = 'Select Quit to close the old version.\nRun the test EXE.'
    translated = '古いバージョンを終了してください。\nテスト版を実行してください。'
    manager.show(translated, 'Japanese', original=source, source_lang='English')
    settle(tk_root)
    assert manager.popup_furigana is not None
    assert manager.popup_furigana.winfo_ismapped()
    assert manager.popup_furigana.get_plain() == source
    assert not manager.popup_furigana.has_ruby
    assert manager.popup_text.get_plain() == translated
    assert manager.popup_text.has_ruby is ruby
    assert getattr(manager, '_linked_controller', None) is None
    assert manager.config.enabled is False


def test_debounce_and_close_cancel_pending_work(manager, tk_root):
    value, controller = show(manager, tk_root)
    controller.motion(0, *hit(manager.popup_furigana, 0))
    first_timer = controller.timer
    controller.motion(0, *hit(manager.popup_furigana, 7))
    assert controller.timer != first_timer
    manager.close()
    settle(tk_root)
    assert controller.closed and controller.timer is None


def test_external_destroy_before_timer_does_not_raise(manager, tk_root):
    value, controller = show(manager, tk_root)
    controller.motion(0, *hit(manager.popup_furigana, 0))
    manager.popup.destroy()
    settle(tk_root)
    assert controller.closed and controller.timer is None


def test_pointer_recovers_after_release_outside_the_box(manager, tk_root):
    value, controller = show(manager, tk_root)
    controller.press()
    controller.motion(0, *hit(manager.popup_furigana, 0), state=0)
    settle(tk_root)
    assert not controller.dragging and controller.active == (0, 0)


def test_error_and_unsupported_results_never_reuse_old_map(manager, tk_root):
    value, controller = show(manager, tk_root)
    manager.show('Error: failed', 'English', original='First. Second.')
    settle(tk_root)
    assert controller.closed and manager._linked_controller is None
    manager.show('Plain answer.', 'English', original='Other source.')
    settle(tk_root)
    assert manager._linked_controller is not None
    assert manager._current_alignment['method'] == 'structure'
    assert manager._current_alignment['source_hash'] != value.alignment['source_hash']


def test_corrupt_metadata_and_off_setting_do_not_link(manager, tk_root):
    value = result()
    value.alignment['target_hash'] = 'bad'
    manager.show(value, 'English', original='First. Second.')
    assert manager._current_alignment['method'] == 'structure'
    manager.config.enabled = False
    manager.show(result(), 'English', original='First. Second.')
    assert manager.popup_furigana is not None
    assert manager.popup_furigana.get_plain() == 'First. Second.'
    assert getattr(manager, '_linked_controller', None) is None


def test_settings_checkbox_really_persists_the_opt_in(tk_root):
    import tkinter as tk
    from config import Config
    from src.ui.settings.hotkey_tab import HotkeyTabMixin
    cfg = Config.__new__(Config)
    cfg._config = {}
    cfg.save = Mock()
    tab = HotkeyTabMixin()
    tab.config = cfg
    window = tk.Toplevel(tk_root)
    try:
        tab._create_linked_reading_section(window)
        button = next(child for child in window.winfo_children()
                      if child.winfo_class() == 'TCheckbutton')
        assert cfg.get_linked_reading_enabled() is False
        button.invoke()
        assert cfg.get_linked_reading_enabled() is True
        button.invoke()
        assert cfg.get_linked_reading_enabled() is False
        assert cfg.save.call_count == 2
    finally:
        window.destroy()


def test_toolbar_toggle_restores_existing_links_without_retranslation(manager, tk_root):
    value, controller = show(manager, tk_root)
    manager.config.set_linked_reading_enabled = Mock(
        side_effect=manager.config.set_linked_reading_enabled)
    manager._on_re_translate = Mock(side_effect=AssertionError('Toggle called the API path'))
    button = manager.popup_linked_btn
    assert button.winfo_ismapped() and button.action_name == 'Linked reading'
    assert manager._linked_tooltip.text.startswith('Linked reading: On.')
    button.invoke()
    settle(tk_root)
    assert controller.closed and manager._linked_controller is None
    assert manager._linked_tooltip.text.startswith('Linked reading: Off.')
    button.invoke()
    settle(tk_root)
    assert manager._linked_controller is not None
    assert manager._linked_controller is not controller
    assert manager.config.set_linked_reading_enabled.call_count == 2
    assert manager.popup_text.get_plain() == value
    manager._on_re_translate.assert_not_called()


def test_enabling_legacy_result_uses_approximate_links_without_retranslate(manager, tk_root):
    manager.config.enabled = False
    manager._on_re_translate = Mock()
    manager.show('Plain result.', 'English', original='Plain source.')
    settle(tk_root)
    manager.popup_linked_btn.invoke()
    settle(tk_root)
    assert manager.config.enabled is True and manager._linked_controller is not None
    assert manager._linked_status.cget('text') == 'Approximate links'
    manager._on_re_translate.assert_not_called()


def test_popup_and_open_settings_share_the_same_toggle(manager, tk_root):
    import tkinter as tk
    from src.ui.settings.hotkey_tab import HotkeyTabMixin
    value, controller = show(manager, tk_root)
    tab = HotkeyTabMixin()
    tab.config = manager.config
    window = tk.Toplevel(tk_root)
    try:
        tab._create_linked_reading_section(window)
        checkbox = next(child for child in window.winfo_children()
                        if child.winfo_class() == 'TCheckbutton')
        manager.popup_linked_btn.invoke()
        settle(tk_root)
        assert tab.linked_reading_var.get() is False
        checkbox.invoke()
        settle(tk_root)
        assert manager._linked_tooltip.text.startswith('Linked reading: On.')
        assert manager._linked_controller is not None
    finally:
        window.destroy()


@pytest.mark.parametrize('mode', ['edit', 'preview'])
def test_settings_changes_do_not_restart_links_in_edit_or_preview(manager, tk_root, mode):
    show(manager, tk_root)
    if mode == 'edit':
        manager._enter_custom_prompt_mode()
    else:
        manager._show_replace_preview()
    manager.config.enabled = False
    manager.root.event_generate('<<LinkedReadingChanged>>', when='tail')
    settle(tk_root)
    manager.config.enabled = True
    manager.root.event_generate('<<LinkedReadingChanged>>', when='tail')
    settle(tk_root)
    assert manager._linked_controller is None


def test_external_popup_destroy_releases_setting_binding(manager, tk_root):
    show(manager, tk_root)
    assert manager._linked_setting_binding is not None
    manager.popup.destroy()
    settle(tk_root)
    assert manager._linked_setting_binding is None
    manager.root.event_generate('<<LinkedReadingChanged>>', when='tail')
    settle(tk_root)


def test_custom_edit_flattens_and_cancel_restores_exact_pair(manager, tk_root):
    value, controller = show(manager, tk_root)
    manager._enter_custom_prompt_mode()
    assert controller.closed and manager._linked_controller is None
    manager.popup_text.insert('end', ' Changed.')
    manager._handle_custom_prompt_cancel()
    settle(tk_root)
    assert manager._linked_controller is not None
    assert manager.popup_text.get_plain() == value


def test_replace_preview_suspends_links_and_preserves_text(manager, tk_root):
    value, controller = show(manager, tk_root)
    manager._show_replace_preview()
    assert controller.closed and manager._linked_controller is None
    assert value in manager.popup_text.get_plain()
    assert 'First. Second.' in manager.popup_text.get_plain()


def test_selection_and_resizing_suspend_hover(manager, tk_root):
    value, controller = show(manager, tk_root)
    controller.press()
    controller.motion(0, *hit(manager.popup_furigana, 0))
    assert controller.timer is None and controller.active is None
    controller.release()
    manager._grip_start = {'pointer': (0, 0)}
    controller.motion(0, *hit(manager.popup_furigana, 0))
    assert controller.timer is None
    manager._grip_start = None
    controller.motion(0, *hit(manager.popup_furigana, 0))
    settle(tk_root)
    assert controller.active == (0, 0)


def test_furigana_labels_have_live_hover_bindings(manager, tk_root):
    manager.config.ruby = True
    value, controller = show(manager, tk_root, '私は毎日日本語を勉強します。次です。')
    assert manager.popup_furigana.has_ruby
    for part in manager.popup_furigana.linked_event_parts():
        assert part.bind('<Motion>')
    frame = manager.popup_furigana._frames[0]
    controller.motion(0, frame.winfo_rootx() + 2, frame.winfo_rooty() + 2)
    settle(tk_root)
    assert controller.active == (0, 0)


def test_scrollbar_hooks_survive_refit_and_restore_on_close(manager, tk_root):
    source = '\n'.join(f'Line {i}.' for i in range(60))
    value, controller = show(manager, tk_root, source)
    manager._toggle_original()
    settle(tk_root)
    for box in controller.boxes:
        assert str(box.cget('yscrollcommand')) == controller.scrolls[box]['command']
    controller.close()
    assert controller.closed


def test_counterpart_scroll_does_not_scroll_reading_box_or_expand_original(manager, tk_root):
    source = '\n'.join(f'Line {i}.' for i in range(60))
    value, controller = show(manager, tk_root, source)
    before = manager.popup_text.yview()
    controller.activate(1, 50)
    settle(tk_root)
    assert manager.popup_text.yview() == before
    assert manager.popup_furigana.yview()[0] > 0
    assert manager._original_collapsed
    assert controller.active == (1, 50)


def test_wheel_over_stationary_pointer_refreshes_owner_not_counterpart(manager, tk_root):
    source = '\n'.join(f'Line {i}.' for i in range(60))
    value, controller = show(manager, tk_root, source)
    controller.motion(0, *hit(manager.popup_furigana, 0))
    settle(tk_root)
    manager.popup_furigana.yview_scroll(5, 'units')
    settle(tk_root)
    settle(tk_root)
    assert controller.active is not None and controller.active[1] > 0


@pytest.mark.parametrize('length', [3000, 10000, 50000])
def test_large_display_pair_uses_cached_map_without_layout_on_hover(manager, tk_root, length):
    paragraph = 'Alpha sentence. ' * 8 + '\n\n'
    target_paragraph = 'Beta sentence. ' * 8 + '\n\n'
    source = (paragraph * (length // len(paragraph) + 1))[:length]
    translated = (target_paragraph * (length // len(target_paragraph) + 1))[:length]
    data = make_metadata(source, translated, 'English', 'text', [
        {'source': [0, length], 'translated': [0, length]}])
    manager.show(AlignedText(translated, data), 'English', original=source)
    settle(tk_root)
    controller = manager._linked_controller
    manager._fit_boxes = Mock(side_effect=AssertionError('Hover re-laid out popup'))
    controller.activate(0, 0)
    settle(tk_root)
    assert manager.popup_text.get_plain() == translated
    manager._fit_boxes.assert_not_called()
