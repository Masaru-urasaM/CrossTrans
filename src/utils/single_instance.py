"""
Single instance lock for CrossTrans.
Prevents multiple instances from running simultaneously.
"""
import socket
from typing import Tuple, Optional

from src.constants import LOCK_PORT


def is_already_running() -> Tuple[bool, Optional[socket.socket]]:
    """Check if another instance is already running using socket lock."""
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.bind(('127.0.0.1', LOCK_PORT))
        lock_socket.listen(1)
        return False, lock_socket
    except socket.error:
        return True, None
