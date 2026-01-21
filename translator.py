import pyperclip
import google.generativeai as genai
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import os
import sys
import queue
import socket
from pynput import keyboard
from pynput.keyboard import Controller as KeyboardController, GlobalHotKeys
from pystray import Icon, MenuItem, Menu
from PIL import Image, ImageDraw
import webbrowser

# ============== SINGLE INSTANCE LOCK ==============
LOCK_PORT = 47823  # Unique port for this app

def is_already_running():
    """Check if another instance is already running using socket lock."""
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.bind(('127.0.0.1', LOCK_PORT))
        lock_socket.listen(1)
        # Keep socket open to maintain lock
        return False, lock_socket
    except socket.error:
        return True, None

# ============== CONFIGURATION ==============
# Get the directory where the exe/script is located
def get_app_dir():
    if getattr(sys, 'frozen', False):
        # Running as compiled exe
        return os.path.dirname(sys.executable)
    else:
        # Running as script
        return os.path.dirname(os.path.abspath(__file__))

# Load API key from environment variable or .env file
def load_api_key():
    # First, try environment variable
    api_key = os.environ.get('GEMINI_API_KEY')
    if api_key:
        return api_key

    # Then, try .env file in the same directory as exe/script
    env_path = os.path.join(get_app_dir(), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('GEMINI_API_KEY='):
                    return line.split('=', 1)[1].strip().strip('"\'')

    return None

GEMINI_API_KEY = load_api_key()

if not GEMINI_API_KEY:
    # Show error using GUI (works with --windowed exe)
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Gemini Translator - API Key Missing",
        "GEMINI_API_KEY not found!\n\n"
        "Please create a .env file in the same folder as this app with:\n"
        "GEMINI_API_KEY=your_api_key\n\n"
        "Get your free API key at:\n"
        "https://aistudio.google.com/app/apikey"
    )
    root.destroy()
    sys.exit(1)

# Available languages
LANGUAGES = [
    ("Vietnamese", "vi", "Tiếng Việt"),
    ("English", "en", "Anh"),
    ("Japanese", "ja", "日本語 Nihongo"),
    ("Chinese Simplified", "zh-CN", "中文简体 Trung Quốc"),
    ("Chinese Traditional", "zh-TW", "中文繁體 Đài Loan"),
    ("Korean", "ko", "한국어 Hàn Quốc"),
    ("French", "fr", "Français Pháp"),
    ("German", "de", "Deutsch Đức"),
    ("Spanish", "es", "Español Tây Ban Nha"),
    ("Italian", "it", "Italiano Ý"),
    ("Portuguese", "pt", "Português Bồ Đào Nha"),
    ("Russian", "ru", "Русский Nga"),
    ("Thai", "th", "ไทย Thái"),
    ("Indonesian", "id", "Bahasa Indonesia"),
    ("Malay", "ms", "Bahasa Melayu Mã Lai"),
    ("Hindi", "hi", "हिन्दी Ấn Độ"),
    ("Arabic", "ar", "العربية Ả Rập"),
    ("Dutch", "nl", "Nederlands Hà Lan"),
    ("Polish", "pl", "Polski Ba Lan"),
    ("Turkish", "tr", "Türkçe Thổ Nhĩ Kỳ"),
    ("Swedish", "sv", "Svenska Thụy Điển"),
    ("Danish", "da", "Dansk Đan Mạch"),
    ("Norwegian", "no", "Norsk Na Uy"),
    ("Finnish", "fi", "Suomi Phần Lan"),
    ("Greek", "el", "Ελληνικά Hy Lạp"),
    ("Czech", "cs", "Čeština Séc"),
    ("Romanian", "ro", "Română Rumani"),
    ("Hungarian", "hu", "Magyar Hungary"),
    ("Ukrainian", "uk", "Українська Ukraina"),
]

# Hotkey configuration (Win+Alt+V/E/J)
COOLDOWN = 2.0

# ============== SETUP GEMINI ==============
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash-lite')

# ============== GLOBAL STATE ==============
last_translation_time = 0
translation_queue = queue.Queue()
keyboard_controller = KeyboardController()

# ============== TRANSLATION FUNCTION ==============
def translate_text(text, target_language):
    prompt = f"""Translate the following text to {target_language}. 
Only return the translation, no explanations or additional text.
If the text is already in {target_language}, still provide a natural rephrasing.

Text to translate:
{text}"""
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Error: {str(e)}"

# ============== CLIPBOARD ==============
def get_selected_text():
    old_clipboard = ""
    try:
        old_clipboard = pyperclip.paste()
    except Exception as e:
        print(f"[DEBUG] Failed to get old clipboard: {e}")
    
    # Try multiple times with different delays
    for attempt in range(3):
        try:
            # Clear clipboard first
            pyperclip.copy("")
            time.sleep(0.05)
            
            # Simulate Ctrl+C
            keyboard_controller.press(keyboard.Key.ctrl)
            time.sleep(0.05)
            keyboard_controller.press('c')
            time.sleep(0.05)
            keyboard_controller.release('c')
            time.sleep(0.05)
            keyboard_controller.release(keyboard.Key.ctrl)
            
            # Wait for clipboard to update
            time.sleep(0.2 + (attempt * 0.1))
            
            new_clipboard = pyperclip.paste()
            print(f"[DEBUG] Attempt {attempt + 1}: clipboard = '{new_clipboard[:50] if new_clipboard else 'EMPTY'}...'")
            
            if new_clipboard and new_clipboard.strip():
                return new_clipboard
                
        except Exception as e:
            print(f"[DEBUG] Attempt {attempt + 1} failed: {e}")
    
    # Restore old clipboard if nothing was copied
    if old_clipboard:
        try:
            pyperclip.copy(old_clipboard)
        except:
            pass
    
    return None

def do_translation(target_language):
    global last_translation_time
    
    current_time = time.time()
    if current_time - last_translation_time < COOLDOWN:
        print(f"[{time.strftime('%H:%M:%S')}] Cooldown active, please wait...")
        return
    
    last_translation_time = current_time
    print(f"[{time.strftime('%H:%M:%S')}] Translating to {target_language}...")
    
    try:
        selected_text = get_selected_text()
        
        if selected_text:
            print(f"[{time.strftime('%H:%M:%S')}] Selected text: {selected_text[:50]}...")
            translated = translate_text(selected_text, target_language)
            print(f"[{time.strftime('%H:%M:%S')}] Translation complete!")
            translation_queue.put((selected_text, translated, target_language))
        else:
            print(f"[{time.strftime('%H:%M:%S')}] No text selected!")
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Error: {e}")

# ============== SYSTEM TRAY ==============
def create_tray_icon(quit_callback):
    image = Image.new('RGB', (64, 64), color='#0078d4')
    draw = ImageDraw.Draw(image)
    draw.text((20, 20), "GT", fill='white')

    menu = Menu(
        MenuItem('Gemini Translator v1.1.0', lambda: None, enabled=False),
        MenuItem('─────────────', lambda: None, enabled=False),
        MenuItem('Win+Alt+V → Vietnamese', lambda: None, enabled=False),
        MenuItem('Win+Alt+E → English', lambda: None, enabled=False),
        MenuItem('Win+Alt+J → Japanese', lambda: None, enabled=False),
        MenuItem('─────────────', lambda: None, enabled=False),
        MenuItem('Quit', quit_callback)
    )

    icon = Icon("Gemini Translator", image, "Gemini Translator v1.1.0", menu)
    return icon

# ============== MAIN APP ==============
class TranslatorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.popup = None
        self.tooltip = None
        self.tray_icon = None
        self.running = True
        self.selected_language = "Vietnamese"
        self.filtered_languages = LANGUAGES.copy()
        # Store current translation data for tooltip -> full window
        self.current_original = ""
        self.current_translated = ""
        self.current_target_lang = ""

    def show_tooltip(self, original, translated, target_lang):
        """Show a compact tooltip near the mouse cursor with translation result."""
        # Store data for potential full window opening
        self.current_original = original
        self.current_translated = translated
        self.current_target_lang = target_lang

        # Close existing tooltip
        if self.tooltip:
            try:
                self.tooltip.destroy()
            except:
                pass

        # Create tooltip window
        self.tooltip = tk.Toplevel(self.root)
        self.tooltip.overrideredirect(True)  # No title bar
        self.tooltip.attributes('-topmost', True)
        self.tooltip.configure(bg='#2d2d2d')

        # Main frame with border effect
        main_frame = tk.Frame(self.tooltip, bg='#2d2d2d', padx=12, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Add subtle border
        self.tooltip.configure(highlightbackground='#555555', highlightthickness=1)

        # Translation text - auto-wrap at ~400px
        self.tooltip_text = tk.Text(main_frame, wrap=tk.WORD, bg='#2d2d2d', fg='#ffffff',
                                    font=('Segoe UI', 11), relief='flat', padx=4, pady=4,
                                    width=50, height=1, borderwidth=0)
        self.tooltip_text.insert('1.0', translated)
        self.tooltip_text.config(state='disabled')

        # Auto-adjust height based on content
        line_count = int(self.tooltip_text.index('end-1c').split('.')[0])
        # Estimate lines needed for wrapping (rough calculation)
        char_count = len(translated)
        estimated_lines = max(line_count, (char_count // 45) + 1)
        display_lines = min(estimated_lines, 10)  # Max 10 lines
        self.tooltip_text.config(height=display_lines)
        self.tooltip_text.pack(fill=tk.BOTH, expand=True)

        # Button frame
        btn_frame = tk.Frame(main_frame, bg='#2d2d2d')
        btn_frame.pack(fill=tk.X, pady=(8, 0))

        # Copy button
        self.tooltip_copy_btn = tk.Button(btn_frame, text="Copy", command=self.copy_from_tooltip,
                                          bg='#0078d4', fg='white', font=('Segoe UI', 9),
                                          relief='flat', padx=12, pady=3, cursor='hand2')
        self.tooltip_copy_btn.pack(side=tk.LEFT)

        # Open Translator button
        open_btn = tk.Button(btn_frame, text="Open Translator", command=self.open_full_translator,
                             bg='#107c10', fg='white', font=('Segoe UI', 9),
                             relief='flat', padx=12, pady=3, cursor='hand2')
        open_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Close button
        close_btn = tk.Button(btn_frame, text="✕", command=self.close_tooltip,
                              bg='#3d3d3d', fg='white', font=('Segoe UI', 9, 'bold'),
                              relief='flat', padx=8, pady=3, cursor='hand2')
        close_btn.pack(side=tk.RIGHT)

        # Position near mouse cursor
        mouse_x = self.root.winfo_pointerx()
        mouse_y = self.root.winfo_pointery()

        # Update to get actual size
        self.tooltip.update_idletasks()
        tooltip_width = self.tooltip.winfo_reqwidth()
        tooltip_height = self.tooltip.winfo_reqheight()

        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # Position tooltip below and to the right of cursor
        x = mouse_x + 10
        y = mouse_y + 15

        # Adjust if tooltip would go off screen
        if x + tooltip_width > screen_width:
            x = mouse_x - tooltip_width - 10
        if y + tooltip_height > screen_height:
            y = mouse_y - tooltip_height - 15

        self.tooltip.geometry(f"+{x}+{y}")

        # Bind Escape to close
        self.tooltip.bind('<Escape>', lambda e: self.close_tooltip())

        # Bind click outside to close (using focus out)
        self.tooltip.bind('<FocusOut>', self.on_tooltip_focus_out)

        # Force focus
        self.tooltip.focus_force()

    def on_tooltip_focus_out(self, event):
        """Close tooltip when clicking outside."""
        # Small delay to allow button clicks to register
        if self.tooltip:
            self.tooltip.after(100, self.check_tooltip_focus)

    def check_tooltip_focus(self):
        """Check if tooltip should be closed."""
        if self.tooltip:
            try:
                # If focus is not on tooltip or its children, close it
                focused = self.root.focus_get()
                if focused is None or not str(focused).startswith(str(self.tooltip)):
                    self.close_tooltip()
            except:
                pass

    def close_tooltip(self):
        """Close the tooltip."""
        if self.tooltip:
            try:
                self.tooltip.destroy()
            except:
                pass
            self.tooltip = None

    def copy_from_tooltip(self):
        """Copy translation from tooltip to clipboard."""
        pyperclip.copy(self.current_translated)
        self.tooltip_copy_btn.config(text="Copied!")
        if self.tooltip:
            self.tooltip.after(1000, lambda: self.tooltip_copy_btn.config(text="Copy") if self.tooltip else None)

    def open_full_translator(self):
        """Close tooltip and open full translator window."""
        self.close_tooltip()
        self.show_popup(self.current_original, self.current_translated, self.current_target_lang)

    def show_popup(self, original, translated, target_lang):
        if self.popup:
            try:
                self.popup.destroy()
            except:
                pass
        
        self.popup = tk.Toplevel(self.root)
        self.popup.title(f"Gemini Translator")
        self.popup.attributes('-topmost', True)
        self.popup.configure(bg='#1e1e1e')
        
        screen_width = self.popup.winfo_screenwidth()
        screen_height = self.popup.winfo_screenheight()
        window_width = 1000
        window_height = 800
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.popup.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        main_frame = tk.Frame(self.popup, bg='#1e1e1e', padx=15, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
# ===== ORIGINAL TEXT =====
        tk.Label(main_frame, text="Original:", bg='#1e1e1e', fg='#888888', 
                 font=('Segoe UI', 10)).pack(anchor='w')
        
        original_frame = tk.Frame(main_frame, bg='#2d2d2d')
        original_frame.pack(fill=tk.X, pady=(2, 10))
        
        original_scroll = tk.Scrollbar(original_frame)
        original_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.original_text = tk.Text(original_frame, height=6, wrap=tk.WORD, 
                                bg='#2d2d2d', fg='#cccccc', 
                                font=('Segoe UI', 11), relief='flat',
                                padx=8, pady=8, yscrollcommand=original_scroll.set)
        self.original_text.insert('1.0', original)
        self.original_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        original_scroll.config(command=self.original_text.yview)
        
        # ===== LANGUAGE SELECTOR =====
        lang_frame = tk.Frame(main_frame, bg='#1e1e1e')
        lang_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(lang_frame, text="Translate to:", bg='#1e1e1e', fg='#888888', 
                 font=('Segoe UI', 10)).pack(anchor='w')
        
        # Language listbox with scrollbar (create BEFORE search_var trace)
        list_frame = tk.Frame(lang_frame, bg='#2d2d2d')
        list_frame.pack(fill=tk.X, pady=(0, 5))

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.lang_listbox = tk.Listbox(list_frame, height=2, bg='#2d2d2d', fg='#ffffff',
                                       font=('Segoe UI', 11), relief='flat',
                                       selectbackground='#0078d4', selectforeground='white',
                                       yscrollcommand=scrollbar.set, activestyle='none')
        self.lang_listbox.pack(fill=tk.X, padx=2, pady=2)
        scrollbar.config(command=self.lang_listbox.yview)

        self.populate_language_list()
        self.lang_listbox.bind('<<ListboxSelect>>', self.on_language_select)

        # Search box (create AFTER listbox so trace doesn't fail)
        search_frame = tk.Frame(lang_frame, bg='#1e1e1e')
        search_frame.pack(fill=tk.X, pady=(2, 5), before=list_frame)

        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self.filter_languages)

        self.search_entry = tk.Entry(search_frame, textvariable=self.search_var,
                                     bg='#2d2d2d', fg='#ffffff',
                                     font=('Segoe UI', 11), relief='flat',
                                     insertbackground='white')
        self.search_entry.pack(fill=tk.X, ipady=5, padx=2)
        self.search_entry.insert(0, "Search language...")
        self.search_entry.bind('<FocusIn>', self.on_search_focus_in)
        self.search_entry.bind('<FocusOut>', self.on_search_focus_out)
        
        # Select current language
        self.select_language_in_list(target_lang)
        
        # ===== TRANSLATION OUTPUT =====
        tk.Label(main_frame, text="Translation:", bg='#1e1e1e', fg='#888888', 
                 font=('Segoe UI', 10)).pack(anchor='w')
        
        self.trans_text = tk.Text(main_frame, height=10, wrap=tk.WORD,
                            bg='#2d2d2d', fg='#ffffff',
                            font=('Segoe UI', 12), relief='flat',
                            padx=8, pady=8)
        self.trans_text.insert('1.0', translated)
        self.trans_text.pack(fill=tk.BOTH, expand=True, pady=(2, 10))
        
        # ===== BUTTONS =====
        btn_frame = tk.Frame(main_frame, bg='#1e1e1e')
        btn_frame.pack(fill=tk.X)
        
        # Translate button
        self.translate_btn = tk.Button(btn_frame, text=f"Translate → {self.selected_language}", 
                            command=self.do_retranslate,
                            bg='#107c10', fg='white', font=('Segoe UI', 10, 'bold'),
                            relief='flat', padx=15, pady=5, cursor='hand2')
        self.translate_btn.pack(side=tk.LEFT)
        
        # Copy button
        self.copy_btn = tk.Button(btn_frame, text="Copy", command=self.copy_translation,
                            bg='#0078d4', fg='white', font=('Segoe UI', 10),
                            relief='flat', padx=20, pady=5, cursor='hand2')
        self.copy_btn.pack(side=tk.LEFT, padx=(10, 0))

        # Open Gemini button
        self.gemini_btn = tk.Button(btn_frame, text="Open Gemini", command=self.open_in_gemini,
                            bg='#5e17eb', fg='white', font=('Segoe UI', 10),
                            relief='flat', padx=20, pady=5, cursor='hand2')
        self.gemini_btn.pack(side=tk.LEFT, padx=(10, 0))

        # Close button
        close_btn = tk.Button(btn_frame, text="Close", command=self.popup.destroy,
                             bg='#3d3d3d', fg='white', font=('Segoe UI', 10),
                             relief='flat', padx=20, pady=5, cursor='hand2')
        close_btn.pack(side=tk.RIGHT)
        
        self.popup.bind('<Escape>', lambda e: self.popup.destroy())
        self.popup.focus_force()
    
    def populate_language_list(self):
        if not hasattr(self, 'lang_listbox') or not self.lang_listbox.winfo_exists():
            return
        self.lang_listbox.delete(0, tk.END)
        for lang_name, lang_code, lang_aliases in self.filtered_languages:
            self.lang_listbox.insert(tk.END, f"{lang_name} ({lang_code})")
    
    def filter_languages(self, *args):
        if not hasattr(self, 'lang_listbox') or not self.lang_listbox.winfo_exists():
            return

        search_term = self.search_var.get().lower()

        if search_term == "" or search_term == "search language...":
            self.filtered_languages = LANGUAGES.copy()
        else:
            self.filtered_languages = []
            for lang_name, lang_code, lang_aliases in LANGUAGES:
                searchable = f"{lang_name} {lang_code} {lang_aliases}".lower()
                if search_term in searchable:
                    self.filtered_languages.append((lang_name, lang_code, lang_aliases))

        self.populate_language_list()

        if self.filtered_languages:
            self.lang_listbox.selection_set(0)
            self.selected_language = self.filtered_languages[0][0]
            self.update_translate_button()
    
    def on_search_focus_in(self, event):
        if self.search_entry.get() == "Search language...":
            self.search_entry.delete(0, tk.END)
            self.search_entry.config(fg='#ffffff')
    
    def on_search_focus_out(self, event):
        if self.search_entry.get() == "":
            self.search_entry.insert(0, "Search language...")
            self.search_entry.config(fg='#888888')
    
    def on_language_select(self, event):
        selection = self.lang_listbox.curselection()
        if selection:
            index = selection[0]
            if index < len(self.filtered_languages):
                self.selected_language = self.filtered_languages[index][0]
                self.update_translate_button()
    
    def select_language_in_list(self, lang_name):
        if not hasattr(self, 'lang_listbox') or not self.lang_listbox.winfo_exists():
            return
        for i, (name, code, aliases) in enumerate(self.filtered_languages):
            if name == lang_name:
                self.lang_listbox.selection_clear(0, tk.END)
                self.lang_listbox.selection_set(i)
                self.lang_listbox.see(i)
                self.selected_language = name
                break
        self.update_translate_button()
    
    def update_translate_button(self):
        if hasattr(self, 'translate_btn') and self.translate_btn.winfo_exists():
            self.translate_btn.config(text=f"Translate → {self.selected_language}")
    
    def do_retranslate(self):
        original = self.original_text.get('1.0', tk.END).strip()
        if not original:
            return
        
        self.translate_btn.config(text="Translating...", state='disabled')
        self.popup.update()
        
        def translate_thread():
            translated = translate_text(original, self.selected_language)
            self.popup.after(0, lambda: self.update_translation(translated))
        
        threading.Thread(target=translate_thread, daemon=True).start()
    
    def update_translation(self, translated):
        self.trans_text.config(state='normal')
        self.trans_text.delete('1.0', tk.END)
        self.trans_text.insert('1.0', translated)
        self.translate_btn.config(text=f"Translate → {self.selected_language}", state='normal')
    
    def copy_translation(self):
        translated = self.trans_text.get('1.0', tk.END).strip()
        pyperclip.copy(translated)
        self.copy_btn.config(text="Copied!")
        self.popup.after(1000, lambda: self.copy_btn.config(text="Copy"))

    def open_in_gemini(self):
        original = self.original_text.get('1.0', tk.END).strip()
        if not original:
            return

        # Create translation prompt
        prompt = f"Translate the following text to {self.selected_language}:\n\n{original}"

        # Copy prompt to clipboard
        pyperclip.copy(prompt)

        # Update button to show feedback
        self.gemini_btn.config(text="Copied! Opening...")

        # Open Gemini
        webbrowser.open("https://gemini.google.com/app")

        # Reset button text after delay
        self.popup.after(2000, lambda: self.gemini_btn.config(text="Open Gemini"))
    
    def check_queue(self):
        try:
            while True:
                original, translated, target_lang = translation_queue.get_nowait()
                self.show_tooltip(original, translated, target_lang)
        except queue.Empty:
            pass

        if self.running:
            self.root.after(100, self.check_queue)
    
    def quit_app(self, icon=None, item=None):
        self.running = False
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.quit()
        os._exit(0)
    
    def run(self):
        print("=" * 50)
        print("Gemini Translator v1.1.0")
        print("=" * 50)
        print("")
        print("Hotkeys:")
        print("  Win+Alt+V → Vietnamese")
        print("  Win+Alt+E → English")
        print("  Win+Alt+J → Japanese")
        print("")
        print("Select any text, then press a hotkey to translate!")
        print("")
        print("Listening...")
        print("-" * 50)

        # Setup global hotkeys (Win+Alt+V/E/J)
        hotkeys = GlobalHotKeys({
            '<cmd>+<alt>+v': lambda: threading.Thread(target=lambda: do_translation("Vietnamese"), daemon=True).start(),
            '<cmd>+<alt>+e': lambda: threading.Thread(target=lambda: do_translation("English"), daemon=True).start(),
            '<cmd>+<alt>+j': lambda: threading.Thread(target=lambda: do_translation("Japanese"), daemon=True).start(),
        })
        hotkeys.start()
        
        self.tray_icon = create_tray_icon(self.quit_app)
        tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        tray_thread.start()
        
        self.root.after(100, self.check_queue)
        self.root.mainloop()

# ============== MAIN ==============
if __name__ == "__main__":
    already_running, lock_socket = is_already_running()

    if already_running:
        # Show message and exit
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning(
            "Gemini Translator",
            "Gemini Translator is already running!\n\nCheck the system tray (bottom-right corner)."
        )
        root.destroy()
        sys.exit(0)

    # Keep lock_socket alive during app lifetime
    app = TranslatorApp()
    app.run()
