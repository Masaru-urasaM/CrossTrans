"""Capture main-window linked reading and whole-popup expansion off screen."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from tools import popup_gallery as gallery


def main():
    gallery.isolate_settings()
    import quiet_session
    quiet_session.install()
    gallery.require_private_desktop(quiet_session.DESKTOP_NAME, quiet_session.DESKTOP_ERROR)
    import tkinter as tk
    import ttkbootstrap as ttk
    from src.core.translation_alignment import reading_result
    from src.ui.quick_translate import QuickTranslateManager
    from src.ui.main_linked_reading import MainLinkedReading
    from src.ui.ruby_text import RubyText, insert_output
    from tests.test_popup_alignment import FakeConfig

    root = ttk.Window(themename='darkly')
    root.withdraw()
    out = ROOT / 'logs/popup_gallery/linked_surfaces'
    out.mkdir(parents=True, exist_ok=True)
    manager = QuickTranslateManager(root, FakeConfig(enabled=True, ruby=True))
    manager._last_mouse_x, manager._last_mouse_y = 800, 400
    source = '\n'.join(f'{i}. Check all document settings before continuing to the next step.' for i in range(1, 13))
    target = '\n'.join(f'{i}. 次の操作に進む前に、文書のすべての設定を確認してください。' for i in range(1, 13))
    manager.show(target, 'Japanese', original=source, model_info='Preview (legacy structural links)')
    gallery.settle(manager, root)
    assert gallery.screenshot(manager.popup, str(out / 'compact.png'))
    before = [manager.popup.winfo_width(), manager.popup.winfo_height()]
    manager._toggle_original()
    gallery.settle(manager, root)
    assert gallery.screenshot(manager.popup, str(out / 'show_all.png'))
    expanded = [manager.popup.winfo_width(), manager.popup.winfo_height()]
    from tkinter import font
    from tests.popup_cases import PopupCase
    metrics = gallery.popup_metrics(manager, PopupCase('expanded', 'expanded', source, target, 'Japanese'),
                                    font.Font(family='Segoe UI', size=11).measure)
    manager._toggle_original()
    root.update()
    assert [manager.popup.winfo_width(), manager.popup.winfo_height()] == before
    assert not metrics['clipped'], metrics['clipped']
    wide_source = '\n'.join('Check the original settings carefully before continuing to the next operation.' for _ in range(20))
    wide_target = '\n'.join('Review the translated document carefully before continuing to the next operation.' for _ in range(20))
    manager.show(wide_target, 'English', original=wide_source, model_info='Preview (width search)')
    gallery.settle(manager, root)
    compact_width = manager.popup.winfo_width()
    manager._toggle_original()
    gallery.settle(manager, root)
    assert manager.popup.winfo_width() > compact_width
    assert gallery.screenshot(manager.popup, str(out / 'show_all_wide.png'))
    wide = [manager.popup.winfo_width(), manager.popup.winfo_height()]
    missing_source = '\n\n'.join(f'Source paragraph {i}. More details.' for i in range(39))
    missing_target = '\n\n'.join(f'Result paragraph {i}. More details.' for i in range(15))
    manager.show(missing_target, 'English', original=missing_source,
                 model_info='Preview (unequal document structures)')
    gallery.settle(manager, root)
    manager.popup_furigana.yview_moveto(0.5)
    manager.popup_text.yview_moveto(0.5)
    root.update()
    assert manager._linked_controller is None
    assert manager._linked_status.cget('text') == 'No reliable links'
    assert gallery.screenshot(manager.popup, str(out / 'no_global_link.png'))
    manager.close()

    window = tk.Toplevel(root)
    window.title('CrossTrans - Linked reading preview')
    window.geometry('950x600+20+20')
    window.configure(bg='#222222')
    ttk.Label(window, text='Original:', font=('Segoe UI', 10)).pack(anchor='w', padx=15, pady=(15, 5))
    original = tk.Text(window, height=8, wrap='word', undo=True, font=('Segoe UI', 11),
                       bg='#303030', fg='#cccccc', relief='flat', padx=10, pady=10)
    original.pack(fill='x', padx=15)
    original.insert('1.0', source)
    original.edit_modified(False)
    header = ttk.Frame(window)
    header.pack(fill='x', padx=15, pady=(15, 5))
    ttk.Label(header, text='Translation:', font=('Segoe UI', 10)).pack(side='left')
    output = RubyText(window, height=10, base_font=('Segoe UI', 11))
    output.pack(fill='both', expand=True, padx=15, pady=(0, 15))
    insert_output(output, '1.0', target, lang_hint='Japanese', enabled=True)
    output.configure(state='disabled')
    reading = MainLinkedReading(root, window, original, output, manager.config, header)
    value = reading_result(target, None, source, 'Japanese')
    reading.set_result(value, source, 'Japanese')
    root.update()
    reading.controller.activate(1, 2)
    for _ in range(8):
        time.sleep(0.02)
        root.update()
    assert gallery.screenshot(window, str(out / 'main_legacy_links.png'))
    window.destroy()
    root.update()
    assert reading.closed
    root.destroy()
    assert not quiet_session.BLOCKED, quiet_session.BLOCKED
    (out / 'metrics.json').write_text(json.dumps({'compact': before, 'expanded': expanded, 'wide': wide,
                                                'popup': metrics}, indent=2), encoding='utf-8')
    print(json.dumps({'compact': before, 'expanded': expanded, 'clipped': metrics['clipped']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
