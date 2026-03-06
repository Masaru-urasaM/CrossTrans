"""
Dialog windows for CrossTrans.
"""
import webbrowser

from src.core.remote_config import get_config

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
            ttk.Label(main, text="⚠️ API Key Not Available", font=('Segoe UI', 16, 'bold'),
                      bootstyle="danger").pack(anchor=W)
        else:
            lbl = ttk.Label(main, text="⚠️ API Key Not Available", font=('Segoe UI', 16, 'bold'))
            lbl.pack(anchor=W)

        ttk.Label(main, text="No working API key found. Please try one of the following:",
                  font=('Segoe UI', 10), wraplength=450).pack(anchor=W, pady=(10, 15))

        # Instructions
        instructions = ttk.Frame(main)
        instructions.pack(fill=X, pady=5)

        # Option 1: Get API key
        ttk.Label(instructions, text="1. Get a free API key:",
                  font=('Segoe UI', 10, 'bold')).pack(anchor=W)
        ttk.Label(instructions, text="   Open Settings → Guide tab for instructions",
                  font=('Segoe UI', 10)).pack(anchor=W)

        # Option 2: Enable Trial Mode
        ttk.Label(instructions, text="\n2. Enable Trial Mode:",
                  font=('Segoe UI', 10, 'bold')).pack(anchor=W)
        ttk.Label(instructions, text=f"   Use shared API without your own key ({get_config().trial_daily_limit} requests/day)",
                  font=('Segoe UI', 10)).pack(anchor=W)
        ttk.Label(instructions, text="   Go to Settings → API Key → Enable Trial Mode",
                  font=('Segoe UI', 10), foreground='#888888').pack(anchor=W)

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=X, pady=20)

        if self.on_open_settings or self.on_open_settings_tab:
            if HAS_TTKBOOTSTRAP:
                ttk.Button(btn_frame, text="Open API Key Settings",
                           command=self._open_settings,
                           bootstyle="primary", width=20).pack(side=LEFT)
            else:
                ttk.Button(btn_frame, text="Open API Key Settings",
                           command=self._open_settings,
                           width=20).pack(side=LEFT)

        if HAS_TTKBOOTSTRAP:
            ttk.Button(btn_frame, text="Close", command=self.window.destroy,
                       bootstyle="secondary", width=10).pack(side=RIGHT)
        else:
            ttk.Button(btn_frame, text="Close", command=self.window.destroy,
                       width=10).pack(side=RIGHT)

        # Trial mode tip
        tip_frame = ttk.Frame(main)
        tip_frame.pack(fill=X, pady=(10, 0))
        ttk.Label(tip_frame, text="💡 Tip: Trial Mode is great for trying the app before getting your own API key",
                  font=('Segoe UI', 9, 'italic'), foreground='#4da6ff', wraplength=450).pack(anchor=W)

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

        ttk.Label(main, text=f"You've used all {get_config().trial_daily_limit} free translations for today.",
                  font=('Segoe UI', 10), wraplength=450).pack(anchor=W, pady=(10, 5))

        ttk.Label(main, text="Quota resets at midnight, or you can get unlimited access now.",
                  font=('Segoe UI', 10), wraplength=450).pack(anchor=W, pady=(0, 20))

        # Instructions
        ttk.Label(main, text="Get unlimited translations:", font=('Segoe UI', 11, 'bold')).pack(anchor=W)

        instructions = ttk.Frame(main)
        instructions.pack(fill=X, pady=10)

        ttk.Label(instructions, text="1. Get a FREE API key:",
                  font=('Segoe UI', 10)).pack(anchor=W)
        ttk.Label(instructions, text="   Open Settings → Guide tab for instructions",
                  font=('Segoe UI', 10), foreground='#888888').pack(anchor=W, padx=(15, 0))

        ttk.Label(instructions, text="\n2. Paste your API key in Settings > API Key tab.",
                  font=('Segoe UI', 10)).pack(anchor=W)

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=X, pady=20)

        if self.on_open_settings or self.on_open_settings_tab:
            if HAS_TTKBOOTSTRAP:
                ttk.Button(btn_frame, text="Open API Key Settings",
                           command=self._open_settings,
                           bootstyle="success", width=20).pack(side=LEFT)
            else:
                ttk.Button(btn_frame, text="Open API Key Settings",
                           command=self._open_settings,
                           width=20).pack(side=LEFT)

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

        # Get API key guidance
        ttk.Label(main, text="Open Settings → Guide tab for API key instructions",
                  font=('Segoe UI', 10), foreground='#888888').pack(anchor=W, pady=(10, 0))

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=X, pady=(15, 0))

        if self.on_open_settings or self.on_open_settings_tab:
            if HAS_TTKBOOTSTRAP:
                ttk.Button(btn_frame, text="Open API Key Settings",
                           command=self._open_settings,
                           bootstyle="success", width=20).pack(side=LEFT)
            else:
                ttk.Button(btn_frame, text="Open API Key Settings",
                           command=self._open_settings,
                           width=20).pack(side=LEFT)

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


class UpdateFailedDialog:
    """Dialog shown when auto-update fails, offering reboot fallback.

    Provides options:
    1. Schedule update for next Windows restart (MoveFileEx fallback)
    2. Download manually from GitHub
    3. Skip for now

    The result is stored in self.result:
    - 'reboot': User chose to schedule for restart
    - 'manual': User wants to download manually
    - 'cancel': User dismissed the dialog
    """

    def __init__(self, parent, error_msg: str, pending_path: str = None,
                 current_exe: str = None):
        """Initialize update failed dialog.

        Args:
            parent: Parent window
            error_msg: Error message from the failed update
            pending_path: Path to the pending update file (for MoveFileEx fallback)
            current_exe: Path to the current executable
        """
        self.result = 'cancel'
        self.pending_path = pending_path
        self.current_exe = current_exe

        self.window = tk.Toplevel(parent)
        self.window.title("Update Failed - CrossTrans")
        self.window.geometry("500x380")
        self.window.resizable(False, False)
        self.window.grab_set()

        # Make modal
        self.window.transient(parent)

        # Center
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - 500) // 2
        y = (self.window.winfo_screenheight() - 380) // 2
        self.window.geometry(f"+{x}+{y}")

        self._create_update_failed_widgets(error_msg)

        # Wait for dialog to close
        self.window.wait_window()

    def _create_update_failed_widgets(self, error_msg: str):
        """Create dialog UI for update failed."""
        main = ttk.Frame(self.window, padding=25) if HAS_TTKBOOTSTRAP else ttk.Frame(self.window)
        main.pack(fill=BOTH, expand=True)

        # Title
        if HAS_TTKBOOTSTRAP:
            ttk.Label(main, text="Update Installation Failed",
                      font=('Segoe UI', 14, 'bold'),
                      bootstyle="warning").pack(anchor=W)
        else:
            ttk.Label(main, text="Update Installation Failed",
                      font=('Segoe UI', 14, 'bold')).pack(anchor=W)

        # Error message
        error_frame = ttk.Frame(main)
        error_frame.pack(fill=X, pady=(15, 10))

        ttk.Label(error_frame, text="The update could not be installed:",
                  font=('Segoe UI', 10)).pack(anchor=W)

        # Error details
        error_box = ttk.Frame(error_frame)
        error_box.pack(fill=X, pady=(5, 0), padx=(10, 0))

        ttk.Label(error_box, text=error_msg, font=('Consolas', 9),
                  foreground='#ff6b6b', wraplength=440).pack(anchor=W)

        # Options section
        ttk.Label(main, text="\nChoose how to proceed:",
                  font=('Segoe UI', 10, 'bold')).pack(anchor=W, pady=(10, 5))

        options_frame = ttk.Frame(main)
        options_frame.pack(fill=X, pady=5)

        # Option selection variable
        self.option_var = tk.StringVar(value='reboot' if self.pending_path else 'manual')

        # Option 1: Schedule for restart (only if pending file exists)
        if self.pending_path:
            opt1_frame = ttk.Frame(options_frame)
            opt1_frame.pack(fill=X, pady=3)
            ttk.Radiobutton(opt1_frame, text="Schedule update for next Windows restart",
                            variable=self.option_var, value='reboot').pack(anchor=W)
            ttk.Label(opt1_frame, text="     (Guaranteed - Windows applies update at boot)",
                      font=('Segoe UI', 9), foreground='#888888').pack(anchor=W)

        # Option 2: Download manually
        opt2_frame = ttk.Frame(options_frame)
        opt2_frame.pack(fill=X, pady=3)
        ttk.Radiobutton(opt2_frame, text="Download manually from GitHub",
                        variable=self.option_var, value='manual').pack(anchor=W)
        ttk.Label(opt2_frame, text="     (Opens the releases page in your browser)",
                  font=('Segoe UI', 9), foreground='#888888').pack(anchor=W)

        # Option 3: Skip
        opt3_frame = ttk.Frame(options_frame)
        opt3_frame.pack(fill=X, pady=3)
        ttk.Radiobutton(opt3_frame, text="Skip for now",
                        variable=self.option_var, value='cancel').pack(anchor=W)
        ttk.Label(opt3_frame, text="     (You can try updating again from Settings)",
                  font=('Segoe UI', 9), foreground='#888888').pack(anchor=W)

        # Buttons
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=X, pady=(20, 0))

        if HAS_TTKBOOTSTRAP:
            ttk.Button(btn_frame, text="Continue", command=self._on_update_continue,
                       bootstyle="primary", width=15).pack(side=LEFT)
            ttk.Button(btn_frame, text="Cancel", command=self._on_update_cancel,
                       bootstyle="secondary", width=15).pack(side=RIGHT)
        else:
            ttk.Button(btn_frame, text="Continue", command=self._on_update_continue,
                       width=15).pack(side=LEFT)
            ttk.Button(btn_frame, text="Cancel", command=self._on_update_cancel,
                       width=15).pack(side=RIGHT)

        # Log file tip
        tip_frame = ttk.Frame(main)
        tip_frame.pack(fill=X, pady=(15, 0))
        ttk.Label(tip_frame,
                  text="Tip: Check %TEMP%\\crosstrans_update.log for details",
                  font=('Segoe UI', 8, 'italic'),
                  foreground='#666666').pack(anchor=W)

    def _on_update_continue(self):
        """Handle continue button click."""
        self.result = self.option_var.get()
        self.window.destroy()

    def _on_update_cancel(self):
        """Handle cancel button click."""
        self.result = 'cancel'
        self.window.destroy()
