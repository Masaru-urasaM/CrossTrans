#!/usr/bin/env python3
"""
CrossTrans - Main Entry Point

This is the modular entry point for CrossTrans.
It initializes the application using the refactored module structure.

For backward compatibility, you can still run translator.py directly.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk

try:
    from ttkbootstrap.dialogs import Messagebox
    HAS_TTKBOOTSTRAP = True
except ImportError:
    HAS_TTKBOOTSTRAP = False

from src.utils.logging_setup import setup_logging
from src.utils.single_instance import is_already_running


def main():
    """Main entry point for CrossTrans."""
    # Setup logging first
    setup_logging()

    # Check single instance
    already_running, lock_socket = is_already_running()
    if already_running:
        root = tk.Tk()
        root.withdraw()
        if HAS_TTKBOOTSTRAP:
            Messagebox.show_warning(
                "CrossTrans is already running!\n\n"
                "Check the system tray (bottom-right corner).",
                title="CrossTrans"
            )
        else:
            from tkinter import messagebox
            messagebox.showwarning(
                "CrossTrans",
                "CrossTrans is already running!\n\n"
                "Check the system tray (bottom-right corner)."
            )
        root.destroy()
        return 0

    try:
        # Import and run the app from modular structure
        from src.app import TranslatorApp
        app = TranslatorApp()
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
