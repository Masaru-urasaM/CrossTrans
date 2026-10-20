"""Evaluation plans cannot spend calls or write the developer's configuration."""
import json
import logging
from unittest.mock import Mock

import pytest

from tools import eval_translation_alignment as evaluation


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    from config import Config
    from src.core.api_manager import AIAPIManager
    config_path = tmp_path / 'config.json'
    content = json.dumps({'api_keys': [{'provider': 'Groq', 'model_name': 'model', 'api_key': 'fake'}]})
    config_path.write_text(content, encoding='utf-8')
    monkeypatch.setattr(Config, 'CONFIG_FILE', str(config_path))
    monkeypatch.setattr(evaluation, 'ROOT', tmp_path)
    monkeypatch.setattr(evaluation.time, 'sleep', lambda seconds: None)
    call = Mock(side_effect=AssertionError('Dry-run requested an API generation'))
    monkeypatch.setattr(AIAPIManager, '_generate_content', call)
    old_disable = logging.root.manager.disable
    yield config_path, content, call
    logging.disable(old_disable)
    assert config_path.read_text(encoding='utf-8') == content


def test_dry_run_and_wrong_confirmation_send_nothing(isolated_config, capsys):
    for confirmation in ([], ['--confirm-calls', '11']):
        assert evaluation.main(['--label', 'dry', *confirmation]) == 0
    assert '12 single-attempt calls' in capsys.readouterr().out
    isolated_config[2].assert_not_called()


@pytest.mark.parametrize('extra', [['--cases', '0'], ['--repeat', '4'], ['--label', '../escape'],
                                 ['--conditions', 'unknown'], ['--key', '0']])
def test_invalid_limits_fail_before_generating(isolated_config, extra):
    with pytest.raises(SystemExit):
        evaluation.main(['--label', 'dry', *extra])
    isolated_config[2].assert_not_called()


def test_summary_distinguishes_failure_and_alignment():
    rows = [{'condition': 'json', 'seconds': 1, 'status': 'aligned',
             'usage': {'completion_tokens': 100}},
            {'condition': 'json', 'seconds': 3, 'status': 'failed', 'error': 'timeout'}]
    summary = evaluation.summarize(rows)['json']
    assert summary == {'calls': 2, 'success': 1, 'aligned': 1, 'latency_median': 1,
                       'output_tokens_median': 100}


def test_confirmed_run_is_bounded_and_does_not_write_config(isolated_config, monkeypatch, tmp_path):
    call = isolated_config[2]
    call.side_effect = None
    call.return_value = json.dumps({'version': 1, 'segments': [{'source_ids': [1], 'text': 'First.'}]})
    monkeypatch.setattr(evaluation, 'CASES', [('one', 'First.', 'English')])
    assert evaluation.main(['--label', 'bounded', '--cases', '1', '--conditions', 'json',
                            '--confirm-calls', '1', '--delay', '0']) == 0
    assert call.call_count == 1
    rows = (tmp_path / 'logs/eval/alignment_bounded.jsonl').read_text(encoding='utf-8')
    assert json.loads(rows)['status'] == 'aligned'
    with pytest.raises(SystemExit):
        evaluation.main(['--label', 'bounded', '--cases', '1', '--conditions', 'json',
                         '--confirm-calls', '1', '--delay', '0'])
    assert call.call_count == 1
