"""
Constants and configuration values for CrossTrans.
"""

# ============== VERSION ==============
VERSION = "1.9.9"
APP_NAME = "CrossTrans"
GITHUB_REPO = "Masaru-urasaM/CrossTrans"
FEEDBACK_URL = f"https://github.com/{GITHUB_REPO}/issues/new"

# ============== NETWORK ==============
LOCK_PORT = 47823  # Port for single instance lock

# ============== REMOTE CONFIG ==============
REMOTE_CONFIG_URL = "https://crossname.trial-api.workers.dev/v1/config"
REMOTE_CONFIG_CACHE_TTL = 86400  # 24 hours in seconds

# ============== TIMING ==============
COOLDOWN = 2.0  # Translation cooldown in seconds

# ============== AVAILABLE LANGUAGES ==============
# Format: (English name, ISO code, Native name)
LANGUAGES = [
    ("Vietnamese", "vi", "Tiếng Việt"),
    ("English", "en", "English"),
    ("Japanese", "ja", "日本語"),
    ("Chinese Simplified", "zh-CN", "中文简体"),
    ("Chinese Traditional", "zh-TW", "中文繁體"),
    ("Korean", "ko", "한국어"),
    ("French", "fr", "Français"),
    ("German", "de", "Deutsch"),
    ("Spanish", "es", "Español"),
    ("Italian", "it", "Italiano"),
    ("Portuguese", "pt", "Português"),
    ("Russian", "ru", "Русский"),
    ("Thai", "th", "ไทย"),
    ("Indonesian", "id", "Bahasa Indonesia"),
    ("Malay", "ms", "Bahasa Melayu"),
    ("Hindi", "hi", "हिन्दी"),
    ("Arabic", "ar", "العربية"),
    ("Dutch", "nl", "Nederlands"),
    ("Polish", "pl", "Polski"),
    ("Turkish", "tr", "Türkçe"),
    ("Swedish", "sv", "Svenska"),
    ("Danish", "da", "Dansk"),
    ("Norwegian", "no", "Norsk"),
    ("Finnish", "fi", "Suomi"),
    ("Greek", "el", "Ελληνικά"),
    ("Czech", "cs", "Čeština"),
    ("Romanian", "ro", "Română"),
    ("Hungarian", "hu", "Magyar"),
    ("Ukrainian", "uk", "Українська"),
    ("Afrikaans", "af", "Afrikaans"),
    ("Albanian", "sq", "Shqip"),
    ("Amharic", "am", "አማርኛ"),
    ("Armenian", "hy", "Հայերեն"),
    ("Azerbaijani", "az", "Azərbaycan"),
    ("Basque", "eu", "Euskara"),
    ("Belarusian", "be", "Беларуская"),
    ("Bengali", "bn", "বাংলা"),
    ("Bosnian", "bs", "Bosanski"),
    ("Bulgarian", "bg", "Български"),
    ("Catalan", "ca", "Català"),
    ("Cebuano", "ceb", "Cebuano"),
    ("Chichewa", "ny", "Chichewa"),
    ("Corsican", "co", "Corsu"),
    ("Croatian", "hr", "Hrvatski"),
    ("Esperanto", "eo", "Esperanto"),
    ("Estonian", "et", "Eesti"),
    ("Filipino", "tl", "Filipino"),
    ("Frisian", "fy", "Frysk"),
    ("Galician", "gl", "Galego"),
    ("Georgian", "ka", "ქართული"),
    ("Gujarati", "gu", "ગુજરાતી"),
    ("Haitian Creole", "ht", "Kreyòl Ayisyen"),
    ("Hausa", "ha", "Hausa"),
    ("Hawaiian", "haw", "Ōlelo Hawaiʻi"),
    ("Hebrew", "iw", "עברית"),
    ("Hmong", "hmn", "Hmoob"),
    ("Icelandic", "is", "Íslenska"),
    ("Igbo", "ig", "Igbo"),
    ("Irish", "ga", "Gaeilge"),
    ("Javanese", "jw", "Jawa"),
    ("Kannada", "kn", "ಕನ್ನಡ"),
    ("Kazakh", "kk", "Қазақ"),
    ("Khmer", "km", "ខ្មែរ"),
    ("Kurdish (Kurmanji)", "ku", "Kurdî"),
    ("Kyrgyz", "ky", "Кыргызча"),
    ("Lao", "lo", "ລາວ"),
    ("Latin", "la", "Latina"),
    ("Latvian", "lv", "Latviešu"),
    ("Lithuanian", "lt", "Lietuvių"),
    ("Luxembourgish", "lb", "Lëtzebuergesch"),
    ("Macedonian", "mk", "Македонски"),
    ("Malagasy", "mg", "Malagasy"),
    ("Malayalam", "ml", "മലയാളം"),
    ("Maltese", "mt", "Malti"),
    ("Maori", "mi", "Māori"),
    ("Marathi", "mr", "मराठी"),
    ("Mongolian", "mn", "Монгол"),
    ("Myanmar (Burmese)", "my", "မြန်မာ"),
    ("Nepali", "ne", "नेपाली"),
    ("Pashto", "ps", "پښتو"),
    ("Persian", "fa", "فارسی"),
    ("Punjabi", "pa", "ਪੰਜਾਬੀ"),
    ("Samoan", "sm", "Gagana faʻa Sāmoa"),
    ("Scots Gaelic", "gd", "Gàidhlig"),
    ("Serbian", "sr", "Српски"),
    ("Sesotho", "st", "Sesotho"),
    ("Shona", "sn", "chiShona"),
    ("Sindhi", "sd", "سنڌي"),
    ("Sinhala", "si", "සිංහල"),
    ("Slovak", "sk", "Slovenčina"),
    ("Slovenian", "sl", "Slovenščina"),
    ("Somali", "so", "Soomaali"),
    ("Sundanese", "su", "Basa Sunda"),
    ("Swahili", "sw", "Kiswahili"),
    ("Tajik", "tg", "Тоҷикӣ"),
    ("Tamil", "ta", "தமிழ்"),
    ("Telugu", "te", "తెలుగు"),
    ("Urdu", "ur", "اردو"),
    ("Uzbek", "uz", "Oʻzbek"),
    ("Welsh", "cy", "Cymraeg"),
    ("Xhosa", "xh", "isiXhosa"),
    ("Yiddish", "yi", "ייִדיש"),
    ("Yoruba", "yo", "Yorùbá"),
    ("Zulu", "zu", "isiZulu"),
]

# ============== AI PROVIDERS ==============
PROVIDERS_LIST = [
    "Auto", "Google", "OpenAI", "Anthropic", "DeepSeek",
    "Groq", "xAI", "Mistral", "Perplexity", "Cerebras",
    "SambaNova", "Together", "SiliconFlow", "OpenRouter", "HuggingFace"
]

# Maps specific model patterns to their native providers
# Keys match PROVIDERS_LIST exactly (Title Case)
# Updated January 2026 with all active models
MODEL_PROVIDER_MAP = {
    # === GOOGLE (Gemini) ===
    'Google': [
        # Gemini 3.0 Series
        'gemini-3-flash',
        # Gemini 2.5 Series
        'gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.5-flash-lite',
        'gemini-2.5-flash-preview-image',
        # Gemini 2.0 Series
        'gemini-2.0-flash', 'gemini-2.0-flash-exp', 'gemini-2.0-flash-lite',
    ],
    # === OPENAI ===
    'OpenAI': [
        # O-Series (Reasoning)
        'o3', 'o3-mini', 'o3-pro',
        'o1', 'o1-preview', 'o1-mini', 'o1-pro',
        # GPT-4.1 Series
        'gpt-4.1', 'gpt-4.1-mini', 'gpt-4.1-nano',
        # GPT-4o Series
        'gpt-4o', 'gpt-4o-mini', 'gpt-4o-2024-11-20', 'gpt-4o-2024-08-06',
        'gpt-4o-audio-preview', 'gpt-4o-realtime-preview',
        # GPT-4 Turbo
        'gpt-4-turbo', 'gpt-4-turbo-preview', 'gpt-4-turbo-2024-04-09',
        # GPT-4 Base
        'gpt-4', 'gpt-4-0613', 'gpt-4-32k',
        # GPT-3.5
        'gpt-3.5-turbo', 'gpt-3.5-turbo-0125', 'gpt-3.5-turbo-16k',
    ],
    # === ANTHROPIC (Claude) ===
    'Anthropic': [
        # Claude 4.5 Series (Latest)
        'claude-opus-4-5-20251101', 'claude-sonnet-4-5-20251101', 'claude-haiku-4-5-20251101',
        # Claude 4 Series
        'claude-4-opus', 'claude-4-sonnet', 'claude-4-haiku',
        # Claude 3.5 Series
        'claude-3-5-sonnet-20241022', 'claude-3-5-sonnet-latest',
        'claude-3-5-haiku-20241022', 'claude-3-5-haiku-latest',
        # Claude 3 Series
        'claude-3-opus-20240229', 'claude-3-sonnet-20240229', 'claude-3-haiku-20240307',
    ],
    # === DEEPSEEK ===
    'DeepSeek': [
        'deepseek-chat', 'deepseek-coder', 'deepseek-reasoner',
        'deepseek-r1', 'deepseek-r1-lite',
        'deepseek-v3', 'deepseek-v2.5',
    ],
    # === GROQ ===
    'Groq': [
        # Llama 3.3
        'llama-3.3-70b-versatile', 'llama-3.3-70b-specdec',
        # Llama 3.2
        'llama-3.2-1b-preview', 'llama-3.2-3b-preview',
        'llama-3.2-11b-vision-preview', 'llama-3.2-90b-vision-preview',
        # Llama 3.1
        'llama-3.1-70b-versatile', 'llama-3.1-8b-instant',
        # Llama 3
        'llama3-70b-8192', 'llama3-8b-8192', 'llama-guard-3-8b',
        # Mixtral & Gemma
        'mixtral-8x7b-32768', 'gemma-7b-it', 'gemma2-9b-it',
        # Whisper (Audio)
        'whisper-large-v3', 'whisper-large-v3-turbo', 'distil-whisper-large-v3-en',
    ],
    # === XAI (Grok) ===
    'xAI': [
        'grok-3', 'grok-3-fast',
        'grok-2', 'grok-2-vision', 'grok-2-1212',
        'grok-beta', 'grok-vision-beta',
    ],
    # === MISTRAL AI ===
    'Mistral': [
        # Large Models
        'mistral-large-latest', 'mistral-large-2411', 'mistral-large-2407',
        # Medium & Small
        'mistral-medium-latest', 'mistral-small-latest', 'mistral-small-2409',
        # Ministral
        'ministral-8b-latest', 'ministral-3b-latest',
        # Open Models
        'open-mistral-nemo', 'open-mistral-7b', 'open-mixtral-8x7b', 'open-mixtral-8x22b',
        # Codestral
        'codestral-latest', 'codestral-mamba-latest',
        # Pixtral (Vision)
        'pixtral-large-latest', 'pixtral-12b-latest',
    ],
    # === PERPLEXITY ===
    'Perplexity': [
        # Sonar Series
        'sonar', 'sonar-pro', 'sonar-reasoning', 'sonar-reasoning-pro',
        'sonar-deep-research',
        # Legacy Sonar
        'llama-3.1-sonar-small-128k-online', 'llama-3.1-sonar-large-128k-online',
        'llama-3.1-sonar-huge-128k-online',
    ],
    # === CEREBRAS ===
    'Cerebras': [
        # Llama Series
        'llama-4-scout-17b', 'llama-4-maverick-17b',
        'llama-3.3-70b', 'llama3.1-8b', 'llama3.1-70b',
        # Qwen Series
        'qwen-3-32b',
    ],
    # === SAMBANOVA ===
    'SambaNova': [
        # DeepSeek
        'DeepSeek-R1', 'DeepSeek-R1-Distill-Llama-70B', 'DeepSeek-R1-Distill-Qwen-32B',
        # Llama 3.3
        'Meta-Llama-3.3-70B-Instruct',
        # Llama 3.2
        'Meta-Llama-3.2-1B-Instruct', 'Meta-Llama-3.2-3B-Instruct',
        # Llama 3.1
        'Meta-Llama-3.1-8B-Instruct', 'Meta-Llama-3.1-70B-Instruct', 'Meta-Llama-3.1-405B-Instruct',
        # Qwen
        'Qwen2.5-72B-Instruct', 'Qwen2.5-Coder-32B-Instruct', 'QwQ-32B-Preview',
    ],
    # === TOGETHER ===
    'Together': [
        # Llama 3.3
        'meta-llama/Llama-3.3-70B-Instruct-Turbo',
        # Llama 3.2
        'meta-llama/Llama-3.2-3B-Instruct-Turbo', 'meta-llama/Llama-3.2-11B-Vision-Instruct-Turbo',
        # Llama 3.1
        'meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo', 'meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo',
        'meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo',
        # Qwen
        'Qwen/Qwen2.5-7B-Instruct-Turbo', 'Qwen/Qwen2.5-72B-Instruct-Turbo',
        'Qwen/QwQ-32B-Preview',
        # Mistral
        'mistralai/Mixtral-8x7B-Instruct-v0.1', 'mistralai/Mistral-7B-Instruct-v0.3',
        # DeepSeek
        'deepseek-ai/DeepSeek-R1', 'deepseek-ai/DeepSeek-R1-Distill-Llama-70B',
        # Google
        'google/gemma-2-9b-it', 'google/gemma-2-27b-it',
    ],
    # === SILICONFLOW ===
    'SiliconFlow': [
        # Qwen Series
        'Qwen/Qwen2.5-7B-Instruct', 'Qwen/Qwen2.5-14B-Instruct', 'Qwen/Qwen2.5-32B-Instruct',
        'Qwen/Qwen2.5-72B-Instruct', 'Qwen/Qwen2.5-Coder-7B-Instruct',
        'Qwen/QwQ-32B-Preview', 'Qwen/Qwen2-VL-72B-Instruct',
        # DeepSeek
        'deepseek-ai/DeepSeek-V3', 'deepseek-ai/DeepSeek-V2.5', 'deepseek-ai/DeepSeek-R1',
        'deepseek-ai/DeepSeek-Coder-V2-Instruct',
        # GLM
        'THUDM/glm-4-9b-chat',
        # InternLM
        'internlm/internlm2_5-7b-chat',
        # Yi
        '01-ai/Yi-1.5-9B-Chat', '01-ai/Yi-1.5-34B-Chat',
        # Pro versions
        'Pro/Qwen/Qwen2.5-7B-Instruct', 'Pro/deepseek-ai/DeepSeek-V3',
    ],
    # === OPENROUTER (aggregator - common models) ===
    'OpenRouter': [
        # OpenAI
        'openai/gpt-4o', 'openai/gpt-4-turbo', 'openai/gpt-3.5-turbo', 'openai/o1', 'openai/o1-mini',
        # Anthropic
        'anthropic/claude-3.5-sonnet', 'anthropic/claude-3-opus', 'anthropic/claude-3-haiku',
        # Google
        'google/gemini-2.0-flash-exp', 'google/gemini-pro', 'google/gemini-flash-1.5',
        # Meta
        'meta-llama/llama-3.3-70b-instruct', 'meta-llama/llama-3.1-70b-instruct', 'meta-llama/llama-3.1-405b-instruct',
        # Mistral
        'mistralai/mistral-large', 'mistralai/mixtral-8x7b-instruct',
        # DeepSeek
        'deepseek/deepseek-chat', 'deepseek/deepseek-r1',
        # Qwen
        'qwen/qwen-2.5-72b-instruct', 'qwen/qwq-32b-preview',
    ],
    # === HUGGINGFACE ===
    'HuggingFace': [
        # Qwen Series
        'Qwen/Qwen2.5-72B-Instruct', 'Qwen/Qwen2.5-32B-Instruct', 'Qwen/Qwen2.5-14B-Instruct',
        'Qwen/Qwen2.5-7B-Instruct', 'Qwen/Qwen2.5-3B-Instruct', 'Qwen/Qwen2.5-Coder-32B-Instruct',
        # Llama Series
        'meta-llama/Llama-3.3-70B-Instruct', 'meta-llama/Llama-3.2-3B-Instruct',
        'meta-llama/Llama-3.1-8B-Instruct', 'meta-llama/Llama-3.1-70B-Instruct',
        # Mistral
        'mistralai/Mistral-7B-Instruct-v0.3', 'mistralai/Mixtral-8x7B-Instruct-v0.1',
        # Microsoft Phi
        'microsoft/Phi-3-mini-4k-instruct', 'microsoft/Phi-3.5-mini-instruct',
        # Google Gemma
        'google/gemma-2-9b-it', 'google/gemma-2-27b-it',
        # DeepSeek
        'deepseek-ai/DeepSeek-R1-Distill-Qwen-32B',
    ],
}

# API Key Patterns for provider detection
# Values match PROVIDERS_LIST exactly (Title Case)
API_KEY_PATTERNS = {
    'gsk_': 'Groq',           # Groq keys start with gsk_
    'sk-ant-': 'Anthropic',   # Anthropic keys start with sk-ant-
    'xai-': 'xAI',            # xAI keys start with xai-
    'sk-or-v1-': 'OpenRouter', # OpenRouter keys
    'pplx-': 'Perplexity',    # Perplexity keys
    'hf_': 'HuggingFace',     # HuggingFace keys start with hf_
    # Note: sk- is used by OpenAI, DeepSeek, Together, SiliconFlow - need model name
}

# ============== VISION MODELS ==============
# Models that support vision/image input. Supports wildcards (*).
# Note: Naming patterns like 'vision', 'VL', 'pixtral' are also detected in multimodal.py
VISION_MODELS = {
    'google': ['gemini-*'],  # All Gemini models support vision
    'openai': ['gpt-4-vision-*', 'gpt-4o', 'gpt-4o-*'],  # Note: o1 models do NOT support vision
    'anthropic': ['claude-3-*', 'claude-3.5-*', 'claude-3-5-*'],  # Wildcard support
    'groq': ['llama-3.2-*-vision-*', 'llava-*'],
    'xai': ['grok-*-vision*', 'grok-vision-*'],
    'mistral': ['pixtral-*'],
    'together': ['meta-llama/Llama-3.2-*-Vision-*', 'Qwen/Qwen2-VL-*', '*-vision-*'],
    'siliconflow': ['Qwen/Qwen2-VL-*', '*-VL-*'],
    'openrouter': ['*'],  # OpenRouter aggregates models - rely on naming heuristics
}

# ============== TRIAL MODE ==============
# Configuration for trial mode (users without API keys)
TRIAL_MODE_ENABLED = True  # Set to False to disable trial mode completely
TRIAL_DAILY_QUOTA = 100  # Maximum translations per day
TRIAL_PROVIDER = "cerebras"  # Provider for trial mode (Cerebras has generous free tier)
TRIAL_MODEL = "llama-3.3-70b"  # Model for trial mode

# Proxy server URL for trial mode (protects your API key)
# Set this to your deployed Cloudflare Worker URL
# TRIAL_PROXY_URL = ""  # e.g., "https://your-translator-proxy.workers.dev/v1/translate"
TRIAL_PROXY_URL = "https://crossname.trial-api.workers.dev"

# Trial mode restrictions
TRIAL_VISION_ENABLED = False  # Vision/OCR disabled in trial mode
TRIAL_FILE_ENABLED = False  # File translation disabled in trial mode
