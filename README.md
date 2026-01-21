# Gemini Translator

A Windows desktop application for instant text translation using Google's Gemini AI. Select any text, press a hotkey, and get translations in a compact tooltip - no window switching needed!

## Features

- **Hotkey Translation**: Press simple hotkeys to translate selected text instantly
  - `Win+Alt+V` → Vietnamese
  - `Win+Alt+E` → English
  - `Win+Alt+J` → Japanese
- **Compact Tooltip**: Translation appears near your cursor, not in a separate window
- **Full Translator Window**: Open the complete interface for more options
- **30+ Languages**: Support for major world languages
- **Open in Gemini**: Quick access to Gemini web for complex translations
- **System Tray**: Runs quietly in the background
- **Single Instance**: Prevents multiple instances from running

## Screenshots

<!-- Add screenshots here -->
<!-- ![Tooltip](assets/tooltip.png) -->
<!-- ![Full Window](assets/full-window.png) -->

## Installation

### Prerequisites

- Python 3.10 or higher
- Windows 10/11
- Gemini API key (free)

### Option 1: Download .exe (Recommended)

1. Go to [Releases](https://github.com/sytacxinh/gemini-translator/releases)
2. Download `GeminiTranslator.exe` and `.env`
3. Edit `.env` file and replace `your_api_key_here` with your actual API key
4. Get your free API key at: https://aistudio.google.com/app/apikey
5. Run `GeminiTranslator.exe`

### Option 2: Run from source

1. **Clone the repository**
   ```bash
   git clone https://github.com/sytacxinh/gemini-translator.git
   cd gemini-translator
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Get your Gemini API key**
   - Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
   - Create a new API key (it's free!)

4. **Configure API key**

   Create a `.env` file in the project folder:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```

5. **Run the application**
   ```bash
   python translator.py
   ```

   Or double-click `run_silent.vbs` to run without console window.

## Usage

1. **Start the app** - It will minimize to system tray (look for "GT" icon)

2. **Translate text**:
   - Select any text in any application
   - Press one of the hotkeys:
     - `Win+Alt+V` → Vietnamese
     - `Win+Alt+E` → English
     - `Win+Alt+J` → Japanese
   - A tooltip with the translation will appear near your cursor

3. **Tooltip actions**:
   - **Copy** - Copy translation to clipboard
   - **Open Translator** - Open full window with more options
   - **✕** - Close tooltip (or press `Escape`)

4. **Full Translator window**:
   - Edit original text
   - Choose any of 30+ languages
   - Re-translate with different settings
   - Open in Gemini web for complex queries

5. **Exit**: Right-click the tray icon → Quit

## Auto-start with Windows (Optional)

1. Press `Win + R`, type `shell:startup`, press Enter
2. Create a shortcut to `run_silent.vbs` (or `GeminiTranslator.exe`) in that folder

## Configuration

Edit the hotkeys in `translator.py` if needed:

```python
# In the run() method, modify the GlobalHotKeys:
hotkeys = GlobalHotKeys({
    '<cmd>+<alt>+v': lambda: ...,  # Win+Alt+V → Vietnamese
    '<cmd>+<alt>+e': lambda: ...,  # Win+Alt+E → English
    '<cmd>+<alt>+j': lambda: ...,  # Win+Alt+J → Japanese
})

# Cooldown between translations (seconds)
COOLDOWN = 2.0
```

## Requirements

- pyperclip
- google-generativeai
- pystray
- Pillow
- pynput

## Troubleshooting

### "GEMINI_API_KEY not found"
Make sure you've created the `.env` file in the same folder as the app with your API key.

### Translation not working
- Check if text is actually selected (try Ctrl+C manually)
- Some applications may block clipboard access
- Wait for the cooldown period (2 seconds between translations)

### Hotkeys not working
- Make sure no other app is using the same hotkey combination
- Try running the app as administrator

### Multiple instances running
The app should prevent this automatically. If it happens, check Task Manager and end extra processes.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Powered by [Google Gemini AI](https://deepmind.google/technologies/gemini/)
- Built with Python and Tkinter
