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


def test_long_text_wraps_and_still_fits():
    raster = render.render_text_raster("A considerably longer label name that needs wrapping", 240)
    assert len(raster) == 240 * 12
    assert any(raster)


def test_date_label_fits():
    raster = render.render_text_raster("29-08-2026", 240)
    assert len(raster) == 240 * 12
