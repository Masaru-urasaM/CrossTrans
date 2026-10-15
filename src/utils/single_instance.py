"""
Single instance lock for CrossTrans.

The lock is a TCP socket on 127.0.0.1:LOCK_PORT - whoever binds it is the running
instance. It has always been `listen()`ing with nobody ever accepting, so a second
instance could do nothing but fail to bind and then scold the user into hunting
through the system tray. Somebody who double-clicks the icon wants the window, so
the second instance now asks for it and the running one obliges (D4).
"""
import socket
import logging
import threading
from typing import Callable, Optional, Tuple

from src.constants import LOCK_PORT

# What a second instance sends, and what a running instance answers. A token
# rather than a bare connection: the port sits on loopback where any local
# process can reach it, and merely opening a socket must not be enough to throw
# a window onto somebody's screen.
SHOW_REQUEST = b'CROSSTRANS_SHOW\n'
SHOW_ACK = b'CROSSTRANS_OK\n'

# How long each side waits on the other before giving up. Short: the second
# instance is holding up its own exit, and the running one must not let a
# connection that says nothing wedge its accept loop.
SIGNAL_TIMEOUT_S = 1.5


def is_already_running() -> Tuple[bool, Optional[socket.socket]]:
    """Check if another instance is already running using socket lock."""
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.bind(('127.0.0.1', LOCK_PORT))
        lock_socket.listen(1)
        return False, lock_socket
    except socket.error:
        return True, None


def signal_running_instance(timeout: float = SIGNAL_TIMEOUT_S,
                            port: int = LOCK_PORT) -> bool:
    """Ask the instance holding the lock to show itself.

    True only when it acknowledged; False means the caller must fall back to the
    notice dialog. **The acknowledgement is the whole point.** `listen()` has
    been called since long before this function existed, so connecting succeeds
    against an older build too - the connection just lands in the backlog with
    nobody to read it. Waiting for a reply is the only way to tell a version that
    will raise its window from one that will silently swallow the request, and
    without it somebody mid-upgrade would get a second instance that exits
    quietly having done nothing at all. (Seen for real on 2026-09-08 against a
    running 1.9.20: netstat showed the connection in CLOSE_WAIT, accepted by
    nobody.)

    `port` exists for the tests: LOCK_PORT is held by whatever CrossTrans is
    running on the machine, and a suite that reaches for it either skips or
    raises somebody's window mid-run.
    """
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(SHOW_REQUEST)
            return sock.recv(len(SHOW_ACK)) == SHOW_ACK
    except OSError as exc:
        logging.info(f"Could not signal the running instance: {exc}")
        return False


def _answer(conn: socket.socket) -> bool:
    """Read one request and acknowledge it. True if it really was one of ours.

    The acknowledgement goes out **before** the window is raised, so the second
    instance can exit on its own schedule rather than waiting on this one's UI.
    """
    try:
        with conn:
            conn.settimeout(SIGNAL_TIMEOUT_S)
            if conn.recv(len(SHOW_REQUEST)) != SHOW_REQUEST:
                return False               # not ours - answer nothing at all
            conn.sendall(SHOW_ACK)
            return True
    except OSError as exc:
        logging.debug(f"Show request dropped: {exc}")
        return False


def serve_show_requests(lock_socket: socket.socket,
                        on_show: Callable[[], None]) -> threading.Thread:
    """Answer show requests on the lock socket, on a daemon thread.

    The loop ends when the socket closes - `accept()` raises, which is how
    shutdown reaches this thread; it is a daemon besides, so it can never be the
    reason a CrossTrans process outlives its window (the exact failure Decision
    12 was about). Nothing a handler does is allowed to end the loop either: one
    bad connection, or one exception out of the UI callback, must not leave every
    later double-click unanswered.
    """
    def serve() -> None:
        while True:
            try:
                conn, _ = lock_socket.accept()
            except OSError:
                return                     # socket closed: the app is going away
            if not _answer(conn):
                continue
            try:
                on_show()
            except Exception as exc:       # noqa: BLE001 - the loop outlives its handler
                logging.error(f"Show request handler failed: {exc}")

    thread = threading.Thread(target=serve, name='crosstrans-show-server', daemon=True)
    thread.start()
    return thread
