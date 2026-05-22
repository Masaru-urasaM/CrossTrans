"""
Dictionary (NLP Language Packs) tab functionality for Settings window.
"""
import logging
import threading

import tkinter as tk
from tkinter import BOTH, X, LEFT, RIGHT, W

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.dialogs import Messagebox
    HAS_TTKBOOTSTRAP = True
except ImportError:
    from tkinter import ttk
    HAS_TTKBOOTSTRAP = False


class DictionaryTabMixin:
    """Mixin class providing Dictionary/NLP tab functionality."""

    def _create_dictionary_tab(self, parent):
        """Create Dictionary language packs management tab with collapsible design."""
        # Header first (always shows)
        ttk.Label(parent, text="Dictionary Language Packs",
                  font=('Segoe UI', 12, 'bold')).pack(anchor=W)

        ttk.Label(parent, text="Install language packs to enable smart word recognition in Dictionary mode.",
                  font=('Segoe UI', 9), foreground='#888888').pack(anchor=W, pady=(2, 10))

        try:
            self._create_dictionary_tab_content(parent)
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logging.error(f"Failed to create Dictionary tab content: {e}\n{error_details}")
            # Show error message with details
            error_frame = ttk.Frame(parent)
            error_frame.pack(fill=X, pady=20)
            ttk.Label(error_frame, text="Error loading Dictionary tab:",
                     font=('Segoe UI', 10, 'bold'), foreground='#ff6b6b').pack(anchor=W)
            ttk.Label(error_frame, text=str(e),
                     font=('Segoe UI', 9), foreground='#ff6b6b', wraplength=450).pack(anchor=W, pady=(5, 0))
            ttk.Label(error_frame, text="Please restart the application and try again.\n"
                                       "Check logs (crosstrans.log) for details.",
                     font=('Segoe UI', 9), foreground='#888888').pack(anchor=W, pady=(10, 0))

    def _create_dictionary_tab_content(self, parent):
        """Create the main content of Dictionary tab."""
        # Defensive import with error logging
        try:
            from src.core.nlp_manager import nlp_manager, LANGUAGE_PACKS
        except ImportError as e:
            logging.error(f"Failed to import nlp_manager: {e}")
            raise RuntimeError(f"Cannot import NLP manager: {e}")

        # Set config reference for nlp_manager
        try:
            nlp_manager.set_config(self.config)
        except Exception as e:
            logging.warning(f"Failed to set nlp_manager config: {e}")
            # Continue - this is not fatal

        # NOTE: Don't clear cache here - it defeats pre-warming optimization.
        # Cache is cleared only after install/uninstall operations in:
        # - _on_install_complete() and _on_bulk_install_complete()
        # - _on_bulk_delete_complete() and uninstall handlers

        # Store references
        self.nlp_pack_rows = {}
        self._nlp_all_languages = list(LANGUAGE_PACKS.keys())
        self._nlp_list_expanded = False  # Default: collapsed
        self._nlp_search_updating = False  # Flag to prevent filter trigger on placeholder update

        # ============ PROGRESS BAR (at top, hidden by default) ============
        self.nlp_progress_frame = ttk.Frame(parent)
        # Don't pack initially

        self.nlp_progress_label = ttk.Label(self.nlp_progress_frame, text="",
                                            font=('Segoe UI', 10))
        self.nlp_progress_label.pack(anchor=W)

        if HAS_TTKBOOTSTRAP:
            self.nlp_progress_bar = ttk.Progressbar(self.nlp_progress_frame,
                                                    bootstyle="success-striped",
                                                    length=500, mode='determinate')
        else:
            self.nlp_progress_bar = ttk.Progressbar(self.nlp_progress_frame,
                                                    length=500, mode='determinate')
        self.nlp_progress_bar.pack(fill=X, pady=5)

        # ============ INSTALLED LANGUAGES SECTION ============
        self.installed_frame = ttk.LabelFrame(parent, text=" Installed Languages ", padding=10)
        self.installed_frame.pack(fill=X, pady=(0, 15))

        # Get installed languages with error handling
        try:
            installed_languages = nlp_manager.get_installed_languages()
        except Exception as e:
            logging.error(f"Failed to get installed languages: {e}")
            installed_languages = []
        installed_count = len(installed_languages)
        total_count = len(LANGUAGE_PACKS)

        # Uninstall All button (only show if languages are installed)
        if installed_count > 0:
            uninstall_all_frame = ttk.Frame(self.installed_frame)
            uninstall_all_frame.pack(fill=X, pady=(0, 10))

            if HAS_TTKBOOTSTRAP:
                self.uninstall_all_btn = ttk.Button(uninstall_all_frame, text="Uninstall All",
                                                    width=12, bootstyle="danger-outline",
                                                    command=self._delete_all_nlp_packs)
            else:
                self.uninstall_all_btn = ttk.Button(uninstall_all_frame, text="Uninstall All",
                                                    width=12, command=self._delete_all_nlp_packs)
            self.uninstall_all_btn.pack(side=RIGHT)

        if installed_languages:
            # Create scrollable container for installed languages (max height 200px)
            installed_container = ttk.Frame(self.installed_frame)
            installed_container.pack(fill=X, expand=False)

            # Canvas for scrolling
            installed_canvas = tk.Canvas(installed_container, bg='#2b2b2b', highlightthickness=0, height=min(200, len(installed_languages) * 35))
            installed_scrollbar = ttk.Scrollbar(installed_container, orient="vertical", command=installed_canvas.yview)

            installed_inner_frame = ttk.Frame(installed_canvas)
            installed_inner_frame.bind(
                "<Configure>",
                lambda e: installed_canvas.configure(scrollregion=installed_canvas.bbox("all"))
            )

            installed_canvas.create_window((0, 0), window=installed_inner_frame, anchor="nw")
            installed_canvas.configure(yscrollcommand=installed_scrollbar.set)

            installed_canvas.pack(side=LEFT, fill=X, expand=True)
            # Only show scrollbar if more than 5 languages
            if len(installed_languages) > 5:
                installed_scrollbar.pack(side=RIGHT, fill=tk.Y)

            # Mouse wheel scrolling
            def _on_installed_mousewheel(event):
                installed_canvas.yview_scroll(int(-3 * (event.delta / 120)), "units")
            installed_canvas.bind("<MouseWheel>", _on_installed_mousewheel)
            installed_inner_frame.bind("<MouseWheel>", _on_installed_mousewheel)

            # Create a row for each installed language with Uninstall button
            for lang in installed_languages:
                row = ttk.Frame(installed_inner_frame)
                row.pack(fill=X, pady=3)
                row.bind("<MouseWheel>", _on_installed_mousewheel)

                # Green checkmark + language name
                chk = tk.Label(row, text="✓", fg='#28a745', bg='#2b2b2b',
                        font=('Segoe UI', 10, 'bold'))
                chk.pack(side=LEFT)
                chk.bind("<MouseWheel>", _on_installed_mousewheel)

                lbl = ttk.Label(row, text=lang, font=('Segoe UI', 10), width=20)
                lbl.pack(side=LEFT, padx=(5, 10))
                lbl.bind("<MouseWheel>", _on_installed_mousewheel)

                # Size info
                pack_info = LANGUAGE_PACKS.get(lang)
                if pack_info:
                    size_lbl = ttk.Label(row, text=f"~{pack_info.size_mb} MB",
                             font=('Segoe UI', 9), foreground='#888888')
                    size_lbl.pack(side=LEFT, padx=(0, 15))
                    size_lbl.bind("<MouseWheel>", _on_installed_mousewheel)

                # Uninstall button
                if HAS_TTKBOOTSTRAP:
                    uninstall_btn = ttk.Button(row, text="Uninstall", width=10,
                                              bootstyle="danger-outline",
                                              command=lambda l=lang: self._uninstall_nlp_pack(l))
                else:
                    uninstall_btn = ttk.Button(row, text="Uninstall", width=10,
                                              command=lambda l=lang: self._uninstall_nlp_pack(l))
                uninstall_btn.pack(side=LEFT)

            # Summary (outside scrollable area)
            total_size = nlp_manager.get_total_installed_size()
            self.nlp_summary_label = ttk.Label(
                self.installed_frame,
                text=f"{installed_count} language(s) installed (~{total_size} MB total)",
                font=('Segoe UI', 9), foreground='#888888'
            )
            self.nlp_summary_label.pack(anchor=W, pady=(10, 0))
        else:
            # No languages installed
            self.nlp_summary_label = ttk.Label(
                self.installed_frame,
                text="No language packs installed. Click 'Add More Languages' below to install.",
                font=('Segoe UI', 10), foreground='#888888'
            )
            self.nlp_summary_label.pack(anchor=W, pady=10)

        # ============ COLLAPSIBLE "ADD MORE LANGUAGES" SECTION ============
        # Toggle header
        toggle_frame = ttk.Frame(parent)
        toggle_frame.pack(fill=X, pady=(0, 5))

        self._toggle_arrow = tk.StringVar(value="▶")  # Collapsed by default
        toggle_label = tk.Label(toggle_frame, textvariable=self._toggle_arrow,
                               font=('Segoe UI', 10), fg='#4da6ff', cursor='hand2')
        toggle_label.pack(side=LEFT)
        toggle_label.bind('<Button-1>', lambda e: self._toggle_nlp_list())

        toggle_text = tk.Label(toggle_frame, text="Add More Languages",
                              font=('Segoe UI', 10, 'bold'), fg='#4da6ff', cursor='hand2')
        toggle_text.pack(side=LEFT, padx=(5, 0))
        toggle_text.bind('<Button-1>', lambda e: self._toggle_nlp_list())

        # Available count
        not_installed_count = total_count - installed_count
        self._available_count_label = ttk.Label(toggle_frame, text=f"({not_installed_count} available)",
                 font=('Segoe UI', 9), foreground='#888888')
        self._available_count_label.pack(side=LEFT, padx=(10, 0))

        # ============ COLLAPSIBLE CONTENT FRAME ============
        self.nlp_collapsible_frame = ttk.Frame(parent)
        # Don't pack initially (collapsed)

        # Search and filter inside collapsible frame
        controls_frame = ttk.Frame(self.nlp_collapsible_frame)
        controls_frame.pack(fill=X, pady=(5, 10))

        # Search box
        ttk.Label(controls_frame, text="🔍", font=('Segoe UI', 10)).pack(side=LEFT, padx=(0, 5))
        self.nlp_search_var = tk.StringVar()
        self.nlp_search_entry = ttk.Entry(controls_frame, textvariable=self.nlp_search_var,
                                          font=('Segoe UI', 10), width=25)
        self.nlp_search_entry.pack(side=LEFT)
        self.nlp_search_entry.insert(0, "Search...")
        self.nlp_search_entry.bind('<FocusIn>', self._on_nlp_search_focus_in)
        self.nlp_search_entry.bind('<FocusOut>', self._on_nlp_search_focus_out)
        self.nlp_search_var.trace_add('write', self._filter_nlp_languages)

        # Always show not-installed languages only (no filter UI needed)
        self.nlp_filter_var = tk.StringVar(value="not_installed")

        # Install All button (right side)
        if HAS_TTKBOOTSTRAP:
            self.install_all_btn = ttk.Button(controls_frame, text="Install All", width=10,
                                              bootstyle="success-outline",
                                              command=self._install_all_nlp_packs)
        else:
            self.install_all_btn = ttk.Button(controls_frame, text="Install All", width=10,
                                              command=self._install_all_nlp_packs)
        self.install_all_btn.pack(side=RIGHT, padx=2)

        # Animation state for bulk buttons
        self._bulk_animation_running = False
        self._bulk_animation_step = 0
        self._bulk_animation_btn = None
        self._bulk_animation_original_text = ""

        # Scrollable language list
        list_container = ttk.Frame(self.nlp_collapsible_frame)
        list_container.pack(fill=BOTH, expand=True, pady=(0, 10))

        # Canvas for scrolling
        self.nlp_canvas = tk.Canvas(list_container, bg='#2b2b2b', highlightthickness=0, height=200)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.nlp_canvas.yview)

        self.nlp_scrollable_frame = ttk.Frame(self.nlp_canvas)
        self.nlp_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.nlp_canvas.configure(scrollregion=self.nlp_canvas.bbox("all"))
        )

        self.nlp_canvas.create_window((0, 0), window=self.nlp_scrollable_frame, anchor="nw")
        self.nlp_canvas.configure(yscrollcommand=scrollbar.set)

        # Mouse wheel scrolling (only when canvas has focus)
        def on_mousewheel(event):
            if self.nlp_canvas.winfo_exists():
                self.nlp_canvas.yview_scroll(int(-3*(event.delta/120)), "units")

        self.nlp_canvas.bind("<MouseWheel>", on_mousewheel)
        self.nlp_scrollable_frame.bind("<MouseWheel>", on_mousewheel)

        self.nlp_canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=tk.Y)

        # Header row
        header = ttk.Frame(self.nlp_scrollable_frame)
        header.pack(fill=X, pady=(0, 5), padx=5)
        ttk.Label(header, text="Language", font=('Segoe UI', 9, 'bold'), width=20).pack(side=LEFT)
        ttk.Label(header, text="Category", font=('Segoe UI', 9, 'bold'), width=12).pack(side=LEFT)
        ttk.Label(header, text="Size", font=('Segoe UI', 9, 'bold'), width=8).pack(side=LEFT)
        ttk.Label(header, text="", width=10).pack(side=LEFT)

        ttk.Separator(self.nlp_scrollable_frame).pack(fill=X, pady=3, padx=5)

        # Create rows for each language
        self._create_nlp_language_rows()

        # Info note (outside collapsible)
        ttk.Label(parent, text="ℹ️ Language packs are downloaded from PyPI. Internet connection required.",
                  font=('Segoe UI', 9), foreground='#666666').pack(anchor=W, pady=(10, 0))

    def _toggle_nlp_list(self):
        """Toggle the collapsible language list."""
        self._nlp_list_expanded = not self._nlp_list_expanded

        if self._nlp_list_expanded:
            self._toggle_arrow.set("▼")
            self.nlp_collapsible_frame.pack(fill=BOTH, expand=True, pady=(0, 5))

            # Auto-scroll to top and focus search for immediate interaction
            def setup_expanded_view():
                try:
                    self.nlp_canvas.yview_moveto(0.0)  # Scroll to top
                    # Clear search placeholder and focus
                    current = self.nlp_search_entry.get()
                    if current in ("Search...", "Search languages..."):
                        self._nlp_search_updating = True
                        self.nlp_search_entry.delete(0, tk.END)
                        self._nlp_search_updating = False
                    self.nlp_search_entry.focus_set()
                except tk.TclError:
                    pass  # Widget destroyed
            self.nlp_collapsible_frame.after(50, setup_expanded_view)
        else:
            self._toggle_arrow.set("▶")
            self.nlp_collapsible_frame.pack_forget()

    def _create_nlp_language_rows(self):
        """Create language rows in the scrollable frame (not installed only)."""
        from src.core.nlp_manager import nlp_manager, LANGUAGE_PACKS

        # Clear existing rows (skip header and separator)
        for widget in list(self.nlp_scrollable_frame.winfo_children())[2:]:
            widget.destroy()
        self.nlp_pack_rows.clear()

        # Get filter settings
        search_term = self.nlp_search_var.get().lower()
        if search_term in ("search...", "search languages..."):
            search_term = ""
        filter_mode = self.nlp_filter_var.get()

        # When search is empty, show ALL languages (both installed & not installed)
        # Only apply filter when user starts typing
        show_all = not search_term

        # Create rows for each language
        for language in sorted(LANGUAGE_PACKS.keys()):
            pack = LANGUAGE_PACKS[language]
            is_installed = nlp_manager.is_installed(language)

            # Apply search filter (only when user is typing)
            if search_term and search_term not in language.lower():
                continue

            # Apply installed filter only when search term exists
            if not show_all:
                if filter_mode == "not_installed" and is_installed:
                    continue

            row = ttk.Frame(self.nlp_scrollable_frame)
            row.pack(fill=X, pady=2, padx=5)

            # Language name
            ttk.Label(row, text=language, font=('Segoe UI', 10), width=20).pack(side=LEFT)

            # Category
            ttk.Label(row, text=pack.category, font=('Segoe UI', 9),
                     foreground='#888888', width=12).pack(side=LEFT)

            # Size
            ttk.Label(row, text=f"~{pack.size_mb}MB", font=('Segoe UI', 9), width=8).pack(side=LEFT)

            # Action button
            btn_frame = ttk.Frame(row)
            btn_frame.pack(side=LEFT)

            if is_installed:
                # Show "Installed" badge instead of button
                badge = tk.Label(btn_frame, text="✓ Installed", bg='#28a745', fg='white',
                               font=('Segoe UI', 8), padx=6, pady=2)
                badge.pack()
                action_btn = None
            else:
                if HAS_TTKBOOTSTRAP:
                    action_btn = ttk.Button(btn_frame, text="Install", width=8,
                                           bootstyle="success-outline",
                                           command=lambda l=language: self._install_nlp_pack(l))
                else:
                    action_btn = ttk.Button(btn_frame, text="Install", width=8,
                                           command=lambda l=language: self._install_nlp_pack(l))
                action_btn.pack()

            # Store references
            self.nlp_pack_rows[language] = {
                'row': row,
                'action_btn': action_btn,
                'btn_frame': btn_frame
            }

    def _on_nlp_search_focus_in(self, event):
        """Handle search box focus in."""
        current = self.nlp_search_entry.get()
        if current in ("Search...", "Search languages..."):
            # Temporarily disable trace to avoid triggering filter
            self._nlp_search_updating = True
            self.nlp_search_entry.delete(0, tk.END)
            self._nlp_search_updating = False

    def _on_nlp_search_focus_out(self, event):
        """Handle search box focus out."""
        if not self.nlp_search_entry.get():
            # Temporarily disable trace to avoid triggering filter
            self._nlp_search_updating = True
            self.nlp_search_entry.insert(0, "Search...")
            self._nlp_search_updating = False

    def _filter_nlp_languages(self, *args):
        """Filter language list based on search and filter settings."""
        # Skip if install/uninstall is in progress
        if getattr(self, '_nlp_operation_in_progress', False):
            return
        # Skip if just updating placeholder text
        if getattr(self, '_nlp_search_updating', False):
            return
        self._create_nlp_language_rows()

    def _update_nlp_summary(self):
        """Update NLP installation summary."""
        from src.core.nlp_manager import nlp_manager

        installed_count, total_count = nlp_manager.get_language_count()
        total_size = nlp_manager.get_total_installed_size()

        if installed_count > 0:
            self.nlp_summary_label.config(
                text=f"{installed_count} language(s) installed (~{total_size} MB total)"
            )
        else:
            self.nlp_summary_label.config(
                text="No language packs installed. Click 'Add More Languages' below to install."
            )

    def _install_nlp_pack(self, language: str):
        """Install an NLP language pack with animated progress bar."""
        from src.core.nlp_manager import nlp_manager, LANGUAGE_PACKS

        # Prevent filter from triggering during install
        self._nlp_operation_in_progress = True

        pack_info = LANGUAGE_PACKS.get(language)
        size_mb = pack_info.size_mb if pack_info else "?"

        # Show progress bar at top of tab (before installed section)
        self.nlp_progress_frame.pack(fill=X, pady=(0, 15), before=self.installed_frame)
        self.nlp_progress_bar['value'] = 0
        if HAS_TTKBOOTSTRAP:
            self.nlp_progress_bar.configure(bootstyle="info-striped")
        self.window.update()

        # Disable all Install buttons
        self._disable_all_nlp_buttons()

        # Start animated progress simulation
        self._progress_animation_running = True
        self._nlp_install_base_text = f"Installing {language} (~{size_mb} MB)"
        self._animate_progress(0)
        self._animate_install_text(0)

        # Run installation in thread
        def do_install():
            def progress_callback(message: str, percent: int):
                # Update base text for animation (remove trailing dots)
                base_msg = message.rstrip('.')
                self._nlp_install_base_text = base_msg
                self.window.after(0, lambda p=percent: self._update_install_progress_bar(p))

            success, error = nlp_manager.install(language, progress_callback)
            self._progress_animation_running = False
            self.window.after(0, lambda: self._on_install_complete(language, success, error))

        thread = threading.Thread(target=do_install, daemon=True)
        thread.start()

    def _animate_progress(self, value: int):
        """Animate progress bar smoothly."""
        if not self._progress_animation_running:
            return
        # Gradually increase to 90% while waiting for actual completion
        if value < 90:
            self.nlp_progress_bar['value'] = value
            self.window.after(200, lambda: self._animate_progress(value + 2))

    def _animate_install_text(self, state: int):
        """Animate the 'Installing...' text with moving dots and color change."""
        if not self._progress_animation_running:
            return

        try:
            # Dot patterns for animation: . -> .. -> ... -> .... -> ...
            dot_patterns = ['.', '..', '...', '....', '...', '..']
            dots = dot_patterns[state % len(dot_patterns)]

            # Color cycling (cyan -> blue -> purple -> magenta -> blue -> cyan)
            colors = ['#00bcd4', '#2196f3', '#9c27b0', '#e91e63', '#673ab7', '#03a9f4']
            color = colors[state % len(colors)]

            # Get base text
            base_text = getattr(self, '_nlp_install_base_text', 'Installing')
            display_text = f"⏳ {base_text}{dots}"

            # Update label with new text and color
            self.nlp_progress_label.config(text=display_text, foreground=color)

            # Schedule next animation frame (300ms interval)
            self.window.after(300, lambda: self._animate_install_text(state + 1))

        except tk.TclError:
            pass  # Widget destroyed

    def _update_install_progress_bar(self, percent: int):
        """Update only the progress bar value."""
        try:
            if percent > 0:
                self.nlp_progress_bar['value'] = percent
        except tk.TclError:
            pass

    def _update_install_progress(self, message: str, percent: int):
        """Update installation progress UI (for bulk operations)."""
        try:
            # Update base text for animation (remove trailing dots)
            base_msg = message.rstrip('.')
            self._nlp_install_base_text = base_msg
            if percent > 0:
                self.nlp_progress_bar['value'] = percent
        except tk.TclError:
            pass

    def _disable_all_nlp_buttons(self):
        """Disable all Install/Uninstall buttons during operation."""
        # Disable buttons in Add More Languages list
        for lang, row_data in self.nlp_pack_rows.items():
            if row_data.get('action_btn'):
                try:
                    row_data['action_btn'].config(state='disabled')
                except tk.TclError:
                    pass
        # Disable Uninstall buttons in Installed section
        for widget in self.installed_frame.winfo_children():
            if isinstance(widget, ttk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Button):
                        try:
                            child.config(state='disabled')
                        except tk.TclError:
                            pass

    def _on_install_complete(self, language: str, success: bool, error: str):
        """Handle installation completion with animation."""
        from src.core.nlp_manager import nlp_manager

        if success:
            is_basic_mode = (error == "BASIC_MODE")

            if is_basic_mode:
                self.nlp_progress_label.config(
                    text=f"ℹ {language} installed with basic tokenization",
                    foreground='#17a2b8')
            else:
                self.nlp_progress_label.config(
                    text=f"✓ {language} installed successfully!",
                    foreground='#28a745')
            self.nlp_progress_bar['value'] = 100

            if HAS_TTKBOOTSTRAP:
                self.nlp_progress_bar.configure(bootstyle="info" if is_basic_mode else "success")

            # Delay before hiding progress and refreshing
            def finish_install():
                self.nlp_progress_frame.pack_forget()
                # Clear cache to force re-check installed status
                nlp_manager._installed_cache.clear()
                # Re-enable filter
                self._nlp_operation_in_progress = False
                # Delay to let Python import system stabilize, then refresh
                self.window.after(500, self._refresh_dictionary_tab)

            self.window.after(1500, finish_install)
        else:
            # Hide progress immediately on error
            self.nlp_progress_frame.pack_forget()
            # Re-enable filter
            self._nlp_operation_in_progress = False

            # Re-enable all buttons
            for lang, row_data in self.nlp_pack_rows.items():
                if row_data.get('action_btn'):
                    try:
                        row_data['action_btn'].config(state='normal')
                    except tk.TclError:
                        pass

            # Show error
            if HAS_TTKBOOTSTRAP:
                Messagebox.show_error(f"Failed to install {language}:\n\n{error}",
                                     title="Installation Failed", parent=self.window)
            else:
                from tkinter import messagebox
                messagebox.showerror("Installation Failed",
                                    f"Failed to install {language}:\n\n{error}",
                                    parent=self.window)

    def _uninstall_nlp_pack(self, language: str):
        """Uninstall an NLP language pack with animation.

        Runs pip uninstall in background thread to avoid blocking UI.
        """
        from src.core.nlp_manager import nlp_manager

        # Confirm uninstall
        if HAS_TTKBOOTSTRAP:
            answer = Messagebox.yesno(
                f"Remove {language} language pack?\n\n"
                "This will uninstall the pip packages.",
                title="Confirm Remove", parent=self.window
            )
            if answer != "Yes":
                return
        else:
            from tkinter import messagebox
            if not messagebox.askyesno("Confirm Remove",
                                       f"Remove {language} language pack?\n\n"
                                       "This will uninstall the pip packages.",
                                       parent=self.window):
                return

        # Prevent filter from triggering during uninstall
        self._nlp_operation_in_progress = True

        # Disable all buttons
        self._disable_all_nlp_buttons()

        # Show progress bar at top (before installed section)
        self.nlp_progress_frame.pack(fill=X, pady=(0, 15), before=self.installed_frame)
        self.nlp_progress_bar['value'] = 0
        if HAS_TTKBOOTSTRAP:
            self.nlp_progress_bar.configure(bootstyle="warning-striped")
        self.window.update()

        # Start animation (same pattern as install)
        self._progress_animation_running = True
        self._nlp_install_base_text = f"Removing {language}"
        self._animate_progress(0)
        self._animate_install_text(0)

        # Run uninstall in background thread
        def do_uninstall():
            def progress_callback(message: str, percent: int):
                def update_ui():
                    try:
                        base_msg = message.rstrip('.')
                        self._nlp_install_base_text = base_msg
                        self.nlp_progress_bar['value'] = percent
                    except tk.TclError:
                        pass
                self.window.after(0, update_ui)

            success, error = nlp_manager.uninstall(language, progress_callback)

            # Stop animation
            self._progress_animation_running = False

            def on_complete():

                if success:
                    # Clear cache to force re-check
                    nlp_manager._installed_cache.clear()

                    # Update config
                    self.config.remove_nlp_installed(language)

                    # Show success animation (reset color to green)
                    self.nlp_progress_bar['value'] = 100
                    self.nlp_progress_label.config(text=f"✓ {language} removed successfully!", foreground='#28a745')
                    if HAS_TTKBOOTSTRAP:
                        self.nlp_progress_bar.configure(bootstyle="success")
                    self.window.update()

                    # Delay before hiding and refreshing
                    def finish_uninstall():
                        self.nlp_progress_frame.pack_forget()
                        if HAS_TTKBOOTSTRAP:
                            self.nlp_progress_bar.configure(bootstyle="success-striped")
                        # Re-enable filter
                        self._nlp_operation_in_progress = False
                        # Delay to let Python import system stabilize
                        self.window.after(500, self._refresh_dictionary_tab)

                    self.window.after(1000, finish_uninstall)
                else:
                    # Hide progress
                    self.nlp_progress_frame.pack_forget()
                    if HAS_TTKBOOTSTRAP:
                        self.nlp_progress_bar.configure(bootstyle="success-striped")
                    # Re-enable filter
                    self._nlp_operation_in_progress = False

                    # Re-enable buttons
                    self._refresh_dictionary_tab()

                    if HAS_TTKBOOTSTRAP:
                        Messagebox.show_error(f"Failed to remove {language}:\n\n{error}",
                                             title="Remove Failed", parent=self.window)
                    else:
                        from tkinter import messagebox
                        messagebox.showerror("Remove Failed",
                                            f"Failed to remove {language}:\n\n{error}",
                                            parent=self.window)

            self.window.after(0, on_complete)

        thread = threading.Thread(target=do_uninstall, daemon=True)
        thread.start()

    def _install_all_nlp_packs(self):
        """Install all available (not installed) language packs."""
        from src.core.nlp_manager import nlp_manager, LANGUAGE_PACKS

        # Get list of not installed languages
        not_installed = [lang for lang in LANGUAGE_PACKS.keys()
                        if not nlp_manager.is_installed(lang)]

        if not not_installed:
            if HAS_TTKBOOTSTRAP:
                Messagebox.show_info("All language packs are already installed!",
                                    title="Nothing to Install", parent=self.window)
            else:
                from tkinter import messagebox
                messagebox.showinfo("Nothing to Install",
                                   "All language packs are already installed!",
                                   parent=self.window)
            return

        # Confirm install all
        total_size = sum(LANGUAGE_PACKS[lang].size_mb for lang in not_installed)
        if HAS_TTKBOOTSTRAP:
            answer = Messagebox.yesno(
                f"Install all {len(not_installed)} language packs?\n\n"
                f"Total size: ~{total_size} MB\n"
                "This may take several minutes.",
                title="Confirm Install All", parent=self.window
            )
            if answer != "Yes":
                return
        else:
            from tkinter import messagebox
            if not messagebox.askyesno("Confirm Install All",
                                       f"Install all {len(not_installed)} language packs?\n\n"
                                       f"Total size: ~{total_size} MB\n"
                                       "This may take several minutes.",
                                       parent=self.window):
                return

        # Start bulk install with animation
        self._start_bulk_animation(self.install_all_btn, "Installing")
        self._bulk_install_queue = list(not_installed)
        self._bulk_install_total = len(not_installed)
        self._bulk_install_current = 0
        self._install_next_in_queue()

    def _install_next_in_queue(self):
        """Install the next language in the bulk install queue."""
        from src.core.nlp_manager import nlp_manager, LANGUAGE_PACKS

        if not self._bulk_install_queue:
            # All done
            self._stop_bulk_animation()
            self._refresh_dictionary_tab()
            if HAS_TTKBOOTSTRAP:
                Messagebox.show_info(
                    f"Successfully installed {self._bulk_install_total} language packs!",
                    title="Install Complete", parent=self.window
                )
            else:
                from tkinter import messagebox
                messagebox.showinfo("Install Complete",
                                   f"Successfully installed {self._bulk_install_total} language packs!",
                                   parent=self.window)
            return

        language = self._bulk_install_queue.pop(0)
        self._bulk_install_current += 1

        # Update animation text
        self._bulk_animation_base_text = f"Installing ({self._bulk_install_current}/{self._bulk_install_total})"

        pack_info = LANGUAGE_PACKS.get(language)
        size_mb = pack_info.size_mb if pack_info else "?"

        # Show progress bar
        self._nlp_operation_in_progress = True
        self.nlp_progress_frame.pack(fill=X, pady=(0, 15), before=self.installed_frame)
        self.nlp_progress_bar['value'] = 0
        if HAS_TTKBOOTSTRAP:
            self.nlp_progress_bar.configure(bootstyle="info-striped")
        self.window.update()

        self._disable_all_nlp_buttons()
        self._progress_animation_running = True
        self._nlp_install_base_text = f"Installing {language} ({self._bulk_install_current}/{self._bulk_install_total})"
        self._animate_progress(0)
        self._animate_install_text(0)

        def do_install():
            def progress_callback(message: str, percent: int):
                self.window.after(0, lambda m=message, p=percent: self._update_install_progress(m, p))

            success, error = nlp_manager.install(language, progress_callback)
            self._progress_animation_running = False
            self.window.after(0, lambda: self._on_bulk_install_complete(language, success, error))

        thread = threading.Thread(target=do_install, daemon=True)
        thread.start()

    def _on_bulk_install_complete(self, language: str, success: bool, error: str):
        """Handle completion of one language in bulk install."""
        if success:
            self.nlp_progress_bar['value'] = 100
            self.nlp_progress_label.config(text=f"✓ {language} installed!", foreground='#28a745')
            if HAS_TTKBOOTSTRAP:
                self.nlp_progress_bar.configure(bootstyle="success")
            self.window.update()
            self.config.add_nlp_installed(language)

            # Short delay then install next
            self.window.after(500, lambda: self._install_next_continue())
        else:
            # Log error but continue with next
            logging.warning(f"Failed to install {language}: {error}")
            self.window.after(500, lambda: self._install_next_continue())

    def _install_next_continue(self):
        """Continue to next language in queue."""
        self._nlp_operation_in_progress = False
        self.nlp_progress_frame.pack_forget()
        if HAS_TTKBOOTSTRAP:
            self.nlp_progress_bar.configure(bootstyle="success-striped")
        self._install_next_in_queue()

    def _delete_all_nlp_packs(self):
        """Delete all installed language packs."""
        from src.core.nlp_manager import nlp_manager

        installed = nlp_manager.get_installed_languages()

        if not installed:
            if HAS_TTKBOOTSTRAP:
                Messagebox.show_info("No language packs are installed!",
                                    title="Nothing to Delete", parent=self.window)
            else:
                from tkinter import messagebox
                messagebox.showinfo("Nothing to Delete",
                                   "No language packs are installed!",
                                   parent=self.window)
            return

        # Confirm delete all
        if HAS_TTKBOOTSTRAP:
            answer = Messagebox.yesno(
                f"Remove all {len(installed)} language packs?\n\n"
                "This cannot be undone.",
                title="Confirm Delete All", parent=self.window
            )
            if answer != "Yes":
                return
        else:
            from tkinter import messagebox
            if not messagebox.askyesno("Confirm Delete All",
                                       f"Remove all {len(installed)} language packs?\n\n"
                                       "This cannot be undone.",
                                       parent=self.window):
                return

        # Start bulk delete with animation
        self._start_bulk_animation(self.uninstall_all_btn, "Deleting")
        self._bulk_delete_queue = list(installed)
        self._bulk_delete_total = len(installed)
        self._bulk_delete_current = 0
        self._delete_next_in_queue()

    def _delete_next_in_queue(self):
        """Delete the next language in the bulk delete queue."""
        from src.core.nlp_manager import nlp_manager

        if not self._bulk_delete_queue:
            # All done
            self._stop_bulk_animation()
            self._refresh_dictionary_tab()
            if HAS_TTKBOOTSTRAP:
                Messagebox.show_info(
                    f"Successfully removed {self._bulk_delete_total} language packs!",
                    title="Delete Complete", parent=self.window
                )
            else:
                from tkinter import messagebox
                messagebox.showinfo("Delete Complete",
                                   f"Successfully removed {self._bulk_delete_total} language packs!",
                                   parent=self.window)
            return

        language = self._bulk_delete_queue.pop(0)
        self._bulk_delete_current += 1

        # Update animation text
        self._bulk_animation_base_text = f"Deleting ({self._bulk_delete_current}/{self._bulk_delete_total})"

        # Show progress bar
        self._nlp_operation_in_progress = True
        self.nlp_progress_frame.pack(fill=X, pady=(0, 15), before=self.installed_frame)
        self.nlp_progress_bar['value'] = 0
        if HAS_TTKBOOTSTRAP:
            self.nlp_progress_bar.configure(bootstyle="warning-striped")
        self.window.update()

        self._disable_all_nlp_buttons()
        self._progress_animation_running = True
        self._nlp_install_base_text = f"Removing {language} ({self._bulk_delete_current}/{self._bulk_delete_total})"
        self._animate_progress(0)
        self._animate_install_text(0)

        def do_uninstall():
            def progress_callback(message: str, percent: int):
                self.window.after(0, lambda m=message, p=percent: self._update_install_progress(m, p))

            success, error = nlp_manager.uninstall(language, progress_callback)
            self._progress_animation_running = False
            self.window.after(0, lambda: self._on_bulk_delete_complete(language, success, error))

        thread = threading.Thread(target=do_uninstall, daemon=True)
        thread.start()

    def _on_bulk_delete_complete(self, language: str, success: bool, error: str):
        """Handle completion of one language in bulk delete."""
        from src.core.nlp_manager import nlp_manager

        if success:
            nlp_manager._installed_cache.clear()
            self.config.remove_nlp_installed(language)
            self.nlp_progress_bar['value'] = 100
            self.nlp_progress_label.config(text=f"✓ {language} removed!", foreground='#28a745')
            if HAS_TTKBOOTSTRAP:
                self.nlp_progress_bar.configure(bootstyle="success")
            self.window.update()

            # Short delay then delete next
            self.window.after(500, lambda: self._delete_next_continue())
        else:
            # Log error but continue with next
            logging.warning(f"Failed to remove {language}: {error}")
            self.window.after(500, lambda: self._delete_next_continue())

    def _delete_next_continue(self):
        """Continue to next language in queue."""
        self._nlp_operation_in_progress = False
        self.nlp_progress_frame.pack_forget()
        if HAS_TTKBOOTSTRAP:
            self.nlp_progress_bar.configure(bootstyle="success-striped")
        self._delete_next_in_queue()

    def _start_bulk_animation(self, btn, base_text: str):
        """Start '...' animation on a bulk action button."""
        self._bulk_animation_running = True
        self._bulk_animation_step = 0
        self._bulk_animation_btn = btn
        self._bulk_animation_base_text = base_text
        self._bulk_animation_original_text = btn.cget('text')
        self._animate_bulk_button()

    def _animate_bulk_button(self):
        """Animate the bulk action button with moving dots."""
        if not self._bulk_animation_running or not self._bulk_animation_btn:
            return

        try:
            dots = "." * (self._bulk_animation_step % 4)
            spaces = " " * (3 - (self._bulk_animation_step % 4))
            self._bulk_animation_btn.configure(text=f"{self._bulk_animation_base_text}{dots}{spaces}")
            self._bulk_animation_step += 1
            self.window.after(400, self._animate_bulk_button)
        except tk.TclError:
            self._bulk_animation_running = False

    def _stop_bulk_animation(self):
        """Stop bulk action button animation."""
        self._bulk_animation_running = False
        if self._bulk_animation_btn:
            try:
                self._bulk_animation_btn.configure(text=self._bulk_animation_original_text)
            except tk.TclError:
                pass
        self._bulk_animation_btn = None

    def _refresh_dictionary_tab(self):
        """Refresh entire Dictionary tab to reflect install/uninstall changes."""
        try:
            # Find and clear the Dictionary tab frame
            if hasattr(self, 'notebook'):
                for i in range(self.notebook.index('end')):
                    if 'Dictionary' in self.notebook.tab(i, 'text'):
                        # Get the tab frame
                        tab_id = self.notebook.tabs()[i]
                        dict_frame = self.notebook.nametowidget(tab_id)

                        # Clear all children
                        for widget in dict_frame.winfo_children():
                            widget.destroy()

                        # Rebuild the tab
                        self._create_dictionary_tab(dict_frame)

                        # Re-select Dictionary tab
                        self.notebook.select(i)
                        break
        except Exception as e:
            logging.error(f"Failed to refresh Dictionary tab: {e}")
            # Fallback: show message asking user to reopen Settings
            if HAS_TTKBOOTSTRAP:
                Messagebox.show_warning(
                    "Please close and reopen Settings to see changes.",
                    title="Refresh Failed", parent=self.window
                )

    def open_dictionary_tab(self):
        """Open settings window with Dictionary tab selected."""
        self.open_tab("Dictionary")

    def open_tab(self, tab_name: str):
        """Open settings window with specified tab selected.

        Args:
            tab_name: Name of tab to select (e.g., "General", "Hotkeys", "API Key", "Dictionary", "Guide")
        """
        if hasattr(self, 'notebook'):
            # Find tab by name (partial match)
            for i in range(self.notebook.index('end')):
                tab_text = self.notebook.tab(i, 'text')
                if tab_name in tab_text:
                    self.notebook.select(i)
                    break
