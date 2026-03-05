"""
Update management functionality for Settings window.
"""
import sys
import logging
import threading
import webbrowser

import tkinter as tk
from tkinter import BOTH, X

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.dialogs import Messagebox
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.constants import VERSION, GITHUB_REPO
from src.utils.updates import (
    AutoUpdater,
    DownloadCancelledException,
    classify_error_type,
    UPDATE_THREAD_TIMEOUT,
    RELEASE_NOTES_MAX_LENGTH,
    PROGRESS_WINDOW_SIZE,
    THREAD_NAMES
)


class UpdateManagerMixin:
    """Mixin class providing update management functionality."""

    def _check_for_updates_click(self) -> None:
        """Handle Check for Updates button - runs full update flow with proper error handling."""
        self.check_update_btn.config(state='disabled')
        self.update_status_label.config(text="Checking for updates...", foreground='gray')

        # Create thread-safe exception container
        exception_holder = {'error': None}

        def run_update_flow():
            try:
                # Step 1: Check for update
                from datetime import datetime
                logging.info(f"[UPDATE] User initiated update check at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Current version: {VERSION})")
                result = self.updater.check_update()

                # Log result for debugging
                logging.info(f"Update check result: {result}")

                if result.get('error'):
                    error_msg = result['error']
                    logging.error(f"Update check error: {error_msg}")
                    # Record failed check for telemetry with classified error type
                    error_type = classify_error_type(error_msg)
                    self.config.record_update_check(success=False, error_type=error_type)
                    self.window.after(0, lambda: self._update_status(
                        f"Error: {error_msg}", 'red'))
                    return

                if not result.get('has_update'):
                    current_version = result.get('version', VERSION)
                    logging.info(f"No update available. Current: {current_version}")
                    # Record successful check for telemetry
                    self.config.record_update_check(success=True)
                    self.window.after(0, lambda: self._update_status(
                        f"You're up to date (v{current_version})", 'green'))
                    return

                # Has update - ask user
                new_version = result['version']
                logging.info(f"Update available: {new_version}")
                # Record successful check for telemetry (update available)
                self.config.record_update_check(success=True)
                self.window.after(0, lambda: self._confirm_update(new_version))

            except Exception as e:
                # Catch any unhandled exceptions
                logging.error(f"Unexpected error in update flow: {e}", exc_info=True)
                exception_holder['error'] = str(e)
                self.window.after(0, lambda: self._update_status(
                    f"Unexpected error: {str(e)}", 'red'))

        # Use non-daemon thread to ensure exceptions are captured
        thread = threading.Thread(
            target=run_update_flow,
            daemon=False,
            name=THREAD_NAMES['check']
        )
        thread.start()

        # Monitor thread health with timeout
        def monitor_thread():
            thread.join(timeout=UPDATE_THREAD_TIMEOUT)
            if thread.is_alive():
                logging.error("Update check thread timeout!")
                self.window.after(0, lambda: self._update_status(
                    "Update check timed out", 'red'))

        threading.Thread(
            target=monitor_thread,
            daemon=True,
            name=THREAD_NAMES['monitor']
        ).start()

    def _confirm_update(self, new_version: str) -> None:
        """Ask user to confirm update with release notes displayed.

        Shows different dialogs based on whether running from source or EXE:
        - Source: Opens browser to GitHub releases page
        - EXE: Offers to download and install update automatically

        Args:
            new_version: Version number of available update (e.g., "1.9.7")
        """
        is_exe = getattr(sys, 'frozen', False)

        # Get release notes from updater
        release_notes = getattr(self.updater, 'release_notes', '')
        if release_notes:
            # Truncate if too long
            if len(release_notes) > RELEASE_NOTES_MAX_LENGTH:
                release_notes = release_notes[:RELEASE_NOTES_MAX_LENGTH] + "..."
            notes_text = f"\n\nWhat's new:\n{release_notes}\n"
        else:
            notes_text = "\n"

        if not is_exe:
            # Running from source - open download page
            message = (f"New version v{new_version} available!\n"
                       f"Current: v{VERSION}\n"
                       f"{notes_text}"
                       f"You're running from source.\n"
                       f"Open download page?")

            if HAS_TTKBOOTSTRAP:
                answer = Messagebox.yesno(
                    message,
                    title="Update Available", parent=self.window)
                if answer == "Yes":
                    webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases/latest")
            else:
                from tkinter import messagebox
                if messagebox.askyesno("Update Available", message, parent=self.window):
                    webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases/latest")
            self._update_status(f"v{new_version} available", 'green')
            return

        # Running as exe - offer auto-update
        message = (f"New version v{new_version} available!\n"
                   f"Current: v{VERSION}\n"
                   f"{notes_text}"
                   f"Download and install now?")

        if HAS_TTKBOOTSTRAP:
            answer = Messagebox.yesno(
                message,
                title="Update Available", parent=self.window)
            if answer != "Yes":
                self._update_status(f"v{new_version} available", 'green')
                return
        else:
            from tkinter import messagebox
            if not messagebox.askyesno("Update Available", message, parent=self.window):
                self._update_status(f"v{new_version} available", 'green')
                return

        # User accepted - start download
        self._start_update_download(new_version)

    def _start_update_download(self, new_version: str) -> None:
        """Download update with progress dialog.

        Args:
            new_version: Version number being downloaded (e.g., "1.9.7")
        """
        # Create progress window
        self.progress_win = tk.Toplevel(self.window)
        self.progress_win.title("Updating")
        self.progress_win.geometry(PROGRESS_WINDOW_SIZE)
        self.progress_win.resizable(False, False)
        self.progress_win.transient(self.window)
        self.progress_win.grab_set()

        # Center
        self.progress_win.update_idletasks()
        x = self.window.winfo_x() + (self.window.winfo_width() - 350) // 2
        y = self.window.winfo_y() + (self.window.winfo_height() - 150) // 2
        self.progress_win.geometry(f"+{x}+{y}")

        frame = ttk.Frame(self.progress_win, padding=15)
        frame.pack(fill=BOTH, expand=True)

        self.progress_text = ttk.Label(frame, text=f"Downloading v{new_version}...")
        self.progress_text.pack(anchor=tk.W)

        if HAS_TTKBOOTSTRAP:
            self.progress_bar = ttk.Progressbar(frame, length=320, bootstyle="success-striped")
        else:
            self.progress_bar = ttk.Progressbar(frame, length=320)
        self.progress_bar.pack(fill=X, pady=10)

        # Add cancel button
        cancel_btn = ttk.Button(frame, text="Cancel", command=self._cancel_download)
        cancel_btn.pack(pady=5)

        # Thread-safe cancellation event
        self.download_cancel_event = threading.Event()

        def download_thread():
            def on_progress(percent):
                if self.download_cancel_event.is_set():
                    logging.info("Download cancelled by user")
                    raise DownloadCancelledException("User cancelled download")
                self.window.after(0, lambda p=percent: self._set_progress(p))

            try:
                result = self.updater.download(on_progress)
                if not self.download_cancel_event.is_set():
                    self.window.after(0, lambda: self._on_download_done(result, new_version))
            except DownloadCancelledException:
                logging.info("Download cancelled by user")
                self.window.after(0, lambda: self._update_status("Download cancelled", 'gray'))
            except Exception as e:
                logging.error(f"Download error: {e}", exc_info=True)
                self.window.after(0, lambda: self._update_status(f"Download failed: {e}", 'red'))
            finally:
                if hasattr(self, 'progress_win') and self.progress_win.winfo_exists():
                    self.progress_win.destroy()

        threading.Thread(
            target=download_thread,
            daemon=False,
            name=THREAD_NAMES['download']
        ).start()

    def _cancel_download(self) -> None:
        """Cancel ongoing download by setting thread-safe cancellation event."""
        from datetime import datetime
        version_info = getattr(self.updater, 'latest_version', 'unknown')
        logging.info(
            f"[UPDATE] User cancelled download at {datetime.now().strftime('%H:%M:%S')} "
            f"(Target version: {version_info}, Thread: {threading.current_thread().name})"
        )
        if hasattr(self, 'download_cancel_event'):
            self.download_cancel_event.set()
        if hasattr(self, 'progress_text'):
            self.progress_text.config(text="Cancelling...")

    def _set_progress(self, percent: int) -> None:
        """Update progress bar with download percentage.

        Args:
            percent: Download progress percentage (0-100)
        """
        if hasattr(self, 'progress_bar') and hasattr(self, 'progress_win') and self.progress_win.winfo_exists():
            self.progress_bar['value'] = percent
            self.progress_text.config(text=f"Downloading... {percent}%")

    def _on_download_done(self, result: dict, new_version: str) -> None:
        """Handle download completion and prompt for installation.

        Args:
            result: Download result dict with 'success' and optional 'error' keys
            new_version: Version number that was downloaded (e.g., "1.9.7")
        """
        if hasattr(self, 'progress_win') and self.progress_win.winfo_exists():
            self.progress_win.destroy()

        if not result.get('success'):
            self._update_status(f"Download failed: {result.get('error', 'Unknown')}", 'red')
            return

        # Download success - ask to restart
        if HAS_TTKBOOTSTRAP:
            answer = Messagebox.yesno(
                f"v{new_version} downloaded!\n\n"
                f"Restart now to apply update?",
                title="Ready to Install", parent=self.window)
            if answer == "Yes":
                self.updater.install_and_restart()
            else:
                self._update_status("Restart app to apply update", '#0066cc')
        else:
            from tkinter import messagebox
            if messagebox.askyesno("Ready to Install",
                f"v{new_version} downloaded!\n\n"
                f"Restart now to apply update?", parent=self.window):
                self.updater.install_and_restart()
            else:
                self._update_status("Restart app to apply update", '#0066cc')

    def _update_status(self, text: str, color: str) -> None:
        """Update status label and re-enable button. Change button text to 'Retry' on error.

        Args:
            text: Status message to display
            color: Foreground color for the message ('green', 'red', 'gray', etc.)
        """
        self.check_update_btn.config(state='normal')
        self.update_status_label.config(text=text, foreground=color)

        # If error, change button text to "Retry"
        if 'error' in text.lower() or 'failed' in text.lower() or 'timed out' in text.lower():
            self.check_update_btn.config(text="Retry Update Check")
            logging.info("Update check failed - retry available")
        else:
            self.check_update_btn.config(text="Check for Updates")
