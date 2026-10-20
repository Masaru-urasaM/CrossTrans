"""Automatic offers, persisted choices, safe UI delivery and explicit restarts."""
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.core import update_ui_manager as updates
from config import Config
from src.core.update_policy import UPDATE_INTERVAL_SECONDS, should_notify, reminder_changes
from src.ui.settings.update_manager import UpdateManagerMixin
from src.ui.toast import ToastType


DAY = UPDATE_INTERVAL_SECONDS
NEW = '9.9.9'


class Preferences:
    def __init__(self):
        self.enabled = True
        self.preferences = {}

    def get_auto_check_updates(self):
        return self.enabled

    def get_update_reminders(self):
        return dict(self.preferences)

    def set_update_reminders(self, **changes):
        self.preferences.update(changes)


class Clock:
    mono = 100
    wall = 100000

    def advance(self, seconds):
        self.mono += seconds
        self.wall += seconds


class Root:
    """A deterministic UI scheduler that rejects worker-thread Tk operations."""
    def __init__(self):
        self.owner = threading.get_ident()
        self.jobs = {}
        self.serial = 0

    def after(self, delay, callback):
        assert threading.get_ident() == self.owner
        self.serial += 1
        self.jobs[self.serial] = callback
        return self.serial

    def after_cancel(self, job):
        assert threading.get_ident() == self.owner
        self.jobs.pop(job, None)

    def tick(self):
        pending, self.jobs = self.jobs, {}
        for callback in pending.values():
            callback()


class Notice:
    instances = []

    def __init__(self, root, version, callback):
        assert threading.get_ident() == root.owner
        self.version, self.callback, self.closed = version, callback, False
        self.instances.append(self)

    def close(self):
        self.closed = True


@pytest.fixture
def controller(monkeypatch):
    clock, root, config = Clock(), Root(), Preferences()
    monkeypatch.setattr(updates, 'time', SimpleNamespace(
        monotonic=lambda: clock.mono, time=lambda: clock.wall))
    monkeypatch.setattr(updates, 'UpdateNotice', Notice)
    Notice.instances = []
    updater = Mock()
    updater.check_update.return_value = {'has_update': True, 'version': NEW}
    factory = Mock(return_value=updater)
    monkeypatch.setattr(updates, 'AutoUpdater', factory)
    manager = updates.UpdateUIManager(root, config, Mock())
    manager.configure_callbacks(on_state_changed=Mock(), on_open_update=Mock())
    yield SimpleNamespace(manager=manager, root=root, config=config, clock=clock,
                          factory=factory, updater=updater)
    manager.stop()


def completed(c):
    deadline = time.monotonic() + 2
    while c.manager._answers.empty() and time.monotonic() < deadline:
        time.sleep(0.002)
    assert not c.manager._answers.empty(), 'Check worker did not finish'
    c.root.tick()


@pytest.mark.parametrize('action', ['shown', 'later', 'skip'])
def test_reminder_is_version_specific(action):
    prefs = reminder_changes(action, NEW, 100000)
    assert not should_notify(NEW, prefs, 100001)
    assert should_notify('10.0.0', prefs, 100001)
    assert should_notify(NEW, prefs, 100000 + DAY) == (action != 'skip')


@pytest.mark.parametrize('bad', [None, 'bad', float('nan'), float('inf'), -1])
def test_invalid_saved_timestamp_cannot_block_updates_forever(bad):
    assert should_notify(NEW, {'snoozed_version': NEW, 'snooze_until': bad}, 100000)


def test_preferences_survive_restart_and_preserve_explicit_opt_out(tmp_path, monkeypatch):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'auto_check_updates': False}), encoding='utf-8')
    monkeypatch.setattr(Config, 'CONFIG_DIR', str(tmp_path))
    monkeypatch.setattr(Config, 'CONFIG_FILE', str(path))
    config = Config()
    assert config.get_auto_check_updates() is False
    config.set_update_reminders(**reminder_changes('later', NEW, 100000))
    config.set_update_reminders(skipped_version='8.0.0')
    reloaded = Config()
    assert not should_notify(NEW, reloaded.get_update_reminders(), 100001)
    assert reloaded.get_update_reminders()['skipped_version'] == '8.0.0'
    isolated = reloaded.get_update_reminders()
    isolated.clear()
    assert reloaded.get_update_reminders()
    assert Config.DEFAULT_CONFIG['update_reminders'] == {}


def test_auto_check_default_is_enabled():
    config = Config.__new__(Config)
    config._config = {}
    assert config.get_auto_check_updates() is True
    config._config['update_reminders'] = 'invalid legacy data'
    assert config.get_update_reminders() == {}


def test_startup_delay_daily_check_and_no_duplicate_pump(controller):
    c = controller
    c.manager.startup_update_check()
    c.manager.startup_update_check()
    assert len(c.root.jobs) == 1
    c.root.tick()
    c.factory.assert_not_called()
    c.clock.advance(3)
    c.root.tick()
    completed(c)
    assert c.manager.available_version == NEW
    assert len(Notice.instances) == 1
    c.clock.advance(DAY - 1)
    c.root.tick()
    assert c.factory.call_count == 1
    c.clock.advance(1)
    c.root.tick()
    completed(c)
    assert c.factory.call_count == 2


def test_disabled_auto_check_still_allows_manual_check(controller):
    c = controller
    c.config.enabled = False
    c.manager.startup_update_check()
    c.clock.advance(DAY)
    c.root.tick()
    c.factory.assert_not_called()
    callback = Mock()
    c.manager.request_check(callback)
    completed(c)
    callback.assert_called_once_with({'has_update': True, 'version': NEW}, c.updater)
    assert not Notice.instances


def test_busy_translation_defers_notice_and_explicit_open(controller):
    c = controller
    busy = [True]
    c.manager._is_busy = lambda: busy[0]
    c.manager.request_check()
    completed(c)
    assert not Notice.instances
    c.manager.request_update()
    c.manager._on_open_update.assert_not_called()
    busy[0] = False
    c.root.tick()
    c.manager._on_open_update.assert_called_once_with(NEW, c.updater)


@pytest.mark.parametrize('action', ['later', 'skip'])
def test_notice_choice_is_saved_and_does_not_hide_manual_entry(controller, action):
    c = controller
    c.manager.request_check()
    completed(c)
    notice = Notice.instances[-1]
    notice.callback(action)
    assert notice.closed
    assert c.manager.available_version == NEW
    assert not should_notify(NEW, c.config.preferences, c.clock.wall + 1)
    c.manager.request_update()
    c.manager._on_open_update.assert_called_once_with(NEW, c.updater)
    c.root.tick()
    assert len(Notice.instances) == 1


def test_update_action_opens_settings_with_the_checked_snapshot(controller):
    c = controller
    c.manager.request_check()
    completed(c)
    Notice.instances[-1].callback('update')
    c.manager._on_open_update.assert_called_once_with(NEW, c.updater)
    c.factory.assert_called_once()


def test_manual_check_bypasses_skip_and_shares_worker(controller):
    c = controller
    c.config.preferences['skipped_version'] = NEW
    gate = threading.Event()
    c.updater.check_update.side_effect = lambda: (gate.wait(2) and {'has_update': True, 'version': NEW})
    one, two = Mock(), Mock()
    c.manager.request_check(one)
    c.manager.request_check(two)
    gate.set()
    completed(c)
    c.factory.assert_called_once()
    one.assert_called_once()
    two.assert_called_once()
    assert not Notice.instances


def test_timeout_ignores_late_answer_and_keeps_pump_alive(controller):
    c = controller
    gate = threading.Event()
    c.updater.check_update.side_effect = lambda: (gate.wait(2) and {'has_update': True, 'version': NEW})
    callback = Mock()
    c.manager.request_check(callback)
    c.clock.advance(61)
    c.root.tick()
    assert 'timed out' in callback.call_args.args[0]['error']
    gate.set()
    completed(c)
    assert c.manager.available_version is None
    assert c.root.jobs


@pytest.mark.parametrize('failure', ['offline', RuntimeError('offline')])
def test_background_error_is_quiet_and_manual_error_is_delivered(controller, failure):
    c = controller
    if isinstance(failure, Exception):
        c.updater.check_update.side_effect = failure
    else:
        c.updater.check_update.return_value = {'error': failure, 'has_update': False}
    callback = Mock()
    c.manager.request_check(callback)
    completed(c)
    assert callback.call_args.args[0]['error'] == 'offline'
    assert not Notice.instances
    assert c.root.jobs


def test_tray_thread_only_queues_and_stop_prevents_callbacks(controller):
    c = controller
    c.manager.request_check()
    completed(c)
    thread = threading.Thread(target=c.manager.post_update_request)
    thread.start()
    thread.join()
    c.manager._on_open_update.assert_not_called()
    c.root.tick()
    c.manager._on_open_update.assert_called_once()
    c.manager.stop()
    c.manager.post_update_request()
    c.root.tick()
    c.manager._on_open_update.assert_called_once()
    assert not c.root.jobs


def test_current_release_and_downloaded_release_do_not_offer_again(controller):
    c = controller
    c.manager.ready_update = (NEW, c.updater)
    c.manager.request_check()
    completed(c)
    assert not Notice.instances
    c.updater.check_update.return_value = {'has_update': False, 'version': '1.0.0'}
    c.manager.request_check()
    completed(c)
    assert c.manager.available_version is None
    assert c.manager.available_updater is None


def test_success_toast_uses_current_api(controller):
    c = controller
    c.manager._show_update_success_toast(NEW)
    c.manager.toast.show.assert_called_once_with(
        f'CrossTrans has been updated to v{NEW}', ToastType.SUCCESS, duration=5000)


def test_old_reply_cannot_finish_a_new_check(controller):
    c = controller
    c.config.enabled = False
    old_release, new_release = threading.Event(), threading.Event()
    old_entered, new_entered = threading.Event(), threading.Event()
    old, new = Mock(), Mock()

    def answer(entered, release, version):
        entered.set()
        release.wait(2)
        return {'has_update': True, 'version': version}

    old.check_update.side_effect = lambda: answer(old_entered, old_release, '8.8.8')
    new.check_update.side_effect = lambda: answer(new_entered, new_release, NEW)
    c.factory.side_effect = [old, new]
    try:
        c.manager.request_check(Mock())
        assert old_entered.wait(1)
        c.clock.advance(61)
        c.root.tick()
        callback = Mock()
        c.manager.request_check(callback)
        assert new_entered.wait(1)
        old_release.set()
        completed(c)
        callback.assert_not_called()
        assert c.manager.available_version is None
        new_release.set()
        completed(c)
        callback.assert_called_once_with({'has_update': True, 'version': NEW}, new)
        assert c.manager.available_updater is new
    finally:
        old_release.set()
        new_release.set()


def test_stop_discards_pending_results(controller):
    c = controller
    callback = Mock()
    c.manager.request_check(callback)
    c.manager.stop()
    c.root.tick()
    callback.assert_not_called()
    assert c.manager.available_version is None
    assert not c.root.jobs
