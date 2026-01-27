"""
Core modules for CrossTrans.
"""
from src.core.clipboard import ClipboardManager
from src.core.api_manager import AIAPIManager
from src.core.translation import TranslationService
from src.core.hotkey import HotkeyManager

__all__ = ['ClipboardManager', 'AIAPIManager', 'TranslationService', 'HotkeyManager']
