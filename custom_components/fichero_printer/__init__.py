"""Home Assistant integration for the Fichero/D11s label printer."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    CARD_URL,
    DOMAIN,
    PLATFORMS,
    SERVICE_CONNECT,
    SERVICE_DELETE_FAVORITE,
    SERVICE_DISCONNECT,
    SERVICE_PRINT,
    SERVICE_SAVE_FAVORITE,
)
from .manager import FicheroManager

SERVICE_ENTRY_SCHEMA = vol.Schema({vol.Required("config_entry_id"): cv.string})
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
SERVICE_PRINT_SCHEMA = SERVICE_ENTRY_SCHEMA.extend(
    {vol.Required("text"): cv.string, vol.Optional("copies", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=100))}
)
SERVICE_FAVORITE_SCHEMA = SERVICE_ENTRY_SCHEMA.extend({vol.Required("text"): cv.string})


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Register services and the bundled dashboard card once."""
    frontend_file = Path(__file__).parent / "frontend" / "fichero-printer-card.js"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(frontend_file), cache_headers=False)]
    )
    add_extra_js_url(hass, CARD_URL)

    def manager_for(call: ServiceCall) -> FicheroManager:
        entry = hass.config_entries.async_get_entry(call.data["config_entry_id"])
        if entry is None or entry.domain != DOMAIN or entry.runtime_data is None:
            raise HomeAssistantError("Fichero printer configuration is not loaded")
        return entry.runtime_data

    async def handle_connect(call: ServiceCall) -> None:
        await manager_for(call).async_connect()

    async def handle_disconnect(call: ServiceCall) -> None:
        await manager_for(call).async_disconnect()

    async def handle_print(call: ServiceCall) -> None:
        await manager_for(call).async_print(call.data["text"], call.data["copies"])

    async def handle_save(call: ServiceCall) -> None:
        await manager_for(call).async_save_favorite(call.data["text"])

    async def handle_delete(call: ServiceCall) -> None:
        await manager_for(call).async_delete_favorite(call.data["text"])

    hass.services.async_register(DOMAIN, SERVICE_CONNECT, handle_connect, schema=SERVICE_ENTRY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DISCONNECT, handle_disconnect, schema=SERVICE_ENTRY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_PRINT, handle_print, schema=SERVICE_PRINT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SAVE_FAVORITE, handle_save, schema=SERVICE_FAVORITE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE_FAVORITE, handle_delete, schema=SERVICE_FAVORITE_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one configured printer."""
    manager = FicheroManager(hass, entry)
    await manager.async_load()
    entry.runtime_data = manager
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await manager.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Disconnect and unload one printer."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.async_stop()
    await entry.runtime_data.async_disconnect(power_off=False)
    return True
