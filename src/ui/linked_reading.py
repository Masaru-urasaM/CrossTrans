"""Debounced bidirectional hover for an exact, immutable pair of result boxes."""
from bisect import bisect_right
import tkinter as tk

from src.constants import LINKED_READING_DELAY_MS


class LinkedReadingController:
    def __init__(self, root, source, translated, metadata, suspended=lambda: False):
        self.root = root
        self.boxes = (source, translated)
        self.groups = metadata['groups']
        self.starts = [[g[key][0] for g in self.groups] for key in ('source', 'translated')]
        self.keys = ('source', 'translated')
        self.suspended = suspended
        self.active = None
        self.pending = None
        self.timer = None
        self.closed = False
        self.dragging = False
        self.bindings = []
        self.scrolls = {}
        self.pointer = None
        for side, box in enumerate(self.boxes):
            box.prepare_plain_map()
            for part in box.linked_event_parts():
                for sequence, handler in (
                    ('<Motion>', lambda e, s=side: self.motion(s, e.x_root, e.y_root, e.state)),
                    ('<Leave>', self.leave),
                    ('<ButtonPress-1>', self.press),
                    ('<ButtonRelease-1>', self.release),
                    ('<MouseWheel>', lambda e, s=side: self.geometry_changed(e, side=s)),
                    ('<Configure>', lambda e, s=side: self.geometry_changed(e, side=s)),
                ):
                    token = part.bind(sequence, handler, add='+')
                    self.bindings.append((part, sequence, token))
            # Scrollbars, keyboard scrolling and wheel changes all pass here.
            previous = box.cget('yscrollcommand')
            state = {'old': previous, 'fractions': None, 'command': None}
            self.scrolls[box] = state
            def scrolled(first, last, widget=box, number=side, saved=state):
                if saved['old']:
                    widget.tk.call(*widget.tk.splitlist(saved['old']), first, last)
                fractions = first, last
                if fractions != saved['fractions']:
                    saved['fractions'] = fractions
                    self.geometry_changed(side=number)
            state['command'] = box.register(scrolled)
            box.configure(yscrollcommand=state['command'])

    def watch_scroll(self, box):
        state = self.scrolls.get(box)
        if state is not None and not self.closed:
            current = str(box.cget('yscrollcommand'))
            if current != state['command']:
                state['old'] = current
                box.configure(yscrollcommand=state['command'])

    def _cancel(self):
        if self.timer is not None:
            try:
                self.root.after_cancel(self.timer)
            except tk.TclError:
                pass
            self.timer = None
        self.pending = None

    def _alive(self):
        try:
            return not self.closed and all(box.winfo_exists() for box in self.boxes)
        except tk.TclError:
            return False

    def clear(self):
        self._cancel()
        self.active = None
        for box in self.boxes:
            try:
                box.highlight_plain_range()
            except tk.TclError:
                pass

    def motion(self, side, x_root, y_root, state=None):
        if not self._alive():
            self.close()
            return
        if state is not None:
            self.dragging = bool(state & 0x0100)
        self.pointer = side, x_root, y_root
        if self.dragging or self.suspended():
            self.clear()
            return
        box = self.boxes[side]
        offset = box.plain_offset_at(x_root, y_root)
        index = bisect_right(self.starts[side], offset) - 1 if offset is not None else -1
        if index < 0:
            self.clear()
            return
        key = side, index
        if self.active == key or self.pending == key:
            return
        self._cancel()
        self.pending = key
        self.timer = self.root.after(LINKED_READING_DELAY_MS, lambda: self.activate(side, index))

    def activate(self, side, index):
        self.timer = None
        self.pending = None
        if not self._alive():
            self.close()
            return
        if self.dragging or self.suspended():
            return
        self.active = side, index
        group = self.groups[index]
        for number, box in enumerate(self.boxes):
            box.highlight_plain_range(group[self.keys[number]], animate=True)
        self.boxes[1 - side].see_plain_range(group[self.keys[1 - side]])

    def leave(self, event=None):
        if self.closed:
            return
        self._cancel()
        def check():
            self.timer = None
            if not self._alive():
                self.close()
                return
            x, y = self.root.winfo_pointerxy()
            for box in self.boxes:
                if (box.winfo_rootx() <= x < box.winfo_rootx() + box.winfo_width()
                        and box.winfo_rooty() <= y < box.winfo_rooty() + box.winfo_height()):
                    return
            self.clear()
        self.timer = self.root.after(LINKED_READING_DELAY_MS, check)

    def press(self, event=None):
        self.dragging = True
        self.clear()

    def release(self, event=None):
        self.dragging = False

    def geometry_changed(self, event=None, side=None):
        # Invalidate pending coordinates, but counterpart scrolling must not
        # turn itself into a reciprocal hover on the other pane.
        if self.closed or self.pointer is None:
            return
        owner, x, y = self.pointer
        if side != owner:
            return
        self._cancel()
        self.active = None
        def refresh():
            self.timer = None
            if not self.closed:
                self.motion(owner, x, y)
        self.timer = self.root.after_idle(refresh)

    def close(self):
        if self.closed:
            return
        self.clear()
        self.closed = True
        for part, sequence, token in self.bindings:
            try:
                part.unbind(sequence, token)
            except tk.TclError:
                pass
        self.bindings.clear()
        for box, state in self.scrolls.items():
            try:
                box.configure(yscrollcommand=state['old'])
                box.deletecommand(state['command'])
            except tk.TclError:
                pass
        self.scrolls.clear()
