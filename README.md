# CrossTrans

![Version](https://img.shields.io/badge/version-1.9.10-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-yellow.svg)
![License](https://img.shields.io/badge/license-AGPL%20v3-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows-informational.svg)

A powerful Windows desktop application for instant text translation using AI. Select any text, press a hotkey, and get translations instantly - no window switching needed!

![CrossTrans](CrossTrans.png)

## Highlights

- **Instant Translation** - Select text, press hotkey, get translation in tooltip
- **Screenshot Translation** - Win+Alt+S to capture and translate any screen region
- **Free Trial Mode** - 100 translations/day without API key
- **15 AI Providers** - Google, OpenAI, Anthropic, DeepSeek, Groq, and more (many offer free tiers)
- **File Processing** - Translate documents (.docx, .txt, .srt, .pdf) and images
- **120+ Languages** - Comprehensive language support
- **Custom Hotkeys** - Configure any key combination for any language

---

## Features

### Quick Translation Hotkeys
| Hotkey | Action |
|--------|--------|
| `Win+Alt+V` | Translate to Vietnamese |
| `Win+Alt+E` | Translate to English |
| `Win+Alt+J` | Translate to Japanese |
| `Win+Alt+C` | Translate to Chinese Simplified |
| `Win+Alt+S` | **Screenshot OCR Translation** |

**+ 4 customizable hotkeys** for any language of your choice.

### Free Trial Mode
- **100 free translations per day** without any API key
- Perfect for trying out the app before getting your own API key
- Quota resets at midnight

### Screenshot Translation
- **Win+Alt+S** - Capture any screen region for instant OCR and translation
- **Multi-monitor support** - Works across all connected displays
- **Visual selection** - Semi-transparent overlay with drag selection
- **Configurable target language** - Set in Settings > Hotkeys tab
- **Open Translator integration** - Screenshot loads into Attachments for further editing

### File Processing
- **Image Translation** - Drag & drop images for OCR and translation
- **Document Support** - Process `.docx`, `.txt`, `.srt`, `.pdf` files
- **Multi-file Batch** - Translate multiple files in a single API request
- **Drag & Drop** - Simply drop files onto the translator window
- **Double-click Preview** - Open attached files/images with system default app

### Multi-Provider Support

| Provider | Provider |
|----------|----------|
| Google Gemini | OpenAI |
| Anthropic | DeepSeek |
| Groq | xAI |
| Mistral | Perplexity |
| Cerebras | SambaNova |
| Together | SiliconFlow |
| OpenRouter (400+) | HuggingFace |

Many providers offer free API keys. See Settings → Guide tab for details.

**Smart Routing** - Automatically detects provider from API key or model name.

### User Interface
- **Compact Tooltip** - Translation appears near cursor, auto-sizes to content
- **Full Translator** - Rich window with language selector, custom prompts, attachments
- **Dark Theme** - Modern UI with ttkbootstrap
- **System Tray** - Runs quietly in background
- **Translation History** - Review and reuse past translations (up to 100 entries)

### Smart Features
- **Dictionary Mode** - Click words to select, get definitions, pronunciation, synonyms, antonyms, examples
- **Custom Prompts** - Add instructions like "Make it formal" or "Technical terms only"
- **Clipboard Preservation** - Your files/images in clipboard are preserved
- **Auto-start** - Optionally start with Windows
- **Auto-update** - Get notified of new versions

---

## Installation

### Prerequisites
- Windows 10/11
- Python 3.10+ (if running from source)
- An API key (optional - free trial mode available!)

### Option 1: Download EXE (Recommended)
1. Go to [Releases](https://github.com/Masaru-urasaM/CrossTrans/releases)
2. Download the newest version of `CrossTrans.exe`
3. Run the application
4. Start translating immediately with trial mode, or enter your API key in Settings

### Option 2: Run from Source

```bash
# Clone repository
git clone https://github.com/Masaru-urasaM/CrossTrans.git
cd CrossTrans

# Install dependencies
pip install -r requirements.txt

# Run
python main.py

# Or run without console window
# Double-click run_silent.vbs
```

### Get an API Key (Optional)

Many providers offer free API keys. Get one from any supported provider and paste it in Settings → API Key tab. See the in-app Guide tab for step-by-step instructions.

---

## Usage

### Basic Translation
1. **Start the app** - Look for "CT" icon in system tray
2. **Select any text** in any application
3. **Press hotkey** (e.g., `Win+Alt+V` for Vietnamese)
4. **Translation appears** in a tooltip near your cursor

### Tooltip Actions
- **Copy** - Copy translation to clipboard
- **Replace** - Replace selected text in source app with translation
  - **Manual mode** (default): Shows preview with strikethrough original → translated text, then Agree/Cancel
  - **Quick mode**: Immediately pastes translation (configurable in Settings → Hotkeys)
  - **⚙ Gear icon**: Quick access to Replace mode settings
- **Dictionary** - Open word-by-word lookup mode
- **Open Translator** - Open full window with more options
- **X** or `Escape` - Close tooltip

### Full Translator Window
Right-click tray icon -> "Open Translator" or click from tooltip

Features:
- Edit original text
- Choose from 120+ languages
- Add custom prompt for translation style
- Attach images or files
- View translation history

### File Translation
1. Open Full Translator
2. Click **+** button or drag & drop files
3. Supported: Images (PNG, JPG, GIF, WebP), Documents (DOCX, TXT, SRT, PDF)
4. Click Translate - all files processed in single API call

---

## Configuration

### Settings Tabs

**General**
- Auto-start with Windows
- Check for updates
- Enable/disable history
- Theme selection

**Hotkeys**
- View default hotkeys
- Record custom hotkeys (click "Record" then press keys)
- Assign any language to any hotkey
- Replace Mode toggle (Quick Replace vs Manual Replace)

**API Key**
- Add multiple API keys
- Auto-detect provider or select manually
- Test connection
- View vision/file capabilities

**Guide**
- Step-by-step instructions for getting started
- Troubleshooting tips

### Custom Prompts
In translator window, use "Custom prompt" field:
- "Make it formal" - Business communication
- "Use casual tone" - Friendly messages
- "Technical translation" - Documentation
- "Explain like I'm 5" - Simple explanations
- "Preserve formatting" - Keep structure

---

## Project Structure

```
CrossTrans/
├── main.py                 # Entry point
├── config.py               # Configuration management
├── requirements.txt        # Dependencies
├── src/
│   ├── app.py              # Main application
│   ├── constants.py        # Languages, providers, models
│   ├── core/
│   │   ├── remote_config.py # Dynamic model/provider config (Cloudflare KV)
│   │   ├── api_manager.py  # AI provider management
│   │   ├── translation.py  # Translation service
│   │   ├── hotkey.py       # Global hotkey system
│   │   ├── clipboard.py    # Clipboard operations
│   │   ├── multimodal.py   # Vision processing
│   │   ├── file_processor.py # Document text extraction
│   │   ├── pdf_ocr.py      # Scanned PDF OCR
│   │   ├── screenshot.py   # Screenshot capture for OCR
│   │   ├── history.py      # Translation history
│   │   ├── crypto.py       # Secure API key storage (DPAPI)
│   │   ├── ssl_pinning.py  # SSL certificate pinning
│   │   ├── auth.py         # Windows Hello authentication
│   │   ├── drop_handler.py # Drag-drop handler
│   │   ├── quota_manager.py # Trial mode quota tracking
│   │   ├── trial_api.py    # Trial mode API handler
│   │   └── provider_health.py # Smart provider fallback
│   ├── ui/
│   │   ├── settings.py     # Settings window
│   │   ├── attachments.py  # File attachment widget
│   │   ├── dictionary_mode.py # Dictionary word selection
│   │   ├── history_dialog.py # History viewer with search
│   │   ├── progress_dialog.py # Progress indicator
│   │   ├── toast.py        # Toast notifications
│   │   ├── tray.py         # System tray manager
│   │   ├── tooltip.py      # Tooltip widget
│   │   └── dialogs.py      # Error dialogs
│   ├── assets/             # Icon assets
│   └── utils/
│       ├── logging_setup.py    # Logging
│       ├── single_instance.py  # Prevent duplicates
│       └── updates.py          # Auto-update
├── tests/                  # Unit tests
└── logs/                   # Application logs
```

---

## Troubleshooting

### API Error / Connection Failed
1. Open Settings -> API Key tab
2. Verify your API key is correct
3. Select correct Provider (or use "Auto")
4. Click "Test" to verify connection

### Translation Not Working
- Ensure text is selected (try Ctrl+C manually first)
- Wait for cooldown (2 seconds between translations)
- Some apps may block clipboard access
- Check logs folder for error details

### Hotkeys Not Working
- Check Settings -> Hotkeys for configured shortcuts
- Try running as administrator
- Some apps capture certain key combinations
- Ensure no hotkey conflicts with other software

### Vision/File Features Disabled
- You need a vision-capable model (e.g., Gemini 2.0 Flash, GPT-4o)
- Go to Settings -> API Key -> Click "Test"
- If test shows "Image OK", vision is enabled

### Trial Mode Issues
- Trial mode requires internet connection
- If quota exhausted, wait until midnight or add your own API key

---

## What's New in v1.9.10

### Replace in Source App
- **Replace button** - One-click replace selected text with translation directly in the source app
- **Manual Replace mode** (default) - Preview with strikethrough original → translated text, then Agree/Cancel for safe replacement
- **Quick Replace mode** - Immediate paste without preview for faster workflow
- **⚙ Gear icon** - Dropdown menu next to Replace button for quick access to settings
- **Replace Mode toggle** - Configurable in Settings → Hotkeys → Replace Mode section
- **WS_EX_NOACTIVATE tooltip** - Tooltip doesn't steal focus from source app, keeping text selection alive

### Dictionary Mode Improvements
- **Synonyms & Antonyms** - Dictionary now shows synonyms and antonyms with translations (8-field output)
- **Smart word filtering** - Punctuation, symbols, and pure numbers no longer appear as clickable word buttons
- **Unicode letter detection** - Filter works across all languages (Latin, CJK, Cyrillic, Arabic, Thai, Korean)
- **Dedicated mode only** - Dictionary lookup only through the Dictionary button, no auto-detection on short text

### Generic API Guidance
- Removed provider-specific API key links and pricing from all UI dialogs
- Guide tab now shows generic instructions for any supported provider

### Previous in v1.9.9

### Dynamic Remote Model Configuration
- **Models updated without rebuilding EXE** - Provider list, model names, and API URLs are now fetched from Cloudflare KV
- **3-tier fallback** - Remote → Local cache (24h) → Hardcoded defaults, app never blocks on network
- **15 AI providers, 180+ models** - Updated dynamically without app update

### Auto-Update System Overhaul
- **Versioned EXE rename** - New EXE saved as `CrossTrans_v{version}.exe`, old renamed to `.bak`
- **Registry auto-start sync** - Auto-start path updated automatically after update
- **First-launch retry** - Handles Windows Defender scanning delay on new EXE

### Performance (v1.9.8.1)
- **Settings window opens instantly** - Lazy loading for heavy tabs (API, Dictionary, Guide)
- **NLP pre-warming** - Dictionary tab loads faster on subsequent opens

### Dictionary Mode (v1.9.8.2)
- **Hyphenated words preserved** - Words like "auto-update" now stay as single tokens
- **Better sentence detection** - Expanded punctuation detection (55 characters)

### Stability (v1.9.8)
- **Trial mode auto-recheck** - Automatically re-validates API keys every 24h
- **Version upgrade detection** - Clears cache when upgrading to new version
- **Settings refactored** - Split into modular package structure

### Previous in v1.9.7
- **Screenshot Translation** - Win+Alt+S captures screen region for OCR translation
- **Multi-monitor support** - Works across all connected displays
- **Double-click to Preview** - Open attached files with system default app
- **Auto-check updates** - Non-intrusive toast notification on startup

### Previous in v1.9.6
- Critical bug fix for Dictionary Language Pack in EXE builds
- Auto-detects system Python when running from EXE

### Previous in v1.9.5
- Fixed API Key saving position issue
- Animated "Installing..." text for Dictionary Language Pack
- Google provider now uses REST API (EXE 30MB smaller)

### Previous in v1.9.4
- HuggingFace provider added (14 AI providers total)
- Test button now saves API key even on test failure

### Previous in v1.9.2-1.9.3
- Dictionary Mode with interactive word selection
- Enhanced Trial mode security
- 180+ models from 14 providers

### Previous in v1.7.0-1.9.0
- Trial Mode - 100 free translations/day without API key
- Windows Hello Authentication for API key protection
- Smart Provider Fallback - auto-switch to backup API
- Scanned PDF OCR support
- Toast notifications and Search History

---

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Setup
```bash
git clone https://github.com/Masaru-urasaM/CrossTrans.git
cd CrossTrans
pip install -r requirements.txt
python main.py
```

### Building EXE
```bash
pip install pyinstaller
pyinstaller CrossTrans.spec
# Output: dist/CrossTrans_v1.9.9.exe
```

### Running Tests
```bash
pip install pytest pytest-cov pytest-mock
pytest tests/ --cov=src --cov-report=html
```

---

## License

This project is licensed under the GNU Affero General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Powered by 15+ AI providers including Google, OpenAI, Anthropic, and more
- Built with Python, Tkinter, and ttkbootstrap
- Icons and UI inspired by modern design principles

---

**Made with care for translators, developers, and anyone who works across languages.**
