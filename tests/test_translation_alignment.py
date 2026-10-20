"""The response protocol must never convert broken metadata into false certainty."""
import json
import pytest

from src.core.translation_alignment import (
    AlignmentError, MAX_SOURCE_CHARS, build_prompt, delimiter_token, eligible,
    parse_answer, segment_source, validate_metadata,
)


@pytest.mark.parametrize('text', [
    'First. Second! Third?', '  First.\r\n\r\n> Second sentence.\r\n',
    'これは最初です。次の文です。', 'Dr. Smith paid 3.14 USD. Next sentence.',
    'Visit https://example.com/a.b?q=x. Now wait.', '1. One item\n2. Another item',
    '```python\nx = 1.2\nprint(x)\n```\nNext.', 'No terminal punctuation',
    'Emoji \U0001f642. Combining e\u0301. 日本語。', 'A' * 50000,
], ids=lambda text: text[:35].encode('unicode_escape').decode('ascii'))
def test_lossless_segments(text):
    units = segment_source(text)
    assert ''.join(u.text for u in units) == text
    assert [u.id for u in units] == list(range(1, len(units) + 1))
    for unit in units:
        assert text[unit.start:unit.end] == unit.text


def test_abbreviations_urls_and_code_are_not_split_internally():
    text = 'Dr. Smith paid 3.14 USD. Next.\n```\nx.y!\n```\nhttps://x.y/a.b\n'
    assert [u.text for u in segment_source(text)] == [
        'Dr. Smith paid 3.14 USD. ', 'Next.\n', '```\nx.y!\n```\n', 'https://x.y/a.b\n']


def response(rows, version=1):
    return json.dumps({'version': version, 'segments': rows})


def test_groups_offsets_and_exact_identity():
    source = 'First. Second. Third.'
    raw = response([{'source_ids': [1], 'text': 'One. '}, {'source_ids': [2, 3], 'text': 'Two and three.'}])
    result = parse_answer(raw, source, 'English')
    assert result.text == 'One. Two and three.'
    assert result.metadata['groups'] == [
        {'source': [0, 7], 'translated': [0, 5]},
        {'source': [7, len(source)], 'translated': [5, len(result.text)]}]
    assert validate_metadata(result.metadata, source, result.text, 'English', 'merged')
    for args in [(source + ' ', result.text, 'English', 'merged'),
                 (source, result.text + ' ', 'English', 'merged'),
                 (source, result.text.replace('One', 'Uno'), 'English', 'merged'),
                 (source, result.text, 'Japanese', 'merged'),
                 (source, result.text, 'English', 'text')]:
        assert validate_metadata(result.metadata, *args) is None


@pytest.mark.parametrize('ids', [[True], [0], [2], [1, 1], [1, 3], ['1'], [], None])
def test_bad_ids_recover_text_without_mapping(ids):
    result = parse_answer(response([{'source_ids': ids, 'text': 'Complete.'}]), 'Source.', 'English')
    assert result.text == 'Complete.' and result.metadata is None
    assert result.status == 'invalid_ids'


@pytest.mark.parametrize('raw', ['{', '{"segments":[{"text":"partial"}',
                                '{"segments":[]}', '{"segments":[{"source_ids":[1]}]}',
                                '```json\n{}', '[]', '', '{"segments":[{"text":""}]}'])
def test_broken_response_is_not_a_success(raw):
    with pytest.raises(AlignmentError):
        parse_answer(raw, 'Source.', 'English')


def test_complete_fence_marker_and_literal_marker_inside_text():
    raw = response([{'source_ids': [1], 'text': 'Literal [[SOURCE: Chinese]] stays.'}])
    result = parse_answer('[[SOURCE: Japanese]]\n```json\n' + raw + '\n```', '東京大学', 'English')
    assert result.verdict == 'Japanese'
    assert result.text == 'Literal [[SOURCE: Chinese]] stays.'
    assert parse_answer(raw, '東京大学', 'English', known='Chinese').verdict.startswith('Chinese')


def test_plain_fallback_and_bad_version():
    assert parse_answer('Ordinary answer.', 'Source.', 'English').status == 'plain'
    assert parse_answer(response([{'source_ids': [1], 'text': 'One.'}], True), 'Source.', 'English').metadata is None


def test_compact_requires_end_and_preserves_spacing():
    source = 'First. Second.'
    token = delimiter_token(source)
    raw = f'[[{token}:1]]One. [[{token}:2]]Two.\n[[{token}:END]]'
    result = parse_answer(raw, source, 'English', protocol='compact')
    assert result.text == 'One. Two.'
    assert result.metadata
    with pytest.raises(AlignmentError):
        parse_answer(raw.replace(f'[[{token}:END]]', ''), source, 'English', protocol='compact')


def test_prompt_contains_source_once_and_keeps_merged_rule():
    source = 'Unique source sentence.'
    prompt = build_prompt(source, 'English')
    assert prompt.count(source) == 1
    assert 'minimal changes' in prompt and 'Do not censor' in prompt
    assert not eligible('A' * (MAX_SOURCE_CHARS + 1))
    assert not eligible('  ')
    with pytest.raises(ValueError):
        build_prompt('A' * (MAX_SOURCE_CHARS + 1), 'English')


def test_metadata_invalid_range_and_version():
    result = parse_answer(response([{'source_ids': [1], 'text': 'One.'}]), 'Source.', 'English')
    for field, value in [('version', 2), ('groups', [{'source': [0, 6], 'translated': [0, 4]}])]:
        data = dict(result.metadata, **{field: value})
        assert validate_metadata(data, 'Source.', result.text, 'English') is None


def test_app_restores_line_breaks_and_sentence_spacing():
    source = '  最初です。次です。\r\n\r\n最後です。\n'
    rows = [{'source_ids': [i], 'text': text} for i, text in enumerate(
        ['First.', 'Second.', 'Last.'], 1)]
    result = parse_answer(response(rows), source, 'English')
    assert result.text == '  First. Second.\r\n\r\nLast.\n'
    assert validate_metadata(result.metadata, source, result.text, 'English')


def test_japanese_target_has_no_added_horizontal_spaces():
    result = parse_answer(response([{'source_ids': [1], 'text': ' 最初。\n'},
                                   {'source_ids': [2], 'text': ' 次。 '}]), 'First. Next.', 'Japanese')
    assert result.text == '最初。次。'


def test_quoted_punctuation_stays_with_its_sentence():
    source = '「明日です。」と言いました。次の文です。'
    assert [u.text for u in segment_source(source)] == ['「明日です。」と言いました。', '次の文です。']


def test_validator_rejects_shifted_source_boundary():
    source = 'First. Second.'
    data = parse_answer(response([{'source_ids': [1], 'text': 'One.'},
                                  {'source_ids': [2], 'text': 'Two.'}]), source, 'English').metadata
    data['groups'][0]['source'][1] -= 1
    data['groups'][1]['source'][0] -= 1
    assert validate_metadata(data, source, 'One. Two.', 'English') is None
