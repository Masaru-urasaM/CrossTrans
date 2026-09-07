"""
Where the log file goes, and how long it stays.

The log is the only thing anyone has when a user reports a crash, and in the
shipped EXE it was being written where it could never be read. `setup_logging()`
derived the directory from `__file__`, which under a PyInstaller onefile build
points inside the temporary `_MEIxxxxx` extraction directory - deleted on exit.
Measured 2026-09-07: six orphaned `_MEI*` directories (202 MB) on one machine,
each holding a `logs/translator_*.log` that nothing would ever have found.

Moving the frozen log to %APPDATA% creates the opposite problem - nothing there
cleans up after it - so retention is pinned here as well.
"""
import os
import sys
import time

import pytest

import src.core  # noqa: F401  (must precede `config`: see project CLAUDE.md)
from src.constants import APP_NAME
from src.utils import logging_setup


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def frozen(monkeypatch):
    """Pretend we are the PyInstaller EXE."""
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    return True


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path))
    return tmp_path


def touch(path, age_days=0.0):
    path.write_text('log line\n', encoding='utf-8')
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))
    return path


class TestWhereTheLogGoes:
    def test_from_source_it_sits_next_to_the_code(self):
        assert logging_setup.is_frozen() is False
        assert logging_setup.resolve_log_dir() == os.path.join(PROJECT_ROOT, 'logs')

    def test_from_the_exe_it_goes_to_appdata(self, frozen, appdata):
        assert logging_setup.resolve_log_dir() == os.path.join(str(appdata), APP_NAME, 'logs')

    def test_from_the_exe_it_is_not_next_to_the_bundle(self, frozen, appdata, monkeypatch):
        # The regression: a path derived from __file__ lands in _MEIxxxxx, which
        # PyInstaller deletes on exit, taking the log with it.
        meipass = os.path.join(str(appdata), '_MEI123456')
        monkeypatch.setattr(sys, '_MEIPASS', meipass, raising=False)

        resolved = logging_setup.resolve_log_dir()

        assert '_MEI' not in resolved
        assert resolved.startswith(str(appdata))
        assert PROJECT_ROOT not in resolved

    def test_it_lands_beside_the_config_the_app_already_keeps(self, frozen, appdata):
        # Same %APPDATA%/CrossTrans root as config.json, so support has one place
        # to ask for.
        assert os.path.dirname(logging_setup.resolve_log_dir()) == \
            os.path.join(str(appdata), APP_NAME)


class TestRetention:
    def test_it_deletes_logs_past_the_cutoff(self, tmp_path):
        old = touch(tmp_path / 'translator_20250101.log', age_days=90)

        assert logging_setup.prune_old_logs(str(tmp_path), retention_days=14) == 1
        assert not old.exists()

    def test_it_keeps_recent_logs(self, tmp_path):
        today = touch(tmp_path / 'translator_20260907.log')
        yesterday = touch(tmp_path / 'translator_20260906.log', age_days=1)

        assert logging_setup.prune_old_logs(str(tmp_path), retention_days=14) == 0
        assert today.exists() and yesterday.exists()

    def test_it_touches_nothing_it_did_not_write(self, tmp_path):
        strangers = [
            touch(tmp_path / 'important.log', age_days=999),
            touch(tmp_path / 'translator_notes.log', age_days=999),
            touch(tmp_path / 'translator_2026.log', age_days=999),
            touch(tmp_path / 'translator_20250101.log.bak', age_days=999),
        ]

        logging_setup.prune_old_logs(str(tmp_path), retention_days=14)

        assert all(p.exists() for p in strangers)

    def test_a_file_it_cannot_delete_is_not_fatal(self, tmp_path, monkeypatch):
        # Another instance may hold today's file open on Windows.
        touch(tmp_path / 'translator_20250101.log', age_days=90)
        monkeypatch.setattr(logging_setup.os, 'remove',
                            lambda p: (_ for _ in ()).throw(OSError("locked")))

        assert logging_setup.prune_old_logs(str(tmp_path), retention_days=14) == 0

    def test_an_empty_directory_is_fine(self, tmp_path):
        assert logging_setup.prune_old_logs(str(tmp_path)) == 0

    def test_the_default_retention_is_bounded_but_useful(self):
        assert 7 <= logging_setup.LOG_RETENTION_DAYS <= 90


class TestSetupComposesThem:
    @pytest.fixture
    def quiet(self, monkeypatch, tmp_path):
        """Run setup_logging without touching this process's logging state."""
        monkeypatch.setattr(logging_setup.logging, 'basicConfig', lambda **kw: None)
        monkeypatch.setattr(logging_setup.logging, 'info', lambda *a, **k: None)
        monkeypatch.setattr(logging_setup, 'resolve_log_dir', lambda: str(tmp_path / 'logs'))
        hook = sys.excepthook
        yield tmp_path / 'logs'
        sys.excepthook = hook

    def test_it_creates_the_directory_and_returns_the_file(self, quiet):
        path = logging_setup.setup_logging()

        assert os.path.isdir(str(quiet))
        assert os.path.dirname(path) == str(quiet)
        assert os.path.basename(path).startswith('translator_')
        assert path.endswith('.log')

    def test_it_prunes_on_the_way_in(self, quiet, monkeypatch):
        pruned = []
        monkeypatch.setattr(logging_setup, 'prune_old_logs',
                            lambda d, *a, **k: pruned.append(d))

        logging_setup.setup_logging()

        assert pruned == [str(quiet)]

    def test_it_installs_the_crash_hook(self, quiet):
        logging_setup.setup_logging()

        assert sys.excepthook is not sys.__excepthook__

    def test_a_keyboard_interrupt_still_goes_to_python(self, quiet, monkeypatch):
        logging_setup.setup_logging()
        seen = []
        monkeypatch.setattr(sys, '__excepthook__', lambda *a: seen.append(a))
        critical = []
        monkeypatch.setattr(logging_setup.logging, 'critical', lambda *a, **k: critical.append(a))

        sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)

        assert len(seen) == 1
        assert critical == []
