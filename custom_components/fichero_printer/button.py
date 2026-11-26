"""Maintenance button: re-learn the label gap."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory

from .entity import FicheroEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([FicheroCalibrateGapButton(entry)])


class FicheroCalibrateGapButton(FicheroEntity, ButtonEntity):
    """Recover a printer that feeds blank labels after losing gap detection."""

    _attr_translation_key = "calibrate_gap"
    _attr_icon = "mdi:tape-measure"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, entry) -> None:
        super().__init__(entry, "calibrate_gap")

    async def async_press(self) -> None:
        await self._manager.async_calibrate_gap()
