"""The CI guard that stops a green tick from meaning nothing.

`tests/conftest.py`'s `tk_root` fixture skips when there is no usable display -
correct for a developer on a headless shell, wrong for CI. 312 of the 630 tests
here need Tk, so a runner without a desktop session would skip roughly half the
suite and still report success. `tools/check_test_counts.py` reads the JUnit XML
and refuses that outcome.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))

import check_test_counts as guard


def write(tmp_path, tests, failures=0, errors=0, skipped=0, wrap=True, name='junit.xml'):
    cases = []
    for i in range(skipped):
        cases.append(f'<testcase classname="tests.test_widgets" name="test_{i}">'
                     f'<skipped message="no usable Tk display"/></testcase>')
    for i in range(tests - skipped):
        cases.append(f'<testcase classname="tests.test_core" name="test_ok_{i}"/>')
    suite = (f'<testsuite name="pytest" tests="{tests}" failures="{failures}" '
             f'errors="{errors}" skipped="{skipped}">' + ''.join(cases) + '</testsuite>')
    xml = f'<testsuites>{suite}</testsuites>' if wrap else suite
    path = tmp_path / name
    path.write_text(xml, encoding='utf-8')
    return str(path)


class TestAHealthyRunPasses:
    def test_everything_green(self, tmp_path):
        assert guard.main([write(tmp_path, 630)]) == 0

    def test_a_couple_of_skips_are_normal(self, tmp_path):
        # The clipboard round trip yields when another process owns the clipboard.
        assert guard.main([write(tmp_path, 630, skipped=2)]) == 0

    def test_the_old_single_testsuite_root_is_understood(self, tmp_path):
        assert guard.main([write(tmp_path, 630, wrap=False)]) == 0


class TestTheHeadlessRunnerIsCaught:
    def test_mass_skips_fail_the_build(self, tmp_path, capsys):
        # What a runner with no display produces: half the suite skipped, and
        # pytest itself exits 0.
        code = guard.main([write(tmp_path, 630, skipped=312)])
        out = capsys.readouterr().out
        assert code == 1
        assert '312 tests skipped' in out
        assert 'Tk display' in out, "the message must say what to go and look at"

    def test_it_names_some_of_them(self, tmp_path, capsys):
        guard.main([write(tmp_path, 630, skipped=312)])
        assert 'skipped: tests.test_widgets::test_0' in capsys.readouterr().out

    def test_the_ceiling_is_configurable(self, tmp_path):
        report = write(tmp_path, 630, skipped=12)
        assert guard.main([report]) == 1
        assert guard.main([report, '--max-skipped', '20']) == 0

    def test_the_default_ceiling_is_far_below_a_broken_runner(self):
        assert 0 < guard.DEFAULT_MAX_SKIPPED < 50


class TestTheOtherWaysARunCanBeEmpty:
    def test_failures_fail(self, tmp_path):
        assert guard.main([write(tmp_path, 630, failures=3)]) == 1

    def test_errors_fail(self, tmp_path):
        assert guard.main([write(tmp_path, 630, errors=1)]) == 1

    def test_a_collection_that_found_almost_nothing_fails(self, tmp_path):
        assert guard.main([write(tmp_path, 3), '--min-total', '100']) == 1

    def test_a_missing_report_is_not_a_pass(self, tmp_path):
        assert guard.main([str(tmp_path / 'nope.xml')]) == 2

    def test_an_unparseable_report_is_not_a_pass(self, tmp_path):
        path = tmp_path / 'broken.xml'
        path.write_text('<testsuite tests="1"', encoding='utf-8')
        assert guard.main([str(path)]) == 2
