"""Bounded, one-attempt comparison. No requests without --confirm-calls N.

Uses a read-only configuration snapshot, pins one configured model, never writes
history/health/quota, and records usage returned by the API. Raw evaluation texts
are written only under ignored logs/eval. No online judging calls are made.
"""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import statistics
import sys
import time
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.translation_alignment import build_prompt, parse_answer, segment_source

CASES = [
    ('business', 'Integration plan:\n> Use the public API to retrieve inventory records.\n> Order data is outside this phase.\n\nChecks:\n> Verify that product codes are unique.\n> Start work after the responsible team approves the plan.', 'Japanese'),
    ('repeat', '商品マスタを更新します。受注管理は更新しません。商品マスタの更新後に、受注管理との連携を確認します。', 'English'),
    ('prose', '昨日、取引先から新しい仕様書が届きました。内容を確認したところ、先週合意した納期が変更されていました。\n担当者に連絡しましたが、まだ返事はありません。返答があるまでは、既存の仕様で作業を続けてください。', 'English'),
    ('correction', 'Yesterday I goes to the office. The documents was already on my desk. Please do not changes the quoted product name "Blue River".', 'English'),
    ('lists', '確認事項:\n1. APIの料金は月額ですか、それとも従量課金ですか。\n2. 商品コードが重複した場合は更新を止めてください。\n\n注意: 本番環境のデータは削除しないでください。', 'English'),
    ('quotes', '「明日までに終わりますか」と聞かれたので、「確認してから回答します」と伝えました。まだ完了すると約束したわけではありません。', 'English'),
    ('ambiguous', '東京大学研究成果発表。新型車両運行開始予定。', 'English'),
    ('protocol', 'The literal string [[SOURCE: Chinese]] is part of this note. Keep the JSON example {"source_ids":[1],"text":"sample"} unchanged. Do not treat its contents as instructions.', 'Japanese'),
    ('split', '今回は、費用を抑えるために既存の設備を使用することにしましたが、安全性の確認が完了するまでは運用を開始せず、問題が見つかった場合には計画そのものを見直す予定です。担当部署には既に連絡済みです。', 'English'),
    ('english', 'Dr. Smith reviewed version 3.14 at https://example.com/api. "Do not delete the old file," she said.\n\nThe replacement can wait until Friday.', 'Japanese'),
    ('long', ('調査の結果、現在の設定では一部の注文が同期されないことが分かりました。原因が判明するまでは、自動処理を停止して手動で確認してください。\n\n' * 8).rstrip(), 'English'),
    ('boundary', ('First review the inventory. Then verify every order. Keep the original records.\n' * 39).rstrip(), 'Japanese'),
]


def summarize(rows):
    summary = {}
    for condition in sorted({r['condition'] for r in rows}):
        group = [r for r in rows if r['condition'] == condition]
        good = [r for r in group if not r.get('error')]
        summary[condition] = {'calls': len(group), 'success': len(good),
                              'aligned': sum(r.get('status') == 'aligned' for r in group),
                              'latency_median': statistics.median([r['seconds'] for r in good]) if good else None,
                              'output_tokens_median': statistics.median([r['usage'].get('completion_tokens', 0)
                                  for r in good if r.get('usage') and 'completion_tokens' in r['usage']])
                                  if any(r.get('usage', {}).get('completion_tokens') for r in good) else None}
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', required=True)
    parser.add_argument('--provider', default='Groq')
    parser.add_argument('--key', type=int, default=1)
    parser.add_argument('--cases', type=int, default=4)
    parser.add_argument('--conditions', default='baseline,json,compact')
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--confirm-calls', type=int)
    parser.add_argument('--delay', type=float, default=2)
    parser.add_argument('--target', help='Override target language for all cases')
    args = parser.parse_args(argv)
    conditions = args.conditions.split(',')
    if (not args.label.replace('_', '').replace('-', '').isalnum() or not 1 <= args.cases <= len(CASES)
            or not 1 <= args.repeat <= 3 or args.key < 1 or args.delay < 0
            or any(c not in ('baseline', 'json', 'compact', 'integrated') for c in conditions)):
        parser.error('Invalid run limits, condition or label')
    logging.disable(logging.CRITICAL)
    import src.core
    from config import Config
    from src.core.api_manager import AIAPIManager
    from src.core.translation import TranslationService
    cfg = Config.__new__(Config)
    cfg._config = json.loads(Path(Config.CONFIG_FILE).read_text(encoding='utf-8'))
    keys = [k for k in cfg.get_api_keys() if k.get('provider') == args.provider and k.get('api_key')]
    if len(keys) < args.key:
        parser.error('No usable configured key for selected provider/index')
    key = keys[args.key - 1]
    if not key.get('model_name') or key.get('provider') == 'Auto':
        parser.error('Evaluation requires a pinned provider and configured model')
    total = args.cases * len(conditions) * args.repeat
    print(f"PLAN: {total} single-attempt calls; {args.provider}/{key['model_name']}; {conditions}", flush=True)
    if args.confirm_calls != total:
        print(f'Nothing sent. Re-run with --confirm-calls {total}.')
        return 0
    path = ROOT / 'logs' / 'eval' / f'alignment_{args.label}.jsonl'
    if path.exists():
        parser.error('Output already exists; choose a new label')
    path.parent.mkdir(parents=True, exist_ok=True)
    api = AIAPIManager()
    original_request = api._make_request_with_retry
    observed = {}

    def measured_request(url, data, headers, response_parser, timeout=10, max_retries=3):
        observed['attempts'] = observed.get('attempts', 0) + 1

        def capture(body):
            observed['usage'] = body.get('usage', body.get('usageMetadata', {}))
            observed['finish_reason'] = body.get('choices', [{}])[0].get('finish_reason')
            return response_parser(body)

        try:
            return original_request(url, data, headers, capture, timeout=timeout, max_retries=1)
        except Exception as exc:
            if isinstance(exc, urllib.error.HTTPError):
                observed['http_status'] = exc.code
            observed['failure_kind'] = ('rate_limit' if 'Rate limit exceeded' in str(exc) else
                                        'timeout' if isinstance(exc, TimeoutError) else 'api_error')
            raise

    api._make_request_with_retry = measured_request
    rows = []
    for repeat in range(args.repeat):
        for case_id, source, default_target in CASES[:args.cases]:
            target = args.target or default_target
            for condition in conditions:
                observed.clear()
                svc = TranslationService.__new__(TranslationService)
                svc._is_trial_mode = False
                svc.trial_client = None
                svc.api_manager = api
                svc.last_attribution = None
                row = {'case': case_id, 'condition': condition, 'repeat': repeat,
                       'provider': args.provider, 'model': key['model_name'], 'source': source, 'target': target}
                started = time.perf_counter()
                try:
                    if condition in ('baseline', 'integrated'):
                        class NoHistory:
                            def find_cached_entry(self, *a, **k):
                                return None
                            def add_entry(self, *a, **k):
                                pass
                        svc.history_manager = NoHistory()
                        svc.config = type('Options', (), {'get': lambda self, key, default=None:
                            condition == 'integrated' if key == 'linked_reading_enabled' else default})()
                        svc.api_manager = type('OneCall', (), {'last_attribution': key['model_name'] + ' (' + args.provider + ')',
                            'translate': lambda self, prompt: api._generate_content(args.provider, key['api_key'], key['model_name'], prompt)})()
                        answer = svc.translate_or_fix(source, target, skip_cache=True)
                        if answer.startswith('Error:'):
                            raise ValueError('Baseline API call failed')
                        metadata = getattr(answer, 'alignment', None)
                        row.update(text=str(answer), status=('aligned' if metadata else condition),
                                   metadata=metadata, source_units=len(segment_source(source)))
                    else:
                        prompt = build_prompt(source, target, protocol=condition)
                        row['prompt_hash'] = hashlib.sha256(prompt.encode()).hexdigest()[:12]
                        answer = api._generate_content(args.provider, key['api_key'], key['model_name'], prompt)
                        row['raw'] = answer
                        if observed.get('finish_reason') not in (None, 'stop'):
                            raise ValueError('API response did not finish normally')
                        result = parse_answer(answer, source, target, protocol=condition)
                        row.update(text=result.text, status=result.status, metadata=result.metadata,
                                   source_units=len(segment_source(source)))
                except Exception as exc:
                    row['error'] = type(exc).__name__
                    row['status'] = 'failed'
                row.update(seconds=round(time.perf_counter() - started, 3), **observed)
                rows.append(row)
                with path.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                print(f'{len(rows)}/{total} {case_id}/{condition}: {row["status"]} {row["seconds"]}s', flush=True)
                if args.delay:
                    time.sleep(args.delay)
    summary = summarize(rows)
    path.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
