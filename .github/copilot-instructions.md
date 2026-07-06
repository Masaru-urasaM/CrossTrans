# CrossTrans Copilot Instructions

**CrossTrans v1.9.13** — Windows desktop translation app with 15 AI API providers, instant hotkey translation, screenshot OCR, furigana reading guides, and trial mode.

**See [CLAUDE.md](../CLAUDE.md) for comprehensive technical documentation.**

---

## Quick Start for Development

### Build, Run, Test
```bash
# Build EXE (auto-versioned)
build_exe.bat

# Run app
python main.py

# Run tests with coverage
pytest tests/ --cov=src
```

### Key Files at a Glance
| Task | File(s) |
|------|---------|
| Change app version | `src/constants.py` → `VERSION` |
| Add/remove AI models | Cloudflare KV `MODELS_KV` (no rebuild needed) |
| Add new UI component | `src/ui/` + callback injection via `configure_callbacks()` |
| Add settings tab | `src/ui/settings/` then register in `main.py` |
| Translation logic | `src/core/translation.py` |
| Furigana rendering | `src/ui/quick_translate.py` (`_render_furigana`) + `src/core/translation.py` (`generate_furigana`) |
| Hotkey mappings | `src/core/hotkey.py` |
| Update system | `src/utils/updates.py` |

---

## Architecture Overview

### UI + Coordinator Pattern
- **[src/app.py](../src/app.py)** (~1630 lines): Main `TranslatorApp` orchestrator
  - Manages services: hotkeys, translation, file processor, clipboard
  - Handles window lifecycle and UI state
  - Injects callbacks into modular UI components
- **[src/ui/](../src/ui/)**: UI components (quick_translate, tray, dialogs, settings)
- **[src/core/](../src/core/)**: Business logic (22 modules)
- **[src/utils/](../src/utils/)**: Utilities (update system, single instance, logging)

### Key Patterns

#### 1. **Callback Injection (Dependency Injection)**
Extracted UI modules **never accept app reference** — avoid circular imports:

```python
# ✓ CORRECT: Inject callbacks
self.screenshot_handler = ScreenshotHandler(self.root, self.config, ...)
self.screenshot_handler.configure_callbacks(
    on_show_quick_translate=self.show_quick_translate,
    get_selected_language=lambda: self.selected_language
)

# ✗ WRONG: Don't pass app reference
self.screenshot_handler = ScreenshotHandler(self.root, self.config, app=self)
```

Used in: [screenshot_handler.py](../src/ui/screenshot_handler.py), [dictionary_popup.py](../src/ui/dictionary_popup.py), [expanded_window.py](../src/ui/expanded_window.py)

#### 2. **Remote Config Singleton (3-Tier Fallback)**
Dynamic model/provider config fetched from Cloudflare KV:

```python
from src.core.remote_config import get_config

config = get_config()  # Thread-safe singleton
providers = config.providers_list  # Returns live list
model_map = config.model_provider_map  # Model → provider mapping
```

Fallback chain: Remote KV → Local cache (`%APPDATA%/models_config.json`) → Hardcoded (`constants.py`)

Used in: [api_tab.py](../src/ui/settings/api_tab.py), [api_manager.py](../src/core/api_manager.py)

#### 3. **Auto-Provider Detection**
When user selects "Auto" for model:
- Priority: `MODEL_PROVIDER_MAP` → API key pattern match → fallback list
- Performance: Caches working models per API key prefix
- See [api_manager.py](../src/core/api_manager.py#L60-L100)

#### 4. **Multi-Provider API Manager**
15 AI providers (Google, OpenAI, Claude, DeepSeek, Groq, etc.) with smart health tracking:
- [api_manager.py](../src/core/api_manager.py): Provider detection, API routing
- [provider_health.py](../src/core/provider_health.py): Success/failure tracking + fallback logic

---

## 🚨 Critical Gotchas & Anti-Patterns

### Update System (MUST READ)
**See [CLAUDE.md](../CLAUDE.md) "Auto-Update System" section for full details.**

| Gotcha | Impact | Solution |
|--------|--------|----------|
| **Must use `os._exit(0)`, not `sys.exit()`** | `sys.exit()` raises `SystemExit` silently caught by Tkinter's `after()` handler | Always: `os._exit(0)` after launching batch script |
| **Never use `(` or `)` in batch echo inside if blocks** | cmd.exe interprets `)` as closing the if block | Use separate echo statements or escape differently |
| **Always space before `>` in batch echo** | `echo 1.9.8>file` is interpreted as FD redirect | Correct: `echo 1.9.8 > file` |
| **Never combine `CREATE_NO_WINDOW` + `DETACHED_PROCESS`** | Mutually exclusive per Windows docs | Use only `CREATE_NO_WINDOW` |

### PyInstaller First-Launch Gotcha
Fresh-built EXE may fail on **first double-click** (Windows Defender scanning). **Not a bug** — works on 2nd attempt.  
Update system's batch retry handles this. See [CLAUDE.md](../CLAUDE.md) "Auto-Update System" section.

### Tkinter DnD Library
Always check flags before drag-and-drop:
```python
if HAS_DND and HAS_WINDND:
    # Use DnD features
else:
    # Fallback to paste button
```
See [app.py](../src/app.py#L30-L45).

### Single Instance Lock
App enforces single instance via TCP socket on `127.0.0.1:47823`.  
Second launch shows warning and exits. See [single_instance.py](../src/utils/single_instance.py).

---

## Adding New Features

### Adding a New UI Component

1. **Create file in `src/ui/`**, e.g. `src/ui/my_feature.py`
2. **Accept root, config, and other non-app dependencies**:
   ```python
   class MyComponent:
       def __init__(self, root, config, translation_service, ...):
           self.root = root
           self._callbacks = {}
       
       def configure_callbacks(self, on_action=None, on_error=None):
           self._callbacks['on_action'] = on_action
           self._callbacks['on_error'] = on_error
   ```
3. **Register callbacks in `TranslatorApp.__init__()`**:
   ```python
   self.my_component = MyComponent(self.root, self.config, self.translation)
   self.my_component.configure_callbacks(
       on_action=self._handle_action,
       on_error=self._show_error
   )
   ```

### Adding a Settings Tab

1. Create `src/ui/settings/my_tab.py` (see [hotkey_tab.py](../src/ui/settings/hotkey_tab.py) for pattern)
2. Register in [src/ui/settings/main.py](../src/ui/settings/main.py#L20-L30):
   ```python
   from .my_tab import MyTab
   tabs.append(("My Tab", MyTab(notebook, self.config, ...)))
   ```

### Adding Translation Logic

- **Core service**: [src/core/translation.py](../src/core/translation.py)
- **API routing**: [src/core/api_manager.py](../src/core/api_manager.py)
- **File processing**: [src/core/file_processor.py](../src/core/file_processor.py)
- **Vision/OCR**: [src/core/multimodal.py](../src/core/multimodal.py)

### Adding a New AI Provider

1. Update models in Cloudflare KV `MODELS_KV` (no code change if API format matches existing provider)
2. If new API format needed:
   - Add handler in [src/core/api_manager.py](../src/core/api_manager.py#L150+)
   - Update `_identify_provider()` detection logic
   - Add API key pattern to [src/constants.py](../src/constants.py)

---

## Project Layout

```
CrossTrans/
├── build_exe.bat                 # EXE build script (PyInstaller)
├── main.py                       # Entry point (single instance check)
├── config.py                     # Config management + registry auto-start
├── CrossTrans.spec               # PyInstaller spec file
├── src/
│   ├── app.py                    # TranslatorApp coordinator (~1630 lines)
│   ├── constants.py              # VERSION, LANGUAGES, hardcoded fallback config
│   ├── core/                     # Business logic (22 modules)
│   │   ├── api_manager.py        # Multi-provider API communication
│   │   ├── translation.py        # Core translation service
│   │   ├── hotkey.py             # Win+Alt+V/E/J/C/S registration
│   │   ├── remote_config.py      # Cloudflare KV config (singleton)
│   │   ├── multimodal.py         # Vision/OCR support
│   │   ├── clipboard.py          # Clipboard manager
│   │   ├── history.py            # Translation history
│   │   └── [15+ other modules]   # Crypto, auth, file processing, etc.
│   ├── ui/                       # UI components (12+ files)
│   │   ├── quick_translate.py     # Quick Translate popup (Copy, Replace, Dict)
│   │   ├── tray.py               # System tray manager
│   │   ├── dictionary_popup.py   # Dictionary UI (extracted module)
│   │   ├── screenshot_handler.py # Screenshot OCR (extracted module)
│   │   ├── expanded_window.py    # Fullscreen translation (extracted)
│   │   ├── settings/             # Settings tabs package
│   │   │   ├── main.py           # Settings window coordinator
│   │   │   ├── api_tab.py        # API keys, provider selection
│   │   │   ├── hotkey_tab.py     # Hotkey configuration
│   │   │   ├── general_tab.py    # General settings
│   │   │   └── [other tabs]
│   │   └── [dialogs, attachments, etc.]
│   ├── utils/
│   │   ├── updates.py            # Auto-update system (critical!)
│   │   ├── single_instance.py    # TCP socket single instance lock
│   │   └── ui_helpers.py         # Dark title bar, utilities
│   └── assets/
│       └── generate_icons.py     # Icon generation from SVG
├── tests/                        # pytest test suite
├── docs/
│   └── models_config_template.json  # Template JSON for Cloudflare KV config
├── CLAUDE.md                     # 📖 DETAILED TECHNICAL DOCUMENTATION
├── README.md                     # User-facing feature list
└── requirements.txt
```

---

## Configuration & Environment

### Config Storage
- Location: `%APPDATA%/CrossTrans/config.json`
- API keys: DPAPI encrypted (Windows secret store)
- Auto-start: Registry entry `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\CrossTrans`

### Environment
- **Python**: ≥3.10
- **UI Framework**: Tkinter (stdlib) + ttkbootstrap
- **Key Dependencies**: pyperclip, pystray, pywin32, Pillow, keyboard, PyPDF2, python-docx
- **Windows Hello**: Optional (winsdk, requires VS Build Tools)

### Remote Config (Cloudflare KV)
Models and providers are fetched from remote at startup:
- Worker endpoint: `GET /v1/config`
- KV key: `MODELS_KV` → `models_config`
- Update without rebuilding EXE

---

## Code Style & Conventions

### Language Policy
**Code MUST be English only. NO Vietnamese in code. Vietnamese is for communication only.**  
See [CLAUDE.md](../CLAUDE.md) line 4—this is a hard requirement.

### Import Order
1. Standard library (os, sys, json, etc.)
2. Third-party (tkinter, pywin32, etc.)
3. Local (from src.core, from src.ui, etc.)

### Naming
- Classes: PascalCase (`ScreenshotHandler`, `TranslatorApp`)
- Functions/methods: snake_case (`configure_callbacks`, `_show_quick_translate`)
- Constants: UPPER_CASE (`VERSION`, `MAX_RETRIES`)
- Private: Leading underscore (`_callbacks`, `_working_models_cache`)

### Threading
- Translation happens in thread via `threading.Thread`
- UI updates marshalled back to main thread via `root.after()`
- See [translation.py](../src/core/translation.py) for pattern

---

## Common Development Tasks

| Task | Command | File(s) |
|------|---------|---------|
| **Change version** | Edit `VERSION` in `src/constants.py` | [constants.py](../src/constants.py#L1-L5) |
| **Update models** | Edit `MODELS_KV` key in Cloudflare Dashboard | No rebuild needed |
| **Add language** | Add to `LANGUAGES` dict in `src/constants.py` | [constants.py](../src/constants.py) |
| **Key bindings** | Modify hotkey registration in `src/core/hotkey.py` | [hotkey.py](../src/core/hotkey.py) |
| **Test update system** | Set `VERSION` to older value, build, test → revert | [constants.py](../src/constants.py) + [build_exe.bat](../build_exe.bat) |
| **Check update logs** | `%TEMP%/crosstrans_update.log` | Auto-generated |

---

## Related Documentation

- **[CLAUDE.md](../CLAUDE.md)** — Comprehensive technical docs (this should be your primary reference)
  - App architecture details
  - Auto-update system deep dive
  - Remote config system
  - All 22 core modules documented
  - Replace button implementation
  - Configuration details

- **[README.md](../README.md)** — User-facing feature documentation

---

## Tips for Agents

1. **Always consult [CLAUDE.md](../CLAUDE.md)** first—it has detailed design decisions and gotchas
2. **Remote config is key**: Use `get_config()` singleton instead of hardcoded constants from the start
3. **Use callback injection**: New UI components should never accept `app` reference
4. **Update system is fragile**: Read CLAUDE.md "Auto-Update System" section carefully if touching `updates.py`
5. **Test on fresh build**: Always test update system with a clean build (see "Test update system" task)
6. **Check single instance**: If app won't launch, check if another instance is already running on port 47823

---

**Last Updated**: March 2026 | **Version**: 1.9.13
