"""Check that the tests catch the bug they are about: break the code, watch them fail.

    python tools/mutation_check.py path/to/mutations.py [--root .] [--log-dir logs]

The list file is Python and defines

    MUTATIONS = [
        (name, path, old, new, pytest_args),
        ...
    ]

where `path` is relative to `--root`, `old` must occur in it exactly once, and
`pytest_args` (files and `-k` selectors) name the tests that must FAIL once `old`
is replaced by `new`. Each mutation is applied, its tests run in a subprocess,
and the file restored byte for byte - also on an error or Ctrl+C. A mutation is
KILLED when a test failed; SURVIVED otherwise, which includes a run where no test
ran at all (a collection error is not a kill). Line endings follow the target
file, so a pattern written with \\n matches a CRLF file too.

Two lessons are built in:

- **Stale bytecode.** Python keys a module's .pyc on its mtime and size. Two
  same-size mutants written within one second share both, so the second run
  executed the FIRST mutant - a result that flipped between runs gave it away
  (2026-10-15). The module's cached bytecode is deleted before each run and the
  run writes none (PYTHONDONTWRITEBYTECODE).
- **A survivor is a question, not a verdict.** It can be an equivalent mutant
  (the code behaves the same), a selector that skips the test that would catch
  it, or a missing test. The JSONL log keeps each run's last pytest line so the
  three can be told apart.

Output: one line per mutation, and <log-dir>/mutation_<list name>.jsonl. Exit
status 0 when every mutation was killed, 1 otherwise, 2 when the list is unusable.
"""
import argparse
import glob
import json
import os
import runpy
import subprocess
import sys
import time
from typing import List, Optional


def _clear_bytecode(path: str) -> None:
    """Delete the target module's cached bytecode (see the stale-bytecode lesson)."""
    stem = os.path.splitext(os.path.basename(path))[0]
    cache = os.path.join(os.path.dirname(path) or '.', '__pycache__')
    for pyc in glob.glob(os.path.join(cache, stem + '.*.pyc')):
        try:
            os.remove(pyc)
        except OSError:
            pass


def _run_tests(pytest_args: List[str], root: str) -> subprocess.CompletedProcess:
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1'}
    return subprocess.run([sys.executable, '-m', 'pytest', *pytest_args, '-q', '-x',
                           '-p', 'no:cacheprovider'],
                          cwd=root, capture_output=True, text=True, encoding='utf-8',
                          errors='replace', env=env)


def check(name: str, path: str, old: str, new: str, pytest_args: List[str],
          root: str) -> dict:
    """Apply one mutation, run its tests, restore the file. Returns the log record."""
    full = os.path.join(root, path)
    raw = open(full, 'rb').read()
    crlf = b'\r\n' in raw
    old_b = (old.replace('\n', '\r\n') if crlf else old).encode('utf-8')
    new_b = (new.replace('\n', '\r\n') if crlf else new).encode('utf-8')
    count = raw.count(old_b)
    if count != 1:
        return {'mutation': name, 'path': path, 'result': 'setup-fail', 'count': count,
                'summary': f'pattern found {count} times'}
    started = time.time()
    try:
        with open(full, 'wb') as fh:
            fh.write(raw.replace(old_b, new_b))
        _clear_bytecode(full)
        run = _run_tests(pytest_args, root)
    finally:
        with open(full, 'wb') as fh:
            fh.write(raw)
        _clear_bytecode(full)
    lines = run.stdout.strip().splitlines()
    summary = lines[-1] if lines else run.stderr.strip()[-200:]
    killed = run.returncode != 0 and ' failed' in summary
    if run.returncode != 0 and not killed:
        summary = 'no test failed - check the selector or the test file: ' + summary
    return {'mutation': name, 'path': path, 'result': 'killed' if killed else 'survived',
            'summary': summary, 'seconds': round(time.time() - started, 1)}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mutations', help='a .py file defining MUTATIONS')
    parser.add_argument('--root', default='.', help='where the paths and the tests are')
    parser.add_argument('--log-dir', default='logs')
    args = parser.parse_args(argv)

    try:
        mutations = runpy.run_path(args.mutations)['MUTATIONS']
    except (OSError, KeyError, SyntaxError) as exc:
        print(f"FAIL: cannot read MUTATIONS from {args.mutations}: {exc}")
        return 2

    label = os.path.splitext(os.path.basename(args.mutations))[0]
    os.makedirs(args.log_dir, exist_ok=True)
    log_path = os.path.join(args.log_dir, f'mutation_{label}.jsonl')
    survived = []
    with open(log_path, 'w', encoding='utf-8') as log:
        for name, path, old, new, pytest_args in mutations:
            record = check(name, path, old, new, list(pytest_args), args.root)
            log.write(json.dumps(record, ensure_ascii=False) + '\n')
            log.flush()
            word = {'killed': 'KILLED  ', 'survived': 'SURVIVED',
                    'setup-fail': 'SETUP FAIL'}[record['result']]
            print(f"{word} [{name}] -> {record['summary']}")
            if record['result'] != 'killed':
                survived.append(name)
    print("ALL MUTATIONS KILLED" if not survived else f"NOT KILLED: {survived}")
    print(f"-> {log_path}")
    return 1 if survived else 0


if __name__ == '__main__':
    sys.exit(main())
