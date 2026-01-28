"""
Dialog windows for CrossTrans.
"""
import webbrowser

import tkinter as tk
from tkinter import BOTH, X, LEFT, RIGHT, W

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.dialogs import Messagebox
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False


class APIErrorDialog:
    """Professional error dialog for API key issues."""

    def __init__(self, parent, error_message: str = "", on_open_settings=None,
                 on_open_settings_tab=None):
        """Initialize API error dialog.

        Args:
            parent: Parent window
            error_message: Error message to display
            on_open_settings: Legacy callback for opening settings (no tab)
            on_open_settings_tab: Callback for opening settings at specific tab (tab_name: str)
        """
        self.on_open_settings = on_open_settings
        self.on_open_settings_tab = on_open_settings_tab

        self.window = tk.Toplevel(parent)
        self.window.title("API Key Error - CrossTrans")
        self.window.geometry("500x400")
        self.window.resizable(False, False)
        self.window.grab_set()

        # Center
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - 500) // 2
        y = (self.window.winfo_screenheight() - 400) // 2
        self.window.geometry(f"+{x}+{y}")

        self._create_widgets(error_message)

    def _create_widgets(self, error_message: str):
        """Create error dialog UI."""
        main = ttk.Frame(self.window, padding=25) if HAS_TTKBOOTSTRAP else ttk.Frame(self.window)
        main.pack(fill=BOTH, expand=True)

        # Warning icon and title
        if HAS_TTKBOOTSTRAP:
            ttk.Label(main, text="API Key Error", font=('Segoe UI', 16, 'bold'),
                      bootstyle="danger").pack(anchor=W)
        else:
            lbl = ttk.Label(main, text="API Key Error", font=('Segoe UI', 16, 'bold'))
            lbl.pack(anchor=W)

        ttk.Label(main, text="Your AI API key is not working or not configured.",
                  font=('Segoe UI', 10), wraplength=450).pack(anchor=W, pady=(10, 20))

        # Instructions
        ttk.Label(main, text="How to fix:", font=('Segoe UI', 11, 'bold')).pack(anchor=W)

        instructions = ttk.Frame(main)
        instructions.pack(fill=X, pady=10)

        ttk.Label(instructions, text="1. Get a free API key at:",
                  font=('Segoe UI', 10)).pack(anchor=W)
        if HAS_TTKBOOTSTRAP:
            ttk.Button(instructions, text="https://aistudio.google.com/app/apikey",
                       command=lambda: webbrowser.open("https://aistudio.google.com/app/apikey"),
                       bootstyle="link").pack(anchor=W, padx=(15, 0))
        else:
            ttk.Button(instructions, text="https://aistudio.google.com/app/apikey",
                       command=lambda: webbrowser.open("https://aistudio.google.com/app/apikey")).pack(anchor=W, padx=(15, 0))

        ttk.Label(instructions, text="\n2. Open Settings and enter your API key.",
                  font=('Segoe UI', 10)).pack(anchor=W)

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=X, pady=20)

        if self.on_open_settings:
            if HAS_TTKBOOTSTRAP:
                ttk.Button(btn_frame, text="Open Settings",
                           command=self._open_settings,
                           bootstyle="success", width=15).pack(side=LEFT)
            else:
                ttk.Button(btn_frame, text="Open Settings",
                           command=self._open_settings,
                           width=15).pack(side=LEFT)

        if HAS_TTKBOOTSTRAP:
            ttk.Button(btn_frame, text="Close", command=self.window.destroy,
                       bootstyle="secondary", width=15).pack(side=RIGHT)
        else:
            ttk.Button(btn_frame, text="Close", command=self.window.destroy,
                       width=15).pack(side=RIGHT)

    def _open_settings(self):
        """Open settings at API Key tab and close this dialog."""
        self.window.destroy()
        if self.on_open_settings_tab:
            self.on_open_settings_tab("API Key")
        elif self.on_open_settings:
            self.on_open_settings()


class TrialExhaustedDialog:
    """Dialog shown when trial quota is exhausted."""

    def __init__(self, parent, on_open_settings=None, on_open_settings_tab=None):
        """Initialize trial exhausted dialog.

        Args:
            parent: Parent window
            on_open_settings: Legacy callback for opening settings
            on_open_settings_tab: Callback for opening settings at specific tab
        """
        self.on_open_settings = on_open_settings
        self.on_open_settings_tab = on_open_settings_tab

        self.window = tk.Toplevel(parent)
        self.window.title("Trial Quota Exhausted - CrossTrans")
        self.window.geometry("500x350")
        self.window.resizable(False, False)
        self.window.grab_set()

        # Center
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - 500) // 2
        y = (self.window.winfo_screenheight() - 350) // 2
        self.window.geometry(f"+{x}+{y}")

        self._create_widgets()

    def _create_widgets(self):
        """Create dialog UI."""
        main = ttk.Frame(self.window, padding=25) if HAS_TTKBOOTSTRAP else ttk.Frame(self.window)
        main.pack(fill=BOTH, expand=True)

        # Title
        if HAS_TTKBOOTSTRAP:
            ttk.Label(main, text="Trial Quota Exhausted", font=('Segoe UI', 16, 'bold'),
                      bootstyle="warning").pack(anchor=W)
        else:
            ttk.Label(main, text="Trial Quota Exhausted", font=('Segoe UI', 16, 'bold')).pack(anchor=W)

        ttk.Label(main, text="You've used all 100 free translations for today.",
                  font=('Segoe UI', 10), wraplength=450).pack(anchor=W, pady=(10, 5))

        ttk.Label(main, text="Quota resets at midnight, or you can get unlimited access now.",
                  font=('Segoe UI', 10), wraplength=450).pack(anchor=W, pady=(0, 20))

        # Instructions
        ttk.Label(main, text="Get unlimited translations:", font=('Segoe UI', 11, 'bold')).pack(anchor=W)

        instructions = ttk.Frame(main)
        instructions.pack(fill=X, pady=10)

        ttk.Label(instructions, text="1. Get a FREE API key (takes 1 minute):",
                  font=('Segoe UI', 10)).pack(anchor=W)
        if HAS_TTKBOOTSTRAP:
            ttk.Button(instructions, text="https://aistudio.google.com/app/apikey",
                       command=lambda: webbrowser.open("https://aistudio.google.com/app/apikey"),
                       bootstyle="link").pack(anchor=W, padx=(15, 0))
        else:
            ttk.Button(instructions, text="https://aistudio.google.com/app/apikey",
                       command=lambda: webbrowser.open("https://aistudio.google.com/app/apikey")).pack(anchor=W, padx=(15, 0))

        ttk.Label(instructions, text="\n2. Paste your API key in Settings > API Key tab.",
                  font=('Segoe UI', 10)).pack(anchor=W)

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=X, pady=20)

        if self.on_open_settings:
            if HAS_TTKBOOTSTRAP:
                ttk.Button(btn_frame, text="Open Settings",
                           command=self._open_settings,
                           bootstyle="success", width=15).pack(side=LEFT)
            else:
                ttk.Button(btn_frame, text="Open Settings",
                           command=self._open_settings,
                           width=15).pack(side=LEFT)

        if HAS_TTKBOOTSTRAP:
            ttk.Button(btn_frame, text="Close", command=self.window.destroy,
                       bootstyle="secondary", width=15).pack(side=RIGHT)
        else:
            ttk.Button(btn_frame, text="Close", command=self.window.destroy,
                       width=15).pack(side=RIGHT)

    def _open_settings(self):
        """Open settings at API Key tab and close this dialog."""
        self.window.destroy()
        if self.on_open_settings_tab:
            self.on_open_settings_tab("API Key")
        elif self.on_open_settings:
            self.on_open_settings()


class TrialFeatureDialog:
    """Dialog shown when user tries to use a feature disabled in trial mode."""

    def __init__(self, parent, feature_name: str = "This feature", on_open_settings=None,
                 on_open_settings_tab=None):
        """Initialize trial feature dialog.

        Args:
            parent: Parent window
            feature_name: Name of the feature being accessed
            on_open_settings: Legacy callback for opening settings
            on_open_settings_tab: Callback for opening settings at specific tab
        """
        self.on_open_settings = on_open_settings
        self.on_open_settings_tab = on_open_settings_tab

        self.window = tk.Toplevel(parent)
        self.window.title("Feature Not Available - CrossTrans")
        self.window.geometry("480x360")
        self.window.resizable(False, False)
        self.window.grab_set()

        # Center
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - 480) // 2
        y = (self.window.winfo_screenheight() - 360) // 2
        self.window.geometry(f"+{x}+{y}")

        self._create_widgets(feature_name)

    def _create_widgets(self, feature_name: str):
        """Create dialog UI."""
        main = ttk.Frame(self.window, padding=25) if HAS_TTKBOOTSTRAP else ttk.Frame(self.window)
        main.pack(fill=BOTH, expand=True)

        # Title
        if HAS_TTKBOOTSTRAP:
            ttk.Label(main, text="Free Trial Mode", font=('Segoe UI', 16, 'bold'),
                      bootstyle="info").pack(anchor=W)
        else:
            ttk.Label(main, text="Free Trial Mode", font=('Segoe UI', 16, 'bold')).pack(anchor=W)

        ttk.Label(main, text=f"{feature_name} is not available in free trial mode.",
                  font=('Segoe UI', 10), wraplength=430).pack(anchor=W, pady=(10, 5))

        ttk.Label(main, text="Get a FREE API key to unlock all features:",
                  font=('Segoe UI', 10), wraplength=430).pack(anchor=W, pady=(0, 15))

        # Features list
        features_frame = ttk.Frame(main)
        features_frame.pack(fill=X, pady=5)

        ttk.Label(features_frame, text="  - Unlimited text translations", font=('Segoe UI', 10)).pack(anchor=W)
        ttk.Label(features_frame, text="  - File translation (PDF, DOCX, TXT, images)", font=('Segoe UI', 10)).pack(anchor=W)

        # Get API key link
        if HAS_TTKBOOTSTRAP:
            ttk.Button(main, text="Get FREE API Key (1 minute)",
                       command=lambda: webbrowser.open("https://aistudio.google.com/app/apikey"),
                       bootstyle="link").pack(anchor=W, pady=(10, 0))
        else:
            ttk.Button(main, text="Get FREE API Key (1 minute)",
                       command=lambda: webbrowser.open("https://aistudio.google.com/app/apikey")).pack(anchor=W, pady=(10, 0))

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=X, pady=(15, 0))

        if self.on_open_settings:
            if HAS_TTKBOOTSTRAP:
                ttk.Button(btn_frame, text="Open Settings",
                           command=self._open_settings,
                           bootstyle="success", width=15).pack(side=LEFT)
            else:
                ttk.Button(btn_frame, text="Open Settings",
                           command=self._open_settings,
                           width=15).pack(side=LEFT)

        if HAS_TTKBOOTSTRAP:
            ttk.Button(btn_frame, text="Close", command=self.window.destroy,
                       bootstyle="secondary", width=15).pack(side=RIGHT)
        else:
            ttk.Button(btn_frame, text="Close", command=self.window.destroy,
                       width=15).pack(side=RIGHT)

    def _open_settings(self):
        """Open settings at API Key tab and close this dialog."""
        self.window.destroy()
        if self.on_open_settings_tab:
            self.on_open_settings_tab("API Key")
        elif self.on_open_settings:
            self.on_open_settings()
