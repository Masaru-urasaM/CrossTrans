"""One model result owns its correspondence; cache and hover spend no calls."""
import json
from unittest.mock import Mock

import pytest

import src.core  # Initialize the existing package before config's circular import.
from config import Config
from src.core.translation import TranslationService
from src.core.translation_alignment import AlignedText
from src.core.history import HistoryManager


SOURCE = 'First. Second.'
RAW = json.dumps({'version': 1, 'segments': [
    {'source_ids': [1], 'text': 'One.'}, {'source_ids': [2], 'text': 'Two.'}]})


class FakeConfig:
    def __init__(self, enabled=True, history_enabled=True):
        self.data = {'linked_reading_enabled': enabled, 'history_enabled': history_enabled}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


def make_service(enabled=True, history_enabled=True, raw=RAW):
    service = TranslationService.__new__(TranslationService)
    service.config = FakeConfig(enabled, history_enabled)
    service._is_trial_mode = False
    service.last_attribution = 'model (Provider)'
    service.history_manager = HistoryManager(service.config)
    service._call_model = Mock(return_value=raw)
    return service


def test_one_generation_and_cached_metadata_with_plain_history_text():
    service = make_service()
    result = service.translate_or_fix(SOURCE, 'English')
    assert isinstance(result, AlignedText)
    assert result == 'One. Two.'
    service._call_model.assert_called_once()
    assert service.config.data['history'][0]['alignment'] == result.alignment
    assert json.loads(json.dumps(service.config.data))['history'][0]['translated'] == 'One. Two.'
    service.config.data = json.loads(json.dumps(service.config.data))
    cached = service.translate_or_fix(SOURCE, 'English')
    assert isinstance(cached, AlignedText) and cached.alignment == result.alignment
    assert service._call_model.call_count == 1


def test_legacy_cache_and_corrupt_metadata_never_trigger_upgrade_calls():
    service = make_service()
    service.history_manager.add_entry(SOURCE, 'Old answer.', 'English', source_type='merged')
    result = service.translate_or_fix(SOURCE, 'English')
    assert type(result) is str and result == 'Old answer.'
    service.config.data['history'][0]['alignment'] = {'version': 99}
    assert type(service.translate_or_fix(SOURCE, 'English')) is str
    service._call_model.assert_not_called()


def test_disabled_history_still_carries_exact_result_metadata():
    service = make_service(history_enabled=False)
    first = service.translate_or_fix(SOURCE, 'English')
    service._call_model.return_value = RAW.replace('One.', 'Uno.')
    second = service.translate_or_fix(SOURCE, 'English')
    assert first == 'One. Two.' and second == 'Uno. Two.'
    assert first.alignment['target_hash'] != second.alignment['target_hash']
    assert 'history' not in service.config.data


@pytest.mark.parametrize('raw', ['{', '{"version":1,"segments":[]}', '```json\n{'])
def test_malformed_response_no_repair_or_partial_history(raw):
    service = make_service(raw=raw)
    assert service.translate_or_fix(SOURCE, 'English').startswith('Error:')
    service._call_model.assert_called_once()
    assert not service.config.data.get('history')


def test_bad_ids_return_complete_text_without_fabricated_links():
    service = make_service(raw=RAW.replace('[2]', '[20]'))
    result = service.translate_or_fix(SOURCE, 'English')
    assert type(result) is str
    assert result == 'One. Two.'
    assert 'source_ids' not in result
    assert 'alignment' not in service.config.data['history'][0]
    service._call_model.assert_called_once()


def test_off_code_and_trial_paths_do_not_use_structured_prompt():
    for source, enabled, trial in [(SOURCE, False, False), ('Keep {"x":1}.', True, False),
                                    (SOURCE, True, True)]:
        service = make_service(enabled=enabled, raw='Ordinary answer.')
        service._is_trial_mode = trial
        result = service.translate_or_fix(source, 'English')
        assert result == 'Ordinary answer.' and type(result) is str
        assert 'SOURCE UNITS:' not in service._call_model.call_args.args[0]


def test_plain_main_translation_stays_plain_but_popup_redo_can_link():
    service = make_service(raw='Ordinary.')
    service.translate_text(SOURCE, 'English')
    assert 'SOURCE UNITS:' not in service._call_model.call_args.args[0]
    service._call_model.return_value = RAW
    result = service.translate_text(SOURCE, 'English', skip_cache=True, allow_linked=True,
                                    source_language='Japanese')
    assert isinstance(result, AlignedText)
    assert service.last_source_language == 'Japanese'
    assert result.alignment['mode'] == 'text'


def test_setting_default_and_toggle_do_not_change_other_options():
    cfg = Config.__new__(Config)
    cfg._config = {'furigana_enabled': False}
    cfg.save = Mock()
    assert cfg.get_linked_reading_enabled() is False
    cfg.set_linked_reading_enabled(True)
    assert cfg.get_linked_reading_enabled() is True
    assert cfg._config['furigana_enabled'] is False
    cfg.save.assert_called_once()


def test_off_mode_retains_cached_carrier_for_later_display_toggle():
    service = make_service()
    service.translate_or_fix(SOURCE, 'English')
    service.config.data['linked_reading_enabled'] = False
    result = service.translate_or_fix(SOURCE, 'English')
    assert isinstance(result, AlignedText)
    assert result.alignment == service.config.data['history'][0]['alignment']


def test_changed_source_verdict_invalidates_old_alignment():
    service = make_service()
    service.translate_or_fix(SOURCE, 'English')
    assert service.config.data['history'][0].get('alignment')
    service.history_manager.set_source_verdict(SOURCE, 'Japanese')
    assert 'alignment' not in service.config.data['history'][0]
    assert service.translate_or_fix(SOURCE, 'English').alignment['method'] == 'structure'
    assert service._call_model.call_count == 1


def test_existing_queue_and_app_forward_the_exact_metadata_carrier():
    import queue
    from src.app import TranslatorApp
    service = make_service()
    value = service.translate_or_fix(SOURCE, 'English')
    service._call_model.return_value = RAW.replace('One.', 'Uno.')
    newer = service.translate_or_fix(SOURCE, 'English', skip_cache=True)
    service.translation_queue = queue.Queue()
    service.translation_queue.put((SOURCE, newer, 'English', None, None))
    service.translation_queue.put((SOURCE, value, 'English', None, None))
    app = TranslatorApp.__new__(TranslatorApp)
    app.translation_service = service
    app.running = True
    app.root = Mock()
    app.quick_translate_manager = Mock()
    app._check_queue()
    delivered = [call.args[0] for call in app.quick_translate_manager.show.call_args_list]
    assert delivered[0] is newer and delivered[1] is value
    assert delivered[0].alignment['target_hash'] != delivered[1].alignment['target_hash']
