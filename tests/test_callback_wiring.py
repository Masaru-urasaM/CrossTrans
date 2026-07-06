"""
Integration guard for R1/R2 callback wiring.

These checks catch name mismatches between the popup callback signature, the app-level
handlers, and the translation-service methods — the kind of typo that unit tests on
individual functions cannot detect. They are static (no Tk window, no mainloop).
"""
import os
import sys
import inspect

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import a src.core submodule BEFORE src.app: this primes the src.core -> config import
# chain in the order that resolves cleanly (importing config or src.app first hits an
# order-dependent circular import that only succeeds once src.core has started loading).
from src.core.translation import TranslationService
from src.app import TranslatorApp
from src.ui.quick_translate import QuickTranslateManager


def test_popup_configure_callbacks_accepts_new_params():
    """The popup must accept the R1/R2 callbacks the app wires into it."""
    params = inspect.signature(QuickTranslateManager.configure_callbacks).parameters
    assert 'on_re_translate' in params          # R1
    assert 'on_custom_prompt_send' in params     # R2


def test_app_defines_new_handlers():
    """The app must define the handlers it passes to configure_callbacks."""
    assert callable(getattr(TranslatorApp, '_on_quick_translate_retranslate', None))
    assert callable(getattr(TranslatorApp, '_on_quick_translate_custom_prompt_send', None))


def test_translation_service_has_new_methods():
    """The service must expose the R1/R2 entry points."""
    assert callable(getattr(TranslationService, 'redo_translation', None))   # R1
    assert callable(getattr(TranslationService, 'ask_freeform', None))        # R2


def test_translate_text_has_skip_cache_param():
    """R1 cache: translate_text must expose skip_cache."""
    params = inspect.signature(TranslationService.translate_text).parameters
    assert 'skip_cache' in params


def test_popup_has_edit_mode_methods():
    """R2 custom-prompt mode handlers must exist on the popup manager."""
    for name in ('_handle_custom_prompt', '_enter_custom_prompt_mode',
                 '_handle_custom_prompt_send', '_handle_custom_prompt_cancel',
                 '_handle_re_translate'):
        assert callable(getattr(QuickTranslateManager, name, None)), name


def test_translation_service_has_merged_methods():
    """Merged translate-or-fix entry points must exist on the service."""
    assert callable(getattr(TranslationService, 'translate_or_fix', None))
    assert callable(getattr(TranslationService, 'do_translate_or_fix', None))


def test_hotkey_normal_branch_uses_merged_path():
    """The language-hotkey branch must route through do_translate_or_fix (not the plain
    do_translation), so text already in the target language is grammar-fixed in place."""
    src = inspect.getsource(TranslatorApp._on_hotkey_translate)
    assert 'do_translate_or_fix(language)' in src
    assert 'do_translation(language)' not in src
