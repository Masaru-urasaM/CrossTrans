"""
AI API Manager for CrossTrans.
Handles communication with various AI providers (Google, OpenAI, Anthropic, Groq, etc.)
"""
import json
import time
import urllib.request
import urllib.error
import logging
from typing import Optional, List, Dict, Any, Callable, TYPE_CHECKING

import google.generativeai as genai

from src.constants import MODEL_PROVIDER_MAP, API_KEY_PATTERNS
from src.core.multimodal import MultimodalProcessor
from src.core.ssl_pinning import get_ssl_context_for_url

# Default models to try for each provider when model is "Auto"
# Ordered by preference (best models first)
DEFAULT_MODELS_BY_PROVIDER = {
    'google': ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro'],
    'openai': ['gpt-4o-mini', 'gpt-4o', 'gpt-3.5-turbo'],
    'anthropic': ['claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022', 'claude-3-haiku-20240307'],
    'groq': ['llama-3.3-70b-versatile', 'llama-3.1-70b-versatile', 'mixtral-8x7b-32768'],
    'deepseek': ['deepseek-chat', 'deepseek-coder'],
    'xai': ['grok-2', 'grok-beta'],
    'mistral': ['mistral-large-latest', 'mistral-small-latest'],
    'perplexity': ['sonar', 'sonar-pro'],
    'cerebras': ['llama-3.3-70b', 'llama3.1-70b'],
    'sambanova': ['Meta-Llama-3.3-70B-Instruct', 'Meta-Llama-3.1-70B-Instruct'],
    'together': ['meta-llama/Llama-3.3-70B-Instruct-Turbo', 'meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo'],
    'siliconflow': ['deepseek-ai/DeepSeek-V3', 'Qwen/Qwen2.5-72B-Instruct'],
    'openrouter': ['google/gemini-2.0-flash-exp:free', 'meta-llama/llama-3.3-70b-instruct:free'],
}

if TYPE_CHECKING:
    from src.core.provider_health import ProviderHealthManager


class AIAPIManager:
    """
    Manages AI API with primary/backup key fallback and smart provider selection.
    Uses AI model for fast translations.
    Supports: Google Gemini, OpenAI, Anthropic, Groq, xAI, DeepSeek, Mistral, Perplexity,
              Cerebras, SambaNova, Together, SiliconFlow, OpenRouter.

    Features:
    - Multi-provider support with auto-detection
    - Smart fallback with health tracking
    - Adaptive timeouts based on provider performance
    - Circuit breaker for failing providers
    - Auto-model detection when model is not specified
    """

    MODEL_NAME: str = ''

    # Class-level cache for working models (key: api_key_prefix -> model_name)
    _working_models_cache: Dict[str, str] = {}

    def __init__(self) -> None:
        self.api_configs: List[Dict[str, Any]] = []
        self.notification_callback: Optional[Callable[[str], None]] = None
        self.health_manager: Optional['ProviderHealthManager'] = None

    def configure(self, api_configs: List[Dict[str, Any]],
                  notification_callback: Optional[Callable[[str], None]] = None,
                  health_manager: Optional['ProviderHealthManager'] = None) -> None:
        """Configure the API with list of {model_name, api_key, provider}."""
        self.api_configs = api_configs
        self.notification_callback = notification_callback
        self.health_manager = health_manager

    def _identify_provider(self, model_name: str, api_key: str = "") -> str:  # noqa: C901
        """
        Identify API provider based on model name and API key format.

        Priority:
        1. Exact match in MODEL_PROVIDER_MAP (case-insensitive)
        2. Explicit provider prefix (openrouter/, together/, etc.)
        3. API key pattern (gsk_, sk-ant-, etc.)
        4. Model name pattern matching
        5. Default fallback
        """
        model = model_name.strip()
        model_lower = model.lower()
        key = api_key.strip()

        # 1. HIGHEST PRIORITY: Exact match in MODEL_PROVIDER_MAP
        for provider, models in MODEL_PROVIDER_MAP.items():
            for m in models:
                if m.lower() == model_lower:
                    return provider

        # 2. Check for explicit provider prefixes
        if model_lower.startswith('openrouter/'): return 'openrouter'
        if model_lower.startswith('together/') or model_lower.startswith('meta-llama/'): return 'together'
        if model_lower.startswith('silicon/') or model_lower.startswith('sf/'): return 'siliconflow'

        # 3. Model name contains "/" - likely Together or SiliconFlow format
        if '/' in model:
            # SiliconFlow patterns
            if any(model.startswith(p) for p in ['Qwen/', 'deepseek-ai/', 'THUDM/', '01-ai/', 'internlm/', 'Pro/']):
                return 'siliconflow'
            # Together patterns
            if any(model.startswith(p) for p in ['meta-llama/', 'mistralai/', 'google/']):
                return 'together'

        # 4. API Key Patterns
        for pattern, provider in API_KEY_PATTERNS.items():
            if key.startswith(pattern):
                return provider

        # 5. Proprietary Models
        if 'gemini' in model_lower:
            return 'google'
        if 'claude' in model_lower:
            return 'anthropic'
        if 'gpt' in model_lower or model_lower.startswith('o1') or model_lower.startswith('o3') or 'dall-e' in model_lower:
            return 'openai'
        if 'grok' in model_lower:
            return 'xai'

        # 6. Official Provider Models
        if model_lower.startswith('deepseek-'):
            return 'deepseek'

        if any(model_lower.startswith(p) for p in ['mistral-', 'codestral-', 'pixtral-', 'ministral-', 'open-mistral', 'open-mixtral']):
            return 'mistral'

        if 'sonar' in model_lower:
            return 'perplexity'

        # 7. Groq-specific model signatures
        groq_suffixes = ['-32768', '-8192', '-versatile', '-instant', '-preview', '-specdec']
        if any(model_lower.endswith(s) for s in groq_suffixes):
            return 'groq'

        if '/' not in model and any(model_lower.startswith(p) for p in ['llama3-', 'llama-3', 'gemma-', 'gemma2-', 'mixtral-', 'whisper-', 'distil-']):
            return 'groq'

        # 8. SambaNova: Meta-Llama-xxx format
        if model.startswith('Meta-Llama-'):
            return 'sambanova'

        # 9. Cerebras: llama3.1-xxx format (with dot)
        if model_lower.startswith('llama3.'):
            return 'cerebras'

        # 10. Generic fallback
        if 'qwen' in model_lower or model_lower.startswith('yi-'):
            return 'siliconflow'

        if any(x in model_lower for x in ['llama', 'mixtral', 'gemma', 'whisper']):
            return 'groq'

        return 'google'  # Ultimate fallback

    def _make_request_with_retry(self, url: str, data: dict, headers: dict,
                                  response_parser: Callable[[dict], str],
                                  timeout: int = 10, max_retries: int = 3) -> str:
        """Make HTTP request with retry logic for rate limits and transient errors.

        Args:
            url: API endpoint URL
            data: Request body as dict (will be JSON encoded)
            headers: HTTP headers
            response_parser: Function to extract response text from JSON result
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts

        Returns:
            Extracted response text

        Raises:
            Exception: On authentication failure, rate limit exceeded, or network errors
        """
        ssl_context = get_ssl_context_for_url(url)

        for attempt in range(max_retries):
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode('utf-8'),
                headers=headers,
                method="POST"
            )

            try:
                with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as response:
                    result = json.loads(response.read().decode('utf-8'))
                    return response_parser(result)

            except urllib.error.HTTPError as e:
                if e.code == 429:  # Rate limit
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # 1s, 2s, 4s
                        logging.warning(f"Rate limit hit, waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise Exception(f"Rate limit exceeded after {max_retries} retries")

                elif e.code in (401, 403):
                    raise Exception("API_KEY_INVALID: Authentication failed")

                elif e.code >= 500:
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt
                        logging.warning(f"Server error {e.code}, waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise Exception(f"Server error {e.code} after {max_retries} retries")
                else:
                    raise  # Re-raise other HTTP errors

            except urllib.error.URLError as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logging.warning(f"Network error, waiting {wait_time}s before retry: {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    raise Exception(f"Network error after {max_retries} retries: {e}")

        # Should not reach here, but just in case
        raise Exception("Request failed after all retries")

    def _call_generic_openai_style(self, api_key: str, model_name: str, prompt: str,
                                     base_url: str, image_path: Optional[str] = None) -> str:
        """Helper for OpenAI-compatible APIs with rate limit handling."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }

        messages = []
        if image_path:
            # Vision request
            b64_data, mime_type = MultimodalProcessor.encode_image_base64(image_path)
            if b64_data:
                content = [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}}
                ]
                messages.append({"role": "user", "content": content})
            else:
                messages.append({"role": "user", "content": prompt})
        else:
            messages.append({"role": "user", "content": prompt})

        data = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.3
        }

        # OpenAI response parser
        def parse_openai_response(result: dict) -> str:
            return result['choices'][0]['message']['content'].strip()

        return self._make_request_with_retry(
            url=base_url,
            data=data,
            headers=headers,
            response_parser=parse_openai_response,
            timeout=10
        )

    def _call_anthropic(self, api_key: str, model_name: str, prompt: str,
                         image_path: Optional[str] = None) -> str:
        """Helper for Anthropic Claude API with rate limit handling."""
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }

        content = []
        if image_path:
            b64_data, mime_type = MultimodalProcessor.encode_image_base64(image_path)
            if b64_data:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": b64_data
                    }
                })

        content.append({"type": "text", "text": prompt})

        data = {
            "model": model_name,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": content}]
        }

        # Anthropic response parser
        def parse_anthropic_response(result: dict) -> str:
            return result['content'][0]['text'].strip()

        return self._make_request_with_retry(
            url=url,
            data=data,
            headers=headers,
            response_parser=parse_anthropic_response,
            timeout=10
        )

    def _generate_content(self, provider: str, api_key: str, model_name: str,
                           prompt: str, image_path: Optional[str] = None) -> str:
        """Route the request to the correct provider."""

        # --- Google (SDK) ---
        if provider == 'google':
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)
            if image_path:
                import PIL.Image
                img = PIL.Image.open(image_path)
                response = model.generate_content([prompt, img])
            else:
                response = model.generate_content(prompt)
            return response.text.strip()

        # --- Anthropic ---
        elif provider == 'anthropic':
            return self._call_anthropic(api_key, model_name, prompt, image_path)

        # --- OpenAI Compatible APIs ---
        base_urls = {
            'openai': "https://api.openai.com/v1/chat/completions",
            'groq': "https://api.groq.com/openai/v1/chat/completions",
            'deepseek': "https://api.deepseek.com/chat/completions",
            'mistral': "https://api.mistral.ai/v1/chat/completions",
            'xai': "https://api.x.ai/v1/chat/completions",
            'perplexity': "https://api.perplexity.ai/chat/completions",
            'cerebras': "https://api.cerebras.ai/v1/chat/completions",
            'sambanova': "https://api.sambanova.ai/v1/chat/completions",
            'together': "https://api.together.xyz/v1/chat/completions",
            'siliconflow': "https://api.siliconflow.cn/v1/chat/completions",
            'openrouter': "https://openrouter.ai/api/v1/chat/completions",
        }

        if provider in base_urls:
            return self._call_generic_openai_style(api_key, model_name, prompt, base_urls[provider], image_path)

        raise Exception(f"Unknown provider: {provider}")

    def get_display_name(self, provider_code: str) -> str:
        """Get nice display name for provider."""
        display_map = {
            'google': 'Google (Gemini)',
            'openai': 'OpenAI',
            'anthropic': 'Anthropic (Claude)',
            'groq': 'Groq',
            'xai': 'xAI (Grok)',
            'deepseek': 'DeepSeek',
            'mistral': 'Mistral AI',
            'perplexity': 'Perplexity',
            'cerebras': 'Cerebras',
            'sambanova': 'SambaNova',
            'together': 'Together AI',
            'siliconflow': 'SiliconFlow',
            'openrouter': 'OpenRouter'
        }
        return display_map.get(provider_code.lower(), provider_code.title())

    def test_connection(self, model_name: str, api_key: str, provider: str = 'Auto') -> bool:
        """Test connection with a specific model and key."""
        try:
            target_provider = self._identify_provider(model_name, api_key) if provider == 'Auto' else provider.lower()
            self._generate_content(target_provider, api_key, model_name, "Say OK")
            return True
        except Exception as e:
            raise e

    def _get_api_key_prefix(self, api_key: str) -> str:
        """Get a prefix of API key for caching (to avoid storing full key)."""
        return api_key[:12] if len(api_key) > 12 else api_key

    def _detect_provider_from_key(self, api_key: str) -> str:
        """Detect provider from API key pattern."""
        for pattern, provider in API_KEY_PATTERNS.items():
            if api_key.startswith(pattern):
                return provider
        # Default to google if can't detect
        return 'google'

    def _try_auto_detect_model(self, api_key: str, provider: str, prompt: str) -> Optional[str]:
        """Try to auto-detect a working model for the given provider.

        Tries models from DEFAULT_MODELS_BY_PROVIDER until one works.
        Caches the working model for future use.

        Returns:
            Translation result if successful, None if all models failed.
        """
        key_prefix = self._get_api_key_prefix(api_key)

        # Check if we have a cached working model
        cached_model = self._working_models_cache.get(key_prefix)
        if cached_model:
            logging.info(f"[Auto-Model] Trying cached model: {cached_model}")
            try:
                result = self._generate_content(provider, api_key, cached_model, prompt)
                logging.info(f"[Auto-Model] Cached model {cached_model} worked!")
                return result
            except Exception as e:
                logging.warning(f"[Auto-Model] Cached model {cached_model} failed: {e}")
                # Clear cache and try all models
                del self._working_models_cache[key_prefix]

        # Try models for this provider
        models_to_try = DEFAULT_MODELS_BY_PROVIDER.get(provider, [])
        if not models_to_try:
            logging.warning(f"[Auto-Model] No default models for provider: {provider}")
            return None

        for model in models_to_try:
            logging.info(f"[Auto-Model] Trying model: {model}")
            try:
                result = self._generate_content(provider, api_key, model, prompt)
                # Success! Cache this model
                self._working_models_cache[key_prefix] = model
                logging.info(f"[Auto-Model] Model {model} works! Cached for future use.")
                return result
            except Exception as e:
                logging.warning(f"[Auto-Model] Model {model} failed: {e}")
                continue

        return None

    def translate(self, prompt: str) -> str:
        """Translate text using configured keys with smart fallback."""
        if not self.api_configs:
            raise Exception("API not configured. Please set your API key in Settings.")

        errors = []
        has_valid_key = False

        # Prepare configs with provider info for sorting
        configs_with_providers = []
        for i, config in enumerate(self.api_configs):
            api_key = config.get('api_key', '').strip()
            model_name = config.get('model_name', '').strip()
            provider_setting = config.get('provider', 'Auto')

            if not api_key:
                continue

            # Handle empty model name (Auto mode)
            if not model_name:
                # Detect provider from key or use setting
                if provider_setting == 'Auto':
                    target_provider = self._detect_provider_from_key(api_key)
                else:
                    target_provider = provider_setting.lower()

                # Try auto-detect model
                logging.info(f"[API] Key #{i+1}: Model is Auto, detecting for provider {target_provider}...")
                result = self._try_auto_detect_model(api_key, target_provider, prompt)
                if result:
                    return result
                else:
                    errors.append(f"Key #{i+1}: Auto-detection failed for all models")
                    continue

            target_provider = self._identify_provider(model_name, api_key) if provider_setting == 'Auto' else provider_setting.lower()
            configs_with_providers.append({
                'config': config,
                'provider': target_provider,
                'api_key': api_key,
                'model_name': model_name,
                'index': i
            })

        if not configs_with_providers:
            if errors:
                raise Exception("No valid API configuration.\n" + "\n".join(errors))
            raise Exception("No valid API key configured. Please add an API key in Settings.")

        # Sort by provider health if health manager is available
        if self.health_manager:
            # Get unique providers and their priority
            providers = list(set(c['provider'] for c in configs_with_providers))
            sorted_providers = self.health_manager.get_priority_sorted_providers(providers)

            # Sort configs by provider priority
            provider_priority = {p: i for i, p in enumerate(sorted_providers)}
            configs_with_providers.sort(key=lambda c: provider_priority.get(c['provider'], 999))

            logging.debug(f"[API] Provider order after sorting: {[c['provider'] for c in configs_with_providers]}")

        # Try each config in order
        for item in configs_with_providers:
            has_valid_key = True
            config = item['config']
            target_provider = item['provider']
            api_key = item['api_key']
            model_name = item['model_name']

            # Get adaptive timeout if health manager available
            timeout = None
            if self.health_manager:
                timeout = self.health_manager.get_adaptive_timeout(target_provider)

            start_time = time.time()
            try:
                result = self._generate_content(target_provider, api_key, model_name, prompt)

                # Record success
                if self.health_manager:
                    response_time_ms = int((time.time() - start_time) * 1000)
                    self.health_manager.record_success(target_provider, response_time_ms)

                return result

            except Exception as e:
                # Record failure
                if self.health_manager:
                    self.health_manager.record_failure(target_provider)

                logging.warning(f"[API] Failed with {model_name} ({target_provider}): {e}")
                errors.append(f"{model_name}: {str(e)}")
                continue

        if not has_valid_key:
            raise Exception("No valid API key configured. Please add an API key in Settings.")

        raise Exception("All API keys failed.\n" + "\n".join(errors))

    def translate_image(self, prompt: str, image_path: str) -> str:
        """Translate/Analyze image using configured keys with smart fallback."""
        if not self.api_configs:
            raise Exception("API not configured. Please set your API key in Settings.")

        errors = []
        has_valid_key = False

        # Prepare vision-capable configs
        vision_configs = []
        for i, config in enumerate(self.api_configs):
            api_key = config.get('api_key', '').strip()
            model_name = config.get('model_name', '').strip()
            provider_setting = config.get('provider', 'Auto')

            if not api_key or not model_name:
                continue

            target_provider = self._identify_provider(model_name, api_key) if provider_setting == 'Auto' else provider_setting.lower()

            # Check vision capability
            if not MultimodalProcessor.is_vision_capable(model_name, target_provider):
                continue

            vision_configs.append({
                'config': config,
                'provider': target_provider,
                'api_key': api_key,
                'model_name': model_name
            })

        if not vision_configs:
            raise Exception("No configured API supports vision. Please use a vision-capable model (e.g., Gemini 2.0 Flash, GPT-4o).")

        # Sort by provider health if health manager is available
        if self.health_manager:
            providers = list(set(c['provider'] for c in vision_configs))
            sorted_providers = self.health_manager.get_priority_sorted_providers(providers)
            provider_priority = {p: i for i, p in enumerate(sorted_providers)}
            vision_configs.sort(key=lambda c: provider_priority.get(c['provider'], 999))

        # Try each config
        for item in vision_configs:
            has_valid_key = True
            target_provider = item['provider']
            api_key = item['api_key']
            model_name = item['model_name']

            start_time = time.time()
            try:
                result = self._generate_content(target_provider, api_key, model_name, prompt, image_path)

                # Record success
                if self.health_manager:
                    response_time_ms = int((time.time() - start_time) * 1000)
                    self.health_manager.record_success(target_provider, response_time_ms)

                return result

            except Exception as e:
                # Record failure
                if self.health_manager:
                    self.health_manager.record_failure(target_provider)

                errors.append(f"{model_name}: {str(e)}")
                continue

        raise Exception("All vision APIs failed.\n" + "\n".join(errors))

    def translate_multimodal(self, prompt: str,
                              image_paths: Optional[List[str]] = None,
                              file_contents: Optional[Dict[str, str]] = None) -> str:
        """Translate with multiple images and file contents in ONE request.

        Args:
            prompt: Translation instructions
            image_paths: List of image file paths
            file_contents: Dict of {filename: content} for text files

        Returns:
            Combined translation result
        """
        if not self.api_configs:
            raise Exception("API not configured. Please set your API key in Settings.")

        image_paths = image_paths or []
        file_contents = file_contents or {}
        needs_vision = len(image_paths) > 0

        errors = []

        # Prepare configs
        multimodal_configs = []
        for i, config in enumerate(self.api_configs):
            api_key = config.get('api_key', '').strip()
            model_name = config.get('model_name', '').strip()
            provider_setting = config.get('provider', 'Auto')

            if not api_key or not model_name:
                continue

            target_provider = self._identify_provider(model_name, api_key) if provider_setting == 'Auto' else provider_setting.lower()

            # If we have images, check vision capability
            if needs_vision and not MultimodalProcessor.is_vision_capable(model_name, target_provider):
                continue

            multimodal_configs.append({
                'config': config,
                'provider': target_provider,
                'api_key': api_key,
                'model_name': model_name
            })

        if not multimodal_configs:
            if needs_vision:
                raise Exception("No configured API supports vision. Please use a vision-capable model (e.g., Gemini 2.0 Flash, GPT-4o).")
            else:
                raise Exception("No valid API key configured. Please add an API key in Settings.")

        # Sort by provider health if health manager is available
        if self.health_manager:
            providers = list(set(c['provider'] for c in multimodal_configs))
            sorted_providers = self.health_manager.get_priority_sorted_providers(providers)
            provider_priority = {p: i for i, p in enumerate(sorted_providers)}
            multimodal_configs.sort(key=lambda c: provider_priority.get(c['provider'], 999))

        # Try each config
        for item in multimodal_configs:
            target_provider = item['provider']
            api_key = item['api_key']
            model_name = item['model_name']

            start_time = time.time()
            try:
                result = self._generate_content_multimodal(
                    target_provider, api_key, model_name, prompt, image_paths, file_contents
                )

                # Record success
                if self.health_manager:
                    response_time_ms = int((time.time() - start_time) * 1000)
                    self.health_manager.record_success(target_provider, response_time_ms)

                return result

            except Exception as e:
                # Record failure
                if self.health_manager:
                    self.health_manager.record_failure(target_provider)

                errors.append(f"{model_name}: {str(e)}")
                continue

        raise Exception("All API calls failed.\n" + "\n".join(errors))

    def _generate_content_multimodal(self, provider: str, api_key: str, model_name: str,
                                      prompt: str, image_paths: List[str],
                                      file_contents: Dict[str, str]) -> str:
        """Generate content with multiple images and file contents."""
        import PIL.Image
        import os

        # Build the full prompt with file contents embedded
        full_prompt = prompt
        if file_contents:
            file_section = "\n\n--- Attached File Contents ---\n"
            for filename, content in file_contents.items():
                file_section += f"\n**{filename}:**\n{content}\n"
            full_prompt = prompt + file_section

        # --- Google (SDK) - supports multiple images natively ---
        if provider == 'google':
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(model_name)

            content_parts = [full_prompt]
            for img_path in image_paths:
                if os.path.exists(img_path):
                    img = PIL.Image.open(img_path)
                    content_parts.append(img)

            response = model.generate_content(content_parts)
            return response.text.strip()

        # --- Anthropic - supports multiple images ---
        elif provider == 'anthropic':
            return self._call_anthropic_multimodal(api_key, model_name, full_prompt, image_paths)

        # --- OpenAI Compatible APIs ---
        base_urls = {
            'openai': "https://api.openai.com/v1/chat/completions",
            'groq': "https://api.groq.com/openai/v1/chat/completions",
            'deepseek': "https://api.deepseek.com/chat/completions",
            'mistral': "https://api.mistral.ai/v1/chat/completions",
            'xai': "https://api.x.ai/v1/chat/completions",
            'perplexity': "https://api.perplexity.ai/chat/completions",
            'cerebras': "https://api.cerebras.ai/v1/chat/completions",
            'sambanova': "https://api.sambanova.ai/v1/chat/completions",
            'together': "https://api.together.xyz/v1/chat/completions",
            'siliconflow': "https://api.siliconflow.cn/v1/chat/completions",
            'openrouter': "https://openrouter.ai/api/v1/chat/completions",
        }

        if provider in base_urls:
            return self._call_openai_style_multimodal(api_key, model_name, full_prompt, base_urls[provider], image_paths)

        raise Exception(f"Unknown provider: {provider}")

    def _call_openai_style_multimodal(self, api_key: str, model_name: str, prompt: str,
                                        base_url: str, image_paths: List[str]) -> str:
        """Helper for OpenAI-compatible APIs with multiple images."""
        import os

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }

        # Build content array with text + all images
        content = [{"type": "text", "text": prompt}]

        for img_path in image_paths:
            if os.path.exists(img_path):
                b64_data, mime_type = MultimodalProcessor.encode_image_base64(img_path)
                if b64_data:
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}
                    })

        messages = [{"role": "user", "content": content}]

        data = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.3
        }

        # OpenAI response parser
        def parse_openai_response(result: dict) -> str:
            return result['choices'][0]['message']['content'].strip()

        return self._make_request_with_retry(
            url=base_url,
            data=data,
            headers=headers,
            response_parser=parse_openai_response,
            timeout=60  # Longer timeout for multi-image processing
        )

    def _call_anthropic_multimodal(self, api_key: str, model_name: str, prompt: str,
                                     image_paths: List[str]) -> str:
        """Helper for Anthropic Claude API with multiple images."""
        import os

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }

        content = []

        # Add all images first
        for img_path in image_paths:
            if os.path.exists(img_path):
                b64_data, mime_type = MultimodalProcessor.encode_image_base64(img_path)
                if b64_data:
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": b64_data
                        }
                    })

        # Add text prompt
        content.append({"type": "text", "text": prompt})

        data = {
            "model": model_name,
            "max_tokens": 4096,  # Larger for multi-image responses
            "messages": [{"role": "user", "content": content}]
        }

        # Anthropic response parser
        def parse_anthropic_response(result: dict) -> str:
            return result['content'][0]['text'].strip()

        return self._make_request_with_retry(
            url=url,
            data=data,
            headers=headers,
            response_parser=parse_anthropic_response,
            timeout=60  # Longer timeout for multi-image processing
        )
