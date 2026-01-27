"""
Drag and Drop Handler for CrossTrans.
Handles file drag-and-drop operations using various methods (tkinterdnd2, windnd, WM_DROPFILES).
"""
import sys
import queue
import logging
import tkinter as tk
from typing import Callable, Optional, List

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.dialogs import Messagebox
    HAS_TTKBOOTSTRAP = True
except ImportError:
    HAS_TTKBOOTSTRAP = False

try:
    from tkinterdnd2 import DND_FILES
    HAS_DND = True
except ImportError:
    HAS_DND = False
    DND_FILES = None

try:
    import windnd
    HAS_WINDND = True
except ImportError:
    HAS_WINDND = False


class DropHandler:
    """Manages drag-and-drop file operations."""

    def __init__(self, root: tk.Tk):
        """Initialize drop handler.

        Args:
            root: The root Tk window for scheduling
        """
        self.root = root
        self._drop_queue: queue.Queue = queue.Queue()
        self._running = True

        # State references (set by app)
        self._popup: Optional[tk.Toplevel] = None
        self._attachment_area = None

        # Callbacks
        self._on_files_dropped: Optional[Callable[[List[str]], None]] = None

        # WM_DROPFILES state
        self._original_wndproc = None
        self._wndproc_callback = None

    def configure(self,
                  on_files_dropped: Optional[Callable[[List[str]], None]] = None):
        """Configure callback for file drops.

        Args:
            on_files_dropped: Called with list of file paths when files are dropped
        """
        self._on_files_dropped = on_files_dropped

    def set_popup(self, popup: Optional[tk.Toplevel]):
        """Set the popup window reference.

        Args:
            popup: The translator popup window
        """
        self._popup = popup

    def set_attachment_area(self, attachment_area):
        """Set the attachment area reference.

        Args:
            attachment_area: The AttachmentArea widget
        """
        self._attachment_area = attachment_area

    def setup_tkdnd(self, widget: tk.Widget):
        """Setup tkinterdnd2 drag-and-drop on a widget.

        Args:
            widget: The widget to enable drag-and-drop on
        """
        if HAS_DND and DND_FILES:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind('<<Drop>>', self._on_tkdnd_drop)
                logging.info(f"tkinterdnd2 drop registered on {widget}")
            except Exception as e:
                logging.warning(f"Failed to setup tkinterdnd2: {e}")

    def setup_windnd(self, widget: tk.Widget):
        """Setup windnd drag-and-drop on a widget.

        Args:
            widget: The widget to enable drag-and-drop on
        """
        if HAS_WINDND:
            try:
                windnd.hook_dropfiles(widget, func=self._on_windnd_drop_direct)
                logging.info(f"windnd registered on {widget}")
            except Exception as e:
                logging.warning(f"Failed to setup windnd: {e}")

    def setup_wm_dropfiles(self, hwnd: int):
        """Setup Windows message handler for WM_DROPFILES using ctypes subclassing.

        Args:
            hwnd: Window handle to hook
        """
        import ctypes
        from ctypes import wintypes

        # Windows constants
        WM_DROPFILES = 0x0233
        GWL_WNDPROC = -4

        # Function signatures
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                                     wintypes.WPARAM, wintypes.LPARAM)

        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32

        # Get original window procedure
        SetWindowLongPtrW = user32.SetWindowLongPtrW
        SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, WNDPROC]
        SetWindowLongPtrW.restype = WNDPROC

        CallWindowProcW = user32.CallWindowProcW
        CallWindowProcW.argtypes = [WNDPROC, wintypes.HWND, wintypes.UINT,
                                    wintypes.WPARAM, wintypes.LPARAM]
        CallWindowProcW.restype = ctypes.c_long

        # DragQueryFileW
        DragQueryFileW = shell32.DragQueryFileW
        DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
        DragQueryFileW.restype = wintypes.UINT

        DragFinish = shell32.DragFinish
        DragFinish.argtypes = [wintypes.HANDLE]

        def wndproc(hwnd_inner, msg, wparam, lparam):
            if msg == WM_DROPFILES:
                logging.info("WM_DROPFILES received!")
                hdrop = wparam
                try:
                    # Get number of files
                    file_count = DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                    logging.info(f"Dropped {file_count} files")

                    paths = []
                    for i in range(file_count):
                        # Get required buffer size
                        length = DragQueryFileW(hdrop, i, None, 0)
                        buffer = ctypes.create_unicode_buffer(length + 1)
                        DragQueryFileW(hdrop, i, buffer, length + 1)
                        paths.append(buffer.value)
                        logging.info(f"  File {i}: {buffer.value}")

                    DragFinish(hdrop)

                    # Process files on main thread
                    if paths:
                        self.root.after(0, lambda p=paths: self._process_dropped_files(p))

                except Exception as e:
                    logging.error(f"Error processing WM_DROPFILES: {e}")
                    import traceback
                    traceback.print_exc()

                return 0

            # Call original window procedure
            return CallWindowProcW(self._original_wndproc, hwnd_inner, msg, wparam, lparam)

        # Keep reference to prevent garbage collection
        self._wndproc_callback = WNDPROC(wndproc)

        # Subclass the window
        self._original_wndproc = SetWindowLongPtrW(hwnd, GWL_WNDPROC, self._wndproc_callback)
        logging.info(f"Window subclassed, original wndproc: {self._original_wndproc}")

    def _on_tkdnd_drop(self, event):
        """Handle file drops via tkinterdnd2.

        This runs on the main Tkinter thread, so we can directly call Tkinter methods.
        """
        logging.info(f"tkinterdnd2 drop received: {event.data}")

        if not event.data:
            logging.warning("Drop event has no data")
            return

        # Parse file paths from tkinterdnd2 format
        raw_data = event.data
        paths = []

        if '{' in raw_data:
            # Parse braced paths (handles paths with spaces)
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

        logging.info(f"Parsed paths: {paths}")
        self._process_dropped_files(paths)

    def _on_windnd_drop_direct(self, file_paths):
        """Handle file drops via windnd.

        CRITICAL: This callback runs on a WINDOWS THREAD, not the Python main thread.
        We MUST NOT call ANY Tkinter methods here (including root.after()).
        Only use thread-safe operations: logging and queue.put().
        """
        try:
            logging.info(f"windnd drop received: {len(file_paths)} files")

            # Decode paths (windnd returns bytes)
            # Windows uses system encoding (e.g., cp932 for Japanese), not UTF-8
            fs_encoding = sys.getfilesystemencoding() or 'utf-8'
            paths = []
            for fp in file_paths:
                if isinstance(fp, bytes):
                    try:
                        path = fp.decode(fs_encoding)
                    except UnicodeDecodeError:
                        path = fp.decode('utf-8', errors='replace')
                else:
                    path = str(fp)
                paths.append(path)
                logging.info(f"  Dropped file: {path}")

            # Put in thread-safe queue - DO NOT call any Tkinter methods!
            self._drop_queue.put(paths)
            logging.info("Files added to drop queue")

        except Exception as e:
            logging.error(f"Error in windnd drop handler: {e}")

    def _process_dropped_files(self, paths: List[str]):
        """Process files dropped via any method.

        Args:
            paths: List of file paths
        """
        logging.info(f"Processing {len(paths)} dropped files")

        if not self._popup or not self._popup.winfo_exists():
            logging.warning("Popup window no longer exists")
            return

        if not self._attachment_area:
            logging.warning("No attachment area available")
            self._show_upload_disabled_warning()
            return

        for path in paths:
            try:
                result = self._attachment_area.add_file(path, show_warning=True)
                logging.info(f"add_file result for {path}: {result}")
            except Exception as e:
                logging.warning(f"Error adding dropped file {path}: {e}")

        # Call callback if set
        if self._on_files_dropped:
            self._on_files_dropped(paths)

    def _show_upload_disabled_warning(self):
        """Show warning dialog that upload is disabled."""
        message = (
            "Cannot add files.\n\n"
            "Upload features are not enabled.\n"
            "Please go to Settings > API Key tab and test your API to enable upload features."
        )

        if HAS_TTKBOOTSTRAP and self._popup:
            Messagebox.show_warning(
                message,
                title="Upload Disabled",
                parent=self._popup
            )
        else:
            from tkinter import messagebox
            messagebox.showwarning(
                "Upload Disabled",
                message,
                parent=self._popup if self._popup else None
            )

    def check_drop_queue(self):
        """Check drop queue for files (runs on main Tkinter thread)."""
        try:
            while True:
                paths = self._drop_queue.get_nowait()
                logging.info(f"Processing drop queue: {len(paths)} files")
                self._process_dropped_files(paths)
        except queue.Empty:
            pass
        except Exception as e:
            logging.error(f"Error checking drop queue: {e}")
            import traceback
            traceback.print_exc()

        # Schedule next check if running and popup exists
        if self._running and self._popup:
            try:
                if self._popup.winfo_exists():
                    self.root.after(50, self.check_drop_queue)
            except tk.TclError:
                pass
            except Exception as e:
                logging.debug(f"Error scheduling next queue check: {e}")

    def start_queue_checker(self):
        """Start the drop queue checker loop."""
        self._running = True
        self.check_drop_queue()

    def stop(self):
        """Stop the drop handler."""
        self._running = False
