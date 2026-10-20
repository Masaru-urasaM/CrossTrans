"""Render linked-reading states and measure hover work off the user's desktop."""
import json
from pathlib import Path
import platform
import statistics
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
    import src.core
    import ttkbootstrap as ttk
    from tkinter import font
    from src.core.translation_alignment import AlignedText, parse_answer, segment_source
    from src.ui.quick_translate import QuickTranslateManager
    from tests.test_popup_alignment import FakeConfig
    from tests.popup_cases import PopupCase

    root = ttk.Window(themename='darkly')
    root.withdraw()
    out = ROOT / 'logs/popup_gallery/linked_reading'
    out.mkdir(parents=True, exist_ok=True)
    manager = QuickTranslateManager(root, FakeConfig())
    manager._last_mouse_x, manager._last_mouse_y = 500, 300
    cases = [
        ('plain', 'First sentence. Second sentence.', ['Première phrase.', 'Deuxième phrase.'], 'French', False),
        ('source_ruby', '私は日本語を勉強します。明日は京都へ行きます。', ['I study Japanese.', 'Tomorrow I will go to Kyoto.'], 'English', True),
        ('target_ruby', 'I study Japanese. Tomorrow I will go to Kyoto.', ['私は日本語を勉強します。', '明日は京都へ行きます。'], 'Japanese', True),
        ('ruby_off', '私は日本語を勉強します。明日は京都へ行きます。', ['I study Japanese.', 'Tomorrow I will go to Kyoto.'], 'English', False),
        ('short_lines', 'Quit.\nRun.\nCheck the settings before continuing.',
         ['終了してください。', '実行してください。', '続行する前に設定を確認してください。'], 'Japanese', True),
        ('wrapped_group', 'A short sentence.\nCheck every setting in this document carefully before continuing with the next operation. ' * 3,
         ['短い文です。\n次の操作に進む前に、この文書に記載されているすべての設定を慎重に確認してください。' * 3], 'Japanese', True),
        ('linking_off', 'Select Quit to close the old version.\nRun the test EXE.',
         ['古いバージョンを終了してください。', 'テスト版を実行してください。'], 'Japanese', True),
        ('collapsed_scroll', '\n'.join(f'Line {i}.' for i in range(30)),
         [f'Result {i}.' for i in range(30)], 'English', False),
        ('long_plain_fallback', '\n'.join(['長い文書の設定を確認してから、次の処理に進んでください。'] * 110),
         [f'Check the document settings before the next step ({i}).' for i in range(110)], 'English', True),
    ]
    rows = []
    for name, source, texts, target, ruby in cases:
        manager.config = FakeConfig(enabled=name != 'linking_off', ruby=ruby)
        segments = ([{'source_ids': [unit.id for unit in segment_source(source)], 'text': texts[0]}]
                    if name == 'wrapped_group' else
                    [{'source_ids': [i], 'text': text} for i, text in enumerate(texts, 1)])
        parsed = parse_answer(json.dumps({'version': 1, 'segments': segments}), source, target)
        displayed = parsed.text if name == 'linking_off' else AlignedText(parsed.text, parsed.metadata)
        manager.show(displayed, target, original=source,
                     source_lang='Japanese' if name in ('source_ruby', 'ruby_off') else None,
                     model_info='Preview (synthetic data)')
        gallery.settle(manager, root)
        active_index = (20 if name in ('collapsed_scroll', 'long_plain_fallback') else
                        0 if name == 'wrapped_group' else 1)
        if active_index == 20:
            starts, *_ = manager.popup_text.prepare_plain_map()
            manager.popup_text.see(starts[parsed.metadata['groups'][active_index]['translated'][0]])
            root.update()
        if getattr(manager, '_linked_controller', None) is not None:
            manager._linked_controller.activate(1, active_index)
        for _ in range(8):
            time.sleep(0.02)
            root.update()
        path = out / (name + '.png')
        assert gallery.screenshot(manager.popup, str(path)), 'Screenshot capture failed'
        rows.append(gallery.popup_metrics(manager, PopupCase(name, name, source, parsed.text, target),
                                         font.Font(family='Segoe UI', size=11).measure))
        if name == 'source_ruby':
            box = manager.popup_furigana
            starts, ends, _, _, _ = box.prepare_plain_map()
            box.tag_add('sel', starts[0], ends[2])
            box._on_selection()
            root.update()
            gallery.screenshot(manager.popup, str(out / 'selection.png'))
    timings = []
    controller = manager._linked_controller
    for index in range(200):
        start = time.perf_counter()
        controller.activate(index % 2, index % 2)
        timings.append((time.perf_counter() - start) * 1000)
    rows.append({'benchmark': f'200 alternating hover activations, cached {len(controller.groups)}-group document',
                 'machine': platform.platform(), 'python': platform.python_version(),
                 'median_ms': statistics.median(timings), 'p95_ms': sorted(timings)[189]})
    from src.ui.ruby_text import RubyText
    for length in (3000, 10000, 50000):
        widget = RubyText(root)
        widget.set_plain(('Word. ' * (length // 6 + 1))[:length])
        start = time.perf_counter()
        mapping = widget.prepare_plain_map()
        build_ms = (time.perf_counter() - start) * 1000
        samples = []
        for iteration in range(200):
            at = iteration * 13 % (length - 20)
            start = time.perf_counter()
            widget.highlight_plain_range([at, at + 20])
            samples.append((time.perf_counter() - start) * 1000)
            assert widget.prepare_plain_map() is mapping
        rows.append({'benchmark': 'unmapped plain RubyText; map build versus cached paint handler',
                     'characters': length, 'map_build_ms': build_ms,
                     'paint_p95_ms': sorted(samples)[189], 'iterations': len(samples)})
        widget.destroy()
    manager.close()
    root.destroy()
    assert not quiet_session.BLOCKED, quiet_session.BLOCKED
    (out / 'metrics.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print(json.dumps(rows[-4:]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
