"""Number entities for label settings that are tuned while printing."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfLength

from .const import CONF_LABEL_LENGTH, CONF_OFFSET, MAX_OFFSET_MM
from .entity import FicheroEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([FicheroOffsetNumber(entry), FicheroLabelLengthNumber(entry)])


class FicheroOffsetNumber(FicheroEntity, NumberEntity):
    """Shift the content along the label (positive = right in reading direction)."""

    _attr_translation_key = "offset"
    _attr_icon = "mdi:arrow-left-right"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = -MAX_OFFSET_MM
    _attr_native_max_value = MAX_OFFSET_MM
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = UnitOfLength.MILLIMETERS
    _attr_mode = NumberMode.BOX

    def __init__(self, entry) -> None:
        super().__init__(entry, CONF_OFFSET)

    @property
    def native_value(self) -> float:
        return float(self.settings[CONF_OFFSET])

    async def async_set_native_value(self, value: float) -> None:
        self._store_setting(CONF_OFFSET, round(value * 2) / 2)


class FicheroLabelLengthNumber(FicheroEntity, NumberEntity):
    """Physical label length along the paper."""

    _attr_translation_key = "label_length"
    _attr_icon = "mdi:ruler"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 10
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfLength.MILLIMETERS
    _attr_mode = NumberMode.BOX

    def __init__(self, entry) -> None:
        super().__init__(entry, CONF_LABEL_LENGTH)

    @property
    def native_value(self) -> int:
        return int(self.settings[CONF_LABEL_LENGTH])

    async def async_set_native_value(self, value: float) -> None:
        self._store_setting(CONF_LABEL_LENGTH, int(round(value)))
