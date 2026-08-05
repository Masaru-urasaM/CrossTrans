# Changelog

All notable changes to CrossTrans are documented here.

## [Unreleased]

### Phase 0 — Furigana engine: structured segments, accurate readings (2026-08-04)

First phase of "furigana everywhere". **Pure logic only — no UI file was touched**, so the
Quick Translate popup looks and behaves exactly as before except that its readings are now
correct. Groundwork for rendering ruby on every surface in later phases.

**Added**
- **`src/core/furigana.py`** — the furigana engine.
  - `RubySegment(base, ruby)` — a structured segment model replacing the fragile
    `{kanji|reading}` string as the internal contract.
  - **Invariant I1**: `''.join(seg.base for seg in annotate(text)) == text`, asserted at
    runtime and in tests. Annotation can no longer alter the text it describes.
  - `should_annotate(text, lang_hint)` — requires kanji **plus** kana evidence, or an
    explicit language hint. Chinese hanzi no longer qualifies for Japanese readings, while
    kanji-only Japanese (`東京都`, `電源設定`) still annotates when the caller passes a hint.
  - `align(surface, reading)` — maps a whole-token reading onto the kanji runs inside it by
    anchoring on the kana already present. **Fail-safe**: returns `None` rather than guess,
    so no wrong reading is ever drawn.
  - Provider chain `FugashiProvider` → `KakasiProvider`, each built **once** and reused.
  - `_refine_compounds()` — restores whole-compound readings that morphological splitting
    destroys, restricted to all-kanji spans.
  - `to_notation()` / `parse_notation()` with backslash escaping for `\ { } |`.
- **`tests/test_furigana_core.py`** — 80 tests: detection matrix, aligner (incl. every
  fail-safe branch), I1 over a 19-case corpus, notation escaping round-trip, whitespace
  preservation, the pair cap, and the reading-quality regressions below.

**Fixed**
- **Okurigana covered by ruby** — `取り消し` produced `{取り消|とりけ}し`, the ruby spanning
  the り, because the old code stripped only a *trailing* kana suffix. Now
  `{取|と}り{消|け}し`. Same class fixed for `話し合い`, `申し込み`, `生き物`.
- **Wrong homograph readings** — `今日は雨` gave こんにち; now きょう (morphological context).
- **`kakasi()` rebuilt on every call** — measured ~175 ms to construct versus ~0.3 ms to
  convert. Now a lock-guarded singleton, plus a 256-entry `lru_cache` on annotation.
- **Notation injection** — source text containing a literal `{a|b}` was parsed back as a
  real ruby pair and rendered as "a" with the reading "b". The segment model makes this
  structurally impossible; until the renderer consumes segments (Phase 1), the legacy wire
  format additionally suppresses ruby for any text holding `\ { } |`.
- **Multi-line text lost all ruby** — tokenizers normalize whitespace away, which broke the
  round-trip check. Annotation now runs on whitespace-free chunks and re-inserts separators
  verbatim, so newlines, CRLF, tabs and blank lines survive.
- **Misleading counter readings** — `2日` is *futsuka*: the digit carries part of the reading
  and cannot take ruby, so drawing カ over 日 alone invited "ni-ka". Counters following a
  digit are now suppressed, which also removes real errors (`2人` is *futari*, not ni-**nin**;
  standalone `1月` reported ツキ instead of ガツ).
- **Compound readings broken by splitting** — UniDic tags 日本 as a proper noun reading
  ニッポン, so `日本語` came out にっぽんご and `日本人` にっぽんにん. Both correct now, and
  `東京駅` → とうきょうえき, `中国語` → ちゅうごくご.
- **Chinese text was given Japanese readings** — the pipeline gate matches U+4E00-U+9FFF, so
  hanzi qualified. `你好世界` produced `{你|}{世界|せかい}` — note the **empty** reading on 你,
  which would have rendered a blank ruby label. Both are gone.
- **Misleading log message** — the old `"pykakasi not installed"` warning did not fire when
  the package imported but its bundled dictionary data was missing, which is the likely
  packaging regression. Provider failures now log the actual exception.

**⚠️ One behaviour change: kanji-only source text no longer gets furigana from the hotkey path.**
Ruby now requires kanji **plus** kana evidence, or an explicit language hint. A sentence
(`今日は雨が降る`) is unaffected — it has kana. But a kanji-only selection (`電源設定`, `東京都`,
`翻訳`) used to be annotated and now is not, because the pipeline calls
`generate_furigana(selected_text)` with no hint and **cannot tell Japanese kanji from Chinese
hanzi**: the same permissive check that annotated `東京都` is what annotated `你好世界`.
This is the deliberate "blank beats a wrong reading" trade — a lost reading is visibly absent,
whereas a wrong one is unfalsifiable at the point of use. Phase 2 closes the gap by threading
the real source language from the surfaces that already know it (the popup, and the dictionary's
`_open_with_language`), at which point kanji-only Japanese annotates again *without* also
re-annotating Chinese.

**Changed**
- `src/core/translation.py` — `_is_japanese_text()` and `generate_furigana()` are now
  two-line delegates onto the new module. `generate_furigana()` gained an optional
  `lang_hint`. The queue tuple shapes are **unchanged** (arity is the discriminator in
  `app.py:_check_queue`, so extending it positionally would abort the drain loop).

**Verified**
- Packaging: `collect_data_files('pykakasi')` at `CrossTrans.spec:15` is load-bearing and
  sufficient — proven with two minimal one-file probe EXEs (with data: readings work in the
  frozen EXE; without: `FileNotFoundError` on `kanwadict4.db`, swallowed into a silent
  no-furigana state). No new packaging risk from this phase.

**Tests**: 124 → 204 passed / 0 failed. No regressions; the pre-existing tuple-shape
assertions in `test_translate_or_fix.py`, `test_fix_grammar.py` and `test_freeform_prompt.py`
all still hold.

## [Unreleased] — Storage identity renamed to CrossTrans (2026-07-01)

The app's internal **storage identity** — the `%APPDATA%` config folder, the model-config cache folder, the Windows auto-start registry value, and the DPAPI encryption entropy/description — was renamed from the legacy product name to **`CrossTrans`**, matching the user-facing name already in `src/constants.py`. A fresh install now uses `%APPDATA%\CrossTrans\` throughout.

### ⚠️ Breaking change (existing installs)
- **Saved API keys must be re-entered.** Keys are DPAPI-encrypted with an app-specific entropy that changed as part of the rename, so keys stored by an older build can no longer be decrypted and are cleared on load.
- **Settings/history do not carry over.** The new build reads `%APPDATA%\CrossTrans\config.json`; the old build's folder is no longer consulted.
- The old `%APPDATA%` config folder is a harmless leftover — delete it manually if you want the disk space back.
- **Auto-start needs a one-time manual cleanup for anyone who had it enabled.** The old auto-start registry entry (under the previous name) still launches the app, but the Settings toggle now manages the `CrossTrans` entry only — so the toggle reads **OFF** and cannot remove the old entry. To actually stop auto-start, disable it via **Task Manager → Startup apps**, or delete the stale value under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` once. (On a manual reinstall the stale entry may still point at the *old* exe, so the previous version could keep launching — masked by the single-instance lock — until removed.)
- **No automatic migration was implemented — deliberately**, to keep the rename total (no trace of the old name remains in the project) per explicit request. A migration (old-folder copy + key re-encryption) is a clean future option, but cannot coexist with a "no old-name anywhere" requirement.

### Changed
- `config.py` — `APP_NAME` is now `"CrossTrans"` (drives the config dir and the auto-start registry value name); docstring updated.
- `src/core/crypto.py` — `SecureStorage.ENTROPY` (the DPAPI salt) and `DESCRIPTION` (cosmetic) now use the `CrossTrans` identity.
- `src/core/remote_config.py` — model-config `CACHE_DIR` is now `%APPDATA%\CrossTrans\`.
- `src/utils/updates.py` — the auto-updater batch script now reads/writes the `CrossTrans` auto-start registry value.
- Docs — `CLAUDE.md`, `.github/copilot-instructions.md`, and `OPS_GUIDE.md` path/registry references updated; removed a stale deprecated `.spec` entry from `.gitignore` (the real, tracked build spec is `CrossTrans.spec`).

**Tests**: 124 passed / 0 failed — no regressions. Verified a full-repo case-insensitive search for the old name returns **zero** matches (excluding `.git`).

## [1.9.18] - Merged Translate-or-Fix on the language hotkeys (2026-07-01)

Pressing a **language hotkey** (Win+Alt+V/E/J/C — and any custom language hotkey) on text that is **already in that hotkey's target language** now **fixes its grammar in place** instead of pointlessly "translating" it. One merged AI prompt lets the model auto-decide translate-vs-fix. This makes grammar-fixing reachable without a dedicated hotkey — sidestepping the Xbox Game Bar (`Win+Alt+G`) and Feedback Hub (`Win+Alt+F`) collisions entirely.

### Added
- **`TranslationService.translate_or_fix(text, target_language, skip_cache=False)`** — Sends ONE merged prompt: if the text is already in `target_language` the model corrects only grammar/spelling/punctuation (minimal changes, same language); otherwise it translates. BOTH branches are uncensored and meaning-preserving (offensive words survive — faithful equivalent when translating, verbatim when fixing). Cached/stored under `source_type='merged'`.
- **`TranslationService.do_translate_or_fix(target_language)`** — Language-hotkey orchestrator (mirrors `do_translation`): captures the selection, shares the `last_translation_time` cooldown, generates furigana for Japanese source, queues the same 5-tuple as a translation (`is_grammar=False` — the output is a real language in both branches).
- **Merged cache namespace** — `HistoryManager.find_cached(original, target_lang, source_type='text')` gained a `source_type` param; the merged path reads/writes under `'merged'` so a minimal-change fix is never cross-served as a plain 'rephrase' translation (and vice versa).
- **Config**: `fix_grammar_hotkey_enabled` (default **False**) with `get/set_fix_grammar_hotkey_enabled` — a separate flag registering the global `Win+Alt+G` hotkey.

### Changed
- **`app._on_hotkey_translate()`** — The normal language branch now calls `do_translate_or_fix(language)` instead of `do_translation(language)`. Covers every language hotkey (defaults + custom) since this branch handles all non-special `language` values.
- **No-censor everywhere** — The no-censor rule was added to the plain `translate_text` prompts (both variants) and the screenshot/OCR vision prompt, per user request, so offensive words survive all translations (not just the merged path).
- **`Win+Alt+G` hotkey now OFF by default** — split from the button: `fix_grammar_enabled` (default True) controls only the main-window **button**; the new `fix_grammar_hotkey_enabled` (default **False**) gates the global hotkey registration + tray hint. `hotkey.py`, `tray.py`, `app.py` guard, and the Settings → Hotkeys section (new "Enable global Win+Alt+G hotkey" checkbox) updated accordingly. The button and the merged language-hotkey behavior always work.

### Notes
- **Uncensored output is best-effort and model-dependent** — the prompt can only *request* it; some of the 15 providers/180+ models and the trial proxy enforce hard content filters that may still refuse/mask. Additionally, adding an explicit no-censor instruction to *all* translations can itself increase refusals on some models for otherwise-benign text (accepted tradeoff). Confirm behavior against the configured model.
- **LEAN display consequences** (documented, not blockers): the popup shows the language (not "Grammar") for a same-language fix, and the popup **Re-translate** button re-runs the plain `translate_text` (rephrase), not the merged prompt.

**Tests**: +24 (`tests/test_translate_or_fix.py`) covering the merged prompt content (tie-break + both-branch no-censor + verbatim token via a neutral placeholder, never a real slur), `'merged'` cache namespace isolation (no cross-serve), `do_translate_or_fix` routing/tuple/cooldown/trial/no-selection/history, and no-censor presence in the plain prompts; +2 wiring guards (`tests/test_callback_wiring.py`); updated `tests/test_fix_grammar.py` for the split hotkey flag. Suite: **100 → 124 passed / 0 failed** (0 regressions).

## [1.9.17] - Fix Grammar (2026-06-30)

A new **Fix Grammar** action that corrects the grammar of selected text *in place* — no translation, no rephrasing, no censoring. The output is always the same text in the same language with only grammar/spelling/punctuation fixed.

### Added
- **Fix Grammar hotkey** (default **Win+Alt+G**) — Select text anywhere, press the hotkey, and a popup shows the grammar-corrected text with **Copy** / **Replace** to apply it back into the source app. ⚠️ `Win+Alt+G` is also Xbox Game Bar's "Record that" default; registration fails gracefully (error 1409) if Game Bar holds it, the hotkey is fully rebindable, and the button always works. `Win+Alt+F` is the recommended conflict-free alternative.
- **"Fix Grammar" button** in the main translate window (next to Translate) — Corrects the input box text and writes the result into the output box.
- **Settings → Hotkeys → Fix Grammar section** — "Enable Fix Grammar" toggle (default **ON**) + rebindable hotkey row (mirrors the Screenshot hotkey row), with duplicate-hotkey validation.
- **Tray menu entry** — `Win+Alt+G → Fix Grammar` listed with the other hotkeys (shown only when the feature is enabled).
- **`TranslationService.fix_grammar(text)`** — Builds a strict correction prompt (fix grammar/spelling/punctuation only; never translate, paraphrase, change meaning/tone, or censor — including offensive words; return unchanged if already correct), calls the API, strips thinking tags. Not written to history.
- **`TranslationService.do_grammar_fix()`** — Hotkey entry point: captures the live selection (Ctrl+C), honors a dedicated cooldown (`last_grammar_fix_time`), surfaces trial info, and queues a 6-tuple `(original, corrected, "Grammar", trial_info, None, True)`.
- **Config**: `FIX_GRAMMAR_HOTKEY_DEFAULT="win+alt+g"`, `fix_grammar_hotkey` + `fix_grammar_enabled` (default `True`) in `DEFAULT_CONFIG`, with `get/set_fix_grammar_hotkey` and `get/set_fix_grammar_enabled`.

### Changed
- **`HotkeyManager.register_hotkeys()`** — Registers a `__fix_grammar__` hotkey (gated by `fix_grammar_enabled`, so disabling frees the combo); fails gracefully on conflict like the other hotkeys.
- **`app._on_hotkey_translate()`** — Added a guarded `__fix_grammar__` dispatch branch (additive; the translation path is untouched). Source-window HWND is captured first so Replace works.
- **Quick Translate popup** — `show(..., is_grammar=False)` hides the translation-only buttons (Re-translate, Dictionary, Custom Prompt) for grammar results, keeping Copy / Replace / Open Translator. `show_loading(..., loading_text=...)` shows "Fixing grammar…" instead of "Translating to …".
- **`_check_queue()`** — Now also handles the 6-tuple grammar result and routes it with `is_grammar=True` (4- and 5-tuple translation paths unchanged).

### Notes
- **No prompt fully guarantees uncensored output across all 15 providers/180+ models** — some have hard content filters that may refuse or soften sensitive input (the trial proxy may too). The prompt is engineered to preserve text verbatim; behavior should be confirmed against the actually-configured model.

**Tests**: +13 (`tests/test_fix_grammar.py`) — `fix_grammar` prompt content (never-translate / no-censor / same-language / verbatim token preservation) + empty guard + thinking-tag strip; `do_grammar_fix` 6-tuple/`is_grammar` flag + cooldown + error path + no-history; config defaults/fallbacks; hotkey registration wiring. Suite: **87 → 100 passed / 0 failed** (0 regressions).

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
