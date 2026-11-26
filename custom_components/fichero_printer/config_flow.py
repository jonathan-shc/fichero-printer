"""Config and options flow for Fichero Label Printer."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ADDRESS,
    CONF_DENSITY,
    CONF_LABEL_LENGTH,
    CONF_OFFSET,
    CONF_POWER_OFF_ON_DISCONNECT,
    CONF_STARTUP_DELAY,
    CONF_SWITCHBOT_ENTITY,
    DEFAULT_DENSITY,
    DEFAULT_LABEL_LENGTH,
    DEFAULT_OFFSET,
    DEFAULT_STARTUP_DELAY,
    DOMAIN,
    MAX_OFFSET_MM,
)
from .settings import entry_settings, switchbot_entity

# Reloads the entry after the options are saved (HA 2025.8+). Older cores fall
# back to an update listener registered in async_setup_entry.
OptionsFlowBase = getattr(config_entries, "OptionsFlowWithReload", config_entries.OptionsFlow)

_SWITCHBOT_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["switch", "button", "input_button"])
)
_DENSITY_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=["0", "1", "2"],
        mode=selector.SelectSelectorMode.LIST,
        translation_key="density",
    )
)
_OFFSET_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=-MAX_OFFSET_MM,
        max=MAX_OFFSET_MM,
        step=0.5,
        unit_of_measurement="mm",
        mode=selector.NumberSelectorMode.SLIDER,
    )
)


def _settings_schema(current: dict[str, Any]) -> dict:
    """Fields shared by setup and options, pre-filled with the current values."""
    switchbot = switchbot_entity(current)
    return {
        # Optional: without a SwitchBot the printer is switched on by hand and
        # Home Assistant connects as soon as it advertises.
        vol.Optional(
            CONF_SWITCHBOT_ENTITY,
            description={"suggested_value": switchbot} if switchbot else None,
        ): _SWITCHBOT_SELECTOR,
        vol.Required(CONF_STARTUP_DELAY, default=float(current[CONF_STARTUP_DELAY])): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=30)
        ),
        vol.Required(CONF_LABEL_LENGTH, default=int(current[CONF_LABEL_LENGTH])): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=100)
        ),
        vol.Required(CONF_DENSITY, default=str(current[CONF_DENSITY])): _DENSITY_SELECTOR,
        vol.Required(CONF_OFFSET, default=float(current[CONF_OFFSET])): _OFFSET_SELECTOR,
        vol.Required(
            CONF_POWER_OFF_ON_DISCONNECT, default=bool(current[CONF_POWER_OFF_ON_DISCONNECT])
        ): bool,
    }


def _clean(user_input: dict[str, Any]) -> dict[str, Any]:
    """Normalise form values; an empty SwitchBot field means 'none'."""
    data = dict(user_input)
    data[CONF_SWITCHBOT_ENTITY] = (data.get(CONF_SWITCHBOT_ENTITY) or "").strip()
    data[CONF_DENSITY] = int(data[CONF_DENSITY])
    data[CONF_LABEL_LENGTH] = int(data[CONF_LABEL_LENGTH])
    data[CONF_OFFSET] = round(float(data[CONF_OFFSET]) * 2) / 2
    if not data[CONF_SWITCHBOT_ENTITY]:
        # Pressing nothing on disconnect is the only meaningful choice.
        data[CONF_POWER_OFF_ON_DISCONNECT] = False
    return data


class FicheroConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a Fichero printer without requiring it to be awake."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return FicheroOptionsFlow()

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            unique_id = user_input.get(CONF_ADDRESS) or user_input[CONF_NAME]
            await self.async_set_unique_id(unique_id.lower())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=user_input[CONF_NAME], data=_clean(user_input))

        defaults = {
            CONF_SWITCHBOT_ENTITY: "",
            CONF_STARTUP_DELAY: DEFAULT_STARTUP_DELAY,
            CONF_LABEL_LENGTH: DEFAULT_LABEL_LENGTH,
            CONF_DENSITY: DEFAULT_DENSITY,
            CONF_OFFSET: DEFAULT_OFFSET,
            CONF_POWER_OFF_ON_DISCONNECT: False,
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="Fichero D11s"): str,
                vol.Optional(CONF_ADDRESS, default=""): str,
                **_settings_schema(defaults),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)


class FicheroOptionsFlow(OptionsFlowBase):
    """Change label, print and power settings after setup."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=_clean(user_input))
        current = entry_settings(self.config_entry)
        return self.async_show_form(step_id="init", data_schema=vol.Schema(_settings_schema(current)))
