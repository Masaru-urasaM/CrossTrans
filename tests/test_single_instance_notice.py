"""
The notice a second instance shows, and the fact that it never outlives it.

A second CrossTrans has exactly one job: say "already running" and leave. It used
to do neither. `Messagebox.show_warning` from ttkbootstrap builds its dialog with
`transient=<the root>`, and Tk withdraws a transient window whose master is
withdrawn - so the dialog was never mapped and `show()` sat in `wait_window()`
forever, invisible. Measured 2026-09-07 with py-spy on a process that had been
resident since 2026-08-19:

    wait_window (tkinter/__init__.py:758)
    show (ttkbootstrap/dialogs/dialogs.py:90)
    show_warning (ttkbootstrap/dialogs/dialogs.py:1241)
    main (main.py:46)

Two things had to change, and both are pinned here: the dialog is a native one
that a withdrawn root cannot hide, and a watchdog force-exits the process if the
notice is still up.
"""
import os
import sys
import socket
import subprocess
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.core  # noqa: F401  - before config, see the circular-import note
import main
from src.constants import LOCK_PORT


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _FakeTimer:
    """Stands in for threading.Timer and records what was asked of it."""

    made = []

    def __init__(self, interval, function):
        self.interval = interval
        self.function = function
        self.daemon = None
        self.started = False
        self.cancelled = False
        _FakeTimer.made.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


@pytest.fixture
def fake_tk(monkeypatch):
    """Replace Tk and the messagebox; record the calls."""
    calls = {'withdrawn': 0, 'destroyed': 0, 'warned': []}

    class FakeRoot:
        def withdraw(self):
            calls['withdrawn'] += 1

        def destroy(self):
            calls['destroyed'] += 1

    monkeypatch.setattr(main.tk, 'Tk', lambda: FakeRoot())
    monkeypatch.setattr(main.messagebox, 'showwarning',
                        lambda title, message: calls['warned'].append((title, message)))
    return calls


@pytest.fixture
def fake_timer(monkeypatch):
    _FakeTimer.made = []
    monkeypatch.setattr(main.threading, 'Timer', _FakeTimer)
    return _FakeTimer


class TestTheNotice:
    def test_it_uses_the_stdlib_messagebox(self, fake_tk, fake_timer):
        main._warn_already_running()

        assert len(fake_tk['warned']) == 1
        title, message = fake_tk['warned'][0]
        assert title == "CrossTrans"
        assert "already running" in message
        assert "tray" in message.lower()

    def test_the_root_is_hidden_and_cleaned_up(self, fake_tk, fake_timer):
        main._warn_already_running()

        assert fake_tk['withdrawn'] == 1
        assert fake_tk['destroyed'] == 1

    def test_ttkbootstrap_is_not_involved(self):
        # The dialog that hung was ttkbootstrap's; main.py must not import it.
        # (The comment explaining that history is allowed to name it - hence AST
        # rather than a substring search.)
        import ast
        import io

        source = io.open(os.path.join(PROJECT_ROOT, 'main.py'), encoding='utf-8').read()
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split('.')[0])

        assert 'ttkbootstrap' not in imported
        assert 'tkinter' in imported


class TestTheWatchdog:
    def test_it_is_armed_before_the_dialog(self, fake_tk, fake_timer):
        main._warn_already_running()

        assert len(fake_timer.made) == 1
        timer = fake_timer.made[0]
        assert timer.started is True
        assert timer.interval == main.ALREADY_RUNNING_TIMEOUT_S

    def test_it_is_a_daemon(self, fake_tk, fake_timer):
        # A non-daemon timer would itself hold the process open for the timeout.
        main._warn_already_running()

        assert fake_timer.made[0].daemon is True

    def test_it_is_disarmed_once_the_notice_is_gone(self, fake_tk, fake_timer):
        main._warn_already_running()

        assert fake_timer.made[0].cancelled is True

    def test_it_is_disarmed_even_when_the_dialog_raises(self, fake_tk, fake_timer, monkeypatch):
        def boom(title, message):
            raise RuntimeError("dialog exploded")

        monkeypatch.setattr(main.messagebox, 'showwarning', boom)

        with pytest.raises(RuntimeError):
            main._warn_already_running()

        assert fake_timer.made[0].cancelled is True

    def test_it_force_exits(self, fake_tk, fake_timer, monkeypatch):
        # os._exit, not sys.exit: SystemExit is catchable and this must not be.
        exits = []
        monkeypatch.setattr(main.os, '_exit', lambda code: exits.append(code))

        main._warn_already_running()
        fake_timer.made[0].function()

        assert exits == [0]

    def test_the_timeout_is_a_real_wait_not_an_instant_kill(self):
        # Long enough for someone to read the notice, short enough to not linger.
        assert 5.0 <= main.ALREADY_RUNNING_TIMEOUT_S <= 300.0


class TestMainTakesTheNoticePath:
    def test_it_warns_and_returns_without_starting_the_app(self, monkeypatch):
        warned = []
        monkeypatch.setattr(main, 'is_already_running', lambda: (True, None))
        monkeypatch.setattr(main, '_warn_already_running', lambda: warned.append(True))
        monkeypatch.setattr(main, 'setup_logging', lambda: None)

        assert main.main() == 0
        assert warned == [True]


class TestItReallyExits:
    """The regression itself: a second instance must not survive its notice."""

    def test_a_second_instance_does_not_outlive_its_notice(self, tk_root):
        # tk_root is not used - it is the project's "skip without a display"
        # guard, and the child process below builds a real dialog.
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            holder.bind(('127.0.0.1', LOCK_PORT))
            holder.listen(1)
        except OSError:
            # A real CrossTrans already holds the lock - equally good for this.
            holder.close()
            holder = None

        driver = (
            "import main;"
            "main.ALREADY_RUNNING_TIMEOUT_S = 1.0;"
            "raise SystemExit(main.main())"
        )
        try:
            proc = subprocess.run(
                [sys.executable, '-c', driver],
                cwd=PROJECT_ROOT,
                capture_output=True,
                timeout=45,
            )
        except subprocess.TimeoutExpired:
            pytest.fail(
                "the second instance hung on its notice - the dialog is modal on a "
                "window the user cannot see or close (see this module's docstring)"
            )
        finally:
            if holder is not None:
                holder.close()

        assert proc.returncode == 0, proc.stderr.decode('utf-8', 'replace')
