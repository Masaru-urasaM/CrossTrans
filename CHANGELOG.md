# Changelog

All notable changes to CrossTrans are documented here.

## [1.9.16] - Translation Cache, Re-translate & Custom Prompt

### R1 — Translation Cache + Re-translate Button
- **History-backed translation cache** — Identical source text with the same target language is served from the existing 100-entry history instead of calling the AI API again (saves quota/cost/latency, consistent output). Applies to plain translations only; custom-prompt requests are never cached.
- **`HistoryManager.find_cached(original, target_lang)`** — Exact-match lookup, most-recent-wins, skips `"Error:"` results
- **`translate_text(..., skip_cache=False)`** — Cache lookup before the API call; early return on hit without re-adding to history (no duplicate entries)
- **"Re-translate" button** (orange) in the Quick Translate popup — Forces a fresh API call (`skip_cache=True`), bypassing the cache so a bad/garbled result is never stuck. Runs off the UI thread (no Tk freeze); no cooldown, no clipboard re-capture
- **`TranslationService.redo_translation(text, target_lang)`** — Forced-refresh path that reuses already-known text and pushes a fresh result to the translation queue
- **Cache-poisoning guard** — `find_cached` only serves `source_type == 'text'` entries, and custom-prompt translations are stored as `source_type == 'custom'`. Prevents a main-window custom-prompt result (or a screenshot/multimodal entry) from being served as a plain-translation cache hit — honors the "custom prompts are never written as a cache match" decision while keeping them visible in the history viewer
- **Decision:** the optional cache on/off toggle from the roadmap was intentionally omitted — the Re-translate button is the escape hatch; cache is also implicitly inert when history is disabled
- **Tests**: +13 (`tests/test_translation_cache.py`) — `find_cached` semantics + `translate_text` hit/miss/skip_cache/custom-prompt-bypass

### R2 — Custom Prompt in Quick Translate Popup
- **"Custom Prompt" button** (teal) in the popup — Makes the translation box editable (keeping the current translation as a starting point) and swaps the button bar to [Send] [Cancel]. The user edits freely and the entire box content is sent verbatim as the prompt, so besides translating they can quickly ask the AI anything about the text
- **`TranslationService.ask_freeform(raw_prompt, target_lang)`** — Raw path that sends the prompt verbatim (no translate wrapper); result pushed to the queue and rendered as a normal popup. Freeform asks are one-offs: never written to history and never served from / written to the R1 cache
- **Edit-mode focus** — Temporarily clears `WS_EX_NOACTIVATE` and force-focuses the box so typing works despite the no-activate popup style; restored to normal on the result popup
- **Single wide button bar** — Popup minimum width widened (560→670px) so all 7 actions + close fit in one row (developer-selected layout)
- **R2-bug fix** — `translate_text()` custom_prompt branch now embeds the source text via `===TEXT TO TRANSLATE===` delimiters. Previously the source text was omitted, so the main-window "additional instructions" feature sent instructions to the API with nothing to translate
- **Tests**: +7 (`tests/test_freeform_prompt.py`) — custom_prompt embeds source text + bypasses cache; `ask_freeform` verbatim/no-history/queue/empty/strip-thinking

### Test suite repair & wiring guard
- **Fixed 20 outdated `test_api_manager.py` tests** — Provider identification now returns Title-Case names (`'Google'`, `'OpenAI'`, …); the 15 provider-id assertions were updated from the old lowercase contract. The 5 Google tests were rewritten from the removed `genai` SDK to the current Gemini REST path (mock `urllib.request.urlopen`)
- **Added `tests/test_callback_wiring.py`** (+5) — Static integration guard that the popup callback signature, the app handlers, and the service methods stay name-consistent (catches wiring typos unit tests miss)
- **Suite: 39 passed / 20 failed → 84 passed / 0 failed** (+25 new tests, 20 repaired, 0 regressions)

## [1.9.15] - Dictionary Improvements & NLP Install Hardening

### Custom Word Boxes Improvements
- **Smart CJK joining** — Custom box tags join without space for CJK characters (`[無礼][講]` → `"無礼講"`), with space for Latin (`[ice][cream]` → `"ice cream"`)
- **Right-click drag reorder** — Drag tags within/between custom boxes to reorder (move semantics, not copy)
- **Drag visual feedback** — Ghost label follows cursor, source tag dims, cyan drop line shows exact insertion point
- **Precise word insertion** — Dragging words from tokenized area inserts at cursor position, not end of box
- **Text selection fix** — Left-click text selection now works properly in custom boxes
- **Surrogate character filter** — Tkinter embedded window placeholders no longer leak into lookup text

### NLP Install Graceful Degradation
- **No more scary errors** — Whitespace-separated languages (Vietnamese, European) gracefully fall back to basic tokenization instead of showing error dialog
- **Basic mode indicator** — UI shows info-blue "ℹ Installed with basic tokenization" for basic-mode languages
- **`whitespace_separated` field** — `LanguagePack` now tracks whether simple tokenize gives usable Dictionary results
- **`nlp_basic_mode` config** — Persists basic tokenization state across sessions

### Auto-Retry NLP Install
- **Multi-Python discovery** — When post-install verification fails, discovers all Python interpreters via `py -0p` and common install paths
- **Automatic retry** — Cleans custom packages dir and retries pip install with each discovered Python
- **Cached Python path** — Successful Python interpreter path cached in config for future installs

## [1.9.14] - Custom Word Boxes & NLP Install Fix

### Custom Word Boxes
- **Manual phrase composition** — New input boxes in Dictionary popup for composing custom lookup phrases when NLP tokenization doesn't detect the desired word/phrase
- **Typed text to tags** — Type text and press Enter to convert into orange tags (same visual as selected dictionary words)
- **Right-click drag from word area** — Drag tokenized words into custom boxes
- **Dynamic boxes** — Add (+) / remove (-) boxes, up to 5 per lookup
- **Combined lookup** — "Dictionary Lookup" button combines selected words from word area + all box content

### NLP Language Pack Install Fix
- **Post-install verification** — `install()` now verifies packages are actually importable after pip succeeds, instead of trusting pip exit code
- **EXE subprocess fallback** — When bundled Python can't import C extensions (version mismatch), falls back to subprocess tokenization via system Python
- **C extension detection** — `is_installed()` detects `.pyd`/`.so` files in custom packages directory
- **Module cache clearing** — Clears parent modules from `sys.modules` for dotted names (e.g., `ufal.udpipe`) to prevent stale cache

## [1.9.13] - Furigana Reading Guides for Japanese

### Furigana Feature
- **Japanese reading guides** — When translating Japanese text, original text is displayed with furigana (hiragana readings above kanji) to help learn pronunciation
- **Offline generation** — Uses pykakasi library for local kanji-to-hiragana conversion (no extra API call)
- **Embedded frame rendering** — Each kanji+reading pair is an inline frame with `align='baseline'` for perfect vertical alignment with surrounding text
- **Word wrap support** — Long furigana lines wrap naturally using `wrap=tk.CHAR` (CJK-friendly)
- **Toggle in Settings** — Enable/disable in Settings → Hotkeys → "Enable Furigana" checkbox
- **Config key**: `furigana_enabled` (boolean, default `True`)

### Dev Runner
- **`dev_run.bat`** — Development script that kills running CrossTrans instance and restarts with console output for debugging
- Uses PowerShell `Get-CimInstance` to find and kill python processes by command line match

## [1.9.12] - Rename & Documentation Overhaul

### Codebase Rename: Tooltip → Quick Translate
- **Renamed `tooltip.py` → `quick_translate.py`** — Feature now consistently called "Quick Translate" everywhere
- **`TooltipManager` → `QuickTranslateManager`** — Class, variables, methods, callbacks all renamed
- **User-facing text** — All UI strings now say "popup" instead of "tooltip"
- **Documentation updated** — README, CHANGELOG, CLAUDE.md, copilot instructions all consistent

### README Overhaul
- **"Translate Anywhere" highlighted as core advantage** — Works in any app, no plugin needed
- **Two translation methods explained** — Text selection + hotkey, or screenshot OCR for non-selectable text
- **Cross-platform workflow focus** — Browsers, IDEs, chat apps, games, images, videos
- **All screenshots added** — 10 screenshots now included in the repository

### Guide Tab Improvements
- **Hotkeys section moved to top** — First thing users see after Getting Started
- **Hotkey intro line added** — Explains that hotkeys activate Quick Translate

## [1.9.11] - Public Release Hardening

- **Cleaned .gitignore** — Ensured no sensitive or dev-only files leak into the repository
- **Standardized API Settings buttons** — All error dialogs now consistently show "Open API Key Settings" button that navigates directly to Settings > API Key tab
- **Fixed trial dialogs bug** — "Open Settings" button in Trial Exhausted and Trial Feature dialogs now renders correctly
- **DPI awareness** — App respects system scaling on high-DPI displays
- **SmartScreen documentation** — Added first-run guidance for unsigned EXE

## [1.9.10] - Replace in Source App & Dictionary Improvements

### Replace in Source App
- **Replace button** — One-click replace selected text with translation directly in the source app
- **Manual Replace mode** (default) — Preview with strikethrough original and translated text, then Agree/Cancel
- **Quick Replace mode** — Immediate paste without preview for faster workflow
- **Gear icon (⚙)** — Dropdown menu next to Replace button for quick access to settings
- **Replace Mode toggle** — Configurable in Settings → Hotkeys → Replace Mode section
- **WS_EX_NOACTIVATE popup** — Popup doesn't steal focus from source app, keeping text selection alive

### Dictionary Mode Improvements
- **Synonyms & Antonyms** — Dictionary now shows synonyms and antonyms with translations (8-field output)
- **Smart word filtering** — Punctuation, symbols, and pure numbers no longer appear as clickable word buttons
- **Unicode letter detection** — Filter works across all languages (Latin, CJK, Cyrillic, Arabic, Thai, Korean)
- **Dedicated mode only** — Dictionary lookup only through the Dictionary button, no auto-detection on short text

### Generic API Guidance
- Removed provider-specific API key links and pricing from all UI dialogs
- Guide tab now shows generic instructions for any supported provider

## [1.9.9] - Dynamic Remote Config & Auto-Update Overhaul

### Dynamic Remote Model Configuration
- **Models updated without rebuilding EXE** — Provider list, model names, and API URLs fetched from Cloudflare KV
- **3-tier fallback** — Remote → Local cache (24h) → Hardcoded defaults; app never blocks on network
- **15 AI providers, 180+ models** — Updated dynamically without app update

### Auto-Update System Overhaul
- **Versioned EXE rename** — New EXE saved as `CrossTrans_v{version}.exe`, old renamed to `.bak`
- **Registry auto-start sync** — Auto-start path updated automatically after update
- **First-launch retry** — Handles Windows Defender scanning delay on new EXE

## [1.9.8.x] - Performance, Dictionary & Stability

### Performance (v1.9.8.1)
- **Settings window opens instantly** — Lazy loading for heavy tabs (API, Dictionary, Guide)
- **NLP pre-warming** — Dictionary tab loads faster on subsequent opens

### Dictionary Mode (v1.9.8.2)
- **Hyphenated words preserved** — Words like "auto-update" stay as single tokens
- **Better sentence detection** — Expanded punctuation detection (55 characters)

### Stability (v1.9.8)
- **Trial mode auto-recheck** — Automatically re-validates API keys every 24h
- **Version upgrade detection** — Clears cache when upgrading to new version
- **Settings refactored** — Split into modular package structure

## [1.9.7] - Screenshot Translation

- **Screenshot Translation** — Win+Alt+S captures screen region for OCR translation
- **Multi-monitor support** — Works across all connected displays
- **Double-click to Preview** — Open attached files with system default app
- **Auto-check updates** — Non-intrusive toast notification on startup

## [1.9.6] - Dictionary Language Pack Fix

- Critical bug fix for Dictionary Language Pack in EXE builds
- Auto-detects system Python when running from EXE

## [1.9.5] - API Key Fix & Google REST API

- Fixed API Key saving position issue
- Animated "Installing..." text for Dictionary Language Pack
- Google provider now uses REST API (EXE 30MB smaller)

## [1.9.4] - HuggingFace Provider

- HuggingFace provider added (14 AI providers total)
- Test button now saves API key even on test failure

## [1.9.2–1.9.3] - Dictionary Mode & Trial Security

- Dictionary Mode with interactive word selection
- Enhanced Trial mode security
- 180+ models from 14 providers

## [1.7.0–1.9.0] - Trial Mode, Windows Hello & Provider Fallback

- **Trial Mode** — Free daily translations without API key
- **Windows Hello Authentication** — Secure API key protection
- **Smart Provider Fallback** — Auto-switch to backup API on failure
- **Scanned PDF OCR** support
- **Toast notifications** and **Search History**
