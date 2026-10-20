"""
General settings tab functionality for Settings window.
"""
import logging
import webbrowser

import tkinter as tk
from tkinter import X, W

try:
    import ttkbootstrap as ttk
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.constants import VERSION, GITHUB_REPO, FEEDBACK_URL


class GeneralTabMixin:
    """Mixin class providing General settings tab functionality."""

    def _create_general_tab(self, parent):
        """Create general settings tab."""
        ttk.Label(parent, text="General Settings", font=('Segoe UI', 12, 'bold')).pack(anchor=W)

        # Auto-start (with auto-save on toggle)
        ttk.Separator(parent).pack(fill=X, pady=15)
        self.autostart_var = tk.BooleanVar(value=self.config.is_autostart_enabled())
        if HAS_TTKBOOTSTRAP:
            ttk.Checkbutton(parent, text="Start CrossTrans with Windows",
                            variable=self.autostart_var,
                            command=self._on_autostart_toggle,
                            bootstyle="round-toggle-success").pack(anchor=W, pady=5)
        else:
            ttk.Checkbutton(parent, text="Start CrossTrans with Windows",
                            variable=self.autostart_var,
                            command=self._on_autostart_toggle).pack(anchor=W, pady=5)

        # Check for updates on startup (auto-save on toggle)
        self.auto_check_var = tk.BooleanVar(value=self.config.get_auto_check_updates())
        if HAS_TTKBOOTSTRAP:
            ttk.Checkbutton(parent, text="Check for updates automatically (startup and every 24 hours)",
                            variable=self.auto_check_var,
                            command=self._on_auto_check_changed,
                            bootstyle="round-toggle-success").pack(anchor=W, pady=5)
        else:
            ttk.Checkbutton(parent, text="Check for updates automatically (startup and every 24 hours)",
                            variable=self.auto_check_var,
                            command=self._on_auto_check_changed).pack(anchor=W, pady=5)

        # Check for updates button
        update_frame = ttk.Frame(parent)
        self.update_check_frame = update_frame
        update_frame.pack(anchor=W, pady=(10, 0), fill=X)

        if HAS_TTKBOOTSTRAP:
            self.check_update_btn = ttk.Button(update_frame, text="Check for updates",
                                               command=self._check_for_updates_click,
                                               bootstyle="info-outline", width=18)
        else:
            self.check_update_btn = ttk.Button(update_frame, text="Check for updates",
                                               command=self._check_for_updates_click, width=18)
        self.check_update_btn.pack(side=tk.LEFT)

        self.update_status_label = ttk.Label(update_frame, text="", font=('Segoe UI', 9))
        self.update_status_label.pack(side=tk.LEFT, padx=(10, 0))

        self.update_offer_frame = ttk.Frame(parent)
        self.update_offer_label = ttk.Label(self.update_offer_frame, font=('Segoe UI', 10, 'bold'))
        self.update_offer_label.pack(side=tk.LEFT, padx=(0, 12))
        self.update_offer_button = ttk.Button(self.update_offer_frame, text='View update')
        self.update_offer_button.pack(side=tk.LEFT)

        # Restore Defaults button
        ttk.Separator(parent).pack(fill=X, pady=15)
        if HAS_TTKBOOTSTRAP:
            ttk.Button(parent, text="Restore Defaults", command=self._restore_defaults,
                       bootstyle="warning-outline", width=15).pack(anchor=W)
        else:
            ttk.Button(parent, text="Restore Defaults", command=self._restore_defaults,
                       width=15).pack(anchor=W)
        ttk.Label(parent, text="Reset hotkeys and settings to default values (keeps API keys)",
                  font=('Segoe UI', 8)).pack(anchor=W, pady=(2, 0))

        # About section
        ttk.Separator(parent).pack(fill=X, pady=20)
        ttk.Label(parent, text="About", font=('Segoe UI', 11, 'bold')).pack(anchor=W)
        ttk.Label(parent, text=f"CrossTrans v{VERSION}").pack(anchor=W, pady=(5, 0))
        ttk.Label(parent, text="Supports multiple AI models with failover").pack(anchor=W)

        if HAS_TTKBOOTSTRAP:
            link_btn = ttk.Button(parent, text="View on GitHub",
                                  command=lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}"),
                                  bootstyle="link")
        else:
            link_btn = ttk.Button(parent, text="View on GitHub",
                                  command=lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}"))
        link_btn.pack(anchor=W, pady=5)

        # Feedback button
        if HAS_TTKBOOTSTRAP:
            feedback_btn = ttk.Button(parent, text="Send Feedback / Report Bug",
                                      command=lambda: webbrowser.open(FEEDBACK_URL),
                                      bootstyle="info-outline")
        else:
            feedback_btn = ttk.Button(parent, text="Send Feedback / Report Bug",
                                      command=lambda: webbrowser.open(FEEDBACK_URL))
        feedback_btn.pack(anchor=W, pady=5)

    def _on_autostart_toggle(self):
        """Handle autostart toggle with debounce for auto-save."""
        # Cancel any pending save
        if hasattr(self, '_autostart_timer'):
            self.window.after_cancel(self._autostart_timer)
        # Schedule save with 500ms debounce
        self._autostart_timer = self.window.after(500, self._save_autostart)

    def _save_autostart(self):
        """Save autostart setting to config."""
        self.config.set_autostart(self.autostart_var.get())
        logging.info(f"Auto-saved autostart: {self.autostart_var.get()}")

    def _on_auto_check_changed(self):
        """Handle auto-check setting change - auto-save immediately."""
        enabled = self.auto_check_var.get()
        self.config.set_auto_check_updates(enabled)
        self.update_manager.auto_check_changed()
        logging.info(f"Auto-check updates on startup: {enabled}")

    def _restore_defaults(self):
        """Restore all settings to defaults (except API keys) and auto-save."""
        # Restore default hotkeys
        # Only for default languages
        for lang, entry_var in self.hotkey_entries.items():
            default_hotkey = self.config.DEFAULT_HOTKEYS.get(lang, "")
            entry_var.set(default_hotkey)

        # Note: We don't delete custom rows here to avoid data loss,
        # but user can delete them manually.

        # Auto-save hotkeys
        self._save_all_hotkeys()

        # Restore general settings and auto-save
        self.autostart_var.set(False)
        self.auto_check_var.set(True)
        self.config.set_autostart(False)
        self.config.set_auto_check_updates(True)
        self.update_manager.auto_check_changed()

        logging.info("Restored defaults and auto-saved")

    def _save(self):
        """Save all settings."""
        # Save API keys list
        api_keys_list = []
        for row in self.api_rows:
            model = row['model_var'].get().strip()
            key = row['key_var'].get().strip()
            provider = row['provider_var'].get()
            # Save "Auto" as empty string (will trigger auto-detection)
            if model == "Auto":
                model = ''
            api_keys_list.append({'model_name': model, 'api_key': key, 'provider': provider})
        self.config.set_api_keys(api_keys_list)

        # Save all hotkeys
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

        # Save general settings
        self.config.set_autostart(self.autostart_var.get())

        if self.on_save_callback:
            self.on_save_callback()
