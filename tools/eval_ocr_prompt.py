"""Measure the screenshot prompt's ===SOURCE LANGUAGE=== on real models (manual - never in CI).

A screenshot of kanji-only text is as ambiguous as a selection, so the vision prompt
(`screenshot_handler.ocr_prompt`, J8) asks the model to name the language of what it
read. This tool draws ten short texts of known language into images - Japanese and
Chinese, with and without the characters that settle it - sends each through the
app's own prompt and `AIAPIManager.translate_multimodal()`, parses the answer with
the app's own `parse_ocr_result()`, and records whether the sections came back,
whether the text was read exactly, and whether the language matches:

    python tools/eval_ocr_prompt.py --label k10 --providers Google --key 3 --confirm-calls 10

Real API calls on the user's own keys: one image per case per provider, through a
vision-capable key - nothing is sent until `--confirm-calls N` names their number
(K12; a run without it prints the number). The tool never writes config.json.
Fonts are Windows' own (Yu Gothic, Microsoft YaHei, Microsoft JhengHei) so each
script draws with real glyphs. Output: logs/eval/ocr_<label>.jsonl; images in
logs/eval/ocr_images/.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (ROOT, os.path.join(ROOT, 'tools')):
    if path not in sys.path:
        sys.path.insert(0, path)

FONTS = {
    'ja': r'C:\Windows\Fonts\YuGothM.ttc',
    'zh-s': r'C:\Windows\Fonts\msyh.ttc',
    'zh-t': r'C:\Windows\Fonts\msjh.ttc',
}

# (text, script for the font, expected language, what settles it)
OCR_CASES = [
    ('今日は日本語を勉強します。', 'ja', 'Japanese', 'kana'),
    ('本日のおすすめ', 'ja', 'Japanese', 'kana'),
    ('営業時間', 'ja', 'Japanese', 'a Japanese-only glyph'),
    ('立入禁止', 'ja', 'Japanese', 'nothing - a sign'),
    ('首相官邸前抗議集会', 'ja', 'Japanese', 'nothing - a headline'),
    ('東京大学', 'ja', 'Japanese', 'nothing - a name'),
    ('我们明天去北京。', 'zh-s', 'Chinese', 'a simplified-only glyph'),
    ('這是我的書。', 'zh-t', 'Chinese', 'two function words (K6)'),
    ('他在大學學習中文。', 'zh-t', 'Chinese', 'nothing'),
    ('今天天氣很好。', 'zh-t', 'Chinese', 'nothing'),
]


def render(text: str, script: str, path: str) -> str:
    """Draw `text` black on white in the script's font; returns `path`."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(FONTS[script], 40)
    left, top, right, bottom = font.getbbox(text)
    image = Image.new('RGB', (right - left + 60, bottom - top + 60), 'white')
    ImageDraw.Draw(image).text((30 - left, 30 - top), text, font=font, fill='black')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    image.save(path)
    return path


def family(language: Optional[str]) -> Optional[str]:
    """'Japanese', 'Chinese' (either script) or the name as given."""
    if not language:
        return None
    return 'Chinese' if language.startswith('Chinese') else language


def score(text: str, expected: str, answer: str) -> dict:
    """What a vision answer says about one case, read with the app's own parser."""
    from src.ui.screenshot_handler import OCR_FALLBACK_ORIGINAL, parse_ocr_result
    original, source, translation = parse_ocr_result(answer or '')
    sections = original != OCR_FALLBACK_ORIGINAL
    return {
        'sections': sections,
        'source_section': '===SOURCE LANGUAGE===' in (answer or ''),
        'read_exactly': sections and original.strip() == text,
        'ocr': original if sections else None,
        'verdict': source,
        'correct': family(source) == expected,
        'translation': translation,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--label', required=True)
    parser.add_argument('--providers', default='Google')
    parser.add_argument('--key', type=int, default=1)
    parser.add_argument('--target', default='English')
    parser.add_argument('--delay', type=float, default=3.0,
                        help='seconds between calls (a free tier allows ~10 a minute)')
    parser.add_argument('--texts', default='', help='comma-separated subset of the cases')
    parser.add_argument('--confirm-calls', type=int, default=None,
                        help='the number of real API calls the run makes, as a run without '
                             'it prints - nothing is sent until it matches (K12)')
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    import logging
    logging.disable(logging.WARNING)
    import src.core  # noqa: F401 - must precede config (circular import)
    from config import Config
    from eval_dictionary_prompt import build_services, confirmed, planned_calls
    from src.ui.screenshot_handler import ocr_prompt

    config = Config()
    wanted = [p.strip() for p in args.providers.split(',') if p.strip()]
    services, _ = build_services(config, wanted, args.key)
    services = [(name, svc) for name, svc in services if name != 'trial']
    if not services:
        print("FAIL: no vision provider to measure")
        return 2

    cases = OCR_CASES
    if args.texts:
        chosen = {t.strip() for t in args.texts.split(',')}
        cases = [case for case in OCR_CASES if case[0] in chosen]
    if not confirmed(planned_calls(services, len(cases)), args.confirm_calls):
        return 3

    out_dir = os.path.join(ROOT, 'logs', 'eval')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'ocr_{args.label}.jsonl')
    rows = []
    with open(out_path, 'a', encoding='utf-8') as out:
        for provider, svc in services:
            for i, (text, script, expected, settles) in enumerate(cases):
                if i or provider != services[0][0]:
                    time.sleep(args.delay)
                image = render(text, script, os.path.join(out_dir, 'ocr_images', f'case{i}.png'))
                started = time.time()
                answer, error = '', None
                try:
                    answer = svc.api_manager.translate_multimodal(ocr_prompt(args.target), [image], {})
                except Exception as exc:  # recorded, never fatal: one bad call
                    error = f'{type(exc).__name__}: {exc}'
                row = {'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                       'label': args.label, 'provider': provider,
                       'model': svc.api_manager.last_attribution, 'text': text,
                       'expected': expected, 'settles': settles,
                       **score(text, expected, answer),
                       'elapsed_s': round(time.time() - started, 2), 'error': error,
                       'raw': answer}
                out.write(json.dumps(row, ensure_ascii=False) + '\n')
                out.flush()
                rows.append(row)
                print(f"[{provider}] {text}: " + (error or
                      f"verdict={row['verdict']} correct={row['correct']} "
                      f"read_exactly={row['read_exactly']}"))

    print(f"\nwrote {len(rows)} rows to {out_path}\n")
    for provider, _svc in services:
        ok = [r for r in rows if r['provider'] == provider and not r['error']]
        print(f"{provider}: {len(ok)} answered, sections {sum(r['sections'] for r in ok)}, "
              f"SOURCE LANGUAGE {sum(r['source_section'] for r in ok)}, "
              f"read exactly {sum(r['read_exactly'] for r in ok)}, "
              f"language correct {sum(r['correct'] for r in ok)}/{len(ok)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
