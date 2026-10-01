"""Tests for Home Assistant label auto-fitting."""

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "custom_components" / "fichero_printer" / "render.py"
SPEC = importlib.util.spec_from_file_location("fichero_render", MODULE_PATH)
render = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render)


def test_short_text_fills_standard_label():
    raster = render.render_text_raster("Kitchen", 240)
    assert len(raster) == 240 * 12
    assert any(raster)


def test_long_text_stays_on_one_line_and_still_fits(monkeypatch):
    draw_text = render.ImageDraw.ImageDraw.text
    calls = []

    def record_text(self, position, text, *args, **kwargs):
        calls.append(text)
        return draw_text(self, position, text, *args, **kwargs)

    monkeypatch.setattr(render.ImageDraw.ImageDraw, "text", record_text)
    text = "A considerably longer label name"
    raster = render.render_text_raster(text, 240)
    assert len(raster) == 240 * 12
    assert any(raster)
    assert calls == [text]


def test_line_breaks_are_rendered_as_spaces(monkeypatch):
    draw_text = render.ImageDraw.ImageDraw.text
    calls = []

    def record_text(self, position, text, *args, **kwargs):
        calls.append(text)
        return draw_text(self, position, text, *args, **kwargs)

    monkeypatch.setattr(render.ImageDraw.ImageDraw, "text", record_text)
    render.render_text_raster("Best before\nFriday", 240)
    assert calls == ["Best before Friday"]


def test_date_label_fits():
    raster = render.render_text_raster("29-08-2026", 240)
    assert len(raster) == 240 * 12


def test_text_keeps_clear_of_label_ends():
    # Rows are dots along the label length; each row is 12 bytes wide.
    raster = render.render_text_raster("A considerably longer label name", 240)
    rows = [raster[i * 12:(i + 1) * 12] for i in range(240)]
    inked = [i for i, row in enumerate(rows) if any(row)]
    assert inked[0] >= render.EDGE_MARGIN_PX
    assert inked[-1] <= 240 - 1 - render.EDGE_MARGIN_PX


def _inked_rows(raster, label_rows=240):
    rows = [raster[i * 12:(i + 1) * 12] for i in range(label_rows)]
    return [i for i, row in enumerate(rows) if any(row)]


def _ink_columns(raster, label_rows=240):
    """Printhead positions (0-95) that carry ink, across the whole label."""
    cols = set()
    for i in range(label_rows):
        row = int.from_bytes(raster[i * 12:(i + 1) * 12], "big")
        for bit in range(96):
            if row >> (95 - bit) & 1:
                cols.add(bit)
    return cols


def test_default_ignores_line_breaks():
    assert render.render_text_raster("Basilicum\n2026-09", 240) == render.render_text_raster("Basilicum 2026-09", 240)


def test_multiline_keeps_typed_breaks_and_is_larger():
    single = render.render_text_raster("Basilicum 2026-09", 240)
    multi = render.render_text_raster("Basilicum\n2026-09", 240, multiline=True)
    assert len(multi) == 240 * 12
    assert multi != single
    # Two stacked lines use more of the printhead height than one small line.
    assert len(_ink_columns(multi)) > len(_ink_columns(single))


def test_multiline_keeps_clear_of_label_ends():
    raster = render.render_text_raster("A considerably longer\nlabel name", 240, multiline=True)
    inked = _inked_rows(raster)
    assert inked[0] >= render.EDGE_MARGIN_PX
    assert inked[-1] <= 240 - 1 - render.EDGE_MARGIN_PX


def test_multiline_wraps_only_when_line_would_be_tiny():
    long_line = "one very long typed line that cannot stay readable on a single row"
    raster = render.render_text_raster(long_line, 240, multiline=True)
    assert len(raster) == 240 * 12 and any(raster)


def test_multiline_empty_raises():
    import pytest
    with pytest.raises(ValueError):
        render.render_text_raster("\n  \n", 240, multiline=True)


def test_accented_characters_are_not_missing_glyph_boxes():
    from PIL import Image, ImageDraw

    def glyph(char):
        image = Image.new("1", (80, 80), 1)
        ImageDraw.Draw(image).text((5, 5), char, font=render._font(40), fill=0)
        return image.tobytes()

    notdef = glyph("\ue000")  # private-use code point: the font's missing glyph
    for char in "éëüñç€":
        assert glyph(char) != notdef, char
    assert render.FONT_PATH.exists()
    assert any(render.render_text_raster("Crème brûlée €5", 240))
