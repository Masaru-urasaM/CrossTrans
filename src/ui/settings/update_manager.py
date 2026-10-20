"""User-initiated update checks and cancellable downloads, with UI-thread delivery."""
import logging
import queue
import sys
import threading
import tkinter as tk
import webbrowser

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.dialogs import Messagebox
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.constants import VERSION, GITHUB_REPO
from src.utils.updates import DownloadCancelledException, classify_error_type, RELEASE_NOTES_MAX_LENGTH


class UpdateManagerMixin:
    def _updates_alive(self):
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            return False

    def refresh_update_state(self):
        """Keep a persistent entry point even after a reminder was dismissed."""
        if not self._updates_alive() or not hasattr(self, 'update_offer_frame'):
            return
        version = self.update_manager.available_version
        ready = self.update_manager.ready_update
        if ready:
            text = f'v{ready[0]} downloaded. Restart when you are ready.'
            action = self._install_ready_update
            label = 'Restart to update'
        elif version:
            text = f'Update available: v{version}'
            action = self.update_manager.request_update
            label = 'View update'
        else:
            self.update_offer_frame.pack_forget()
            return
        self.update_offer_label.configure(text=text)
        self.update_offer_button.configure(text=label, command=action)
        self.update_offer_frame.pack(anchor='w', fill='x', pady=(8, 0),
                                     after=self.update_check_frame)

    def _check_for_updates_click(self):
        if self._download_active:
            return
        self.check_update_btn.configure(state='disabled')
        self.update_status_label.configure(text='Checking for updates...', foreground='gray')
        self.update_manager.request_check(self._show_check_result)

    def _show_check_result(self, result, updater):
        if not self._updates_alive():
            return
        error = result.get('error')
        self.config.record_update_check(success=not bool(error),
                                        error_type=classify_error_type(error) if error else None)
        if error:
            self._update_status(f'Error: {error}', 'red')
        elif not result.get('has_update'):
            self._update_status(f"You're up to date (v{VERSION})", 'green')
        else:
            self._update_status(f"v{result['version']} available", 'green')
            if not self.is_translation_busy():
                self.offer_update(result['version'], updater)

    def offer_update(self, version, updater):
        if not self._updates_alive() or self._download_active:
            return
        if self.is_translation_busy():
            self._update_status('Update available. Finish or cancel the translation first.', 'gray')
            return
        if self.update_manager.ready_update:
            self.refresh_update_state()
            return
        if updater is None:
            self._check_for_updates_click()
            return
        self.updater = updater
        self._confirm_update(version)

    def _confirm_update(self, version):
        notes = getattr(self.updater, 'release_notes', '')[:RELEASE_NOTES_MAX_LENGTH]
        message = f'New version v{version} available!\nCurrent: v{VERSION}'
        if notes:
            message += f"\n\nWhat's new:\n{notes}\n"
        is_exe = getattr(sys, 'frozen', False)
        message += '\nDownload update now?' if is_exe else '\nRunning from source. Open download page?'
        if HAS_TTKBOOTSTRAP:
            accepted = Messagebox.yesno(message, title='Update Available', parent=self.window) == 'Yes'
        else:
            from tkinter import messagebox
            accepted = messagebox.askyesno('Update Available', message, parent=self.window)
        if not accepted:
            self._update_status(f'v{version} available', 'green')
        elif is_exe:
            self._start_update_download(version)
        else:
            webbrowser.open(f'https://github.com/{GITHUB_REPO}/releases/latest')

    def _start_update_download(self, version):
        if self._download_active:
            return
        self._download_active = True
        self.check_update_btn.configure(state='disabled')
        self.download_cancel_event = threading.Event()
        cancelled = self.download_cancel_event
        answers = queue.Queue()
        updater = self.updater
        self.progress_win = tk.Toplevel(self.window)
        self.progress_win.title('Downloading update')
        self.progress_win.resizable(False, False)
        self.progress_win.protocol('WM_DELETE_WINDOW', self._cancel_download)
        frame = ttk.Frame(self.progress_win, padding=18)
        frame.pack(fill='both', expand=True)
        self.progress_text = ttk.Label(frame, text=f'Downloading v{version}...')
        self.progress_text.pack(anchor='w')
        self.progress_bar = ttk.Progressbar(frame, length=320, maximum=100)
        self.progress_bar.pack(fill='x', pady=12)
        ttk.Button(frame, text='Cancel', command=self._cancel_download).pack()

        def worker():
            def progress(percent):
                if cancelled.is_set():
                    raise DownloadCancelledException('User cancelled download')
                answers.put(('progress', percent))
            try:
                result = updater.download(progress)
            except DownloadCancelledException:
                result = {'success': False, 'cancelled': True}
            except Exception as error:
                logging.exception('[Update] Download failed')
                result = {'success': False, 'error': str(error)}
            answers.put(('done', result))

        def poll():
            self._download_poll_id = None
            if not self._updates_alive():
                cancelled.set()
                return
            latest_progress = None
            done = None
            while True:
                try:
                    kind, value = answers.get_nowait()
                except queue.Empty:
                    break
                if kind == 'progress':
                    latest_progress = value
                else:
                    done = value
            if latest_progress is not None and not cancelled.is_set():
                self._set_progress(latest_progress)
            if done is not None:
                self._download_active = False
                if self.progress_win.winfo_exists():
                    self.progress_win.destroy()
                if cancelled.is_set() or done.get('cancelled'):
                    self._update_status('Download cancelled', 'gray')
                else:
                    self._on_download_done(done, version, updater)
            else:
                self._download_poll_id = self.window.after(100, poll)

        threading.Thread(target=worker, daemon=True, name='UpdateDownload').start()
        self._download_poll_id = self.window.after(100, poll)

    def _cancel_download(self):
        if hasattr(self, 'download_cancel_event'):
            self.download_cancel_event.set()
        if hasattr(self, 'progress_win') and self.progress_win.winfo_exists():
            self.progress_text.configure(text='Cancelling...')

    def _set_progress(self, percent):
        if self.progress_win.winfo_exists():
            self.progress_bar.configure(value=percent)
            self.progress_text.configure(text=f'Downloading... {percent}%')

    def _on_download_done(self, result, version, updater=None):
        if not result.get('success'):
            self._update_status(f"Download failed: {result.get('error', 'Unknown')}", 'red')
            return
        self.update_manager.ready_update = (version, updater or self.updater)
        self._update_status('Download complete. Choose Restart to update when ready.', 'green')
        self.refresh_update_state()

    def _install_ready_update(self):
        if self.is_translation_busy():
            self._update_status('Finish or cancel the translation before restarting.', 'gray')
            return
        ready = self.update_manager.ready_update
        if ready:
            result = ready[1].install_and_restart()
            if result and not result.get('success'):
                self._update_status(f"Install failed: {result.get('error', 'Unknown')}", 'red')

    def _close_update_work(self, event):
        if event.widget is not self.window:
            return
        self._download_active = False
        if hasattr(self, 'download_cancel_event'):
            self.download_cancel_event.set()
        if self._download_poll_id:
            self.window.after_cancel(self._download_poll_id)
            self._download_poll_id = None
        if self._owns_update_manager:
            self.update_manager.stop()

    def _update_status(self, text, color):
        if not self._updates_alive():
            return
        self.check_update_btn.configure(state='disabled' if self._download_active else 'normal')
        self.update_status_label.configure(text=text, foreground=color)
        failed = any(word in text.lower() for word in ('error', 'failed', 'timed out'))
        self.check_update_btn.configure(text='Retry Update Check' if failed else 'Check for updates')
