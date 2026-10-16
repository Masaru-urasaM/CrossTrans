"""A provider's default models must route back to that provider.

`DEFAULT_MODELS_BY_PROVIDER` is read whenever the model field is blank. When the
provider is set to 'Auto', the chosen model is then handed straight back to
`_identify_provider()` to decide which API to call - so a default that does not
identify as its own provider sends the user's key to somebody else's endpoint.

These tests run against **tier 3**: `src/constants.py` alone, no remote config
and no cache. That is a fresh install with no network, and it is the one tier
where a wrong entry cannot be corrected from Cloudflare.

Measured 2026-09-08: `google/gemma-4-31b-it:free`, chosen as an OpenRouter
default, identified as **Together**. `_identify_provider()` tries an exact match
in `model_provider_map` first, then a set of prefix rules in which `google/`
means Together - and the free models were not in the map, so the prefix rule
won. Both of the OpenRouter defaults it replaced did the same thing, on top of
being dead.
"""

import pytest

import src.core.api_manager as api_manager_module
from src.core.api_manager import AIAPIManager, DEFAULT_MODELS_BY_PROVIDER
from src.constants import API_KEY_PATTERNS, MODEL_PROVIDER_MAP


class _HardcodedConfig:
    """The tier-3 view: what constants.py provides with no network."""

    model_provider_map = MODEL_PROVIDER_MAP
    api_key_patterns = API_KEY_PATTERNS


@pytest.fixture
def offline_manager(monkeypatch):
    """An AIAPIManager whose config is the hardcoded fallback only."""
    monkeypatch.setattr(api_manager_module, 'get_config', _HardcodedConfig)
    return AIAPIManager()


def _key_for(provider):
    """A plausible API key for `provider`, or a neutral one if it has no pattern."""
    for prefix, name in API_KEY_PATTERNS.items():
        if name == provider:
            return prefix + 'x' * 8
    return 'x' * 8


@pytest.mark.parametrize(
    'provider,model',
    [(p, m) for p, models in DEFAULT_MODELS_BY_PROVIDER.items() for m in models],
)
def test_a_default_model_identifies_as_its_own_provider(offline_manager, provider, model):
    """Every entry, for every provider, offline. The whole point of the table."""
    identified = offline_manager._identify_provider(model, _key_for(provider))
    assert identified == provider, (
        f"{provider}'s default model {model!r} identifies as {identified!r}. "
        f"Under provider='Auto' that routes the request to {identified}'s API "
        f"with a {provider} key. Add it to MODEL_PROVIDER_MAP[{provider!r}] so "
        f"the exact-match step of _identify_provider() wins."
    )


def test_openrouter_defaults_are_listed_in_the_model_map(offline_manager):
    """The specific trap: a slash-prefixed default that a prefix rule can steal.

    Kept separate from the parametrized sweep because it names the mechanism.
    `_identify_provider()` reads `model_provider_map` before its prefix rules,
    so listing the model there is what makes the exact match win. Drop these two
    from the map and `google/gemma-4-31b-it:free` answers Together again.
    """
    listed = MODEL_PROVIDER_MAP['OpenRouter']
    for model in DEFAULT_MODELS_BY_PROVIDER['OpenRouter']:
        assert model in listed, (
            f"{model!r} is an OpenRouter default but is missing from "
            f"MODEL_PROVIDER_MAP['OpenRouter']"
        )


def test_the_google_prefix_rule_really_does_claim_together(offline_manager):
    """Pins the mechanism itself, so the test above cannot quietly stop meaning anything.

    If this ever fails, the prefix rule changed and the guard above is no longer
    protecting against anything - which is worth knowing.
    """
    stolen = offline_manager._identify_provider('google/not-a-real-model', 'sk-or-v1-xxxxxxxx')
    assert stolen == 'Together'


def test_no_default_model_is_a_batch_variant():
    """':batch' endpoints are asynchronous and cannot answer an interactive translation."""
    for provider, models in DEFAULT_MODELS_BY_PROVIDER.items():
        for model in models:
            assert ':batch' not in model, f'{provider} default {model!r} is a batch endpoint'


def test_a_cerebras_key_is_not_mistaken_for_google(offline_manager):
    """`_detect_provider_from_key()` defaults to Google, so a missing pattern is expensive.

    Measured 2026-09-08 with a real key: without the `csk-` entry a Cerebras user
    who leaves Provider on 'Auto' and the model field blank was handed Google's
    default (`gemini-2.5-flash`) and sent it to `api.cerebras.ai`. The failure is
    silent and looks like a dead model, which is what made it worth a test rather
    than just a table entry.
    """
    assert offline_manager._detect_provider_from_key('csk-' + 'x' * 20) == 'Cerebras'


def test_an_unknown_model_on_a_known_key_still_finds_its_provider(offline_manager):
    """The key pattern is the backstop when a model is too new to be in the map."""
    for prefix, provider in API_KEY_PATTERNS.items():
        identified = offline_manager._identify_provider('some-unreleased-model', prefix + 'x' * 20)
        assert identified == provider, (
            f'a {provider} key ({prefix}...) with an unlisted model identified as {identified}'
        )


# Retired or going, by their own providers' documentation (desk check 2026-10-16,
# DEFERRED D11, K15). No key was at hand, so the replacements are listed by each
# provider today rather than answered - but these are known dead, and a default
# must never be one of them again.
RETIRED = {
    'OpenAI': {'gpt-3.5-turbo'},                                    # shuts down 2026-10-23
    'Anthropic': {'claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022',
                  'claude-3-haiku-20240307'},                       # retired 2025-10 .. 2026-04
    'DeepSeek': {'deepseek-chat', 'deepseek-coder'},                # gone from the API docs
    'xAI': {'grok-2', 'grok-beta'},                                 # not on xAI's model list
    'Together': {'meta-llama/Llama-3.3-70B-Instruct-Turbo',         # removed 2026-10-22
                 'meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo'},   # removed 2026-02-25
}


@pytest.mark.parametrize('provider', sorted(RETIRED))
def test_no_default_is_a_model_its_provider_has_retired(provider):
    stale = set(DEFAULT_MODELS_BY_PROVIDER[provider]) & RETIRED[provider]
    assert not stale, (f"{provider}'s defaults {sorted(stale)} are retired by {provider} "
                       f"itself - every auto-pick would fail (DEFERRED D11)")


def test_every_provider_has_a_second_default_to_rotate_to():
    """_try_model_rotation() moves to the next default when the first fails; a
    provider left with one has nowhere to go (D11 removed gpt-3.5-turbo)."""
    for provider, models in DEFAULT_MODELS_BY_PROVIDER.items():
        assert len(models) >= 2, f"{provider} has {models}"
