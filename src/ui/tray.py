"""
System Tray Manager for CrossTrans.
Handles system tray icon and menu.
"""
import webbrowser
from typing import Callable, Dict, Optional

from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw

from src.constants import VERSION, FEEDBACK_URL


class TrayManager:
    """Manages system tray icon and menu."""

    def __init__(self, config):
        """Initialize tray manager.

        Args:
            config: Config object for reading hotkey settings
        """
        self.config = config
        self.tray_icon: Optional[Icon] = None

        # Callbacks
        self._on_show_main_window: Optional[Callable[[], None]] = None
        self._on_show_settings: Optional[Callable[[], None]] = None
        self._on_quit: Optional[Callable[[], None]] = None

    def configure_callbacks(self,
                            on_show_main_window: Optional[Callable[[], None]] = None,
                            on_show_settings: Optional[Callable[[], None]] = None,
                            on_quit: Optional[Callable[[], None]] = None):
        """Configure callback functions for tray menu actions.

        Args:
            on_show_main_window: Called when user clicks Open Translator
            on_show_settings: Called when user clicks Settings
            on_quit: Called when user clicks Quit
        """
        self._on_show_main_window = on_show_main_window
        self._on_show_settings = on_show_settings
        self._on_quit = on_quit

    def _create_icon_image(self) -> Image.Image:
        """Create the tray icon image.

        Returns:
            PIL Image for the tray icon
        """
        image = Image.new('RGB', (64, 64), color='#0d6efd')
        draw = ImageDraw.Draw(image)
        draw.text((18, 18), "T", fill='white')
        return image

    def _build_menu_items(self) -> list:
        """Build menu items list from config.

        Returns:
            List of MenuItem objects
        """
        menu_items = [
            MenuItem('Open Translator', lambda: self._on_show_main_window() if self._on_show_main_window else None, default=True),
            MenuItem('Settings', lambda: self._on_show_settings() if self._on_show_settings else None),
            MenuItem('\u2500' * 13, lambda: None, enabled=False),
        ]

        # Add all hotkeys (default + custom) from config
        all_hotkeys = self.config.get_all_hotkeys()
        for language, hotkey in all_hotkeys.items():
            # Format hotkey for display (e.g., "win+alt+v" -> "Win+Alt+V")
            display_hotkey = '+'.join(part.capitalize() for part in hotkey.split('+'))
            menu_items.append(
                MenuItem(f'{display_hotkey} \u2192 {language}', lambda: None, enabled=False)
            )

        menu_items.extend([
            MenuItem('\u2500' * 13, lambda: None, enabled=False),
            MenuItem('Send Feedback', lambda: webbrowser.open(FEEDBACK_URL)),
            MenuItem('Quit', lambda: self._on_quit() if self._on_quit else None)
        ])

        return menu_items

    def create(self) -> Icon:
        """Create and return the system tray icon.

        Returns:
            The pystray Icon object
        """
        image = self._create_icon_image()
        menu_items = self._build_menu_items()
        menu = Menu(*menu_items)

        self.tray_icon = Icon("CrossTrans", image,
                              f"CrossTrans v{VERSION}", menu)
        return self.tray_icon

    def refresh_menu(self):
        """Refresh tray menu to reflect updated hotkeys."""
        if self.tray_icon:
            menu_items = self._build_menu_items()
            self.tray_icon.menu = Menu(*menu_items)

    def stop(self):
        """Stop and cleanup the tray icon."""
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
            self.tray_icon = None
