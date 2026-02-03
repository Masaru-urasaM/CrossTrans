# CrossTrans

![Version](https://img.shields.io/badge/version-1.9.8.2-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-yellow.svg)
![License](https://img.shields.io/badge/license-AGPL%20v3-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows-informational.svg)

A powerful Windows desktop application for instant text translation using AI. Select any text, press a hotkey, and get translations instantly - no window switching needed!

![CrossTrans](CrossTrans.png)

## Highlights

- **Instant Translation** - Select text, press hotkey, get translation in tooltip
- **Screenshot Translation** - Win+Alt+S to capture and translate any screen region
- **Free Trial Mode** - 100 translations/day without API key
- **15 AI Providers** - Google Gemini (free!), OpenAI, Claude, DeepSeek, Groq, HuggingFace, and more
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

| Provider | Models | Free Tier |
|----------|--------|-----------|
| **Google Gemini** | Gemini 2.5, 2.0, 1.5 | 1,500 req/day |
| **OpenAI** | o3, GPT-4.1, GPT-4o | No |
| **Anthropic** | Claude 4.5, Claude 3.5 | No |
| **DeepSeek** | DeepSeek-R1, V3 | Yes |
| **Groq** | Llama 3.3, Mixtral | Yes |
| **xAI** | Grok 3, Grok 2 | No |
| **Mistral** | Mistral Large, Pixtral | No |
| **Perplexity** | Sonar Pro, Reasoning | No |
| **Cerebras** | Llama 4, Llama 3.3 | Yes |
| **SambaNova** | DeepSeek-R1, Llama 405B | Yes |
| **Together** | Llama 3.3, Qwen 2.5 | No |
| **SiliconFlow** | Qwen 2.5, DeepSeek-V3 | Yes |
| **OpenRouter** | 400+ models | Varies |
| **HuggingFace** | Qwen 2.5, Llama 3.x, Gemma | Yes |

**Smart Routing** - Automatically detects provider from API key or model name.

### User Interface
- **Compact Tooltip** - Translation appears near cursor, auto-sizes to content
- **Full Translator** - Rich window with language selector, custom prompts, attachments
- **Dark Theme** - Modern UI with ttkbootstrap
- **System Tray** - Runs quietly in background
- **Translation History** - Review and reuse past translations (up to 100 entries)

### Smart Features
- **Dictionary Mode** - Click words to select, get definitions, pronunciation, examples
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

### Get Your Free API Key (Optional)

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Click "Create API Key"
3. Copy the key and paste in Settings

---

## Usage

### Basic Translation
1. **Start the app** - Look for "CT" icon in system tray
2. **Select any text** in any application
3. **Press hotkey** (e.g., `Win+Alt+V` for Vietnamese)
4. **Translation appears** in a tooltip near your cursor

### Tooltip Actions
- **Copy** - Copy translation to clipboard
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

## What's New in v1.9.8.2

### Dictionary Mode Improvements
- **Hyphenated words preserved** - Words like "auto-update", "state-of-the-art" now stay as single tokens
- **Better sentence detection** - Expanded punctuation list (55 characters) for accurate dictionary vs sentence detection
- **Language pack info** - Guide tab updated with NLP language pack instructions

### Performance (v1.9.8.1)
- **Settings window opens instantly** - Lazy loading for heavy tabs (API, Dictionary, Guide)
- **NLP pre-warming** - Dictionary tab loads faster on subsequent opens
- **Cache optimization** - Fixed bug that was clearing cache on every Settings open

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
# Output: dist/CrossTrans_v1.9.8.2.exe
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

- Powered by Google Gemini AI, OpenAI, Anthropic, and other AI providers
- Built with Python, Tkinter, and ttkbootstrap
- Icons and UI inspired by modern design principles

---

**Made with care for translators, developers, and anyone who works across languages.**
