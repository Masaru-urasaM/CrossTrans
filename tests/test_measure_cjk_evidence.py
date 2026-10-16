"""
Tests for tools/measure_cjk_evidence.py - the measurement behind Decision 30 (K6)
and DEFERRED D19 (K1). The tool itself is run by hand on Tatoeba's exports; these
tests keep its pure parts honest on tiny corpora, with no network.
"""
import bz2
import importlib.util
import os

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.core import furigana as F

TOOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'tools', 'measure_cjk_evidence.py')
spec = importlib.util.spec_from_file_location('measure_cjk_evidence', TOOL)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


@pytest.mark.parametrize("text, expected", [
    ("這是我的書。", True),        # open by glyphs - grammar settles it since K6
    ("勉強", True),
    ("勉強します", False),         # kana
    ("我们去学校。", False),        # a simplified form proves Chinese by itself
    ("経済", False),               # a Japanese-only form
    ("Hello", False),
])
def test_open_by_glyphs(text, expected):
    assert tool.open_by_glyphs(text) is expected


def test_chinese_by_grammar():
    assert tool.chinese_by_grammar("這是我的書。") is True
    assert tool.chinese_by_grammar("東京大学。") is False
    assert tool.chinese_by_grammar("我们去学校。") is False      # glyph evidence, not grammar


def test_the_japanese_sets():
    words = ["東京", "大学", "目的", "終了", "是正", "経済"]
    sets = tool.japanese_sets(["以上。", "今日は晴れ。"], words)
    assert sets['tatoeba sentences'] == ["以上。"]                # kana is not open
    assert "経済" not in sets['dictionary words']                 # nor is a Japanese glyph
    assert sets['one-word sentences'] == [w + '。' for w in sets['dictionary words']]
    assert all(t.endswith('。') for t in sets['lists']) and sets['lists']
    assert len(sets['stress compounds']) == 20000
    holders = {"目的", "終了", "是正"}
    assert all(any(t.startswith(h) for h in holders) for t in sets['stress compounds'][:50])


def test_measure_evidence_counts_both_sides():
    report = tool.measure_evidence(
        ["這是我的書。", "你好嗎？", "我们去学校。", "我是學生。"],
        {'sentences': ["以上。", "了解。"]})
    assert report['chinese_open_by_glyphs'] == 3          # the simplified one is not open
    assert report['chinese_settled'] == 2
    assert report['chinese_settled_share'] == round(2 / 3, 4)
    assert report['japanese_called_chinese']['sentences'] == {
        'count': 0, 'of': 2, 'examples': []}


def test_a_rule_that_calls_japanese_chinese_is_caught():
    report = tool.measure_evidence(["這是我的書。"], {'sentences': ["以上。"]},
                                   rule=lambda text: True)
    assert report['japanese_called_chinese']['sentences']['count'] == 1


def test_reading_pairs_keep_offsets():
    segments = (F.RubySegment("今日", "きょう"), F.RubySegment("は", None),
                F.RubySegment("今日", "こんにち"))
    assert tool.reading_pairs(segments) == {(0, "今日"): "きょう", (3, "今日"): "こんにち"}


def test_a_downloaded_export_is_read_without_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(tool, 'TATOEBA_DIR', str(tmp_path))
    with bz2.open(tmp_path / 'jpn_sentences.tsv.bz2', 'wt', encoding='utf-8') as fh:
        fh.write("1\tjpn\t今日は晴れ。\n2\tjpn\t以上。\nbroken line\n")
    monkeypatch.setattr(tool.urllib.request, 'urlretrieve',
                        lambda *a, **k: pytest.fail("must not download"))
    assert tool.tatoeba('jpn') == ["今日は晴れ。", "以上。"]


def test_an_unknown_mode_is_refused():
    with pytest.raises(SystemExit):
        tool.main(['everything'])
