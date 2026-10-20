"""Deadlines, replacement and out-of-order completions must preserve the newest intent."""
import json
import queue
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock
import urllib.error

import pytest

import src.core
from src.app import TranslatorApp
from src.constants import TRANSLATION_TIMEOUT_SECONDS
from src.core.api_manager import AIAPIManager
from src.core.translation_task import (TranslationCancelled, TranslationQueue, TranslationTasks,
                                       TranslationTimedOut, bounded_io)
from src.ui.quick_translate import QuickTranslateManager
from src.ui.translation_tasks import TranslationTaskRunner
from src.ui.screenshot_handler import ScreenshotHandler
from tests.test_alignment_service import make_service
from tests.test_popup_alignment import FakeConfig
from tests.test_source_choice import main_window


def pump(root, duration=0.15):
    end = time.monotonic() + duration
    while time.monotonic() < end:
        root.update()
        time.sleep(0.005)


def response():
    result = Mock()
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    result.read.return_value = json.dumps({'choices': [
        {'finish_reason': 'stop', 'message': {'content': 'Complete.'}}]}).encode()
    return result


def test_default_is_a_twenty_second_whole_request_budget():
    start = time.monotonic()
    task = TranslationTasks().begin()
    assert TRANSLATION_TIMEOUT_SECONDS == 20
    assert 19.9 <= task.deadline - start <= 20.1


def test_blocked_transport_stops_waiting_at_deadline():
    release = threading.Event()
    task = TranslationTasks().begin(timeout=0.06)
    start = time.monotonic()
    try:
        with task.activate(), pytest.raises(TranslationTimedOut):
            bounded_io(lambda: release.wait(1))
        assert time.monotonic() - start < 0.4
    finally:
        release.set()


def test_replacement_releases_old_waiter_without_waiting_for_old_http():
    tasks = TranslationTasks()
    old = tasks.begin()
    entered, release = threading.Event(), threading.Event()
    failures = []

    def work():
        try:
            with old.activate():
                bounded_io(lambda: (entered.set(), release.wait(1)))
        except Exception as error:
            failures.append(error)

    thread = threading.Thread(target=work)
    thread.start()
    try:
        assert entered.wait(0.5)
        newest = tasks.begin()
        thread.join(0.3)
        assert not thread.is_alive()
        assert isinstance(failures[0], TranslationCancelled)
        assert newest.is_current()
    finally:
        release.set()
        thread.join(1)


def test_deadline_covers_retry_delay_and_prevents_rotation(monkeypatch):
    api = AIAPIManager()
    api.configure([{'model_name': 'openai/gpt-oss-120b', 'provider': 'Groq', 'api_key': 'test-key'}])
    request = Mock(side_effect=urllib.error.HTTPError('https://api.groq.com', 500, 'busy', {}, None))
    monkeypatch.setattr('urllib.request.urlopen', request)
    api._try_model_rotation = Mock(side_effect=AssertionError('Deadline must not rotate'))
    task = TranslationTasks().begin(timeout=0.5)

    def elapse(seconds):
        task.deadline -= seconds
        task.check()

    monkeypatch.setattr('src.core.api_manager.pause', elapse)
    with task.activate(), pytest.raises(TranslationTimedOut):
        api.translate('Translate everything.')
    request.assert_called_once()
    api._try_model_rotation.assert_not_called()


def test_late_service_result_cannot_enter_history_or_queue():
    service = make_service(enabled=False)
    service.translation_queue = TranslationQueue()
    tasks = TranslationTasks()
    old = tasks.begin()
    entered, release = threading.Event(), threading.Event()

    def model(prompt):
        if 'Old input.' in prompt:
            entered.set()
            release.wait(1)
            return 'Late output.'
        return 'Current output.'

    service._call_model.side_effect = model

    def work():
        with old.activate():
            text = service.translate_or_fix('Old input.', 'English')
            service.translation_queue.put(('Old input.', text, 'English', None))

    thread = threading.Thread(target=work)
    thread.start()
    try:
        assert entered.wait(0.5)
        newest = tasks.begin()
        with newest.activate():
            service.translate_or_fix('New input.', 'English')
        release.set()
        thread.join(0.5)
        assert not thread.is_alive()
        assert [item['original'] for item in service.history_manager.get_history()] == ['New input.']
        assert service.translation_queue.empty()
    finally:
        release.set()
        thread.join(1)


def test_queued_old_result_is_discarded_and_credit_belongs_to_new_result():
    tasks = TranslationTasks()
    results = TranslationQueue()
    old = tasks.begin()
    old.attribution = 'old-model (Test)'
    with old.activate():
        results.put(('Old.', 'Old output.', 'English', None, None))
    newest = tasks.begin()
    newest.attribution = 'new-model (Test)'
    with newest.activate():
        results.put(('New.', 'New output.', 'English', None, None))
    app = TranslatorApp.__new__(TranslatorApp)
    app.translation_service = SimpleNamespace(translation_queue=results, last_attribution='wrong-model')
    app.root = SimpleNamespace(winfo_exists=lambda: False)
    app.running = True
    app.show_quick_translate = Mock()
    app._check_queue()
    app.show_quick_translate.assert_called_once_with(
        'New.', 'New output.', 'English', None, None, is_grammar=False, model_info='new-model (Test)')


def test_api_cancellation_does_not_retry_or_replace_credit(monkeypatch):
    api = AIAPIManager()
    api.configure([{'model_name': 'openai/gpt-oss-120b', 'provider': 'Groq', 'api_key': 'test-key'}])
    api.last_model, api.last_provider = 'previous', 'Test'
    tasks = TranslationTasks()
    old = tasks.begin()
    result = response()
    entered, release = threading.Event(), threading.Event()
    result.read.side_effect = lambda: (entered.set(), release.wait(1), b'{}')[-1]
    request = Mock(return_value=result)
    monkeypatch.setattr('urllib.request.urlopen', request)
    failures = []

    def work():
        try:
            with old.activate():
                api.translate('Old request.')
        except Exception as error:
            failures.append(error)

    thread = threading.Thread(target=work)
    thread.start()
    try:
        assert entered.wait(0.5)
        tasks.begin()
        thread.join(0.3)
        assert not thread.is_alive()
        assert isinstance(failures[0], TranslationCancelled)
        request.assert_called_once()
        assert api.last_attribution == 'previous (Test)'
    finally:
        release.set()
        thread.join(1)


def test_runner_timeout_is_delivered_on_ui_thread_and_late_answer_ignored(tk_root, monkeypatch):
    runner = TranslationTaskRunner(tk_root)
    original_begin = runner.tasks.begin
    monkeypatch.setattr(runner.tasks, 'begin', lambda: original_begin(timeout=0.05))
    release = threading.Event()
    finished, errors, cancelled = [], [], []
    try:
        runner.start(lambda: release.wait(1), on_result=finished.append,
                     on_error=lambda error: errors.append((error, threading.current_thread())),
                     on_cancel=lambda: cancelled.append(True))
        pump(tk_root)
        assert len(errors) == 1 and isinstance(errors[0][0], TranslationTimedOut)
        assert errors[0][1] is threading.main_thread()
        assert cancelled == [True]
        release.set()
        pump(tk_root, 0.05)
        assert finished == [] and len(errors) == 1
    finally:
        release.set()
        runner.cancel()


def test_loading_close_cancels_and_dismisses(tk_root):
    manager = QuickTranslateManager(tk_root, FakeConfig())
    dismissed = []
    manager.configure_callbacks(on_dismiss=lambda: dismissed.append(True))
    try:
        manager.show_loading('English')
        manager.dismiss()
        assert dismissed == [True] and not manager.is_open
    finally:
        manager.close()


def test_main_input_replacement_keeps_new_result_when_old_finishes_last(main_window):
    app = main_window('Old input.', furigana=False)
    entered, release = threading.Event(), threading.Event()

    def translate(text, *args, **kwargs):
        if text == 'Old input.':
            entered.set()
            release.wait(1)
            return 'Late output.'
        return 'Current output.'

    app.translation_service.translate_text = translate
    try:
        app._do_retranslate()
        assert entered.wait(0.5)
        assert str(app.translate_btn.cget('state')) == 'normal'
        app.original_text.delete('1.0', 'end')
        app.original_text.insert('1.0', 'New input.')
        pump(app.root, 0.03)
        app._do_retranslate()
        pump(app.root)
        assert app.trans_text.get_plain() == 'Current output.'
        release.set()
        pump(app.root)
        assert app.trans_text.get_plain() == 'Current output.'
    finally:
        release.set()
        app._translation_tasks().cancel()


def test_main_button_cancels_pending_translation(main_window):
    app = main_window('Old input.', furigana=False)
    release = threading.Event()
    app.translation_service.translate_text = lambda *args, **kwargs: (release.wait(1) or 'Late.')
    try:
        app._do_retranslate()
        old = app._translation_tasks().tasks.current
        app.translate_btn.invoke()
        assert not old.is_current()
        assert app._main_pending_source is None
        assert 'Cancel' not in app.translate_btn.cget('text')
    finally:
        release.set()
        app._translation_tasks().cancel()


def test_history_load_cancels_pending_main_translation(main_window):
    app = main_window('Old input.', furigana=False)
    release = threading.Event()
    app.translation_service.translate_text = lambda *args, **kwargs: (release.wait(1) or 'Late.')
    try:
        app._do_retranslate()
        old = app._translation_tasks().tasks.current
        app._load_history_item({'original': 'Saved input.', 'translated': 'Saved output.', 'target_lang': 'English'})
        assert not old.is_current()
        release.set()
        pump(app.root)
        assert app.trans_text.get_plain() == 'Saved output.'
    finally:
        release.set()
        app._translation_tasks().cancel()


def test_main_timeout_releases_controls_and_does_not_accept_late_result(main_window, monkeypatch):
    app = main_window('Old input.', furigana=False)
    runner = app._translation_tasks()
    original_begin = runner.tasks.begin
    monkeypatch.setattr(runner.tasks, 'begin', lambda: original_begin(timeout=0.05))
    release = threading.Event()
    app.translation_service.translate_text = lambda *args, **kwargs: (release.wait(1) or 'Late.')
    try:
        app._do_retranslate()
        pump(app.root)
        assert 'timed out' in app.trans_text.get_plain()
        assert str(app.translate_btn.cget('state')) == 'normal'
        assert not app._translate_animation_running
        release.set()
        pump(app.root, 0.05)
        assert 'timed out' in app.trans_text.get_plain()
    finally:
        release.set()
        runner.cancel()


def test_main_window_close_prevents_late_output_in_reopened_window(main_window):
    app = main_window('Old input.', furigana=False)
    entered, release = threading.Event(), threading.Event()
    app.translation_service.translate_text = lambda *args, **kwargs: (entered.set(), release.wait(1), 'Late.')[-1]
    try:
        app._do_retranslate()
        assert entered.wait(0.5)
        old_window = app.popup
        command = old_window.protocol('WM_DELETE_WINDOW')
        old_window.tk.call(command)
        app.show_popup('New input.', 'New output.', 'English', force_new=True)
        release.set()
        pump(app.root)
        assert app.trans_text.get_plain() == 'New output.'
    finally:
        release.set()
        app._translation_tasks().cancel()


def test_hotkey_callback_returns_without_running_translation_on_hotkey_thread():
    app = TranslatorApp.__new__(TranslatorApp)
    scheduled = queue.Queue()
    app.root = SimpleNamespace(after=lambda _delay, callback: scheduled.put(callback))
    app.translation_service = Mock()
    thread = threading.Thread(target=lambda: app._on_hotkey_translate('English'))
    thread.start()
    thread.join(0.3)
    assert not thread.is_alive()
    assert scheduled.qsize() == 1
    app.translation_service.do_translate_or_fix.assert_not_called()


def test_language_change_cancels_the_old_target(main_window):
    app = main_window('Old input.', furigana=False)
    release = threading.Event()
    app.translation_service.translate_text = lambda *args, **kwargs: (release.wait(1) or 'Late.')
    try:
        app._do_retranslate()
        old = app._translation_tasks().tasks.current
        index = next(i for i, row in enumerate(app.filtered_languages) if row[0] == 'Japanese')
        app.lang_listbox.selection_clear(0, 'end')
        app.lang_listbox.selection_set(index)
        app._on_language_select(None)
        assert not old.is_current()
        assert app.selected_language == 'Japanese'
    finally:
        release.set()
        app._translation_tasks().cancel()


def test_late_grammar_result_does_not_replace_a_new_translation(main_window):
    app = main_window('Old input.', furigana=False)
    entered, release = threading.Event(), threading.Event()
    app.translation_service.fix_grammar = lambda *args: (entered.set(), release.wait(1), 'Old correction.')[-1]
    app.translation_service.translate_text = lambda *args, **kwargs: 'New translation.'
    try:
        app._do_fix_grammar()
        assert entered.wait(0.5)
        app.original_text.delete('1.0', 'end')
        app.original_text.insert('1.0', 'New input.')
        pump(app.root, 0.03)
        app._do_retranslate()
        pump(app.root)
        release.set()
        pump(app.root)
        assert app.trans_text.get_plain() == 'New translation.'
        assert not app._translate_animation_running
    finally:
        release.set()
        app._translation_tasks().cancel()


@pytest.mark.parametrize('replace', [False, True])
def test_screenshot_uses_same_task_owner_and_snapshots_credit(tk_root, replace):
    runner = TranslationTaskRunner(tk_root)
    service = make_service(enabled=False)
    service.api_manager = Mock()
    service.api_manager.last_attribution = 'vision-model (Test)'
    entered, release = threading.Event(), threading.Event()
    answer = '===ORIGINAL===\nA source.\n===SOURCE LANGUAGE===\nEnglish\n===TRANSLATION===\nA result.'
    service.api_manager.translate_multimodal.side_effect = lambda *args: (entered.set(), release.wait(1), answer)[-1]
    service.get_trial_info = lambda: None
    config = SimpleNamespace(get_furigana_enabled=lambda: False)
    handler = ScreenshotHandler(tk_root, config, service, Mock(), Mock())
    shown, errors, new_results = [], [], []
    handler.configure_callbacks(
        on_show_quick_translate=lambda *args, **kwargs: shown.append((args, kwargs)),
        run_translation=lambda operation, _language, completed: runner.start(
            operation, on_result=completed, on_error=errors.append))
    handler._screenshot_target_language = 'English'
    try:
        handler._on_screenshot_captured('sample.png')
        assert entered.wait(0.5)
        if replace:
            runner.start(lambda: 'New result.', on_result=new_results.append)
            pump(tk_root, 0.03)
        release.set()
        pump(tk_root)
        if replace:
            assert new_results == ['New result.'] and shown == []
            assert service.history_manager.get_history() == []
        else:
            assert shown[0][1]['model_info'] == 'vision-model (Test)'
            assert shown[0][0][1] == 'A result.'
        assert errors == []
    finally:
        release.set()
        runner.cancel()
