"""
Render every quick-translate popup case and state, and measure it (TODO.md, P0).

    python tools/popup_gallery.py --label before
    python tools/popup_gallery.py --label after --cases A,G,L --no-shots

Writes logs/popup_gallery/<label>/<key>.png and logs/popup_gallery/<label>.json and
prints one line per case. The cases are tests/popup_cases.py - the same ones the popup
geometry tests use.

Nothing reaches the user's screen: before any window exists, the Tk thread moves to a
desktop no monitor shows (tests/quiet_session.py, Decision 32), and the tool refuses to
run if it cannot. No network and no API call - the texts are fixed - and APPDATA points
at a scratch folder, so the user's settings are neither read nor written. The images
come from PrintWindow(PW_RENDERFULLCONTENT), which works on that desktop. A run that
reached for the network, the clipboard or the keyboard, or left a window on the user's
desktop, exits 1.
"""
import argparse
import ctypes
import json
import os
import platform
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(REPO, 'tests')
OUT_ROOT = os.path.join(REPO, 'logs', 'popup_gallery')
CLOSE_TEXT = chr(0x2715)                     # the popup's close button


# --------------------------------------------------------------------------- #
# Safety
# --------------------------------------------------------------------------- #
def require_private_desktop(desktop_name, error):
    """Exit unless the Tk thread is on the private desktop: never draw on the user's screen."""
    if not desktop_name:
        raise SystemExit(f"popup_gallery: no private desktop ({error}) - refusing to draw on "
                         f"the screen")


def isolate_settings():
    """Point APPDATA at a scratch folder. Must run before `src` is imported: `config`
    reads APPDATA when it is imported. Python's own user site-packages were settled at
    start-up, so imports are unaffected."""
    scratch = tempfile.mkdtemp(prefix='popup-gallery-')
    os.environ['APPDATA'] = scratch
    return scratch


# --------------------------------------------------------------------------- #
# Measuring (no Tk import here: these take the widgets they are given)
# --------------------------------------------------------------------------- #
def _first(value):
    """Text.count() returns a tuple, a bare int or None, depending on the Tk build."""
    if isinstance(value, tuple):
        return value[0]
    return value or 0


def content_box(widget, axis):
    """A Text widget's content size: its size less border, highlight and padding."""
    size = widget.winfo_height() if axis == 'y' else widget.winfo_width()
    pad = int(widget.cget('pady' if axis == 'y' else 'padx'))
    edge = int(widget.cget('borderwidth')) + int(widget.cget('highlightthickness'))
    return size - 2 * (edge + pad)


def chars_per_line(widget, text):
    """Characters per display line in the worst paragraph: every logical line's length
    over the display lines Tk wrapped it into - an unwrapped line counts whole - and the
    largest of those. `text` is the widget's plain text (`get_plain()`), so a ruby frame
    counts as the characters it shows."""
    worst = 0.0
    for number, line in enumerate(text.split('\n'), start=1):
        rows = _first(widget.count(f'{number}.0', f'{number}.end', 'update', 'displaylines')) + 1
        worst = max(worst, len(line) / rows)
    return round(worst, 1)


def box_metrics(widget, text, measure):
    """How tall a text box is against how tall its content is, and how its lines run."""
    given = content_box(widget, 'y')
    needed = _first(widget.count('1.0', 'end', 'update', 'ypixels'))
    lines = _first(widget.count('1.0', 'end -1c', 'update', 'displaylines')) + 1
    width = content_box(widget, 'x')
    widest = max((measure(line) for line in text.split('\n')), default=0)
    return {'given': given, 'needed': needed, 'blank': max(0, given - needed),
            'hidden': max(0, needed - given), 'lines': lines, 'width': width,
            'widest_line': min(widest, width), 'chars_per_line': chars_per_line(widget, text)}


def descendants(widget, into_text=True):
    """Every widget under `widget`, depth first. `into_text=False` stops at Text widgets:
    their children are embedded windows (ruby frames), mapped and unmapped as the text
    scrolls - part of the content, not of the layout."""
    for child in widget.winfo_children():
        yield child
        if into_text or child.winfo_class() != 'Text':
            yield from descendants(child, into_text)


def widget_text(widget):
    try:
        return widget.cget('text')
    except Exception:
        return None


def find_close_button(popup):
    """The popup's close button, wherever the layout puts it - or None."""
    return next((w for w in descendants(popup) if widget_text(w) == CLOSE_TEXT), None)


def close_button_metrics(popup):
    """Is the close button drawn, at its full width, inside the popup? (TODO.md S1)"""
    button = find_close_button(popup)
    if button is None:
        return {'found': False, 'shown': False, 'full_width': False, 'inside': False}
    shown = bool(button.winfo_ismapped()) and button.winfo_width() > 1
    right = button.winfo_rootx() + button.winfo_width()
    return {'found': True, 'shown': shown,
            'full_width': button.winfo_width() >= button.winfo_reqwidth(),
            'inside': shown and right <= popup.winfo_rootx() + popup.winfo_width()}


def too_narrow_for_its_text(widget):
    """A label or button whose `width` option, in characters, is shorter than its text:
    the text is cut inside the widget at any popup width ("Get Free API Key" in a
    14-character button, TODO.md S2)."""
    text = widget_text(widget)
    try:
        width = int(widget.cget('width') or 0)
    except Exception:
        return False
    return bool(text) and width > 0 and len(text) > width


def clipped_controls(popup):
    """Buttons and labels cut off: squeezed out or narrower than they asked to be at the
    popup's edge (TODO.md S1), or given fewer characters than their text (S2)."""
    found = []
    for widget in descendants(popup, into_text=False):
        if widget.winfo_class() not in ('Button', 'TButton', 'Label', 'TLabel'):
            continue
        try:
            widget.pack_info()
        except Exception:
            continue                        # not packed (a ruby label inside a frame, ...)
        if (not widget.winfo_ismapped() or widget.winfo_width() < widget.winfo_reqwidth()
                or too_narrow_for_its_text(widget)):
            found.append(widget_text(widget))
    return found


def popup_metrics(manager, popup_case, measure):
    """Everything TODO.md §4 reports about one popup."""
    popup = manager.popup
    width, height = popup.winfo_width(), popup.winfo_height()
    x, y = popup.winfo_x(), popup.winfo_y()
    ax, ay = manager._last_mouse_x, manager._last_mouse_y
    row = {'key': popup_case.key, 'name': popup_case.name, 'state': popup_case.state,
           'size': [width, height], 'pos': [x, y], 'anchor': [ax, ay],
           'covers_anchor': x <= ax < x + width and y <= ay < y + height,
           'translation': box_metrics(manager.popup_text, manager.popup_text.get_plain(),
                                      measure),
           'close_button': close_button_metrics(popup),
           'clipped': clipped_controls(popup)}
    source = getattr(manager, 'popup_furigana', None)
    if source is not None and source.winfo_exists():
        row['original'] = box_metrics(source, source.get_plain(), measure)
    boxes = [row['translation']] + ([row['original']] if 'original' in row else [])
    row['chrome_px'] = height - sum(box['given'] for box in boxes)
    shown_text = sum(box['widest_line'] * min(box['needed'], box['given']) for box in boxes)
    row['text_covers_pct'] = round(100 * shown_text / max(1, width * height), 1)
    return row


def screenshot(popup, path):
    """PrintWindow (PW_RENDERFULLCONTENT) into a PNG - works on the private desktop.
    Returns False when Pillow is missing or Windows refused."""
    try:
        from PIL import Image
    except ImportError:
        return False
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    hwnd = int(popup.wm_frame(), 16)
    width, height = popup.winfo_width(), popup.winfo_height()
    window_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    gdi32.SelectObject(memory_dc, bitmap)
    printed = user32.PrintWindow(hwnd, memory_dc, 2)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [('biSize', ctypes.c_uint32), ('biWidth', ctypes.c_int32),
                    ('biHeight', ctypes.c_int32), ('biPlanes', ctypes.c_uint16),
                    ('biBitCount', ctypes.c_uint16), ('biCompression', ctypes.c_uint32),
                    ('biSizeImage', ctypes.c_uint32), ('biXPelsPerMeter', ctypes.c_int32),
                    ('biYPelsPerMeter', ctypes.c_int32), ('biClrUsed', ctypes.c_uint32),
                    ('biClrImportant', ctypes.c_uint32)]

    header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), width, -height, 1, 32,
                              0, 0, 0, 0, 0, 0)
    pixels = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(memory_dc, bitmap, 0, height, pixels, ctypes.byref(header), 0)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory_dc)
    user32.ReleaseDC(hwnd, window_dc)
    Image.frombuffer('RGB', (width, height), pixels, 'raw', 'BGRX', 0, 1).save(path)
    return bool(printed)


def settle(manager, root, timeout=2.0, compose_s=0.15):
    """Run the event loop until the popup is measured and shown, then give the desktop
    compositor a moment: an image taken earlier can still hold the previous drawing."""
    import time
    root.update_idletasks()
    root.update()
    deadline = time.perf_counter() + timeout
    while (manager.popup is not None and getattr(manager, '_layout', None) is not None
           and not manager._layout.get('revealed') and time.perf_counter() < deadline):
        time.sleep(0.005)
        root.update()
    end = time.perf_counter() + compose_s
    while time.perf_counter() < end:
        time.sleep(0.01)
        root.update()


def summary_line(row):
    t = row['translation']
    close = row['close_button']
    line = (f"{row['key']:<10} {row['size'][0]:>4}x{row['size'][1]:<4} "
            f"box {t['given']:>4}/{t['needed']:<4} blank {t['blank']:>3} hidden {t['hidden']:>3} "
            f"| {t['lines']:>3} lines, {t['chars_per_line']:>5} ch/line "
            f"| text {row['text_covers_pct']:>5}% | x {'ok' if close['inside'] else 'MISSING'}"
            f"{' | over the cursor' if row['covers_anchor'] else ''}")
    if 'original' in row:
        o = row['original']
        line += (f"\n{'':<10} original {o['given']:>4}/{o['needed']:<4} blank {o['blank']:>3} "
                 f"hidden {o['hidden']:>3}")
    if row['clipped']:
        line += f"\n{'':<10} clipped: {row['clipped']}"
    return line


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #
def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument('--label', required=True, help="names the output, e.g. before / after")
    parser.add_argument('--cases', help="comma-separated keys (default: every case and state)")
    parser.add_argument('--no-shots', action='store_true', help="metrics only, no images")
    return parser.parse_args(argv)


def git_commit():
    try:
        return subprocess.run(['git', '-C', REPO, 'rev-parse', '--short', 'HEAD'],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return None


def main(argv=None):
    args = parse_args(argv)
    isolate_settings()
    sys.path[:0] = [REPO, TESTS]
    import quiet_session
    quiet_session.install()
    require_private_desktop(quiet_session.DESKTOP_NAME, quiet_session.DESKTOP_ERROR)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)      # as main.py does
    except Exception:
        pass

    import src.core  # noqa: F401  - must precede `config` (project CLAUDE.md)
    import ttkbootstrap as ttk
    from tkinter import font
    from src.core import furigana
    from src.ui.quick_translate import QuickTranslateManager
    import popup_cases

    wanted = set(args.cases.split(',')) if args.cases else None
    cases = [c for c in popup_cases.ALL_CASES if wanted is None or c.key in wanted]
    if not cases:
        raise SystemExit(f"popup_gallery: no case matches {args.cases!r}")

    root = ttk.Window(themename='darkly')                   # the app's theme
    root.withdraw()
    measure = font.Font(family='Segoe UI', size=11).measure
    manager = QuickTranslateManager(root, popup_cases.FakeConfig())
    manager._last_mouse_x = root.winfo_screenwidth() // 2
    manager._last_mouse_y = root.winfo_screenheight() // 3
    shots_dir = os.path.join(OUT_ROOT, args.label)
    if not args.no_shots:
        os.makedirs(shots_dir, exist_ok=True)

    rows = []
    for popup_case in cases:
        furigana.clear_cache()
        popup_cases.show_case(manager, popup_case)
        settle(manager, root)
        row = popup_metrics(manager, popup_case, measure)
        if not args.no_shots:
            row['image'] = os.path.relpath(os.path.join(shots_dir, f'{popup_case.key}.png'), REPO)
            screenshot(manager.popup, os.path.join(REPO, row['image']))
        rows.append(row)
        print(summary_line(row))
        manager.close()
        root.update()

    on_user_desktop = quiet_session.our_windows_on('Default')
    report = {'label': args.label, 'commit': git_commit(),
              'python': platform.python_version(), 'tk': root.tk.call('info', 'patchlevel'),
              'screen': [root.winfo_screenwidth(), root.winfo_screenheight()],
              'dpi': round(root.winfo_fpixels('1i')), 'cases': rows,
              'blocked': [what for _, what in quiet_session.BLOCKED],
              'windows_on_user_desktop': len(on_user_desktop)}
    os.makedirs(OUT_ROOT, exist_ok=True)
    out = os.path.join(OUT_ROOT, f'{args.label}.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    root.destroy()
    print(f"\n{len(rows)} popups -> {os.path.relpath(out, REPO)}"
          f"{'' if args.no_shots else ' and ' + os.path.relpath(shots_dir, REPO)}")
    if report['blocked'] or on_user_desktop:
        print(f"popup_gallery: FAILED - blocked calls {report['blocked']}, "
              f"{len(on_user_desktop)} window(s) on the user's desktop")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
