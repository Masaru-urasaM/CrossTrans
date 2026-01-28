"""
Settings Window for CrossTrans.
"""
import os
import sys
import gc
import logging
import threading
import webbrowser

import keyboard

import tkinter as tk
from tkinter import BOTH, X, LEFT, RIGHT, W, NW, END

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.dialogs import Messagebox
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.constants import VERSION, GITHUB_REPO, LANGUAGES, PROVIDERS_LIST, FEEDBACK_URL, MODEL_PROVIDER_MAP, API_KEY_PATTERNS
from src.core.api_manager import AIAPIManager
from src.utils.updates import check_for_updates, download_and_install_update, execute_update
from src.core.multimodal import MultimodalProcessor
from src.core.auth import require_auth


def set_dark_title_bar(window):
    """Set dark title bar for Windows 10/11 windows."""
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()

        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_CAPTION_COLOR = 35
        dwmapi = ctypes.windll.dwmapi

        value = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                                     ctypes.byref(value), ctypes.sizeof(value))
        caption_color = ctypes.c_int(0x002b2b2b)
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR,
                                     ctypes.byref(caption_color), ctypes.sizeof(caption_color))
    except Exception:
        pass


def get_all_models_list(provider: str = "Auto") -> list:
    """Get list of models for dropdown, filtered by provider and sorted alphabetically.

    Args:
        provider: Provider name or "Auto" for all models

    Returns:
        List of model names starting with "Auto", then sorted A-Z
    """
    models = []

    if provider == "Auto":
        # Add all models from all providers
        for prov, model_list in MODEL_PROVIDER_MAP.items():
            models.extend(model_list)
    else:
        # Add models for specific provider only (keys are Title Case)
        if provider in MODEL_PROVIDER_MAP:
            models.extend(MODEL_PROVIDER_MAP[provider])

    # Sort alphabetically (case-insensitive)
    models.sort(key=lambda x: x.lower())

    # "Auto" always first
    return ["Auto"] + models


class AutocompleteCombobox(ttk.Combobox):
    """Combobox with autocomplete filtering.

    As the user types, the dropdown list is filtered to show only
    matching options. Supports both selection and custom input.
    """

    def __init__(self, master, **kwargs):
        self._all_values = list(kwargs.pop('values', []))
        super().__init__(master, **kwargs)
        self['values'] = self._all_values

        # Bind key release for filtering
        self.bind('<KeyRelease>', self._on_key_release)
        self.bind('<FocusIn>', self._on_focus_in)

    def set_values(self, values):
        """Update the full list of values.

        Args:
            values: List of all possible values
        """
        self._all_values = list(values)
        self['values'] = self._all_values

    def _on_key_release(self, event):
        """Filter dropdown based on typed text."""
        # Ignore navigation and special keys
        if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Return', 'Tab',
                            'Escape', 'Shift_L', 'Shift_R', 'Control_L',
                            'Control_R', 'Alt_L', 'Alt_R', 'BackSpace'):
            if event.keysym == 'BackSpace':
                # Still filter on backspace
                pass
            else:
                return

        typed = self.get().strip().lower()
        if not typed or typed == 'auto':
            # Show all values when empty or "Auto"
            self['values'] = self._all_values
        else:
            # Filter values that contain the typed text
            filtered = [v for v in self._all_values if typed in v.lower()]
            self['values'] = filtered if filtered else self._all_values

    def _on_focus_in(self, event):
        """Show full list on focus."""
        self['values'] = self._all_values


class SettingsWindow:
    """Settings dialog for configuring the application."""

    def __init__(self, parent, config, on_save_callback=None, on_api_change_callback=None):
        self.config = config
        self.on_save_callback = on_save_callback
        self.on_api_change_callback = on_api_change_callback  # Called when API keys change (for trial mode)
        self.hotkey_entries = {}
        self.custom_rows = []
        self.api_rows = []
        self.recording_language = None

        # Use tk.Toplevel for better compatibility
        self.window = tk.Toplevel(parent)
        self.window.title("Settings - CrossTrans")
        self.window.geometry("1400x650")
        self.window.resizable(True, True)
        self.window.configure(bg='#2b2b2b')

        # Center on screen
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - 1400) // 2
        y = (self.window.winfo_screenheight() - 650) // 2
        self.window.geometry(f"+{x}+{y}")

        # Apply dark title bar (Windows 10/11)
        set_dark_title_bar(self.window)

        # Make window modal and handle close properly
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)
        self.window.focus_force()

        try:
            self._create_widgets()
        except Exception as e:
            print(f"Error creating settings widgets: {e}")
            import traceback
            traceback.print_exc()

    def _create_widgets(self):
        """Create settings UI."""
        if HAS_TTKBOOTSTRAP:
            notebook = ttk.Notebook(self.window, bootstyle="dark")
        else:
            notebook = ttk.Notebook(self.window)
        notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # Tab 1: General (moved to first position)
        general_frame = ttk.Frame(notebook, padding=20) if HAS_TTKBOOTSTRAP else ttk.Frame(notebook)
        notebook.add(general_frame, text="  General  ")
        self._create_general_tab(general_frame)

        # Tab 2: Hotkeys
        hotkey_frame = ttk.Frame(notebook, padding=20) if HAS_TTKBOOTSTRAP else ttk.Frame(notebook)
        notebook.add(hotkey_frame, text="  Hotkeys  ")
        self._create_hotkey_tab(hotkey_frame)

        # Tab 3: API Key
        api_frame = ttk.Frame(notebook, padding=20) if HAS_TTKBOOTSTRAP else ttk.Frame(notebook)
        notebook.add(api_frame, text="  API Key  ")
        self._create_api_tab(api_frame)

        # Tab 4: Dictionary (NLP Language Packs)
        dict_frame = ttk.Frame(notebook, padding=20) if HAS_TTKBOOTSTRAP else ttk.Frame(notebook)
        notebook.add(dict_frame, text="  Dictionary  ")
        self._create_dictionary_tab(dict_frame)

        # Store notebook reference for opening specific tabs
        self.notebook = notebook

        # Tab 5: Guide
        guide_frame = ttk.Frame(notebook, padding=20) if HAS_TTKBOOTSTRAP else ttk.Frame(notebook)
        notebook.add(guide_frame, text="  Guide  ")
        self._create_guide_tab(guide_frame)

        # Buttons
        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(fill=X, padx=10, pady=(0, 10))

        if HAS_TTKBOOTSTRAP:
            ttk.Button(btn_frame, text="Save", command=self._save,
                       bootstyle="success", width=15).pack(side=RIGHT, padx=5)
            ttk.Button(btn_frame, text="Cancel", command=self.window.destroy,
                       bootstyle="secondary", width=15).pack(side=RIGHT)
        else:
            ttk.Button(btn_frame, text="Save", command=self._save,
                       width=15).pack(side=RIGHT, padx=5)
            ttk.Button(btn_frame, text="Cancel", command=self.window.destroy,
                       width=15).pack(side=RIGHT)

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
        canvas = tk.Canvas(parent, highlightthickness=0, height=380)
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
        ttk.Label(vision_frame, text=f"({status_text})", font=('Segoe UI', 8), foreground=status_color).pack(side=LEFT, padx=(5, 0))

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
        ttk.Label(file_frame, text=f"({file_status})", font=('Segoe UI', 8), foreground=file_color).pack(side=LEFT, padx=(5, 0))

        ttk.Label(api_container, text="💡 Tip: Click 'Test' on an API to detect its capabilities.",
                  font=('Segoe UI', 8), foreground='#888888').pack(anchor=W, pady=(5, 0))

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

        # Note: Auto-test is now done once at app startup (see app.py _startup_api_check)
        # to avoid consuming API quota every time Settings is opened.

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
        provider_cb = ttk.Combobox(row, textvariable=provider_var, values=PROVIDERS_LIST, width=10, state="readonly")
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

        key_entry = ttk.Entry(row, textvariable=key_var, width=70, show="*")
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
        if len(self.api_rows) < 6: # 1 Primary + 5 Backups
            self._add_api_row(container, "", "")  # Empty model and key for new rows
            container.update_idletasks()
            canvas.config(scrollregion=canvas.bbox("all"))

    def _delete_api_row(self, row_frame, key_var):
        """Delete an API row from UI."""
        row_frame.destroy()
        self.api_rows = [r for r in self.api_rows if r['key_var'] != key_var]
        self._update_api_add_button()

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
        for pattern, provider in API_KEY_PATTERNS.items():
            if key.startswith(pattern):
                return provider  # Already Title Case from constants.py
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

            if detected_provider and detected_provider in MODEL_PROVIDER_MAP:
                # Provider detected! Try ALL models of that provider
                for model in MODEL_PROVIDER_MAP[detected_provider]:
                    combinations_to_try.append((detected_provider, model))
            else:
                # No pattern match - try ALL providers with ALL models
                for prov_name, models in MODEL_PROVIDER_MAP.items():
                    for model in models:
                        combinations_to_try.append((prov_name, model))

        elif provider != 'Auto' and (not model_name or model_name == 'Auto'):
            # Case 2: Provider specific, Model Auto - try ALL models of that provider
            provider_models = MODEL_PROVIDER_MAP.get(provider, [])
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
                for prov_name in MODEL_PROVIDER_MAP.keys():
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

    def _refresh_vision_toggle_state(self):
        """Refresh vision toggle state based on API capabilities (auto-managed)."""
        try:
            has_vision = self.config.has_any_vision_capable()
            if hasattr(self, 'vision_var'):
                self.vision_var.set(has_vision)
            if hasattr(self, 'vision_chk'):
                # Toggle is display-only, always disabled
                self.vision_chk.configure(state='disabled')
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
        except Exception as e:
            logging.warning(f"Failed to refresh file toggle: {e}")

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
                        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
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

        # Update scroll
        hotkey_container.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

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

                if entry:
                    entry.config(state='readonly')

    def _create_general_tab(self, parent):
        """Create general settings tab."""
        ttk.Label(parent, text="General Settings", font=('Segoe UI', 12, 'bold')).pack(anchor=W)

        # Auto-start
        ttk.Separator(parent).pack(fill=X, pady=15)
        self.autostart_var = tk.BooleanVar(value=self.config.is_autostart_enabled())
        if HAS_TTKBOOTSTRAP:
            ttk.Checkbutton(parent, text="Start CrossTrans with Windows",
                            variable=self.autostart_var,
                            bootstyle="round-toggle-success").pack(anchor=W, pady=5)
        else:
            ttk.Checkbutton(parent, text="Start CrossTrans with Windows",
                            variable=self.autostart_var).pack(anchor=W, pady=5)

        # Check for updates
        self.updates_var = tk.BooleanVar(value=self.config.get_check_updates())
        if HAS_TTKBOOTSTRAP:
            ttk.Checkbutton(parent, text="Check for updates on startup",
                            variable=self.updates_var,
                            bootstyle="round-toggle-success").pack(anchor=W, pady=5)
        else:
            ttk.Checkbutton(parent, text="Check for updates on startup",
                            variable=self.updates_var).pack(anchor=W, pady=5)

        # Check for updates button
        update_frame = ttk.Frame(parent)
        update_frame.pack(anchor=W, pady=(10, 0), fill=X)

        if HAS_TTKBOOTSTRAP:
            self.check_update_btn = ttk.Button(update_frame, text="Check for updates",
                                               command=self._check_for_updates_click,
                                               bootstyle="info-outline", width=18)
        else:
            self.check_update_btn = ttk.Button(update_frame, text="Check for updates",
                                               command=self._check_for_updates_click, width=18)
        self.check_update_btn.pack(side=LEFT)

        self.update_status_label = ttk.Label(update_frame, text="", font=('Segoe UI', 9))
        self.update_status_label.pack(side=LEFT, padx=(10, 0))

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

    def _create_dictionary_tab(self, parent):
        """Create Dictionary language packs management tab with collapsible design."""
        # Header first (always shows)
        ttk.Label(parent, text="Dictionary Language Packs",
                  font=('Segoe UI', 12, 'bold')).pack(anchor=W)

        ttk.Label(parent, text="Install language packs to enable smart word recognition in Dictionary mode.",
                  font=('Segoe UI', 9), foreground='#888888').pack(anchor=W, pady=(2, 10))

        try:
            self._create_dictionary_tab_content(parent)
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logging.error(f"Failed to create Dictionary tab content: {e}\n{error_details}")
            # Show error message with details
            error_frame = ttk.Frame(parent)
            error_frame.pack(fill=X, pady=20)
            ttk.Label(error_frame, text="Error loading Dictionary tab:",
                     font=('Segoe UI', 10, 'bold'), foreground='#ff6b6b').pack(anchor=W)
            ttk.Label(error_frame, text=str(e),
                     font=('Segoe UI', 9), foreground='#ff6b6b', wraplength=450).pack(anchor=W, pady=(5, 0))
            ttk.Label(error_frame, text="Please restart the application and try again.\n"
                                       "Check logs (crosstrans.log) for details.",
                     font=('Segoe UI', 9), foreground='#888888').pack(anchor=W, pady=(10, 0))

    def _create_dictionary_tab_content(self, parent):
        """Create the main content of Dictionary tab."""
        # Defensive import with error logging
        try:
            from src.core.nlp_manager import nlp_manager, LANGUAGE_PACKS
        except ImportError as e:
            logging.error(f"Failed to import nlp_manager: {e}")
            raise RuntimeError(f"Cannot import NLP manager: {e}")

        # Set config reference for nlp_manager
        try:
            nlp_manager.set_config(self.config)
        except Exception as e:
            logging.warning(f"Failed to set nlp_manager config: {e}")
            # Continue - this is not fatal

        # Clear installed cache to ensure fresh check (fix for UDPipe model detection)
        try:
            nlp_manager._installed_cache.clear()
        except Exception as e:
            logging.warning(f"Failed to clear installed cache: {e}")
            # Continue - this is not fatal

        # Store references
        self.nlp_pack_rows = {}
        self._nlp_all_languages = list(LANGUAGE_PACKS.keys())
        self._nlp_list_expanded = False  # Default: collapsed
        self._nlp_search_updating = False  # Flag to prevent filter trigger on placeholder update

        # ============ PROGRESS BAR (at top, hidden by default) ============
        self.nlp_progress_frame = ttk.Frame(parent)
        # Don't pack initially

        self.nlp_progress_label = ttk.Label(self.nlp_progress_frame, text="",
                                            font=('Segoe UI', 10))
        self.nlp_progress_label.pack(anchor=W)

        if HAS_TTKBOOTSTRAP:
            self.nlp_progress_bar = ttk.Progressbar(self.nlp_progress_frame,
                                                    bootstyle="success-striped",
                                                    length=500, mode='determinate')
        else:
            self.nlp_progress_bar = ttk.Progressbar(self.nlp_progress_frame,
                                                    length=500, mode='determinate')
        self.nlp_progress_bar.pack(fill=X, pady=5)

        # ============ INSTALLED LANGUAGES SECTION ============
        self.installed_frame = ttk.LabelFrame(parent, text=" Installed Languages ", padding=10)
        self.installed_frame.pack(fill=X, pady=(0, 15))

        # Get installed languages with error handling
        try:
            installed_languages = nlp_manager.get_installed_languages()
        except Exception as e:
            logging.error(f"Failed to get installed languages: {e}")
            installed_languages = []
        installed_count = len(installed_languages)
        total_count = len(LANGUAGE_PACKS)

        if installed_languages:
            # Create scrollable container for installed languages (max height 200px)
            installed_container = ttk.Frame(self.installed_frame)
            installed_container.pack(fill=X, expand=False)

            # Canvas for scrolling
            installed_canvas = tk.Canvas(installed_container, bg='#2b2b2b', highlightthickness=0, height=min(200, len(installed_languages) * 35))
            installed_scrollbar = ttk.Scrollbar(installed_container, orient="vertical", command=installed_canvas.yview)

            installed_inner_frame = ttk.Frame(installed_canvas)
            installed_inner_frame.bind(
                "<Configure>",
                lambda e: installed_canvas.configure(scrollregion=installed_canvas.bbox("all"))
            )

            installed_canvas.create_window((0, 0), window=installed_inner_frame, anchor="nw")
            installed_canvas.configure(yscrollcommand=installed_scrollbar.set)

            installed_canvas.pack(side=LEFT, fill=X, expand=True)
            # Only show scrollbar if more than 5 languages
            if len(installed_languages) > 5:
                installed_scrollbar.pack(side=RIGHT, fill=tk.Y)

            # Mouse wheel scrolling
            def _on_installed_mousewheel(event):
                installed_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            installed_canvas.bind("<MouseWheel>", _on_installed_mousewheel)
            installed_inner_frame.bind("<MouseWheel>", _on_installed_mousewheel)

            # Create a row for each installed language with Uninstall button
            for lang in installed_languages:
                row = ttk.Frame(installed_inner_frame)
                row.pack(fill=X, pady=3)
                row.bind("<MouseWheel>", _on_installed_mousewheel)

                # Green checkmark + language name
                chk = tk.Label(row, text="✓", fg='#28a745', bg='#2b2b2b',
                        font=('Segoe UI', 10, 'bold'))
                chk.pack(side=LEFT)
                chk.bind("<MouseWheel>", _on_installed_mousewheel)

                lbl = ttk.Label(row, text=lang, font=('Segoe UI', 10), width=20)
                lbl.pack(side=LEFT, padx=(5, 10))
                lbl.bind("<MouseWheel>", _on_installed_mousewheel)

                # Size info
                pack_info = LANGUAGE_PACKS.get(lang)
                if pack_info:
                    size_lbl = ttk.Label(row, text=f"~{pack_info.size_mb} MB",
                             font=('Segoe UI', 9), foreground='#888888')
                    size_lbl.pack(side=LEFT, padx=(0, 15))
                    size_lbl.bind("<MouseWheel>", _on_installed_mousewheel)

                # Uninstall button
                if HAS_TTKBOOTSTRAP:
                    uninstall_btn = ttk.Button(row, text="Uninstall", width=10,
                                              bootstyle="danger-outline",
                                              command=lambda l=lang: self._uninstall_nlp_pack(l))
                else:
                    uninstall_btn = ttk.Button(row, text="Uninstall", width=10,
                                              command=lambda l=lang: self._uninstall_nlp_pack(l))
                uninstall_btn.pack(side=LEFT)

            # Summary (outside scrollable area)
            total_size = nlp_manager.get_total_installed_size()
            self.nlp_summary_label = ttk.Label(
                self.installed_frame,
                text=f"{installed_count} language(s) installed (~{total_size} MB total)",
                font=('Segoe UI', 9), foreground='#888888'
            )
            self.nlp_summary_label.pack(anchor=W, pady=(10, 0))
        else:
            # No languages installed
            self.nlp_summary_label = ttk.Label(
                self.installed_frame,
                text="No language packs installed. Click 'Add More Languages' below to install.",
                font=('Segoe UI', 10), foreground='#888888'
            )
            self.nlp_summary_label.pack(anchor=W, pady=10)

        # ============ COLLAPSIBLE "ADD MORE LANGUAGES" SECTION ============
        # Toggle header
        toggle_frame = ttk.Frame(parent)
        toggle_frame.pack(fill=X, pady=(0, 5))

        self._toggle_arrow = tk.StringVar(value="▶")  # Collapsed by default
        toggle_label = tk.Label(toggle_frame, textvariable=self._toggle_arrow,
                               font=('Segoe UI', 10), fg='#4da6ff', cursor='hand2')
        toggle_label.pack(side=LEFT)
        toggle_label.bind('<Button-1>', lambda e: self._toggle_nlp_list())

        toggle_text = tk.Label(toggle_frame, text="Add More Languages",
                              font=('Segoe UI', 10, 'bold'), fg='#4da6ff', cursor='hand2')
        toggle_text.pack(side=LEFT, padx=(5, 0))
        toggle_text.bind('<Button-1>', lambda e: self._toggle_nlp_list())

        # Available count
        not_installed_count = total_count - installed_count
        self._available_count_label = ttk.Label(toggle_frame, text=f"({not_installed_count} available)",
                 font=('Segoe UI', 9), foreground='#888888')
        self._available_count_label.pack(side=LEFT, padx=(10, 0))

        # ============ COLLAPSIBLE CONTENT FRAME ============
        self.nlp_collapsible_frame = ttk.Frame(parent)
        # Don't pack initially (collapsed)

        # Search and filter inside collapsible frame
        controls_frame = ttk.Frame(self.nlp_collapsible_frame)
        controls_frame.pack(fill=X, pady=(5, 10))

        # Search box
        ttk.Label(controls_frame, text="🔍", font=('Segoe UI', 10)).pack(side=LEFT, padx=(0, 5))
        self.nlp_search_var = tk.StringVar()
        self.nlp_search_entry = ttk.Entry(controls_frame, textvariable=self.nlp_search_var,
                                          font=('Segoe UI', 10), width=25)
        self.nlp_search_entry.pack(side=LEFT)
        self.nlp_search_entry.insert(0, "Search...")
        self.nlp_search_entry.bind('<FocusIn>', self._on_nlp_search_focus_in)
        self.nlp_search_entry.bind('<FocusOut>', self._on_nlp_search_focus_out)
        self.nlp_search_var.trace_add('write', self._filter_nlp_languages)

        # Filter buttons
        self.nlp_filter_var = tk.StringVar(value="all")

        ttk.Radiobutton(controls_frame, text="All", variable=self.nlp_filter_var,
                       value="all", command=self._filter_nlp_languages).pack(side=LEFT, padx=(20, 5))
        ttk.Radiobutton(controls_frame, text="Not Installed", variable=self.nlp_filter_var,
                       value="not_installed", command=self._filter_nlp_languages).pack(side=LEFT, padx=5)

        # Bulk action buttons (right side)
        bulk_frame = ttk.Frame(controls_frame)
        bulk_frame.pack(side=RIGHT)

        # Install All button
        if HAS_TTKBOOTSTRAP:
            self.install_all_btn = ttk.Button(bulk_frame, text="Install All", width=10,
                                              bootstyle="success-outline",
                                              command=self._install_all_nlp_packs)
        else:
            self.install_all_btn = ttk.Button(bulk_frame, text="Install All", width=10,
                                              command=self._install_all_nlp_packs)
        self.install_all_btn.pack(side=LEFT, padx=2)

        # Delete All button
        if HAS_TTKBOOTSTRAP:
            self.delete_all_btn = ttk.Button(bulk_frame, text="Delete All", width=10,
                                             bootstyle="danger-outline",
                                             command=self._delete_all_nlp_packs)
        else:
            self.delete_all_btn = ttk.Button(bulk_frame, text="Delete All", width=10,
                                             command=self._delete_all_nlp_packs)
        self.delete_all_btn.pack(side=LEFT, padx=2)

        # Animation state for bulk buttons
        self._bulk_animation_running = False
        self._bulk_animation_step = 0
        self._bulk_animation_btn = None
        self._bulk_animation_original_text = ""

        # Scrollable language list
        list_container = ttk.Frame(self.nlp_collapsible_frame)
        list_container.pack(fill=BOTH, expand=True, pady=(0, 10))

        # Canvas for scrolling
        self.nlp_canvas = tk.Canvas(list_container, bg='#2b2b2b', highlightthickness=0, height=200)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.nlp_canvas.yview)

        self.nlp_scrollable_frame = ttk.Frame(self.nlp_canvas)
        self.nlp_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.nlp_canvas.configure(scrollregion=self.nlp_canvas.bbox("all"))
        )

        self.nlp_canvas.create_window((0, 0), window=self.nlp_scrollable_frame, anchor="nw")
        self.nlp_canvas.configure(yscrollcommand=scrollbar.set)

        # Mouse wheel scrolling (only when canvas has focus)
        def on_mousewheel(event):
            if self.nlp_canvas.winfo_exists():
                self.nlp_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        self.nlp_canvas.bind("<MouseWheel>", on_mousewheel)
        self.nlp_scrollable_frame.bind("<MouseWheel>", on_mousewheel)

        self.nlp_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=tk.Y)

        # Header row
        header = ttk.Frame(self.nlp_scrollable_frame)
        header.pack(fill=X, pady=(0, 5), padx=5)
        ttk.Label(header, text="Language", font=('Segoe UI', 9, 'bold'), width=20).pack(side=LEFT)
        ttk.Label(header, text="Category", font=('Segoe UI', 9, 'bold'), width=12).pack(side=LEFT)
        ttk.Label(header, text="Size", font=('Segoe UI', 9, 'bold'), width=8).pack(side=LEFT)
        ttk.Label(header, text="", width=10).pack(side=LEFT)

        ttk.Separator(self.nlp_scrollable_frame).pack(fill=X, pady=3, padx=5)

        # Create rows for each language
        self._create_nlp_language_rows()

        # Info note (outside collapsible)
        ttk.Label(parent, text="ℹ️ Language packs are downloaded from PyPI. Internet connection required.",
                  font=('Segoe UI', 9), foreground='#666666').pack(anchor=W, pady=(10, 0))

    def _toggle_nlp_list(self):
        """Toggle the collapsible language list."""
        self._nlp_list_expanded = not self._nlp_list_expanded

        if self._nlp_list_expanded:
            self._toggle_arrow.set("▼")
            self.nlp_collapsible_frame.pack(fill=BOTH, expand=True, pady=(0, 5))

            # Auto-scroll to top and focus search for immediate interaction
            def setup_expanded_view():
                try:
                    self.nlp_canvas.yview_moveto(0.0)  # Scroll to top
                    # Clear search placeholder and focus
                    current = self.nlp_search_entry.get()
                    if current in ("Search...", "Search languages..."):
                        self._nlp_search_updating = True
                        self.nlp_search_entry.delete(0, tk.END)
                        self._nlp_search_updating = False
                    self.nlp_search_entry.focus_set()
                except tk.TclError:
                    pass  # Widget destroyed
            self.nlp_collapsible_frame.after(50, setup_expanded_view)
        else:
            self._toggle_arrow.set("▶")
            self.nlp_collapsible_frame.pack_forget()

    def _create_nlp_language_rows(self):
        """Create language rows in the scrollable frame (not installed only)."""
        from src.core.nlp_manager import nlp_manager, LANGUAGE_PACKS

        # Clear existing rows (skip header and separator)
        for widget in list(self.nlp_scrollable_frame.winfo_children())[2:]:
            widget.destroy()
        self.nlp_pack_rows.clear()

        # Get filter settings
        search_term = self.nlp_search_var.get().lower()
        if search_term in ("search...", "search languages..."):
            search_term = ""
        filter_mode = self.nlp_filter_var.get()

        # When search is empty, show ALL languages (both installed & not installed)
        # Only apply filter when user starts typing
        show_all = not search_term

        # Create rows for each language
        for language in sorted(LANGUAGE_PACKS.keys()):
            pack = LANGUAGE_PACKS[language]
            is_installed = nlp_manager.is_installed(language)

            # Apply search filter (only when user is typing)
            if search_term and search_term not in language.lower():
                continue

            # Apply installed filter only when search term exists
            if not show_all:
                if filter_mode == "not_installed" and is_installed:
                    continue

            row = ttk.Frame(self.nlp_scrollable_frame)
            row.pack(fill=X, pady=2, padx=5)

            # Language name
            ttk.Label(row, text=language, font=('Segoe UI', 10), width=20).pack(side=LEFT)

            # Category
            ttk.Label(row, text=pack.category, font=('Segoe UI', 9),
                     foreground='#888888', width=12).pack(side=LEFT)

            # Size
            ttk.Label(row, text=f"~{pack.size_mb}MB", font=('Segoe UI', 9), width=8).pack(side=LEFT)

            # Action button
            btn_frame = ttk.Frame(row)
            btn_frame.pack(side=LEFT)

            if is_installed:
                # Show "Installed" badge instead of button
                badge = tk.Label(btn_frame, text="✓ Installed", bg='#28a745', fg='white',
                               font=('Segoe UI', 8), padx=6, pady=2)
                badge.pack()
                action_btn = None
            else:
                if HAS_TTKBOOTSTRAP:
                    action_btn = ttk.Button(btn_frame, text="Install", width=8,
                                           bootstyle="success-outline",
                                           command=lambda l=language: self._install_nlp_pack(l))
                else:
                    action_btn = ttk.Button(btn_frame, text="Install", width=8,
                                           command=lambda l=language: self._install_nlp_pack(l))
                action_btn.pack()

            # Store references
            self.nlp_pack_rows[language] = {
                'row': row,
                'action_btn': action_btn,
                'btn_frame': btn_frame
            }

    def _on_nlp_search_focus_in(self, event):
        """Handle search box focus in."""
        current = self.nlp_search_entry.get()
        if current in ("Search...", "Search languages..."):
            # Temporarily disable trace to avoid triggering filter
            self._nlp_search_updating = True
            self.nlp_search_entry.delete(0, tk.END)
            self._nlp_search_updating = False

    def _on_nlp_search_focus_out(self, event):
        """Handle search box focus out."""
        if not self.nlp_search_entry.get():
            # Temporarily disable trace to avoid triggering filter
            self._nlp_search_updating = True
            self.nlp_search_entry.insert(0, "Search...")
            self._nlp_search_updating = False

    def _filter_nlp_languages(self, *args):
        """Filter language list based on search and filter settings."""
        # Skip if install/uninstall is in progress
        if getattr(self, '_nlp_operation_in_progress', False):
            return
        # Skip if just updating placeholder text
        if getattr(self, '_nlp_search_updating', False):
            return
        self._create_nlp_language_rows()

    def _update_nlp_summary(self):
        """Update NLP installation summary."""
        from src.core.nlp_manager import nlp_manager

        installed_count, total_count = nlp_manager.get_language_count()
        total_size = nlp_manager.get_total_installed_size()

        if installed_count > 0:
            self.nlp_summary_label.config(
                text=f"{installed_count} language(s) installed (~{total_size} MB total)"
            )
        else:
            self.nlp_summary_label.config(
                text="No language packs installed. Click 'Add More Languages' below to install."
            )

    def _install_nlp_pack(self, language: str):
        """Install an NLP language pack with animated progress bar."""
        from src.core.nlp_manager import nlp_manager, LANGUAGE_PACKS

        # Prevent filter from triggering during install
        self._nlp_operation_in_progress = True

        pack_info = LANGUAGE_PACKS.get(language)
        size_mb = pack_info.size_mb if pack_info else "?"

        # Show progress bar at top of tab (before installed section)
        self.nlp_progress_frame.pack(fill=X, pady=(0, 15), before=self.installed_frame)
        self.nlp_progress_label.config(text=f"⏳ Installing {language} (~{size_mb} MB)...")
        self.nlp_progress_bar['value'] = 0
        if HAS_TTKBOOTSTRAP:
            self.nlp_progress_bar.configure(bootstyle="info-striped")
        self.window.update()

        # Disable all Install buttons
        self._disable_all_nlp_buttons()

        # Start animated progress simulation
        self._progress_animation_running = True
        self._animate_progress(0)

        # Run installation in thread
        def do_install():
            def progress_callback(message: str, percent: int):
                self.window.after(0, lambda m=message, p=percent: self._update_install_progress(m, p))

            success, error = nlp_manager.install(language, progress_callback)
            self._progress_animation_running = False
            self.window.after(0, lambda: self._on_install_complete(language, success, error))

        thread = threading.Thread(target=do_install, daemon=True)
        thread.start()

    def _animate_progress(self, value: int):
        """Animate progress bar smoothly."""
        if not self._progress_animation_running:
            return
        # Gradually increase to 90% while waiting for actual completion
        if value < 90:
            self.nlp_progress_bar['value'] = value
            self.window.after(200, lambda: self._animate_progress(value + 2))

    def _update_install_progress(self, message: str, percent: int):
        """Update installation progress UI."""
        try:
            self.nlp_progress_label.config(text=f"⏳ {message}")
            if percent > 0:
                self.nlp_progress_bar['value'] = percent
        except tk.TclError:
            pass

    def _disable_all_nlp_buttons(self):
        """Disable all Install/Uninstall buttons during operation."""
        # Disable buttons in Add More Languages list
        for lang, row_data in self.nlp_pack_rows.items():
            if row_data.get('action_btn'):
                try:
                    row_data['action_btn'].config(state='disabled')
                except tk.TclError:
                    pass
        # Disable Uninstall buttons in Installed section
        for widget in self.installed_frame.winfo_children():
            if isinstance(widget, ttk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Button):
                        try:
                            child.config(state='disabled')
                        except tk.TclError:
                            pass

    def _on_install_complete(self, language: str, success: bool, error: str):
        """Handle installation completion with animation."""
        from src.core.nlp_manager import nlp_manager

        if success:
            # Update config
            self.config.add_nlp_installed(language)

            # Show success animation in progress bar
            self.nlp_progress_label.config(text=f"✓ {language} installed successfully!")
            self.nlp_progress_bar['value'] = 100

            # Flash green color effect
            if HAS_TTKBOOTSTRAP:
                self.nlp_progress_bar.configure(bootstyle="success")

            # Delay before hiding progress and refreshing
            def finish_install():
                self.nlp_progress_frame.pack_forget()
                # Clear cache to force re-check installed status
                nlp_manager._installed_cache.clear()
                # Re-enable filter
                self._nlp_operation_in_progress = False
                # Delay to let Python import system stabilize, then refresh
                self.window.after(500, self._refresh_dictionary_tab)

            self.window.after(1500, finish_install)
        else:
            # Hide progress immediately on error
            self.nlp_progress_frame.pack_forget()
            # Re-enable filter
            self._nlp_operation_in_progress = False

            # Re-enable all buttons
            for lang, row_data in self.nlp_pack_rows.items():
                if row_data.get('action_btn'):
                    try:
                        row_data['action_btn'].config(state='normal')
                    except tk.TclError:
                        pass

            # Show error
            if HAS_TTKBOOTSTRAP:
                Messagebox.show_error(f"Failed to install {language}:\n\n{error}",
                                     title="Installation Failed", parent=self.window)
            else:
                from tkinter import messagebox
                messagebox.showerror("Installation Failed",
                                    f"Failed to install {language}:\n\n{error}",
                                    parent=self.window)

    def _uninstall_nlp_pack(self, language: str):
        """Uninstall an NLP language pack with animation.

        Runs pip uninstall in background thread to avoid blocking UI.
        """
        from src.core.nlp_manager import nlp_manager

        # Confirm uninstall
        if HAS_TTKBOOTSTRAP:
            answer = Messagebox.yesno(
                f"Remove {language} language pack?\n\n"
                "This will uninstall the pip packages.",
                title="Confirm Remove", parent=self.window
            )
            if answer != "Yes":
                return
        else:
            from tkinter import messagebox
            if not messagebox.askyesno("Confirm Remove",
                                       f"Remove {language} language pack?\n\n"
                                       "This will uninstall the pip packages.",
                                       parent=self.window):
                return

        # Prevent filter from triggering during uninstall
        self._nlp_operation_in_progress = True

        # Disable all buttons
        self._disable_all_nlp_buttons()

        # Show progress bar at top (before installed section)
        self.nlp_progress_frame.pack(fill=X, pady=(0, 15), before=self.installed_frame)
        self.nlp_progress_label.config(text=f"⏳ Removing {language}...")
        self.nlp_progress_bar['value'] = 0
        if HAS_TTKBOOTSTRAP:
            self.nlp_progress_bar.configure(bootstyle="warning-striped")
        self.window.update()

        # Start animation (same pattern as install)
        self._progress_animation_running = True
        self._animate_progress(0)

        # Run uninstall in background thread
        def do_uninstall():
            def progress_callback(message: str, percent: int):
                def update_ui():
                    try:
                        self.nlp_progress_label.config(text=f"⏳ {message}")
                        self.nlp_progress_bar['value'] = percent
                    except tk.TclError:
                        pass
                self.window.after(0, update_ui)

            success, error = nlp_manager.uninstall(language, progress_callback)

            # Stop animation
            self._progress_animation_running = False

            def on_complete():

                if success:
                    # Clear cache to force re-check
                    nlp_manager._installed_cache.clear()

                    # Update config
                    self.config.remove_nlp_installed(language)

                    # Show success animation
                    self.nlp_progress_bar['value'] = 100
                    self.nlp_progress_label.config(text=f"✓ {language} removed successfully!")
                    if HAS_TTKBOOTSTRAP:
                        self.nlp_progress_bar.configure(bootstyle="success")
                    self.window.update()

                    # Delay before hiding and refreshing
                    def finish_uninstall():
                        self.nlp_progress_frame.pack_forget()
                        if HAS_TTKBOOTSTRAP:
                            self.nlp_progress_bar.configure(bootstyle="success-striped")
                        # Re-enable filter
                        self._nlp_operation_in_progress = False
                        # Delay to let Python import system stabilize
                        self.window.after(500, self._refresh_dictionary_tab)

                    self.window.after(1000, finish_uninstall)
                else:
                    # Hide progress
                    self.nlp_progress_frame.pack_forget()
                    if HAS_TTKBOOTSTRAP:
                        self.nlp_progress_bar.configure(bootstyle="success-striped")
                    # Re-enable filter
                    self._nlp_operation_in_progress = False

                    # Re-enable buttons
                    self._refresh_dictionary_tab()

                    if HAS_TTKBOOTSTRAP:
                        Messagebox.show_error(f"Failed to remove {language}:\n\n{error}",
                                             title="Remove Failed", parent=self.window)
                    else:
                        from tkinter import messagebox
                        messagebox.showerror("Remove Failed",
                                            f"Failed to remove {language}:\n\n{error}",
                                            parent=self.window)

            self.window.after(0, on_complete)

        thread = threading.Thread(target=do_uninstall, daemon=True)
        thread.start()

    def _install_all_nlp_packs(self):
        """Install all available (not installed) language packs."""
        from src.core.nlp_manager import nlp_manager, LANGUAGE_PACKS

        # Get list of not installed languages
        not_installed = [lang for lang in LANGUAGE_PACKS.keys()
                        if not nlp_manager.is_installed(lang)]

        if not not_installed:
            if HAS_TTKBOOTSTRAP:
                Messagebox.show_info("All language packs are already installed!",
                                    title="Nothing to Install", parent=self.window)
            else:
                from tkinter import messagebox
                messagebox.showinfo("Nothing to Install",
                                   "All language packs are already installed!",
                                   parent=self.window)
            return

        # Confirm install all
        total_size = sum(LANGUAGE_PACKS[lang].size_mb for lang in not_installed)
        if HAS_TTKBOOTSTRAP:
            answer = Messagebox.yesno(
                f"Install all {len(not_installed)} language packs?\n\n"
                f"Total size: ~{total_size} MB\n"
                "This may take several minutes.",
                title="Confirm Install All", parent=self.window
            )
            if answer != "Yes":
                return
        else:
            from tkinter import messagebox
            if not messagebox.askyesno("Confirm Install All",
                                       f"Install all {len(not_installed)} language packs?\n\n"
                                       f"Total size: ~{total_size} MB\n"
                                       "This may take several minutes.",
                                       parent=self.window):
                return

        # Start bulk install with animation
        self._start_bulk_animation(self.install_all_btn, "Installing")
        self._bulk_install_queue = list(not_installed)
        self._bulk_install_total = len(not_installed)
        self._bulk_install_current = 0
        self._install_next_in_queue()

    def _install_next_in_queue(self):
        """Install the next language in the bulk install queue."""
        from src.core.nlp_manager import nlp_manager, LANGUAGE_PACKS

        if not self._bulk_install_queue:
            # All done
            self._stop_bulk_animation()
            self._refresh_dictionary_tab()
            if HAS_TTKBOOTSTRAP:
                Messagebox.show_info(
                    f"Successfully installed {self._bulk_install_total} language packs!",
                    title="Install Complete", parent=self.window
                )
            else:
                from tkinter import messagebox
                messagebox.showinfo("Install Complete",
                                   f"Successfully installed {self._bulk_install_total} language packs!",
                                   parent=self.window)
            return

        language = self._bulk_install_queue.pop(0)
        self._bulk_install_current += 1

        # Update animation text
        self._bulk_animation_base_text = f"Installing ({self._bulk_install_current}/{self._bulk_install_total})"

        pack_info = LANGUAGE_PACKS.get(language)
        size_mb = pack_info.size_mb if pack_info else "?"

        # Show progress bar
        self._nlp_operation_in_progress = True
        self.nlp_progress_frame.pack(fill=X, pady=(0, 15), before=self.installed_frame)
        self.nlp_progress_label.config(text=f"⏳ Installing {language} ({self._bulk_install_current}/{self._bulk_install_total})...")
        self.nlp_progress_bar['value'] = 0
        if HAS_TTKBOOTSTRAP:
            self.nlp_progress_bar.configure(bootstyle="info-striped")
        self.window.update()

        self._disable_all_nlp_buttons()
        self._progress_animation_running = True
        self._animate_progress(0)

        def do_install():
            def progress_callback(message: str, percent: int):
                self.window.after(0, lambda m=message, p=percent: self._update_install_progress(m, p))

            success, error = nlp_manager.install(language, progress_callback)
            self._progress_animation_running = False
            self.window.after(0, lambda: self._on_bulk_install_complete(language, success, error))

        thread = threading.Thread(target=do_install, daemon=True)
        thread.start()

    def _on_bulk_install_complete(self, language: str, success: bool, error: str):
        """Handle completion of one language in bulk install."""
        if success:
            self.nlp_progress_bar['value'] = 100
            self.nlp_progress_label.config(text=f"✓ {language} installed!")
            if HAS_TTKBOOTSTRAP:
                self.nlp_progress_bar.configure(bootstyle="success")
            self.window.update()
            self.config.add_nlp_installed(language)

            # Short delay then install next
            self.window.after(500, lambda: self._install_next_continue())
        else:
            # Log error but continue with next
            logging.warning(f"Failed to install {language}: {error}")
            self.window.after(500, lambda: self._install_next_continue())

    def _install_next_continue(self):
        """Continue to next language in queue."""
        self._nlp_operation_in_progress = False
        self.nlp_progress_frame.pack_forget()
        if HAS_TTKBOOTSTRAP:
            self.nlp_progress_bar.configure(bootstyle="success-striped")
        self._install_next_in_queue()

    def _delete_all_nlp_packs(self):
        """Delete all installed language packs."""
        from src.core.nlp_manager import nlp_manager

        installed = nlp_manager.get_installed_languages()

        if not installed:
            if HAS_TTKBOOTSTRAP:
                Messagebox.show_info("No language packs are installed!",
                                    title="Nothing to Delete", parent=self.window)
            else:
                from tkinter import messagebox
                messagebox.showinfo("Nothing to Delete",
                                   "No language packs are installed!",
                                   parent=self.window)
            return

        # Confirm delete all
        if HAS_TTKBOOTSTRAP:
            answer = Messagebox.yesno(
                f"Remove all {len(installed)} language packs?\n\n"
                "This cannot be undone.",
                title="Confirm Delete All", parent=self.window
            )
            if answer != "Yes":
                return
        else:
            from tkinter import messagebox
            if not messagebox.askyesno("Confirm Delete All",
                                       f"Remove all {len(installed)} language packs?\n\n"
                                       "This cannot be undone.",
                                       parent=self.window):
                return

        # Start bulk delete with animation
        self._start_bulk_animation(self.delete_all_btn, "Deleting")
        self._bulk_delete_queue = list(installed)
        self._bulk_delete_total = len(installed)
        self._bulk_delete_current = 0
        self._delete_next_in_queue()

    def _delete_next_in_queue(self):
        """Delete the next language in the bulk delete queue."""
        from src.core.nlp_manager import nlp_manager

        if not self._bulk_delete_queue:
            # All done
            self._stop_bulk_animation()
            self._refresh_dictionary_tab()
            if HAS_TTKBOOTSTRAP:
                Messagebox.show_info(
                    f"Successfully removed {self._bulk_delete_total} language packs!",
                    title="Delete Complete", parent=self.window
                )
            else:
                from tkinter import messagebox
                messagebox.showinfo("Delete Complete",
                                   f"Successfully removed {self._bulk_delete_total} language packs!",
                                   parent=self.window)
            return

        language = self._bulk_delete_queue.pop(0)
        self._bulk_delete_current += 1

        # Update animation text
        self._bulk_animation_base_text = f"Deleting ({self._bulk_delete_current}/{self._bulk_delete_total})"

        # Show progress bar
        self._nlp_operation_in_progress = True
        self.nlp_progress_frame.pack(fill=X, pady=(0, 15), before=self.installed_frame)
        self.nlp_progress_label.config(text=f"⏳ Removing {language} ({self._bulk_delete_current}/{self._bulk_delete_total})...")
        self.nlp_progress_bar['value'] = 0
        if HAS_TTKBOOTSTRAP:
            self.nlp_progress_bar.configure(bootstyle="warning-striped")
        self.window.update()

        self._disable_all_nlp_buttons()
        self._progress_animation_running = True
        self._animate_progress(0)

        def do_uninstall():
            def progress_callback(message: str, percent: int):
                self.window.after(0, lambda m=message, p=percent: self._update_install_progress(m, p))

            success, error = nlp_manager.uninstall(language, progress_callback)
            self._progress_animation_running = False
            self.window.after(0, lambda: self._on_bulk_delete_complete(language, success, error))

        thread = threading.Thread(target=do_uninstall, daemon=True)
        thread.start()

    def _on_bulk_delete_complete(self, language: str, success: bool, error: str):
        """Handle completion of one language in bulk delete."""
        from src.core.nlp_manager import nlp_manager

        if success:
            nlp_manager._installed_cache.clear()
            self.config.remove_nlp_installed(language)
            self.nlp_progress_bar['value'] = 100
            self.nlp_progress_label.config(text=f"✓ {language} removed!")
            if HAS_TTKBOOTSTRAP:
                self.nlp_progress_bar.configure(bootstyle="success")
            self.window.update()

            # Short delay then delete next
            self.window.after(500, lambda: self._delete_next_continue())
        else:
            # Log error but continue with next
            logging.warning(f"Failed to remove {language}: {error}")
            self.window.after(500, lambda: self._delete_next_continue())

    def _delete_next_continue(self):
        """Continue to next language in queue."""
        self._nlp_operation_in_progress = False
        self.nlp_progress_frame.pack_forget()
        if HAS_TTKBOOTSTRAP:
            self.nlp_progress_bar.configure(bootstyle="success-striped")
        self._delete_next_in_queue()

    def _start_bulk_animation(self, btn, base_text: str):
        """Start '...' animation on a bulk action button."""
        self._bulk_animation_running = True
        self._bulk_animation_step = 0
        self._bulk_animation_btn = btn
        self._bulk_animation_base_text = base_text
        self._bulk_animation_original_text = btn.cget('text')
        self._animate_bulk_button()

    def _animate_bulk_button(self):
        """Animate the bulk action button with moving dots."""
        if not self._bulk_animation_running or not self._bulk_animation_btn:
            return

        try:
            dots = "." * (self._bulk_animation_step % 4)
            spaces = " " * (3 - (self._bulk_animation_step % 4))
            self._bulk_animation_btn.configure(text=f"{self._bulk_animation_base_text}{dots}{spaces}")
            self._bulk_animation_step += 1
            self.window.after(400, self._animate_bulk_button)
        except tk.TclError:
            self._bulk_animation_running = False

    def _stop_bulk_animation(self):
        """Stop bulk action button animation."""
        self._bulk_animation_running = False
        if self._bulk_animation_btn:
            try:
                self._bulk_animation_btn.configure(text=self._bulk_animation_original_text)
            except tk.TclError:
                pass
        self._bulk_animation_btn = None

    def _refresh_dictionary_tab(self):
        """Refresh entire Dictionary tab to reflect install/uninstall changes."""
        try:
            # Find and clear the Dictionary tab frame
            if hasattr(self, 'notebook'):
                for i in range(self.notebook.index('end')):
                    if 'Dictionary' in self.notebook.tab(i, 'text'):
                        # Get the tab frame
                        tab_id = self.notebook.tabs()[i]
                        dict_frame = self.notebook.nametowidget(tab_id)

                        # Clear all children
                        for widget in dict_frame.winfo_children():
                            widget.destroy()

                        # Rebuild the tab
                        self._create_dictionary_tab(dict_frame)

                        # Re-select Dictionary tab
                        self.notebook.select(i)
                        break
        except Exception as e:
            logging.error(f"Failed to refresh Dictionary tab: {e}")
            # Fallback: show message asking user to reopen Settings
            if HAS_TTKBOOTSTRAP:
                Messagebox.show_warning(
                    "Please close and reopen Settings to see changes.",
                    title="Refresh Failed", parent=self.window
                )

    def open_dictionary_tab(self):
        """Open settings window with Dictionary tab selected."""
        self.open_tab("Dictionary")

    def open_tab(self, tab_name: str):
        """Open settings window with specified tab selected.

        Args:
            tab_name: Name of tab to select (e.g., "General", "Hotkeys", "API Key", "Dictionary", "Guide")
        """
        if hasattr(self, 'notebook'):
            # Find tab by name (partial match)
            for i in range(self.notebook.index('end')):
                tab_text = self.notebook.tab(i, 'text')
                if tab_name in tab_text:
                    self.notebook.select(i)
                    break

    def _create_guide_tab(self, parent):
        """Create user guide tab with helpful instructions."""
        # Scrollable container
        canvas = tk.Canvas(parent, highlightthickness=0)
        guide_container = ttk.Frame(canvas)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=RIGHT, fill='y')
        canvas.pack(side=LEFT, fill=BOTH, expand=True)

        window_id = canvas.create_window((0, 0), window=guide_container, anchor=NW)

        def _configure_canvas(event):
            canvas.itemconfig(window_id, width=event.width)
        canvas.bind('<Configure>', _configure_canvas)

        def _on_mousewheel(event):
            if canvas.winfo_exists() and canvas.winfo_ismapped():
                try:
                    canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                except tk.TclError:
                    pass
        canvas.bind("<MouseWheel>", _on_mousewheel)
        guide_container.bind("<MouseWheel>", _on_mousewheel)

        # Header
        ttk.Label(guide_container, text="User Guide", font=('Segoe UI', 14, 'bold')).pack(anchor=W, pady=(0, 5))
        ttk.Label(guide_container, text="Everything you need to know about CrossTrans",
                  font=('Segoe UI', 9), foreground='#888888').pack(anchor=W, pady=(0, 15))

        # === Section 1: Quick Start ===
        self._create_guide_section(guide_container, "Quick Start", [
            "1. Select any text in any application (browser, Word, PDF viewer, etc.)",
            "2. Press a hotkey (e.g., Win+Alt+V for Vietnamese)",
            "3. Translation appears in a tooltip near your cursor",
            "4. Click 'Copy' to copy the translation, or press Escape to close",
        ])

        # === Section 2: How to Get Free API Key ===
        self._create_guide_section(guide_container, "How to Get a Free API Key", [
            "Google Gemini offers a generous free tier (1,500 requests/day):",
            "",
            "1. Go to Google AI Studio:",
        ])

        # Clickable link for Google AI Studio
        link_frame = ttk.Frame(guide_container)
        link_frame.pack(anchor=W, padx=20)
        if HAS_TTKBOOTSTRAP:
            link_btn = ttk.Button(link_frame, text="https://aistudio.google.com/app/apikey",
                                  command=lambda: webbrowser.open("https://aistudio.google.com/app/apikey"),
                                  bootstyle="link")
        else:
            link_btn = ttk.Button(link_frame, text="https://aistudio.google.com/app/apikey",
                                  command=lambda: webbrowser.open("https://aistudio.google.com/app/apikey"))
        link_btn.pack(anchor=W)

        self._create_guide_content(guide_container, [
            "",
            "2. Sign in with your Google account",
            "3. Click 'Create API Key' button",
            "4. Copy the generated key",
            "5. Open Settings > API Key tab > Paste in 'API Key' field",
            "6. Click 'Test' to verify the connection",
            "",
            "[Screenshots will be added here]",
        ])

        # === Section 3: Default Hotkeys ===
        self._create_guide_section(guide_container, "Default Hotkeys", [
            "Translation Hotkeys:",
            "  • Win + Alt + V  →  Translate to Vietnamese",
            "  • Win + Alt + E  →  Translate to English",
            "  • Win + Alt + J  →  Translate to Japanese",
            "  • Win + Alt + C  →  Translate to Chinese (Simplified)",
            "",
            "You can customize hotkeys in the 'Hotkeys' tab.",
        ])

        self._create_guide_section(guide_container, "File Translation", [
            "Translate entire documents with a single click:",
            "",
            "Supported formats:",
            "  • .txt   - Plain text files",
            "  • .docx  - Microsoft Word documents",
            "  • .srt   - Subtitle files",
            "  • .pdf   - PDF documents (text-based and scanned)",
            "",
            "How to use:",
            "1. Right-click tray icon > 'Open Translator'",
            "2. Click the '+' button or drag & drop files",
            "3. Select target language",
            "4. Click 'Translate'",
            "",
            "Tips:",
            "  • You can add multiple files at once",
            "  • Images (PNG, JPG) are also supported for OCR",
        ])

        self._create_guide_section(guide_container, "Dictionary Mode", [
            "Click the 'Dictionary' button to look up words interactively:",
            "",
            "Word Selection:",
            "  • Click on any word to select/deselect it",
            "  • Drag across multiple words to select a range",
            "  • Shift+Click to select from anchor to clicked word",
            "",
            "Dictionary Lookup:",
            "  • Select words and click 'Dictionary Lookup'",
            "  • Get translation, definition, word type, pronunciation",
            "  • Example sentences with translations",
            "",
            "Features:",
            "  • Words flow like a paragraph with line wrapping",
            "  • 'Expand' button for larger view",
            "  • Results appear in a separate window",
        ])

        # === Section 6: Tips & Tricks ===
        self._create_guide_section(guide_container, "Tips & Tricks", [
            "Custom Prompts:",
            "  • Add instructions in the 'Custom prompt' field",
            "  • Examples: 'formal tone', 'casual', 'technical terms'",
            "",
            "Translation History:",
            "  • Click the clock icon to view past translations",
            "  • Search through history with keywords",
            "  • Copy any previous translation",
            "",
            "Multiple API Keys:",
            "  • Add backup keys for failover redundancy",
            "  • If primary API fails, backup is used automatically",
            "",
            "Trial Mode:",
            "  • 100 free translations/day without API key",
            "  • Quota resets at midnight",
            "  • Get your own API key for unlimited use",
        ])

        # === Section 7: Troubleshooting ===
        self._create_guide_section(guide_container, "Troubleshooting", [
            "Hotkey not working?",
            "  • Check if another app is using the same hotkey",
            "  • Try running CrossTrans as Administrator",
            "  • Reconfigure hotkeys in Settings > Hotkeys",
            "",
            "API Error / Connection Failed?",
            "  • Verify your API key is correct",
            "  • Click 'Test' to check the connection",
            "  • Make sure you have internet access",
            "  • Check if you've exceeded API quota",
            "",
            "Translation not appearing?",
            "  • Make sure text is selected before pressing hotkey",
            "  • Try copying text manually (Ctrl+C) first",
            "  • Some applications block clipboard access",
        ])

        # === Section 8: Supported Providers ===
        self._create_guide_section(guide_container, "Supported AI Providers", [
            "13 providers with 180+ models:",
            "",
            "Free Tier Available:",
            "  • Google Gemini - 1,500 req/day (Recommended)",
            "  • Groq - Fast inference, Llama 3.3",
            "  • Cerebras - High throughput",
            "  • DeepSeek - DeepSeek-R1, V3",
            "  • SambaNova - Llama 405B",
            "",
            "Premium Providers:",
            "  • OpenAI (o3, GPT-4.1, GPT-4o)",
            "  • Anthropic (Claude 4.5, Claude 3.5)",
            "  • xAI (Grok 3)",
            "  • Mistral AI, Perplexity, Together, SiliconFlow",
            "  • OpenRouter (400+ aggregated models)",
            "",
            "Auto-detection:",
            "  • App detects provider from API key pattern",
            "  • Smart fallback tries multiple models automatically",
        ])

        # Footer
        ttk.Separator(guide_container).pack(fill=X, pady=20)
        footer_frame = ttk.Frame(guide_container)
        footer_frame.pack(fill=X)

        ttk.Label(footer_frame, text="Need more help?", font=('Segoe UI', 9, 'bold')).pack(anchor=W)

        links_frame = ttk.Frame(footer_frame)
        links_frame.pack(anchor=W, pady=5)

        if HAS_TTKBOOTSTRAP:
            ttk.Button(links_frame, text="View on GitHub",
                       command=lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}"),
                       bootstyle="link").pack(side=LEFT)
            ttk.Label(links_frame, text="  |  ").pack(side=LEFT)
            ttk.Button(links_frame, text="Report an Issue",
                       command=lambda: webbrowser.open(FEEDBACK_URL),
                       bootstyle="link").pack(side=LEFT)
        else:
            ttk.Button(links_frame, text="View on GitHub",
                       command=lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}")).pack(side=LEFT)
            ttk.Label(links_frame, text="  |  ").pack(side=LEFT)
            ttk.Button(links_frame, text="Report an Issue",
                       command=lambda: webbrowser.open(FEEDBACK_URL)).pack(side=LEFT)

        # Update scroll region
        def update_scroll():
            guide_container.update_idletasks()
            canvas.config(scrollregion=canvas.bbox("all"))
        self.window.after(100, update_scroll)

    def _create_guide_section(self, parent, title, content_lines):
        """Create a collapsible section in the guide."""
        # Section header
        ttk.Separator(parent).pack(fill=X, pady=10)
        ttk.Label(parent, text=title, font=('Segoe UI', 11, 'bold')).pack(anchor=W, pady=(5, 10))

        # Content
        self._create_guide_content(parent, content_lines)

    def _create_guide_content(self, parent, content_lines):
        """Create content lines for a guide section."""
        for line in content_lines:
            if line == "":
                # Empty line for spacing
                ttk.Label(parent, text="").pack(anchor=W)
            elif line.startswith("  •"):
                # Bullet point with indent
                ttk.Label(parent, text=line, font=('Segoe UI', 9),
                         foreground='#cccccc').pack(anchor=W, padx=(20, 0))
            elif line.startswith("[") and line.endswith("]"):
                # Placeholder text (italic, gray)
                ttk.Label(parent, text=line, font=('Segoe UI', 9, 'italic'),
                         foreground='#666666').pack(anchor=W, padx=20, pady=5)
            else:
                # Normal text
                ttk.Label(parent, text=line, font=('Segoe UI', 9),
                         foreground='#aaaaaa').pack(anchor=W, padx=20)

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
        self.config.set_check_updates(self.updates_var.get())

        if self.on_save_callback:
            self.on_save_callback()

    def _restore_defaults(self):
        """Restore all settings to defaults (except API keys)."""
        # Restore default hotkeys
        # Only for default languages
        for lang, entry_var in self.hotkey_entries.items():
            default_hotkey = self.config.DEFAULT_HOTKEYS.get(lang, "")
            entry_var.set(default_hotkey)

        # Note: We don't delete custom rows here to avoid data loss,
        # but user can delete them manually.

        # Restore general settings
        self.autostart_var.set(False)
        self.updates_var.set(False)

    def _check_for_updates_click(self):
        """Handle Check for updates button click."""
        self.check_update_btn.config(state='disabled')
        self.update_status_label.config(text="Checking...")

        def check_async():
            try:
                result = check_for_updates()
                self.window.after(0, lambda: self._show_update_result(result))
            except Exception as e:
                self.window.after(0, lambda: self._show_update_result({'error': str(e)}))

        threading.Thread(target=check_async, daemon=True).start()

    def _show_update_result(self, result):
        """Show update check result."""
        self.check_update_btn.config(state='normal')

        if result.get('error'):
            self.update_status_label.config(text=f"Error: {result['error']}", foreground="#991700")
        elif result.get('available'):
            new_version = result['version']
            exe_url = result.get('exe_url')
            self.update_status_label.config(text=f"v{new_version} available!", foreground='green')

            # Store for later use
            self._pending_update = result

            # Check if auto-update is possible (exe version and exe_url available)
            is_exe = getattr(sys, 'frozen', False)

            if is_exe and exe_url:
                # Can auto-update
                if HAS_TTKBOOTSTRAP:
                    answer = Messagebox.yesno(
                        f"A new version v{new_version} is available!\n\n"
                        f"Current version: v{VERSION}\n\n"
                        f"Do you want to download and install the update?\n"
                        f"The application will restart automatically.",
                        title="Update Available",
                        parent=self.window
                    )
                    if answer == "Yes":
                        self._start_download_update(exe_url, new_version)
                else:
                    from tkinter import messagebox
                    answer = messagebox.askyesno(
                        "Update Available",
                        f"A new version v{new_version} is available!\n\n"
                        f"Current version: v{VERSION}\n\n"
                        f"Do you want to download and install the update?\n"
                        f"The application will restart automatically.",
                        parent=self.window
                    )
                    if answer:
                        self._start_download_update(exe_url, new_version)
            else:
                # Running from source or no exe in release - open download page
                msg = f"A new version v{new_version} is available!\n\nCurrent version: v{VERSION}\n\n"
                if not is_exe:
                    msg += "You're running from source code.\n"
                msg += "Do you want to open the download page?"

                if HAS_TTKBOOTSTRAP:
                    answer = Messagebox.yesno(msg, title="Update Available", parent=self.window)
                    if answer == "Yes":
                        webbrowser.open(result['url'])
                else:
                    from tkinter import messagebox
                    answer = messagebox.askyesno("Update Available", msg, parent=self.window)
                    if answer:
                        webbrowser.open(result['url'])
        else:
            self.update_status_label.config(text=f"You're up to date (v{VERSION})", foreground='gray')

    def _start_download_update(self, exe_url: str, new_version: str):
        """Start downloading the update with progress dialog."""
        # Create progress dialog
        self.progress_window = tk.Toplevel(self.window)
        self.progress_window.title("Downloading Update")
        self.progress_window.geometry("400x150")
        self.progress_window.resizable(False, False)
        self.progress_window.transient(self.window)
        self.progress_window.grab_set()

        # Center
        self.progress_window.update_idletasks()
        x = self.window.winfo_x() + (self.window.winfo_width() - 400) // 2
        y = self.window.winfo_y() + (self.window.winfo_height() - 150) // 2
        self.progress_window.geometry(f"+{x}+{y}")

        frame = ttk.Frame(self.progress_window, padding=20)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text=f"Downloading CrossTrans v{new_version}...",
                  font=('Segoe UI', 10, 'bold')).pack(anchor=W)

        self.progress_label = ttk.Label(frame, text="Starting download...")
        self.progress_label.pack(anchor=W, pady=(10, 5))

        if HAS_TTKBOOTSTRAP:
            self.progress_bar = ttk.Progressbar(frame, length=350, mode='determinate',
                                                 bootstyle="success-striped")
        else:
            self.progress_bar = ttk.Progressbar(frame, length=350, mode='determinate')
        self.progress_bar.pack(fill=X, pady=5)

        self.progress_percent = ttk.Label(frame, text="0%")
        self.progress_percent.pack(anchor='e')

        # Start download in thread
        def download_thread():
            def progress_callback(percent, downloaded, total):
                self.window.after(0, lambda: self._update_progress(percent, downloaded, total))

            result = download_and_install_update(exe_url, new_version, progress_callback)
            self.window.after(0, lambda: self._download_complete(result, new_version))

        threading.Thread(target=download_thread, daemon=True).start()

    def _update_progress(self, percent, downloaded, total):
        """Update progress bar."""
        if hasattr(self, 'progress_bar') and self.progress_window.winfo_exists():
            self.progress_bar['value'] = percent
            self.progress_percent.config(text=f"{percent}%")

            # Format size
            downloaded_mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            self.progress_label.config(text=f"Downloaded: {downloaded_mb:.1f} MB / {total_mb:.1f} MB")

    def _download_complete(self, result, new_version):
        """Handle download completion."""
        if hasattr(self, 'progress_window') and self.progress_window.winfo_exists():
            self.progress_window.destroy()

        if result.get('success'):
            # Ask to install now
            if HAS_TTKBOOTSTRAP:
                answer = Messagebox.yesno(
                    f"Download complete!\n\n"
                    f"CrossTrans v{new_version} is ready to install.\n\n"
                    f"The application will close and restart automatically.\n"
                    f"Install now?",
                    title="Install Update",
                    parent=self.window
                )
                if answer == "Yes":
                    self._execute_update(result['script_path'])
            else:
                from tkinter import messagebox
                answer = messagebox.askyesno(
                    "Install Update",
                    f"Download complete!\n\n"
                    f"CrossTrans v{new_version} is ready to install.\n\n"
                    f"The application will close and restart automatically.\n"
                    f"Install now?",
                    parent=self.window
                )
                if answer:
                    self._execute_update(result['script_path'])
        else:
            # Download failed
            error_msg = result.get('error', 'Unknown error')
            self.update_status_label.config(text="Download failed", foreground="#991700")

            if HAS_TTKBOOTSTRAP:
                Messagebox.show_error(
                    f"Failed to download update:\n\n{error_msg}\n\n"
                    f"Please try again or download manually from GitHub.",
                    title="Download Failed",
                    parent=self.window
                )
            else:
                from tkinter import messagebox
                messagebox.showerror(
                    "Download Failed",
                    f"Failed to download update:\n\n{error_msg}\n\n"
                    f"Please try again or download manually from GitHub.",
                    parent=self.window
                )

    def _execute_update(self, script_path: str):
        """Execute update and close application."""
        self.update_status_label.config(text="Installing update...", foreground='blue')

        # Close settings window
        self.window.destroy()

        # Execute update script (this will handle app restart)
        execute_update(script_path)

        # Exit the application - the batch script will restart it
        # Find the main app and quit
        try:
            # Get root window and quit
            root = self.window.master if hasattr(self, 'window') else None
            if root:
                root.after(500, lambda: os._exit(0))
            else:
                os._exit(0)
        except Exception:
            os._exit(0)  # Force exit even on error
