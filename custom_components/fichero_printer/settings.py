"""Effective printer settings: setup data overridden by the options flow."""

from __future__ import annotations

from typing import Any

from .const import (
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
)

DEFAULTS: dict[str, Any] = {
    CONF_SWITCHBOT_ENTITY: "",
    CONF_STARTUP_DELAY: DEFAULT_STARTUP_DELAY,
    CONF_LABEL_LENGTH: DEFAULT_LABEL_LENGTH,
    CONF_DENSITY: DEFAULT_DENSITY,
    CONF_POWER_OFF_ON_DISCONNECT: False,
    CONF_OFFSET: DEFAULT_OFFSET,
}


def entry_settings(entry) -> dict[str, Any]:
    """Return the settings in effect for a config entry.

    Options win over the original setup data, including an empty SwitchBot
    entity: clearing it in the options must not fall back to the entity that
    was chosen during setup.
    """
    options = getattr(entry, "options", None) or {}
    return {**DEFAULTS, **(entry.data or {}), **options}


def switchbot_entity(settings: dict[str, Any]) -> str | None:
    """The configured power-button entity, or None when the printer is switched on by hand."""
    return (settings.get(CONF_SWITCHBOT_ENTITY) or "").strip() or None
