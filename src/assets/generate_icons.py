"""Generate icon images for UI elements."""
from PIL import Image, ImageDraw


def create_add_button_icon(size=56, color='#888888', bg_color=None):
    """Create a dashed circle with plus sign icon.

    Args:
        size: Image size (square)
        color: Line color (hex string)
        bg_color: Background color (None for transparent)

    Returns:
        PIL Image object
    """
    # Create image with transparency
    if bg_color:
        img = Image.new('RGBA', (size, size), bg_color)
    else:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))

    draw = ImageDraw.Draw(img)

    center = size // 2
    radius = (size // 2) - 4  # Leave some margin

    # Convert hex color to RGB
    if color.startswith('#'):
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        rgb_color = (r, g, b, 255)
    else:
        rgb_color = (136, 136, 136, 255)  # Default gray

    # Draw dashed circle using small arcs
    num_dashes = 24
    dash_angle = 360 / num_dashes
    gap_ratio = 0.4  # Gap takes 40% of each segment

    for i in range(num_dashes):
        start_angle = i * dash_angle
        end_angle = start_angle + dash_angle * (1 - gap_ratio)

        # Draw arc segment
        bbox = [center - radius, center - radius, center + radius, center + radius]
        draw.arc(bbox, start=start_angle, end=end_angle, fill=rgb_color, width=2)

    # Draw plus sign
    plus_len = size // 5
    line_width = 2

    # Horizontal line
    draw.line(
        [(center - plus_len, center), (center + plus_len, center)],
        fill=rgb_color,
        width=line_width
    )

    # Vertical line
    draw.line(
        [(center, center - plus_len), (center, center + plus_len)],
        fill=rgb_color,
        width=line_width
    )

    return img


def generate_all_icons():
    """Generate all icon variations."""
    import os

    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Generate add button icons
    sizes_and_names = [
        (56, 'add_btn_gray.png', '#888888'),       # Empty state
        (56, 'add_btn_blue.png', '#0d6efd'),       # Has attachments
        (56, 'add_btn_light.png', '#aaaaaa'),      # Hover (empty)
        (56, 'add_btn_light_blue.png', '#5a9fd4'), # Drag-drop hover
    ]

    for size, name, color in sizes_and_names:
        img = create_add_button_icon(size=size, color=color)
        path = os.path.join(script_dir, name)
        img.save(path, 'PNG')
        print(f"Created: {path}")


if __name__ == '__main__':
    generate_all_icons()
