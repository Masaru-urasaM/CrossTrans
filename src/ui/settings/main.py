"""
Main Settings Window - Composes all tab mixins into the final SettingsWindow class.
"""
import logging
import tkinter as tk
from tkinter import BOTH, X, RIGHT

try:
    import ttkbootstrap as ttk
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.utils.updates import AutoUpdater
from src.ui.settings.widgets import set_dark_title_bar
from src.ui.settings.api_tab import APITabMixin
from src.ui.settings.hotkey_tab import HotkeyTabMixin
from src.ui.settings.general_tab import GeneralTabMixin
from src.ui.settings.dictionary_tab import DictionaryTabMixin
from src.ui.settings.guide_tab import GuideTabMixin
from src.ui.settings.update_manager import UpdateManagerMixin


class SettingsWindow(
    APITabMixin,
    HotkeyTabMixin,
    GeneralTabMixin,
    DictionaryTabMixin,
    GuideTabMixin,
    UpdateManagerMixin
):
    """Settings dialog for configuring the application.

    This class uses mixins to organize functionality by tab:
    - APITabMixin: API Key tab with provider management and testing
    - HotkeyTabMixin: Hotkeys tab with keyboard shortcut configuration
    - GeneralTabMixin: General settings tab with autostart and updates
    - DictionaryTabMixin: Dictionary/NLP tab with language pack management
    - GuideTabMixin: User guide tab with help documentation
    - UpdateManagerMixin: Update checking and downloading functionality
    """

    def __init__(self, parent, config, on_save_callback=None, on_api_change_callback=None):
        """Initialize the Settings window.

        Args:
            parent: Parent tkinter window
            config: Configuration object for reading/writing settings
            on_save_callback: Optional callback when settings are saved
            on_api_change_callback: Optional callback when API keys change (for trial mode)
        """
        self.config = config
        self.on_save_callback = on_save_callback
        self.on_api_change_callback = on_api_change_callback
        self.hotkey_entries = {}
        self.custom_rows = []
        self.api_rows = []
        self.recording_language = None
        self.updater = AutoUpdater()

        # Lazy loading: Track which tabs have been loaded
        self._tab_loaded = {
            'general': False,
            'hotkeys': False,
            'api': False,
            'dictionary': False,
            'guide': False
        }
        self._tab_frames = {}  # Store frame references

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
            logging.exception(f"Error creating settings widgets: {e}")

    def _create_widgets(self):
        """Create settings UI with lazy-loaded tabs for fast startup."""
        if HAS_TTKBOOTSTRAP:
            notebook = ttk.Notebook(self.window, bootstyle="dark")
        else:
            notebook = ttk.Notebook(self.window)
        notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)
        self.notebook = notebook

        # Create all 5 empty frames immediately (fast)
        tab_configs = [
            ('general', "  General  "),
            ('hotkeys', "  Hotkeys  "),
            ('api', "  API Key  "),
            ('dictionary', "  Dictionary  "),
            ('guide', "  Guide  ")
        ]

        for tab_name, tab_text in tab_configs:
            frame = ttk.Frame(notebook, padding=20) if HAS_TTKBOOTSTRAP else ttk.Frame(notebook)
            notebook.add(frame, text=tab_text)
            self._tab_frames[tab_name] = frame

        # Load General and Hotkeys immediately (they're fast, ~50ms each)
        self._create_general_tab(self._tab_frames['general'])
        self._tab_loaded['general'] = True

        self._create_hotkey_tab(self._tab_frames['hotkeys'])
        self._tab_loaded['hotkeys'] = True

        # Show placeholders for heavy tabs (API, Dictionary, Guide)
        for tab_name in ['api', 'dictionary', 'guide']:
            self._create_tab_placeholder(self._tab_frames[tab_name])

        # Bind tab change event for lazy loading
        notebook.bind('<<NotebookTabChanged>>', self._on_tab_changed)

        # Close button only (auto-save handles all saves)
        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(fill=X, padx=10, pady=(0, 10))

        if HAS_TTKBOOTSTRAP:
            ttk.Button(btn_frame, text="Close", command=self.window.destroy,
                       bootstyle="secondary", width=15).pack(side=RIGHT)
        else:
            ttk.Button(btn_frame, text="Close", command=self.window.destroy,
                       width=15).pack(side=RIGHT)

    def _create_tab_placeholder(self, parent):
        """Show loading indicator in unloaded tab."""
        placeholder = ttk.Frame(parent)
        placeholder.pack(expand=True)
        ttk.Label(placeholder, text="Loading...",
                  font=('Segoe UI', 11)).pack()
        parent._placeholder = placeholder

    def _on_tab_changed(self, event):
        """Load tab content on first access (lazy loading)."""
        try:
            tab_id = self.notebook.select()
            tab_index = self.notebook.index(tab_id)

            tab_map = {
                0: ('general', self._create_general_tab),
                1: ('hotkeys', self._create_hotkey_tab),
                2: ('api', self._create_api_tab),
                3: ('dictionary', self._create_dictionary_tab),
                4: ('guide', self._create_guide_tab)
            }

            tab_name, create_func = tab_map.get(tab_index, (None, None))

            if tab_name and not self._tab_loaded.get(tab_name):
                frame = self._tab_frames[tab_name]

                # Clear placeholder
                if hasattr(frame, '_placeholder'):
                    frame._placeholder.destroy()
                    delattr(frame, '_placeholder')

                # Load content
                try:
                    create_func(frame)
                    self._tab_loaded[tab_name] = True
                    logging.debug(f"Lazy loaded {tab_name} tab")
                except Exception as e:
                    logging.error(f"Failed to load {tab_name} tab: {e}")
                    import traceback
                    traceback.print_exc()
                    ttk.Label(frame, text=f"Error loading tab: {e}",
                             foreground='#ff6b6b').pack()
        except Exception as e:
            logging.error(f"Tab change handler error: {e}")
