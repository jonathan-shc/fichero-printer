"""Settings merge: options override the original setup data."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).parents[1] / "custom_components" / "fichero_printer"
package = ModuleType("fichero_settings_pkg")
package.__path__ = [str(ROOT)]
sys.modules.setdefault("fichero_settings_pkg", package)
for name in ("const", "settings"):
    spec = importlib.util.spec_from_file_location(f"fichero_settings_pkg.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
settings = sys.modules["fichero_settings_pkg.settings"]


def test_defaults_fill_missing_values():
    merged = settings.entry_settings(SimpleNamespace(data={"name": "x"}, options={}))
    assert merged["offset_mm"] == 0.0
    assert merged["label_length"] == 30
    assert settings.switchbot_entity(merged) is None


def test_options_override_setup_data_even_when_cleared():
    entry = SimpleNamespace(
        data={"switchbot_entity": "input_button.dummy", "label_length": 30},
        options={"switchbot_entity": "", "label_length": 40, "offset_mm": 1.0},
    )
    merged = settings.entry_settings(entry)
    assert settings.switchbot_entity(merged) is None
    assert merged["label_length"] == 40
    assert merged["offset_mm"] == 1.0


def test_existing_entries_keep_their_switchbot():
    entry = SimpleNamespace(data={"switchbot_entity": "input_button.dummy"}, options={})
    assert settings.switchbot_entity(settings.entry_settings(entry)) == "input_button.dummy"
