"""
Screenshot Capture Module for CrossTrans.
Supports multi-monitor setups with proper coordinate handling.
"""
import ctypes
import tkinter as tk
import tempfile
import os
from PIL import ImageGrab


def get_virtual_screen_bounds():
    """Get the bounding box of all monitors (virtual screen).

    Returns:
        Tuple of (left, top, width, height) for the virtual screen.
        Left and top can be negative if monitors are positioned to the left/above primary.
    """
    try:
        user32 = ctypes.windll.user32

        # SM_XVIRTUALSCREEN = 76 (left edge of virtual screen)
        # SM_YVIRTUALSCREEN = 77 (top edge of virtual screen)
        # SM_CXVIRTUALSCREEN = 78 (width of virtual screen)
        # SM_CYVIRTUALSCREEN = 79 (height of virtual screen)
        left = user32.GetSystemMetrics(76)
        top = user32.GetSystemMetrics(77)
        width = user32.GetSystemMetrics(78)
        height = user32.GetSystemMetrics(79)

        return left, top, width, height
    except Exception:
        # Fallback to primary monitor
        return 0, 0, 1920, 1080


class ScreenshotCapture:
    """Handles screen capture for OCR."""

    def __init__(self, root=None):
        self.root = root
        self.top = None
        self.canvas = None
        self.original_image = None
        self.callback = None
        self.start_x = 0
        self.start_y = 0
        self.cur_x = 0
        self.cur_y = 0
        self.rect = None
        # Virtual screen offset for multi-monitor support
        self._vscreen_left = 0
        self._vscreen_top = 0

    def capture_region(self, callback):
        """
        Opens an overlay to select a region.
        callback(image_path): function to call with captured image path.
        Supports multi-monitor setups.
        """
        self.callback = callback

        try:
            # Capture full screen (all monitors on Windows if supported by Pillow)
            self.original_image = ImageGrab.grab(all_screens=True)
        except Exception as e:
            print(f"Screenshot error: {e}")
            if callback:
                callback(None)
            return

        # Get virtual screen bounds (all monitors combined)
        vscreen_left, vscreen_top, vscreen_width, vscreen_height = get_virtual_screen_bounds()
        self._vscreen_left = vscreen_left
        self._vscreen_top = vscreen_top

        # Create overlay window with parent for proper event loop integration
        self.top = tk.Toplevel(self.root)
        self.top.overrideredirect(True)  # Remove window decorations
        self.top.attributes('-topmost', True)
        self.top.attributes('-alpha', 0.3)  # Semi-transparent overlay
        self.top.configure(bg='black', cursor="cross")

        # Position and size to cover ALL monitors (virtual screen)
        self.top.geometry(f"{vscreen_width}x{vscreen_height}+{vscreen_left}+{vscreen_top}")
        
        # Bind events
        self.top.bind("<ButtonPress-1>", self._on_press)
        self.top.bind("<B1-Motion>", self._on_drag)
        self.top.bind("<ButtonRelease-1>", self._on_release)
        self.top.bind("<Escape>", lambda e: self._close(call_callback=True))
        
        # Create canvas for drawing selection rectangle
        self.canvas = tk.Canvas(self.top, highlightthickness=0, bg='black')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.top.focus_force()

    def _on_press(self, event):
        self.start_x = event.x_root
        self.start_y = event.y_root

        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            0, 0, 0, 0, outline='red', width=2, fill='white', stipple='gray25'
        )

    def _on_drag(self, event):
        self.cur_x = event.x_root
        self.cur_y = event.y_root
        
        # Map global coords to canvas coords
        canvas_x = self.cur_x - self.top.winfo_rootx()
        canvas_y = self.cur_y - self.top.winfo_rooty()
        start_canvas_x = self.start_x - self.top.winfo_rootx()
        start_canvas_y = self.start_y - self.top.winfo_rooty()

        self.canvas.coords(self.rect, start_canvas_x, start_canvas_y, canvas_x, canvas_y)

    def _on_release(self, event):
        if not self.original_image:
            self._close()
            return

        x1 = min(self.start_x, self.cur_x)
        y1 = min(self.start_y, self.cur_y)
        x2 = max(self.start_x, self.cur_x)
        y2 = max(self.start_y, self.cur_y)

        # Save image reference and offsets BEFORE closing (close sets original_image = None)
        image = self.original_image
        vscreen_left = self._vscreen_left
        vscreen_top = self._vscreen_top

        self._close()

        # Ensure valid size
        if (x2 - x1) < 10 or (y2 - y1) < 10:
            if self.callback:
                self.callback(None)
            return

        try:
            # Convert screen coordinates to image coordinates
            # The image from ImageGrab starts at (0,0) but screen coords start at vscreen origin
            img_x1 = x1 - vscreen_left
            img_y1 = y1 - vscreen_top
            img_x2 = x2 - vscreen_left
            img_y2 = y2 - vscreen_top

            # Crop image using adjusted coordinates
            cropped = image.crop((img_x1, img_y1, img_x2, img_y2))
            
            fd, path = tempfile.mkstemp(suffix='.png')
            os.close(fd)
            cropped.save(path)
            
            if self.callback:
                self.callback(path)
                
        except Exception as e:
            print(f"Crop failed: {e}")

    def _close(self, call_callback=False):
        if self.top:
            self.top.destroy()
        self.top = None
        self.original_image = None
        self._vscreen_left = 0
        self._vscreen_top = 0
        if call_callback and self.callback:
            self.callback(None)