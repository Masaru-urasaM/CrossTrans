"""
Update status checking and UI management for CrossTrans.

Handles checking previous update status, showing update dialogs,
and startup update checks.
"""
import os
import sys
import logging
import threading
import queue
import time
import tkinter as tk
from typing import Optional

from src.constants import VERSION
from src.ui.toast import ToastType
from src.utils.updates import (
    AutoUpdater,
    STARTUP_UPDATE_DELAY,
    UPDATE_THREAD_TIMEOUT,
    THREAD_NAMES
)
from src.core.update_policy import UPDATE_INTERVAL_SECONDS, should_notify, reminder_changes
from src.ui.update_notice import UpdateNotice


class UpdateUIManager:
    """Manages update status checking and UI feedback.

    Responsibilities:
    - Check status files from previous update attempts
    - Show success/failure dialogs after UI initialization
    - Perform silent startup update checks
    - Show update available notifications
    """

    def __init__(self, root, config, toast_manager):
        """Initialize the update UI manager.

        Args:
            root: Root Tk window
            config: Config object
            toast_manager: ToastManager instance for notifications
        """
        self.root = root
        self.config = config
        self.toast = toast_manager

        # Pending update info (set during check, shown later)
        self._pending_update_success_version: Optional[str] = None
        self._pending_update_error: Optional[str] = None
        self._pending_update_path: Optional[str] = None
        self.available_version = None
        self.available_updater = None
        self.ready_update = None
        self._on_state_changed = None
        self._on_open_update = None
        self._is_busy = lambda: False
        self._answers = queue.Queue()
        self._commands = queue.SimpleQueue()
        self._callbacks = []
        self._request_id = 0
        self._checking = False
        self._started = False
        self._stopped = False
        self._poll_id = None
        self._notice = None
        self._pending_open = False
        self._next_check = 0
        self._check_deadline = 0

    def configure_callbacks(self, on_state_changed=None, on_open_update=None, is_busy=None):
        self._on_state_changed = on_state_changed
        self._on_open_update = on_open_update
        if is_busy:
            self._is_busy = is_busy

    def check_update_status(self) -> None:
        """Check if previous update succeeded or failed.

        Reads status files created by the update batch script:
        - crosstrans_update_error.txt: Update failed, shows error dialog
        - crosstrans_update_success.txt: Update completed
        - crosstrans_update_expected.txt: Expected version number
        - crosstrans_update_pending.txt: Path to pending update file (for reboot fallback)

        Shows appropriate feedback to user and offers MoveFileEx fallback if update failed.
        """
        temp = os.environ.get('TEMP', os.environ.get('TMP', ''))
        if not temp:
            return

        error_file = os.path.join(temp, 'crosstrans_update_error.txt')
        success_file = os.path.join(temp, 'crosstrans_update_success.txt')
        expected_file = os.path.join(temp, 'crosstrans_update_expected.txt')
        pending_file = os.path.join(temp, 'crosstrans_update_pending.txt')

        status_files = [error_file, success_file, expected_file, pending_file]

        try:
            if os.path.exists(error_file):
                # Update failed - offer reboot fallback
                error_msg = ""
                pending_path = None

                try:
                    with open(error_file, 'r') as f:
                        error_msg = f.read().strip()
                except Exception:
                    error_msg = "Unknown error"

                if os.path.exists(pending_file):
                    try:
                        with open(pending_file, 'r') as f:
                            pending_path = f.read().strip()
                    except Exception:
                        pass

                logging.warning(f"Previous update failed: {error_msg}")

                # Schedule dialog to show after UI is initialized
                self._pending_update_error = error_msg
                self._pending_update_path = pending_path

                # Cleanup status files (but keep pending for MoveFileEx if needed)
                for f in [error_file, success_file, expected_file]:
                    if os.path.exists(f):
                        try:
                            os.remove(f)
                        except Exception:
                            pass

            elif os.path.exists(success_file):
                # Check if version matches expected
                expected_ver = None
                if os.path.exists(expected_file):
                    try:
                        with open(expected_file, 'r') as f:
                            expected_ver = f.read().strip()
                    except Exception:
                        pass

                if expected_ver:
                    if VERSION == expected_ver:
                        # Success! Schedule toast after UI initialized
                        logging.info(f"Update to v{expected_ver} successful!")
                        self._pending_update_success_version = expected_ver
                    else:
                        # Version mismatch - update failed silently
                        logging.error(f"Update verification failed: Expected v{expected_ver} but running v{VERSION}")
                        self._pending_update_error = f"Expected v{expected_ver} but running v{VERSION}"
                        self._pending_update_path = None

                # Cleanup all status files
                for f in status_files:
                    if os.path.exists(f):
                        try:
                            os.remove(f)
                        except Exception:
                            pass

        except Exception as e:
            logging.warning(f"Error checking update status: {e}")

    def show_pending_dialogs(self) -> None:
        """Show any pending update dialogs after main window is ready.

        Called after the main UI components are initialized.
        """
        # Show update success toast
        if self._pending_update_success_version:
            version = self._pending_update_success_version
            self._pending_update_success_version = None
            self.root.after(2000, lambda: self._show_update_success_toast(version))

        # Show update failed dialog
        if self._pending_update_error:
            error_msg = self._pending_update_error
            pending_path = self._pending_update_path
            self._pending_update_error = None
            self._pending_update_path = None
            self.root.after(1000, lambda: self._show_update_failed_dialog(error_msg, pending_path))

    def startup_update_check(self) -> None:
        """Start the UI-thread pump, including when automatic checks are disabled."""
        if self._started or self._stopped:
            return
        self._started = True
        self._next_check = time.monotonic() + STARTUP_UPDATE_DELAY
        self._poll_id = self.root.after(250, self._tick)

    def auto_check_changed(self):
        """Apply Settings changes immediately without restarting the app."""
        self._next_check = time.monotonic() + STARTUP_UPDATE_DELAY
        if not self.config.get_auto_check_updates():
            self._close_notice()

    def request_check(self, callback=None):
        """Join one check in flight. Workers only publish to a queue, never Tk."""
        if self._stopped:
            return
        self.startup_update_check()
        if callback:
            self._callbacks.append(callback)
        if self._checking:
            return
        self._checking = True
        self._request_id += 1
        request_id = self._request_id
        self._check_deadline = time.monotonic() + UPDATE_THREAD_TIMEOUT
        self._next_check = time.monotonic() + UPDATE_INTERVAL_SECONDS

        def worker():
            updater = None
            try:
                updater = AutoUpdater()
                result = updater.check_update()
            except Exception as error:
                logging.exception('[Update] Check failed')
                result = {'error': str(error), 'has_update': False}
            self._answers.put((request_id, result, updater))

        threading.Thread(target=worker, daemon=True, name=THREAD_NAMES['check']).start()

    def _tick(self):
        self._poll_id = None
        if self._stopped:
            return
        try:
            while not self._commands.empty():
                self._commands.get_nowait()
                self._pending_open = True
            while True:
                try:
                    request_id, result, updater = self._answers.get_nowait()
                except queue.Empty:
                    break
                if self._checking and request_id == self._request_id:
                    self._finish_check(result, updater)
            if self._checking and time.monotonic() >= self._check_deadline:
                self._finish_check({'error': 'Update check timed out', 'has_update': False}, None)
            if self.config.get_auto_check_updates():
                if not self._checking and time.monotonic() >= self._next_check:
                    self.request_check()
                self._maybe_notify()
            if self._pending_open and not self._is_busy():
                self._pending_open = False
                self.request_update()
        except tk.TclError:
            self.stop()
            return
        finally:
            if not self._stopped:
                self._poll_id = self.root.after(250 if self._checking else 1000, self._tick)

    def _finish_check(self, result, updater):
        self._checking = False
        callbacks, self._callbacks = self._callbacks, []
        if result.get('error'):
            logging.warning('[Update] %s', result['error'])
        else:
            self.available_version = result.get('version') if result.get('has_update') else None
            self.available_updater = updater if self.available_version else None
            self._close_notice()
            if callbacks and self.available_version:
                self.config.set_update_reminders(**reminder_changes(
                    'shown', self.available_version, time.time()))
            if self._on_state_changed:
                self._on_state_changed()
        for callback in callbacks:
            try:
                callback(result, updater)
            except Exception:
                logging.exception('[Update] Result callback failed')

    def _maybe_notify(self):
        if not self.available_version or self._notice or self._is_busy():
            return
        if self.ready_update and self.ready_update[0] == self.available_version:
            return
        if should_notify(self.available_version, self.config.get_update_reminders(), time.time()):
            self._show_update_toast(self.available_version)

    def _close_notice(self):
        notice, self._notice = self._notice, None
        if notice:
            notice.close()

    def _notice_action(self, action, version):
        self._close_notice()
        if action == 'update':
            self.request_update()
        else:
            self.config.set_update_reminders(**reminder_changes(action, version, time.time()))

    def request_update(self):
        """Only a user action opens Settings; never interrupt an active translation."""
        if self._stopped:
            return
        self._close_notice()
        if self._is_busy():
            self._pending_open = True
        elif self.available_version and self._on_open_update:
            self._on_open_update(self.available_version, self.available_updater)

    def post_update_request(self):
        """The tray thread must not call Tk, including after()."""
        self._commands.put(None)

    def stop(self):
        self._stopped = True
        self._callbacks.clear()
        self._close_notice()
        if self._poll_id:
            self.root.after_cancel(self._poll_id)
            self._poll_id = None

    def _show_update_success_toast(self, version: str) -> None:
        """Show success toast after update.

        Args:
            version: The version that was successfully installed
        """
        self.toast.show(
            f"CrossTrans has been updated to v{version}",
            ToastType.SUCCESS,
            duration=5000
        )

    def _show_update_failed_dialog(self, error_msg: str, pending_path: str = None) -> None:
        """Show dialog when update failed, offering reboot fallback.

        Args:
            error_msg: Error message from the failed update
            pending_path: Path to the pending update file (for MoveFileEx fallback)
        """
        from src.ui.dialogs import UpdateFailedDialog

        dialog = UpdateFailedDialog(
            self.root,
            error_msg,
            pending_path,
            current_exe=sys.executable
        )

        if dialog.result == 'reboot' and pending_path:
            # User chose to schedule update for reboot
            updater = AutoUpdater()
            result = updater.schedule_update_on_reboot(pending_path, sys.executable)

            if result['success']:
                self.toast.show(
                    "Update will be applied when you restart Windows.",
                    ToastType.INFO,
                    duration=5000
                )
                # Clean up pending file marker
                pending_file = os.path.join(
                    os.environ.get('TEMP', ''),
                    'crosstrans_update_pending.txt'
                )
                if os.path.exists(pending_file):
                    try:
                        os.remove(pending_file)
                    except Exception:
                        pass
            else:
                self.toast.show(
                    result.get('message', 'Could not schedule update'),
                    duration=5000,
                    toast_type=ToastType.ERROR
                )

        elif dialog.result == 'manual':
            # Open GitHub releases page
            import webbrowser
            from src.constants import GITHUB_REPO
            webbrowser.open(f"https://github.com/{GITHUB_REPO}/releases/latest")

    def _show_update_toast(self, new_version: str) -> None:
        """Offer Update / Later / Skip without a grab or focus change."""
        self._close_notice()
        self._notice = UpdateNotice(self.root, new_version,
                                    lambda action: self._notice_action(action, new_version))
        self.config.set_update_reminders(**reminder_changes('shown', new_version, time.time()))
