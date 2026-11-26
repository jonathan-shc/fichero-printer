"""Dependency-light label renderer, kept separate for unit testing.

Label text may contain inline tokens:

* ``[mdi:fridge]`` / ``[m3o:kitchen]`` - a Material Design Icon or a
  Material Symbols (outlined) icon, drawn inline like a character.
* ``[qr:https://example.com]`` - a QR code.
* ``[barcode:4006381333931]`` - a Code 128 barcode with its text underneath.

Emoji are printed with the bundled Noto Emoji font. QR codes and barcodes are
placed beside the text: tokens before the first text go left, all others go
right. Everything is fitted to the label at the largest possible size.
"""

from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache
import io
import json
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont

try:  # Package-relative when loaded by Home Assistant, plain for unit tests.
    from .barcode import code128_modules
except ImportError:  # pragma: no cover - exercised by the standalone tests
    import importlib.util as _util

    _spec = _util.spec_from_file_location(
        "fichero_barcode", Path(__file__).with_name("barcode.py")
    )
    _barcode = _util.module_from_spec(_spec)
    _spec.loader.exec_module(_barcode)
    code128_modules = _barcode.code128_modules

PRINTHEAD_PX = 96
DOTS_PER_MM = 8
# Blank dots kept clear at both ends of the label (8 dots = 1 mm). Paper
# position varies by about 1 mm between labels, so a smaller margin can print
# the first character before the label starts.
EDGE_MARGIN_PX = 16
# Usable height across the printhead.
MAX_HEIGHT_PX = PRINTHEAD_PX - 4
# Space between a QR code/barcode and the text beside it.
BLOCK_GAP_PX = 8
# Narrowest room worth leaving for text next to a code.
MIN_TEXT_WIDTH_PX = 24

# Smallest font a typed line may shrink to in multiline mode before it is
# wrapped on spaces instead.
MIN_MULTILINE_PX = 16
LINE_SPACING_PX = 2
MAX_TEXT_LENGTH = 500

FONT_DIR = Path(__file__).parent / "fonts"
# DejaVu Sans covers Latin-1 and more; Pillow's built-in font is ASCII-only and
# prints accented characters as empty boxes. See fonts/LICENSE.
FONT_PATH = FONT_DIR / "DejaVuSans.ttf"
EMOJI_FONT_PATH = FONT_DIR / "NotoEmoji-Regular.ttf"
ICON_FONTS = {
    "mdi": (FONT_DIR / "materialdesignicons-webfont.ttf", FONT_DIR / "mdi_codepoints.json"),
    "m3o": (FONT_DIR / "MaterialSymbolsOutlined.ttf", FONT_DIR / "m3o_codepoints.json"),
}
# Icons are drawn a little larger than the text so they read as symbols.
ICON_SCALE = 1.15
EMOJI_SCALE = 0.95

TOKEN_RE = re.compile(r"\[\s*(mdi|m3o|qr|barcode)\s*:\s*([^\]]*?)\s*\]", re.IGNORECASE)
# Inline icons are carried through wrapping as characters from Supplementary
# Private Use Area-A, which no bundled text font uses.
_ICON_BASE = 0xF0000
_JOINERS = {0x200D, 0xFE0F, 0xFE0E}


@lru_cache(maxsize=None)
def _font(size: int):
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except OSError:
        return ImageFont.load_default(size=size)


@lru_cache(maxsize=None)
def _emoji_font(size: int):
    return ImageFont.truetype(str(EMOJI_FONT_PATH), max(1, round(size * EMOJI_SCALE)))


@lru_cache(maxsize=None)
def _icon_font(kind: str, size: int):
    return ImageFont.truetype(str(ICON_FONTS[kind][0]), max(1, round(size * ICON_SCALE)))


@lru_cache(maxsize=None)
def _icon_codepoints(kind: str) -> dict[str, int]:
    return json.loads(ICON_FONTS[kind][1].read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _coverage():
    data = json.loads((FONT_DIR / "coverage.json").read_text(encoding="utf-8"))
    return {key: ([r[0] for r in ranges], [r[1] for r in ranges]) for key, ranges in data.items()}


def _covers(key: str, codepoint: int) -> bool:
    starts, ends = _coverage()[key]
    index = bisect_right(starts, codepoint) - 1
    return index >= 0 and codepoint <= ends[index]


def icon_codepoint(kind: str, name: str) -> int:
    """Look up an icon by its Home Assistant name, e.g. ``fridge-outline``."""
    kind = kind.lower()
    names = _icon_codepoints(kind)
    key = name.strip().lower()
    if kind == "m3o":
        key = key.replace("-", "_")
    if key not in names:
        raise ValueError(f"Unknown icon: {kind}:{name.strip()}")
    return names[key]


class _Icons:
    """Map inline icons to private-use placeholder characters."""

    def __init__(self) -> None:
        self.by_char: dict[str, tuple[str, int]] = {}

    def placeholder(self, kind: str, name: str) -> str:
        entry = (kind.lower(), icon_codepoint(kind, name))
        for char, known in self.by_char.items():
            if known == entry:
                return char
        char = chr(_ICON_BASE + len(self.by_char))
        self.by_char[char] = entry
        return char


def _parse(text: str):
    """Split text into (leading codes, text with icon placeholders, trailing codes)."""
    icons = _Icons()
    leading: list[tuple[str, str]] = []
    trailing: list[tuple[str, str]] = []
    parts: list[str] = []
    position = 0
    for match in TOKEN_RE.finditer(text):
        parts.append(text[position : match.start()])
        position = match.end()
        kind, value = match.group(1).lower(), match.group(2)
        if kind in ("mdi", "m3o"):
            parts.append(icons.placeholder(kind, value))
            continue
        if not value:
            raise ValueError(f"{kind} content cannot be empty")
        seen_text = any(part.strip() for part in parts)
        (trailing if seen_text else leading).append((kind, value))
    parts.append(text[position:])
    return leading, "".join(parts), trailing, icons


def _runs(line: str, icons: _Icons):
    """Group a line into runs of ("text"|"emoji", str) and ("icon", kind, cp)."""
    runs: list[tuple] = []
    chars = list(line)
    for i, char in enumerate(chars):
        codepoint = ord(char)
        if char in icons.by_char:
            runs.append(("icon", *icons.by_char[char]))
            continue
        if codepoint in _JOINERS:
            if runs and runs[-1][0] == "emoji":
                runs[-1] = ("emoji", runs[-1][1] + char)
            continue
        wants_emoji = i + 1 < len(chars) and ord(chars[i + 1]) == 0xFE0F
        if _covers("emoji", codepoint) and (wants_emoji or not _covers("text", codepoint)):
            kind = "emoji"
        else:
            kind = "text"
        if runs and runs[-1][0] == kind and kind != "icon":
            runs[-1] = (kind, runs[-1][1] + char)
        else:
            runs.append((kind, char))
    return runs


class _Line:
    """One laid-out line: draw operations relative to a baseline at y=0."""

    def __init__(self, line: str, icons: _Icons, size: int) -> None:
        font = _font(size)
        cap = font.getbbox("H", anchor="ls")
        middle = (cap[1] + cap[3]) / 2
        self.ops: list[tuple] = []
        boxes = []
        x = 0.0
        for run in _runs(line, icons):
            if run[0] == "icon":
                run_font, string = _icon_font(run[1], size), chr(run[2])
            elif run[0] == "emoji":
                run_font, string = _emoji_font(size), run[1]
            else:
                run_font, string = font, run[1]
            box = run_font.getbbox(string, anchor="ls")
            # Symbols are centred on the capital letters, text sits on the baseline.
            dy = 0 if run[0] == "text" else round(middle - (box[1] + box[3]) / 2)
            if box[2] > box[0]:
                boxes.append((x + box[0], box[1] + dy, x + box[2], box[3] + dy))
            self.ops.append((x, dy, run_font, string, run[0] == "text"))
            x += run_font.getlength(string)
        if boxes:
            self.box = (
                min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes),
            )
        else:
            self.box = (0, 0, 0, 0)

    @property
    def width(self) -> float:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> float:
        return self.box[3] - self.box[1]

    def draw(self, draw: ImageDraw.ImageDraw, left: float, top: float) -> None:
        """Draw with the ink box's top-left corner at (left, top)."""
        origin_x, baseline = left - self.box[0], top - self.box[1]
        for x, dy, font, string, is_text in self.ops:
            if is_text and not string.strip():
                continue
            draw.text((round(origin_x + x), round(baseline + dy)), string, font=font, fill=0, anchor="ls")


def _wrap_line(line: str, icons: _Icons, size: int, max_width: int) -> list[str]:
    """Greedily wrap one line on spaces; over-long single words stay whole."""
    lines: list[str] = []
    current = ""
    for word in line.split():
        candidate = f"{current} {word}".strip()
        if not current or _Line(candidate, icons, size).width <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_lines(lines, icons, max_width, min_size, wrap, max_height=MAX_HEIGHT_PX):
    """Return the largest list of laid-out lines that fits, or None."""
    best = None
    low, high = min_size, PRINTHEAD_PX
    while low <= high:
        size = (low + high) // 2
        fitted = [w for line in lines for w in (_wrap_line(line, icons, size, max_width) if wrap else [line])]
        laid_out = [_Line(line, icons, size) for line in fitted]
        total = sum(line.height for line in laid_out) + LINE_SPACING_PX * (len(laid_out) - 1)
        if all(line.width <= max_width for line in laid_out) and total <= max_height:
            best = laid_out
            low = size + 1
        else:
            high = size - 1
    return best


def _qr_image(data: str) -> Image.Image:
    try:
        import segno
    except ImportError as err:  # pragma: no cover - declared in the manifest
        raise ValueError("QR codes need the 'segno' package") from err
    try:
        code = segno.make(data, error="m", micro=False, boost_error=True)
    except Exception as err:  # segno raises its own DataOverflowError
        raise ValueError(f"QR content cannot be encoded: {err}") from err
    matrix = code.matrix
    modules = len(matrix)
    scale = min(4, MAX_HEIGHT_PX // modules)
    if scale < 2:
        raise ValueError("QR content is too long for this label")
    image = Image.new("1", (modules * scale, modules * scale), 1)
    draw = ImageDraw.Draw(image)
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                draw.rectangle(
                    (x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1), fill=0
                )
    return image


def _barcode_image(data: str, max_width: int) -> Image.Image:
    modules = code128_modules(data)
    quiet = 6
    module_px = min(3, max_width // (len(modules) + 2 * quiet))
    if module_px < 1:
        raise ValueError("Barcode content is too long for this label")
    width = (len(modules) + 2 * quiet) * module_px
    caption = None
    for size in range(16, 7, -1):
        font = _font(size)
        if font.getlength(data) <= width:
            caption = font
            break
    caption_height = 0
    if caption is not None:
        # Measured against the descender line the caption is drawn on.
        caption_height = -caption.getbbox(data, anchor="md")[1] + 2
    image = Image.new("1", (width, MAX_HEIGHT_PX), 1)
    draw = ImageDraw.Draw(image)
    bar_bottom = MAX_HEIGHT_PX - caption_height - 1
    for index, bar in enumerate(modules):
        if bar:
            x = (quiet + index) * module_px
            draw.rectangle((x, 0, x + module_px - 1, bar_bottom), fill=0)
    if caption is not None:
        draw.text((width / 2, MAX_HEIGHT_PX - 1), data, font=caption, fill=0, anchor="md")
    return image


def _code_image(kind: str, value: str, max_width: int) -> Image.Image:
    return _qr_image(value) if kind == "qr" else _barcode_image(value, max_width)


def render_label(text: str, label_rows: int, multiline: bool = False) -> Image.Image:
    """Render the label as it is read: ``label_rows`` wide, printhead high.

    By default everything is one line: line breaks become spaces so a label
    only shrinks horizontally. With ``multiline`` typed line breaks are kept
    and a line is only wrapped on spaces if it would otherwise get too small.
    """
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"Label text is limited to {MAX_TEXT_LENGTH} characters")
    leading, body, trailing, icons = _parse(text)
    if multiline:
        lines = [" ".join(line.split()) for line in body.splitlines()]
    else:
        lines = [" ".join(body.split())]
    lines = [line for line in lines if line]
    if not lines and not leading and not trailing:
        raise ValueError("Text cannot be empty")

    available = label_rows - 2 * EDGE_MARGIN_PX
    codes = leading + trailing
    # Codes beside text may only take part of the label.
    code_budget = available - (MIN_TEXT_WIDTH_PX + BLOCK_GAP_PX) * bool(lines)
    images = []
    for kind, value in codes:
        share = max(1, code_budget // len(codes) - BLOCK_GAP_PX * (len(codes) - 1))
        images.append(_code_image(kind, value, share))
    blocks_width = sum(image.width for image in images) + BLOCK_GAP_PX * len(images)
    if not lines:
        blocks_width -= BLOCK_GAP_PX
    text_width = available - blocks_width
    if lines and text_width < MIN_TEXT_WIDTH_PX or text_width < 0:
        raise ValueError("Text cannot fit on this label")

    laid_out: list[_Line] = []
    if lines:
        best = None
        if multiline:
            best = _fit_lines(lines, icons, text_width, MIN_MULTILINE_PX, wrap=False)
            if best is None:
                best = _fit_lines(lines, icons, text_width, 6, wrap=True)
        else:
            best = _fit_lines(lines, icons, text_width, 6, wrap=False)
        if best is None:
            raise ValueError("Text cannot fit on this label")
        laid_out = best

    canvas = Image.new("1", (label_rows, PRINTHEAD_PX), 1)
    draw = ImageDraw.Draw(canvas)
    block_text_width = max((line.width for line in laid_out), default=0)
    total = blocks_width + block_text_width
    x = max(EDGE_MARGIN_PX, (label_rows - total) // 2)
    for image in images[: len(leading)]:
        canvas.paste(image, (round(x), (PRINTHEAD_PX - image.height) // 2))
        x += image.width + BLOCK_GAP_PX
    if laid_out:
        height = sum(line.height for line in laid_out) + LINE_SPACING_PX * (len(laid_out) - 1)
        top = (PRINTHEAD_PX - height) // 2
        for line in laid_out:
            line.draw(draw, x + (block_text_width - line.width) // 2, top)
            top += line.height + LINE_SPACING_PX
        x += block_text_width + BLOCK_GAP_PX
    for image in images[len(leading) :]:
        canvas.paste(image, (round(x), (PRINTHEAD_PX - image.height) // 2))
        x += image.width + BLOCK_GAP_PX
    return canvas


def image_to_raster(image: Image.Image, offset_px: int = 0) -> bytes:
    """Convert a rendered label to printer rows, shifted along the label.

    A positive offset moves the content towards the end of the text (to the
    right when reading the label) to compensate a printer that starts early.
    """
    if offset_px:
        shifted = Image.new("1", image.size, 1)
        shifted.paste(image, (offset_px, 0))
        image = shifted
    # Printer raster is 96 pixels wide and one row per dot along label length.
    rotated = image.rotate(90, expand=True)
    return bytes(byte ^ 0xFF for byte in rotated.tobytes())


def render_text_raster(
    text: str, label_rows: int, multiline: bool = False, offset_px: int = 0
) -> bytes:
    """Fit text (with optional icons and codes) and return printer rows."""
    return image_to_raster(render_label(text, label_rows, multiline), offset_px)


def render_preview_png(text: str, label_rows: int, multiline: bool = False, scale: int = 2) -> bytes:
    """Render a PNG preview of the label as it will be read."""
    image = render_label(text, label_rows, multiline).convert("L")
    if scale > 1:
        image = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
