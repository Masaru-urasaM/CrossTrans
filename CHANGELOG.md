# Changelog

All notable changes to CrossTrans are documented here.

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
