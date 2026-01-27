"""
Logging setup for CrossTrans.
"""
import os
import sys
import logging
import traceback
from datetime import datetime

from src.constants import VERSION


def setup_logging():
    """Setup logging to file and console for crash debugging."""
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'logs')
    os.makedirs(log_dir, exist_ok=True)

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
