"""
A second CrossTrans asks the running one for its window (D4).

The lock socket on 127.0.0.1:LOCK_PORT has been `listen()`ing since single-instance
detection was written, and nobody ever accepted. That is why launching CrossTrans
twice produced a dialog telling the user to go looking in the system tray, when
what they wanted was plainly the window.

The load-bearing part is the **acknowledgement**. Connecting proves nothing: an
older build accepts into the backlog and then ignores the request forever, so
without a reply the second instance would exit silently having achieved nothing.
Every test below that matters is about telling those two cases apart.
"""
import os
import sys
import socket
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import src.core  # noqa: F401  - before config, see the circular-import note
from src.utils import single_instance as si


@pytest.fixture
def lock():
    """A stand-in lock socket on an ephemeral port.

    Deliberately NOT LOCK_PORT. Whatever CrossTrans is running on the developer's
    machine owns that one, so a suite reaching for it either skips every test
    here or - worse, once the running build understands the request - throws the
    user's window onto the screen in the middle of a test run. Measured while
    writing this: with a real CrossTrans up, nine of these skipped and netstat
    showed the suite's connection sitting in CLOSE_WAIT against it.

    `signal_running_instance` takes `port` for exactly this reason.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    sock.listen(1)
    yield sock, sock.getsockname()[1]
    sock.close()


class TestSignalling:
    def test_it_returns_true_when_the_request_is_acknowledged(self, lock):
        sock, port = lock
        served = threading.Event()
        si.serve_show_requests(sock, served.set)

        assert si.signal_running_instance(port=port) is True
        assert served.wait(timeout=5.0), "the handler never ran"

    def test_it_returns_false_when_nothing_is_listening(self, lock):
        sock, port = lock
        sock.close()        # free the port before anyone can answer on it
        assert si.signal_running_instance(timeout=0.5, port=port) is False

    def test_an_older_build_that_never_answers_is_not_mistaken_for_success(self, lock):
        # THE case this protocol exists for: `listen()` without `accept()`, which
        # is every CrossTrans built before D4. The connection succeeds into the
        # backlog and the send goes through; only the missing reply reveals that
        # nobody is home. Seen for real on 2026-09-08 against the running 1.9.20:
        # netstat showed the connection in CLOSE_WAIT, accepted by nobody.
        _sock, port = lock
        assert si.signal_running_instance(timeout=0.5, port=port) is False

    def test_a_failed_signal_costs_at_most_the_timeout(self, lock):
        import time
        _sock, port = lock
        started = time.monotonic()
        si.signal_running_instance(timeout=0.5, port=port)
        assert time.monotonic() - started < 3.0, "the second instance would feel hung"


class TestServing:
    def test_a_wrong_token_is_ignored_and_unanswered(self, lock):
        listener, port = lock
        calls = []
        si.serve_show_requests(listener, lambda: calls.append(1))

        with socket.create_connection(('127.0.0.1', port), timeout=5.0) as sock:
            sock.settimeout(1.0)
            sock.sendall(b'hello?\n')
            with pytest.raises(OSError):     # no ACK: the port is not a doorbell
                if sock.recv(64) == b'':
                    raise OSError('closed without answering')
        assert calls == [], "a stray local connection must not raise the window"

    def test_the_loop_survives_a_handler_that_raises(self, lock):
        sock, port = lock
        calls = []

        def boom():
            calls.append(1)
            raise RuntimeError("the UI callback blew up")

        si.serve_show_requests(sock, boom)
        assert si.signal_running_instance(port=port) is True
        assert si.signal_running_instance(port=port) is True, "one bad handler killed the loop"
        for _ in range(50):
            if len(calls) == 2:
                break
            threading.Event().wait(0.05)
        assert len(calls) == 2

    def test_it_serves_more_than_once(self, lock):
        sock, port = lock
        calls = []
        si.serve_show_requests(sock, lambda: calls.append(1))
        for _ in range(3):
            assert si.signal_running_instance(port=port) is True
        for _ in range(50):
            if len(calls) == 3:
                break
            threading.Event().wait(0.05)
        assert len(calls) == 3

    def test_the_thread_is_a_daemon(self, lock):
        sock, _port = lock
        thread = si.serve_show_requests(sock, lambda: None)
        assert thread.daemon, "a non-daemon accept loop could strand the process"

    def test_closing_the_socket_ends_the_thread(self, lock):
        sock, _port = lock
        thread = si.serve_show_requests(sock, lambda: None)
        sock.close()
        thread.join(timeout=5.0)
        assert not thread.is_alive(), "shutdown must reach the accept loop"


class TestTheProtocolItself:
    def test_the_request_is_a_token_not_a_bare_connection(self):
        # Loopback is reachable by every local process; opening a socket must
        # not be enough to throw a window onto the user's screen.
        assert si.SHOW_REQUEST.strip() and si.SHOW_REQUEST != b'\n'
        assert si.SHOW_ACK != si.SHOW_REQUEST

    def test_the_timeout_is_short_enough_to_not_feel_hung(self):
        assert 0 < si.SIGNAL_TIMEOUT_S <= 3.0


class TestTheAppSideHandler:
    """`TranslatorApp.on_second_instance` runs on the accept thread.

    Built with `__new__` so no hotkeys, tray icon or Tk root come with it - the
    same trick the furigana window tests use.
    """

    @staticmethod
    def _app():
        from src.app import TranslatorApp
        return TranslatorApp.__new__(TranslatorApp)

    def test_it_touches_tk_only_through_after(self):
        # Called from the socket thread. Anything it did to a widget directly
        # would be a cross-thread Tk call.
        from types import SimpleNamespace
        queued = []
        app = self._app()
        app.root = SimpleNamespace(after=lambda ms, fn: queued.append((ms, fn)))

        app.on_second_instance()

        assert len(queued) == 1 and queued[0][0] == 0

    def test_the_queued_work_raises_the_window_and_says_so(self):
        from types import SimpleNamespace
        from src.app import SECOND_INSTANCE_TOAST, SECOND_INSTANCE_TOAST_MS
        shown, toasts = [], []
        app = self._app()
        app.show_main_window = lambda: shown.append(1)
        app.toast = SimpleNamespace(
            show_info=lambda msg, duration=None: toasts.append((msg, duration)))

        app._raise_for_second_instance()

        assert shown == [1], "the window is the actual answer"
        assert toasts == [(SECOND_INSTANCE_TOAST, SECOND_INSTANCE_TOAST_MS)]

    def test_the_toast_is_about_two_seconds(self):
        from src.app import SECOND_INSTANCE_TOAST_MS
        assert 1000 <= SECOND_INSTANCE_TOAST_MS <= 3000

    def test_a_root_already_gone_is_not_an_error(self):
        # Signalled during shutdown: `after` raises, and the accept loop must
        # not log a handler failure over something entirely expected.
        import tkinter as tk
        from types import SimpleNamespace

        def gone(*_args):
            raise tk.TclError("application has been destroyed")

        app = self._app()
        app.root = SimpleNamespace(after=gone)
        app.on_second_instance()          # must simply return
