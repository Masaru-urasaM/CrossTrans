"""Measure what real models answer to the dictionary and translation prompts (manual - never run in CI).

A kanji-only headword is ambiguous on its own: 手紙 is "letter" in Japanese and
"toilet paper" in Chinese. The dictionary prompt used to send such a word with
no source language and no context, and a model that read it as Chinese turned the
whole entry Chinese - and switched its furigana off. This tool sends ten such
false friends through `TranslationService.dictionary_lookup()` - the real prompt
code, not a copy - on each provider configured in Settings, and records what came
back, so a prompt change is judged on measurements rather than on one lookup.

    python tools/eval_dictionary_prompt.py --label before
    python tools/eval_dictionary_prompt.py --label after --condition source-context
    python tools/eval_dictionary_prompt.py --label after --providers Groq,trial

Conditions (what the lookup is told besides the headword):
    bare            nothing - the headword alone
    context         the Japanese sentence it came from; the model decides the language
    source-context  the sentence, and that the source language is Japanese
Only `bare` exists before the prompt learned source and context; the tool says so
rather than silently measuring something else.

`--mode translate` sends each headword alone through `translate_or_fix()` instead -
what a language hotkey does with a selection - and records whether the answer
began with the `[[SOURCE: ...]]` line the prompt asks for on ambiguous kanji-only
text (Phase J4), which language it named, and the sense of the translation:

    python tools/eval_dictionary_prompt.py --mode translate --label before --key 2
    python tools/eval_dictionary_prompt.py --mode translate --label after --key 2

`--key N` measures each provider's N-th configured key (a free key whose daily
quota is spent answers nothing but 429s).

Real API calls, on the user's own keys: one call per word per provider. `trial`
goes through the trial proxy and spends this device's daily trial quota, so it is
never in the default provider list. The tool never writes config.json - provider
health, history and the local trial counter are left alone.

Output: logs/eval/dictionary_<label>.jsonl (translate mode: translate_<label>.jsonl),
one JSON object per call, including the raw answer so a surprising verdict can be
read in full.
"""
import argparse
import hashlib
import inspect
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# (headword, Japanese context sentence, Japanese-sense keywords, Chinese-sense
# keywords). Keywords are matched as whole words in the English translation; they
# give a first-pass verdict only - the summary prints every translation so the
# verdict can be checked by eye.
EVAL_WORDS = [
    ('手紙', '友達に手紙を書きました。', ['letter'], ['toilet paper', 'tissue']),
    ('勉強', '毎日日本語を勉強しています。', ['study', 'studying', 'learning'],
     ['reluctant', 'reluctantly', 'force oneself', 'grudging', 'grudgingly', 'barely']),
    ('大丈夫', '体調はもう大丈夫です。', ['all right', 'alright', 'okay', 'ok', 'fine', 'safe'],
     ['true man', 'real man', 'manly', 'gentleman', 'hero', 'great man']),
    ('新聞', '毎朝新聞を読みます。', ['newspaper', 'newspapers'], ['news']),
    ('汽車', '昔は汽車で旅行しました。', ['train', 'steam train', 'locomotive'],
     ['car', 'automobile', 'motor vehicle']),
    ('愛人', 'その小説には主人公の愛人が登場する。', ['lover', 'mistress', 'paramour'],
     ['spouse', 'wife', 'husband']),
    ('工作', '子供と一緒に紙で工作をしました。', ['handicraft', 'handicrafts', 'craft', 'crafts',
                                     'handiwork', 'arts and crafts'],
     ['work', 'job', 'occupation']),
    ('結構', 'この料理は結構おいしいです。', ['quite', 'fairly', 'rather', 'pretty',
                                 'considerably', 'reasonably'],
     ['structure', 'composition']),
    ('先生', '田中先生は数学を教えています。', ['teacher', 'sensei', 'instructor'],
     ['mr', 'mister', 'sir']),
    ('床', '床に本を置かないでください。', ['floor'], ['bed']),
]

CONDITIONS = ('bare', 'context', 'source-context')

# Labels the prompt numbers 1-8; read by label, since models renumber.
FIELD_KEYS = {
    'translation': 'translation',
    'source language': 'field2',
    'definition': 'definition',
    'word type': 'word_type',
    'pronunciation': 'pronunciation',
}


class _NoQuota:
    """Stand-in for QuotaManager: lets a trial call through, writes nothing."""

    def is_quota_available(self) -> bool:
        return True

    def use_quota(self) -> None:
        pass


class _NoHistory:
    """Stand-in for HistoryManager: never a cache hit, records nothing."""

    def find_cached_entry(self, *args, **kwargs):
        return None

    def find_source_verdict(self, *args, **kwargs):
        return None

    def add_entry(self, *args, **kwargs) -> None:
        pass


def parse_entry(answer: str) -> Dict[str, Optional[str]]:
    """Pull the named fields out of the first `## [word]` entry of an answer."""
    from src.ui.dictionary_render import FIELD_RE

    fields: Dict[str, Optional[str]] = {v: None for v in FIELD_KEYS.values()}
    entries = 0
    for line in answer.splitlines():
        if line.startswith('## '):
            entries += 1
            if entries > 1:
                break
            continue
        match = FIELD_RE.match(line.strip())
        if not match:
            continue
        label = match.group(2).strip().lower()
        for key, name in FIELD_KEYS.items():
            if key in label and fields[name] is None:
                fields[name] = line.strip()[match.end():].strip()
    return fields


def sense_verdict(translation: Optional[str], ja_words: List[str],
                  zh_words: List[str]) -> str:
    """'ja', 'zh', 'both' or 'neither', from whole-word keyword matches."""
    text = (translation or '').lower()

    def hit(words):
        return any(re.search(r'(?<![a-z])' + re.escape(w) + r'(?![a-z])', text) for w in words)

    ja, zh = hit(ja_words), hit(zh_words)
    if ja and zh:
        return 'both'
    return 'ja' if ja else 'zh' if zh else 'neither'


def prompt_version(mode: str = 'dictionary') -> str:
    """Short hash of the code that writes the prompt, so rows from different wordings of
    the prompt are never pooled by mistake."""
    from src.core.translation import TranslationService
    if mode == 'translate':
        source = inspect.getsource(TranslationService.translate_or_fix)
        module = 'src.core.source_marker'
    else:
        source = inspect.getsource(TranslationService.dictionary_lookup)
        module = 'src.core.dictionary_prompt'
    try:
        import importlib
        source += inspect.getsource(importlib.import_module(module))
    except ImportError:          # before the prompt moved into its own module
        pass
    return hashlib.sha1(source.encode('utf-8')).hexdigest()[:10]


def build_services(config, wanted: List[str], key_index: int = 1):
    """One (label, service) per wanted provider, each limited to that provider's
    `key_index`-th key (1-based), with no health manager, no model rotation and no
    history - so the provider that answers is the one being measured, and nothing
    is written back."""
    from src.core.api_manager import AIAPIManager
    from src.core.translation import TranslationService
    from src.core.trial_api import TrialAPIClient

    keys_by_provider: Dict[str, List[dict]] = {}
    for key_cfg in config.get_api_keys():
        if not (key_cfg.get('api_key') or '').strip():
            continue
        keys_by_provider.setdefault((key_cfg.get('provider') or 'Auto'), []).append(key_cfg)
    by_provider: Dict[str, dict] = {}
    for provider, keys in keys_by_provider.items():
        if len(keys) >= key_index:
            by_provider[provider] = keys[key_index - 1]
        else:
            print(f"SKIP {provider}: has {len(keys)} key(s), --key {key_index} asked")

    services = []
    for name in wanted:
        svc = TranslationService.__new__(TranslationService)
        svc.last_attribution = None
        svc.last_source_language = None
        svc.history_manager = _NoHistory()
        if name.lower() == 'trial':
            device_id = config.get('device_id')
            if not device_id:
                print("SKIP trial: no device_id in config.json")
                continue
            svc._is_trial_mode = True
            svc.trial_client = TrialAPIClient(device_id)
            svc.quota_manager = _NoQuota()
            svc.api_manager = None
            services.append(('trial', svc))
            continue
        match = next((p for p in by_provider if p.lower() == name.lower()), None)
        if match is None:
            print(f"SKIP {name}: no configured key (have: {', '.join(by_provider) or 'none'})")
            continue
        api = AIAPIManager()
        api.configure([by_provider[match]], None, None, model_rotation_enabled=False)
        svc._is_trial_mode = False
        svc.trial_client = None
        svc.api_manager = api
        services.append((match, svc))
    return services, sorted(by_provider)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--label', required=True,
                        help='names the output file: logs/eval/<mode>_<label>.jsonl')
    parser.add_argument('--mode', choices=('dictionary', 'translate'), default='dictionary')
    parser.add_argument('--key', type=int, default=1,
                        help="measure each provider's N-th configured key (1-based)")
    parser.add_argument('--condition', choices=CONDITIONS, default='bare')
    parser.add_argument('--providers', default='',
                        help="comma-separated, e.g. 'Google,Groq,trial'; "
                             "default: every configured provider (never trial)")
    parser.add_argument('--target', default='English')
    parser.add_argument('--words', default='', help='comma-separated subset of the ten')
    parser.add_argument('--delay', type=float, default=2.0,
                        help='seconds between calls (free tiers rate-limit)')
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    import logging
    logging.disable(logging.WARNING)
    import src.core  # noqa: F401 - must precede config (circular import)
    from config import Config
    from src.core.translation import TranslationService

    if args.mode == 'translate':
        return run_translate(args)

    params = inspect.signature(TranslationService.dictionary_lookup).parameters
    needs = {'context': ['context'], 'source-context': ['source_language', 'context']}
    missing = [p for p in needs.get(args.condition, []) if p not in params]
    if missing:
        print(f"FAIL: condition '{args.condition}' needs dictionary_lookup({', '.join(missing)}=...), "
              f"which this version of the prompt does not have")
        return 2

    config = Config()
    configured = sorted({(k.get('provider') or 'Auto') for k in config.get_api_keys()
                         if (k.get('api_key') or '').strip()})
    wanted = [p.strip() for p in args.providers.split(',') if p.strip()] or configured
    services, _ = build_services(config, wanted, args.key)
    if not services:
        print("FAIL: no provider to measure")
        return 2

    words = EVAL_WORDS
    if args.words:
        chosen = {w.strip() for w in args.words.split(',')}
        words = [w for w in EVAL_WORDS if w[0] in chosen]

    version = prompt_version()
    out_dir = os.path.join(ROOT, 'logs', 'eval')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'dictionary_{args.label}.jsonl')

    rows = []
    with open(out_path, 'a', encoding='utf-8') as out:
        for provider, svc in services:
            for i, (word, sentence, ja_words, zh_words) in enumerate(words):
                if i or provider != services[0][0]:
                    time.sleep(args.delay)
                kwargs = {}
                if args.condition in ('context', 'source-context'):
                    kwargs['context'] = sentence
                if args.condition == 'source-context':
                    kwargs['source_language'] = 'Japanese'
                started = time.time()
                answer, error = '', None
                try:
                    answer = svc.dictionary_lookup([word], args.target, **kwargs)
                    if answer.startswith('Error:'):
                        error, answer = answer, ''
                except Exception as exc:  # recorded, never fatal: one bad call
                    error = f'{type(exc).__name__}: {exc}'
                fields = parse_entry(answer) if answer else {v: None for v in FIELD_KEYS.values()}
                row = {
                    'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    'label': args.label,
                    'condition': args.condition,
                    'prompt_version': version,
                    'provider': provider,
                    'model': svc.last_attribution,
                    'word': word,
                    'context': kwargs.get('context'),
                    'source_language': kwargs.get('source_language'),
                    'target': args.target,
                    **fields,
                    'sense': sense_verdict(fields['translation'], ja_words, zh_words),
                    'elapsed_s': round(time.time() - started, 2),
                    'error': error,
                    'raw': answer,
                }
                out.write(json.dumps(row, ensure_ascii=False) + '\n')
                out.flush()
                rows.append(row)
                status = error or f"field2={row['field2']!r} sense={row['sense']}"
                print(f"[{provider}] {word}: {status}")

    print(f"\nwrote {len(rows)} rows to {out_path}\n")
    for provider, _svc in services:
        mine = [r for r in rows if r['provider'] == provider]
        ok = [r for r in mine if not r['error']]
        japanese = sum(1 for r in ok if 'japanese' in (r['field2'] or '').lower())
        senses = {s: sum(1 for r in ok if r['sense'] == s) for s in ('ja', 'zh', 'both', 'neither')}
        model = next((r['model'] for r in ok if r['model']), '?')
        print(f"{provider} ({model}) [{args.condition}]: {len(ok)}/{len(mine)} answered, "
              f"field2=Japanese {japanese}/{len(ok)}, sense {senses}")
        for r in mine:
            translation = (r['translation'] or r['error'] or '')[:70]
            print(f"    {r['word']:<4} {(r['field2'] or '-')[:22]:<22} {r['sense']:<8} {translation}")
    return 0


def run_translate(args) -> int:
    """`--mode translate`: each headword alone through translate_or_fix()."""
    from config import Config
    try:
        from src.core.source_marker import parse_source_marker
    except ImportError:          # before the prompts learned the source language
        parse_source_marker = None

    config = Config()
    configured = sorted({(k.get('provider') or 'Auto') for k in config.get_api_keys()
                         if (k.get('api_key') or '').strip()})
    wanted = [p.strip() for p in args.providers.split(',') if p.strip()] or configured
    services, _ = build_services(config, wanted, args.key)
    if not services:
        print("FAIL: no provider to measure")
        return 2

    words = EVAL_WORDS
    if args.words:
        chosen = {w.strip() for w in args.words.split(',')}
        words = [w for w in EVAL_WORDS if w[0] in chosen]

    version = prompt_version('translate')
    out_dir = os.path.join(ROOT, 'logs', 'eval')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'translate_{args.label}.jsonl')

    rows = []
    with open(out_path, 'a', encoding='utf-8') as out:
        for provider, svc in services:
            # Keep the model's own words: the service strips the marker line.
            seen = {}
            real_call = svc._call_model

            def recording_call(prompt, _real=real_call, _seen=seen):
                _seen['prompt'] = prompt
                _seen['raw'] = _real(prompt)
                return _seen['raw']

            svc._call_model = recording_call
            for i, (word, _sentence, ja_words, zh_words) in enumerate(words):
                if i or provider != services[0][0]:
                    time.sleep(args.delay)
                seen.clear()
                started = time.time()
                result, error = '', None
                try:
                    result = svc.translate_or_fix(word, args.target, skip_cache=True)
                    if result.startswith('Error:'):
                        error, result = result, ''
                except Exception as exc:  # recorded, never fatal: one bad call
                    error = f'{type(exc).__name__}: {exc}'
                raw_answer = seen.get('raw', '')
                marker_found, verdict = None, None
                if parse_source_marker and raw_answer:
                    _clean, verdict, marker_found = parse_source_marker(raw_answer)
                row = {
                    'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                    'label': args.label,
                    'mode': 'translate',
                    'prompt_version': version,
                    'provider': provider,
                    'model': svc.last_attribution,
                    'word': word,
                    'target': args.target,
                    'asked_marker': '[[SOURCE:' in seen.get('prompt', ''),
                    'marker_found': marker_found,
                    'verdict': verdict,
                    'service_verdict': getattr(svc, 'last_source_language', None),
                    'result': result,
                    'sense': sense_verdict(result, ja_words, zh_words),
                    'elapsed_s': round(time.time() - started, 2),
                    'error': error,
                    'raw': raw_answer,
                }
                out.write(json.dumps(row, ensure_ascii=False) + '\n')
                out.flush()
                rows.append(row)
                status = error or (f"marker={marker_found} verdict={verdict} "
                                   f"sense={row['sense']} result={result[:40]!r}")
                print(f"[{provider}] {word}: {status}")

    print(f"\nwrote {len(rows)} rows to {out_path}\n")
    for provider, _svc in services:
        mine = [r for r in rows if r['provider'] == provider]
        ok = [r for r in mine if not r['error']]
        markers = sum(1 for r in ok if r['marker_found'])
        verdicts = {}
        for r in ok:
            verdicts[r['verdict'] or 'none'] = verdicts.get(r['verdict'] or 'none', 0) + 1
        senses = {s: sum(1 for r in ok if r['sense'] == s) for s in ('ja', 'zh', 'both', 'neither')}
        leaked = sum(1 for r in ok if '[[SOURCE' in (r['result'] or '').upper())
        model = next((r['model'] for r in ok if r['model']), '?')
        print(f"{provider} ({model}) [translate -> {args.target}]: {len(ok)}/{len(mine)} answered, "
              f"marker {markers}/{len(ok)}, verdicts {verdicts}, sense {senses}, "
              f"marker leaked into the result {leaked}")
        for r in mine:
            print(f"    {r['word']:<4} {str(r['verdict'] or '-'):<22} {r['sense']:<8} "
                  f"{(r['result'] or r['error'] or '')[:60]}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
