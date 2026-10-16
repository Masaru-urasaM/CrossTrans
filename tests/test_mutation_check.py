"""
Tests for tools/mutation_check.py - the runner that checked every phase since J1.

Runs the real tool on a throwaway module and test in a temporary directory: a
mutation the test catches, one it cannot (an equivalent mutant), a pattern that is
not there, and a test file that does not even import. The target file must come
back byte for byte, CRLF and all.
"""
import importlib.util
import json
import os

import pytest

TOOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'tools', 'mutation_check.py')
spec = importlib.util.spec_from_file_location('mutation_check', TOOL)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

MODULE = b"def add(a, b):\r\n    return a + b\r\n"


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'calc.py').write_bytes(MODULE)
    (tmp_path / 'test_calc.py').write_text(
        "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding='utf-8')
    (tmp_path / 'test_broken.py').write_text("import no_such_module_anywhere\n",
                                             encoding='utf-8')
    return tmp_path


def write_list(project, mutations):
    path = project / 'mut_list.py'
    path.write_text(f"MUTATIONS = {mutations!r}\n", encoding='utf-8')
    return str(path)


def run(project, mutations):
    code = tool.main([write_list(project, mutations), '--root', str(project),
                      '--log-dir', str(project / 'logs')])
    log = (project / 'logs' / 'mutation_mut_list.jsonl').read_text(encoding='utf-8')
    return code, [json.loads(line) for line in log.splitlines()]


def test_a_caught_mutation_is_killed_and_the_file_restored(project):
    code, records = run(project, [
        ("plus to minus", "calc.py", "    return a + b", "    return a - b", ["test_calc.py"])])
    assert code == 0
    assert records[0]['result'] == 'killed'
    assert (project / 'calc.py').read_bytes() == MODULE           # CRLF kept


def test_a_pattern_written_with_newlines_matches_a_crlf_file(project):
    # Lists are written with \n; calc.py, like much of this repo, is CRLF.
    code, records = run(project, [
        ("two lines", "calc.py", "def add(a, b):\n    return a + b",
         "def add(a, b):\n    return a * b", ["test_calc.py"])])
    assert code == 0 and records[0]['result'] == 'killed'
    assert (project / 'calc.py').read_bytes() == MODULE


def test_an_equivalent_mutation_survives(project):
    code, records = run(project, [
        ("commuted", "calc.py", "    return a + b", "    return b + a", ["test_calc.py"])])
    assert code == 1
    assert records[0]['result'] == 'survived'
    assert (project / 'calc.py').read_bytes() == MODULE


def test_a_missing_pattern_is_a_setup_failure(project):
    code, records = run(project, [
        ("not there", "calc.py", "return a * b", "return 0", ["test_calc.py"])])
    assert code == 1
    assert records[0]['result'] == 'setup-fail' and records[0]['count'] == 0


def test_a_pattern_found_twice_is_a_setup_failure(project):
    # Which of the two to mutate would be a guess; the list must be exact.
    code, records = run(project, [
        ("ambiguous", "calc.py", "a", "x", ["test_calc.py"])])
    assert code == 1
    assert records[0]['result'] == 'setup-fail' and records[0]['count'] > 1
    assert (project / 'calc.py').read_bytes() == MODULE


def test_a_test_that_never_ran_is_not_a_kill(project):
    code, records = run(project, [
        ("plus to minus", "calc.py", "    return a + b", "    return a - b", ["test_broken.py"])])
    assert code == 1
    assert records[0]['result'] == 'survived'
    assert 'no test failed' in records[0]['summary']


def test_two_same_size_mutants_in_one_second_each_run_their_own_code(project):
    # The stale-bytecode trap: 'a - b' and 'b + a' make files of the same size,
    # written within a second. The second must be tested as itself - equivalent,
    # so it survives - not as the first, which the test kills.
    code, records = run(project, [
        ("minus", "calc.py", "    return a + b", "    return a - b", ["test_calc.py"]),
        ("same size, equivalent", "calc.py", "    return a + b", "    return b + a",
         ["test_calc.py"]),
        ("longer, equivalent", "calc.py", "    return a + b", "    return a + 0 + b",
         ["test_calc.py"]),
    ])
    assert [r['result'] for r in records] == ['killed', 'survived', 'survived']
    assert (project / 'calc.py').read_bytes() == MODULE


def test_an_unreadable_list_is_refused(project):
    bad = project / 'bad.py'
    bad.write_text("NOT_MUTATIONS = []\n", encoding='utf-8')
    assert tool.main([str(bad), '--root', str(project), '--log-dir', str(project)]) == 2
