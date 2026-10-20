"""An update offer that never grabs input or takes keyboard focus."""
import tkinter as tk

try:
    import ttkbootstrap as ttk
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False


class UpdateNotice:
    def __init__(self, root, version, on_action):
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title('CrossTrans update')
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.window.protocol('WM_DELETE_WINDOW', lambda: self.choose('later'))
        self._on_action = on_action
        panel = ttk.Frame(self.window, padding=18, borderwidth=1, relief='solid')
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Update available', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        ttk.Label(panel, text=f'CrossTrans v{version} is ready to download.',
                  wraplength=340).pack(anchor='w', pady=(8, 4))
        ttk.Label(panel, text='Your work stays open until you choose to restart.',
                  wraplength=340).pack(anchor='w', pady=(0, 14))
        buttons = ttk.Frame(panel)
        buttons.pack(fill='x')
        self.buttons = {}
        for label, action in [('Update', 'update'), ('Later', 'later'),
                              ('Skip this version', 'skip')]:
            options = {}
            if HAS_TTKBOOTSTRAP:
                options['bootstyle'] = {'update': 'primary', 'later': 'light-outline',
                                        'skip': 'light-link'}[action]
            button = ttk.Button(buttons, text=label, command=lambda a=action: self.choose(a), **options)
            button.pack(side='left', padx=(0, 8))
            self.buttons[action] = button
        self.window.bind('<Escape>', lambda _event: self.choose('later'))
        self.window.update_idletasks()
        width = self.window.winfo_reqwidth()
        height = self.window.winfo_reqheight()
        left, top, right, bottom = self._work_area(root)
        x = max(left, right - width - 20)
        y = max(top, bottom - height - 20)
        self.window.geometry(f'{width}x{height}{x:+d}{y:+d}')
        self._prevent_activation()
        self.window.deiconify()

    def _prevent_activation(self):
        """Mapping a Toplevel can activate it on Windows even without focus_force."""
        try:
            import win32con
            import win32gui
            client = self.window.winfo_id()
            hwnd = win32gui.GetParent(client) or client
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                  style | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW)
        except (ImportError, OSError):
            pass

    @staticmethod
    def _work_area(root):
        try:
            import win32api
            monitor = win32api.MonitorFromPoint(root.winfo_pointerxy(), 2)
            return win32api.GetMonitorInfo(monitor)['Work']
        except Exception:
            return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight() - 60

    def choose(self, action):
        callback, self._on_action = self._on_action, None
        self.close()
        if callback:
            callback(action)

    def close(self):
        if self.window.winfo_exists():
            self.window.destroy()
