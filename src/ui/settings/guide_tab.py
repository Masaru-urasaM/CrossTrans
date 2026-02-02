"""
User Guide tab functionality for Settings window.
"""
import webbrowser

import tkinter as tk
from tkinter import BOTH, X, LEFT, RIGHT, W, NW

try:
    import ttkbootstrap as ttk
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False

from src.constants import GITHUB_REPO, FEEDBACK_URL


class GuideTabMixin:
    """Mixin class providing User Guide tab functionality."""

    def _create_guide_tab(self, parent):
        """Create user guide tab with helpful instructions."""
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
                    canvas.yview_scroll(int(-1*(event.delta/120)), "units")
                except tk.TclError:
                    pass
        canvas.bind("<MouseWheel>", _on_mousewheel)
        guide_container.bind("<MouseWheel>", _on_mousewheel)

        # Header
        ttk.Label(guide_container, text="User Guide", font=('Segoe UI', 14, 'bold')).pack(anchor=W, pady=(0, 5))
        ttk.Label(guide_container, text="Everything you need to know about CrossTrans",
                  font=('Segoe UI', 9), foreground='#888888').pack(anchor=W, pady=(0, 15))

        # === Section 1: Quick Start ===
        self._create_guide_section(guide_container, "Quick Start", [
            "1. Select any text in any application (browser, Word, PDF viewer, etc.)",
            "2. Press a hotkey (e.g., Win+Alt+V for Vietnamese)",
            "3. Translation appears in a tooltip near your cursor",
            "4. Click 'Copy' to copy the translation, or press Escape to close",
        ])

        # === Section 2: How to Get Free API Key ===
        self._create_guide_section(guide_container, "How to Get a Free API Key", [
            "Google Gemini offers a generous free tier (1,500 requests/day):",
            "",
            "1. Go to Google AI Studio:",
        ])

        # Clickable link for Google AI Studio
        link_frame = ttk.Frame(guide_container)
        link_frame.pack(anchor=W, padx=20)
        if HAS_TTKBOOTSTRAP:
            link_btn = ttk.Button(link_frame, text="https://aistudio.google.com/app/apikey",
                                  command=lambda: webbrowser.open("https://aistudio.google.com/app/apikey"),
                                  bootstyle="link")
        else:
            link_btn = ttk.Button(link_frame, text="https://aistudio.google.com/app/apikey",
                                  command=lambda: webbrowser.open("https://aistudio.google.com/app/apikey"))
        link_btn.pack(anchor=W)

        self._create_guide_content(guide_container, [
            "",
            "2. Sign in with your Google account",
            "3. Click 'Create API Key' button",
            "4. Copy the generated key",
            "5. Open Settings > API Key tab > Paste in 'API Key' field",
            "6. Click 'Test' to verify the connection",
        ])

        # === Section 3: Default Hotkeys ===
        self._create_guide_section(guide_container, "Default Hotkeys", [
            "Translation Hotkeys:",
            "  • Win + Alt + V  →  Translate to Vietnamese",
            "  • Win + Alt + E  →  Translate to English",
            "  • Win + Alt + J  →  Translate to Japanese",
            "  • Win + Alt + C  →  Translate to Chinese (Simplified)",
            "",
            "Screenshot Translation:",
            "  • Win + Alt + S  →  Capture screen region for OCR",
            "",
            "You can customize hotkeys in the 'Hotkeys' tab.",
        ])

        # === Section 3.5: Screenshot Translation ===
        self._create_guide_section(guide_container, "Screenshot Translation", [
            "Capture any screen region for instant OCR and translation:",
            "",
            "How to use:",
            "1. Press Win + Alt + S",
            "2. Screen dims with selection overlay",
            "3. Click and drag to select region",
            "4. Release to capture and translate",
            "",
            "Features:",
            "  • Multi-monitor support",
            "  • Configurable target language in Hotkeys tab",
            "  • 'Open Translator' loads screenshot into Attachments",
            "",
            "Requirements:",
            "  • Vision-capable API (Gemini 2.0+, GPT-4o, Claude 3)",
            "  • Test API in Settings > API Key to check capability",
        ])

        self._create_guide_section(guide_container, "File Translation", [
            "Translate entire documents with a single click:",
            "",
            "Supported formats:",
            "  • .txt   - Plain text files",
            "  • .docx  - Microsoft Word documents",
            "  • .srt   - Subtitle files",
            "  • .pdf   - PDF documents (text-based and scanned)",
            "",
            "How to use:",
            "1. Right-click tray icon > 'Open Translator'",
            "2. Click the '+' button or drag & drop files",
            "3. Select target language",
            "4. Click 'Translate'",
            "",
            "Tips:",
            "  • You can add multiple files at once",
            "  • Images (PNG, JPG) are also supported for OCR",
            "  • Double-click any attachment to preview/open",
        ])

        self._create_guide_section(guide_container, "Dictionary Mode", [
            "Click the 'Dictionary' button to look up words interactively:",
            "",
            "Word Selection:",
            "  • Click on any word to select/deselect it",
            "  • Drag across multiple words to select a range",
            "  • Shift+Click to select from anchor to clicked word",
            "",
            "Dictionary Lookup:",
            "  • Select words and click 'Dictionary Lookup'",
            "  • Get translation, definition, word type, pronunciation",
            "  • Example sentences with translations",
            "",
            "Features:",
            "  • Words flow like a paragraph with line wrapping",
            "  • Hyphenated words stay together (auto-update, state-of-the-art)",
            "  • 'Expand' button for larger view",
            "  • Results appear in a separate window",
            "",
            "Language Packs:",
            "  • Install NLP packs for better tokenization",
            "  • Supports Japanese, Chinese, Vietnamese, and 30+ languages",
            "  • Settings > Dictionary tab to manage language packs",
        ])

        # === Section 6: Tips & Tricks ===
        self._create_guide_section(guide_container, "Tips & Tricks", [
            "Custom Prompts:",
            "  • Add instructions in the 'Custom prompt' field",
            "  • Examples: 'formal tone', 'casual', 'technical terms'",
            "",
            "Translation History:",
            "  • Click the clock icon to view past translations",
            "  • Search through history with keywords",
            "  • Copy any previous translation",
            "",
            "Multiple API Keys:",
            "  • Add backup keys for failover redundancy",
            "  • If primary API fails, backup is used automatically",
            "",
            "Trial Mode:",
            "  • 100 free translations/day without API key",
            "  • Quota resets at midnight",
            "  • Get your own API key for unlimited use",
        ])

        # === Section 7: Troubleshooting ===
        self._create_guide_section(guide_container, "Troubleshooting", [
            "Hotkey not working?",
            "  • Check if another app is using the same hotkey",
            "  • Try running CrossTrans as Administrator",
            "  • Reconfigure hotkeys in Settings > Hotkeys",
            "",
            "API Error / Connection Failed?",
            "  • Verify your API key is correct",
            "  • Click 'Test' to check the connection",
            "  • Make sure you have internet access",
            "  • Check if you've exceeded API quota",
            "",
            "Translation not appearing?",
            "  • Make sure text is selected before pressing hotkey",
            "  • Try copying text manually (Ctrl+C) first",
            "  • Some applications block clipboard access",
        ])

        # === Section 8: Supported Providers ===
        self._create_guide_section(guide_container, "Supported AI Providers", [
            "15 providers with 180+ models:",
            "",
            "Free Tier Available:",
            "  • Google Gemini - 1,500 req/day (Recommended)",
            "  • Groq - Fast inference, Llama 3.3",
            "  • Cerebras - High throughput",
            "  • DeepSeek - DeepSeek-R1, V3",
            "  • SambaNova - Llama 405B",
            "  • SiliconFlow - Qwen 2.5, DeepSeek-V3",
            "  • HuggingFace - Qwen 2.5, Llama 3.x",
            "",
            "Premium Providers:",
            "  • OpenAI (o3, GPT-4.1, GPT-4o)",
            "  • Anthropic (Claude 4.5, Claude 3.5)",
            "  • xAI (Grok 3)",
            "  • Mistral AI, Perplexity, Together, SiliconFlow",
            "  • OpenRouter (400+ aggregated models)",
            "",
            "Auto-detection:",
            "  • App detects provider from API key pattern",
            "  • Smart fallback tries multiple models automatically",
        ])

        # Footer
        ttk.Separator(guide_container).pack(fill=X, pady=20)
        footer_frame = ttk.Frame(guide_container)
        footer_frame.pack(fill=X)

        ttk.Label(footer_frame, text="Need more help?", font=('Segoe UI', 9, 'bold')).pack(anchor=W)

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
        """Create a collapsible section in the guide."""
        # Section header
        ttk.Separator(parent).pack(fill=X, pady=10)
        ttk.Label(parent, text=title, font=('Segoe UI', 11, 'bold')).pack(anchor=W, pady=(5, 10))

        # Content
        self._create_guide_content(parent, content_lines)

    def _create_guide_content(self, parent, content_lines):
        """Create content lines for a guide section."""
        for line in content_lines:
            if line == "":
                # Empty line for spacing
                ttk.Label(parent, text="").pack(anchor=W)
            elif line.startswith("  •"):
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
