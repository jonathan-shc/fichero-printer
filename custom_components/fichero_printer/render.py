"""Dependency-light label renderer, kept separate for unit testing."""

import textwrap

from PIL import Image, ImageDraw, ImageFont

PRINTHEAD_PX = 96


def render_text_raster(text: str, label_rows: int) -> bytes:
    """Fit wrapped text to the full physical label and return printer raster."""
    canvas = Image.new("1", (label_rows, PRINTHEAD_PX), 1)
    draw = ImageDraw.Draw(canvas)
    best = None
    low, high = 6, min(96, label_rows)
    while low <= high:
        size = (low + high) // 2
        font = ImageFont.load_default(size=size)
        avg = max(1, int(draw.textlength("M", font=font)))
        width_chars = max(1, label_rows // avg)
        lines: list[str] = []
        for paragraph in text.splitlines() or [text]:
            lines.extend(textwrap.wrap(paragraph, width=width_chars, break_long_words=True) or [""])
        rendered = "\n".join(lines)
        spacing = max(1, size // 6)
        bbox = draw.multiline_textbbox((0, 0), rendered, font=font, spacing=spacing, align="center")
        if bbox[2] - bbox[0] <= label_rows - 4 and bbox[3] - bbox[1] <= PRINTHEAD_PX - 4:
            best = (font, lines, bbox, spacing)
            low = size + 1
        else:
            high = size - 1
    if best is None:
        raise ValueError("Text cannot fit on this label")
    font, lines, bbox, spacing = best
    rendered = "\n".join(lines)
    x = (label_rows - (bbox[2] - bbox[0])) // 2 - bbox[0]
    y = (PRINTHEAD_PX - (bbox[3] - bbox[1])) // 2 - bbox[1]
    draw.multiline_text((x, y), rendered, font=font, fill=0, spacing=spacing, align="center")
    # Printer raster is 96 pixels wide and one row per dot along label length.
    rotated = canvas.rotate(90, expand=True)
    return bytes(byte ^ 0xFF for byte in rotated.tobytes())
