"""Dependency-light label renderer, kept separate for unit testing."""

from PIL import Image, ImageDraw, ImageFont

PRINTHEAD_PX = 96


def render_text_raster(text: str, label_rows: int) -> bytes:
    """Fit text on one line at the largest possible size."""
    # Treat pasted line breaks and repeated whitespace as ordinary spaces. A
    # label should only become smaller horizontally, never wrap vertically.
    text = " ".join(text.split())
    if not text:
        raise ValueError("Text cannot be empty")

    canvas = Image.new("1", (label_rows, PRINTHEAD_PX), 1)
    draw = ImageDraw.Draw(canvas)
    best = None
    low, high = 6, min(96, label_rows)
    while low <= high:
        size = (low + high) // 2
        font = ImageFont.load_default(size=size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= label_rows - 4 and bbox[3] - bbox[1] <= PRINTHEAD_PX - 4:
            best = (font, bbox)
            low = size + 1
        else:
            high = size - 1
    if best is None:
        raise ValueError("Text cannot fit on this label")
    font, bbox = best
    x = (label_rows - (bbox[2] - bbox[0])) // 2 - bbox[0]
    y = (PRINTHEAD_PX - (bbox[3] - bbox[1])) // 2 - bbox[1]
    draw.text((x, y), text, font=font, fill=0)
    # Printer raster is 96 pixels wide and one row per dot along label length.
    rotated = canvas.rotate(90, expand=True)
    return bytes(byte ^ 0xFF for byte in rotated.tobytes())
