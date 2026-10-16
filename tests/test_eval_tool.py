"""
Tests for tools/eval_dictionary_prompt.py's K9 additions: --repeat, --input phrases,
and the two figures they report. The tool itself makes real API calls and is run
by hand; these keep its pure parts and its phrase set honest, with no network.
"""
import logging
import os
import sys
from types import SimpleNamespace

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.core.source_marker import source_clause

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'tools'))
import eval_dictionary_prompt as tool  # noqa: E402


@pytest.mark.parametrize("text, expected", tool.EVAL_PHRASES)
def test_every_phrase_is_still_one_the_app_asks_about(text, expected):
    # A phrase the characters settle (kana, a glyph, two function words - K6)
    # would never get the marker clause, and would measure nothing.
    assert source_clause(text).asks, f"{text} is settled by its characters now"
    assert expected in ('Japanese', 'Chinese')


def test_the_phrases_are_balanced():
    languages = [expected for _text, expected in tool.EVAL_PHRASES]
    assert languages.count('Japanese') == languages.count('Chinese') == 5


def test_no_phrase_is_a_measured_word():
    words = {word for word, *_ in tool.EVAL_WORDS}
    assert not words & {text for text, _ in tool.EVAL_PHRASES}


def rows(*cases):
    """[(case, answer), ...] -> rows as the tool writes them."""
    return [{'word': case, 'verdict': answer} for case, answer in cases]


class TestConsistency:
    def test_every_repeat_agreeing_is_one(self):
        assert tool.consistency(rows(('a', 'Japanese'), ('a', 'Japanese')), 'verdict') == 1.0

    def test_it_is_the_mean_of_the_cases(self):
        data = rows(('a', 'Japanese'), ('a', 'Chinese (Simplified)'),
                    ('b', 'Japanese'), ('b', 'Japanese'))
        assert tool.consistency(data, 'verdict') == 0.75

    def test_no_answer_is_an_answer_too(self):
        data = rows(('a', None), ('a', None), ('a', 'Japanese'))
        assert tool.consistency(data, 'verdict') == round(2 / 3, 3)

    def test_no_rows_is_none(self):
        assert tool.consistency([], 'verdict') is None


@pytest.mark.parametrize("verdict, family", [
    ('Japanese', 'Japanese'), ('Chinese (Simplified)', 'Chinese'),
    ('Chinese (Traditional)', 'Chinese'), (None, None), ('', None)])
def test_verdict_family(verdict, family):
    assert tool.verdict_family(verdict) == family


class TestArguments:
    def test_repeat_below_one_is_refused(self):
        with pytest.raises(SystemExit):
            tool.main(['--label', 'x', '--repeat', '0'])

    def test_phrases_are_translate_mode_only(self):
        with pytest.raises(SystemExit):
            tool.main(['--label', 'x', '--input', 'phrases'])


class FakeService:
    """translate_or_fix() through a scripted model: one fixed answer per text."""

    def __init__(self, answers):
        self.answers = answers
        self.last_attribution = 'fake-model (Fake)'
        self.last_source_language = None
        self.calls = []

    def _call_model(self, prompt):
        raise AssertionError("replaced by the tool's recorder")

    def translate_or_fix(self, text, target, skip_cache=False):
        self.calls.append(text)
        answer = self.answers[text]
        self._call_model(f"...{text}...[[SOURCE: x]]")
        return answer.split('\n', 1)[-1]


def test_phrases_are_scored_and_repeated(monkeypatch, tmp_path, capsys):
    answers = {text: ("[[SOURCE: Japanese]]\nok" if expected == 'Japanese'
                      else "[[SOURCE: Chinese]]\nok")
               for text, expected in tool.EVAL_PHRASES}
    answers['他在大學學習中文。'] = "[[SOURCE: Japanese]]\nwrong"     # one wrong verdict
    service = FakeService(answers)
    service._call_model = lambda prompt: answers[next(
        text for text in answers if text in prompt)]
    monkeypatch.setattr(tool, 'build_services', lambda config, wanted, key: ([('Fake', service)], None))
    monkeypatch.setattr(tool, 'ROOT', str(tmp_path))
    monkeypatch.setattr('config.Config', lambda: SimpleNamespace(get_api_keys=lambda: [
        {'provider': 'Fake', 'api_key': 'k'}]))
    args = SimpleNamespace(providers='Fake', key=1, words='', label='t', target='English',
                           delay=0, input='phrases', repeat=2, confirm_calls=20)
    assert tool.run_translate(args) == 0
    assert len(service.calls) == 20                                    # 10 phrases x 2
    assert service.calls[0] == service.calls[1]                        # repeats are adjacent
    out = capsys.readouterr().out
    assert "correct 18/20" in out
    assert "verdict consistency 1.0" in out
    written = (tmp_path / 'logs' / 'eval' / 'translate_t.jsonl').read_text(encoding='utf-8')
    assert written.count('"repeat": 1') == 10


class Untouchable:
    """A service that records any call before failing it: nothing may be sent."""

    def __init__(self):
        self.calls = []
        self.last_attribution = None
        self.last_source_language = None

    def _call_model(self, prompt):
        self.calls.append(prompt)
        raise AssertionError("a real call was made")

    def translate_or_fix(self, text, *args, **kwargs):
        self.calls.append(text)
        raise AssertionError("a real call was made")

    def dictionary_lookup(self, words, *args, **kwargs):
        self.calls.append(words)
        raise AssertionError("a real call was made")


class TestNothingIsSentUnconfirmed:
    """Every call is a real one, on the user's keys or the trial quota (K12):
    without --confirm-calls naming the exact count, a run prints its plan and
    stops before the first."""

    @staticmethod
    def _offline(monkeypatch, tmp_path, service):
        monkeypatch.setattr(tool, 'build_services',
                            lambda config, wanted, key: ([('Fake', service)], None))
        monkeypatch.setattr(tool, 'ROOT', str(tmp_path))
        monkeypatch.setattr('config.Config', lambda: SimpleNamespace(get_api_keys=lambda: [
            {'provider': 'Fake', 'api_key': 'k'}]))
        monkeypatch.setattr(logging, 'disable', lambda level: None)   # main() turns logging off

    @staticmethod
    def _args(**extra):
        return SimpleNamespace(providers='Fake', key=1, words='', label='t', target='English',
                               delay=0, input='phrases', repeat=2, **extra)

    def test_translate_mode_prints_the_plan_and_stops(self, monkeypatch, tmp_path, capsys):
        service = Untouchable()
        self._offline(monkeypatch, tmp_path, service)
        assert tool.run_translate(self._args()) == 3
        assert service.calls == []
        out = capsys.readouterr().out
        assert "PLAN: 20 real API call(s) on your keys (Fake 20)" in out
        assert "--confirm-calls 20" in out
        assert not (tmp_path / 'logs').exists()          # not even an empty results file

    def test_a_wrong_count_is_not_a_yes(self, monkeypatch, tmp_path):
        service = Untouchable()
        self._offline(monkeypatch, tmp_path, service)
        assert tool.run_translate(self._args(confirm_calls=19)) == 3
        assert service.calls == []

    def test_dictionary_mode_prints_the_plan_and_stops(self, monkeypatch, tmp_path, capsys):
        service = Untouchable()
        self._offline(monkeypatch, tmp_path, service)
        assert tool.main(['--label', 't', '--providers', 'Fake', '--words', '手紙,汽車']) == 3
        assert service.calls == []
        assert "PLAN: 2 real API call(s)" in capsys.readouterr().out

    def test_the_plan_counts_cases_repeats_and_providers(self):
        services = [('Groq', None), ('Google', None)]
        assert tool.planned_calls(services, 10, 3) == {'Groq': 30, 'Google': 30}

    def test_the_exact_total_is_a_yes(self):
        assert tool.confirmed({'Groq': 10, 'Google': 10}, 20)

    def test_the_trial_quota_is_named(self, capsys):
        assert not tool.confirmed({'trial': 10}, None)
        assert "trial quota" in capsys.readouterr().out
