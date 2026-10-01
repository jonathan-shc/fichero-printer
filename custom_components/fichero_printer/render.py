"""Dependency-light label renderer, kept separate for unit testing."""

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PRINTHEAD_PX = 96
# Blank dots kept clear at both ends of the label (8 dots = 1 mm). Paper
# position varies by about 1 mm between labels, so a smaller margin can print
# the first character before the label starts.
EDGE_MARGIN_PX = 16


# Smallest font a typed line may shrink to in multiline mode before it is
# wrapped on spaces instead.
MIN_MULTILINE_PX = 16
LINE_SPACING_PX = 2
# DejaVu Sans covers Latin-1 and more; Pillow's built-in font is ASCII-only and
# prints accented characters as empty boxes. See fonts/LICENSE.
FONT_PATH = Path(__file__).parent / "fonts" / "DejaVuSans.ttf"


@lru_cache(maxsize=None)
def _font(size: int):
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except OSError:
        return ImageFont.load_default(size=size)


def _wrap_line(draw, line, font, max_width):
    """Greedily wrap one line on spaces; over-long single words stay whole."""
    lines: list[str] = []
    current = ""
    for word in line.split():
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_lines(draw, lines, label_rows, min_size, wrap):
    """Return the largest (font, lines, bboxes) that fits, or None."""
    max_width = label_rows - 2 * EDGE_MARGIN_PX
    max_height = PRINTHEAD_PX - 4
    best = None
    low, high = min_size, min(96, label_rows)
    while low <= high:
        size = (low + high) // 2
        font = _font(size)
        fitted = [w for line in lines for w in (_wrap_line(draw, line, font, max_width) if wrap else [line])]
        bboxes = [draw.textbbox((0, 0), line, font=font) for line in fitted]
        total = sum(b[3] - b[1] for b in bboxes) + LINE_SPACING_PX * (len(fitted) - 1)
        if all(b[2] - b[0] <= max_width for b in bboxes) and total <= max_height:
            best = (font, fitted, bboxes)
            low = size + 1
        else:
            high = size - 1
    return best


def render_text_raster(text: str, label_rows: int, multiline: bool = False) -> bytes:
    """Fit text at the largest possible size.

    By default everything is one line: line breaks become spaces so a label
    only shrinks horizontally. With ``multiline`` typed line breaks are kept
    and a line is only wrapped on spaces if it would otherwise get too small.
    """
    if multiline:
        lines = [" ".join(line.split()) for line in text.splitlines()]
        lines = [line for line in lines if line]
    else:
        lines = [" ".join(text.split())]
        lines = [line for line in lines if line]
    if not lines:
        raise ValueError("Text cannot be empty")

    canvas = Image.new("1", (label_rows, PRINTHEAD_PX), 1)
    draw = ImageDraw.Draw(canvas)
    best = None
    if multiline:
        best = _fit_lines(draw, lines, label_rows, MIN_MULTILINE_PX, wrap=False)
        if best is None:
            best = _fit_lines(draw, lines, label_rows, 6, wrap=True)
    else:
        best = _fit_lines(draw, lines, label_rows, 6, wrap=False)
    if best is None:
        raise ValueError("Text cannot fit on this label")

    font, fitted, bboxes = best
    total = sum(b[3] - b[1] for b in bboxes) + LINE_SPACING_PX * (len(fitted) - 1)
    top = (PRINTHEAD_PX - total) // 2
    for line, bbox in zip(fitted, bboxes):
        x = max(EDGE_MARGIN_PX, (label_rows - (bbox[2] - bbox[0])) // 2) - bbox[0]
        draw.text((x, top - bbox[1]), line, font=font, fill=0)
        top += bbox[3] - bbox[1] + LINE_SPACING_PX
    # Printer raster is 96 pixels wide and one row per dot along label length.
    rotated = canvas.rotate(90, expand=True)
    return bytes(byte ^ 0xFF for byte in rotated.tobytes())
