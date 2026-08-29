"""Connection-status sensor for the Fichero printer."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import CONF_NAME
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([FicheroStatusSensor(entry)])


class FicheroStatusSensor(SensorEntity):
    """Expose live state and card data."""

    _attr_icon = "mdi:printer-pos"
    _attr_has_entity_name = True
    _attr_name = "Status"

    def __init__(self, entry) -> None:
        self._entry = entry
        self._manager = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_NAME],
            manufacturer="Fichero / AiYin",
            model="D11s",
        )

    @property
    def native_value(self):
        return self._manager.status

    @property
    def available(self) -> bool:
        return True

    @property
    def extra_state_attributes(self):
        return {
            "connected": self._manager.connected,
            "favorites": self._manager.favorites,
            "config_entry_id": self._entry.entry_id,
            "label_length_mm": self._entry.data["label_length"],
            "last_error": self._manager.last_error,
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._manager.add_listener(self.async_write_ha_state))
