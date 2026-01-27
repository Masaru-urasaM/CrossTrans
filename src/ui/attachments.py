"""
Attachment Area Widget for CrossTrans.
Handles file and image attachments with drag-and-drop support.
"""
import os
import logging
import tkinter as tk
from tkinter import ttk, filedialog
from PIL import Image, ImageTk

# Get assets directory path
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets')

try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False

try:
    import ttkbootstrap
    HAS_TTKBOOTSTRAP = True
except ImportError:
    HAS_TTKBOOTSTRAP = False


class AttachmentArea(ttk.Frame):
    """Widget to display and manage attachments."""

    def __init__(self, parent, config, on_change=None):
        super().__init__(parent)
        self.config = config
        self.on_change = on_change
        self.attachments = []  # List of {'type': 'image'|'file', 'path': str}
        self.thumbnails = []   # Keep references to avoid GC

        self._create_ui()

    def _create_ui(self):
        """Create the UI layout."""
        # Top bar
        self.top_frame = ttk.Frame(self)
        self.top_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(self.top_frame, text="Attachments:", font=('Segoe UI', 9, 'bold')).pack(side=tk.LEFT)

        # Clear button with bootstyle if available (rightmost position)
        clear_kwargs = {"text": "Clear All", "command": self.clear, "width": 10}
        if HAS_TTKBOOTSTRAP:
            clear_kwargs["bootstyle"] = "danger-outline"
        self.clear_btn = ttk.Button(self.top_frame, **clear_kwargs)
        # Pack clear_btn later when items exist

        # Scrollable container for items (no visible scrollbar)
        self.scroll_canvas = tk.Canvas(self, bg='#2b2b2b', highlightthickness=0, height=95)
        self.scroll_canvas.pack(fill=tk.X, expand=False)

        # Inner frame for items
        self.items_frame = tk.Frame(self.scroll_canvas, bg='#2b2b2b')
        self.canvas_window = self.scroll_canvas.create_window((0, 0), window=self.items_frame, anchor='nw')

        # Update scroll region when items change
        self.items_frame.bind('<Configure>', self._on_items_configure)
        self.scroll_canvas.bind('<Configure>', self._on_canvas_configure)

        # Mouse wheel horizontal scroll
        self.scroll_canvas.bind('<MouseWheel>', self._on_mousewheel)
        self.items_frame.bind('<MouseWheel>', self._on_mousewheel)
        # Also bind to self for when hovering over the area
        self.bind('<MouseWheel>', self._on_mousewheel)

        # Add button - Professional styled container matching file items
        self._create_add_button()

        # Create Menu with icons
        self.add_menu = tk.Menu(self, tearoff=0, font=('Segoe UI', 10))

        # Update visibility and style based on current config
        self._update_add_button_style()

        # Register for drag-and-drop with tkinterdnd2 if available
        self._setup_dnd()

    def _on_items_configure(self, event):
        """Update scroll region when items frame changes."""
        self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox('all'))

    def _on_canvas_configure(self, event):
        """Adjust canvas window height to match canvas."""
        self.scroll_canvas.itemconfig(self.canvas_window, height=event.height)

    def _on_mousewheel(self, event):
        """Handle mouse wheel for horizontal scrolling."""
        # Check if scrolling is needed (items wider than canvas)
        canvas_width = self.scroll_canvas.winfo_width()
        items_width = self.items_frame.winfo_reqwidth()

        if items_width > canvas_width:
            # Scroll horizontally (negative delta = scroll right)
            self.scroll_canvas.xview_scroll(int(-1 * (event.delta / 120)), 'units')
        return 'break'  # Prevent event propagation

    def _setup_dnd(self):
        """Setup drag-and-drop bindings with tkinterdnd2."""
        if not HAS_DND:
            logging.debug("tkinterdnd2 not available, skipping DnD setup for AttachmentArea")
            return

        try:
            # Check if DnD methods are available on this widget
            if not hasattr(self, 'drop_target_register'):
                logging.debug("Widget does not have DnD methods, skipping")
                return

            # Register the entire frame as a drop target
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<DropEnter>>', self._on_drag_enter)
            self.dnd_bind('<<DropLeave>>', self._on_drag_leave)
            self.dnd_bind('<<Drop>>', self._on_drop)

            # Also register the items_frame for better drop area
            if hasattr(self.items_frame, 'drop_target_register'):
                self.items_frame.drop_target_register(DND_FILES)
                self.items_frame.dnd_bind('<<DropEnter>>', self._on_drag_enter)
                self.items_frame.dnd_bind('<<DropLeave>>', self._on_drag_leave)
                self.items_frame.dnd_bind('<<Drop>>', self._on_drop)

            logging.info("tkinterdnd2 drag-and-drop enabled for AttachmentArea")
        except Exception as e:
            logging.warning(f"Could not setup tkinterdnd2 for AttachmentArea: {e}")

    def _create_add_button(self):
        """Create add button using image icons."""
        # Load icon images
        self._load_add_button_icons()

        # Create label to display the icon
        self.add_btn = tk.Label(self.items_frame, bg='#2b2b2b', cursor='hand2')
        self.add_btn.pack(side=tk.LEFT, padx=14, pady=14)

        # Set initial image
        self._update_add_button_style()

        # Bind events
        self.add_btn.bind("<Button-1>", lambda e: self._show_add_menu())
        self.add_btn.bind("<Enter>", self._on_add_btn_enter)
        self.add_btn.bind("<Leave>", self._on_add_btn_leave)

        # Keep reference for compatibility
        self.add_btn_canvas = self.add_btn

    def _load_add_button_icons(self):
        """Load add button icon images."""
        self._add_btn_icons = {}

        icon_files = {
            'gray': 'add_btn_gray.png',
            'blue': 'add_btn_blue.png',
            'light': 'add_btn_light.png',
            'light_blue': 'add_btn_light_blue.png',  # Drag-drop hover
        }

        for key, filename in icon_files.items():
            path = os.path.join(ASSETS_DIR, filename)
            if os.path.exists(path):
                try:
                    img = Image.open(path)
                    self._add_btn_icons[key] = ImageTk.PhotoImage(img)
                except Exception as e:
                    logging.warning(f"Failed to load icon {filename}: {e}")

        # Fallback: generate icons if files don't exist
        if not self._add_btn_icons:
            self._generate_fallback_icons()

    def _generate_fallback_icons(self):
        """Generate fallback icons if image files don't exist."""
        try:
            from src.assets.generate_icons import create_add_button_icon

            self._add_btn_icons['gray'] = ImageTk.PhotoImage(
                create_add_button_icon(56, '#888888'))
            self._add_btn_icons['blue'] = ImageTk.PhotoImage(
                create_add_button_icon(56, '#0d6efd'))
            self._add_btn_icons['light'] = ImageTk.PhotoImage(
                create_add_button_icon(56, '#aaaaaa'))
            self._add_btn_icons['light_blue'] = ImageTk.PhotoImage(
                create_add_button_icon(56, '#5a9fd4'))
        except Exception as e:
            logging.warning(f"Failed to generate fallback icons: {e}")

    def _on_add_btn_enter(self, event):
        """Hover effect - show light icon."""
        # Hover always shows light color (unless has attachments)
        if self.attachments:
            icon = self._add_btn_icons.get('blue')
        else:
            icon = self._add_btn_icons.get('light')

        if icon:
            self.add_btn.configure(image=icon)

    def _on_add_btn_leave(self, event):
        """Reset hover effect."""
        self._update_add_button_style()

    def _update_add_button_style(self):
        """Update the add button image based on attachments state.

        - Gray: no attachments (empty state)
        - Blue: has attachments
        """
        if self.attachments:
            icon = self._add_btn_icons.get('blue')
        else:
            icon = self._add_btn_icons.get('gray')

        if icon:
            self.add_btn.configure(image=icon)

    def _update_add_button_visibility(self):
        """Alias for backwards compatibility."""
        self._update_add_button_style()

    def _show_add_menu(self):
        """Show the add menu with options based on enabled features."""
        self.add_menu.delete(0, tk.END)

        vision_enabled = self.config.get('vision_enabled', False)
        file_enabled = self.config.get('file_processing_enabled', False)

        if not vision_enabled and not file_enabled:
            # Show warning that no upload features are enabled
            self.add_menu.add_command(label="⚠ No upload features enabled", state='disabled')
            self.add_menu.add_separator()
            self.add_menu.add_command(label="Open Settings to enable", command=self._open_settings_hint)
        else:
            if vision_enabled:
                self.add_menu.add_command(label="📷  Upload Images", command=self._browse_images)

            if file_enabled:
                self.add_menu.add_command(label="📄  Upload Files (.txt, .docx, .srt, .pdf)", command=self._browse_documents)

        # Position menu below button
        try:
            self.add_menu.tk_popup(self.add_btn.winfo_rootx(), self.add_btn.winfo_rooty() + self.add_btn.winfo_height())
        finally:
            self.add_menu.grab_release()

    def _open_settings_hint(self):
        """Hint to open settings - just shows a message for now."""
        from tkinter import messagebox
        messagebox.showinfo("Enable Upload Features",
                           "To enable upload features:\n\n"
                           "1. Open Settings from the system tray\n"
                           "2. Go to 'API Key' tab\n"
                           "3. Enable 'Upload Image Mode' or 'Upload File Mode'\n\n"
                           "Note: These options require a working API key.",
                           parent=self)

    def add_file(self, file_path, show_warning=False):
        """Add a file attachment."""
        if not os.path.exists(file_path):
            return False

        ext = os.path.splitext(file_path)[1].lower()
        is_image = ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp']
        is_supported_doc = ext in ['.txt', '.docx', '.srt', '.pdf']

        # Check permissions based on config
        vision_enabled = self.config.get('vision_enabled', False)
        file_enabled = self.config.get('file_processing_enabled', False)

        if is_image and not vision_enabled:
            if show_warning:
                from tkinter import messagebox
                messagebox.showwarning("Upload Image Disabled",
                                      "Upload Image Mode is not enabled.\n\n"
                                      "Please enable it in Settings > API Key tab.",
                                      parent=self)
            return False

        if not is_image and not file_enabled:
            if show_warning:
                from tkinter import messagebox
                messagebox.showwarning("Upload File Disabled",
                                      "Upload File Mode is not enabled.\n\n"
                                      "Please enable it in Settings > API Key tab.",
                                      parent=self)
            return False

        if not is_image and not is_supported_doc:
            if show_warning:
                from tkinter import messagebox
                messagebox.showwarning("Unsupported File",
                                      f"File type '{ext}' is not supported.\n\n"
                                      "Supported formats:\n"
                                      "• Images: .jpg, .jpeg, .png, .webp, .gif, .bmp\n"
                                      "• Documents: .txt, .docx, .srt, .pdf",
                                      parent=self)
            return False

        # Add to list
        att_type = 'image' if is_image else 'file'
        self.attachments.append({'type': att_type, 'path': file_path})

        self._render_item(file_path, is_image)
        self._update_visibility()
        if self.on_change:
            self.on_change()
        return True

    def _render_item(self, file_path, is_image):
        """Render a single attachment item with uniform size."""
        # Fixed size container for uniform appearance
        ITEM_WIDTH = 90
        ITEM_HEIGHT = 85

        # Main container with fixed size
        frame = tk.Frame(self.items_frame, width=ITEM_WIDTH, height=ITEM_HEIGHT,
                         bg='#3a3a3a', highlightbackground='#555555',
                         highlightthickness=1)
        frame.pack(side=tk.LEFT, padx=4, pady=2)
        frame.pack_propagate(False)  # Prevent resizing

        # Get filename
        filename = os.path.basename(file_path)

        # Content area
        content_frame = tk.Frame(frame, bg='#3a3a3a')
        content_frame.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)

        if is_image:
            try:
                img = Image.open(file_path)
                img.thumbnail((55, 50))
                photo = ImageTk.PhotoImage(img)
                self.thumbnails.append(photo)
                img_label = tk.Label(content_frame, image=photo, bg='#3a3a3a')
                img_label.pack(pady=(2, 0))
            except:
                # Fallback for broken images
                tk.Label(content_frame, text="🖼", font=('Segoe UI', 20),
                         bg='#3a3a3a', fg='#888888').pack(pady=(5, 0))
        else:
            # File type icon with color coding
            ext = os.path.splitext(file_path)[1].lower()
            icon_colors = {
                '.txt': '#4CAF50',   # Green
                '.docx': '#2196F3',  # Blue
                '.pdf': '#F44336',   # Red
                '.srt': '#FF9800',   # Orange
            }
            icon_color = icon_colors.get(ext, '#9E9E9E')

            # File icon
            icon_text = {
                '.txt': '📄',
                '.docx': '📝',
                '.pdf': '📕',
                '.srt': '🎬',
            }.get(ext, '📁')

            tk.Label(content_frame, text=icon_text, font=('Segoe UI', 18),
                     bg='#3a3a3a', fg=icon_color).pack(pady=(3, 0))

            # Extension badge
            ext_label = tk.Label(content_frame, text=ext.upper(),
                                 font=('Segoe UI', 7, 'bold'),
                                 bg=icon_color, fg='white', padx=3)
            ext_label.pack(pady=(2, 0))

        # Filename (truncated with tooltip)
        display_name = filename
        if len(display_name) > 12:
            display_name = filename[:10] + "…"

        name_label = tk.Label(frame, text=display_name, font=('Segoe UI', 7),
                              bg='#3a3a3a', fg='#cccccc')
        name_label.pack(side=tk.BOTTOM, pady=(0, 2))

        # Tooltip for full filename
        self._create_tooltip(name_label, filename)
        self._create_tooltip(frame, filename)

        # Remove button (top-right corner)
        x_btn = tk.Label(frame, text="×", font=('Segoe UI', 10, 'bold'),
                         bg='#3a3a3a', fg='#ff6666', cursor='hand2')
        x_btn.place(relx=1.0, rely=0, x=-2, y=2, anchor='ne')
        x_btn.bind("<Button-1>", lambda e, p=file_path: self._remove_item(p, frame))
        x_btn.bind("<Enter>", lambda e: x_btn.configure(fg='#ff0000'))
        x_btn.bind("<Leave>", lambda e: x_btn.configure(fg='#ff6666'))

        # Bind mousewheel to all widgets in this item for horizontal scrolling
        self._bind_mousewheel_recursive(frame)

    def _bind_mousewheel_recursive(self, widget):
        """Bind mousewheel event to widget and all its children."""
        widget.bind('<MouseWheel>', self._on_mousewheel)
        for child in widget.winfo_children():
            self._bind_mousewheel_recursive(child)

    def _create_tooltip(self, widget, text):
        """Create a simple tooltip for a widget."""
        tooltip = None

        def show_tooltip(event):
            nonlocal tooltip
            if tooltip:
                return
            x = widget.winfo_rootx() + 10
            y = widget.winfo_rooty() + widget.winfo_height() + 5
            tooltip = tk.Toplevel(widget)
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{x}+{y}")
            label = tk.Label(tooltip, text=text, bg='#ffffe0', fg='#000000',
                             relief='solid', borderwidth=1, font=('Segoe UI', 9),
                             padx=5, pady=2)
            label.pack()

        def hide_tooltip(event):
            nonlocal tooltip
            if tooltip:
                tooltip.destroy()
                tooltip = None

        widget.bind("<Enter>", show_tooltip)
        widget.bind("<Leave>", hide_tooltip)

    def _remove_item(self, path, widget):
        """Remove an attachment."""
        self.attachments = [a for a in self.attachments if a['path'] != path]
        widget.destroy()
        self._update_visibility()
        if self.on_change:
            self.on_change()

    def clear(self):
        """Clear all attachments."""
        self.attachments = []
        self.thumbnails = []
        for widget in self.items_frame.winfo_children():
            if widget != self.add_btn:
                widget.destroy()
        # Reset scroll position
        self.scroll_canvas.xview_moveto(0)
        self._update_visibility()
        if self.on_change:
            self.on_change()

    def get_attachments(self):
        """Get list of attachments."""
        return self.attachments

    def _update_visibility(self):
        """Update UI state: show/hide Clear All button and update add button style.

        Screenshot button stays fixed at rightmost position (packed by app.py).
        Clear All appears to its LEFT when there are attachments.
        """
        if self.attachments:
            # Show Clear All button (to the left of Screenshot)
            # Screenshot was packed first with side=RIGHT, so it's rightmost
            # Clear All packed with side=RIGHT will appear to its LEFT
            try:
                self.clear_btn.pack_forget()
            except tk.TclError:
                pass
            self.clear_btn.pack(side=tk.RIGHT, padx=(0, 5))
        else:
            # Hide Clear All button when no attachments
            try:
                self.clear_btn.pack_forget()
            except tk.TclError:
                pass

        # Update add button color based on attachment state
        self._update_add_button_style()

    def _browse_images(self):
        """Browse for images."""
        if not self.config.get('vision_enabled', False):
            from tkinter import messagebox
            messagebox.showwarning("Upload Image Disabled",
                                  "Upload Image Mode is not enabled.\n\n"
                                  "Please enable it in Settings > API Key tab.",
                                  parent=self)
            return

        filetypes = [("Images", "*.jpg *.jpeg *.png *.webp *.gif *.bmp")]
        files = filedialog.askopenfilenames(filetypes=filetypes, parent=self)
        for f in files:
            self.add_file(f, show_warning=True)

    def _browse_documents(self):
        """Browse for documents."""
        if not self.config.get('file_processing_enabled', False):
            from tkinter import messagebox
            messagebox.showwarning("Upload File Disabled",
                                  "Upload File Mode is not enabled.\n\n"
                                  "Please enable it in Settings > API Key tab.",
                                  parent=self)
            return

        filetypes = [("Documents", "*.txt *.docx *.srt *.pdf")]
        files = filedialog.askopenfilenames(filetypes=filetypes, parent=self)
        for f in files:
            self.add_file(f, show_warning=True)

    def _browse_files(self):
        """Deprecated, kept for compatibility if needed."""
        self._show_add_menu()

    def _on_drag_enter(self, event):
        """Visual feedback when dragging over the drop zone."""
        logging.debug("Drag enter detected on AttachmentArea")
        # Show light blue icon for drag-drop hover state
        icon = self._add_btn_icons.get('light_blue')
        if icon:
            self.add_btn.configure(image=icon)
        return event.action

    def _on_drag_leave(self, event):
        """Reset visual feedback when leaving drop zone."""
        logging.debug("Drag leave detected on AttachmentArea")
        # Reset to appropriate color based on attachment state
        self._update_add_button_style()
        return event.action

    def _on_drop(self, event):
        """Handle drag and drop."""
        logging.info(f"Drop detected on AttachmentArea, data: {event.data[:100] if event.data else 'None'}...")

        if not event.data:
            logging.warning("Drop event has no data")
            return

        # Parse file paths (tkinterdnd2 returns a string list)
        # Handling braces {} for paths with spaces
        raw_data = event.data
        paths = []

        # Basic parsing for Windows paths in DND
        if '{' in raw_data:
            current = ""
            in_brace = False
            for char in raw_data:
                if char == '{':
                    in_brace = True
                elif char == '}':
                    in_brace = False
                    if current:
                        paths.append(current)
                        current = ""
                elif char == ' ' and not in_brace:
                    if current:
                        paths.append(current)
                        current = ""
                else:
                    current += char
            if current:
                paths.append(current)
        else:
            paths = raw_data.split()

        # Track rejected files to show warning once
        rejected_images = []
        rejected_files = []
        rejected_unsupported = []

        vision_enabled = self.config.get('vision_enabled', False)
        file_enabled = self.config.get('file_processing_enabled', False)

        for path in paths:
            if not os.path.exists(path):
                continue

            ext = os.path.splitext(path)[1].lower()
            is_image = ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp']
            is_supported_doc = ext in ['.txt', '.docx', '.srt', '.pdf']

            if is_image:
                if vision_enabled:
                    self.add_file(path)
                else:
                    rejected_images.append(os.path.basename(path))
            elif is_supported_doc:
                if file_enabled:
                    self.add_file(path)
                else:
                    rejected_files.append(os.path.basename(path))
            else:
                rejected_unsupported.append(os.path.basename(path))

        # Show combined warning if any files were rejected
        if rejected_images or rejected_files or rejected_unsupported:
            from tkinter import messagebox
            msg_parts = []
            if rejected_images:
                msg_parts.append(f"Images rejected (Upload Image Mode disabled):\n• " + "\n• ".join(rejected_images[:3]))
                if len(rejected_images) > 3:
                    msg_parts[-1] += f"\n  ... and {len(rejected_images) - 3} more"
            if rejected_files:
                msg_parts.append(f"Files rejected (Upload File Mode disabled):\n• " + "\n• ".join(rejected_files[:3]))
                if len(rejected_files) > 3:
                    msg_parts[-1] += f"\n  ... and {len(rejected_files) - 3} more"
            if rejected_unsupported:
                msg_parts.append(f"Unsupported files:\n• " + "\n• ".join(rejected_unsupported[:3]))
                if len(rejected_unsupported) > 3:
                    msg_parts[-1] += f"\n  ... and {len(rejected_unsupported) - 3} more"

            messagebox.showwarning("Some Files Rejected", "\n\n".join(msg_parts), parent=self)