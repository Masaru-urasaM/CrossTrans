"""
Tests for the notice dialogs in src/ui/dialogs.py (D16).

Every one of them hangs off the app's root, which is withdrawn for the whole life
of the process. `UpdateFailedDialog` called grab_set() + transient(root) and then
wait_window(): Tk withdraws a transient window whose master is withdrawn, so the
dialog was never mapped, its grab held every input of the app, and wait_window()
waited for a click on a window nobody could see - reached right after a failed
self-update. Reproduced on 2026-10-16 under the same withdrawn root these tests
use: state 'withdrawn', viewable 0, the grab held by the dialog.

The other three only grabbed: mapped, but holding the popup and the main window
for as long as they stayed open, possibly behind another application.

Skipped automatically when no display is available (see the `tk_root` fixture).
"""
import inspect
import re
import time
import tkinter as tk

import pytest

import src.core  # noqa: F401  (config <-> core import order)
from src.ui import dialogs
from src.ui.dialogs import (APIErrorDialog, TrialExhaustedDialog, TrialFeatureDialog,
                            UpdateFailedDialog)


def _toplevels(root):
    return [w for w in root.winfo_children()
            if isinstance(w, tk.Toplevel) and w.winfo_exists()]


def _pump(root, ms):
    deadline = time.time() + ms / 1000
    while time.time() < deadline:
        root.update()
        time.sleep(0.01)


def _find(widget, text, classes=('TButton', 'Button')):
    for child in widget.winfo_children():
        try:
            if child.winfo_class() in classes and child.cget('text') == text:
                return child
        except tk.TclError:
            pass
        found = _find(child, text, classes)
        if found is not None:
            return found
    return None


@pytest.fixture
def root(tk_root):
    """The session root, withdrawn as the app's is; no dialog is left behind."""
    assert tk_root.wm_state() == 'withdrawn'
    yield tk_root
    for window in _toplevels(tk_root):
        window.destroy()


def open_update_failed(root, probe, pending_path=None):
    """Build an UpdateFailedDialog and run `probe(window, seen)` inside its wait_window().

    The probe is what closes the dialog. A safety net destroys it after five
    seconds, so a regression fails the test instead of hanging the suite.
    """
    seen = {}

    def run_probe():
        windows = _toplevels(root)
        seen['windows'] = len(windows)
        if windows:
            probe(windows[0], seen)

    def safety_net():
        for window in _toplevels(root):
            seen['timed_out'] = True
            window.destroy()

    root.after(300, run_probe)
    net = root.after(5000, safety_net)
    dialog = UpdateFailedDialog(root, "Access is denied", pending_path,
                                current_exe="CrossTrans.exe")
    root.after_cancel(net)
    return dialog, seen


def record_and_close(window, seen):
    seen['state'] = window.wm_state()
    seen['viewable'] = window.winfo_viewable()
    seen['grab'] = window.grab_current()
    window.destroy()


def click(*texts):
    """A probe that clicks each labelled control in turn."""
    def probe(window, seen):
        for text in texts:
            control = _find(window, text, ('TButton', 'Button', 'TRadiobutton', 'Radiobutton'))
            assert control is not None, f"no control labelled {text!r}"
            control.invoke()
    return probe


# --------------------------------------------------------------------------- #
# UpdateFailedDialog - the freeze
# --------------------------------------------------------------------------- #
class TestUpdateFailedDialog:
    def test_it_is_shown_under_the_withdrawn_root(self, root):
        _dialog, seen = open_update_failed(root, record_and_close)
        assert seen['windows'] == 1
        assert seen['state'] == 'normal', "transient() on a withdrawn root hides the dialog"
        assert seen['viewable'] == 1
        assert 'timed_out' not in seen

    def test_it_holds_no_grab(self, root):
        _dialog, seen = open_update_failed(root, record_and_close)
        assert seen['grab'] is None, f"the dialog grabbed every input: {seen['grab']}"

    def test_it_is_raised_above_other_windows_then_lets_go(self, root):
        def probe(window, seen):
            seen['topmost_at_open'] = window.attributes('-topmost')
            window.destroy()
        # Opened 300 ms in - after the 100 ms release, so only the release is seen.
        _dialog, seen = open_update_failed(root, probe)
        assert not seen['topmost_at_open']

    def test_continue_returns_the_chosen_option(self, root):
        dialog, _seen = open_update_failed(
            root, click("Download manually from GitHub", "Continue"))
        assert dialog.result == 'manual'

    def test_a_pending_update_defaults_to_the_restart(self, root):
        dialog, _seen = open_update_failed(root, click("Continue"), pending_path="pending.exe")
        assert dialog.result == 'reboot'

    def test_without_a_pending_update_the_restart_is_not_offered(self, root):
        def probe(window, seen):
            seen['restart'] = _find(window, "Schedule update for next Windows restart",
                                    ('TRadiobutton', 'Radiobutton'))
            click("Continue")(window, seen)
        dialog, seen = open_update_failed(root, probe)
        assert seen['restart'] is None
        assert dialog.result == 'manual'

    def test_cancel_returns_cancel(self, root):
        dialog, _seen = open_update_failed(root, click("Cancel"), pending_path="pending.exe")
        assert dialog.result == 'cancel'

    def test_closing_the_window_returns_cancel(self, root):
        dialog, _seen = open_update_failed(root, record_and_close, pending_path="pending.exe")
        assert dialog.result == 'cancel'


# --------------------------------------------------------------------------- #
# The notices: API error, trial exhausted, trial feature
# --------------------------------------------------------------------------- #
NOTICES = [
    pytest.param(lambda root: APIErrorDialog(root, on_open_settings_tab=lambda tab: None),
                 id="api-error"),
    pytest.param(lambda root: TrialExhaustedDialog(root, on_open_settings_tab=lambda tab: None),
                 id="trial-exhausted"),
    pytest.param(lambda root: TrialFeatureDialog(root, feature_name="File translation",
                                                 on_open_settings_tab=lambda tab: None),
                 id="trial-feature"),
]


@pytest.mark.parametrize("build", NOTICES)
class TestNotices:
    def test_it_is_shown_and_holds_no_grab(self, root, build):
        notice = build(root)
        root.update()
        assert notice.window.wm_state() == 'normal'
        assert notice.window.winfo_viewable()
        assert root.grab_current() is None, "a notice grabbed every input of the app"

    def test_it_is_raised_then_lets_go_of_topmost(self, root, build):
        notice = build(root)
        assert notice.window.attributes('-topmost')
        _pump(root, 300)
        assert not notice.window.attributes('-topmost')

    def test_open_settings_closes_it_and_opens_the_api_key_tab(self, root, build):
        notice = build(root)
        opened = []
        notice.on_open_settings_tab = opened.append
        _find(notice.window, "Open API Key Settings").invoke()
        assert opened == ["API Key"]
        assert not notice.window.winfo_exists()


def test_the_module_calls_neither_grab_set_nor_transient():
    source = inspect.getsource(dialogs)
    code = "\n".join(line.split('#', 1)[0] for line in source.splitlines())
    assert not re.search(r'\.(grab_set|transient|wm_transient)\(', code)
