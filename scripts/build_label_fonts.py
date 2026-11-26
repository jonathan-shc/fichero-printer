"""Regenerate the icon fonts and lookup tables bundled with the HA integration.

Usage (needs fontTools and brotli, plus the npm packages unpacked next to it):

    npm pack @mdi/font @material-symbols/font-400
    tar -xzf mdi-font-*.tgz --one-top-level=mdi
    tar -xzf material-symbols-font-400-*.tgz --one-top-level=symbols
    python scripts/build_label_fonts.py mdi/package symbols/package

Writes into custom_components/fichero_printer/fonts/:
  materialdesignicons-webfont.ttf + mdi_codepoints.json   (name -> codepoint)
  MaterialSymbolsOutlined.ttf + m3o_codepoints.json        (static FILL=0 instance)
  coverage.json   codepoint ranges of DejaVu Sans ("text") and Noto Emoji ("emoji")
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import sys

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

FONTS = Path(__file__).parents[1] / "custom_components" / "fichero_printer" / "fonts"


def ranges(codepoints):
    out: list[list[int]] = []
    for codepoint in sorted(codepoints):
        if out and codepoint == out[-1][1] + 1:
            out[-1][1] = codepoint
        else:
            out.append([codepoint, codepoint])
    return out


def main(mdi_dir: str, symbols_dir: str) -> None:
    mdi = Path(mdi_dir)
    shutil.copy(mdi / "fonts" / "materialdesignicons-webfont.ttf", FONTS)
    css = (mdi / "css" / "materialdesignicons.css").read_text()
    names = {
        match.group(1): int(match.group(2), 16)
        for match in re.finditer(r'\.mdi-([a-z0-9-]+)::before\s*\{\s*content:\s*"\\([0-9A-Fa-f]+)"', css)
    }
    (FONTS / "mdi_codepoints.json").write_text(json.dumps(dict(sorted(names.items())), separators=(",", ":")))

    font = TTFont(Path(symbols_dir) / "material-symbols-outlined.woff2")
    symbols: dict[str, int] = {}
    for codepoint, glyph in font.getBestCmap().items():
        if codepoint >= 0xE000:
            symbols.setdefault(glyph, codepoint)
    static = instancer.instantiateVariableFont(font, {"FILL": 0})
    static.flavor = None
    static.save(FONTS / "MaterialSymbolsOutlined.ttf")
    (FONTS / "m3o_codepoints.json").write_text(json.dumps(dict(sorted(symbols.items())), separators=(",", ":")))

    text = set(TTFont(FONTS / "DejaVuSans.ttf").getBestCmap())
    # Digits, '#', '*' and similar have emoji forms too; keep them as text.
    emoji = {c for c in TTFont(FONTS / "NotoEmoji-Regular.ttf").getBestCmap() if c >= 0x2000}
    (FONTS / "coverage.json").write_text(
        json.dumps({"text": ranges(text), "emoji": ranges(emoji)}, separators=(",", ":"))
    )


if __name__ == "__main__":
    main(*sys.argv[1:3])
