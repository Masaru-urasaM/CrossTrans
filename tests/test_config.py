"""
Unit tests for config.py - Configuration management.
"""
import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config


class TestConfigInit:
    """Tests for Config initialization."""

    def test_default_config_values(self, temp_config_dir):
        """Test that default values are set correctly."""
        with patch.object(Config, 'CONFIG_DIR', temp_config_dir):
            with patch.object(Config, 'CONFIG_FILE', os.path.join(temp_config_dir, 'config.json')):
                config = Config()

                assert config.get_api_keys() == []
                assert config.get_autostart() == False
                assert config.get_theme() == 'darkly'
                assert config.get_check_updates() == False

    def test_load_existing_config(self, temp_config_dir, sample_config_json):
        """Test loading existing configuration file."""
        config_file = os.path.join(temp_config_dir, 'config.json')

        # Write sample config
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(sample_config_json, f)

        with patch.object(Config, 'CONFIG_DIR', temp_config_dir):
            with patch.object(Config, 'CONFIG_FILE', config_file):
                config = Config()

                api_keys = config.get_api_keys()
                assert len(api_keys) == 1
                assert api_keys[0]['model_name'] == 'gemini-2.0-flash'


class TestApiKeyManagement:
    """Tests for API key management."""

    def test_get_api_keys_empty(self, temp_config_dir):
        """Test getting API keys when none are set."""
        with patch.object(Config, 'CONFIG_DIR', temp_config_dir):
            with patch.object(Config, 'CONFIG_FILE', os.path.join(temp_config_dir, 'config.json')):
                config = Config()
                assert config.get_api_keys() == []

    def test_set_and_get_api_keys(self, temp_config_dir):
        """Test setting and retrieving API keys."""
        with patch.object(Config, 'CONFIG_DIR', temp_config_dir):
            with patch.object(Config, 'CONFIG_FILE', os.path.join(temp_config_dir, 'config.json')):
                config = Config()

                test_keys = [
                    {'model_name': 'gpt-4', 'api_key': 'sk-test123', 'provider': 'openai'},
                    {'model_name': 'claude-3', 'api_key': 'sk-ant-test', 'provider': 'anthropic'}
                ]
                config.set_api_keys(test_keys)

                retrieved = config.get_api_keys()
                assert len(retrieved) == 2
                assert retrieved[0]['model_name'] == 'gpt-4'
                assert retrieved[1]['api_key'] == 'sk-ant-test'

    def test_get_api_key_backward_compat(self, temp_config_dir):
        """Test backward compatibility method get_api_key()."""
        with patch.object(Config, 'CONFIG_DIR', temp_config_dir):
            with patch.object(Config, 'CONFIG_FILE', os.path.join(temp_config_dir, 'config.json')):
                config = Config()

                test_keys = [{'model_name': 'test', 'api_key': 'first-key'}]
                config.set_api_keys(test_keys)

                # get_api_key() should return first key
                assert config.get_api_key() == 'first-key'


class TestHotkeyManagement:
    """Tests for hotkey management."""

    def test_get_default_hotkeys(self, temp_config_dir):
        """Test getting default hotkeys."""
        with patch.object(Config, 'CONFIG_DIR', temp_config_dir):
            with patch.object(Config, 'CONFIG_FILE', os.path.join(temp_config_dir, 'config.json')):
                config = Config()

                hotkeys = config.get_hotkeys()
                assert 'Vietnamese' in hotkeys
                assert 'English' in hotkeys
                assert hotkeys['Vietnamese'] == 'win+alt+v'

    def test_set_custom_hotkey(self, temp_config_dir):
        """Test setting custom hotkey."""
        with patch.object(Config, 'CONFIG_DIR', temp_config_dir):
            with patch.object(Config, 'CONFIG_FILE', os.path.join(temp_config_dir, 'config.json')):
                config = Config()

                config.set_custom_hotkey('Korean', 'win+alt+k')
                custom = config.get_custom_hotkeys()

                assert 'Korean' in custom
                assert custom['Korean'] == 'win+alt+k'

    def test_get_all_hotkeys_merges(self, temp_config_dir):
        """Test that get_all_hotkeys merges default and custom."""
        with patch.object(Config, 'CONFIG_DIR', temp_config_dir):
            with patch.object(Config, 'CONFIG_FILE', os.path.join(temp_config_dir, 'config.json')):
                config = Config()

                config.set_custom_hotkey('Korean', 'win+alt+k')
                all_hotkeys = config.get_all_hotkeys()

                # Should have both default and custom
                assert 'Vietnamese' in all_hotkeys
                assert 'Korean' in all_hotkeys

    def test_max_custom_hotkeys(self, temp_config_dir):
        """Test that max custom hotkeys limit is enforced."""
        with patch.object(Config, 'CONFIG_DIR', temp_config_dir):
            with patch.object(Config, 'CONFIG_FILE', os.path.join(temp_config_dir, 'config.json')):
                config = Config()

                # Add max number of custom hotkeys
                for i in range(Config.MAX_CUSTOM_HOTKEYS + 2):
                    config.set_custom_hotkey(f'Lang{i}', f'win+alt+{i}')

                custom = config.get_custom_hotkeys()
                assert len(custom) <= Config.MAX_CUSTOM_HOTKEYS


class TestThemeAndSettings:
    """Tests for theme and other settings."""

    def test_set_and_get_theme(self, temp_config_dir):
        """Test setting and getting theme."""
        with patch.object(Config, 'CONFIG_DIR', temp_config_dir):
            with patch.object(Config, 'CONFIG_FILE', os.path.join(temp_config_dir, 'config.json')):
                config = Config()

                config.set_theme('superhero')
                assert config.get_theme() == 'superhero'

    def test_restore_defaults(self, temp_config_dir):
        """Test restoring default settings preserves API keys."""
        with patch.object(Config, 'CONFIG_DIR', temp_config_dir):
            with patch.object(Config, 'CONFIG_FILE', os.path.join(temp_config_dir, 'config.json')):
                config = Config()

                # Set custom values
                test_keys = [{'model_name': 'test', 'api_key': 'preserve-me'}]
                config.set_api_keys(test_keys)
                config.set_theme('superhero')
                config.set_custom_hotkey('Korean', 'win+alt+k')

                # Restore defaults
                config.restore_defaults()

                # API keys should be preserved
                assert len(config.get_api_keys()) == 1
                assert config.get_api_keys()[0]['api_key'] == 'preserve-me'

                # Theme should be reset
                assert config.get_theme() == 'darkly'

                # Custom hotkeys should be cleared
                assert config.get_custom_hotkeys() == {}


class TestApiCapabilities:
    """Tests for API capability management."""

    def test_update_api_capabilities(self, temp_config_dir):
        """Test updating API capabilities."""
        with patch.object(Config, 'CONFIG_DIR', temp_config_dir):
            with patch.object(Config, 'CONFIG_FILE', os.path.join(temp_config_dir, 'config.json')):
                config = Config()

                test_keys = [{'model_name': 'gpt-4o', 'api_key': 'test-key'}]
                config.set_api_keys(test_keys)

                config.update_api_capabilities('test-key', 'gpt-4o', True, True)

                api_keys = config.get_api_keys()
                assert api_keys[0].get('vision_capable') == True
                assert api_keys[0].get('file_capable') == True

    def test_has_any_vision_capable(self, temp_config_dir):
        """Test checking for vision capability."""
        with patch.object(Config, 'CONFIG_DIR', temp_config_dir):
            with patch.object(Config, 'CONFIG_FILE', os.path.join(temp_config_dir, 'config.json')):
                config = Config()

                # No APIs = no vision
                assert config.has_any_vision_capable() == False

                # Add vision-capable API
                test_keys = [{'model_name': 'gpt-4o', 'api_key': 'test', 'vision_capable': True}]
                config._config['api_keys'] = test_keys

                assert config.has_any_vision_capable() == True


class TestConfigPersistence:
    """Tests for config file persistence."""

    def test_save_creates_file(self, temp_config_dir):
        """Test that save creates the config file."""
        config_file = os.path.join(temp_config_dir, 'config.json')

        with patch.object(Config, 'CONFIG_DIR', temp_config_dir):
            with patch.object(Config, 'CONFIG_FILE', config_file):
                config = Config()
                config.set_theme('cyborg')

                # File should exist after save
                assert os.path.exists(config_file)

                # Content should be valid JSON
                with open(config_file, 'r') as f:
                    data = json.load(f)
                    assert data['theme'] == 'cyborg'

    def test_secure_save(self, temp_config_dir):
        """Test secure save overwrites file content."""
        config_file = os.path.join(temp_config_dir, 'config.json')

        with patch.object(Config, 'CONFIG_DIR', temp_config_dir):
            with patch.object(Config, 'CONFIG_FILE', config_file):
                config = Config()

                # Write initial config
                config.set_api_keys([{'model_name': 'test', 'api_key': 'secret-key'}])

                # Secure save should still work
                config.save(secure=True)

                assert os.path.exists(config_file)


class TestQuickPopupSize:
    """The size the user dragged the quick-translate popup to (Decision 34, P4)."""

    @staticmethod
    def _patched(temp_config_dir):
        return (patch.object(Config, 'CONFIG_DIR', temp_config_dir),
                patch.object(Config, 'CONFIG_FILE', os.path.join(temp_config_dir, 'config.json')))

    def test_automatic_until_the_user_drags_it(self, temp_config_dir):
        directory, file = self._patched(temp_config_dir)
        with directory, file:
            assert Config().get_quick_popup_size() == (None, None)

    def test_a_dragged_size_survives_a_restart(self, temp_config_dir):
        directory, file = self._patched(temp_config_dir)
        with directory, file:
            Config().set_quick_popup_size(480, 300)
            assert Config().get_quick_popup_size() == (480, 300)

    def test_none_returns_it_to_automatic(self, temp_config_dir):
        directory, file = self._patched(temp_config_dir)
        with directory, file:
            config = Config()
            config.set_quick_popup_size(480, 300)
            config.set_quick_popup_size(None, None)
            assert Config().get_quick_popup_size() == (None, None)
