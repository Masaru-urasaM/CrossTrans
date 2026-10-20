"""Bound translation work and prevent superseded requests from publishing state."""
from contextlib import contextmanager
from functools import wraps
import queue
import threading
import time

from src.constants import TRANSLATION_TIMEOUT_SECONDS

_local = threading.local()


class TranslationStopped(Exception):
    """A terminal user cancellation or deadline; never retry or rotate."""


class TranslationCancelled(TranslationStopped):
    pass


class TranslationTimedOut(TranslationStopped):
    pass


class TranslationTasks:
    def __init__(self):
        self.lock = threading.RLock()
        self.current = None

    def begin(self, timeout=TRANSLATION_TIMEOUT_SECONDS):
        with self.lock:
            if self.current:
                self.current.cancelled.set()
            task = TranslationTask(self, timeout)
            self.current = task
            return task


class TranslationTask:
    def __init__(self, owner, timeout):
        self.owner = owner
        self.deadline = time.monotonic() + timeout
        self.cancelled = threading.Event()
        self.attribution = None

    def is_current(self):
        with self.owner.lock:
            return self.owner.current is self and not self.cancelled.is_set()

    def check(self):
        if not self.is_current():
            raise TranslationCancelled('Translation was replaced or cancelled.')
        if self.remaining() <= 0:
            raise TranslationTimedOut('Translation timed out after 20 seconds. Please try a shorter selection or another model.')

    def remaining(self):
        return max(0.0, self.deadline - time.monotonic())

    def cancel(self):
        with self.owner.lock:
            self.cancelled.set()

    @contextmanager
    def activate(self):
        previous = current_task()
        _local.task = self
        try:
            self.check()
            yield self
        finally:
            _local.task = previous


def current_task():
    return getattr(_local, 'task', None)


def check_current():
    task = current_task()
    if task:
        task.check()


def active_write(function):
    """Serialize a small state write with replacement/deadline checks."""
    @wraps(function)
    def guarded(*args, **kwargs):
        task = current_task()
        if task:
            with task.owner.lock:
                task.check()
                return function(*args, **kwargs)
        return function(*args, **kwargs)
    return guarded


def request_budget(function):
    """Nested calls, retries and model rotation share one monotonic deadline."""
    @wraps(function)
    def bounded(*args, **kwargs):
        if current_task():
            check_current()
            return function(*args, **kwargs)
        task = TranslationTasks().begin()
        with task.activate():
            return function(*args, **kwargs)
    return bounded


def pause(seconds):
    task = current_task()
    if task is None:
        time.sleep(seconds)
        return
    task.check()
    task.cancelled.wait(min(seconds, task.remaining()))
    task.check()


def bounded_io(function):
    """Stop waiting promptly; a provider may still finish an already-sent request."""
    task = current_task()
    if task is None:
        return function()
    task.check()
    done = threading.Event()
    outcome = []

    def transport():
        try:
            with task.activate():
                value = function()
            outcome.append((True, value))
        except Exception as error:
            outcome.append((False, error))
        finally:
            done.set()

    threading.Thread(target=transport, daemon=True, name='TranslationTransport').start()
    while True:
        task.check()
        if done.wait(min(0.05, task.remaining())):
            task.check()
            successful, value = outcome[0]
            if successful:
                return value
            raise value


class TranslationResult(tuple):
    def __new__(cls, values, task):
        result = super().__new__(cls, values)
        result.task = task
        result.attribution = task.attribution
        return result


class TranslationQueue(queue.Queue):
    def put(self, item, block=True, timeout=None):
        task = current_task()
        if task:
            try:
                task.check()
            except TranslationStopped:
                return
            item = TranslationResult(item, task)
        super().put(item, block, timeout)
