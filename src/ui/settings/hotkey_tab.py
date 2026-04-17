"""
Hotkey tab functionality for Settings window.
"""
import logging

import keyboard

import tkinter as tk
from tkinter import BOTH, X, LEFT, W, NW, END

try:
    import ttkbootstrap as ttk
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.constants import LANGUAGES


class HotkeyTabMixin:
    """Mixin class providing Hotkey tab functionality."""

    def _create_hotkey_tab(self, parent):
        """Create hotkey settings tab."""
        # Clear previous entries
        self.hotkey_entries = {}
        self.custom_rows = []

        ttk.Label(parent, text="Keyboard Shortcuts", font=('Segoe UI', 12, 'bold')).pack(anchor=W)
        ttk.Label(parent, text="Click 'Edit' and press your desired key combination.",
                  font=('Segoe UI', 9)).pack(anchor=W, pady=(5, 15))

        # Scrollable frame for hotkeys
        canvas = tk.Canvas(parent, highlightthickness=0)
        hotkey_container = ttk.Frame(canvas)

        canvas.pack(side=LEFT, fill=BOTH, expand=True)

        window_id = canvas.create_window((0, 0), window=hotkey_container, anchor=NW)

        def _configure_canvas(event):
            canvas.itemconfig(window_id, width=event.width)
        canvas.bind('<Configure>', _configure_canvas)

        def _on_mousewheel(event):
            if canvas.winfo_exists() and canvas.winfo_ismapped():
                try:
                    x, y = canvas.winfo_pointerxy()
                    cx, cy = canvas.winfo_rootx(), canvas.winfo_rooty()
                    cw, ch = canvas.winfo_width(), canvas.winfo_height()
                    if cx <= x <= cx+cw and cy <= y <= cy+ch:
                        canvas.yview_scroll(int(-3*(event.delta/120)), "units")
                except tk.TclError:
                    pass  # Canvas may have been destroyed

        self.window.bind("<MouseWheel>", _on_mousewheel, add="+")

        # 1. Main Languages
        self.default_langs = ["Vietnamese", "English", "Japanese", "Chinese Simplified"]
        ttk.Label(hotkey_container, text="Main Languages", font=('Segoe UI', 10, 'bold')).pack(anchor=W, pady=(0, 10))

        saved_hotkeys = self.config.get_hotkeys()

        for lang in self.default_langs:
            current_key = saved_hotkeys.get(lang, self.config.DEFAULT_HOTKEYS.get(lang, ""))
            self._add_default_hotkey_row(hotkey_container, lang, current_key)

        ttk.Separator(hotkey_container).pack(fill=X, pady=20)

        # 2. Custom Languages
        ttk.Label(hotkey_container, text="Custom Languages", font=('Segoe UI', 10, 'bold')).pack(anchor=W, pady=(0, 10))

        self.custom_rows_frame = ttk.Frame(hotkey_container)
        self.custom_rows_frame.pack(fill=X)

        # Load existing custom hotkeys
        for lang, key in saved_hotkeys.items():
            if lang not in self.default_langs:
                self._add_custom_hotkey_row(self.custom_rows_frame, lang, key)

        # Add Button
        self.add_btn_frame = ttk.Frame(hotkey_container)
        self.add_btn_frame.pack(fill=X, pady=15)

        if HAS_TTKBOOTSTRAP:
            self.add_btn = ttk.Button(self.add_btn_frame, text="+ Add Language",
                                    command=lambda: self._add_new_custom_row(canvas, hotkey_container),
                                    bootstyle="success-outline")
        else:
            self.add_btn = ttk.Button(self.add_btn_frame, text="+ Add Language",
                                    command=lambda: self._add_new_custom_row(canvas, hotkey_container))
        self.add_btn.pack(side=LEFT)

        self._update_add_button_state()

        # 3. Screenshot Translate section
        ttk.Separator(hotkey_container).pack(fill=X, pady=20)
        ttk.Label(hotkey_container, text="Screenshot Translate", font=('Segoe UI', 10, 'bold')).pack(anchor=W, pady=(0, 10))

        self._create_screenshot_hotkey_section(hotkey_container)

        # 4. Replace Mode section
        ttk.Separator(hotkey_container).pack(fill=X, pady=20)
        ttk.Label(hotkey_container, text="Replace Mode", font=('Segoe UI', 10, 'bold')).pack(anchor=W, pady=(0, 10))
        self._create_replace_mode_section(hotkey_container)

        # 5. Furigana Mode section
        ttk.Separator(hotkey_container).pack(fill=X, pady=20)
        ttk.Label(hotkey_container, text="Furigana Mode", font=('Segoe UI', 10, 'bold')).pack(anchor=W, pady=(0, 10))
        self._create_furigana_section(hotkey_container)

        # Update scroll
        hotkey_container.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

    def _create_screenshot_hotkey_section(self, parent):
        """Create the screenshot hotkey configuration section."""
        # Hotkey row
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=5, padx=5)

        ttk.Label(row, text="Screenshot OCR:", width=22, anchor=W).pack(side=LEFT)

        self.screenshot_hotkey_var = tk.StringVar(value=self.config.get_screenshot_hotkey())
        screenshot_entry = ttk.Entry(row, textvariable=self.screenshot_hotkey_var, width=22, state='readonly')
        screenshot_entry.pack(side=LEFT, padx=5)
        self._screenshot_entry = screenshot_entry  # Save reference for recording

        if HAS_TTKBOOTSTRAP:
            ttk.Button(row, text="Edit",
                       command=lambda: self._start_record(screenshot_entry, self.screenshot_hotkey_var, "__screenshot__"),
                       bootstyle="info-outline", width=8).pack(side=LEFT, padx=2)
            ttk.Button(row, text="Restore",
                       command=self._restore_screenshot_hotkey,
                       bootstyle="secondary-outline", width=8).pack(side=LEFT, padx=2)
        else:
            ttk.Button(row, text="Edit",
                       command=lambda: self._start_record(screenshot_entry, self.screenshot_hotkey_var, "__screenshot__"),
                       width=8).pack(side=LEFT, padx=2)
            ttk.Button(row, text="Restore",
                       command=self._restore_screenshot_hotkey,
                       width=8).pack(side=LEFT, padx=2)

        # Target Language row
        lang_row = ttk.Frame(parent)
        lang_row.pack(fill=X, pady=5, padx=5)

        ttk.Label(lang_row, text="Target Language:", width=22, anchor=W).pack(side=LEFT)

        # Language options: "Auto" + all languages
        lang_options = ["Auto"] + [lang[0] for lang in LANGUAGES]
        self.screenshot_lang_var = tk.StringVar(value=self.config.get_screenshot_target_language())

        lang_combo = ttk.Combobox(lang_row, textvariable=self.screenshot_lang_var,
                                  values=lang_options, width=20, state='readonly')
        lang_combo.pack(side=LEFT, padx=5)

        # Auto-save on change
        lang_combo.bind('<<ComboboxSelected>>', lambda e: self._save_screenshot_settings())

        # Info text
        info_row = ttk.Frame(parent)
        info_row.pack(fill=X, pady=(0, 10), padx=5)
        ttk.Label(info_row, text='("Auto" uses the current language selected in main window)',
                  font=('Segoe UI', 8), foreground='#888888').pack(anchor=W, padx=(22, 0))

    def _restore_screenshot_hotkey(self):
        """Restore screenshot hotkey to default."""
        self.screenshot_hotkey_var.set(self.config.SCREENSHOT_HOTKEY_DEFAULT)
        self._save_screenshot_settings()

    def _save_screenshot_settings(self):
        """Save screenshot hotkey and target language settings."""
        if hasattr(self, 'screenshot_hotkey_var'):
            self.config.set_screenshot_hotkey(self.screenshot_hotkey_var.get())
        if hasattr(self, 'screenshot_lang_var'):
            self.config.set_screenshot_target_language(self.screenshot_lang_var.get())
        logging.info("Auto-saved screenshot settings")

    def _create_replace_mode_section(self, parent):
        """Create the Replace Mode configuration section."""
        desc = ttk.Frame(parent)
        desc.pack(fill=X, pady=(0, 10), padx=5)
        ttk.Label(desc, text="Controls what happens when you click Replace in the popup.",
                  font=('Segoe UI', 9), foreground='#888888').pack(anchor=W)

        toggle_row = ttk.Frame(parent)
        toggle_row.pack(fill=X, pady=5, padx=5)

        self.quick_replace_var = tk.BooleanVar(value=self.config.get_quick_replace())

        if HAS_TTKBOOTSTRAP:
            ttk.Checkbutton(toggle_row,
                            text="Quick Replace (paste immediately without preview)",
                            variable=self.quick_replace_var,
                            command=self._on_replace_mode_toggle,
                            bootstyle="round-toggle-success").pack(anchor=W)
        else:
            ttk.Checkbutton(toggle_row,
                            text="Quick Replace (paste immediately without preview)",
                            variable=self.quick_replace_var,
                            command=self._on_replace_mode_toggle).pack(anchor=W)

        info = ttk.Frame(parent)
        info.pack(fill=X, pady=(0, 5), padx=5)
        ttk.Label(info,
                  text="OFF = Manual Replace: Shows preview (strikethrough original \u2192 translated) with Agree/Cancel",
                  font=('Segoe UI', 8), foreground='#888888').pack(anchor=W)
        ttk.Label(info,
                  text="ON = Quick Replace: Immediately pastes translation into the source app",
                  font=('Segoe UI', 8), foreground='#888888').pack(anchor=W)

    def _on_replace_mode_toggle(self):
        """Handle Replace Mode toggle - auto-save immediately."""
        enabled = self.quick_replace_var.get()
        self.config.set_quick_replace(enabled)
        logging.info(f"Replace mode changed: quick_replace={enabled}")

    def _create_furigana_section(self, parent):
        """Create the Furigana Mode configuration section."""
        desc = ttk.Frame(parent)
        desc.pack(fill=X, pady=(0, 10), padx=5)
        ttk.Label(desc, text="Show hiragana reading guides above kanji when translating Japanese text.",
                  font=('Segoe UI', 9), foreground='#888888').pack(anchor=W)

        toggle_row = ttk.Frame(parent)
        toggle_row.pack(fill=X, pady=5, padx=5)

        self.furigana_var = tk.BooleanVar(value=self.config.get_furigana_enabled())

        if HAS_TTKBOOTSTRAP:
            ttk.Checkbutton(toggle_row,
                            text="Enable Furigana (reading guides for Japanese kanji)",
                            variable=self.furigana_var,
                            command=self._on_furigana_toggle,
                            bootstyle="round-toggle-success").pack(anchor=W)
        else:
            ttk.Checkbutton(toggle_row,
                            text="Enable Furigana (reading guides for Japanese kanji)",
                            variable=self.furigana_var,
                            command=self._on_furigana_toggle).pack(anchor=W)

        info = ttk.Frame(parent)
        info.pack(fill=X, pady=(0, 5), padx=5)
        ttk.Label(info,
                  text="OFF = Normal translation only",
                  font=('Segoe UI', 8), foreground='#888888').pack(anchor=W)
        ttk.Label(info,
                  text="ON = Shows original Japanese text with furigana readings + translation",
                  font=('Segoe UI', 8), foreground='#888888').pack(anchor=W)

    def _on_furigana_toggle(self):
        """Handle Furigana Mode toggle - auto-save immediately."""
        enabled = self.furigana_var.get()
        self.config.set_furigana_enabled(enabled)
        logging.info(f"Furigana mode changed: furigana_enabled={enabled}")

    def _add_default_hotkey_row(self, parent, language, hotkey):
        """Add a row for default languages with Restore button."""
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=5, padx=5)

        ttk.Label(row, text=f"{language}:", width=22, anchor=W).pack(side=LEFT)

        entry_var = tk.StringVar(value=hotkey)
        entry = ttk.Entry(row, textvariable=entry_var, width=22, state='readonly')
        entry.pack(side=LEFT, padx=5)
        self.hotkey_entries[language] = entry_var

        if HAS_TTKBOOTSTRAP:
            ttk.Button(row, text="Edit", command=lambda l=language: self._start_record(entry, entry_var, l),
                       bootstyle="info-outline", width=8).pack(side=LEFT, padx=2)
            ttk.Button(row, text="Restore",
                       command=lambda: entry_var.set(self.config.DEFAULT_HOTKEYS.get(language, "")),
                       bootstyle="secondary-outline", width=8).pack(side=LEFT, padx=2)
        else:
            ttk.Button(row, text="Edit", command=lambda l=language: self._start_record(entry, entry_var, l),
                       width=8).pack(side=LEFT, padx=2)
            ttk.Button(row, text="Restore",
                       command=lambda: entry_var.set(self.config.DEFAULT_HOTKEYS.get(language, "")),
                       width=8).pack(side=LEFT, padx=2)

    def _add_custom_hotkey_row(self, parent, language, hotkey, is_new=False):
        """Add a row for custom languages with Delete button."""
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=5, padx=5)

        lang_var = tk.StringVar(value=language)

        if is_new:
            # Filter available languages
            used_langs = self.default_langs + [r['lang_var'].get() for r in self.custom_rows]
            available = [l[0] for l in LANGUAGES if l[0] not in used_langs]
            all_langs = [l[0] for l in LANGUAGES]

            combo = ttk.Combobox(row, textvariable=lang_var, values=all_langs, width=20)
            combo.pack(side=LEFT)
            if available:
                combo.set(available[0])
        else:
            ttk.Label(row, text=f"{language}:", width=22, anchor=W).pack(side=LEFT)

        entry_var = tk.StringVar(value=hotkey)
        entry = ttk.Entry(row, textvariable=entry_var, width=22, state='readonly')
        entry.pack(side=LEFT, padx=5)

        if HAS_TTKBOOTSTRAP:
            ttk.Button(row, text="Edit", command=lambda lv=lang_var: self._start_record(entry, entry_var, lv.get()),
                       bootstyle="info-outline", width=8).pack(side=LEFT, padx=2)
            ttk.Button(row, text="Delete",
                       command=lambda: self._delete_custom_row(row, lang_var),
                       bootstyle="danger-outline", width=8).pack(side=LEFT, padx=2)
        else:
            ttk.Button(row, text="Edit", command=lambda lv=lang_var: self._start_record(entry, entry_var, lv.get()),
                       width=8).pack(side=LEFT, padx=2)
            ttk.Button(row, text="Delete",
                       command=lambda: self._delete_custom_row(row, lang_var),
                       width=8).pack(side=LEFT, padx=2)

        self.custom_rows.append({
            'frame': row,
            'lang_var': lang_var,
            'key_var': entry_var
        })
        # Only update button if it exists (button is created after initial rows)
        if hasattr(self, 'add_btn'):
            self._update_add_button_state()

    def _add_new_custom_row(self, canvas, container):
        """Handle adding a new custom row."""
        if len(self.custom_rows) < 4:
            self._add_custom_hotkey_row(self.custom_rows_frame, "", "", is_new=True)
            container.update_idletasks()
            canvas.config(scrollregion=canvas.bbox("all"))

    def _delete_custom_row(self, row_frame, lang_var):
        """Delete a custom row."""
        row_frame.destroy()
        self.custom_rows = [r for r in self.custom_rows if r['lang_var'] != lang_var]
        self._update_add_button_state()

    def _update_add_button_state(self):
        """Enable/disable add button based on count."""
        if len(self.custom_rows) >= 4:
            self.add_btn.configure(state='disabled')
        else:
            self.add_btn.configure(state='normal')

    def _start_record(self, entry, entry_var, language=None):
        """Start recording hotkey."""
        # Store the previous hotkey value in case we need to revert
        self._previous_hotkey = entry_var.get()
        self._recording_language = language

        entry.config(state='normal')
        entry.delete(0, END)
        entry.insert(0, "Press keys...")

        # Unhook any existing
        try:
            keyboard.unhook_all()
        except Exception:
            pass  # Keyboard hooks may not be active

        # Hook with specific callback for this entry
        keyboard.hook(lambda e: self._on_key_record(e, entry_var, entry))

    def _validate_hotkey(self, hotkey: str, current_language: str) -> tuple:
        """Validate hotkey is valid and not duplicate.

        Returns:
            tuple: (is_valid: bool, error_message: str)
        """
        if not hotkey or hotkey == "Press keys...":
            return False, "No hotkey recorded"

        # Check for reserved system hotkeys
        reserved_hotkeys = [
            'alt+f4', 'ctrl+alt+delete', 'ctrl+alt+del',
            'windows+l', 'win+l', 'ctrl+esc',
            'alt+tab', 'windows+tab', 'win+tab',
            'ctrl+shift+esc', 'windows+d', 'win+d'
        ]
        if hotkey.lower() in reserved_hotkeys:
            return False, f"'{hotkey}' is a reserved system hotkey"

        # Check for duplicates across all hotkeys
        for lang, entry_var in self.hotkey_entries.items():
            if lang != current_language:
                existing = entry_var.get().strip()
                if existing and existing.lower() == hotkey.lower():
                    return False, f"'{hotkey}' is already used for {lang}"

        # Check custom rows for duplicates
        for row_data in self.custom_rows:
            row_lang = row_data['lang_var'].get().strip()
            row_hotkey = row_data['key_var'].get().strip()
            if row_lang != current_language and row_hotkey.lower() == hotkey.lower():
                return False, f"'{hotkey}' is already used for {row_lang}"

        # Check screenshot hotkey for duplicates
        if current_language != "__screenshot__":
            if hasattr(self, 'screenshot_hotkey_var'):
                screenshot_key = self.screenshot_hotkey_var.get().strip()
                if screenshot_key and screenshot_key.lower() == hotkey.lower():
                    return False, f"'{hotkey}' is already used for Screenshot OCR"

        return True, ""

    def _on_key_record(self, event, entry_var, entry=None):
        """Handle key press during recording."""
        if event.event_type == 'down':
            name = keyboard.get_hotkey_name()
            entry_var.set(name)

            # Check if it's a modifier key
            modifiers = getattr(keyboard, 'all_modifiers',
                              {'alt', 'alt gr', 'ctrl', 'left alt', 'left ctrl',
                               'left shift', 'left windows', 'right alt', 'right ctrl',
                               'right shift', 'right windows', 'shift', 'windows', 'cmd'})
            is_modifier = event.name in modifiers

            # If not a modifier, we assume the combo is complete
            if not is_modifier:
                keyboard.unhook_all()

                # Validate the recorded hotkey
                current_lang = getattr(self, '_recording_language', None) or ''
                is_valid, error_msg = self._validate_hotkey(name, current_lang)

                if not is_valid:
                    # Show warning and revert to previous value
                    from tkinter import messagebox
                    messagebox.showwarning(
                        "Invalid Hotkey",
                        f"{error_msg}\n\nPlease choose a different hotkey.",
                        parent=self.window
                    )
                    # Revert to previous value
                    previous = getattr(self, '_previous_hotkey', '')
                    entry_var.set(previous if previous and previous != "Press keys..." else "")
                else:
                    # Valid hotkey - auto-save immediately
                    if current_lang == "__screenshot__":
                        self._save_screenshot_settings()
                    else:
                        self._save_all_hotkeys()

                if entry:
                    entry.config(state='readonly')

    def _save_all_hotkeys(self):
        """Save all hotkeys to config (auto-save after recording)."""
        hotkeys = {}

        # 1. Default languages
        for lang, entry_var in self.hotkey_entries.items():
            value = entry_var.get().strip()
            if value and value != "Press keys...":
                hotkeys[lang] = value

        # 2. Custom languages
        for row in self.custom_rows:
            lang = row['lang_var'].get().strip()
            value = row['key_var'].get().strip()
            if lang and value and value != "Press keys...":
                hotkeys[lang] = value

        self.config.set_hotkeys(hotkeys)
        logging.info("Auto-saved hotkeys")
