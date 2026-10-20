"""One active translation intent; all Tk callbacks stay on the UI thread."""
import queue
import threading
import tkinter as tk

from src.core.translation_task import TranslationStopped, TranslationTasks, TranslationTimedOut


class TranslationTaskRunner:
    def __init__(self, root):
        self.root = root
        self.tasks = TranslationTasks()
        self._cleanup = None
        self._owner = None

    def cancel(self, owner=None):
        if owner is not None and owner is not self._owner:
            return
        if self.tasks.current:
            self.tasks.current.cancel()
        cleanup, self._cleanup = self._cleanup, None
        self._owner = None
        if cleanup:
            cleanup()

    def start(self, operation, on_result=None, on_error=None, on_cancel=None, owner=None):
        self.cancel()
        task = self.tasks.begin()
        self._cleanup = on_cancel
        self._owner = owner
        answers = queue.Queue()

        def worker():
            try:
                with task.activate():
                    value = operation()
                    task.check()
                answers.put((True, value))
            except Exception as error:
                answers.put((False, error))

        def poll():
            if not task.is_current():
                return
            if owner is not None:
                try:
                    if not owner.winfo_exists():
                        self.cancel(owner)
                        return
                except tk.TclError:
                    self.cancel(owner)
                    return
            if task.remaining() <= 0:
                self.cancel(owner)
                if on_error:
                    on_error(TranslationTimedOut('Translation timed out after 20 seconds. Please try a shorter selection or another model.'))
                return
            try:
                successful, value = answers.get_nowait()
            except queue.Empty:
                self.root.after(min(25, max(1, int(task.remaining() * 1000))), poll)
                return
            self._cleanup = None
            if successful:
                if on_result:
                    on_result(value)
            elif isinstance(value, TranslationStopped):
                self.cancel(owner)
                if isinstance(value, TranslationTimedOut) and on_error:
                    on_error(value)
            elif on_error:
                on_error(value)

        threading.Thread(target=worker, daemon=True, name='TranslationTask').start()
        self.root.after(1, poll)
        return task
