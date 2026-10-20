"""Incomplete generations must not become successful cached translations or global links."""
import json
import logging
import tkinter as tk
from unittest.mock import Mock

import pytest

from src.core.api_manager import AIAPIManager
from src.core.generation_result import (IncompleteGenerationError, check_generation_result,
                                        google_text, anthropic_text)
from src.core.translation_alignment import (AlignedText, make_metadata, reading_result,
                                             structural_alignment, validate_metadata)
from src.core.trial_api import TrialAPIClient
from src.ui.quick_translate import QuickTranslateManager
from tests.test_alignment_service import make_service
from tests.test_popup_alignment import FakeConfig, settle


@pytest.mark.parametrize('payload', [
    {'choices': [{'finish_reason': 'length', 'message': {'content': 'Incomplete'}}]},
    {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': 'Incomplete'}]}}]},
    {'stop_reason': 'max_tokens', 'content': [{'type': 'text', 'text': 'Incomplete'}]},
])
def test_provider_output_limit_is_not_complete(payload):
    with pytest.raises(IncompleteGenerationError, match='output-token limit'):
        check_generation_result(payload)


def test_diagnostic_log_records_finish_and_usage_without_raw_content(caplog):
    with caplog.at_level(logging.INFO):
        check_generation_result({'choices': [{'finish_reason': 'stop', 'message': {'content': 'PRIVATE BODY'}}],
                                 'usage': {'prompt_tokens': 100, 'completion_tokens': 200,
                                           'completion_tokens_details': {'reasoning_tokens': 57, 'private': 'SECRET'},
                                           'unrelated': 'SECRET'}})
    assert 'finish_reason=stop' in caplog.text and '200' in caplog.text
    assert "'reasoning_tokens': 57" in caplog.text
    assert 'PRIVATE BODY' not in caplog.text and 'SECRET' not in caplog.text


def test_all_final_text_blocks_are_read_without_thinking_blocks():
    assert google_text({'candidates': [{'content': {'parts': [
        {'text': 'hidden', 'thought': True}, {'text': 'First. '}, {'text': 'Last.'}]}}]}) == 'First. Last.'
    assert anthropic_text({'content': [{'type': 'thinking', 'thinking': 'hidden'},
        {'type': 'text', 'text': 'First. '}, {'type': 'text', 'text': 'Last.'}]}) == 'First. Last.'


@pytest.mark.parametrize('provider,model,payload', [
    ('Groq', 'openai/gpt-oss-120b', {'choices': [{'finish_reason': 'length', 'message': {'content': 'Partial'}}]}),
    ('Groq', 'openai/gpt-oss-120b', {'choices': [{'finish_reason': 'length', 'message': {'content': None}}],
                                   'usage': {'completion_tokens': 3072,
                                             'completion_tokens_details': {'reasoning_tokens': 3070}}}),
    ('Google', 'gemini-2.5-flash', {'candidates': [{'finishReason': 'MAX_TOKENS', 'content': {'parts': [{'text': 'Partial'}]}}]}),
    ('Anthropic', 'claude-haiku-4-5', {'stop_reason': 'max_tokens', 'content': [{'type': 'text', 'text': 'Partial'}]}),
])
def test_incomplete_generation_makes_one_attempt_without_rotation_or_attribution(monkeypatch, provider, model, payload):
    api = AIAPIManager()
    api.configure([{'model_name': model, 'provider': provider, 'api_key': 'test-key'}])
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps(payload).encode('utf-8')
    request = Mock(return_value=response)
    monkeypatch.setattr('urllib.request.urlopen', request)
    api._try_model_rotation = Mock(side_effect=AssertionError('Partial response retried'))
    api._record_attribution = Mock()
    with pytest.raises(IncompleteGenerationError):
        api.translate('Translate the entire document.')
    request.assert_called_once()
    api._try_model_rotation.assert_not_called()
    api._record_attribution.assert_not_called()


@pytest.mark.parametrize('model', ['openai/gpt-oss-120b', 'openai/gpt-oss-20b'])
@pytest.mark.parametrize('files', [False, True])
def test_groq_explicit_output_budget_reaches_wire_without_trimming_or_extra_calls(monkeypatch, model, files):
    api = AIAPIManager()
    api.configure([{'model_name': model, 'provider': 'Groq', 'api_key': 'test-key'}])
    response = Mock()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.read.return_value = json.dumps({'choices': [
        {'finish_reason': 'stop', 'message': {'content': 'First paragraph.\n\nLast paragraph.'}}]}).encode()
    request = Mock(return_value=response)
    monkeypatch.setattr('urllib.request.urlopen', request)
    source = ('Translate this complete paragraph, including every detail.\n\n' * 500) + 'FINAL SOURCE SENTENCE.'
    if files:
        result = api.translate_multimodal('Translate the whole document.', file_contents={'sample.txt': source})
    else:
        result = api.translate(source)
    assert result == 'First paragraph.\n\nLast paragraph.'
    request.assert_called_once()
    sent_request = request.call_args.args[0]
    assert sent_request.host == 'api.groq.com'
    body = json.loads(sent_request.data)
    assert body['max_completion_tokens'] == 65536
    assert 'max_tokens' not in body and body['reasoning_effort'] == 'low'
    content = body['messages'][0]['content']
    sent_text = content[0]['text'] if files else content
    assert source in sent_text and sent_text.endswith(source + '\n' if files else source)
    assert 0 < request.call_args.kwargs['timeout'] <= 20


@pytest.mark.parametrize('url,model', [
    ('https://api.groq.com/openai/v1/chat/completions', 'qwen/qwen3.8-27b'),
    ('https://api.cerebras.ai/v1/chat/completions', 'openai/gpt-oss-120b'),
    ('https://openrouter.ai/api/v1/chat/completions', 'openai/gpt-oss-120b'),
    ('https://api.groq.com.example.com/chat/completions', 'openai/gpt-oss-120b'),
])
@pytest.mark.parametrize('files', [False, True])
def test_groq_budget_does_not_change_other_provider_or_model_requests(monkeypatch, url, model, files):
    api = AIAPIManager()
    request = Mock(return_value='Complete answer.')
    monkeypatch.setattr(api, '_make_request_with_retry', request)
    if files:
        api._call_openai_style_multimodal('test-key', model, 'Translate.', url, [])
    else:
        api._call_generic_openai_style('test-key', model, 'Translate.', url)
    request.assert_called_once()
    assert 'max_completion_tokens' not in request.call_args.kwargs['data']
    assert request.call_args.kwargs['timeout'] == (60 if files else 10)


def test_incomplete_response_is_never_added_to_history():
    service = make_service(enabled=False)
    service._call_model.side_effect = IncompleteGenerationError('Incomplete response: output-token limit')
    result = service.translate_or_fix('First. Last.', 'English')
    assert result.startswith('Error: Incomplete response')
    assert not service.history_manager.get_history()
    service._call_model.assert_called_once()


def test_trial_rejects_output_limit_instead_of_returning_partial_text():
    trial = TrialAPIClient.__new__(TrialAPIClient)
    with pytest.raises(IncompleteGenerationError):
        trial._parse_response({'choices': [{'finish_reason': 'length', 'message': {'content': 'Partial'}}]})


@pytest.mark.parametrize('cached', [False, True])
def test_auto_detection_does_not_retry_incomplete_generation(cached):
    api = AIAPIManager()
    key = 'test-auto-key'
    if cached:
        api._working_models_cache[api._get_api_key_prefix(key)] = 'openai/gpt-oss-120b'
    api._generate_content = Mock(side_effect=IncompleteGenerationError('output-token limit'))
    with pytest.raises(IncompleteGenerationError):
        api._try_auto_detect_model(key, 'Groq', 'Translate all paragraphs.')
    api._generate_content.assert_called_once()


def test_39_source_paragraphs_and_15_partial_paragraphs_have_no_global_link():
    source = '\n\n'.join(f'Source paragraph number {i}. More details.' for i in range(39))
    translated = '\n\n'.join(f'Result paragraph number {i}. More details.' for i in range(15))
    assert structural_alignment(source, translated, 'English') is None
    assert type(reading_result(translated, None, source, 'English')) is str


def test_unequal_sentence_counts_cannot_become_a_single_document_link():
    assert structural_alignment('First. Second. Last.', 'One combined. Final.', 'English') is None


def test_obsolete_persisted_structural_map_is_ignored(tk_root):
    source = '\n\n'.join(f'Source paragraph {i}.' for i in range(39))
    target = '\n\n'.join(f'Target paragraph {i}.' for i in range(15))
    old = make_metadata(source, target, 'English', 'text', [
        {'source': [0, len(source)], 'translated': [0, len(target)]}])
    old['method'] = 'structure'
    assert validate_metadata(old, source, target, 'English') is None
    manager = QuickTranslateManager(tk_root, FakeConfig())
    try:
        manager.show(AlignedText(target, old), 'English', original=source)
        settle(tk_root)
        assert manager._linked_controller is None
        assert manager._linked_status.cget('text') == 'No reliable links'
        assert manager.popup_text.get_plain() == target
    finally:
        manager.close()


def test_large_visible_group_does_not_scroll_either_pane_to_its_start(tk_root):
    source = '\n'.join(f'Source line {i}.' for i in range(100))
    target = '\n'.join(f'Target line {i}.' for i in range(100))
    data = make_metadata(source, target, 'English', 'text', [
        {'source': [0, len(source)], 'translated': [0, len(target)]}])
    manager = QuickTranslateManager(tk_root, FakeConfig())
    try:
        manager.show(AlignedText(target, data), 'English', original=source)
        settle(tk_root)
        manager.popup_furigana.yview_moveto(0.5)
        manager.popup_text.yview_moveto(0.5)
        settle(tk_root)
        before = manager.popup_furigana.yview(), manager.popup_text.yview()
        manager._linked_controller.activate(1, 0)
        settle(tk_root)
        assert (manager.popup_furigana.yview(), manager.popup_text.yview()) == before
        manager._linked_controller.activate(0, 0)
        settle(tk_root)
        assert (manager.popup_furigana.yview(), manager.popup_text.yview()) == before
    finally:
        manager.close()
