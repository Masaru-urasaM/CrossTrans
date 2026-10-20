"""
Constants and configuration values for CrossTrans.
"""

# ============== VERSION ==============
VERSION = "1.9.21"
APP_NAME = "CrossTrans"
GITHUB_REPO = "Masaru-urasaM/CrossTrans"
FEEDBACK_URL = f"https://github.com/{GITHUB_REPO}/issues/new"

# ============== NETWORK ==============
LOCK_PORT = 47823  # Port for single instance lock

# ============== REMOTE CONFIG ==============
REMOTE_CONFIG_URL = "https://crosstrans.trial-api.workers.dev/v1/config"
REMOTE_CONFIG_CACHE_TTL = 86400  # 24 hours in seconds

# ============== TIMING ==============
COOLDOWN = 2.0  # Translation cooldown in seconds
TRANSLATION_TIMEOUT_SECONDS = 20.0  # Whole request, including retries and fallback

# ============== FURIGANA ==============
# Every tuning knob for the Japanese reading guides, in one place. The engine
# (src/core/furigana.py), the renderer (src/ui/ruby_text.py) and the main
# window's Reading pane (src/app.py) alias these to their own short names, so a
# value is changed here and nowhere else.

# Cost guards. Both bound work that happens on the UI thread.
# Measured on Tk 8.6: 200 ruby pairs ~124 ms to build and lay out, 500 ~400 ms,
# 1000 ~626 ms. Above the pair cap the engine returns plain text; above the
# character cap the renderer skips annotation entirely (that one also bounds the
# tokenizer, which the pair cap cannot, since counting pairs means running it).
FURIGANA_MAX_RUBY_PAIRS = 400
FURIGANA_MAX_ANNOTATE_CHARS = 3000

# Text annotated by prewarm() to build the reading engine off the UI thread.
# It MUST contain kanji AND kana or should_annotate() rejects it and the prewarm
# silently does nothing; the all-kanji compound is what pulls in the pykakasi
# dictionary that _refine_compounds needs on every annotation.
FURIGANA_PREWARM_SAMPLE = "日本語を読む"

# Appearance. Yu Gothic renders kana at 7pt legibly; a Latin UI font does not.
FURIGANA_FONT_FAMILY = 'Yu Gothic'
FURIGANA_BASE_FONT_SIZE = 11
FURIGANA_RUBY_FONT_SIZE = 7

FURIGANA_DEFAULT_BG = '#2b2b2b'      # popup background
FURIGANA_BASE_FG = '#cccccc'         # plain (unannotated) runs
FURIGANA_KANJI_FG = '#ffffff'        # base characters under a reading
FURIGANA_RUBY_FG = '#80b8ff'         # the reading itself
FURIGANA_RUBY_BG = '#363636'         # opt-in plate; RubyText matches its own bg instead

FURIGANA_LINE_SPACING = 4            # spacing1 == spacing3 on the Text widget
FURIGANA_RUBY_PAD_X = 0              # per side, on both ruby labels (0 = Word-like, no gap)
FURIGANA_RUBY_PAD_Y = 1              # padding above the reading and below the base. The
                                     # bottom half is charged back by the baseline lift, so
                                     # changing it keeps the two in step - see ruby_text.
FURIGANA_WHEEL_UNITS = 3             # lines scrolled per wheel notch
FURIGANA_DEFAULT_MAX_ROWS = 12       # rows a RubyText grows to before scrolling

# Reading pane under the main window's input box.
FURIGANA_READING_PANE_DEBOUNCE_MS = 350  # keystroke burst absorbed before annotating
FURIGANA_READING_PANE_MAX_ROWS = 4       # taller than this and the pane scrolls

# ============== QUICK-TRANSLATE POPUP ==============
# How the quick-translate popup sizes itself (Decision 34, src/ui/popup_layout.py).
# Policy only: how tall or wide a widget is gets measured on the widget, never
# written down here - constants for that drifted once (the hidden close button).
POPUP_READING_CHARS_LATIN = 70      # characters per line, Latin text (WCAG 1.4.8: at most 80)
POPUP_READING_CHARS_CJK = 36        # characters per line, CJK text (WCAG 1.4.8: at most 40)
POPUP_HEIGHT_CAP_SHARE = 0.60       # of the monitor's work area; beyond it a box scrolls
POPUP_MAX_WIDTH_SHARE = 0.90        # of the monitor's work area
POPUP_ORIGINAL_SHARE = 0.40         # of the text room the original may keep when both overflow
POPUP_MIN_BOX_ROWS = 3              # a box squeezed by the cap still shows this many rows
POPUP_USER_MIN_ROWS = 1             # ...and by the user's own drag, this many
POPUP_COLLAPSED_ORIGINAL_ROWS = 3   # the original block (with readings) when collapsed
POPUP_ANCHOR_OFFSET = (15, 20)      # from the cursor to the popup's nearest corner
POPUP_SCREEN_MARGIN = 10            # kept clear along the work area's edges
POPUP_TOOLTIP_DELAY_MS = 500        # before an icon button names itself
POPUP_LAYOUT_WATCHDOG_MS = 300      # the popup is shown by then even if measuring never ran
POPUP_REVEAL_DELAY_MS = 30          # after the final size, for Tk to redraw before it is seen
POPUP_GRIP_PREVIEW_MS = 150         # a grip drag paused this long lays the popup out at its size
POPUP_FRONT_MS = 500                # on top this long after it appears, then free to go behind

LINKED_READING_DELAY_MS = 200
LINKED_READING_BG = '#35434b'
LINKED_READING_FADE_MS = 96
LINKED_READING_FADE_STEPS = 6

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
    # Verified 2026-09-08 by a real generateContent call per model. Six of the
    # eight IDs that used to sit here answer 404: the whole 2.0 line,
    # gemini-3-flash (the live name is gemini-3-flash-preview) and
    # gemini-2.5-flash-preview-image. gemini-2.5-pro is *listed* by the API and
    # still 404s on use ("no longer available to new users") - which is why
    # presence in /models is not the test here, a call is.
    # Chat models only: the same endpoint also serves tts, image, transcribe,
    # robotics, computer-use, lyria (music), nano-banana (image) and the agentic
    # deep-research / antigravity families, none of which translate.
    'Google': [
        # Gemini 3.x flash
        'gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.6-flash',
        'gemini-3.5-flash', 'gemini-3.5-flash-lite',
        'gemini-3.1-flash-lite', 'gemini-3-flash-preview',
        # Gemini 2.5
        'gemini-2.5-flash', 'gemini-2.5-flash-lite',
        # Aliases that follow the current release, so they cannot go stale
        'gemini-flash-latest', 'gemini-flash-lite-latest', 'gemini-pro-latest',
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
        # Claude 5.5 / Fable 5.1 - current, and the D11 defaults (K15, 2026-10-16)
        'claude-haiku-5-5', 'claude-sonnet-5-5', 'claude-opus-5-5', 'claude-fable-5-1',
        'claude-haiku-4-5',
        # Claude 4.5 Series
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
        # Current names in DeepSeek's API docs, and the D11 defaults (K15)
        'deepseek-flash', 'deepseek-v4-pro',
        'deepseek-chat', 'deepseek-coder', 'deepseek-reasoner',
        'deepseek-r1', 'deepseek-r1-lite',
        'deepseek-v3', 'deepseek-v2.5',
    ],
    # === GROQ ===
    # Verified against Groq's own /models endpoint 2026-09-07. The entire Llama
    # chat line is decommissioned: 15 of the 17 IDs that used to sit here are
    # gone, and the 2 survivors were whisper - a speech model that was never a
    # translation candidate. Only reached in tier-3 fallback (remote config
    # unreachable AND no local cache), which is exactly when offering a model
    # that 404s is worst. Live but deliberately absent: whisper / orpheus
    # (speech), *-guard and gpt-oss-safeguard (classifiers), allam-2-7b (Arabic
    # specialist, 4k ctx), groq/compound* (agentic - multi-step, and it cannot
    # hold the trial proxy's 15 s timeout).
    'Groq': [
        # GPT-OSS - 131k ctx, answers directly (measured: no reasoning preamble)
        'openai/gpt-oss-120b', 'openai/gpt-oss-20b',
        # Qwen 3 - 131k ctx, multilingual; emits <think>, which
        # text_cleanup.strip_thinking_tags() removes on every path
        'qwen/qwen3.6-27b', 'qwen/qwen3.8-27b',
    ],
    # === XAI (Grok) ===
    'xAI': [
        # The grok-4.x line - all xAI lists now; the first two are the D11 defaults (K15)
        'grok-4.20-0309-non-reasoning', 'grok-4.3', 'grok-4.7', 'grok-4.6', 'grok-4.5',
        'grok-4.20-0309-reasoning',
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
    # Cerebras serves exactly three models (its own /models, 2026-09-08 with a
    # real key). All SIX IDs that used to be here are gone - the whole Llama line
    # and qwen-3-32b - and llama-3.3-70b / llama3.1-70b answered a real request
    # with 404 "Model does not exist". The three below returned 402 "Payment
    # required" instead, which is the useful distinction: Cerebras validates the
    # model before it checks billing, so 402 proves the model exists where 404
    # proves it does not. Not callable beyond that - the key has no credit.
    'Cerebras': [
        'gpt-oss-120b', 'qwen-3.8-27b', 'gemma-4-31b',
    ],
    # === SAMBANOVA ===
    # SambaNova's own /models, 2026-09-08 with a real key: 11 of the 12 IDs that
    # used to be here are gone - every DeepSeek-R1 variant, the whole Llama 3.1/3.2
    # line and all three Qwen entries. Only Meta-Llama-3.3-70B-Instruct survived.
    # Weaker evidence than Cerebras and Google, deliberately noted: SambaNova checks
    # billing BEFORE model validity, so every call returned 402 - including one for
    # a model absent from its own catalogue. The listing is the only evidence here;
    # no model below has been sent a real translation.
    'SambaNova': [
        'Meta-Llama-3.3-70B-Instruct', 'gemma-4-31B-it', 'gpt-oss-120b',
        'DeepSeek-V3.2', 'DeepSeek-V3.1', 'MiniMax-M3', 'MiniMax-M2.7',
    ],
    # === TOGETHER ===
    'Together': [
        # The D11 defaults (K15): Together's named replacements. No prefix rule knows
        # meta-models/ or zai-org/, so without these entries they would route elsewhere.
        'meta-models/Muse-Glimmer-30B', 'zai-org/GLM-5.3-Flash',
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
    # Tier-3 fallback only: the Worker rebuilds this list from OpenRouter's live
    # catalogue on every cron, so tiers 1 and 2 already carry ~426 current IDs.
    # It is reached on a fresh install with no network, which is exactly when a
    # dead entry is least recoverable - and 9 of the 20 that used to be here were
    # dead (checked 2026-09-08 against the live catalogue AND the per-model
    # /endpoints resource, which agreed exactly): o1-mini, claude-3.5-sonnet,
    # claude-3-opus, gemini-2.0-flash-exp, gemini-pro, gemini-flash-1.5,
    # llama-3.1-405b-instruct, mixtral-8x7b-instruct, qwq-32b-preview.
    # Every ID below has at least one routable endpoint. No ':batch' variants -
    # those are async batch endpoints and cannot serve an interactive translation.
    'OpenRouter': [
        # OpenAI
        'openai/gpt-4o', 'openai/gpt-4o-mini', 'openai/gpt-4-turbo',
        'openai/gpt-3.5-turbo', 'openai/o1',
        # Anthropic
        'anthropic/claude-sonnet-5', 'anthropic/claude-opus-5', 'anthropic/claude-3-haiku',
        # Google
        'google/gemini-3.8-flash', 'google/gemini-2.5-flash', 'google/gemini-2.5-flash-lite',
        # Meta
        'meta-llama/llama-3.3-70b-instruct', 'meta-llama/llama-3.1-70b-instruct',
        'meta-llama/llama-4-maverick',
        # Mistral
        'mistralai/mistral-large', 'mistralai/mistral-medium-3-5',
        # DeepSeek
        'deepseek/deepseek-chat', 'deepseek/deepseek-r1',
        # Qwen
        'qwen/qwen-2.5-72b-instruct', 'qwen/qwen3.8-flash',
        # Free tier - these two are also the OpenRouter entries in
        # DEFAULT_MODELS_BY_PROVIDER, and they MUST stay listed here.
        # _identify_provider() matches this map first; miss it and
        # 'google/gemma-4-31b-it:free' falls through to the 'google/' prefix
        # rule, which answers Together and sends an sk-or-v1- key to the wrong
        # API. Measured 2026-09-08 on the tier-3 path, where this list is the
        # only one there is - and it is what the old defaults were doing.
        'google/gemma-4-31b-it:free', 'nvidia/nemotron-3.5-lightning:free',
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
    'csk-': 'Cerebras',       # Cerebras keys start with csk-
    # Note: sk- is used by OpenAI, DeepSeek, Together, SiliconFlow - need model name
    # SambaNova cannot be added: its keys are bare UUIDs with no prefix to match.
    # A provider missing from this table falls through _detect_provider_from_key()
    # to its 'default to Google' branch, so a Cerebras user with Provider=Auto and
    # a blank model field was being handed gemini-2.5-flash and sending it to
    # api.cerebras.ai (measured 2026-09-08).
}

# ============== VISION MODELS ==============
# Models that support vision/image input. Supports wildcards (*).
# Note: Naming patterns like 'vision', 'VL', 'pixtral' are also detected in multimodal.py
VISION_MODELS = {
    'google': ['gemini-*'],  # All Gemini models support vision
    'openai': ['gpt-4-vision-*', 'gpt-4o', 'gpt-4o-*'],  # Note: o1 models do NOT support vision
    'anthropic': ['claude-3-*', 'claude-3.5-*', 'claude-3-5-*'],  # Wildcard support
    # Measured 2026-09-07 with a 2x2 PNG: qwen3 accepts images; gpt-oss-*,
    # groq/compound* and allam-2-7b reject them ('content must be a string').
    # The llama-3.2 vision previews and llava are gone from Groq entirely.
    'groq': ['qwen/qwen3*'],
    'xai': ['grok-*-vision*', 'grok-vision-*'],
    'mistral': ['pixtral-*'],
    'together': ['meta-llama/Llama-3.2-*-Vision-*', 'Qwen/Qwen2-VL-*', '*-vision-*'],
    'siliconflow': ['Qwen/Qwen2-VL-*', '*-VL-*'],
    'openrouter': ['*'],  # OpenRouter aggregates models - rely on naming heuristics
}

# ============== TRIAL MODE ==============
# Configuration for trial mode (users without API keys)
TRIAL_MODE_ENABLED = True  # Set to False to disable trial mode completely
TRIAL_DAILY_QUOTA = 20  # Maximum translations per day
TRIAL_PROVIDER = "cerebras"  # Provider for trial mode (Cerebras has generous free tier)
TRIAL_MODEL = "llama-3.3-70b"  # Model for trial mode

# Proxy server URL for trial mode (protects your API key)
# Set this to your deployed Cloudflare Worker URL
# TRIAL_PROXY_URL = ""  # e.g., "https://your-translator-proxy.workers.dev/v1/translate"
TRIAL_PROXY_URL = "https://crosstrans.trial-api.workers.dev"

# Trial mode restrictions
TRIAL_VISION_ENABLED = False  # Vision/OCR disabled in trial mode
TRIAL_FILE_ENABLED = False  # File translation disabled in trial mode
