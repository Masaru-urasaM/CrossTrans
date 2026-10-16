"""
Tests for tests/quiet_session.py - a test run stays off the user's session (K12).

The suite drives real Tk windows and the app raises them on purpose, so until
2026-10-16 every run drew them on the developer's screen and took their focus,
and nothing stopped a test from spending API quota or overwriting the clipboard.
These pin each guard: where the windows go; that a mapped, raised, force-focused
window never reaches the user's desktop; and that network, clipboard, keystroke,
hotkey, browser and registry calls are refused. Every refusal is checked to be
installed BEFORE the call is made, so a broken guard fails the test rather than
reach the user's session.
"""
import ctypes
import os
import shutil
import socket
import subprocess
import sys
import textwrap
import tkinter as tk
from pathlib import Path

import pytest

import quiet_session as quiet

ROOT = Path(__file__).resolve().parent.parent
# TEST-NET-3 (RFC 5737): reserved for documentation and never routed, so even a
# broken guard cannot reach anything through it.
UNROUTABLE = ('203.0.113.1', 443)


def needs_the_private_desktop():
    if not quiet.DESKTOP_NAME:
        pytest.skip(f"no private desktop on this run: {quiet.DESKTOP_ERROR}")


class TestWhereWindowsGo:
    def test_the_private_desktop_allows_them(self):
        assert quiet.windows_allowed('crosstrans-tests-1', {})

    def test_without_it_they_are_refused(self):
        assert not quiet.windows_allowed(None, {})

    def test_ci_has_no_one_in_front_of_the_screen(self):
        assert quiet.windows_allowed(None, {'CI': 'true'})

    def test_the_screen_only_when_asked_for(self):
        assert quiet.windows_allowed(None, {quiet.ON_SCREEN_ENV: '1'})
        assert not quiet.windows_allowed(None, {quiet.ON_SCREEN_ENV: '0'})

    def test_this_run_has_a_private_desktop(self):
        # On a developer's machine it is not optional: without it every Tk test
        # would skip. On CI, or when the screen was asked for, Tk may go there -
        # asserted rather than skipped, so CI's skip budget is not spent on it.
        if os.environ.get('CI') or os.environ.get(quiet.ON_SCREEN_ENV) == '1':
            assert quiet.DESKTOP_NAME or quiet.windows_allowed()
        else:
            assert quiet.DESKTOP_NAME, quiet.DESKTOP_ERROR

    def test_a_skip_names_the_reason_and_the_way_out(self, monkeypatch):
        monkeypatch.setattr(quiet, 'DESKTOP_ERROR', 'CreateDesktopW failed, Windows error 5')
        reason = quiet.skip_reason()
        assert 'Windows error 5' in reason and quiet.ON_SCREEN_ENV in reason

    def test_tk_is_refused_without_a_desktop(self, monkeypatch):
        # The refusal comes before Tk exists, so nothing is drawn anywhere.
        monkeypatch.setattr(quiet, 'DESKTOP_NAME', None)
        monkeypatch.delenv('CI', raising=False)
        monkeypatch.delenv(quiet.ON_SCREEN_ENV, raising=False)
        with pytest.raises(pytest.skip.Exception, match='no private desktop'):
            tk.Tk()

    # A Tcl-only interpreter has no windows and is never refused. Checked on the
    # arguments, not by making one: a further interpreter mid-run is fragile under
    # pytest's capture - one could not read init.tcl in some orders (2026-10-16).
    def test_tkinter_tcl_is_not_a_window(self):
        assert not quiet.wants_windows((None, None, 'Tk', False), {})     # tkinter.Tcl()
        assert not quiet.wants_windows((), {'useTk': False})

    def test_tk_is(self):
        assert quiet.wants_windows((), {})
        assert quiet.wants_windows((None, None, 'Tk', True), {})
        assert quiet.wants_windows((), {'className': 'CrossTrans'})

    def test_tcl_passes_use_tk_where_it_is_looked_for(self):
        import inspect
        assert 'return Tk(screenName, baseName, className, useTk)' in inspect.getsource(tk.Tcl)


class TestPrivateDesktop:
    def test_the_tk_thread_is_on_it(self, tk_root):
        needs_the_private_desktop()
        assert quiet.thread_desktop_name() == quiet.DESKTOP_NAME != 'Default'

    def test_a_mapped_window_is_real_but_not_on_the_users_desktop(self, tk_root):
        needs_the_private_desktop()
        top = tk.Toplevel(tk_root)
        try:
            top.geometry('320x200+40+40')
            tk.Label(top, text='quiet').pack()
            top.update()
            assert top.winfo_viewable() and top.winfo_height() > 1     # really mapped
            assert quiet.our_windows_on('Default') == []
        finally:
            top.destroy()

    def test_raising_and_forcing_focus_leave_the_users_focus_alone(self, tk_root):
        needs_the_private_desktop()
        top = tk.Toplevel(tk_root)
        try:
            top.attributes('-topmost', True)
            top.update()
            top.lift()
            top.focus_force()
            top.update()
            assert top.focus_get() is not None      # it has the focus - on its own desktop
            assert quiet.foreground_pid('Default') != os.getpid()
            assert quiet.our_windows_on('Default') == []
        finally:
            top.destroy()

    def test_the_root_shown_stays_off_the_users_desktop(self, tk_root):
        # What `mapped_root` does for the word-chip tests.
        needs_the_private_desktop()
        tk_root.deiconify()
        try:
            tk_root.update()
            assert tk_root.winfo_viewable()
            assert quiet.our_windows_on('Default') == []
        finally:
            tk_root.withdraw()


class TestNetwork:
    def test_the_socket_guards_are_installed(self):
        assert quiet.is_guard(socket.socket.connect)
        assert quiet.is_guard(socket.socket.connect_ex)
        assert quiet.is_guard(socket.getaddrinfo)

    def test_what_urllib_does_is_refused(self):
        assert quiet.is_guard(socket.getaddrinfo)
        with quiet.expect_blocked() as seen:
            with pytest.raises(quiet.SessionGuardError):
                socket.create_connection(UNROUTABLE, timeout=0.5)
        assert seen and '203.0.113.1' in seen[0]

    def test_a_connection_to_an_address_is_refused(self):
        assert quiet.is_guard(socket.socket.connect)
        sock = socket.socket()
        sock.settimeout(0.5)
        try:
            with quiet.expect_blocked() as seen:
                with pytest.raises(quiet.SessionGuardError):
                    sock.connect(UNROUTABLE)
        finally:
            sock.close()
        assert seen and '203.0.113.1' in seen[0]

    def test_connect_ex_is_refused_too(self):
        assert quiet.is_guard(socket.socket.connect_ex)
        sock = socket.socket()
        try:
            with quiet.expect_blocked() as seen:
                with pytest.raises(quiet.SessionGuardError):
                    sock.connect_ex(UNROUTABLE)
        finally:
            sock.close()
        assert seen and '203.0.113.1' in seen[0]

    def test_a_host_name_is_refused_before_any_lookup(self):
        # .invalid never resolves (RFC 2606), so a broken guard sends nothing useful.
        assert quiet.is_guard(socket.getaddrinfo)
        with quiet.expect_blocked() as seen:
            with pytest.raises(quiet.SessionGuardError):
                socket.getaddrinfo('quota.invalid', 443)
        assert seen and 'quota.invalid' in seen[0]

    def test_loopback_still_works(self):
        server = socket.socket()
        try:
            server.bind(('127.0.0.1', 0))
            server.listen(1)
            with socket.create_connection(('127.0.0.1', server.getsockname()[1]), timeout=2):
                pass
        finally:
            server.close()

    @pytest.mark.parametrize('host', ['127.0.0.1', '127.8.8.8', '::1', 'localhost',
                                      'LOCALHOST', '', None, b'127.0.0.1', '0.0.0.0'])
    def test_this_machine(self, host):
        assert quiet.is_loopback(host)

    @pytest.mark.parametrize('host', ['203.0.113.1', '8.8.8.8', '10.0.0.1', '192.168.1.1',
                                      'api.groq.com', 'generativelanguage.googleapis.com',
                                      '::ffff:8.8.8.8', '2001:db8::1'])
    def test_anywhere_else(self, host):
        assert not quiet.is_loopback(host)

    def test_the_running_apps_lock_port_is_refused_without_connecting(self):
        # Judged on the address, never by connecting: a real connection would
        # reach the CrossTrans the developer is running.
        problem = quiet.check_address(('127.0.0.1', quiet.LOCK_PORT), quiet.LOCK_PORT)
        assert problem and str(quiet.LOCK_PORT) in problem and 'port=' in problem

    def test_other_loopback_ports_are_fine(self):
        assert quiet.check_address(('127.0.0.1', quiet.LOCK_PORT + 1), quiet.LOCK_PORT) is None

    def test_the_lock_port_is_the_apps(self):
        from src.constants import LOCK_PORT
        assert quiet.LOCK_PORT == LOCK_PORT

    def test_a_refusal_says_where_real_calls_belong(self):
        problem = quiet.check_address(UNROUTABLE, quiet.LOCK_PORT)
        assert 'mock the call' in problem and 'tools/eval_' in problem

    def test_a_unix_socket_is_not_the_network(self):
        assert quiet.check_address('/tmp/socket', quiet.LOCK_PORT) is None


class TestClipboard:
    def test_tk_has_the_in_memory_clipboard(self, tk_root):
        assert quiet.tk_clipboard_is_fake(tk_root)

    def test_a_tk_copy_never_reaches_windows(self, tk_root):
        assert quiet.tk_clipboard_is_fake(tk_root)      # never write for real
        tk_root.clipboard_clear()
        tk_root.clipboard_append('勉強 quiet')
        tk_root.update()
        assert tk_root.clipboard_get() == '勉強 quiet'
        assert quiet.clipboard_owner_pid() != os.getpid()

    def test_a_text_widgets_own_binding_stays_in_memory(self, tk_root):
        # tk_textCopy writes through the Tcl command, not through Python.
        assert quiet.tk_clipboard_is_fake(tk_root)
        text = tk.Text(tk_root)
        try:
            text.insert('1.0', 'abc')
            text.tag_add('sel', '1.0', '1.2')
            text.event_generate('<<Copy>>')
            tk_root.update()
            assert tk_root.clipboard_get() == 'ab'
            assert quiet.clipboard_owner_pid() != os.getpid()
        finally:
            text.destroy()

    def test_the_real_one_only_on_ci_or_when_asked_for(self):
        assert not quiet.real_clipboard_allowed({})
        assert quiet.real_clipboard_allowed({'CI': 'true'})
        assert quiet.real_clipboard_allowed({quiet.REAL_CLIPBOARD_ENV: '1'})
        assert not quiet.real_clipboard_allowed({quiet.REAL_CLIPBOARD_ENV: '0'})

    def test_real_clipboard_hands_it_back_and_takes_it_again(self, tk_root):
        # Only the state is looked at - nothing is written.
        import pyperclip
        with quiet.real_clipboard(tk_root):
            assert not quiet.tk_clipboard_is_fake(tk_root)
            assert not quiet.is_guard(pyperclip.copy)
        assert quiet.tk_clipboard_is_fake(tk_root)
        assert quiet.is_guard(pyperclip.copy)


class TestPythonRoutes:
    @pytest.mark.parametrize('module_name, attribute, what',
                             quiet.ACTION_GUARDS + quiet.CLIPBOARD_GUARDS)
    def test_each_is_refused(self, module_name, attribute, what):
        module = pytest.importorskip(module_name)
        function = getattr(module, attribute)
        assert quiet.is_guard(function), f"{module_name}.{attribute} is not guarded"
        with quiet.expect_blocked() as seen:
            with pytest.raises(quiet.SessionGuardError):
                function('x')
        assert seen == [what]

    @pytest.mark.parametrize('attribute, what', quiet.USER32_GUARDS)
    def test_user32_input_and_hotkeys_are_refused(self, attribute, what):
        function = getattr(ctypes.windll.user32, attribute)
        assert quiet.is_guard(function), f"user32.{attribute} is not guarded"
        with quiet.expect_blocked() as seen:
            with pytest.raises(quiet.SessionGuardError):
                function(0, 0, 0, 0)
        assert seen == [what]

    def test_pyperclip_cannot_rebind_its_copy(self):
        # pyperclip's lazy first call rebinds `copy`; settled at install, a
        # paste() later cannot undo the guard.
        import pyperclip
        assert pyperclip.paste is not pyperclip.lazy_load_stub_paste
        assert quiet.is_guard(pyperclip.copy)

    def test_a_refusal_is_an_oserror(self):
        # What code coping with an offline machine or a busy clipboard catches.
        assert issubclass(quiet.SessionGuardError, OSError)


def test_a_swallowed_refusal_still_fails_the_test(tmp_path):
    """The conftest's teardown check, for real, in a child pytest: code that
    catches the SessionGuardError does not hide the attempt."""
    shutil.copy(ROOT / 'tests' / 'conftest.py', tmp_path / 'conftest.py')
    shutil.copy(ROOT / 'tests' / 'quiet_session.py', tmp_path / 'quiet_session.py')
    (tmp_path / 'test_inner.py').write_text(textwrap.dedent('''
        import socket


        def test_swallows_it():
            try:
                socket.create_connection(('203.0.113.1', 443), timeout=0.5)
            except OSError:
                pass
    '''), encoding='utf-8')
    env = {**os.environ, 'PYTHONPATH': str(ROOT), 'PYTHONIOENCODING': 'utf-8'}
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', str(tmp_path / 'test_inner.py'), '-q',
         '-p', 'no:cacheprovider'],
        cwd=tmp_path, capture_output=True, text=True, encoding='utf-8', errors='replace',
        env=env, timeout=180)
    out = result.stdout + result.stderr
    assert result.returncode != 0, out
    assert '1 passed, 1 error' in out, out
    assert 'reached outside the test session' in out and '203.0.113.1' in out, out
    assert 'private desktop' in out, out       # the summary line says where windows went
