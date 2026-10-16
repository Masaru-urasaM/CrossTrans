"""
Tests for tools/eval_ocr_prompt.py (K10) - the measurement of the screenshot prompt's
===SOURCE LANGUAGE===. The tool itself makes real API calls and is run by hand;
these keep its cases, its drawing and its scoring honest, with no network.
"""
import os
import sys

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.core import lang_id
from src.core.source_marker import source_clause

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'tools'))
import eval_ocr_prompt as tool  # noqa: E402

ANSWER = """===ORIGINAL===
{original}

===SOURCE LANGUAGE===
{language}

===TRANSLATION===
{translation}"""


@pytest.mark.parametrize("text, script, expected, settles", tool.OCR_CASES)
def test_each_case_is_what_it_says_it_is(text, script, expected, settles):
    """The 'settles' column must match what the app's evidence makes of the text,
    or the measurement would be reported under the wrong heading."""
    verdict = lang_id.text_evidence(text)
    if settles == 'kana':
        assert verdict and verdict.evidence == 'kana'
    elif settles.startswith('a Japanese-only'):
        assert verdict and verdict.evidence == 'jp-glyph'
    elif settles.startswith('a simplified-only'):
        assert verdict and verdict.evidence == 'zh-glyph'
    elif settles.startswith('two function words'):
        assert verdict and verdict.evidence == 'zh-grammar'
    else:
        assert verdict is None and source_clause(text).asks
    assert lang_id.normalize_language(expected) and script in tool.FONTS


def test_both_languages_are_measured():
    expected = [case[2] for case in tool.OCR_CASES]
    assert expected.count('Japanese') >= 4 and expected.count('Chinese') >= 4


def test_a_case_is_drawn_into_an_image(tmp_path, monkeypatch):
    from PIL import Image
    text = '立入禁止'
    if not os.path.exists(tool.FONTS['ja']):
        # A CI image may lack the Japanese fonts - and this test must not skip
        # (CI's skip ceiling). The drawing is the same with any font.
        monkeypatch.setitem(tool.FONTS, 'ja', r'C:\Windows\Fonts\arial.ttf')
        text = 'NO ENTRY'
    path = tool.render(text, 'ja', str(tmp_path / 'sign.png'))
    with Image.open(path) as image:
        width, height = image.size
        assert width > 4 * 30 and height > 40          # four 40 px glyphs and a margin
        assert image.getpixel((5, 5)) == (255, 255, 255)
        assert min(low for low, _high in image.getextrema()) < 128   # something was drawn


class TestScore:
    def test_a_full_answer(self):
        row = tool.score('立入禁止', 'Japanese', ANSWER.format(
            original='立入禁止', language='Japanese', translation='No entry'))
        assert row['sections'] and row['source_section'] and row['read_exactly']
        assert row['verdict'] == 'Japanese' and row['correct']
        assert row['translation'] == 'No entry'

    def test_either_chinese_script_is_chinese(self):
        row = tool.score('今天天氣很好。', 'Chinese', ANSWER.format(
            original='今天天氣很好。', language='Chinese', translation='Nice day'))
        assert row['correct']

    def test_unknown_is_not_correct(self):
        row = tool.score('東京大学', 'Japanese', ANSWER.format(
            original='東京大学', language='Unknown', translation='Tokyo University'))
        assert row['verdict'] is None and not row['correct']

    def test_a_misread_text_is_not_read_exactly(self):
        row = tool.score('立入禁止', 'Japanese', ANSWER.format(
            original='立入禁上', language='Japanese', translation='?'))
        assert row['sections'] and not row['read_exactly']

    def test_an_answer_without_sections(self):
        row = tool.score('立入禁止', 'Japanese', 'No entry')
        assert not row['sections'] and not row['source_section'] and row['ocr'] is None
        assert not row['correct']


@pytest.mark.parametrize("language, expected", [
    ('Japanese', 'Japanese'), ('Chinese (Simplified)', 'Chinese'),
    ('Chinese (Traditional)', 'Chinese'), (None, None)])
def test_family(language, expected):
    assert tool.family(language) == expected


def test_nothing_is_sent_without_the_count(monkeypatch, tmp_path, capsys):
    """K12: the vision calls are real ones too - the plan, then nothing."""
    import logging
    from types import SimpleNamespace

    import eval_dictionary_prompt
    calls = []
    service = SimpleNamespace(api_manager=SimpleNamespace(
        translate_multimodal=lambda *args, **kwargs: calls.append(args) or '',
        last_attribution=None))
    monkeypatch.setattr(eval_dictionary_prompt, 'build_services',
                        lambda config, wanted, key: ([('Google', service)], None))
    monkeypatch.setattr('config.Config', lambda: SimpleNamespace(get_api_keys=lambda: []))
    monkeypatch.setattr(logging, 'disable', lambda level: None)   # main() turns logging off
    monkeypatch.setattr(tool, 'ROOT', str(tmp_path))
    assert tool.main(['--label', 't']) == 3
    assert calls == []
    out = capsys.readouterr().out
    assert f"PLAN: {len(tool.OCR_CASES)} real API call(s) on your keys (Google" in out
    assert not (tmp_path / 'logs').exists()
