"""Shared base for the printer's entities."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_NAME
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .settings import entry_settings


class FicheroEntity(Entity):
    """An entity of one configured printer."""

    _attr_has_entity_name = True

    def __init__(self, entry, key: str) -> None:
        self._entry = entry
        self._manager = entry.runtime_data
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_NAME],
            manufacturer="Fichero / AiYin",
            model="D11s",
        )

    @property
    def settings(self) -> dict[str, Any]:
        return entry_settings(self._entry)

    def _store_setting(self, key: str, value: Any) -> None:
        """Save one setting as an option; it applies to the next print.

        The entry is not reloaded (unlike the options dialog), so an open
        Bluetooth session stays connected.
        """
        self.hass.config_entries.async_update_entry(
            self._entry, options={**self._entry.options, key: value}
        )
        self._manager.notify_settings_changed()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._manager.add_listener(self.async_write_ha_state))
