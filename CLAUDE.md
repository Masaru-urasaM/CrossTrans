# CrossTrans v1.9.18 - AI Context

## Project Overview
CrossTrans is a Windows desktop translation app using AI APIs (15 providers, 180+ models).
Select text, press hotkey, get instant translation in a popup.

## never remove this line no matter what. Always use english in this project. No Vietnamese allow. Repeat, no Vietnamese allow no matter what. only using Vietnamese to communicate, not in the code.


## Key Files
| File | Purpose |
|------|---------|
| `main.py` | Entry point |
| `config.py` | Configuration management, registry auto-start |
| `src/constants.py` | VERSION, LANGUAGES, PROVIDERS (hardcoded fallbacks) |
| `src/app.py` | Main TranslatorApp coordinator (~1630 lines) |
| `src/core/remote_config.py` | Dynamic model/provider config (Cloudflare KV) |
| `src/core/` | Business logic (22 modules) |
| `src/ui/` | UI components (20+ files) |
| `src/ui/settings/` | Settings tabs (package) |
| `src/utils/updates.py` | Auto-update system (check, download, install) |
| `docs/models_config_template.json` | Template JSON for Cloudflare KV config |

## App.py Modular Architecture

`src/app.py` was refactored from 2533 to ~1630 lines by extracting these modules:

| Module | Lines | Purpose |
|--------|-------|---------|
| `src/utils/ui_helpers.py` | 85 | `set_dark_title_bar()`, `filter_dictionary_words()` |
| `src/ui/expanded_window.py` | 184 | `ExpandedTranslationWindow` - fullscreen translation view |
| `src/core/update_ui_manager.py` | 259 | `UpdateUIManager` - update status checking & UI |
| `src/core/trial_manager.py` | 131 | `TrialManager` - trial mode quota & dialogs |
| `src/ui/screenshot_handler.py` | 222 | `ScreenshotHandler` - screenshot/vision translation |
| `src/ui/dictionary_popup.py` | 516 | `DictionaryPopup` - dictionary word lookup UI |

### Callback Pattern
New modules use `configure_callbacks()` for dependency injection:
```python
self.screenshot_handler = ScreenshotHandler(self.root, self.config, ...)
self.screenshot_handler.configure_callbacks(
    on_show_quick_translate=self.show_quick_translate,
    get_selected_language=lambda: self.selected_language
)
```

### What Remains in app.py
- `TranslatorApp` coordinator class
- `show_popup()` method (tightly coupled with widget state)
- Translation animation logic
- Copy-and-replace logic (source window HWND capture + focus restore + Ctrl+V paste)
- Main window lifecycle

## Common Tasks

| Task | File(s) |
|------|---------|
| Change version | `src/constants.py` |
| Add/remove AI models | Cloudflare KV (`MODELS_KV` -> `models_config`) - no code change needed |
| Add AI provider | Cloudflare KV + `src/core/api_manager.py` (if new API format) |
| Modify hotkeys | `src/core/hotkey.py` |
| Fix Grammar feature | `src/core/translation.py` (`fix_grammar`, `do_grammar_fix`) + `src/app.py` (`_on_hotkey_translate` `__fix_grammar__` branch, `_do_fix_grammar`) + `src/ui/settings/hotkey_tab.py` (`_create_fix_grammar_section`) |
| Update quick translate popup | `src/ui/quick_translate.py` |
| Add settings tab | `src/ui/settings/*.py` |
| Translation logic | `src/core/translation.py` |
| Furigana readings (generation) | `src/core/furigana.py` |
| Furigana rendering (any surface) | `src/ui/ruby_text.py` (`RubyText`) |
| Dictionary mode | `src/core/nlp_manager.py` + `src/ui/dictionary_mode.py` + `src/ui/custom_word_boxes.py` + `src/core/translation.py` (prompt) |
| Update system | `src/utils/updates.py` + `src/ui/settings/update_manager.py` |

## Auto-Update System (Important)

Key points:

### Update flow (EXE mode):
1. Check GitHub API → download EXE → create batch script → `os._exit(0)`
2. Batch script: wait for PID death → copy new EXE → backup old → update Registry → launch new

### Critical implementation details:
- **MUST use `os._exit(0)`** to exit after launching update script, NOT `sys.exit(0)`.
  `sys.exit()` raises `SystemExit` which Tkinter's `after()` callback handler silently catches.
- **Subprocess flags**: Use `CREATE_NO_WINDOW` only. Do NOT combine with `DETACHED_PROCESS` (mutually exclusive per Microsoft docs).
- **Batch script parenthesis**: Never use `(` or `)` inside echo strings within `if` blocks. cmd.exe interprets `)` as closing the if block.
- **Batch script redirect**: Always put a space before `>` in echo commands. `echo 1.9.8>file` interprets `8>` as file descriptor 8 redirect.
- **EXE rename**: After update, new EXE is named `CrossTrans_v{version}.exe`. Old EXE renamed to `.bak`.
- **Registry auto-start**: Batch script updates `HKCU\...\Run\CrossTrans` to point to new EXE path.
- **First-launch retry**: New EXE may fail first launch (Windows Defender scan). Batch script has 2s delay + retry mechanism.

### Testing updates without releasing:
1. Change `VERSION` in `src/constants.py` to an older version (e.g., "1.9.7")
2. Build: `build_exe.bat`
3. Run built EXE → Settings → Check for Updates → it will find the real release on GitHub
4. **Always revert VERSION after testing**

### Verification checklist:
- App exits immediately when clicking "Yes" to restart
- No black CMD window appears
- New EXE appears with correct version name
- Old EXE renamed to `.bak`
- New EXE auto-launches (may need retry)
- Check `%TEMP%\crosstrans_update.log` for details
- Check `%TEMP%\crosstrans_update_success.txt` exists

## Known Issues

- **PyInstaller first-launch delay**: `--onefile` EXE may fail on FIRST double-click after fresh build (Windows Defender scanning). Works on second attempt. This is Windows behavior with new executables, not a bug. The update batch script handles this with its retry mechanism.

- **os._exit(0) cleanup**: `os._exit(0)` skips Python cleanup (atexit handlers, file flushes). This is intentional to bypass Tkinter's exception handling. A 0.5s sleep before `os._exit()` ensures log flushing.

- **Single instance**: TCP socket lock on `127.0.0.1:47823` (see `src/utils/single_instance.py`)

- **ttkbootstrap discards explicit colours on standard `tk` widgets**: it re-themes them at construction, so `tk.Label(fg='#80b8ff', bg='#363636')` comes back `fg='#ffffff'`, `bg='#222222'`. Measured, not theoretical — it is why the furigana reading colour never actually shipped before v1.9.19. Pass `autostyle=False` (as the `tk.Button` call sites in `quick_translate.py` and `ruby_text.py` do) whenever a colour must survive. `tag_configure()` colours are **not** affected, only widget options. Leave a widget themed when it should match the frame around it.

- **Never use `grab_set()` on popups**: Tkinter `grab_set()` + `transient(hidden_root)` causes permanent UI freeze. The root window is withdrawn, so modal grab locks all input with no visible dialog to dismiss. Always use `attributes('-topmost', True)` + `lift()` + `focus_force()` + `after(100, topmost=False)` pattern instead.

## Remote Config System (Important)

Models, providers, and API URLs are dynamically fetched from Cloudflare Worker KV.
Hardcoded values in `constants.py` serve as fallback defaults.

### Architecture (3-tier fallback):
1. **Remote**: Cloudflare Worker `GET /v1/config` -> KV namespace `MODELS_KV`
2. **Local cache**: `%APPDATA%/CrossTrans/models_config.json` (24h TTL)
3. **Hardcoded**: `constants.py` values (always available, compiled into EXE)

### Key module: `src/core/remote_config.py`
- Singleton `RemoteConfigManager` with thread-safe RLock
- `get_config()` returns the singleton instance
- Background fetch on startup via `fetch_remote_async()` (non-blocking)
- Properties: `providers_list`, `model_provider_map`, `api_key_patterns`,
  `vision_models`, `default_models_by_provider`, `provider_api_urls`

### To update models without code changes:
1. Cloudflare Dashboard -> Storage & Databases -> Workers KV -> MODELS_KV
2. Edit key `models_config` -> update JSON -> Save
3. App picks up changes on next startup (or after 24h cache expiry)

### Consumers (use `get_config()` instead of constants directly):
- `api_manager.py` - provider detection, API URLs, default models
- `multimodal.py` - vision model capability check
- `api_tab.py` - provider/model dropdowns in Settings
- `widgets.py` - model list for autocomplete combobox

## Core Modules (src/core/)

- `remote_config.py` - Dynamic model/provider config from Cloudflare KV
- `furigana.py` - Furigana engine: Japanese detection, fugashi/pykakasi providers, reading aligner
- `api_manager.py` - Multi-provider API communication (15 providers)
- `translation.py` - Translation service, clipboard integration, furigana generation
- `hotkey.py` - Global hotkey registration (Win+Alt+V/E/J/C/S)
- `multimodal.py` - Vision/OCR processing
- `screenshot.py` - Screenshot capture for OCR translation
- `clipboard.py` - ClipboardManager for text/file handling
- `history.py` - Translation history (100 entries)
- `file_processor.py` - Document extraction (.docx, .txt, .srt)
- `pdf_ocr.py` - Scanned PDF OCR support
- `crypto.py` - Secure API key storage (DPAPI encryption)
- `auth.py` - Windows Hello authentication
- `provider_health.py` - Smart provider fallback
- `quota_manager.py` - Trial mode quota tracking
- `trial_api.py` - Trial mode proxy API client
- `nlp_manager.py` - NLP language pack management (install verification, subprocess fallback for EXE)
- `update_ui_manager.py` - Update status checking & UI feedback
- `trial_manager.py` - Trial mode status & dialogs

## UI Components (src/ui/)

- `ruby_text.py` - `RubyText` widget: the single place furigana is drawn (+ `get_plain()` readback)
- `quick_translate.py` - QuickTranslateManager (translation popup with Copy, Replace, Dictionary, Open Translator, furigana rendering)
- `tray.py` - System tray manager
- `dialogs.py` - Error/trial dialogs
- `attachments.py` - File attachment widget
- `dictionary_mode.py` - Word selection UI with right-click drag-to-box support
- `dictionary_popup.py` - Dictionary popup manager (extracted from app.py)
- `custom_word_boxes.py` - Custom Word Boxes for manual phrase composition in Dictionary mode
- `expanded_window.py` - Fullscreen translation view
- `screenshot_handler.py` - Screenshot/vision translation handler
- `history_dialog.py` - History viewer
- `toast.py` - Toast notifications
- `settings/` - Settings window (modular tabs)

## Utils (src/utils/)

- `updates.py` - Auto-update system (check, download, install)
- `single_instance.py` - TCP socket lock for single instance
- `ui_helpers.py` - Dark title bar, word filtering utilities

## Build

```bash
# Using batch script (recommended)
build_exe.bat

# Or manually
python -m PyInstaller CrossTrans.spec --clean --noconfirm
```

## Test

```bash
pytest tests/ --cov=src
```

## Run

```bash
python main.py
```

## Key Features

1. **Hotkey Translation** - Win+Alt+V/E/J/C for quick translation
2. **Screenshot OCR** - Win+Alt+S to capture and translate screen region
3. **Replace in Source** - One-click replace selected text with translation (via popup Replace button)
4. **Trial Mode** - Daily free translations without API key (limit from remote config)
5. **15 AI Providers** - Google, OpenAI, Anthropic, DeepSeek, Groq, etc.
6. **Dynamic Model Config** - Models/providers updated via Cloudflare KV (no rebuild needed)
7. **Dictionary Mode** - Click words for definitions, pronunciation, synonyms, antonyms, examples
8. **File Translation** - .docx, .txt, .srt, .pdf, images
9. **Windows Hello** - Secure API key protection
10. **Auto-Update** - In-app update with retry, backup, and registry sync
11. **Furigana** - Japanese reading guides (hiragana above kanji) via pykakasi
12. **Fix Grammar** - Main-window button (default ON) or optional Win+Alt+G hotkey (default **OFF** - collides with Xbox Game Bar): corrects grammar of selected text in place (no translation, no rephrasing, no censoring). Toggle button + hotkey separately in Settings → Hotkeys.
13. **Merged Translate-or-Fix** (v1.9.18) - Pressing a language hotkey (Win+Alt+V/E/J/C + custom) on text already in that language auto-fixes its grammar instead of translating, via one merged AI prompt. No dedicated hotkey needed. See "Merged Translate-or-Fix" section below.

## Merged Translate-or-Fix (language hotkeys, v1.9.18)

Pressing a **language hotkey** (Win+Alt+V/E/J/C, plus any custom language hotkey) sends **one merged
prompt** that makes the model auto-decide: if the selection is **already in that hotkey's target
language** → grammar-fix it in place (minimal change, same language); otherwise → translate. This
covers every language hotkey because `_on_hotkey_translate`'s normal branch handles all non-special
`language` values, and `register_hotkeys()` maps custom hotkeys to their language name too.

### Key points
- **Both branches uncensored & meaning-preserving** — offensive words survive (faithful equivalent
  when translating, verbatim when fixing). The no-censor rule is ALSO in the plain `translate_text`
  prompts and the screenshot vision prompt (v1.9.18), so all translations preserve slurs.
- **LEAN routing** — `do_translate_or_fix()` queues the normal **5-tuple** (`is_grammar=False`); the
  popup shows full buttons and the language header (not "Grammar") because the output is a real
  language in both branches. No mode marker.
- **Cache namespace `'merged'`** — `find_cached(original, target_lang, source_type='text')` gained a
  `source_type` param; the merged path uses `'merged'` so a minimal-change fix is never cross-served
  as a plain 'rephrase' translation (and vice versa).
- **Caveat** — uncensored output is best-effort/model-dependent (hard content filters may refuse or
  mask); the explicit no-censor line can also raise refusals on some models for benign text.

### Files involved
- `src/core/translation.py` - `translate_or_fix()`, `do_translate_or_fix()`, no-censor in `translate_text`
- `src/core/history.py` - `find_cached(..., source_type=...)`
- `src/app.py` - `_on_hotkey_translate()` normal branch → `do_translate_or_fix(language)`
- `src/ui/screenshot_handler.py` - no-censor in the vision prompt

## Fix Grammar (Win+Alt+G)

Corrects grammar/spelling/punctuation of selected text **without translating, rephrasing, or censoring**. Output is the same text in the same language. Mirrors the screenshot-hotkey pattern (special `__fix_grammar__` marker) and the `ask_freeform` non-translation service pattern.

### Flow:
1. Hotkey `Win+Alt+G` → `app._on_hotkey_translate("__fix_grammar__")` (HWND captured for Replace) → `translation_service.do_grammar_fix()`
2. `do_grammar_fix()` captures selection (Ctrl+C), calls `fix_grammar(text)`, queues a **6-tuple** `(original, corrected, "Grammar", trial_info, None, True)`
3. `_check_queue()` routes the 6-tuple with `is_grammar=True` → popup shows **Copy/Replace** only (translation-only buttons hidden)
4. Main-window **"Fix Grammar"** button → `_do_fix_grammar()` reads the input box, writes corrected text to the output box

### Key points:
- **Prompt** (`fix_grammar()` in `translation.py`): strict rules — never translate, fix only grammar/spelling/punctuation, minimal changes, no paraphrase/vocab/meaning change, **never censor offensive words**, return unchanged if already correct. Not written to history.
- **Config**: `fix_grammar_hotkey` (default `win+alt+g`), `fix_grammar_enabled` (default `True`). Disabling un-registers the hotkey on Settings save and hides the button/tray entry.
- **Default hotkey is Win+Alt+G** (per original spec): this collides with Xbox Game Bar "Record that". `register_hotkeys()` fails gracefully (error 1409) if Game Bar holds it; the hotkey is rebindable and the button always works. Win+Alt+F is the recommended conflict-free alternative if a user hits the collision.
- **Caveat**: no prompt guarantees uncensored output across all providers/models; some have hard content filters.

### Files involved:
- `src/core/translation.py` - `fix_grammar()`, `do_grammar_fix()`, `last_grammar_fix_time`
- `src/app.py` - `_on_hotkey_translate()` (`__fix_grammar__` branch), `_do_fix_grammar()`, `_update_grammar_result()`, `_check_queue()` (6-tuple)
- `src/ui/quick_translate.py` - `show(..., is_grammar=...)`, `show_loading(..., loading_text=...)`
- `src/ui/settings/hotkey_tab.py` - `_create_fix_grammar_section()` (toggle + rebindable hotkey)
- `src/ui/tray.py` - Fix Grammar menu entry
- `config.py` - `get/set_fix_grammar_hotkey`, `get/set_fix_grammar_enabled`

## Replace Button (Copy & Replace)

Popup "Replace" button copies translated text and pastes it back into the source app.

### Popup button bar:
```
[Copy] [Replace][⚙] [Dictionary] [Open Translator]  [×]
```

### Two Replace Modes (config: `quick_replace`):
- **Manual Replace** (default, `quick_replace=False`): Click Replace → preview with strikethrough original → translated text → Agree/Cancel buttons
- **Quick Replace** (`quick_replace=True`): Click Replace → immediate paste without preview

### Replace Mode Setting:
- **Gear icon (⚙)** next to Replace button opens dropdown menu → "Hotkey Settings" → Settings Hotkeys tab
- Toggle in Settings → Hotkeys → "Replace Mode" section
- Config key: `quick_replace` (boolean, default `False`)

### Flow (Manual Replace mode):
1. Hotkey pressed → `_on_hotkey_translate()` captures source window HWND via `GetForegroundWindow()`
2. Translation completes → popup shows with [Copy] [Replace][⚙] [Dictionary] [Open Translator] [×]
3. User clicks "Replace" → `_handle_copy_and_replace()` checks mode:
   - Manual mode: `_show_replace_preview()` → strikethrough original → translated text → Agree/Cancel
   - Quick mode: immediate `_on_copy_and_replace()` callback
4. User clicks "Agree" → `_on_quick_translate_copy_and_replace()`:
   - Copy translated text to clipboard
   - Close popup
   - Simulate `Ctrl+V` via `keyboard.press_and_release()`
   - Show toast "Replaced!"

### Key implementation details:
- **WS_EX_NOACTIVATE**: Popup uses `WS_EX_NOACTIVATE` (0x08000000) window style so clicking buttons doesn't steal focus from source app
- **No focus restoration needed**: Source app keeps focus + selection while popup is open
- **Simple paste**: Just `pyperclip.copy()` + `keyboard.press_and_release('ctrl+v')` in daemon thread
- **Fallback**: Text is always on clipboard even if paste fails. Toast warns user.
- **Gear dropdown**: `tk.Menu.post()` auto-dismisses when clicking outside (prevents accidental navigation)

### Files involved:
- `src/ui/quick_translate.py` - Replace button, gear icon, preview UI, mode check (`_handle_copy_and_replace`)
- `src/app.py` - `_on_quick_translate_copy_and_replace()` (clipboard + Ctrl+V paste)
- `config.py` - `get_quick_replace()` / `set_quick_replace()`
- `src/ui/settings/hotkey_tab.py` - Replace Mode toggle in Hotkeys tab

## Configuration

Config file: `%APPDATA%\CrossTrans\config.json`

Key settings:
- `api_keys` - Encrypted API key storage
- `hotkeys` - Default + custom hotkeys
- `screenshot_target_lang` - Target language for screenshot OCR
- `provider_health` - Success/failure tracking per provider
- `nlp_installed` - Installed NLP language packs
- `nlp_basic_mode` - Languages using basic (whitespace) tokenization as fallback
- `autostart` - Auto-start with Windows
- `auto_check_updates` - Check for updates on startup
- `quick_replace` - Replace mode (False=Manual with preview, True=Quick immediate paste)
- `furigana_enabled` - Furigana reading guides for Japanese (True=show readings above kanji)
- `furigana_reading_pane` - Reading pane under the main-window input box expanded (True) or collapsed

## Dictionary Mode

### Dictionary Prompt (8-field output)
Defined in `src/core/translation.py` method `dictionary_lookup()`:
1. Translation, 2. Source Language, 3. Definition, 4. Word Type,
5. Pronunciation, 6. Synonyms, 7. Antonyms, 8. Examples

### Word Filtering (hardcoded, no API call)
Dictionary mode filters tokens before displaying as clickable buttons:
- **Filter location**: `src/ui/dictionary_mode.py` `_create_word_labels()` (after tokenization)
- **Safety net**: `src/ui/dictionary_popup.py` `_do_lookup()` + `src/app.py` `_on_quick_translate_dictionary_lookup()`
- **Shared function**: `src/utils/ui_helpers.py` `filter_dictionary_words()`
- **Regex**: `[^\W\d_]` with `re.UNICODE` — requires at least one Unicode letter (no pure numbers, symbols, punctuation)
- Strips leading/trailing non-word chars: `"Done."` → `"Done"`, `"."` → filtered out

### Auto-dictionary detection REMOVED
`translate()` no longer auto-switches to dictionary mode for short text (1-4 words).
Dictionary lookup only happens through the dedicated Dictionary button.
The `_is_dictionary_query()` method still exists but is unused.

### Custom Word Boxes

Allows users to manually compose lookup phrases when NLP tokenization doesn't detect the desired word/phrase.

**Layout** (inside Dictionary popup, between word area and action buttons):
```
[word area with tokenized clickable words]
Custom lookup:
┌──────────────────────────────┐ [+]
│ [tag1] [tag2] typed text_    │
└──────────────────────────────┘
[Dictionary Lookup] [Clear] [Expand] [Exit]
```

**Features**:
- Text input boxes where users type freely or drag words from the tokenized area
- Words entered become orange tags (same visual as selected dictionary words)
- "+" button adds new box below (max 5), "-" removes current box (first box cannot be removed)
- Right-click drag a word from the tokenized area into a box (inserts at precise cursor position)
- Right-click drag tags within/between boxes to reorder (move semantics, not copy)
- Press Enter to convert typed text into a tag
- Left-click text selection works normally in boxes
- "Dictionary Lookup" combines selected words from word area + all box content
- Each box's content is treated as ONE lookup phrase

**Smart content joining** (`get_content()`):
- CJK tags join without space: [無礼][講] → "無礼講" (correct compound word)
- Latin tags join with space: [ice][cream] → "ice cream"
- Typed whitespace preserved as-is
- Surrogate characters from Tkinter embedded windows automatically filtered

**Drag visual feedback**:
- Ghost Toplevel label follows cursor during drag
- Source tag dims (darker color) to indicate it's being moved
- Target box border highlights orange
- Cyan drop line (Toplevel `#00d4ff`, 3px) shows exact insertion point within box

**Implementation**:
- `CustomWordBoxesFrame` contains multiple `CustomWordBox` instances, manages drag orchestration
- `CustomWordBox` handles tag insertion, removal, position-aware insertion (`insert_tag_at_position`), visual order rebuild (`_rebuild_tags_order`)
- `WordTag` renders orange tags with right-click drag support (`on_drag_start` callback)
- Drag uses `<Button-3>` / `<B3-Motion>` / `<ButtonRelease-3>` with ghost Toplevel + drop line Toplevel
- Drop line positioned via `text_widget.bbox()` → screen coordinates

**Files involved**:
- `src/ui/custom_word_boxes.py` - WordTag, CustomWordBox, CustomWordBoxesFrame classes
- `src/ui/dictionary_mode.py` - Right-click drag support on WordLabel, drop target wiring
- `src/ui/dictionary_popup.py` - Composes CustomWordBoxesFrame, wraps lookup callback
- `src/ui/quick_translate.py` - Same composition at secondary callsite

## NLP Language Pack Install System (Important)

### Install verification with graceful degradation
`install()` verifies packages actually work after pip succeeds, not just pip exit code.
Flow: pip install → `is_installed()` verification → if fails, check `whitespace_separated` flag → graceful degradation or error.

### Graceful degradation (basic mode)
When post-install verification fails for whitespace-separated languages (Vietnamese, European):
- No scary error dialog shown
- Language marked as installed with "basic mode" (`config.nlp_basic_mode`)
- `_load_tokenizer()` uses `_simple_tokenize` (whitespace split) — works well for these languages
- UI shows info-blue "ℹ Installed with basic tokenization" instead of error
- `is_installed()` returns True for basic-mode languages
- CJK/Thai languages (`whitespace_separated=False`) still show error since simple tokenize is useless for them

### LanguagePack `whitespace_separated` field
`LanguagePack` dataclass has `whitespace_separated: bool = True`.
Set to `False` for: Japanese, Chinese (Simplified/Traditional), Korean, Thai.
Determines whether `_simple_tokenize` gives usable Dictionary results.

### EXE mode subprocess fallback
In EXE mode, the bundled Python may differ from system Python version. C extensions
(ufal.udpipe, fugashi, kiwipiepy) compiled for system Python won't load in the EXE.

**4-tier fallback in `is_installed()` and `_load_tokenizer()`:**
1. **Basic mode** — check `config.nlp_basic_mode`, use `_simple_tokenize` directly
2. **Direct import** — try `importlib.import_module()` (works when Python versions match)
3. **Subprocess import** — if direct fails AND is_frozen(), try import via system Python subprocess
4. **Simple tokenize** — whitespace-based fallback if both fail

Languages needing subprocess mode are tracked in `_subprocess_languages` set.
`_safe_tokenize_subprocess()` runs tokenization via system Python (like Vietnamese does).

### Parent module cache clearing
For dotted module names like `ufal.udpipe`, `is_installed()` clears both `ufal.udpipe`
AND `ufal` from `sys.modules` to prevent stale parent modules from blocking detection
of newly installed subpackages.

### EXE file detection
`is_installed()` checks custom packages dir (`~/.crosstrans/nlp_packages/`) for:
- Package directories, `__init__.py`, `.py` files
- C extension files: `.pyd` (Windows) and `.so` (Linux) via glob

### Key methods:
- `install()` — pip install + post-install verification
- `is_installed()` — 3-tier check (cache → direct import → subprocess)
- `_check_import_subprocess()` — verify module importable via system Python
- `_safe_tokenize_subprocess()` — generic subprocess tokenizer for any language
- `_build_subprocess_tokenize_script()` — generates per-language tokenization scripts

### Files involved:
- `src/core/nlp_manager.py` - All install/verify/tokenize logic
- `src/ui/settings/dictionary_tab.py` - Install UI (config update removed, handled by `install()`)

## Furigana System (Japanese Reading Guides)

Displays Japanese text with hiragana readings above kanji characters.
Being rolled out to every surface that can show Japanese — see `ROADMAP.md` rows F0–F7.
**Engine (F0), renderer (F1), Quick Translate popup (F2), main window + expanded view (F3) are
done**; the remaining phases add the input Reading pane, the dictionary result and word chips.

### Architecture: annotate at render time
```
src/core/furigana.py   engine   text -> (RubySegment(base, ruby), ...)     [no Tk]
src/ui/ruby_text.py    widget   segments -> embedded frames in a tk.Text   [no engine logic]
```
Reading generation and drawing are separate: the engine is pure logic (unit-testable, no
display), the widget is pure presentation. Callers annotate the text they are about to
display rather than receiving pre-annotated strings through the queue.

### Engine: `src/core/furigana.py`
- `annotate(text, lang_hint=None) -> tuple[RubySegment, ...]` — the main entry point. Safe on
  ANY string (empty, Latin, Chinese, provider missing) so callers need no branching.
- **Invariant I1**: `''.join(seg.base for seg in annotate(t)) == t`. Annotation can never alter
  the text it describes; violation falls back to plain.
- `should_annotate(text, lang_hint)` — needs kanji **plus** kana in the string, or an explicit
  `lang_hint="Japanese"`. Kanji-only strings look identical to Chinese, and
  `nlp_manager.detect_language()` reports Chinese for them, so a caller that knows the language
  must say so. Pass the hint wherever it is known.
- **Provider chain**: fugashi/UniDic (per-token `feature.kana`) → pykakasi → none. The aligner
  maps a whole-token reading onto interleaved kanji/kana runs and returns `None` on any
  mismatch. **Blank beats a wrong reading** — an absent reading is visibly absent, a wrong one
  is not.
- Two measured suppression rules: digit + counter pairs (`2日` would read as a bare fragment)
  and all-kanji compound refinement (`日本語` would read にっぽんご because UniDic tags 日本 as a
  proper noun).
- `MAX_RUBY_PAIRS = 400`, `lru_cache` on annotation, `prewarm()` to load the dictionary.
- Legacy `{kanji|reading}` notation (`to_notation` / `parse_notation` / `generate_notation`)
  still carries furigana through the translation queue. It escapes `\ { } |`, so source text
  containing a delimiter round-trips as text. New code should use segments.

### Renderer: `src/ui/ruby_text.py`
- `RubyText(tk.Text)` — `insert_ruby()` (annotates), `insert_notation()`, `insert_plain()`,
  `set_ruby()`, `set_notation()`, `clear()`. All work while `state='disabled'`.
- **`get_plain()` — always use this instead of `get()` on a RubyText.** `Text.get()` returns
  zero characters for an embedded window while consuming one index, so `get()` silently deletes
  every annotated word from Copy / Replace / re-send paths. `get_plain()` rebuilds the true
  text from `dump(text=True, window=True)`.
- **`fit_height(available_px)` — never set `height` from a line count.** The option counts rows
  of the base font (28 px) but a row carrying ruby is 47 px. `layout_rows()` simulates the
  `wrap='char'` layout and the pixel requirement is converted to `height` units. Row heights
  are derived from `font.metrics`, matching `Text.count(..., 'ypixels')` exactly.
- `estimate_notation_px()` sizes a window *before* the widget exists — required for the popup,
  whose `overrideredirect` Toplevel gets its geometry once.
- `MAX_ANNOTATE_CHARS = 3000`: longer text inserts plain, because annotation and frame
  construction run on the UI thread.
- Every ruby frame and label is bound to the wheel handler; an embedded window otherwise
  swallows `<MouseWheel>` and creates a scroll dead zone.

### Key details:
- **Embedded frames, not monospace text** — each pair is a `tk.Frame` holding two `tk.Label`s,
  inserted with `window_create(align='baseline')` so the base characters stay level with
  surrounding text at any font size.
- **`autostyle=False` on the ruby frame and labels** — ttkbootstrap would otherwise repaint them
  (see Known Issues). The `RubyText` widget itself stays themed so it matches its parent frame.
- **Word wrap**: `wrap=tk.CHAR` by default, but the popup's output box passes `wrap=tk.WORD` and
  `base_font=('Segoe UI', 11)` to keep Latin translations looking exactly as before.
- **Fonts/colors** (defaults): Yu Gothic 11pt base (`#ffffff` under a reading, `#cccccc` plain),
  Yu Gothic 7pt reading (`#80b8ff`), ruby plate `#363636`
- **Offline only** — no API call is involved in generating readings
- **Toggle**: Settings → Hotkeys → "Enable Furigana" checkbox. It gates **render-time
  annotation**, so it governs every surface, not just the pipeline's notation string.
- **Config**: `furigana_enabled` (default `True`), `furigana_reading_pane` (default `True`) —
  the latter is only the Reading pane's collapse state, not a second feature switch

### Which surfaces annotate, and with what hint
| Surface | Hint used | Notes |
|---------|-----------|-------|
| Popup source block | none (pipeline notation) | kanji-only source stays plain: it cannot be told from Chinese |
| Popup translation box | `target_lang` | authoritative, so kanji-only output *does* annotate |
| Popup, grammar fix | none | "Grammar" is a label, not a language; kana-bearing text still qualifies |
| Replace preview | `target_lang` | translated half only; the struck-through original stays plain |
| Custom Prompt edit mode | — | box is flattened to plain first (I3) |
| Main window output (`trans_text`) | `target_lang` / `selected_language` | read-only, so I3 holds by construction |
| Expanded view | `target_language` arg | read-only since F3; a disabled `tk.Text` still selects and copies |
| Main window input (`original_text`) | — | editable, so it stays plain (I3) forever; its readings live in the Reading pane below |
| Reading pane (`_reading_text`) | none | mirrors the input box; source language unknown, so kanji-only input stays plain |

All result text goes through `ruby_text.insert_output(widget, index, text, lang_hint, enabled)`,
so the toggle is honored in one place. Read every one of these boxes with `get_plain()`.

### Reading pane (main window input, F4)
Read-only `RubyText` under `original_text`, **shown by default** and collapsible via its
`▼ Reading` header (the choice persists in `furigana_reading_pane`). Hidden entirely while
`furigana_enabled` is off.

- **Why a separate pane and not inline ruby**: `edit_undo()` cannot restore destroyed embedded
  windows, and a caret moving between them behaves unpredictably. I3 is not negotiable for a box
  the user types in.
- **Refresh**: one debounced (`READING_PANE_DEBOUNCE_MS`) `<<Modified>>` binding on the input box.
  It covers typing, paste, drag-and-drop, undo/redo **and** the programmatic rewrites in
  `_update_translation_with_original()` / `_load_history_item()` — do not add per-call-site
  refreshes. Tk re-fires only after the flag is cleared, and clearing it fires the event again;
  the debounce collapses that pair into one render.
- **Nothing to annotate → dim placeholder**, never a mirror of the box above: mirroring is noise,
  and it would re-insert a pasted 50 000-character document on every edit.
- The pane grows with the content up to `READING_PANE_MAX_ROWS`, then scrolls.

### Files involved:
- `src/core/furigana.py` - engine: detection, provider chain, aligner, notation
- `src/ui/ruby_text.py` - `RubyText` widget: rendering, `get_plain()`, sizing, wheel
- `src/core/translation.py` - `generate_furigana()` / `_is_japanese_text()` delegate to the
  engine; queue integration in `do_translation()` (5-item tuple)
- `src/ui/quick_translate.py` - `_render_furigana()` (delegate), `show()` height budget,
  `_ruby_enabled()` / `_ruby_hint()`, replace preview, custom-prompt flattening
- `src/app.py` - `_create_translation_box()`, `_ruby_enabled()`, `_update_grammar_result()`,
  `_update_translation_with_original()`, `_copy_translation()`, `_open_expanded_translation()`;
  Reading pane: `_create_reading_pane()`, `_refresh_reading_pane()`,
  `_apply_reading_pane_state()`, `_toggle_reading_pane()`, `_on_input_modified()`,
  `_reading_pane_alive()`, `READING_PANE_*` constants
- `src/ui/expanded_window.py` - read-only `RubyText`, `get_plain()` for Copy and the counter
- `config.py` - `get_furigana_enabled()` / `set_furigana_enabled()`,
  `get_furigana_reading_pane()` / `set_furigana_reading_pane()`
- `src/ui/settings/hotkey_tab.py` - Furigana toggle checkbox
- `tests/test_furigana_core.py` (engine, headless), `tests/test_ruby_text.py` (widget),
  `tests/test_popup_ruby.py` (popup), `tests/test_main_window_ruby.py` (main window + expanded
  view), `tests/test_reading_pane.py` (input Reading pane) — the last two build `TranslatorApp`
  via `__new__` to avoid starting hotkeys/tray; the widget tests use the `tk_root` fixture in
  `tests/conftest.py`, which skips without a display

## Vision Detection System

Vision capability is detected via **real API testing** (not heuristic pattern matching).

### Data flow:
```
Test button → send 2x2 PNG to API → store vision_capable flag in config
Runtime     → read stored flag → heuristic fallback only for untested models
```

### How it works:
1. **Test-time** (`api_tab.py`): `test_vision_connection()` sends a 2x2 white PNG to the model. If the API accepts it, `vision_capable=True` is stored in config.
2. **Runtime** (`api_manager.py` `translate_image`/`translate_multimodal`): Checks stored `vision_capable` flag first. Only falls back to `MultimodalProcessor.is_vision_capable()` heuristic if flag is `None` (never tested).
3. **Startup** (`app.py` `_startup_api_check`): Uses stored flag (no API call). Heuristic fallback for untested models.

### Key details:
- **2x2 PNG required**: Groq rejects 1x1 images ("Image must have at least 2 pixels in each dimension")
- **`test_vision_connection()`** in `api_manager.py` (line ~493): Creates temp 2x2 PNG, calls `_generate_content()`, returns True/False
- **Heuristic kept as fallback**: `multimodal.py` `is_vision_capable()` still used for untested models (e.g., during `_try_model_rotation()`)
- **Stored flag location**: `config.json` → `api_keys[].vision_capable` (True/False/absent)

### Files involved:
- `src/ui/settings/api_tab.py` - Calls `test_vision_connection()` during Test button
- `src/core/api_manager.py` - `test_vision_connection()`, `translate_image()`, `translate_multimodal()` use stored flag
- `src/app.py` - `_startup_api_check()` uses stored flag
- `src/core/multimodal.py` - `is_vision_capable()` heuristic (fallback only)
