"""D12 - a model ID listed by two providers goes to the one the key belongs to.

`_identify_provider()` matched `model_provider_map` first and returned the first
provider listing the model, so for the thirteen IDs two providers share, one of
the two was always wrong under provider='Auto' (DEFERRED D12, 2026-09-08). Now the
key decides between them: the provider whose prefix it carries; else one with no
known prefix, since a key without csk- is not a Cerebras key; else the first.

Run against tier 3 - `src/constants.py` alone, as in test_default_model_routing.py.
"""
import collections

import pytest

import src.core.api_manager as api_manager_module
from src.core.api_manager import AIAPIManager
from src.constants import API_KEY_PATTERNS, MODEL_PROVIDER_MAP

UUID_KEY = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"     # SambaNova's shape: no prefix


class _HardcodedConfig:
    model_provider_map = MODEL_PROVIDER_MAP
    api_key_patterns = API_KEY_PATTERNS


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.setattr(api_manager_module, 'get_config', _HardcodedConfig)
    return AIAPIManager()


PREFIX = {provider: prefix for prefix, provider in API_KEY_PATTERNS.items()}


def shared_models():
    claims = collections.defaultdict(list)
    for provider, models in MODEL_PROVIDER_MAP.items():
        for model in models:
            if provider not in claims[model.lower()]:
                claims[model.lower()].append(provider)
    return {model: providers for model, providers in claims.items() if len(providers) > 1}


SHARED = shared_models()


def test_the_shared_ids_are_the_ones_d12_lists():
    assert len(SHARED) == 13
    assert SHARED['gpt-oss-120b'] == ['Cerebras', 'SambaNova']


@pytest.mark.parametrize("model, provider", [
    (model, provider) for model, providers in SHARED.items()
    for provider in providers if provider in PREFIX])
def test_a_key_with_a_providers_prefix_goes_to_that_provider(manager, model, provider):
    assert manager._identify_provider(model, PREFIX[provider] + "abc123") == provider


@pytest.mark.parametrize("model, provider", [
    (model, provider) for model, providers in SHARED.items()
    for provider in providers
    if provider not in PREFIX and sum(p not in PREFIX for p in providers) == 1])
def test_the_one_claimant_without_a_prefix_gets_the_other_keys(manager, model, provider):
    assert manager._identify_provider(model, UUID_KEY) == provider


def test_d12s_rows_that_were_wrong(manager):
    assert manager._identify_provider("gpt-oss-120b", UUID_KEY) == 'SambaNova'
    assert manager._identify_provider("meta-llama/llama-3.3-70b-instruct", "hf_x") == 'HuggingFace'
    assert manager._identify_provider("google/gemma-2-27b-it", "hf_x") == 'HuggingFace'
    assert manager._identify_provider("qwen/qwen2.5-72b-instruct", "hf_x") == 'HuggingFace'


def test_two_claimants_without_a_prefix_stay_unresolved(manager):
    # Together and SiliconFlow have no key prefix: the first still wins (D12's gap).
    assert SHARED['deepseek-ai/deepseek-r1'] == ['Together', 'SiliconFlow']
    assert manager._identify_provider("deepseek-ai/deepseek-r1", UUID_KEY) == 'Together'


def test_a_key_that_matches_no_claimant_keeps_the_first(manager):
    assert manager._identify_provider("meta-llama/llama-3.3-70b-instruct", UUID_KEY) == 'OpenRouter'


def test_no_key_keeps_the_first(manager):
    assert manager._identify_provider("gpt-oss-120b", "") == 'Cerebras'


def test_a_model_one_provider_lists_ignores_the_key(manager):
    assert manager._identify_provider("gemini-2.5-flash", "gsk_abc") == 'Google'
