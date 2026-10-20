"""Cache redo, old History, editable source, and two-pane expansion regressions."""
import json
import queue
import time
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.core.translation_alignment import AlignedText, structural_alignment, validate_metadata
from src.ui.main_linked_reading import MainLinkedReading
from src.ui.ruby_text import RubyText
from src.ui import popup_layout, quick_translate
from tests.test_alignment_service import make_service, SOURCE, RAW
from tests.test_popup_alignment import FakeConfig, result, settle


def test_redo_updates_the_same_hotkey_cache_namespace():
    service = make_service()
    old = service.translate_or_fix(SOURCE, 'English')
    service._configure_api = Mock(return_value=True)
    service.config.get_furigana_enabled = lambda: False
    service.get_trial_info = Mock(return_value=None)
    service.translation_queue = queue.Queue()
    service._call_model.return_value = RAW.replace('One.', 'New first.')
    service.redo_translation(SOURCE, 'English', mode=old.alignment['mode'])
    fresh = service.translation_queue.get()[1]
    service.config.data = json.loads(json.dumps(service.config.data))
    cached = service.translate_or_fix(SOURCE, 'English')
    assert cached == fresh == 'New first. Two.'
    assert cached.alignment == fresh.alignment
    assert service._call_model.call_count == 2
    assert service.history_manager.find_cached_entry(SOURCE, 'English') is None


def test_source_choice_redo_preserves_merged_cache_and_known_language():
    service = make_service()
    service.translate_or_fix(SOURCE, 'English')
    service._configure_api = Mock(return_value=True)
    service.config.get_furigana_enabled = lambda: False
    service.get_trial_info = Mock(return_value=None)
    service.translation_queue = queue.Queue()
    service._call_model.return_value = RAW.replace('One.', 'Chosen first.')
    service.redo_translation(SOURCE, 'English', source_language='Japanese', mode='merged')
    value = service.translation_queue.get()[1]
    assert value == 'Chosen first. Two.' and value.alignment['mode'] == 'merged'
    assert service.last_source_language == 'Japanese'
    assert service.translate_or_fix(SOURCE, 'English') == value
    assert service._call_model.call_count == 2


def test_plain_cached_translation_keeps_metadata_without_request_permission():
    service = make_service()
    live = service.translate_text(SOURCE, 'English', allow_linked=True)
    service.config.data['linked_reading_enabled'] = False
    cached = service.translate_text(SOURCE, 'English')
    assert cached.alignment == live.alignment
    service._call_model.assert_called_once()


def test_app_retranslate_forwards_original_mode_before_loading(monkeypatch):
    from src.app import TranslatorApp
    app = TranslatorApp.__new__(TranslatorApp)
    app.current_original, app.current_target_lang = SOURCE, 'English'
    app.current_translated = result()
    app.translation_service = Mock()
    app.quick_translate_manager = Mock()
    app.root = Mock()
    monkeypatch.setattr('src.app.threading.Thread', lambda target, **kw: SimpleNamespace(start=target))
    app._on_quick_translate_retranslate()
    app.translation_service.redo_translation.assert_called_once_with(SOURCE, 'English', mode='merged')


@pytest.mark.parametrize('source,target,count', [
    ('First. Second.', 'One. Two.', 2),
    ('First. Second.\nThird.', 'One combined.\nThree.', 2),
    ('  First.\r\n\r\nSecond.  ', '  One.\r\n\r\nTwo.  ', 2),
    ('A\U0001f642. Next.', '一つ。次です。', 2),
])
def test_legacy_structural_links_are_lossless_coarse_and_explicit(source, target, count):
    data = structural_alignment(source, target, 'English')
    assert validate_metadata(data, source, target, 'English') is data
    assert data['method'] == 'structure' and len(data['groups']) == count
    assert ''.join(source[a:b] for a, b in (g['source'] for g in data['groups'])) == source
    assert ''.join(target[a:b] for a, b in (g['translated'] for g in data['groups'])) == target


def test_legacy_history_backfills_locally_and_survives_restart():
    service = make_service()
    service.history_manager.add_entry(SOURCE, 'One. Two.', 'English')
    entry = service.history_manager.get_history()[0]
    value = service.history_manager.reading_result(entry)
    assert isinstance(value, AlignedText) and value.alignment['method'] == 'structure'
    service.config.data = json.loads(json.dumps(service.config.data))
    loaded = service.history_manager.reading_result(service.history_manager.get_history()[0])
    assert loaded.alignment == value.alignment
    service._call_model.assert_not_called()


@pytest.fixture
def main_pair(tk_root):
    top = tk.Toplevel(tk_root)
    top.geometry('700x420+20+20')
    source = tk.Text(top, height=4, undo=True, wrap='word')
    source.pack(fill='x')
    source.insert('1.0', SOURCE)
    source.edit_modified(False)
    translated = RubyText(top, height=4)
    translated.pack(fill='both', expand=True)
    value = result()
    translated.set_plain(value)
    translated.configure(state='disabled')
    bar = tk.Frame(top)
    bar.pack(fill='x')
    config = FakeConfig()
    reading = MainLinkedReading(tk_root, top, source, translated, config, bar)
    reading.set_result(value, SOURCE, 'English')
    settle(tk_root)
    yield reading, source, translated, value, top
    if top.winfo_exists():
        top.destroy()
    settle(tk_root)


def test_main_window_hover_both_directions_and_no_ruby_in_editable_input(main_pair, tk_root):
    reading, source, translated, value, _ = main_pair
    assert not isinstance(source, RubyText)
    reading.controller.activate(0, 1)
    assert source.get(*source.tag_ranges('linked_reading')) == 'Second.'
    assert translated.get_plain(*translated.tag_ranges('linked_reading')) == 'Result 2.'
    reading.controller.activate(1, 0)
    assert source.get(*source.tag_ranges('linked_reading')) == 'First.'
    assert source.get('1.0', 'end-1c') == SOURCE


def test_edit_and_undo_invalidate_then_restore_main_links(main_pair, tk_root):
    reading, source, _, _, _ = main_pair
    controller = reading.controller
    source.edit_separator()
    source.insert('end', ' Changed.')
    settle(tk_root)
    assert controller.closed and reading.controller is None
    assert not source.tag_ranges('linked_reading')
    source.edit_undo()
    settle(tk_root)
    assert reading.controller is not None
    assert source.get('1.0', 'end-1c') == SOURCE


def test_main_toggle_settings_sync_and_close_cleanup(main_pair, tk_root):
    reading, _, _, _, top = main_pair
    reading.button.invoke()
    settle(tk_root)
    assert reading.controller is None and reading.config.enabled is False
    reading.config.enabled = True
    tk_root.event_generate('<<LinkedReadingChanged>>', when='tail')
    settle(tk_root)
    assert reading.controller is not None
    top.destroy()
    settle(tk_root)
    assert reading.closed and reading.controller is None


def test_main_rejects_result_for_a_different_input_snapshot(main_pair, tk_root):
    reading, source, _, value, _ = main_pair
    source.insert('end', ' Changed.')
    reading.set_result(value, SOURCE, 'English')
    settle(tk_root)
    assert reading.controller is None


@pytest.mark.parametrize('padding', ['\n', '  ', '\r\n\t'])
def test_main_rebases_outer_whitespace_without_rewriting_input(main_pair, tk_root, padding):
    reading, source, _, value, _ = main_pair
    source.delete('1.0', 'end')
    source.insert('1.0', padding + SOURCE + padding)
    reading.set_result(value, SOURCE, 'English')
    settle(tk_root)
    assert reading.controller is not None
    assert source.get('1.0', 'end-1c') == padding + SOURCE + padding
    assert not reading.result.alignment.get('method')
    assert validate_metadata(reading.result.alignment, reading.source_snapshot, value, 'English')


def test_history_load_restores_the_carrier_into_main_window(main_pair, tk_root):
    from src.app import TranslatorApp
    reading, source, translated, _, top = main_pair
    service = make_service()
    saved = service.translate_or_fix(SOURCE, 'English')
    app = TranslatorApp.__new__(TranslatorApp)
    app.popup, app.root = top, tk_root
    app.original_text, app.trans_text = source, translated
    app._main_linked, app.translation_service = reading, service
    app.selected_language, app.config = 'English', FakeConfig()
    app._select_language_in_list = lambda value: setattr(app, 'selected_language', value)
    app._stop_translate_animation = lambda: None
    app._update_popup_title_with_trial = lambda: None
    app.translate_btn = Mock()
    app._load_history_item(service.history_manager.get_history()[0])
    settle(tk_root)
    assert reading.result.alignment == saved.alignment and reading.controller is not None
    service._call_model.assert_called_once()


def test_expansion_allocator_grows_both_panes_and_returns_short_pane_room():
    heights = popup_layout.allocate_expanded(800, 900, 900, min_translation=60, min_original=60)
    assert heights.translation == heights.original == 400
    heights = popup_layout.allocate_expanded(800, 50, 2000, min_translation=50, min_original=60)
    assert heights.translation == 50 and heights.original == 750


def test_expansion_search_prefers_smallest_fit_and_bounds_unreadable_lines():
    measured = [(500, 700, 700), (650, 450, 450), (850, 300, 300), (1700, 200, 200)]
    assert popup_layout.choose_expansion(measured, 900, 100, 850) == (850, 700)
    assert popup_layout.choose_expansion(measured, 300, 100, 850) == (850, 300)


def test_popup_expands_both_panes_and_restores_exact_compact_geometry(tk_root, monkeypatch):
    monkeypatch.setattr(quick_translate, 'get_monitor_work_area', lambda *a: (0, 0, 1280, 1000))
    manager = quick_translate.QuickTranslateManager(tk_root, FakeConfig(enabled=False))
    source = '\n'.join('Check the original settings carefully before continuing to the next operation.' for _ in range(20))
    translated = '\n'.join('Review the translated document carefully before continuing to the next operation.' for _ in range(20))
    try:
        manager.show(translated, 'English', original=source)
        settle(tk_root)
        before = manager.popup.winfo_width(), manager.popup.winfo_height(), manager.popup.winfo_x(), manager.popup.winfo_y()
        original_h, target_h = manager.popup_furigana.winfo_height(), manager.popup_text.winfo_height()
        old_target_need = manager._content_px(manager.popup_text)
        manager._toggle_original()
        settle(tk_root)
        assert manager.popup_furigana.winfo_height() > original_h
        # Wider wrapping can use fewer pixels while revealing more of the text.
        assert manager.popup_text.winfo_height() / manager._content_px(manager.popup_text) > target_h / old_target_need
        assert manager.popup.winfo_width() > before[0]
        assert manager.popup.winfo_x() >= 10 and manager.popup.winfo_y() >= 10
        assert manager.popup.winfo_x() + manager.popup.winfo_width() <= 1270
        assert manager.popup.winfo_y() + manager.popup.winfo_height() <= 990
        assert manager.popup_original_toggle.cget('text') == 'Show less'
        manager._toggle_original()
        settle(tk_root)
        assert (manager.popup.winfo_width(), manager.popup.winfo_height(), manager.popup.winfo_x(), manager.popup.winfo_y()) == before
    finally:
        manager.close()


def test_long_translation_exposes_show_all_even_with_a_short_original(tk_root):
    manager = quick_translate.QuickTranslateManager(tk_root, FakeConfig(enabled=False))
    try:
        manager.show('\n'.join('Translated paragraph.' for _ in range(70)), 'English', original='Short source.')
        settle(tk_root)
        assert manager.popup_original_toggle.winfo_ismapped()
        button = manager.popup_open_btn
        assert button.pack_info()['side'] == 'right'
        assert button.winfo_x() + button.winfo_width() == manager._btn_frame.winfo_width()
        assert all(child.winfo_x() + child.winfo_width() <= button.winfo_x() - 12
                   for child in manager._btn_frame.winfo_children() if child is not button)
    finally:
        manager.close()
