#!/usr/bin/env python3
"""
CrossTrans - Main Entry Point

This is the modular entry point for CrossTrans.
It initializes the application using the refactored module structure.

For backward compatibility, you can still run translator.py directly.
"""
import sys
import os
import threading

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from tkinter import messagebox

from src.utils.logging_setup import setup_logging
from src.utils.single_instance import (
    is_already_running,
    signal_running_instance,
    serve_show_requests,
)

# A second instance has one notice to deliver and must never outlive it. It used
# to: ttkbootstrap's Messagebox builds its dialog with transient=<the root>, and
# Tk withdraws a transient window whose master is withdrawn - so show() waited in
# wait_window() on a dialog nobody could see or close. Measured 2026-09-07 with
# py-spy, on a process that had been resident since 2026-08-19.
ALREADY_RUNNING_TIMEOUT_S = 60.0


def _warn_already_running():
    """Tell the user CrossTrans is already up, then leave - whatever happens.

    The stdlib messagebox is a native Windows dialog, so a withdrawn root cannot
    hide it (verified: window class #32770, visible). The watchdog is the second
    line of defence: no trouble here can ever strand a process again.
    """
    watchdog = threading.Timer(ALREADY_RUNNING_TIMEOUT_S, lambda: os._exit(0))
    watchdog.daemon = True
    watchdog.start()
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning(
            "CrossTrans",
            "CrossTrans is already running!\n\n"
            "Check the system tray (bottom-right corner)."
        )
        root.destroy()
    finally:
        watchdog.cancel()


def main():
    """Main entry point for CrossTrans."""
    # Enable DPI awareness for crisp UI on high-DPI displays (must be before any tkinter)
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
    except Exception:
        pass  # Older Windows versions don't have this API

    # Setup logging first
    setup_logging()

    # Check single instance
    already_running, lock_socket = is_already_running()
    if already_running:
        # Somebody who launches CrossTrans twice wants the window, not a lecture
        # about the system tray. Ask the running instance for it; only fall back
        # to the notice when it does not answer - an older build still accepts
        # the connection but will never act on it.
        if signal_running_instance():
            return 0
        _warn_already_running()
        return 0

    try:
        # Import and run the app from modular structure
        from src.app import TranslatorApp
        app = TranslatorApp()
        if lock_socket:
            serve_show_requests(lock_socket, app.on_second_instance)
        app.run()
        return 0
    except Exception as e:
        import logging
        logging.critical(f"Failed to start application: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if lock_socket:
            lock_socket.close()


if __name__ == "__main__":
    sys.exit(main())
