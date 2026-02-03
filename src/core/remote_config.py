"""
Remote Configuration Manager for CrossTrans.
Fetches model/provider configuration from Cloudflare Worker KV,
with local caching and hardcoded fallback.

Architecture (3-tier fallback):
  Tier 1: Remote fetch from Cloudflare Worker /v1/config
  Tier 2: Local cache file (%APPDATA%/AITranslator/models_config.json)
  Tier 3: Hardcoded defaults in constants.py
"""
import json
import os
import time
import logging
import threading
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Any, Callable

from src.constants import (
    MODEL_PROVIDER_MAP as _HARDCODED_MODEL_PROVIDER_MAP,
    PROVIDERS_LIST as _HARDCODED_PROVIDERS_LIST,
    API_KEY_PATTERNS as _HARDCODED_API_KEY_PATTERNS,
    VISION_MODELS as _HARDCODED_VISION_MODELS,
)

# Supported remote config schema versions
SUPPORTED_SCHEMA_VERSIONS = {2}

# Cache file location
_APPDATA = os.environ.get('APPDATA', os.path.expanduser('~'))
CACHE_DIR = os.path.join(_APPDATA, 'AITranslator')
CACHE_FILE = os.path.join(CACHE_DIR, 'models_config.json')

logger = logging.getLogger(__name__)


class RemoteConfigManager:
    """Manages remote model/provider configuration with local caching.

    Singleton - use get_config() to access.
    Thread-safe for concurrent reads from UI and background fetch.
    """

    _instance: Optional['RemoteConfigManager'] = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._config: Dict[str, Any] = {}
        self._config_lock = threading.RLock()
        self._update_callbacks: List[Callable] = []
        self._fetching = False
        self._load_cached_or_defaults()

    # ------------------------------------------------------------------ #
    # Loading & caching
    # ------------------------------------------------------------------ #

    def _load_cached_or_defaults(self):
        """Load config from local cache file, or fall back to hardcoded defaults."""
        cached = self._read_cache_file()
        if cached and self._validate_config(cached):
            self._config = cached
            logger.info("[RemoteConfig] Loaded config from local cache")
        else:
            self._config = self._build_hardcoded_defaults()
            logger.info("[RemoteConfig] Using hardcoded defaults")

    def _build_hardcoded_defaults(self) -> Dict[str, Any]:
        """Build config dict from constants.py hardcoded values."""
        from src.core.api_manager import DEFAULT_MODELS_BY_PROVIDER as _HARDCODED_DEFAULTS

        return {
            "version": 2,
            "updated_at": "",
            "providers_list": list(_HARDCODED_PROVIDERS_LIST),
            "model_provider_map": {k: list(v) for k, v in _HARDCODED_MODEL_PROVIDER_MAP.items()},
            "api_key_patterns": dict(_HARDCODED_API_KEY_PATTERNS),
            "vision_models": {k: list(v) for k, v in _HARDCODED_VISION_MODELS.items()},
            "default_models_by_provider": {k: list(v) for k, v in _HARDCODED_DEFAULTS.items()},
            "provider_api_urls": {
                'OpenAI': "https://api.openai.com/v1/chat/completions",
                'Groq': "https://api.groq.com/openai/v1/chat/completions",
                'DeepSeek': "https://api.deepseek.com/chat/completions",
                'Mistral': "https://api.mistral.ai/v1/chat/completions",
                'xAI': "https://api.x.ai/v1/chat/completions",
                'Perplexity': "https://api.perplexity.ai/chat/completions",
                'Cerebras': "https://api.cerebras.ai/v1/chat/completions",
                'SambaNova': "https://api.sambanova.ai/v1/chat/completions",
                'Together': "https://api.together.xyz/v1/chat/completions",
                'SiliconFlow': "https://api.siliconflow.cn/v1/chat/completions",
                'OpenRouter': "https://openrouter.ai/api/v1/chat/completions",
                'HuggingFace': "https://router.huggingface.co/v1/chat/completions",
            },
            "_source": "hardcoded",
        }

    def _read_cache_file(self) -> Optional[Dict]:
        """Read config from local cache file."""
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"[RemoteConfig] Failed to read cache file: {e}")
        return None

    def _save_cache(self, data: Dict):
        """Save config to local cache file."""
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            data_with_meta = dict(data)
            data_with_meta['_cached_at'] = time.time()
            data_with_meta['_source'] = 'remote'
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data_with_meta, f, ensure_ascii=False, indent=2)
            logger.info("[RemoteConfig] Saved config to local cache")
        except Exception as e:
            logger.warning(f"[RemoteConfig] Failed to save cache: {e}")

    def _is_cache_fresh(self) -> bool:
        """Check if cached config is within TTL (24 hours)."""
        from src.constants import REMOTE_CONFIG_CACHE_TTL
        cached_at = self._config.get('_cached_at', 0)
        if not cached_at:
            return False
        return (time.time() - cached_at) < REMOTE_CONFIG_CACHE_TTL

    # ------------------------------------------------------------------ #
    # Remote fetch
    # ------------------------------------------------------------------ #

    def fetch_remote_async(self, force: bool = False):
        """Fetch remote config in a background daemon thread.

        Args:
            force: If True, fetch even if cache is fresh
        """
        if self._fetching:
            return
        if not force and self._is_cache_fresh():
            logger.debug("[RemoteConfig] Cache is fresh, skipping remote fetch")
            return

        self._fetching = True
        t = threading.Thread(target=self._fetch_remote_thread, daemon=True, name="remote-config")
        t.start()

    def _fetch_remote_thread(self):
        """Background thread: fetch config from Cloudflare Worker."""
        try:
            data = self._fetch_remote()
            if data and self._validate_config(data):
                with self._config_lock:
                    self._config = data
                    self._config['_cached_at'] = time.time()
                    self._config['_source'] = 'remote'
                self._save_cache(data)
                logger.info("[RemoteConfig] Updated config from remote")
                self._notify_callbacks()
            else:
                logger.warning("[RemoteConfig] Remote config invalid or empty, keeping current")
        except Exception as e:
            logger.warning(f"[RemoteConfig] Remote fetch failed: {e}")
        finally:
            self._fetching = False

    def _fetch_remote(self) -> Optional[Dict]:
        """Fetch config JSON from Cloudflare Worker endpoint."""
        from src.constants import REMOTE_CONFIG_URL

        try:
            req = urllib.request.Request(
                REMOTE_CONFIG_URL,
                headers={
                    'User-Agent': 'CrossTrans-Config/1.0',
                    'Accept': 'application/json',
                },
                method='GET'
            )

            # Use SSL context if available
            ssl_context = None
            try:
                from src.core.ssl_pinning import get_ssl_context_for_url
                ssl_context = get_ssl_context_for_url(REMOTE_CONFIG_URL)
            except Exception:
                pass

            with urllib.request.urlopen(req, timeout=15, context=ssl_context) as response:
                raw = response.read().decode('utf-8')
                return json.loads(raw)

        except Exception as e:
            logger.warning(f"[RemoteConfig] HTTP fetch error: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #

    def _validate_config(self, data: Dict) -> bool:
        """Validate remote config schema."""
        if not isinstance(data, dict):
            return False

        version = data.get('version')
        if version not in SUPPORTED_SCHEMA_VERSIONS:
            logger.warning(f"[RemoteConfig] Unsupported schema version: {version}")
            return False

        required_keys = [
            'providers_list', 'model_provider_map', 'api_key_patterns',
            'vision_models', 'default_models_by_provider', 'provider_api_urls'
        ]
        for key in required_keys:
            if key not in data:
                logger.warning(f"[RemoteConfig] Missing required key: {key}")
                return False

        if not isinstance(data['providers_list'], list) or len(data['providers_list']) < 2:
            return False
        if not isinstance(data['model_provider_map'], dict):
            return False
        if not isinstance(data['provider_api_urls'], dict):
            return False

        return True

    # ------------------------------------------------------------------ #
    # Callbacks
    # ------------------------------------------------------------------ #

    def register_update_callback(self, callback: Callable):
        """Register callback to be notified when config updates from remote."""
        self._update_callbacks.append(callback)

    def unregister_update_callback(self, callback: Callable):
        """Unregister a previously registered callback."""
        try:
            self._update_callbacks.remove(callback)
        except ValueError:
            pass

    def _notify_callbacks(self):
        """Notify all registered callbacks that config was updated."""
        for cb in self._update_callbacks:
            try:
                cb()
            except Exception as e:
                logger.warning(f"[RemoteConfig] Callback error: {e}")

    # ------------------------------------------------------------------ #
    # Accessor properties (thread-safe reads)
    # ------------------------------------------------------------------ #

    @property
    def providers_list(self) -> List[str]:
        with self._config_lock:
            return list(self._config.get('providers_list', _HARDCODED_PROVIDERS_LIST))

    @property
    def model_provider_map(self) -> Dict[str, List[str]]:
        with self._config_lock:
            return dict(self._config.get('model_provider_map', _HARDCODED_MODEL_PROVIDER_MAP))

    @property
    def api_key_patterns(self) -> Dict[str, str]:
        with self._config_lock:
            return dict(self._config.get('api_key_patterns', _HARDCODED_API_KEY_PATTERNS))

    @property
    def vision_models(self) -> Dict[str, List[str]]:
        with self._config_lock:
            return dict(self._config.get('vision_models', _HARDCODED_VISION_MODELS))

    @property
    def default_models_by_provider(self) -> Dict[str, List[str]]:
        with self._config_lock:
            defaults = self._config.get('default_models_by_provider', {})
            if defaults:
                return dict(defaults)
            # Fallback to hardcoded
            from src.core.api_manager import DEFAULT_MODELS_BY_PROVIDER
            return dict(DEFAULT_MODELS_BY_PROVIDER)

    @property
    def provider_api_urls(self) -> Dict[str, str]:
        with self._config_lock:
            urls = self._config.get('provider_api_urls', {})
            if urls:
                return dict(urls)
            # Return hardcoded defaults
            return self._build_hardcoded_defaults()['provider_api_urls']

    @property
    def config_source(self) -> str:
        """Return 'remote', 'cached', or 'hardcoded'."""
        with self._config_lock:
            return self._config.get('_source', 'hardcoded')

    @property
    def config_updated_at(self) -> str:
        """Return the updated_at timestamp from config."""
        with self._config_lock:
            return self._config.get('updated_at', '')

    def clear_cache(self):
        """Clear local cache file (e.g., on version upgrade)."""
        try:
            if os.path.exists(CACHE_FILE):
                os.remove(CACHE_FILE)
                logger.info("[RemoteConfig] Cache cleared")
        except Exception as e:
            logger.warning(f"[RemoteConfig] Failed to clear cache: {e}")


def get_config() -> RemoteConfigManager:
    """Get the singleton RemoteConfigManager instance."""
    return RemoteConfigManager()
