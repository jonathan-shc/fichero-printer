"""Print density as a select entity."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory

from .const import CONF_DENSITY
from .entity import FicheroEntity

DENSITIES = ["light", "medium", "dark"]


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([FicheroDensitySelect(entry)])


class FicheroDensitySelect(FicheroEntity, SelectEntity):
    """How dark the printer burns the label."""

    _attr_translation_key = "density"
    _attr_icon = "mdi:contrast-box"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = DENSITIES

    def __init__(self, entry) -> None:
        super().__init__(entry, CONF_DENSITY)

    @property
    def current_option(self) -> str:
        return DENSITIES[min(2, max(0, int(self.settings[CONF_DENSITY])))]

    async def async_select_option(self, option: str) -> None:
        self._store_setting(CONF_DENSITY, DENSITIES.index(option))
