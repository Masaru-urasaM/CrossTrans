"""
User Guide tab functionality for Settings window.
"""
import sys
import os
import logging
import webbrowser

from PIL import Image, ImageTk

from src.core.remote_config import get_config

import tkinter as tk
from tkinter import BOTH, X, LEFT, RIGHT, W, NW

try:
    import ttkbootstrap as ttk
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.constants import GITHUB_REPO, FEEDBACK_URL, LANGUAGES

# Unicode icons for section headers (Segoe UI safe)
SECTION_ICONS = {
    "Getting Started": "\u25B6",        # ▶ right-pointing triangle
    "Quick Translate": "\u26A1",        # ⚡ high voltage (speed)
    "Replace Mode": "\u21C4",           # ⇄ right arrow over left arrow
    "Hotkeys": "\u2328",               # ⌨ keyboard
    "Screenshot Translation": "\u2316",  # ⌖ position indicator
    "Dictionary Mode": "\u2261",        # ≡ triple bar
    "File Translation": "\u2197",       # ↗ north east arrow
    "AI Providers": "\u2601",           # ☁ cloud
    "Tips & Tricks": "\u2605",          # ★ black star
    "Troubleshooting": "\u2692",        # ⚒ hammer and pick
}


class GuideTabMixin:
    """Mixin class providing User Guide tab functionality."""

    def _get_screenshot_path(self, filename):
        """Get absolute path to a screenshot, works for dev and PyInstaller bundle."""
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            # Running as script - go up 3 levels from src/ui/settings/ to project root
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        return os.path.join(base_path, 'docs', 'screenshots', filename)

    def _add_guide_image(self, parent, filename, caption=None, max_width=600):
        """Add a screenshot image to the guide tab.

        Silently skips if the image file is missing or fails to load.
        """
        path = self._get_screenshot_path(filename)
        if not os.path.exists(path):
            return
        try:
            img = Image.open(path)
            # Resize if wider than max_width, keeping aspect ratio
            if img.width > max_width:
                ratio = max_width / img.width
                new_size = (max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._guide_images.append(photo)  # Prevent GC
            try:
                bg = parent.cget('background')
            except Exception:
                bg = '#2b2b2b'  # Dark theme fallback
            label = tk.Label(parent, image=photo, bg=bg if bg else '#2b2b2b')
            label.pack(anchor=W, padx=20, pady=(5, 2))
            # Bind mousewheel so scrolling works over images
            label.bind("<MouseWheel>", lambda e: parent.event_generate("<MouseWheel>", delta=e.delta))
            if caption:
                cap_label = ttk.Label(parent, text=caption, font=('Segoe UI', 8, 'italic'),
                                      foreground='#666666')
                cap_label.pack(anchor=W, padx=20, pady=(0, 5))
                cap_label.bind("<MouseWheel>", lambda e: parent.event_generate("<MouseWheel>", delta=e.delta))
        except Exception as e:
            logging.warning(f"Failed to load guide screenshot {filename}: {e}")

    def _create_guide_tab(self, parent):
        """Create user guide tab with helpful instructions."""
        self._guide_images = []  # Keep PhotoImage references to prevent GC

        # Scrollable container
        canvas = tk.Canvas(parent, highlightthickness=0)
        guide_container = ttk.Frame(canvas)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=RIGHT, fill='y')
        canvas.pack(side=LEFT, fill=BOTH, expand=True)

        window_id = canvas.create_window((0, 0), window=guide_container, anchor=NW)

        def _configure_canvas(event):
            canvas.itemconfig(window_id, width=event.width)
        canvas.bind('<Configure>', _configure_canvas)

        def _on_mousewheel(event):
            if canvas.winfo_exists() and canvas.winfo_ismapped():
                try:
                    canvas.yview_scroll(int(-3*(event.delta/120)), "units")
                except tk.TclError:
                    pass
        canvas.bind("<MouseWheel>", _on_mousewheel)
        guide_container.bind("<MouseWheel>", _on_mousewheel)

        # Header
        ttk.Label(guide_container, text="User Guide",
                  font=('Segoe UI', 14, 'bold')).pack(anchor=W, pady=(0, 5))
        ttk.Label(guide_container, text="Everything you need to know about CrossTrans",
                  font=('Segoe UI', 9), foreground='#888888').pack(anchor=W, pady=(0, 15))

        # Dynamic values
        lang_count = len(LANGUAGES)
        trial_limit = get_config().trial_daily_limit

        # === Section 1: Getting Started ===
        self._create_guide_section(guide_container, "Getting Started", [
            f"CrossTrans translates text instantly using AI \u2014 {lang_count} languages supported.",
            "",
            "Try it now (no setup needed):",
            f"  \u2022 {trial_limit} free translations/day without an API key",
            "  \u2022 Just select text and press a hotkey",
            "",
            "How to translate:",
            "1. Select any text in any application (browser, Word, PDF, etc.)",
            "2. Press a hotkey (e.g., Win+Alt+V for Vietnamese)",
            "3. Translation appears in a popup near your cursor",
            "4. Use the popup buttons: Copy, Replace, Dictionary, or Open Translator",
            "",
            "Want unlimited translations? Get a free API key (see AI Providers below).",
        ])

        # === Section 2: Hotkeys ===
        self._create_guide_section(guide_container, "Hotkeys", [
            "Hotkeys activate Quick Translate \u2014 select text, press a hotkey, and the translation popup appears instantly.",
            "",
            "Default Translation Hotkeys:",
            "  \u2022 Win + Alt + V  \u2192  Translate to Vietnamese",
            "  \u2022 Win + Alt + E  \u2192  Translate to English",
            "  \u2022 Win + Alt + J  \u2192  Translate to Japanese",
            "  \u2022 Win + Alt + C  \u2192  Translate to Chinese (Simplified)",
            "",
            "Screenshot:",
            "  \u2022 Win + Alt + S  \u2192  Capture screen region for OCR translation",
            "",
            "Custom Hotkeys:",
            "  \u2022 Add up to 4 additional language hotkeys",
            f"  \u2022 Choose from {lang_count} languages with any key combination",
            "  \u2022 All hotkeys are fully customizable in Settings \u2192 Hotkeys",
        ])

        # === Section 3: Quick Translate ===
        self._create_guide_section(guide_container, "Quick Translate", [
            "When a translation appears, the popup provides these controls:",
            "",
            "Button Bar:",
            "  \u2022 Copy               \u2192  Copy translation to clipboard",
            "  \u2022 Replace            \u2192  Paste translation into source app",
            "  \u2022 \u2699 (gear icon)      \u2192  Quick access to Replace mode settings",
            "  \u2022 Dictionary         \u2192  Look up individual words interactively",
            "  \u2022 Open Translator    \u2192  Open full translator window with text",
            "  \u2022 \u2715 (close)          \u2192  Close the popup",
            "",
            "Other actions:",
            "  \u2022 Press Escape to close the popup",
            "  \u2022 Popup stays on top and doesn't steal focus from your app",
        ])
        self._add_guide_image(guide_container, "quick_translate.png",
                              "Quick Translate with Copy, Replace, Dictionary, Open Translator buttons")

        # === Section 4: Replace Mode ===
        self._create_guide_section(guide_container, "Replace Mode", [
            "Replace selected text in the source app with the translation.",
            "",
            "Two modes (toggle in Settings \u2192 Hotkeys \u2192 Replace Mode):",
            "",
            "Manual Replace (default):",
            "  1. Click 'Replace' in the popup",
            "  2. Preview shows: original (strikethrough) \u2192 translated text",
            "  3. Click 'Agree' to replace, or 'Cancel' to keep original",
            "",
            "Quick Replace:",
            "  \u2022 Click 'Replace' \u2192 immediately pastes translation",
            "  \u2022 No preview step \u2014 faster workflow",
            "",
            "How it works:",
            "  \u2022 Translation is copied to clipboard, then Ctrl+V is simulated",
            "  \u2022 Source app keeps focus (popup doesn't steal focus)",
            "  \u2022 Toggle mode via the \u2699 gear icon or Settings \u2192 Hotkeys",
        ])
        self._add_guide_image(guide_container, "replace_preview_translated.png",
                              "Translation preview")
        self._add_guide_image(guide_container, "replace_preview_replaced.png",
                              "Replace preview with Agree/Cancel")

        # === Section 5: Screenshot Translation ===
        self._create_guide_section(guide_container, "Screenshot Translation", [
            "Capture any screen region for instant OCR and translation:",
            "",
            "How to use:",
            "1. Press Win + Alt + S",
            "2. Screen dims with a selection overlay",
            "3. Click and drag to select a region",
            "4. Release to capture and translate",
            "",
            "Features:",
            "  \u2022 Multi-monitor support",
            "  \u2022 Configurable target language in Settings \u2192 Hotkeys",
            "  \u2022 'Open Translator' loads screenshot into Attachments",
            "",
            "Requirements:",
            "  \u2022 Vision-capable API (e.g., Gemini, GPT-4o, Claude 3)",
            "  \u2022 Test your API in Settings \u2192 API Key to check capability",
        ])
        self._add_guide_image(guide_container, "screenshot_ocr_when_drag.png",
                              "Drag to select screen region")
        self._add_guide_image(guide_container, "screenshot_ocr_result.png",
                              "OCR translation result")

        # === Section 6: Dictionary Mode ===
        self._create_guide_section(guide_container, "Dictionary Mode", [
            "Look up words interactively with detailed definitions.",
            "",
            "How to use:",
            "  1. After translating, click 'Dictionary' in the popup",
            "  2. Words appear as clickable buttons",
            "  3. Click words to select, then click 'Dictionary Lookup'",
            "",
            "Word Selection:",
            "  \u2022 Click on any word to select/deselect",
            "  \u2022 Drag across words to select a range",
            "  \u2022 Shift+Click to extend selection",
            "  \u2022 Hyphenated words stay together (e.g., 'state-of-the-art')",
            "",
            "Lookup Results (8 fields):",
            "  \u2022 Translation, Definition, Word Type",
            "  \u2022 Pronunciation (IPA)",
            "  \u2022 Synonyms with translations",
            "  \u2022 Antonyms with translations",
            "  \u2022 Example sentences with translations",
            "",
            "Language Packs:",
            "  \u2022 Install NLP packs for better word tokenization",
            "  \u2022 Supports Japanese, Chinese, Korean, and 30+ languages",
            "  \u2022 Manage in Settings \u2192 Dictionary tab",
        ])
        self._add_guide_image(guide_container, "dictionary_mode_selected.png",
                              "Word selection buttons")
        self._add_guide_image(guide_container, "dictionary_mode_look_up.png",
                              "Dictionary lookup result")

        # === Section 7: File Translation ===
        self._create_guide_section(guide_container, "File Translation", [
            "Translate entire documents with a single click:",
            "",
            "Supported formats:",
            "  \u2022 .txt   \u2014 Plain text files",
            "  \u2022 .docx  \u2014 Microsoft Word documents",
            "  \u2022 .srt   \u2014 Subtitle files (timestamps preserved)",
            "  \u2022 .pdf   \u2014 PDF documents (text-based and scanned)",
            "",
            "How to use:",
            "1. Right-click tray icon \u2192 'Open Translator'",
            "2. Click the '+' button or drag & drop files",
            "3. Select target language",
            "4. Click 'Translate'",
            "",
            "Tips:",
            "  \u2022 Add multiple files at once for batch translation",
            "  \u2022 Images (PNG, JPG, WebP, GIF) are supported via OCR",
            "  \u2022 Double-click any attachment to preview with default app",
        ])
        self._add_guide_image(guide_container, "translator_window.png",
                              "Full Translator window")

        # === Section 8: AI Providers ===
        try:
            provider_count = len(get_config().providers_list) - 1  # Exclude "Auto"
        except Exception:
            provider_count = 15
        self._create_guide_section(guide_container, "AI Providers", [
            f"{provider_count} providers with 180+ models:",
            "",
            "  \u2022 Google Gemini, OpenAI, Anthropic, DeepSeek",
            "  \u2022 Groq, xAI, Mistral, Perplexity",
            "  \u2022 Cerebras, SambaNova, Together, SiliconFlow",
            "  \u2022 OpenRouter (400+ aggregated models), HuggingFace",
            "",
            "Many providers offer free API keys. Visit their website to sign up.",
            "",
            "Setup:",
            "  1. Sign up on a provider's website and create an API key",
            "  2. Open Settings \u2192 API Key \u2192 paste your key",
            "  3. Click 'Test' to verify the connection",
            "",
            "Smart Features:",
            "  \u2022 Auto-detects provider from API key format",
            "  \u2022 Add multiple API keys for automatic failover",
            "  \u2022 Provider and model lists update automatically",
        ])
        self._add_guide_image(guide_container, "settings_api.png",
                              "API Key settings with test result")

        # === Section 9: Tips & Tricks ===
        self._create_guide_section(guide_container, "Tips & Tricks", [
            "System Features:",
            "  \u2022 System tray icon for quick access (right-click for menu)",
            "  \u2022 Start with Windows (Settings \u2192 General)",
            "  \u2022 Auto-update notifications (Settings \u2192 General)",
            "",
            "Translation History:",
            "  \u2022 Click the clock icon to view past translations",
            "  \u2022 Search through history with keywords",
            "  \u2022 Last 100 translations are saved",
            "",
            "Full Translator Window:",
            "  \u2022 Open via popup 'Open Translator' or system tray menu",
            "  \u2022 Add custom prompts (e.g., 'formal tone', 'technical terms')",
            "  \u2022 Attach files and images for translation",
            f"  \u2022 Choose from {lang_count} target languages",
            "",
            "Trial Mode:",
            f"  \u2022 {trial_limit} free translations/day without API key",
            "  \u2022 Quota resets at midnight",
            "  \u2022 Get your own API key for unlimited translations",
            "",
            "Security:",
            "  \u2022 API keys are encrypted with Windows DPAPI",
            "  \u2022 Optional Windows Hello protection for API key access",
        ])
        self._add_guide_image(guide_container, "translator_window_expand.png",
                              "Expanded translator view")

        # === Section 10: Troubleshooting ===
        self._create_guide_section(guide_container, "Troubleshooting", [
            "Hotkey not working?",
            "  \u2022 Check if another app uses the same hotkey",
            "  \u2022 Try running CrossTrans as Administrator",
            "  \u2022 Reconfigure in Settings \u2192 Hotkeys",
            "",
            "API Error / Connection Failed?",
            "  \u2022 Verify your API key is correct",
            "  \u2022 Click 'Test' to check the connection",
            "  \u2022 Check internet access and API quota",
            "",
            "Translation not appearing?",
            "  \u2022 Make sure text is selected before pressing hotkey",
            "  \u2022 Try copying text manually (Ctrl+C) first",
            "  \u2022 Some applications block clipboard access",
            "",
            "Replace not working?",
            "  \u2022 The source app must keep the text selected",
            "  \u2022 Some apps block simulated Ctrl+V \u2014 try manual paste",
            "  \u2022 Translation is always on clipboard as a fallback",
            "",
            "App won't start?",
            "  \u2022 Only one instance can run at a time (check system tray)",
            "  \u2022 If crashed, close via Task Manager, then restart",
        ])

        # Footer
        ttk.Separator(guide_container).pack(fill=X, pady=20)
        footer_frame = ttk.Frame(guide_container)
        footer_frame.pack(fill=X)

        ttk.Label(footer_frame, text="Need more help?",
                  font=('Segoe UI', 9, 'bold')).pack(anchor=W)

        links_frame = ttk.Frame(footer_frame)
        links_frame.pack(anchor=W, pady=5)

        if HAS_TTKBOOTSTRAP:
            ttk.Button(links_frame, text="View on GitHub",
                       command=lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}"),
                       bootstyle="link").pack(side=LEFT)
            ttk.Label(links_frame, text="  |  ").pack(side=LEFT)
            ttk.Button(links_frame, text="Report an Issue",
                       command=lambda: webbrowser.open(FEEDBACK_URL),
                       bootstyle="link").pack(side=LEFT)
        else:
            ttk.Button(links_frame, text="View on GitHub",
                       command=lambda: webbrowser.open(f"https://github.com/{GITHUB_REPO}")).pack(side=LEFT)
            ttk.Label(links_frame, text="  |  ").pack(side=LEFT)
            ttk.Button(links_frame, text="Report an Issue",
                       command=lambda: webbrowser.open(FEEDBACK_URL)).pack(side=LEFT)

        # Update scroll region
        def update_scroll():
            guide_container.update_idletasks()
            canvas.config(scrollregion=canvas.bbox("all"))
        self.window.after(100, update_scroll)

    def _create_guide_section(self, parent, title, content_lines):
        """Create a section in the guide with icon prefix."""
        ttk.Separator(parent).pack(fill=X, pady=10)
        icon = SECTION_ICONS.get(title, "")
        display_title = f"{icon}  {title}" if icon else title
        ttk.Label(parent, text=display_title,
                  font=('Segoe UI', 11, 'bold')).pack(anchor=W, pady=(5, 10))
        self._create_guide_content(parent, content_lines)

    def _create_guide_content(self, parent, content_lines):
        """Create content lines for a guide section."""
        for line in content_lines:
            if line == "":
                # Empty line for spacing
                ttk.Label(parent, text="").pack(anchor=W)
            elif line.startswith("  \u2022"):
                # Bullet point with indent
                ttk.Label(parent, text=line, font=('Segoe UI', 9),
                         foreground='#cccccc').pack(anchor=W, padx=(20, 0))
            elif line.startswith("[") and line.endswith("]"):
                # Placeholder text (italic, gray)
                ttk.Label(parent, text=line, font=('Segoe UI', 9, 'italic'),
                         foreground='#666666').pack(anchor=W, padx=20, pady=5)
            else:
                # Normal text
                ttk.Label(parent, text=line, font=('Segoe UI', 9),
                         foreground='#aaaaaa').pack(anchor=W, padx=20)
