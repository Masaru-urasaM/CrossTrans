"""Guard a CI run against a green tick that did not test anything.

Roughly half this suite - 312 of 630 tests as of 2026-09-08 - needs a usable Tk
display, and `tests/conftest.py`'s `tk_root` fixture *skips* rather than fails
when there is none. That is right for a developer on a headless shell and wrong
for CI: a runner without a desktop session would skip every widget test and
still report success, which is worse than having no CI at all because it looks
like coverage.

So the run is checked by hand: parse the JUnit XML pytest wrote, and fail when
more tests were skipped than a healthy run can explain.

    python tools/check_test_counts.py junit.xml --max-skipped 10

A handful of skips is normal (the clipboard round-trip yields when another
process owns the clipboard). Three hundred is a broken runner.
"""
import sys
import argparse
import xml.etree.ElementTree as ET
from typing import List, Tuple

# Enough room for the genuinely environment-dependent tests, far below the
# number that a missing display would produce.
DEFAULT_MAX_SKIPPED = 10


def read_results(path: str) -> Tuple[int, int, int, int, List[str]]:
    """Return (total, failures, errors, skipped, skipped_names) from JUnit XML."""
    root = ET.parse(path).getroot()
    # pytest writes <testsuites><testsuite>; older versions wrote <testsuite>.
    suites = root.findall('testsuite') or [root]

    total = failures = errors = skipped = 0
    names: List[str] = []
    for suite in suites:
        total += int(suite.get('tests', 0))
        failures += int(suite.get('failures', 0))
        errors += int(suite.get('errors', 0))
        skipped += int(suite.get('skipped', 0))
        for case in suite.iter('testcase'):
            if case.find('skipped') is not None:
                names.append(f"{case.get('classname', '')}::{case.get('name', '')}")
    return total, failures, errors, skipped, names


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', help='JUnit XML written by pytest --junitxml')
    parser.add_argument('--max-skipped', type=int, default=DEFAULT_MAX_SKIPPED)
    parser.add_argument('--min-total', type=int, default=1,
                        help='fail if fewer tests than this were collected at all')
    args = parser.parse_args(argv)

    try:
        total, failures, errors, skipped, names = read_results(args.report)
    except (OSError, ET.ParseError) as exc:
        print(f"FAIL: cannot read {args.report}: {exc}")
        return 2

    passed = total - failures - errors - skipped
    print(f"collected {total}  passed {passed}  failed {failures}  "
          f"errors {errors}  skipped {skipped}")

    problems = []
    if total < args.min_total:
        problems.append(f"only {total} tests collected, expected at least {args.min_total}")
    if failures or errors:
        problems.append(f"{failures} failed, {errors} errored")
    if skipped > args.max_skipped:
        problems.append(
            f"{skipped} tests skipped, more than the {args.max_skipped} a healthy run "
            f"explains - a runner with no usable Tk display skips every widget test "
            f"and still looks green")
        for name in names[:15]:
            print(f"    skipped: {name}")
        if len(names) > 15:
            print(f"    ... and {len(names) - 15} more")

    if problems:
        for problem in problems:
            print(f"FAIL: {problem}")
        return 1

    print("OK")
    return 0


if __name__ == '__main__':
    sys.exit(main())
