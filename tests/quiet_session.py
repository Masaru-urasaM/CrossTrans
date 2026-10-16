"""Keep a test run off the user's session: no window on their screen, no focus
taken, no network - so no API quota spent - and no clipboard, keystroke, hotkey,
browser or registry writes (K12, Decision 32).

Until 2026-10-16 the suite drew its windows on the developer's own screen. The
app raises its windows on purpose - `lift()`, `focus_force()`, `-topmost` - so
every popup, dialog and 1400x850 main window a test built took the keyboard
focus from whatever the developer was doing: once per test, dozens of times per
mutation check. Nothing stopped a test from reaching a real API on the
developer's keys either, nor from overwriting their clipboard (one test did, on
every run).

`conftest.py` calls `install()` before any test module is imported:

- **A private desktop for the Tk thread.** `CreateDesktopW` + `SetThreadDesktop`
  move the main thread - the one Tk runs on - to a desktop of its own. Windows
  there are real: mapped, laid out, measured, focused and topmost all work
  (measured 2026-10-16), but no screen shows that desktop, so nothing appears
  and the user's focus never moves. `SwitchDesktop` is never called - that is
  what would show it. Threads started afterwards land there too (measured).
  It has to come first: `SetThreadDesktop` fails once the thread owns a window
  or a hook. Without it, creating Tk skips the test, naming why, rather than
  draw on the screen - except on CI, where no one is in front of it, or when
  CROSSTRANS_TESTS_ON_SCREEN=1 asks for the screen.
- **No network but loopback.** Connecting anywhere else, or to the lock port of
  the CrossTrans the developer is running, is refused - so no test can spend API
  quota. Real model calls belong to tools/eval_*.py, run by hand with the user's
  go-ahead.
- **No clipboard, keystroke, hotkey, browser or registry writes.** Desktops
  share one clipboard, so the private desktop does not protect it: Tk's
  `clipboard` command is replaced by an in-memory one, and the Python routes to
  the real clipboard raise, like the other calls in the tables below.

A refused call raises SessionGuardError - an OSError, which is what code coping
with an offline machine or a busy clipboard expects - and is recorded, so a test
whose code swallowed the error still fails, naming what it reached for.
"""
import contextlib
import ctypes
import functools
import importlib
import ipaddress
import os
import socket
import sys
import threading

import pytest

ON_SCREEN_ENV = 'CROSSTRANS_TESTS_ON_SCREEN'
REAL_CLIPBOARD_ENV = 'CROSSTRANS_TESTS_REAL_CLIPBOARD'

DESKTOP_NAME = None         # the private desktop this run's Tk thread is on
DESKTOP_ERROR = None        # why there is none
LOCK_PORT = None            # src.constants.LOCK_PORT, read by install()
BLOCKED = []                # (test id or None, what it reached for), in order
CURRENT_TEST = None         # set by conftest around each test

_ORIGINALS = {}             # (owner, attribute) -> what install() replaced
_CLIPBOARD_KEYS = []        # the (owner, attribute) pairs `real_clipboard` hands back
_DESKTOP_HANDLES = []       # kept open for the life of the process
_UNSET = object()

GENERIC_ALL = 0x10000000
DESKTOP_READOBJECTS = 0x0001
DESKTOP_ENUMERATE = 0x0040
UOI_NAME = 2

_KEYSTROKES = "keystrokes, which go to the user's focused window"
_CLIPBOARD = "the user's clipboard"

# (module, attribute, what calling it would have done to the user's session)
ACTION_GUARDS = (
    ('keyboard', 'send', _KEYSTROKES),
    ('keyboard', 'press_and_release', _KEYSTROKES),
    ('keyboard', 'press', _KEYSTROKES),
    ('keyboard', 'release', _KEYSTROKES),
    ('keyboard', 'write', _KEYSTROKES),
    ('keyboard', 'add_hotkey', 'a global hotkey'),
    ('keyboard', 'hook', 'a global keyboard hook'),
    ('keyboard', 'on_press', 'a global keyboard hook'),
    ('keyboard', 'on_release', 'a global keyboard hook'),
    ('webbrowser', 'open', 'a browser window'),
    ('webbrowser', 'open_new', 'a browser window'),
    ('webbrowser', 'open_new_tab', 'a browser window'),
    ('os', 'startfile', 'a file opened in its application'),
    ('winreg', 'SetValueEx', 'a registry write'),
    ('winreg', 'SetValue', 'a registry write'),
    ('winreg', 'DeleteValue', 'a registry write'),
    ('winreg', 'DeleteKey', 'a registry write'),
)
CLIPBOARD_GUARDS = (
    ('pyperclip', 'copy', _CLIPBOARD),
    ('win32clipboard', 'EmptyClipboard', _CLIPBOARD),
    ('win32clipboard', 'SetClipboardData', _CLIPBOARD),
    ('win32clipboard', 'SetClipboardText', _CLIPBOARD),
)
# On `ctypes.windll.user32`, the instance the app calls them through.
USER32_GUARDS = (
    ('SendInput', _KEYSTROKES),
    ('keybd_event', _KEYSTROKES),
    ('RegisterHotKey', 'a global hotkey'),
)

# Tk's `clipboard` command, kept in memory. Every write Tk makes goes through
# it - Python's clipboard_clear/append and the text and entry bindings alike.
_FAKE_TK_CLIPBOARD = r'''
namespace eval ::crosstrans_clipboard {
    variable data {}
    variable owned 0
}
rename ::clipboard ::crosstrans_clipboard::real
proc ::clipboard {option args} {
    upvar #0 ::crosstrans_clipboard::data data ::crosstrans_clipboard::owned owned
    switch -- $option {
        clear {
            set data {}
            set owned 1
        }
        append {
            append data [lindex $args end]
            set owned 1
        }
        get {
            if {!$owned} {
                return -code error {CLIPBOARD selection doesn't exist or form "STRING" not defined}
            }
            return $data
        }
        default {
            return -code error "bad option \"$option\": must be append, clear, or get"
        }
    }
    return
}
'''
_USE_REAL_TK_CLIPBOARD = ('rename ::clipboard ::crosstrans_clipboard::fake; '
                          'rename ::crosstrans_clipboard::real ::clipboard')
_USE_FAKE_TK_CLIPBOARD = ('rename ::clipboard ::crosstrans_clipboard::real; '
                          'rename ::crosstrans_clipboard::fake ::clipboard')


class SessionGuardError(OSError):
    """A test reached outside the test session."""


def block(what):
    """Record `what` against the running test and refuse it."""
    BLOCKED.append((CURRENT_TEST, what))
    raise SessionGuardError(f"refused during tests: {what}")


@contextlib.contextmanager
def expect_blocked():
    """For tests of the guards themselves: yields the list of what was refused
    inside the block, which is then not held against the test."""
    first = len(BLOCKED)
    seen = []
    try:
        yield seen
    finally:
        seen.extend(what for _test, what in BLOCKED[first:])
        del BLOCKED[first:]


# --------------------------------------------------------------------------- #
# The private desktop
# --------------------------------------------------------------------------- #
if sys.platform == 'win32':
    from ctypes import wintypes as _wt
    _ENUM_PROC = ctypes.WINFUNCTYPE(_wt.BOOL, _wt.HWND, _wt.LPARAM)


@functools.lru_cache(maxsize=None)
def _user32():
    """A user32 of our own: the argtypes set here must not leak into the app's
    `ctypes.windll.user32`, and its guards must not refuse our own calls."""
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.CreateDesktopW.restype = _wt.HANDLE
    user32.CreateDesktopW.argtypes = [_wt.LPCWSTR, _wt.LPCWSTR, ctypes.c_void_p, _wt.DWORD,
                                      _wt.DWORD, ctypes.c_void_p]
    user32.OpenDesktopW.restype = _wt.HANDLE
    user32.OpenDesktopW.argtypes = [_wt.LPCWSTR, _wt.DWORD, _wt.BOOL, _wt.DWORD]
    user32.SetThreadDesktop.restype = _wt.BOOL
    user32.SetThreadDesktop.argtypes = [_wt.HANDLE]
    user32.GetThreadDesktop.restype = _wt.HANDLE
    user32.GetThreadDesktop.argtypes = [_wt.DWORD]
    user32.CloseDesktop.argtypes = [_wt.HANDLE]
    user32.GetUserObjectInformationW.restype = _wt.BOOL
    user32.GetUserObjectInformationW.argtypes = [_wt.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                 _wt.DWORD, ctypes.POINTER(_wt.DWORD)]
    user32.EnumDesktopWindows.argtypes = [_wt.HANDLE, _ENUM_PROC, _wt.LPARAM]
    user32.GetWindowThreadProcessId.argtypes = [_wt.HWND, ctypes.POINTER(_wt.DWORD)]
    user32.GetForegroundWindow.restype = _wt.HWND
    user32.GetClipboardOwner.restype = _wt.HWND
    return user32


def _owner_pid(hwnd):
    pid = _wt.DWORD()
    _user32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def thread_desktop_name():
    """The desktop the calling thread is on - 'Default' is the user's own."""
    user32 = _user32()
    handle = user32.GetThreadDesktop(ctypes.WinDLL('kernel32').GetCurrentThreadId())
    name = ctypes.create_unicode_buffer(256)
    needed = _wt.DWORD()
    if not user32.GetUserObjectInformationW(handle, UOI_NAME, name, ctypes.sizeof(name),
                                            ctypes.byref(needed)):
        return None
    return name.value


def enter_private_desktop():
    """Move the calling thread - the Tk thread - to a desktop no screen shows."""
    global DESKTOP_NAME, DESKTOP_ERROR
    if sys.platform != 'win32':
        DESKTOP_ERROR = 'not Windows'
        return
    if os.environ.get(ON_SCREEN_ENV) == '1':
        DESKTOP_ERROR = f'{ON_SCREEN_ENV}=1 asked for the screen'
        return
    user32 = _user32()
    name = f'crosstrans-tests-{os.getpid()}'
    handle = user32.CreateDesktopW(name, None, None, 0, GENERIC_ALL, None)
    if not handle:
        DESKTOP_ERROR = f'CreateDesktopW failed, Windows error {ctypes.get_last_error()}'
        return
    if not user32.SetThreadDesktop(handle):
        DESKTOP_ERROR = (f'SetThreadDesktop failed, Windows error {ctypes.get_last_error()} '
                         f'- the thread already owned a window or a hook')
        user32.CloseDesktop(handle)
        return
    if thread_desktop_name() != name:
        DESKTOP_ERROR = 'SetThreadDesktop succeeded but the thread is on another desktop'
        return
    _DESKTOP_HANDLES.append(handle)
    DESKTOP_NAME = name


def windows_allowed(desktop=_UNSET, environ=None):
    """May a test create Tk windows? On the private desktop, yes. On the user's
    screen only on CI, where no one is in front of it, or when asked for."""
    desktop = DESKTOP_NAME if desktop is _UNSET else desktop
    environ = os.environ if environ is None else environ
    return bool(desktop) or environ.get(ON_SCREEN_ENV) == '1' or bool(environ.get('CI'))


def real_clipboard_allowed(environ=None):
    """May a test write the Windows clipboard? On CI, where no one's clipboard is
    there to lose, or when asked for - never by default."""
    environ = os.environ if environ is None else environ
    return bool(environ.get('CI')) or environ.get(REAL_CLIPBOARD_ENV) == '1'


def skip_reason():
    return (f"no private desktop for Tk windows ({DESKTOP_ERROR}), and they are not drawn "
            f"on the user's screen - set {ON_SCREEN_ENV}=1 to run them there anyway")


def describe():
    """One line on where this run's windows go, for the terminal summary."""
    if DESKTOP_NAME:
        where = f"Tk windows on the private desktop {DESKTOP_NAME}"
    elif windows_allowed():
        where = f"Tk windows ON THE SCREEN ({DESKTOP_ERROR})"
    else:
        where = f"Tk tests skipped ({DESKTOP_ERROR})"
    return (f"{where}; network, clipboard, keystrokes, hotkeys, browser and "
            f"registry writes refused")


def our_windows_on(desktop_name='Default'):
    """This process's top-level windows on `desktop_name` - the user's desktop by
    default, where no window of a test may ever be."""
    user32 = _user32()
    handle = user32.OpenDesktopW(desktop_name, 0, False, DESKTOP_READOBJECTS | DESKTOP_ENUMERATE)
    if not handle:
        raise OSError(f"cannot open desktop {desktop_name!r}: Windows error "
                      f"{ctypes.get_last_error()}")
    mine = []

    def visit(hwnd, _lparam):
        if _owner_pid(hwnd) == os.getpid():
            mine.append(hwnd)
        return True
    try:
        user32.EnumDesktopWindows(handle, _ENUM_PROC(visit), 0)
    finally:
        user32.CloseDesktop(handle)
    return mine


def foreground_pid(desktop_name='Default'):
    """The process that owns the foreground window of `desktop_name`, read from a
    thread attached to that desktop - every other thread of this process is on
    the private one, and sees no foreground window at all."""
    result = {}

    def look():
        user32 = _user32()
        handle = user32.OpenDesktopW(desktop_name, 0, False,
                                     DESKTOP_READOBJECTS | DESKTOP_ENUMERATE)
        if not handle or not user32.SetThreadDesktop(handle):
            result['error'] = (f"cannot attach to desktop {desktop_name!r}: Windows error "
                               f"{ctypes.get_last_error()}")
            return
        result['pid'] = _owner_pid(user32.GetForegroundWindow())

    thread = threading.Thread(target=look, daemon=True)
    thread.start()
    thread.join(10)
    if 'error' in result:
        raise OSError(result['error'])
    return result.get('pid', 0)


def clipboard_owner_pid():
    """The process that last wrote the Windows clipboard (0 when none did)."""
    return _owner_pid(_user32().GetClipboardOwner())


# --------------------------------------------------------------------------- #
# The guards
# --------------------------------------------------------------------------- #
def is_loopback(host):
    """True for this machine: loopback addresses, 'localhost', and no host."""
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode('ascii', 'replace')
    host = str(host)
    if host.lower() in ('', 'localhost', '0.0.0.0'):
        return True
    try:
        return ipaddress.ip_address(host.split('%', 1)[0]).is_loopback
    except ValueError:
        return False


def check_address(address, lock_port):
    """None when a test may connect to `address`, else what to report."""
    if not (isinstance(address, tuple) and len(address) >= 2):
        return None                         # AF_UNIX and the like: not the network
    host, port = address[0], address[1]
    if not is_loopback(host):
        return (f"the network ({host}:{port}) - mock the call; real API calls belong "
                f"in tools/eval_*.py, run by hand with the user's go-ahead")
    if port == lock_port:
        return (f"127.0.0.1:{port}, the lock of the CrossTrans the developer is "
                f"running - pass port= instead")
    return None


def _replace(owner, attribute, replacement):
    _ORIGINALS[(owner, attribute)] = getattr(owner, attribute)
    setattr(owner, attribute, replacement)


def _refusal(what):
    def refused(*_args, **_kwargs):
        block(what)
    refused.quiet_guard = what
    return refused


def is_guard(function):
    """True when `function` is one of the refusals installed here."""
    return hasattr(function, 'quiet_guard')


def _guard_network(lock_port):
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def connect(self, address):
        problem = check_address(address, lock_port)
        if problem:
            block(problem)
        return real_connect(self, address)

    def connect_ex(self, address):
        problem = check_address(address, lock_port)
        if problem:
            block(problem)
        return real_connect_ex(self, address)

    def getaddrinfo(host, port, *args, **kwargs):
        if not is_loopback(host):
            block(f"the network (a lookup of {host}) - mock the call; real API calls "
                  f"belong in tools/eval_*.py, run by hand with the user's go-ahead")
        return real_getaddrinfo(host, port, *args, **kwargs)

    for function in (connect, connect_ex, getaddrinfo):
        function.quiet_guard = 'the network'
    _replace(socket.socket, 'connect', connect)
    _replace(socket.socket, 'connect_ex', connect_ex)
    _replace(socket, 'getaddrinfo', getaddrinfo)


def wants_windows(args, kwargs):
    """Whether Tk(*args, **kwargs) is a real Tk: tkinter.Tcl() is
    Tk(None, None, 'Tk', False), an interpreter with no windows at all."""
    return bool(kwargs.get('useTk', args[3] if len(args) > 3 else True))


def _guard_tk():
    """Every Tk interpreter: refused without a desktop to put it on, and given
    the in-memory clipboard."""
    import tkinter
    real_init = tkinter.Tk.__init__

    def init(self, *args, **kwargs):
        windows = wants_windows(args, kwargs)
        if windows and not windows_allowed():
            pytest.skip(skip_reason())
        real_init(self, *args, **kwargs)
        if windows:
            fake_tk_clipboard(self)
    _replace(tkinter.Tk, '__init__', init)


def fake_tk_clipboard(root):
    """Give `root`'s interpreter the in-memory clipboard (idempotent)."""
    if not tk_clipboard_is_fake(root):
        root.tk.eval(_FAKE_TK_CLIPBOARD)


def tk_clipboard_is_fake(root):
    return bool(root.tk.call('info', 'procs', '::clipboard'))


@contextlib.contextmanager
def real_clipboard(root):
    """The Windows clipboard for the duration - Tk's command and the Python
    routes alike. Only the `real_clipboard` fixture should need this."""
    root.tk.eval(_USE_REAL_TK_CLIPBOARD)
    guards = [(key, getattr(*key)) for key in _CLIPBOARD_KEYS]
    for (owner, attribute), _guard in guards:
        setattr(owner, attribute, _ORIGINALS[(owner, attribute)])
    try:
        yield
    finally:
        for (owner, attribute), guard in guards:
            setattr(owner, attribute, guard)
        root.tk.eval(_USE_FAKE_TK_CLIPBOARD)


def _import(name):
    try:
        return importlib.import_module(name)
    except ImportError:
        return None


def install():
    """Everything above, once, before any test module is imported."""
    global LOCK_PORT
    if _ORIGINALS:
        return
    enter_private_desktop()                 # first: no window or hook may exist yet
    from src.constants import LOCK_PORT as lock_port
    LOCK_PORT = lock_port
    _guard_network(lock_port)
    _guard_tk()
    for table in (ACTION_GUARDS, CLIPBOARD_GUARDS):
        for module_name, attribute, what in table:
            module = _import(module_name)
            if module is None or not hasattr(module, attribute):
                continue
            if module_name == 'pyperclip':
                # Settle pyperclip's mechanism now: its lazy first call rebinds
                # `copy` and would quietly undo the guard.
                try:
                    module.copy, module.paste = module.determine_clipboard()
                except Exception:
                    pass
            _replace(module, attribute, _refusal(what))
            if table is CLIPBOARD_GUARDS:
                _CLIPBOARD_KEYS.append((module, attribute))
    if sys.platform == 'win32':
        user32 = ctypes.windll.user32
        for attribute, what in USER32_GUARDS:
            _replace(user32, attribute, _refusal(what))
