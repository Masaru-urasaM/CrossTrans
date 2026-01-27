"""
Hotkey Manager for CrossTrans.
Uses Windows RegisterHotKey API for global hotkey handling.
"""
import time
import ctypes
import logging
import threading
from ctypes import wintypes


class HotkeyManager(threading.Thread):
    """
    Manages global hotkeys using Windows RegisterHotKey API.

    Uses RegisterHotKey instead of low-level hooks for:
    - Instant response (no delay when holding modifier keys)
    - Selective suppression (only blocks the exact combo, not individual keys)
    - No conflict with system hotkeys like Win+Space
    - Zero CPU usage when idle (blocking GetMessageW)
    """

    # Windows API constants
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012
    MOD_ALT = 0x0001
    MOD_CTRL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    MOD_NOREPEAT = 0x4000

    # Virtual key codes for common keys
    VK_CODES = {
        'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45,
        'f': 0x46, 'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A,
        'k': 0x4B, 'l': 0x4C, 'm': 0x4D, 'n': 0x4E, 'o': 0x4F,
        'p': 0x50, 'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54,
        'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58, 'y': 0x59,
        'z': 0x5A,
        '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
        '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
        'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73, 'f5': 0x74,
        'f6': 0x75, 'f7': 0x76, 'f8': 0x77, 'f9': 0x78, 'f10': 0x79,
        'f11': 0x7A, 'f12': 0x7B,
        'space': 0x20, 'enter': 0x0D, 'tab': 0x09, 'escape': 0x1B,
        'backspace': 0x08, 'delete': 0x2E, 'insert': 0x2D,
        'home': 0x24, 'end': 0x23, 'pageup': 0x21, 'pagedown': 0x22,
        'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28,
    }

    # Modifier key mapping
    MOD_MAP = {
        'win': MOD_WIN,
        'windows': MOD_WIN,
        'alt': MOD_ALT,
        'ctrl': MOD_CTRL,
        'control': MOD_CTRL,
        'shift': MOD_SHIFT,
    }

    def __init__(self, config, callback):
        super().__init__(daemon=True)
        self.config = config
        self.callback = callback
        self._registered_ids = []
        self._hotkey_map = {}
        self._thread_id = None
        self._last_hotkey_time = 0
        self._hotkey_cooldown = 0.3
        self._running = False
        self._ready_event = threading.Event()

        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32

    def _parse_hotkey(self, combo: str) -> tuple:
        """Parse hotkey string like 'win+alt+v' into (modifiers, vk_code)."""
        parts = combo.lower().replace(' ', '').split('+')
        if len(parts) < 2:
            return None, None

        modifiers = self.MOD_NOREPEAT
        vk_code = None

        for part in parts:
            if part in self.MOD_MAP:
                modifiers |= self.MOD_MAP[part]
            elif part in self.VK_CODES:
                vk_code = self.VK_CODES[part]
            else:
                logging.warning(f"Unknown key in hotkey combo: {part}")
                return None, None

        if vk_code is None:
            logging.warning(f"No main key found in hotkey combo: {combo}")
            return None, None

        return modifiers, vk_code

    def register_hotkeys(self):
        """Register all configured hotkeys. Must be called from hotkey thread."""
        self._unregister_all_internal()

        hotkeys = self.config.get_hotkeys()
        custom_hotkeys = self.config.get_custom_hotkeys()
        all_hotkeys = {**hotkeys, **custom_hotkeys}

        hotkey_id = 1

        for language, combo in all_hotkeys.items():
            if not combo:
                continue

            modifiers, vk_code = self._parse_hotkey(combo)
            if modifiers is None or vk_code is None:
                logging.error(f"Failed to parse hotkey '{combo}' for {language}")
                continue

            result = self.user32.RegisterHotKey(None, hotkey_id, modifiers, vk_code)

            if result:
                self._registered_ids.append(hotkey_id)
                self._hotkey_map[hotkey_id] = language
                logging.info(f"Registered hotkey: {combo} -> {language} (ID: {hotkey_id})")
            else:
                error_code = self.kernel32.GetLastError()
                if error_code == 1409:
                    logging.warning(f"Hotkey '{combo}' already registered by another app")
                else:
                    logging.error(f"Failed to register hotkey '{combo}': error {error_code}")

            hotkey_id += 1

    def _unregister_all_internal(self):
        """Unregister all hotkeys (internal use)."""
        for hk_id in self._registered_ids:
            self.user32.UnregisterHotKey(None, hk_id)
        self._registered_ids.clear()
        self._hotkey_map.clear()

    def run(self):
        """Main thread loop. Registers hotkeys and processes Windows messages."""
        self._thread_id = self.kernel32.GetCurrentThreadId()
        self._running = True

        self.register_hotkeys()
        self._ready_event.set()

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hWnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt", wintypes.POINT),
            ]

        msg = MSG()
        logging.info("Hotkey message loop started")

        while self._running:
            result = self.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)

            if result == 0:
                logging.info("Received WM_QUIT, exiting message loop")
                break
            elif result < 0:
                logging.error("GetMessageW error")
                break

            if msg.message == self.WM_HOTKEY:
                hotkey_id = msg.wParam
                if hotkey_id in self._hotkey_map:
                    self._on_hotkey(self._hotkey_map[hotkey_id])

        self._unregister_all_internal()
        logging.info("Hotkey thread stopped")

    def _on_hotkey(self, language: str):
        """Handle hotkey press with debounce."""
        current_time = time.time()
        if current_time - self._last_hotkey_time < self._hotkey_cooldown:
            return

        self._last_hotkey_time = current_time
        logging.info(f"Hotkey triggered: {language}")

        threading.Thread(target=lambda: self.callback(language), daemon=True).start()

    def stop(self):
        """Stop the hotkey thread by posting WM_QUIT."""
        if self._thread_id and self._running:
            self._running = False
            self.user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)

    def unregister_all(self):
        """Re-register hotkeys (restart thread)."""
        if self._running and self._thread_id:
            self.stop()
            self.join(timeout=2.0)

            self._registered_ids = []
            self._hotkey_map = {}
            self._thread_id = None
            self._running = False
            self._ready_event.clear()

            threading.Thread.__init__(self, daemon=True)
            self.start()
            self._ready_event.wait(timeout=2.0)

    def cleanup(self):
        """Full cleanup - stop thread and unregister all hotkeys."""
        logging.info("Cleaning up hotkey manager...")
        self.stop()
        self.join(timeout=2.0)
