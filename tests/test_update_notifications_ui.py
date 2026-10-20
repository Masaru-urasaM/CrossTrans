"""Real notification/Settings widgets on the private test desktop, no network."""
import threading
import gc
import time
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.core.update_ui_manager import UpdateUIManager
from config import Config
from src.ui.settings.general_tab import GeneralTabMixin
from src.ui.settings.update_manager import UpdateManagerMixin
from src.ui.toast import ToastManager
from src.ui.tray import TrayManager
from src.ui.update_notice import UpdateNotice
from src.ui.translation_tasks import TranslationTaskRunner


NEW = '9.9.9'


@pytest.fixture(autouse=True)
def collect_widget_cycles_on_ui_thread():
    yield
    # General-tab variables can otherwise be finalized by a later worker's GC.
    gc.collect()


def pump(root, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        root.update()
        time.sleep(0.005)
    assert predicate()


@pytest.mark.parametrize('action', ['update', 'later', 'skip'])
def test_notice_hidden_root_no_grab_no_focus_and_real_buttons(tk_root, monkeypatch, action):
    tk_root.withdraw()
    other = tk.Toplevel(tk_root)
    entry = tk.Entry(other)
    entry.pack()
    other.update()
    entry.focus_force()
    tk_root.update()
    before = tk_root.focus_get()
    forbidden = Mock(side_effect=AssertionError('Notification grabbed input or focus'))
    monkeypatch.setattr(tk.Toplevel, 'grab_set', forbidden)
    monkeypatch.setattr(tk.Toplevel, 'focus_force', forbidden)
    monkeypatch.setattr(tk.Toplevel, 'transient', forbidden)
    callback = Mock()
    notice = UpdateNotice(tk_root, NEW, callback)
    try:
        tk_root.update()
        assert notice.window.winfo_viewable()
        assert tk_root.grab_current() is None
        assert tk_root.focus_get() == before
        # A private desktop may not reproduce activation on the input desktop.
        # Verify the native no-activation contract as well as the observed focus.
        import win32con
        import win32gui
        client = notice.window.winfo_id()
        hwnd = win32gui.GetParent(client) or client
        assert win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_NOACTIVATE
        assert [b.cget('text') for b in notice.buttons.values()] == [
            'Update', 'Later', 'Skip this version']
        notice.buttons[action].invoke()
        callback.assert_called_once_with(action)
        assert not notice.window.winfo_exists()
    finally:
        notice.close()
        other.destroy()


class SettingsHarness(UpdateManagerMixin, GeneralTabMixin):
    def __init__(self, root, manager):
        self.window = tk.Toplevel(root)
        self.config = manager.config
        self.update_manager = manager
        self.updater = Mock()
        self._download_active = False
        self._download_poll_id = None
        self._owns_update_manager = False
        self.is_translation_busy = lambda: False
        self._save_all_hotkeys = Mock()
        self.hotkey_entries = {}
        self._create_general_tab(self.window)
        self.window.bind('<Destroy>', self._close_update_work, add='+')


@pytest.fixture
def settings(tk_root):
    config = Config.__new__(Config)
    config._config = Config.DEFAULT_CONFIG.copy()
    config.save = Mock()
    config.is_autostart_enabled = lambda: False
    manager = UpdateUIManager(tk_root, config, ToastManager(tk_root))
    manager.available_version = NEW
    manager.available_updater = Mock()
    manager.configure_callbacks(on_open_update=Mock())
    view = SettingsHarness(tk_root, manager)
    yield view
    if view.window.winfo_exists():
        view.window.destroy()
    manager.stop()


def test_persistent_settings_badge_and_manual_entry(settings):
    view = settings
    view.refresh_update_state()
    view.window.update()
    assert view.update_offer_frame.winfo_ismapped()
    assert NEW in view.update_offer_label.cget('text')
    view.update_offer_button.invoke()
    view.update_manager._on_open_update.assert_called_once_with(
        NEW, view.update_manager.available_updater)
    view.update_manager.available_version = None
    view.refresh_update_state()
    assert not view.update_offer_frame.winfo_ismapped()


def test_auto_check_toggle_applies_live(settings):
    view = settings
    view.auto_check_var.set(False)
    view._on_auto_check_changed()
    assert view.config.get_auto_check_updates() is False
    view.auto_check_var.set(True)
    view._on_auto_check_changed()
    assert view.config.get_auto_check_updates() is True


def test_download_only_queues_ui_and_requires_explicit_idle_restart(settings, tk_root, monkeypatch):
    view = settings
    owner = threading.get_ident()
    original_after = tk.Misc.after

    def ui_after(self, *args, **kwargs):
        assert threading.get_ident() == owner, 'Worker called Tk.after'
        return original_after(self, *args, **kwargs)

    monkeypatch.setattr(tk.Misc, 'after', ui_after)
    forbidden = Mock(side_effect=AssertionError('Download must not grab input'))
    monkeypatch.setattr(tk.Toplevel, 'grab_set', forbidden)
    updater = view.updater

    def download(progress):
        assert threading.get_ident() != owner
        progress(15)
        progress(100)
        return {'success': True}

    updater.download.side_effect = download
    updater.install_and_restart.return_value = {'success': True}
    view.is_translation_busy = lambda: True
    view._start_update_download(NEW)
    pump(tk_root, lambda: not view._download_active)
    assert not view.progress_win.winfo_exists()
    assert view.update_manager.ready_update == (NEW, updater)
    assert view.update_offer_button.cget('text') == 'Restart to update'
    updater.install_and_restart.assert_not_called()
    view.update_offer_button.invoke()
    updater.install_and_restart.assert_not_called()
    assert 'translation' in view.update_status_label.cget('text')
    view.is_translation_busy = lambda: False
    view.update_offer_button.invoke()
    updater.install_and_restart.assert_called_once()


@pytest.mark.parametrize('close_settings', [False, True])
def test_cancel_or_close_during_download_never_offers_install(settings, tk_root, close_settings):
    view = settings
    entered, release, done = threading.Event(), threading.Event(), threading.Event()

    def download(progress):
        entered.set()
        try:
            release.wait(2)
            progress(50)
            return {'success': True}
        finally:
            done.set()

    view.updater.download.side_effect = download
    view._start_update_download(NEW)
    assert entered.wait(1)
    if close_settings:
        view.window.destroy()
    else:
        view._cancel_download()
    release.set()
    assert done.wait(1)
    if not close_settings:
        pump(tk_root, lambda: not view._download_active)
        assert 'cancelled' in view.update_status_label.cget('text')
    else:
        assert view._download_poll_id is None
        assert not view._download_active
    assert view.update_manager.ready_update is None
    view.updater.install_and_restart.assert_not_called()


def test_downloaded_update_survives_reopening_settings(settings, tk_root):
    manager = settings.update_manager
    settings._on_download_done({'success': True}, NEW, settings.updater)
    settings.window.destroy()
    reopened = SettingsHarness(tk_root, manager)
    try:
        reopened.refresh_update_state()
        assert reopened.update_offer_button.cget('text') == 'Restart to update'
        assert NEW in reopened.update_offer_label.cget('text')
    finally:
        reopened.window.destroy()


def test_tray_available_update_is_actionable_without_starting_tray():
    config = Mock()
    config.get_all_hotkeys.return_value = {}
    config.has_any_vision_capable.return_value = False
    config.get_fix_grammar_hotkey_enabled.return_value = False
    tray = TrayManager(config)
    action = Mock()
    tray.configure_callbacks(on_update=action)
    tray.set_update_available(NEW)
    entry = next(item for item in tray._build_menu_items() if item.text.startswith('Update available'))
    assert NEW in entry.text
    entry(None)
    action.assert_called_once()
    tray.set_update_available(None)
    assert all(not item.text.startswith('Update available') for item in tray._build_menu_items())


def test_runner_busy_ends_when_result_is_delivered(tk_root):
    runner = TranslationTaskRunner(tk_root)
    release = threading.Event()
    results = []
    runner.start(lambda: release.wait(2), on_result=results.append)
    assert runner.busy
    release.set()
    pump(tk_root, lambda: bool(results))
    assert not runner.busy
    runner.start(lambda: 'cancelled')
    runner.cancel()
    assert not runner.busy


def test_coordinator_wires_ready_metadata_and_translation_guard():
    from src.app import TranslatorApp
    app = TranslatorApp.__new__(TranslatorApp)
    app.settings_window = SimpleNamespace(
        _download_active=False, refresh_update_state=Mock(), offer_update=Mock(),
        notebook=Mock(), _tab_frames={'general': 'general frame'})
    app.update_manager = SimpleNamespace(available_version=NEW)
    app.tray_manager = Mock()
    app.root = SimpleNamespace(grab_current=lambda: None)
    app.show_settings = Mock()
    app._translation_task_runner = SimpleNamespace(busy=True)
    assert app._updates_are_busy()
    app._translation_task_runner.busy = False
    assert not app._updates_are_busy()
    app._update_state_changed()
    app.tray_manager.set_update_available.assert_called_once_with(NEW)
    app.settings_window.refresh_update_state.assert_called_once()
    snapshot = object()
    app._open_available_update(NEW, snapshot)
    app.settings_window.notebook.select.assert_called_once_with('general frame')
    app.settings_window.offer_update.assert_called_once_with(NEW, snapshot)
