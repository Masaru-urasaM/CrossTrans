"""
Logging setup for CrossTrans.
"""
import os
import re
import sys
import glob
import time
import logging
import traceback
from datetime import datetime

from src.constants import VERSION, APP_NAME

# How long a daily log file is kept. The frozen app writes into %APPDATA%, which
# nothing ever cleans up on its behalf, so the growth has to be bounded here.
LOG_RETENTION_DAYS = 14

_LOG_NAME_RE = re.compile(r'^translator_\d{8}\.log$')


def is_frozen() -> bool:
    """True when running from the PyInstaller EXE rather than from source."""
    return getattr(sys, 'frozen', False)


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

    for path in glob.glob(os.path.join(log_dir, 'translator_*.log')):
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

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

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
