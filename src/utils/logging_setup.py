"""
Logging setup for CrossTrans.

The **file** log is JSON Lines - one `{"ts","level","tag","msg"}` object per line,
so a tool can filter it instead of a human guessing at a regex (global Rule 10).
The **console** stays human-readable: `python main.py` prints to a terminal
somebody is reading, and JSON there helps nobody.
"""
import os
import re
import sys
import json
import glob
import time
import logging
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler

from src.constants import VERSION, APP_NAME

# How long a daily log file is kept. The frozen app writes into %APPDATA%, which
# nothing ever cleans up on its behalf, so the growth has to be bounded here.
LOG_RETENTION_DAYS = 14

# ...and bounded in size as well as in time. Retention alone caps a *quiet* app;
# one runaway loop inside a single day is unbounded without this. At most
# (1 + LOG_BACKUP_COUNT) x LOG_MAX_BYTES per day.
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUP_COUNT = 3

# Today's file plus the rotated siblings RotatingFileHandler leaves beside it
# (translator_20260908.log.1). They must be prunable too, or the size cap simply
# converts unbounded growth within a day into unbounded growth across days.
# `.bak` and anything else deliberately does not match.
_LOG_NAME_RE = re.compile(r'^translator_\d{8}\.log(?:\.\d+)?$')

# 55 of the project's ~458 log calls already open with a bracketed tag -
# [ModelRotation], [Trial], [TOKENIZE]. That convention is more informative than
# the module name, so it becomes the `tag` field and leaves the message. Nothing
# at the call sites had to change for this.
_TAG_RE = re.compile(r'^\[([^\]\r\n]{1,40})\]\s*')


def is_frozen() -> bool:
    """True when running from the PyInstaller EXE rather than from source."""
    return getattr(sys, 'frozen', False)


class JsonLinesFormatter(logging.Formatter):
    """One JSON object per line: ts, level, tag, msg (global Rule 10).

    `ts` carries a real UTC offset rather than a bare local timestamp: a log is
    read next to a user saying "it broke at three", and read by a tool that must
    not guess which three.
    """

    def format(self, record: logging.LogRecord) -> str:
        try:
            message = record.getMessage()
        except Exception as exc:                     # a bad %-format must not lose the line
            message = f"<unformattable log record: {exc!r}>"

        matched = _TAG_RE.match(message)
        if matched:
            tag = matched.group(1)
            message = message[matched.end():]
        else:
            tag = record.module

        entry = {
            'ts': datetime.fromtimestamp(record.created).astimezone()
                          .isoformat(timespec='milliseconds'),
            'level': record.levelname,
            'tag': tag,
            'msg': message,
        }
        # Only when it adds something: with no bracketed tag the two are equal.
        if record.module != tag:
            entry['mod'] = record.module
        if record.exc_info:
            entry['trace'] = self.formatException(record.exc_info)

        return json.dumps(entry, ensure_ascii=False)


def resolve_log_dir() -> str:
    """Where the log file belongs.

    From source: `<project>/logs`, next to the code being worked on.

    From the EXE: `%APPDATA%/CrossTrans/logs`. It must NOT be derived from
    `__file__` there - under a onefile build that path is inside the temporary
    `_MEIxxxxx` extraction directory, which PyInstaller deletes on exit. Logs
    written there are gone by the time anyone asks for them, which is the exact
    moment they matter. (Measured 2026-09-07: six orphaned `_MEI*` directories,
    202 MB, each holding a `logs/translator_*.log` nobody could have found.)
    """
    if is_frozen():
        return os.path.join(os.environ.get('APPDATA', '.'), APP_NAME, 'logs')

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, 'logs')


def prune_old_logs(log_dir: str, retention_days: int = LOG_RETENTION_DAYS) -> int:
    """Delete daily logs older than `retention_days`. Returns how many went.

    Only files this module writes are considered - the name pattern is matched
    exactly, so nothing else that happens to sit in the directory is touched.
    """
    cutoff = time.time() - retention_days * 86400
    removed = 0

    for path in glob.glob(os.path.join(log_dir, 'translator_*.log*')):
        if not _LOG_NAME_RE.match(os.path.basename(path)):
            continue
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except OSError:
            pass  # in use by another instance, or already gone

    return removed


def setup_logging():
    """Setup logging to file and console for crash debugging."""
    log_dir = resolve_log_dir()
    os.makedirs(log_dir, exist_ok=True)
    prune_old_logs(log_dir)

    log_file = os.path.join(log_dir, f'translator_{datetime.now().strftime("%Y%m%d")}.log')

    # delay=True: no empty file for a run that never logs, and nothing to leak
    # when a caller builds the handler without installing it.
    #
    # Deliberately NOT buffered, though Rule 10 suggests it. Every line this app
    # most needs survives an ending that skips cleanup: the updater exits with
    # os._exit(0) (see CLAUDE.md), the crash hook writes as the process dies, and
    # the already-running watchdog force-exits. A buffer would drop exactly those.
    file_handler = RotatingFileHandler(
        log_file, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT,
        encoding='utf-8', delay=True)
    file_handler.setFormatter(JsonLinesFormatter())

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))

    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])

    def exception_handler(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.critical("Uncaught exception:", exc_info=(exc_type, exc_value, exc_tb))
        logging.critical("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))

    sys.excepthook = exception_handler
    logging.info(f"CrossTrans v{VERSION} started")
    logging.info(f"Log file: {log_file}")

    return log_file
