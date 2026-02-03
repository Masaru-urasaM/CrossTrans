"""
API Key tab functionality for Settings window.
"""
import gc
import logging
import threading
import webbrowser

import tkinter as tk
from tkinter import BOTH, X, LEFT, RIGHT, W, NW

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.dialogs import Messagebox
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.core.remote_config import get_config
from src.core.api_manager import AIAPIManager
from src.core.multimodal import MultimodalProcessor
from src.core.auth import require_auth
from src.ui.settings.widgets import AutocompleteCombobox, get_all_models_list


class APITabMixin:
    """Mixin class providing API Key tab functionality."""

    def _create_api_tab(self, parent):
        """Create API key settings tab."""
        self.api_rows = []
        self.api_canvas = None
        self.api_container = None

        ttk.Label(parent, text="API Configuration", font=('Segoe UI', 12, 'bold')).pack(anchor=W)
        ttk.Label(parent, text="Configure multiple models and keys for failover redundancy.",
                  font=('Segoe UI', 9)).pack(anchor=W, pady=(5, 5))
        ttk.Label(parent, text="⚠ Note: Each 'Test' counts as 1 API request toward your quota.",
                  font=('Segoe UI', 9, 'italic'), foreground='#ff9900').pack(anchor=W, pady=(0, 3))
        ttk.Label(parent, text="💡 Auto mode: System will scan providers/models to find a working pair (saved for future use).",
                  font=('Segoe UI', 9, 'italic'), foreground='#888888').pack(anchor=W, pady=(0, 10))

        # Scrollable container for API keys (no visible scrollbar)
        canvas = tk.Canvas(parent, highlightthickness=0, height=100)
        api_container = ttk.Frame(canvas)

        canvas.pack(fill=BOTH, expand=True)
        self.api_canvas = canvas
        self.api_container = api_container

        window_id = canvas.create_window((0, 0), window=api_container, anchor=NW)

        def _configure_canvas(event):
            canvas.itemconfig(window_id, width=event.width)
        canvas.bind('<Configure>', _configure_canvas)

        # Mousewheel scrolling only
        def _on_mousewheel(event):
            if canvas.winfo_exists() and canvas.winfo_ismapped():
                try:
                    canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                except tk.TclError:
                    pass  # Canvas may have been destroyed
        canvas.bind("<MouseWheel>", _on_mousewheel)
        api_container.bind("<MouseWheel>", _on_mousewheel)

        # Container for API rows (to keep them separate from buttons/footer)
        self.api_list_frame = ttk.Frame(api_container)
        self.api_list_frame.pack(fill=X, expand=True)

        # Load existing keys (Primary row always exists, empty by default)
        saved_keys = self.config.get_api_keys()
        if not saved_keys:
            saved_keys = [{'model_name': '', 'api_key': ''}]

        # Render rows
        for i, config in enumerate(saved_keys):
            is_primary = (i == 0)
            self._add_api_row(self.api_list_frame, config.get('model_name', ''), config.get('api_key', ''), config.get('provider', 'Auto'), is_primary)

        # Buttons frame: Show All + Delete All (left) + Add Backup (right)
        btn_frame = ttk.Frame(api_container)
        btn_frame.pack(fill=X, pady=15)

        # Track show all state
        self.show_all_state = {'showing': False, 'authenticated': False}

        if HAS_TTKBOOTSTRAP:
            self.show_all_btn = ttk.Button(btn_frame, text="Show All API Keys",
                       command=self._toggle_show_all_keys,
                       bootstyle="secondary-outline", width=18)
            self.show_all_btn.pack(side=LEFT)
            ttk.Button(btn_frame, text="Delete All API Keys",
                       command=self._delete_all_keys,
                       bootstyle="danger-outline", width=18).pack(side=LEFT, padx=(10, 0))
            self.add_api_btn = ttk.Button(btn_frame, text="+ Add Backup Key",
                                        command=lambda: self._add_new_api_row(self.api_list_frame, canvas),
                                        bootstyle="success-outline", width=18)
        else:
            self.show_all_btn = ttk.Button(btn_frame, text="Show All API Keys",
                       command=self._toggle_show_all_keys, width=18)
            self.show_all_btn.pack(side=LEFT)
            ttk.Button(btn_frame, text="Delete All API Keys",
                       command=self._delete_all_keys, width=18).pack(side=LEFT, padx=(10, 0))
            self.add_api_btn = ttk.Button(btn_frame, text="+ Add Backup Key",
                                        command=lambda: self._add_new_api_row(self.api_list_frame, canvas), width=18)
        self.add_api_btn.pack(side=LEFT, padx=10)

        ttk.Label(api_container, text="Delete All: Removes all API keys from storage permanently.",
                  font=('Segoe UI', 8), foreground='#888888').pack(anchor=W, pady=(5, 0))
        ttk.Label(api_container, text="⚠ No API keys = Trial Mode (limited quota, may not work as expected)",
                  font=('Segoe UI', 8, 'italic'), foreground='#ff9900').pack(anchor=W, pady=(2, 0))

        # Google AI Studio link for easy API key registration
        ttk.Separator(api_container).pack(fill=X, pady=10)
        ttk.Label(api_container, text="Get your free API key:",
                  font=('Segoe UI', 10, 'bold')).pack(anchor=W)

        if HAS_TTKBOOTSTRAP:
            studio_link = ttk.Button(api_container,
                                     text="Google AI Studio (Free, 1500 req/day)",
                                     command=lambda: webbrowser.open("https://aistudio.google.com/app/apikey"),
                                     bootstyle="link")
        else:
            studio_link = ttk.Button(api_container,
                                     text="Google AI Studio (Free, 1500 req/day)",
                                     command=lambda: webbrowser.open("https://aistudio.google.com/app/apikey"))
        studio_link.pack(anchor=W)

        # ===== CAPABILITY STATUS (Auto-managed) =====
        ttk.Separator(api_container).pack(fill=X, pady=15)
        ttk.Label(api_container, text="API Capabilities (Auto-detected when you Test APIs):",
                  font=('Segoe UI', 10, 'bold')).pack(anchor=W)

        # Vision/Image capability
        vision_frame = ttk.Frame(api_container)
        vision_frame.pack(fill=X, pady=5)

        has_vision = self.config.has_any_vision_capable()
        self.vision_var = tk.BooleanVar(value=has_vision)

        if HAS_TTKBOOTSTRAP:
            self.vision_chk = ttk.Checkbutton(vision_frame, text="📷 Image Processing",
                                  variable=self.vision_var,
                                  bootstyle="success-round-toggle")
        else:
            self.vision_chk = ttk.Checkbutton(vision_frame, text="📷 Image Processing",
                                  variable=self.vision_var)
        self.vision_chk.pack(side=LEFT)
        self.vision_chk.configure(state='disabled')  # Display only
        status_text = "Available" if has_vision else "No capable API found"
        status_color = '#28a745' if has_vision else '#888888'
        self.vision_status_label = ttk.Label(vision_frame, text=f"({status_text})", font=('Segoe UI', 8), foreground=status_color)
        self.vision_status_label.pack(side=LEFT, padx=(5, 0))

        # File processing capability
        file_frame = ttk.Frame(api_container)
        file_frame.pack(fill=X, pady=5)

        has_file = self.config.has_any_file_capable()
        self.file_var = tk.BooleanVar(value=has_file)

        if HAS_TTKBOOTSTRAP:
            self.file_chk = ttk.Checkbutton(file_frame, text="📄 File Processing (.txt, .docx, .srt, .pdf)",
                                  variable=self.file_var,
                                  bootstyle="success-round-toggle")
        else:
            self.file_chk = ttk.Checkbutton(file_frame, text="📄 File Processing (.txt, .docx, .srt, .pdf)",
                                  variable=self.file_var)
        self.file_chk.pack(side=LEFT)
        self.file_chk.configure(state='disabled')  # Display only
        file_status = "Available" if has_file else "No capable API found"
        file_color = '#28a745' if has_file else '#888888'
        self.file_status_label = ttk.Label(file_frame, text=f"({file_status})", font=('Segoe UI', 8), foreground=file_color)
        self.file_status_label.pack(side=LEFT, padx=(5, 0))

        ttk.Label(api_container, text="💡 Tip: Click 'Test' on an API to detect its capabilities.",
                  font=('Segoe UI', 8), foreground='#888888').pack(anchor=W, pady=(5, 0))

        # ===== TRIAL MODE TOGGLE =====
        ttk.Separator(api_container).pack(fill=X, pady=15)
        ttk.Label(api_container, text="Trial Mode:",
                  font=('Segoe UI', 10, 'bold')).pack(anchor=W)
        ttk.Label(api_container, text="Use shared API when your keys don't work (100 requests/day limit)",
                  font=('Segoe UI', 9), foreground='#888888').pack(anchor=W, pady=(2, 10))

        # Toggle frame
        trial_toggle_frame = ttk.Frame(api_container)
        trial_toggle_frame.pack(fill=X, pady=5)

        # Trial mode toggle variable
        self.trial_forced_var = tk.BooleanVar(value=self.config.get_trial_mode_forced())

        if HAS_TTKBOOTSTRAP:
            self.trial_toggle_btn = ttk.Button(
                trial_toggle_frame,
                text="Disable Trial Mode" if self.trial_forced_var.get() else "Enable Trial Mode",
                command=self._toggle_trial_mode,
                bootstyle="success" if self.trial_forced_var.get() else "warning-outline",
                width=18
            )
        else:
            self.trial_toggle_btn = ttk.Button(
                trial_toggle_frame,
                text="Disable Trial Mode" if self.trial_forced_var.get() else "Enable Trial Mode",
                command=self._toggle_trial_mode,
                width=18
            )
        self.trial_toggle_btn.pack(side=LEFT)

        # Status label
        self.trial_status_label = ttk.Label(
            trial_toggle_frame,
            text="",
            font=('Segoe UI', 9)
        )
        self.trial_status_label.pack(side=LEFT, padx=(10, 0))

        # Update initial status
        self._update_trial_status_label()

        # Supported Providers Table
        ttk.Separator(api_container).pack(fill=X, pady=15)
        ttk.Label(api_container, text="Supported Providers:", font=('Segoe UI', 10, 'bold')).pack(anchor=W)

        providers_text = (
            "Google • OpenAI • Anthropic • DeepSeek • Groq • xAI\n"
            "Mistral • Perplexity • Cerebras • SambaNova • Together • SiliconFlow • OpenRouter"
        )

        ttk.Label(api_container, text=providers_text, font=('Segoe UI', 9),
                 foreground='#aaaaaa', justify=LEFT).pack(anchor=W, pady=(5, 10))

        # Update scroll region
        def update_scroll():
            api_container.update_idletasks()
            canvas.config(scrollregion=canvas.bbox("all"))
        self.window.after(100, update_scroll)

    def _add_api_row(self, parent, model, key, provider="Auto", is_primary=False):
        """Add a single API configuration row.

        Row format: Label + Model + API Key + Show + Test + Delete
        """
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=5)

        # Row label (Primary or Backup #N)
        row_num = len(self.api_rows) + 1
        if is_primary:
            label_text = "Primary:"
        else:
            label_text = f"Backup {row_num - 1}:"
        ttk.Label(row, text=label_text, font=('Segoe UI', 9, 'bold'), width=10).pack(side=LEFT)

        # Provider Combobox
        provider_var = tk.StringVar(value=provider)
        ttk.Label(row, text="Provider:", font=('Segoe UI', 9)).pack(side=LEFT)
        provider_cb = ttk.Combobox(row, textvariable=provider_var, values=get_config().providers_list, width=10, state="readonly")
        provider_cb.pack(side=LEFT, padx=(3, 8))

        # Model Combobox (autocomplete - can select or type to filter)
        model_var = tk.StringVar(value=model if model else "Auto")
        ttk.Label(row, text="Model:", font=('Segoe UI', 9)).pack(side=LEFT)
        model_values = get_all_models_list(provider)
        model_cb = AutocompleteCombobox(row, textvariable=model_var, width=28)
        model_cb.set_values(model_values)
        model_cb.pack(side=LEFT, padx=(3, 8))

        # Update model list when provider changes
        def on_provider_change(event=None):
            current_provider = provider_var.get()
            new_values = get_all_models_list(current_provider)
            model_cb.set_values(new_values)
            # If current model is not in new list and not custom, reset to Auto
            current_model = model_var.get()
            if current_model not in new_values and current_model != "Auto":
                # Keep custom models, only reset if it was from a different provider's list
                pass  # Allow custom input

        provider_cb.bind('<<ComboboxSelected>>', on_provider_change)

        # API Key with placeholder
        key_var = tk.StringVar(value=key)
        ttk.Label(row, text="API Key:", font=('Segoe UI', 9)).pack(side=LEFT)

        key_entry = ttk.Entry(row, textvariable=key_var, width=28, show="*")
        key_entry.pack(side=LEFT, padx=(3, 5))

        # Store show state for this row
        show_state = {'showing': False, 'authenticated': False}

        # Show button (per-row)
        def toggle_show_key():
            if show_state['showing']:
                # Hide the key
                key_entry.config(show="*")
                show_btn.config(text="Show")
                if HAS_TTKBOOTSTRAP: show_btn.configure(bootstyle="secondary-outline")
                show_state['showing'] = False
            else:
                # Show the key - require authentication first
                # Skip auth if already authenticated via Show All or this row
                if not show_state['authenticated'] and not self.show_all_state.get('authenticated', False):
                    # Check if there's actually a key to show
                    if not key_var.get().strip():
                        return

                    # Require Windows authentication
                    if not require_auth(self.window):
                        return  # Auth failed or cancelled

                    # Mark as authenticated for this session (both row and global)
                    show_state['authenticated'] = True
                    self.show_all_state['authenticated'] = True

                key_entry.config(show="")
                show_btn.config(text="Hide")
                if HAS_TTKBOOTSTRAP: show_btn.configure(bootstyle="warning")
                show_state['showing'] = True

            # Sync "Show All" button state based on all rows
            self._sync_show_all_button_state()

        if HAS_TTKBOOTSTRAP:
            show_btn = ttk.Button(row, text="Show", command=toggle_show_key,
                                  bootstyle="secondary-outline", width=5)
        else:
            show_btn = ttk.Button(row, text="Show", command=toggle_show_key, width=5)
        show_btn.pack(side=LEFT, padx=2)

        # Test Button - width must accommodate "OK! Image OK | Files OK" (~24 chars)
        test_label = ttk.Label(row, text="", width=25, anchor='w')

        # Create row_data dict early so Test button can reference it
        row_data = {
            'frame': row,
            'model_var': model_var,
            'provider_var': provider_var,
            'model_cb': model_cb,
            'key_var': key_var,
            'key_entry': key_entry,
            'is_primary': is_primary,
            'test_label': test_label,
            'show_btn': show_btn,
            'show_state': show_state
        }

        if HAS_TTKBOOTSTRAP:
            ttk.Button(row, text="Test",
                       command=lambda rd=row_data: self._test_single_api(
                           rd['model_var'].get(), rd['key_var'].get(), rd['provider_var'].get(),
                           rd['test_label'], silent=False, row_data=rd),
                       bootstyle="info-outline", width=5).pack(side=LEFT, padx=2)
        else:
            ttk.Button(row, text="Test",
                       command=lambda rd=row_data: self._test_single_api(
                           rd['model_var'].get(), rd['key_var'].get(), rd['provider_var'].get(),
                           rd['test_label'], silent=False, row_data=rd),
                       width=5).pack(side=LEFT, padx=2)

        # Delete Button (only for backups)
        if not is_primary:
            if HAS_TTKBOOTSTRAP:
                ttk.Button(row, text="Delete",
                           command=lambda r=row, kv=key_var: self._delete_api_row(r, kv),
                           bootstyle="danger-outline", width=6).pack(side=LEFT, padx=2)
            else:
                ttk.Button(row, text="Delete",
                           command=lambda r=row, kv=key_var: self._delete_api_row(r, kv),
                           width=6).pack(side=LEFT, padx=2)

        test_label.pack(side=LEFT, padx=3)

        # Display cached status from startup check (if available)
        if key:
            cached_status = self.config.api_status_cache.get(key, None)
            if cached_status is True:
                if HAS_TTKBOOTSTRAP:
                    test_label.config(text="OK (cached)", bootstyle="success")
                else:
                    test_label.config(text="OK (cached)", foreground="green")
            elif cached_status is False:
                if HAS_TTKBOOTSTRAP:
                    test_label.config(text="Error (cached)", bootstyle="danger")
                else:
                    test_label.config(text="Error (cached)", foreground="red")

        self.api_rows.append(row_data)
        # Only update button if it exists (button is created after initial rows)
        if hasattr(self, 'add_api_btn'):
            self._update_api_add_button()

    def _add_new_api_row(self, container, canvas):
        """Add a new backup API row."""
        if len(self.api_rows) < 6:  # 1 Primary + 5 Backups
            self._add_api_row(container, "", "")  # Empty model and key for new rows
            container.update_idletasks()
            canvas.config(scrollregion=canvas.bbox("all"))

    def _delete_api_row(self, row_frame, key_var):
        """Delete an API row from UI and auto-save to config."""
        row_frame.destroy()
        self.api_rows = [r for r in self.api_rows if r['key_var'] != key_var]
        self._update_api_add_button()

        # AUTO-SAVE: Remove from config immediately
        self._save_api_keys_to_config(notify_change=True)
        logging.info("Auto-saved after deleting API row")

    def _delete_all_keys(self):
        """Clear all API keys but keep models, and save immediately."""
        msg = "Are you sure you want to clear all API keys?\nThis will keep your model names but remove the keys.\nChanges will be saved immediately."
        if HAS_TTKBOOTSTRAP:
            result = Messagebox.yesno(msg, title="Confirm Clear", parent=self.window)
            if result != "Yes": return
        else:
            from tkinter import messagebox
            if not messagebox.askyesno("Confirm Clear", msg, parent=self.window): return

        # Clear keys in all rows
        for row in self.api_rows:
            row['key_var'].set("")

        # Save immediately as requested
        self._save_api_keys_to_config(secure=True)

        # Force garbage collection to clear strings from RAM immediately
        gc.collect()

        if HAS_TTKBOOTSTRAP:
            Messagebox.show_info("All API keys have been cleared and saved.", title="Keys Cleared", parent=self.window)
        else:
            from tkinter import messagebox
            messagebox.showinfo("Keys Cleared", "All API keys have been cleared and saved.", parent=self.window)

    def _toggle_show_all_keys(self):
        """Toggle showing/hiding all API keys with authentication."""
        if self.show_all_state['showing']:
            # Hide all keys
            for row in self.api_rows:
                row['key_entry'].config(show="*")
                # Update individual show button state and text
                if 'show_state' in row:
                    row['show_state']['showing'] = False
                if 'show_btn' in row:
                    row['show_btn'].config(text="Show")
                    if HAS_TTKBOOTSTRAP:
                        row['show_btn'].configure(bootstyle="secondary-outline")

            self.show_all_btn.config(text="Show All API Keys")
            if HAS_TTKBOOTSTRAP:
                self.show_all_btn.configure(bootstyle="secondary-outline")
            self.show_all_state['showing'] = False
        else:
            # Check if there are any keys to show
            has_keys = any(row['key_var'].get().strip() for row in self.api_rows)
            if not has_keys:
                if HAS_TTKBOOTSTRAP:
                    Messagebox.show_info("No API keys to show.", title="No Keys", parent=self.window)
                else:
                    from tkinter import messagebox
                    messagebox.showinfo("No Keys", "No API keys to show.", parent=self.window)
                return

            # Require authentication if not already authenticated
            if not self.show_all_state['authenticated']:
                if not require_auth(self.window):
                    return  # Auth failed or cancelled

                # Mark as authenticated for this session
                self.show_all_state['authenticated'] = True

            # Show all keys and update individual buttons
            for row in self.api_rows:
                row['key_entry'].config(show="")
                # Update individual show button state and text
                if 'show_state' in row:
                    row['show_state']['showing'] = True
                    row['show_state']['authenticated'] = True  # Mark row as authenticated too
                if 'show_btn' in row:
                    row['show_btn'].config(text="Hide")
                    if HAS_TTKBOOTSTRAP:
                        row['show_btn'].configure(bootstyle="warning")

            self.show_all_btn.config(text="Hide All API Keys")
            if HAS_TTKBOOTSTRAP:
                self.show_all_btn.configure(bootstyle="warning")
            self.show_all_state['showing'] = True

    def _sync_show_all_button_state(self):
        """Sync 'Show All' button state based on individual row states."""
        if not self.api_rows:
            return

        # Check if all rows with keys are showing
        rows_with_keys = [row for row in self.api_rows if row['key_var'].get().strip()]
        if not rows_with_keys:
            return

        all_showing = all(row.get('show_state', {}).get('showing', False) for row in rows_with_keys)
        all_hidden = all(not row.get('show_state', {}).get('showing', False) for row in rows_with_keys)

        if all_showing and not self.show_all_state['showing']:
            # All individual buttons are "Hide" -> update "Show All" to "Hide All"
            self.show_all_btn.config(text="Hide All API Keys")
            if HAS_TTKBOOTSTRAP:
                self.show_all_btn.configure(bootstyle="warning")
            self.show_all_state['showing'] = True
        elif all_hidden and self.show_all_state['showing']:
            # All individual buttons are "Show" -> update "Hide All" to "Show All"
            self.show_all_btn.config(text="Show All API Keys")
            if HAS_TTKBOOTSTRAP:
                self.show_all_btn.configure(bootstyle="secondary-outline")
            self.show_all_state['showing'] = False

    def _save_api_keys_to_config(self, secure=False, notify_change=True):
        """Save current API keys to config.

        Args:
            secure: Whether to use secure storage
            notify_change: Whether to trigger API change callback (for trial mode switching)

        Preserves capability flags (vision_capable, file_capable) from existing config.
        These flags are only updated when API is tested successfully.
        """
        try:
            # Get existing API configs to preserve capability flags
            existing_keys = {
                (cfg.get('api_key', ''), cfg.get('model_name', '')): cfg
                for cfg in self.config.get_api_keys()
            }

            api_keys_list = []
            for row in self.api_rows:
                model = row['model_var'].get().strip()
                key = row['key_var'].get().strip()
                provider = row['provider_var'].get()
                # Save "Auto" as empty string (will trigger auto-detection)
                if model == "Auto":
                    model = ''
                if model or key:  # Only save if there's actual data
                    new_config = {'model_name': model, 'api_key': key, 'provider': provider}

                    # Preserve capability flags from existing config if available
                    existing = existing_keys.get((key, model))
                    if existing:
                        if 'vision_capable' in existing:
                            new_config['vision_capable'] = existing['vision_capable']
                        if 'file_capable' in existing:
                            new_config['file_capable'] = existing['file_capable']

                    api_keys_list.append(new_config)
            self.config.set_api_keys(api_keys_list, secure=secure)

            # Update the vision/file toggles based on new capabilities
            self.config._auto_update_toggles()

            # Trigger API change callback to update trial mode status
            if notify_change and self.on_api_change_callback:
                self.on_api_change_callback()
        except Exception as e:
            print(f"Error saving API keys to config: {e}")
            import traceback
            traceback.print_exc()

    def _update_api_add_button(self):
        """Enable/disable add button based on limit."""
        if len(self.api_rows) >= 6:
            self.add_api_btn.configure(state='disabled')
        else:
            self.add_api_btn.configure(state='normal')

    def _test_all_apis_async(self):
        """Test all API configurations asynchronously."""
        def run_tests():
            # Iterate through a copy of rows to avoid modification issues
            rows = list(self.api_rows)
            for row in rows:
                try:
                    # Call test function on main thread to update UI safely
                    self.window.after(0, lambda r=row: self._test_single_api(
                        r['model_var'].get(),
                        r['key_var'].get(),
                        r['provider_var'].get(),
                        r['test_label'],
                        silent=True,
                        row_data=r
                    ))
                except Exception:
                    pass

        threading.Thread(target=run_tests, daemon=True).start()

    def _detect_provider_from_key(self, api_key: str) -> str:
        """Detect provider from API key pattern.

        Args:
            api_key: The API key to analyze

        Returns:
            Provider name (Title Case) or empty string if not detected
        """
        key = api_key.strip()
        for pattern, provider in get_config().api_key_patterns.items():
            if key.startswith(pattern):
                return provider  # Already Title Case
        return ""

    def _test_single_api(self, model_name, api_key, provider, result_label, silent=False, row_data=None):
        """Test API connection with comprehensive iteration.

        Iteration Logic:
        1. Provider=Auto + Model=Auto: Try first model of EACH provider
        2. Provider=Specific + Model=Auto: Try ALL models of that provider
        3. Provider=Auto + Model=Specific: Try that model with ALL providers
        4. Both Specific: Test exact combination only

        Only shows error if ALL combinations fail.
        """
        model_name = model_name.strip()
        api_key = api_key.strip()

        if HAS_TTKBOOTSTRAP:
            result_label.config(text="Testing...", bootstyle="warning")
        else:
            result_label.config(text="Testing...", foreground="orange")
        self.window.update()

        if not api_key:
            if HAS_TTKBOOTSTRAP:
                result_label.config(text="No API key", bootstyle="danger")
            else:
                result_label.config(text="No API key", foreground="red")
            return

        api_manager = AIAPIManager()

        # Determine which combinations to try
        combinations_to_try = []

        if provider == 'Auto' and (not model_name or model_name == 'Auto'):
            # Case 1: Both Auto - first detect provider from API key pattern
            detected_provider = self._detect_provider_from_key(api_key)

            model_map = get_config().model_provider_map
            if detected_provider and detected_provider in model_map:
                # Provider detected! Try ALL models of that provider
                for model in model_map[detected_provider]:
                    combinations_to_try.append((detected_provider, model))
            else:
                # No pattern match - try ALL providers with ALL models
                for prov_name, models in model_map.items():
                    for model in models:
                        combinations_to_try.append((prov_name, model))

        elif provider != 'Auto' and (not model_name or model_name == 'Auto'):
            # Case 2: Provider specific, Model Auto - try ALL models of that provider
            provider_models = get_config().model_provider_map.get(provider, [])
            for model in provider_models:
                combinations_to_try.append((provider, model))

        elif provider == 'Auto' and model_name and model_name != 'Auto':
            # Case 3: Provider Auto, Model specific - detect provider from key first
            detected_provider = self._detect_provider_from_key(api_key)

            if detected_provider:
                # Provider detected - only try with that provider
                combinations_to_try.append((detected_provider, model_name))
            else:
                # No pattern match - try that model with all providers
                for prov_name in get_config().model_provider_map.keys():
                    combinations_to_try.append((prov_name, model_name))

        else:
            # Case 4: Both specific - try exact combination only
            combinations_to_try = [(provider, model_name)]

        # Fallback if empty
        if not combinations_to_try:
            combinations_to_try = [('Google', 'gemini-2.0-flash')]

        # Try each combination
        total = len(combinations_to_try)
        last_error = ""

        for i, (try_provider, try_model) in enumerate(combinations_to_try, 1):
            try:
                # Update label to show progress
                if HAS_TTKBOOTSTRAP:
                    result_label.config(text=f"Testing {i}/{total}...", bootstyle="warning")
                else:
                    result_label.config(text=f"Testing {i}/{total}...", foreground="orange")
                self.window.update()

                # Test this combination (provider is already Title Case)
                api_manager.test_connection(try_model, api_key, try_provider)

                # SUCCESS! This combination works
                display_name = api_manager.get_display_name(try_provider)

                # Check Vision Capability
                is_vision = MultimodalProcessor.is_vision_capable(try_model, try_provider)
                is_file_capable = True

                # Build capability status
                capability_parts = []
                if is_vision:
                    capability_parts.append("Image OK")
                if is_file_capable:
                    capability_parts.append("Files OK")
                capability_str = " | ".join(capability_parts) if capability_parts else ""
                label_text = f"OK! {capability_str}" if capability_str else "OK!"

                # Store capabilities in config
                self.config.update_api_capabilities(api_key, try_model, is_vision, is_file_capable)

                # Refresh toggle states
                self._refresh_vision_toggle_state()
                self._refresh_file_toggle_state()

                # Update UI dropdowns with working combination if row_data provided
                if row_data:
                    row_data['provider_var'].set(try_provider)
                    row_data['model_var'].set(try_model)

                # Build detailed message
                capability_msg = ""
                if is_vision:
                    capability_msg += "\n✓ Image Processing: Supported"
                if is_file_capable:
                    capability_msg += "\n✓ File Processing: Supported"

                if HAS_TTKBOOTSTRAP:
                    result_label.config(text=label_text, bootstyle="success")
                    if not silent:
                        Messagebox.show_info(
                            f"Connection Verified!\n\nProvider: {display_name}\nModel: {try_model}\nStatus: OK{capability_msg}",
                            title="Test Result", parent=self.window)
                else:
                    result_label.config(text=label_text, foreground="green")
                    if not silent:
                        from tkinter import messagebox
                        messagebox.showinfo(
                            "Test Result",
                            f"Connection Verified!\n\nProvider: {display_name}\nModel: {try_model}\nStatus: OK{capability_msg}",
                            parent=self.window)
                # AUTO-SAVE: Save this API row immediately after successful test
                self._save_single_api_row(try_provider, try_model, api_key, row_data)

                # Notify main app to refresh attachments (if callback provided)
                if self.on_api_change_callback:
                    self.on_api_change_callback()

                return  # Success, exit early

            except Exception as e:
                last_error = str(e)
                logging.debug(f"Test failed for {try_provider}/{try_model}: {last_error}")
                continue  # Try next combination

        # All combinations failed
        error_msg = (
            f"All {total} provider/model combinations failed.\n\n"
            f"Last Error: {last_error}\n\n"
            f"Please check:\n"
            f"• API key is correct and active\n"
            f"• Provider/Model selection matches your API key"
        )

        if HAS_TTKBOOTSTRAP:
            result_label.config(text="All Failed", bootstyle="danger")
            if not silent:
                Messagebox.show_error(error_msg, title="Test Failed", parent=self.window)
        else:
            result_label.config(text="All Failed", foreground="red")
            if not silent:
                from tkinter import messagebox
                messagebox.showerror("Test Failed", error_msg, parent=self.window)

        # AUTO-SAVE: Save API row even if test failed (user requested)
        self._save_single_api_row(provider, model_name, api_key, row_data)
        logging.info(f"Auto-saved API key (test failed) for {provider}/{model_name}")

    def _refresh_vision_toggle_state(self):
        """Refresh vision toggle state based on API capabilities (auto-managed)."""
        try:
            has_vision = self.config.has_any_vision_capable()
            if hasattr(self, 'vision_var'):
                self.vision_var.set(has_vision)
            if hasattr(self, 'vision_chk'):
                # Toggle is display-only, always disabled
                self.vision_chk.configure(state='disabled')
            # Update status label text and color
            if hasattr(self, 'vision_status_label'):
                status_text = "Available" if has_vision else "No capable API found"
                status_color = '#28a745' if has_vision else '#888888'
                self.vision_status_label.configure(text=f"({status_text})", foreground=status_color)
        except Exception as e:
            logging.warning(f"Failed to refresh vision toggle: {e}")

    def _refresh_file_toggle_state(self):
        """Refresh file toggle state based on API capabilities (auto-managed)."""
        try:
            has_file = self.config.has_any_file_capable()
            if hasattr(self, 'file_var'):
                self.file_var.set(has_file)
            if hasattr(self, 'file_chk'):
                # Toggle is display-only, always disabled
                self.file_chk.configure(state='disabled')
            # Update status label text and color
            if hasattr(self, 'file_status_label'):
                status_text = "Available" if has_file else "No capable API found"
                status_color = '#28a745' if has_file else '#888888'
                self.file_status_label.configure(text=f"({status_text})", foreground=status_color)
        except Exception as e:
            logging.warning(f"Failed to refresh file toggle: {e}")

    def _save_single_api_row(self, provider: str, model: str, api_key: str, row_data=None):
        """Save a single API row to config (auto-save after successful test).

        This rebuilds the entire API keys list from UI rows to ensure correct order.

        Args:
            provider: Provider name
            model: Model name
            api_key: API key value
            row_data: Row data dict that was updated (used to update the UI vars)
        """
        # Update the row_data with test results if provided
        if row_data:
            row_data['provider_var'].set(provider)
            if model != 'Auto':
                row_data['model_var'].set(model)

        # Rebuild entire list from UI rows (preserves exact order)
        # This is the same approach as _save_api_keys_to_config
        existing_keys = {
            (cfg.get('api_key', ''), cfg.get('model_name', '')): cfg
            for cfg in self.config.get_api_keys()
        }

        api_keys_list = []
        for row in self.api_rows:
            row_model = row['model_var'].get().strip()
            row_key = row['key_var'].get().strip()
            row_provider = row['provider_var'].get()

            # Save "Auto" as empty string
            if row_model == "Auto":
                row_model = ''

            if row_model or row_key:  # Only save if there's actual data
                new_config = {'model_name': row_model, 'api_key': row_key, 'provider': row_provider}

                # Preserve capability flags from existing config
                existing = existing_keys.get((row_key, row_model))
                if existing:
                    if 'vision_capable' in existing:
                        new_config['vision_capable'] = existing['vision_capable']
                    if 'file_capable' in existing:
                        new_config['file_capable'] = existing['file_capable']

                api_keys_list.append(new_config)

        self.config.set_api_keys(api_keys_list)
        logging.info(f"Auto-saved API key for {provider}/{model} (total {len(api_keys_list)} keys)")

    # ===== TRIAL MODE METHODS =====

    def _toggle_trial_mode(self):
        """Toggle trial mode - tests all API keys first when enabling."""
        current = self.trial_forced_var.get()

        if not current:
            # Enabling trial mode - test all keys first
            self._enable_trial_mode_with_check()
        else:
            # Disabling trial mode immediately
            self.trial_forced_var.set(False)
            self.config.set_trial_mode_forced(False)
            self._update_trial_toggle_button()
            self._update_trial_status_label("Trial Mode disabled")
            logging.info("Trial mode manually disabled")

    def _enable_trial_mode_with_check(self):
        """Test all API keys before enabling trial mode."""
        # Disable button during testing
        self.trial_toggle_btn.configure(state='disabled')
        self._update_trial_status_label("Testing API keys...")
        self.window.update_idletasks()

        # Run test in background thread
        thread = threading.Thread(target=self._test_all_keys_for_trial, daemon=True)
        thread.start()

    def _test_all_keys_for_trial(self):
        """Test all API keys and enable trial if none work."""
        api_keys = self.config.get_api_keys()
        any_working = False

        if api_keys:
            manager = AIAPIManager()
            total = len(api_keys)

            for i, key_config in enumerate(api_keys):
                key = key_config.get('api_key', '').strip()
                model = key_config.get('model_name', '').strip() or 'Auto'
                provider = key_config.get('provider', 'Auto')

                if not key:
                    continue

                # Update status on main thread
                self.window.after(0, lambda idx=i, tot=total:
                    self._update_trial_status_label(f"Testing key {idx+1}/{tot}..."))

                try:
                    success, _, _, _ = manager.test_connection(model, key, provider)
                    if success:
                        any_working = True
                        self.config.api_status_cache[key] = True
                        break
                except Exception as e:
                    self.config.api_status_cache[key] = False
                    logging.debug(f"API key test failed: {e}")

        # Update on main thread
        self.window.after(0, lambda: self._finish_trial_toggle(any_working))

    def _finish_trial_toggle(self, any_key_working: bool):
        """Finish trial mode toggle after key testing."""
        from datetime import datetime

        # Re-enable button
        self.trial_toggle_btn.configure(state='normal')

        if any_key_working:
            # Found working key - don't enable trial
            self.trial_forced_var.set(False)
            self.config.set_trial_mode_forced(False)
            self._update_trial_status_label("Found working API key!")
            self._update_trial_toggle_button()

            from tkinter import messagebox
            messagebox.showinfo(
                "API Key Working",
                "A working API key was found!\nTrial Mode not needed.",
                parent=self.window
            )
        else:
            # No working key - enable trial mode
            self.trial_forced_var.set(True)
            self.config.set_trial_mode_forced(True)
            self.config.set_trial_last_api_check(datetime.now().isoformat())
            self._update_trial_status_label("Trial Mode enabled (100 req/day)")
            self._update_trial_toggle_button()
            logging.info("Trial mode enabled - no working API keys found")

    def _update_trial_toggle_button(self):
        """Update trial toggle button text and style."""
        is_enabled = self.trial_forced_var.get()

        if HAS_TTKBOOTSTRAP:
            if is_enabled:
                self.trial_toggle_btn.configure(
                    text="Disable Trial Mode",
                    bootstyle="success"
                )
            else:
                self.trial_toggle_btn.configure(
                    text="Enable Trial Mode",
                    bootstyle="warning-outline"
                )
        else:
            self.trial_toggle_btn.configure(
                text="Disable Trial Mode" if is_enabled else "Enable Trial Mode"
            )

    def _update_trial_status_label(self, text: str = ""):
        """Update trial status label with text and appropriate color."""
        if not text:
            if self.trial_forced_var.get():
                text = "Active - 100 requests/day"
                color = '#28a745'  # Green
            else:
                text = "Disabled"
                color = '#888888'  # Gray
        else:
            color = '#4da6ff'  # Blue for status messages

        self.trial_status_label.configure(text=text, foreground=color)
