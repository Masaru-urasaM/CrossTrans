"""Linked reading for an editable plain input and a read-only translation."""
import tkinter as tk
from copy import deepcopy

from src.core.translation_alignment import AlignedText, make_metadata, reading_result, validate_metadata
from src.ui.linked_reading import LinkedReadingController
from src.ui.ruby_text import RubyText, NO_AUTOSTYLE


class PlainTextLinkAdapter:
    """Share canonical mapping/painting without changing the editable Tk widget."""
    prepare_plain_map = RubyText.prepare_plain_map
    plain_offset_at = RubyText.plain_offset_at
    highlight_plain_range = RubyText.highlight_plain_range
    see_plain_range = RubyText.see_plain_range
    _cancel_link_animation = RubyText._cancel_link_animation
    _fade_link_background = RubyText._fade_link_background

    def __init__(self, widget):
        self.widget = widget
        self._plain_map = None
        self._window_base = {}
        self._linked_frames = set()
        self._linked_bg = None
        self._linked_animation = None

    def __getattr__(self, name):
        return getattr(self.widget, name)

    def get_plain(self):
        return self.widget.get('1.0', 'end-1c')

    def linked_event_parts(self):
        return [self.widget]

    def _paint_link_frames(self, _keys):
        pass


class MainLinkedReading:
    def __init__(self, root, window, source, translated, config, toolbar):
        self.root, self.window, self.config = root, window, config
        self.source = PlainTextLinkAdapter(source)
        self.translated = translated
        self.controller = None
        self.result = ''
        self.source_snapshot = ''
        self.closed = False
        self.button = tk.Button(toolbar, command=self.toggle, font=('Segoe UI', 9),
                                relief='flat', padx=10, pady=3, cursor='hand2', **NO_AUTOSTYLE)
        self.button.pack(side=tk.RIGHT, padx=(0, 8))
        self.status = tk.Label(toolbar, font=('Segoe UI', 8), fg='#8a8a8a',
                               bg=window.cget('bg'), **NO_AUTOSTYLE)
        self.status.pack(side=tk.LEFT, padx=(12, 0))
        self.setting_binding = root.bind('<<LinkedReadingChanged>>', self.sync, add='+')
        self.modified_binding = source.bind('<<Modified>>', self.modified, add='+')
        window.bind('<Destroy>', self.destroyed, add='+')
        self.sync()

    def enabled(self):
        getter = getattr(self.config, 'get_linked_reading_enabled', None)
        return getter is not None and getter() is True

    def toggle(self):
        self.config.set_linked_reading_enabled(not self.enabled())
        self.sync()
        self.root.event_generate('<<LinkedReadingChanged>>', when='tail')

    def stop(self):
        if self.controller is not None:
            self.controller.close()
            self.controller = None

    def set_result(self, result, source, target):
        self.stop()
        self.source_snapshot = source
        self.result = reading_result(result, getattr(result, 'alignment', None), source, target)
        live = self.source.get_plain()
        data = getattr(self.result, 'alignment', None)
        if data and live != source and live.strip() == source.strip():
            # Translation requests trim outside whitespace; keep the editable
            # input untouched and rebase only the displayed source coordinates.
            shift = (len(live) - len(live.lstrip())) - (len(source) - len(source.lstrip()))
            groups = deepcopy(data['groups'])
            for group in groups:
                group['source'] = [offset + shift for offset in group['source']]
            groups[0]['source'][0], groups[-1]['source'][1] = 0, len(live)
            rebased = make_metadata(live, self.result, target, data['mode'], groups)
            if data.get('method'):
                rebased['method'] = data['method']
                rebased['structure_version'] = data.get('structure_version')
            if validate_metadata(rebased, live, self.result, target):
                self.source_snapshot, self.result = live, AlignedText(self.result, rebased)
        self.source._plain_map = None
        self.sync()

    def modified(self, _event=None):
        self.source.edit_modified(False)
        self.source._plain_map = None
        self.sync()

    def sync(self, _event=None):
        if self.closed:
            return
        enabled = self.enabled()
        self.button.configure(text='Linked reading: On' if enabled else 'Linked reading: Off',
                              bg='#2e4446' if enabled else '#3a3f44',
                              fg='#b7e3dc' if enabled else '#c4cbd4',
                              activebackground='#3a5557', activeforeground='#ffffff')
        data = getattr(self.result, 'alignment', None)
        exact_pair = (self.source.get_plain() == self.source_snapshot
                      and self.translated.get_plain() == self.result)
        self.status.configure(text=(('Approximate links' if data.get('method') == 'structure'
                                     else 'Sentence links') if data else 'No reliable links')
                              if enabled and exact_pair and self.result else '')
        if not enabled or not exact_pair or not data:
            self.stop()
        elif self.controller is None:
            self.controller = LinkedReadingController(
                self.root, self.source, self.translated, data,
                suspended=lambda: bool(self.source.edit_modified()))

    def destroyed(self, event):
        if event.widget is self.window:
            self.close()

    def close(self):
        if self.closed:
            return
        self.stop()
        self.closed = True
        self.root.unbind('<<LinkedReadingChanged>>', self.setting_binding)
        try:
            self.source.unbind('<<Modified>>', self.modified_binding)
        except tk.TclError:
            pass
