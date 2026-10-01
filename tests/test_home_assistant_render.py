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
