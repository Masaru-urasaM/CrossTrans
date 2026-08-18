"""
Configuration management for CrossTrans.
Handles API key, hotkeys, auto-start settings, and other preferences.
"""
import os
import sys
import json
import shutil
import logging
import winreg
from typing import Optional, Dict, Any, List

from src.core.crypto import SecureStorage


class Config:
    """Manages application configuration stored in %APPDATA%/CrossTrans/config.json"""

    APP_NAME = "CrossTrans"
    CONFIG_DIR = os.path.join(os.environ.get('APPDATA', '.'), APP_NAME)
    CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

    DEFAULT_HOTKEYS = {
        "Vietnamese": "win+alt+v",
        "English": "win+alt+e",
        "Japanese": "win+alt+j",
        "Chinese Simplified": "win+alt+c"
    }

    # Screenshot hotkey (for vision/OCR translation)
    SCREENSHOT_HOTKEY_DEFAULT = "win+alt+s"
    SCREENSHOT_TARGET_LANGUAGE_DEFAULT = "Auto"  # "Auto" = use current selected_language

    # Fix Grammar hotkey (corrects grammar of selected text without translating)
    # NOTE: Win+Alt+G is also Xbox Game Bar's "Record that" default. Registration fails
    # gracefully (error 1409) if Game Bar has it; the hotkey is rebindable and the
    # main-window "Fix Grammar" button always works as a fallback.
    FIX_GRAMMAR_HOTKEY_DEFAULT = "win+alt+g"

    # Languages that can be added as custom hotkeys
    DEFAULT_LANGUAGES = ["Vietnamese", "English", "Japanese", "Chinese Simplified"]
    MAX_CUSTOM_HOTKEYS = 4  # Max 4 additional custom hotkeys

    DEFAULT_CONFIG = {
        "api_keys": [],  # List of {model_name, api_key, provider, vision_capable, file_capable} dicts
        "hotkeys": DEFAULT_HOTKEYS.copy(),
        "custom_hotkeys": {},  # Custom language hotkeys (max 4)
        "screenshot_hotkey": SCREENSHOT_HOTKEY_DEFAULT,  # Screenshot OCR hotkey
        "screenshot_target_language": SCREENSHOT_TARGET_LANGUAGE_DEFAULT,  # Target language for screenshot OCR
        "fix_grammar_hotkey": FIX_GRAMMAR_HOTKEY_DEFAULT,  # Hotkey to fix grammar of selected text
        "fix_grammar_enabled": True,  # Enable Fix Grammar main-window button
        "fix_grammar_hotkey_enabled": False,  # Register global Win+Alt+G hotkey (off by default - collides with Xbox Game Bar; the button + language hotkeys always work)
        "autostart": False,
        "check_updates": False,  # Default to False
        "theme": "darkly",
        "history": [],
        "history_enabled": True,
        # Note: vision_enabled and file_processing_enabled are now auto-managed
        # based on API capabilities detected during testing
        "vision_enabled": False,
        "file_processing_enabled": False,
        # Provider health tracking for smart fallback
        "provider_health": {},
        # NLP language packs for Dictionary mode
        "nlp_installed": [],  # List of installed language names (e.g., ["Vietnamese", "English"])
        "nlp_basic_mode": [],  # Languages using basic (whitespace) tokenization as fallback
        # Trial mode settings
        "trial_mode_forced": False,  # User manually enabled trial mode
        "trial_last_api_check": "",  # ISO datetime of last API check
        # Version tracking for cache clearing
        "last_run_version": None,  # Track version to detect upgrades
        # Replace mode setting
        "quick_replace": False,  # False = Manual Replace (preview), True = Quick Replace (immediate)
        "model_rotation": False,  # Try other models before switching keys on failure
        "furigana_enabled": True,  # Show furigana (reading guides) for Japanese source text
        "furigana_reading_pane": True,  # Reading pane under the main-window input box
    }

    def __init__(self):
        self._config: Dict[str, Any] = {}
        self.api_status_cache: Dict[str, bool] = {}
        self.runtime_capabilities: Dict[str, bool] = {'vision': False, 'file': False}
        self._ensure_config_dir()
        self.load()

    def _ensure_config_dir(self):
        """Create config directory if it doesn't exist."""
        if not os.path.exists(self.CONFIG_DIR):
            os.makedirs(self.CONFIG_DIR)

    def load(self) -> Dict[str, Any]:
        """Load configuration from file."""
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._config = self.DEFAULT_CONFIG.copy()
        else:
            self._config = self.DEFAULT_CONFIG.copy()

        # Merge with defaults for any missing keys
        for key, value in self.DEFAULT_CONFIG.items():
            if key not in self._config:
                self._config[key] = value

        # Migration: Encrypt plaintext API keys if DPAPI is available
        self._migrate_plaintext_keys()

        return self._config

    def _migrate_plaintext_keys(self) -> None:
        """Migrate plaintext API keys to encrypted format."""
        if not SecureStorage.is_available():
            return

        # Check if already migrated
        if self._config.get('encryption_version', 0) >= 1:
            return

        api_keys = self._config.get('api_keys', [])
        needs_migration = False

        for key_config in api_keys:
            # Check for plaintext api_key that needs encryption
            if 'api_key' in key_config and 'api_key_encrypted' not in key_config:
                needs_migration = True
                break

        if needs_migration:
            logging.info("Migrating plaintext API keys to encrypted storage...")

            # Backup config before migration
            backup_file = self.CONFIG_FILE + '.backup'
            try:
                shutil.copy2(self.CONFIG_FILE, backup_file)
                logging.info(f"Config backup saved to: {backup_file}")
            except Exception as e:
                logging.warning(f"Failed to create backup: {e}")

            # Re-save with encryption (get_api_keys decrypts, set_api_keys encrypts)
            current_keys = self.get_api_keys()
            self.set_api_keys(current_keys)

    def save(self, secure: bool = False):
        """Save configuration to file."""
        self._ensure_config_dir()
        
        # Secure overwrite: write zeros to the file before truncating if secure delete is requested
        if secure and os.path.exists(self.CONFIG_FILE):
            try:
                file_size = os.path.getsize(self.CONFIG_FILE)
                with open(self.CONFIG_FILE, "rb+") as f:
                    f.write(b"\0" * file_size)
                    f.flush()
                    os.fsync(f.fileno())
            except Exception:
                pass

        with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno()) # Force write to disk immediately

    # API Key management
    def get_api_keys(self) -> List[Dict[str, Any]]:
        """Get all API keys with their models (decrypted).
        Returns list of dicts: [{model_name, api_key, provider, vision_capable, file_capable}, ...]
        """
        # If 'api_keys' is explicitly set (even empty), process it
        if 'api_keys' in self._config:
            api_keys = []
            for key_config in self._config['api_keys']:
                decrypted_config = key_config.copy()

                # Check for encrypted key
                if 'api_key_encrypted' in key_config:
                    decrypted = SecureStorage.decrypt(key_config['api_key_encrypted'])
                    if decrypted:
                        decrypted_config['api_key'] = decrypted
                    else:
                        # Decryption failed - maybe different user/machine
                        decrypted_config['api_key'] = ''
                        logging.warning("Failed to decrypt API key - may need to re-enter")
                    # Remove encrypted key from returned dict
                    decrypted_config.pop('api_key_encrypted', None)

                api_keys.append(decrypted_config)
            return api_keys

        # Migration: Check for old singular keys if list is missing
        api_keys = []
        primary = self._config.get('api_key')
        if primary:
            api_keys.append({'model_name': '', 'api_key': primary})
        backup = self._config.get('backup_api_key')
        if backup:
            api_keys.append({'model_name': '', 'api_key': backup})

        return api_keys

    def set_api_keys(self, api_keys: List[Dict[str, Any]], secure: bool = False) -> None:
        """Set all API keys with their models (encrypted with DPAPI).
        api_keys: list of dicts [{model_name, api_key, provider}, ...]
        """
        encrypted_keys = []
        for key_config in api_keys:
            encrypted_config = key_config.copy()

            # Encrypt the API key if DPAPI is available
            if 'api_key' in key_config and key_config['api_key']:
                encrypted = SecureStorage.encrypt(key_config['api_key'])
                if encrypted:
                    encrypted_config['api_key_encrypted'] = encrypted
                    encrypted_config.pop('api_key', None)  # Remove plaintext
                # If encryption fails, keep plaintext as fallback

            encrypted_keys.append(encrypted_config)

        self._config['api_keys'] = encrypted_keys
        self._config['encryption_version'] = 1  # Track encryption format
        self.save(secure=secure)

    def get_api_key(self) -> str:
        """Get first API key (for backward compatibility)."""
        api_keys = self.get_api_keys()
        if api_keys:
            return api_keys[0]['api_key']
        
        # Fallback to environment variable (system level only)
        api_key = os.environ.get('GEMINI_API_KEY')
        if api_key:
            return api_key
        return ""

    def set_api_key(self, api_key: str, model_name: str = "gemini-2.0-flash-lite"):
        """Set first API key with model."""
        api_keys = self.get_api_keys()
        if api_keys:
            api_keys[0] = {'model_name': model_name, 'api_key': api_key}
        else:
            api_keys = [{'model_name': model_name, 'api_key': api_key}]
        self.set_api_keys(api_keys)

    def _get_app_dir(self) -> str:
        """Get the directory where the exe/script is located."""
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    # Hotkeys management
    def get_hotkeys(self) -> Dict[str, str]:
        """Get hotkey configuration."""
        return self._config.get('hotkeys', self.DEFAULT_HOTKEYS.copy())

    def set_hotkeys(self, hotkeys: Dict[str, str]):
        """Set hotkey configuration."""
        self._config['hotkeys'] = hotkeys
        self.save()

    def set_hotkey(self, language: str, hotkey: str):
        """Set hotkey for a specific language."""
        if 'hotkeys' not in self._config:
            self._config['hotkeys'] = self.DEFAULT_HOTKEYS.copy()
        self._config['hotkeys'][language] = hotkey
        self.save()

    def remove_hotkey(self, language: str):
        """Remove hotkey for a specific language."""
        if 'hotkeys' in self._config and language in self._config['hotkeys']:
            del self._config['hotkeys'][language]
            self.save()

    # Custom hotkeys management
    def get_custom_hotkeys(self) -> Dict[str, str]:
        """Get custom hotkey configuration."""
        return self._config.get('custom_hotkeys', {})

    def set_custom_hotkey(self, language: str, hotkey: str):
        """Set a custom hotkey for a language."""
        if 'custom_hotkeys' not in self._config:
            self._config['custom_hotkeys'] = {}
        if len(self._config['custom_hotkeys']) < self.MAX_CUSTOM_HOTKEYS or language in self._config['custom_hotkeys']:
            self._config['custom_hotkeys'][language] = hotkey
            self.save()

    def remove_custom_hotkey(self, language: str):
        """Remove a custom hotkey."""
        if 'custom_hotkeys' in self._config and language in self._config['custom_hotkeys']:
            del self._config['custom_hotkeys'][language]
            self.save()

    def get_all_hotkeys(self) -> Dict[str, str]:
        """Get all hotkeys (default + custom)."""
        all_hotkeys = self.get_hotkeys().copy()
        all_hotkeys.update(self.get_custom_hotkeys())
        return all_hotkeys

    # Screenshot hotkey management
    def get_screenshot_hotkey(self) -> str:
        """Get screenshot hotkey combination for vision/OCR translation."""
        return self._config.get('screenshot_hotkey', self.SCREENSHOT_HOTKEY_DEFAULT)

    def set_screenshot_hotkey(self, hotkey: str):
        """Set screenshot hotkey combination."""
        self._config['screenshot_hotkey'] = hotkey
        self.save()

    def get_screenshot_target_language(self) -> str:
        """Get target language for screenshot translation.

        Returns:
            Language name or "Auto" to use current selected language
        """
        return self._config.get('screenshot_target_language', self.SCREENSHOT_TARGET_LANGUAGE_DEFAULT)

    def set_screenshot_target_language(self, language: str):
        """Set target language for screenshot translation."""
        self._config['screenshot_target_language'] = language
        self.save()

    # Replace mode setting
    def get_quick_replace(self) -> bool:
        """Get whether Quick Replace mode is enabled."""
        return self._config.get('quick_replace', False)

    def set_quick_replace(self, enabled: bool):
        """Set Quick Replace mode."""
        self._config['quick_replace'] = enabled
        self.save()

    # Model rotation setting
    def get_model_rotation(self) -> bool:
        """Get whether model rotation on quota failure is enabled."""
        return self._config.get('model_rotation', False)

    def set_model_rotation(self, enabled: bool):
        """Set model rotation on quota failure."""
        self._config['model_rotation'] = enabled
        self.save()

    # Furigana setting
    def get_furigana_enabled(self) -> bool:
        """Get whether furigana (reading guides) is enabled for Japanese text.

        Defaults to True to match DEFAULT_CONFIG: the fallback only applies to a
        config file written before this key existed, and those users should get
        the documented default rather than the feature silently switched off.
        """
        return self._config.get('furigana_enabled', True)

    def set_furigana_enabled(self, enabled: bool):
        """Set furigana mode for Japanese text."""
        self._config['furigana_enabled'] = enabled
        self.save()

    def get_furigana_reading_pane(self) -> bool:
        """Get whether the main window's Reading pane is expanded.

        Only the user's collapse choice, not a feature switch: the pane exists
        whenever furigana is enabled. Defaults to True (expanded) so the
        readings are visible without anyone having to find the toggle.
        """
        return self._config.get('furigana_reading_pane', True)

    def set_furigana_reading_pane(self, expanded: bool):
        """Remember whether the Reading pane is expanded."""
        self._config['furigana_reading_pane'] = expanded
        self.save()

    # Fix Grammar settings
    def get_fix_grammar_hotkey(self) -> str:
        """Get the Fix Grammar hotkey combination."""
        return self._config.get('fix_grammar_hotkey', self.FIX_GRAMMAR_HOTKEY_DEFAULT)

    def set_fix_grammar_hotkey(self, hotkey: str):
        """Set the Fix Grammar hotkey combination."""
        self._config['fix_grammar_hotkey'] = hotkey
        self.save()

    def get_fix_grammar_enabled(self) -> bool:
        """Get whether the Fix Grammar main-window button is shown."""
        return self._config.get('fix_grammar_enabled', True)

    def set_fix_grammar_enabled(self, enabled: bool):
        """Set whether the Fix Grammar main-window button is shown."""
        self._config['fix_grammar_enabled'] = enabled
        self.save()

    def get_fix_grammar_hotkey_enabled(self) -> bool:
        """Get whether the global Win+Alt+G Fix Grammar hotkey is registered.

        Separate from get_fix_grammar_enabled() (the main-window button). Off by default
        because Win+Alt+G collides with Xbox Game Bar; the button and the language
        hotkeys' merged translate-or-fix always work regardless.
        """
        return self._config.get('fix_grammar_hotkey_enabled', False)

    def set_fix_grammar_hotkey_enabled(self, enabled: bool):
        """Set whether the global Win+Alt+G Fix Grammar hotkey is registered."""
        self._config['fix_grammar_hotkey_enabled'] = enabled
        self.save()

    def restore_defaults(self):
        """Restore all settings to defaults except API keys."""
        api_keys = self._config.get('api_keys', [])
        self._config = self.DEFAULT_CONFIG.copy()
        self._config['hotkeys'] = self.DEFAULT_HOTKEYS.copy()
        self._config['custom_hotkeys'] = {}
        self._config['api_keys'] = api_keys  # Preserve API keys with models
        
        # Preserve history
        history = self._config.get('history', [])
        self._config['history'] = history
        self.save()

    # Auto-start management
    def get_autostart(self) -> bool:
        """Get auto-start setting."""
        return self._config.get('autostart', False)

    def set_autostart(self, enable: bool):
        """Set auto-start with Windows."""
        self._config['autostart'] = enable
        self._update_registry_autostart(enable)
        self.save()

    def _update_registry_autostart(self, enable: bool):
        """Update Windows registry for auto-start."""
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                               winreg.KEY_SET_VALUE | winreg.KEY_READ) as key:
                if enable:
                    exe_path = self._get_exe_path()
                    winreg.SetValueEx(key, self.APP_NAME, 0, winreg.REG_SZ, exe_path)
                else:
                    try:
                        winreg.DeleteValue(key, self.APP_NAME)
                    except FileNotFoundError:
                        pass
        except WindowsError as e:
            print(f"Failed to update registry: {e}")

    def _get_exe_path(self) -> str:
        """Get the path to use for auto-start."""
        if getattr(sys, 'frozen', False):
            return sys.executable
        
        # Use absolute path to pythonw.exe to ensure reliability
        python_dir = os.path.dirname(sys.executable)
        pythonw = os.path.join(python_dir, 'pythonw.exe')
        if not os.path.exists(pythonw):
            pythonw = sys.executable
            
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'main.py'))
        return f'"{pythonw}" "{script_path}"'

    def is_autostart_enabled(self) -> bool:
        """Check if auto-start is currently enabled in registry."""
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                               winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, self.APP_NAME)
                return True
        except (FileNotFoundError, WindowsError):
            return False

    # Update settings
    def get_check_updates(self) -> bool:
        """Get check for updates setting."""
        return self._config.get('check_updates', True)

    def set_check_updates(self, enable: bool):
        """Set check for updates setting."""
        self._config['check_updates'] = enable
        self.save()

    def get_auto_check_updates(self) -> bool:
        """Get whether to auto-check updates on startup."""
        return self._config.get('auto_check_updates', False)

    def set_auto_check_updates(self, enabled: bool):
        """Set auto-check updates on startup."""
        self._config['auto_check_updates'] = enabled
        self.save()

    # Trial mode settings
    def get_trial_mode_forced(self) -> bool:
        """Get whether trial mode is forced by user."""
        return self._config.get('trial_mode_forced', False)

    def set_trial_mode_forced(self, enabled: bool):
        """Set trial mode forced flag."""
        self._config['trial_mode_forced'] = enabled
        self.save()

    def get_trial_last_api_check(self) -> str:
        """Get ISO datetime of last API check for trial mode."""
        return self._config.get('trial_last_api_check', '')

    def set_trial_last_api_check(self, dt_str: str):
        """Set last API check datetime for trial mode."""
        self._config['trial_last_api_check'] = dt_str
        self.save()

    # Theme settings
    def get_theme(self) -> str:
        """Get UI theme."""
        return self._config.get('theme', 'darkly')

    def set_theme(self, theme: str):
        """Set UI theme."""
        self._config['theme'] = theme
        self.save()

    # API Capability Management
    def update_api_capabilities(self, api_key: str, model_name: str, vision_capable: bool, file_capable: bool):
        """Update capability flags for a specific API configuration.

        This is called when an API is tested successfully.
        The flags persist until the API is re-tested and fails, or deleted.
        """
        api_keys = self.get_api_keys()
        updated = False
        for api_config in api_keys:
            if api_config.get('api_key') == api_key and api_config.get('model_name') == model_name:
                api_config['vision_capable'] = vision_capable
                api_config['file_capable'] = file_capable
                updated = True
                break

        if updated:
            # Use set_api_keys to properly encrypt and save
            self.set_api_keys(api_keys)
            self._auto_update_toggles()
            self.save()

    def _auto_update_toggles(self):
        """Auto-enable toggles based on API capabilities."""
        api_keys = self.get_api_keys()
        has_vision = any(api.get('vision_capable', False) for api in api_keys)
        has_file = any(api.get('file_capable', False) for api in api_keys)

        self._config['vision_enabled'] = has_vision
        self._config['file_processing_enabled'] = has_file

    def get_vision_capable_apis(self) -> list:
        """Get list of API configs that support vision/image processing."""
        return [api for api in self.get_api_keys() if api.get('vision_capable', False)]

    def get_file_capable_apis(self) -> list:
        """Get list of API configs that support file processing."""
        return [api for api in self.get_api_keys() if api.get('file_capable', False)]

    def has_any_vision_capable(self) -> bool:
        """Check if any API supports vision."""
        return len(self.get_vision_capable_apis()) > 0

    def has_any_file_capable(self) -> bool:
        """Check if any API supports file processing."""
        return len(self.get_file_capable_apis()) > 0

    # NLP Language Pack Management
    def get_nlp_installed(self) -> List[str]:
        """Get list of installed NLP language pack names."""
        return self._config.get('nlp_installed', [])

    def set_nlp_installed(self, languages: List[str]):
        """Set list of installed NLP language packs."""
        self._config['nlp_installed'] = languages
        self.save()

    def add_nlp_installed(self, language: str):
        """Add a language to installed NLP packs."""
        installed = self.get_nlp_installed()
        if language not in installed:
            installed.append(language)
            self.set_nlp_installed(installed)

    def remove_nlp_installed(self, language: str):
        """Remove a language from installed NLP packs."""
        installed = self.get_nlp_installed()
        if language in installed:
            installed.remove(language)
            self.set_nlp_installed(installed)

    def is_nlp_installed(self, language: str) -> bool:
        """Check if a language NLP pack is installed."""
        return language in self.get_nlp_installed()

    def has_any_nlp_installed(self) -> bool:
        """Check if any NLP language pack is installed."""
        return len(self.get_nlp_installed()) > 0

    def get_nlp_basic_mode(self) -> List[str]:
        """Get languages installed in basic tokenization mode."""
        return self._config.get('nlp_basic_mode', [])

    def add_nlp_basic_mode(self, language: str):
        """Mark a language as using basic tokenization mode."""
        basic = self.get_nlp_basic_mode()
        if language not in basic:
            basic.append(language)
            self._config['nlp_basic_mode'] = basic
            self.save()

    def remove_nlp_basic_mode(self, language: str):
        """Remove a language from basic tokenization mode."""
        basic = self.get_nlp_basic_mode()
        if language in basic:
            basic.remove(language)
            self._config['nlp_basic_mode'] = basic
            self.save()

    def is_nlp_basic_mode(self, language: str) -> bool:
        """Check if a language is in basic tokenization mode."""
        return language in self.get_nlp_basic_mode()

    def get_nlp_working_python(self) -> Optional[str]:
        """Get the cached working Python path for NLP packages."""
        return self._config.get('nlp_working_python', None)

    def set_nlp_working_python(self, path: str):
        """Cache a verified working Python path for NLP packages."""
        self._config['nlp_working_python'] = path
        self.save()

    # Update check telemetry (local only)
    def record_update_check(self, success: bool, error_type: Optional[str] = None) -> None:
        """Record update check attempt for diagnostics (local only - no data sent externally).

        Args:
            success: Whether the update check succeeded
            error_type: Type of error if failed (must be from VALID_ERROR_TYPES:
                        'network', 'rate_limit', 'ssl', 'parse_error', 'timeout', 'other')

        Note:
            All data is stored locally in config.json. Nothing is sent externally.
            This helps diagnose update issues and track reliability.
        """
        try:
            from datetime import datetime

            # Validate error_type if provided
            if error_type is not None:
                # Import valid types - avoid circular import by importing here
                from src.utils.updates import VALID_ERROR_TYPES
                if error_type not in VALID_ERROR_TYPES:
                    logging.warning(
                        f"Invalid error_type '{error_type}'. Must be one of {VALID_ERROR_TYPES}. "
                        f"Using 'other' instead."
                    )
                    error_type = 'other'

            if 'update_stats' not in self._config:
                self._config['update_stats'] = {
                    'total': 0,
                    'success': 0,
                    'failed': 0,
                    'last_check': None,
                    'last_success': None
                }

            stats = self._config['update_stats']
            stats['total'] += 1
            stats['last_check'] = datetime.now().isoformat()

            if success:
                stats['success'] += 1
                stats['last_success'] = datetime.now().isoformat()
            else:
                stats['failed'] += 1
                if error_type:
                    if 'error_types' not in stats:
                        stats['error_types'] = {}
                    stats['error_types'][error_type] = stats['error_types'].get(error_type, 0) + 1

            self.save()
            logging.debug(f"Update check recorded: success={success}, total={stats['total']}")

        except Exception as e:
            # Don't let telemetry errors break the app
            logging.warning(f"Failed to record update check telemetry: {e}")

    # Version tracking for cache clearing on upgrade
    def get_last_run_version(self) -> Optional[str]:
        """Get the version from last app run."""
        return self._config.get('last_run_version')

    def set_last_run_version(self, version: str):
        """Set the last run version."""
        self._config['last_run_version'] = version
        self.save()

    # Generic getter/setter
    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value."""
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        """Set a config value."""
        self._config[key] = value
        self.save()
