"""Persistent BLE session and label rendering for Fichero/D11s printers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import logging

from bleak import BleakClient

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store

from .const import (
    CONF_ADDRESS,
    CONF_DENSITY,
    CONF_LABEL_LENGTH,
    CONF_POWER_OFF_ON_DISCONNECT,
    CONF_STARTUP_DELAY,
    CONF_SWITCHBOT_ENTITY,
)
from .render import render_text_raster

_LOGGER = logging.getLogger(__name__)
WRITE_UUID = "00002af1-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "00002af0-0000-1000-8000-00805f9b34fb"
PRINTHEAD_PX = 96
BYTES_PER_ROW = 12
DOTS_PER_MM = 8
NAME_PREFIXES = ("FICHERO", "D11s_")


class FicheroManager:
    """Own one printer session and its persisted favorites."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self.client: BleakClient | None = None
        self._buffer = bytearray()
        self._response = asyncio.Event()
        self._operation_lock = asyncio.Lock()
        self._listeners: set[Callable[[], None]] = set()
        self._store = Store(hass, 1, f"fichero_printer.{entry.entry_id}")
        self.favorites: list[str] = []
        self.status = "disconnected"
        self.last_error: str | None = None

    @property
    def connected(self) -> bool:
        return self.client is not None and self.client.is_connected

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.favorites = list(data.get("favorites", []))

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def _notify(self) -> None:
        for listener in self._listeners:
            listener()

    def _set_status(self, status: str, error: str | None = None) -> None:
        self.status = status
        self.last_error = error
        self._notify()

    async def _press_switchbot(self) -> None:
        entity_id = self.entry.data[CONF_SWITCHBOT_ENTITY]
        domain = entity_id.split(".", 1)[0]
        if self.hass.states.get(entity_id) is None:
            raise HomeAssistantError(
                f"Configured SwitchBot entity {entity_id} does not exist"
            )
        service = "press" if domain in ("button", "input_button") else "turn_on"
        await self.hass.services.async_call(
            domain,
            service,
            {"entity_id": entity_id},
            blocking=True,
        )

    async def async_connect(self) -> None:
        async with self._operation_lock:
            if self.connected:
                return
            self._set_status("powering_on")
            try:
                await self._press_switchbot()
                await asyncio.sleep(self.entry.data[CONF_STARTUP_DELAY])
                self._set_status("connecting")
                target = await self._resolve_printer()
                client = BleakClient(target, disconnected_callback=self._on_disconnect)
                await client.connect(timeout=15)
                await client.start_notify(NOTIFY_UUID, self._on_notify)
                self.client = client
                self._set_status("connected")
            except Exception as err:
                self.client = None
                self._set_status("error", str(err))
                raise HomeAssistantError(f"Could not connect to the printer: {err}") from err

    async def _resolve_printer(self):
        """Wait for HA discovery, including advertisements from BLE proxies."""
        address = self.entry.data.get(CONF_ADDRESS)
        await bluetooth.async_request_active_scan(self.hass)
        deadline = asyncio.get_running_loop().time() + 12
        while asyncio.get_running_loop().time() < deadline:
            if address and (device := bluetooth.async_ble_device_from_address(
                self.hass, address, connectable=True
            )):
                return device
            for service_info in bluetooth.async_discovered_service_info(
                self.hass, connectable=True
            ):
                device = service_info.device
                if address and device.address.lower() == address.lower():
                    return device
                if (
                    not address
                    and service_info.name
                    and service_info.name.startswith(NAME_PREFIXES)
                ):
                    return device
            await asyncio.sleep(0.5)
        target = address or "a device named FICHERO…/D11s_…"
        raise HomeAssistantError(
            f"No connectable Fichero printer advertisement found for {target}"
        )

    def _on_disconnect(self, _client) -> None:
        self.client = None
        self._set_status("disconnected")

    def _on_notify(self, _char, data: bytearray) -> None:
        self._buffer.extend(data)
        self._response.set()

    async def async_disconnect(self, power_off: bool = True) -> None:
        async with self._operation_lock:
            self._set_status("disconnecting")
            if self.client is not None:
                client, self.client = self.client, None
                if client.is_connected:
                    await client.disconnect()
            if power_off and self.entry.data[CONF_POWER_OFF_ON_DISCONNECT]:
                await self._press_switchbot()
            self._set_status("disconnected")

    async def _send(self, data: bytes, wait: bool = False, timeout: float = 3) -> bytes:
        if not self.connected:
            raise HomeAssistantError("Printer disconnected during operation")
        if wait:
            self._buffer.clear()
            self._response.clear()
        await self.client.write_gatt_char(WRITE_UUID, data, response=False)
        if wait:
            try:
                await asyncio.wait_for(self._response.wait(), timeout)
                await asyncio.sleep(0.05)
            except TimeoutError as err:
                raise HomeAssistantError("Printer did not respond") from err
        return bytes(self._buffer)

    async def _send_chunked(self, data: bytes) -> None:
        for offset in range(0, len(data), 200):
            await self._send(data[offset : offset + 200])
            await asyncio.sleep(0.02)

    async def async_print(self, text: str, copies: int) -> None:
        text = text.strip()
        if not text:
            raise HomeAssistantError("Label text cannot be empty")
        if not 1 <= copies <= 100:
            raise HomeAssistantError("Copies must be between 1 and 100")
        if not self.connected:
            await self.async_connect()
        async with self._operation_lock:
            self._set_status("printing")
            try:
                label_rows = self.entry.data[CONF_LABEL_LENGTH] * DOTS_PER_MM
                raster = render_text_raster(text, label_rows)
                await self._send(bytes([0x10, 0xFF, 0x10, 0, self.entry.data[CONF_DENSITY]]), True)
                await asyncio.sleep(0.1)
                for _ in range(copies):
                    status = await self._send(bytes([0x10, 0xFF, 0x40]), True)
                    if not status or status[-1] & 0x56:
                        raise HomeAssistantError("Printer is not ready (paper, cover, heat, or status error)")
                    await self._send(bytes([0x10, 0xFF, 0x84, 0]), True)
                    await self._send(b"\x00" * 12)
                    await self._send(bytes([0x10, 0xFF, 0xFE, 0x01]))
                    header = bytes([0x1D, 0x76, 0x30, 0, BYTES_PER_ROW, 0, label_rows & 0xFF, label_rows >> 8])
                    await self._send_chunked(header + raster)
                    await asyncio.sleep(0.5)
                    await self._send(bytes([0x1D, 0x0C]))
                    await asyncio.sleep(0.3)
                    await self._send(bytes([0x10, 0xFF, 0xFE, 0x45]), True, 60)
                self._set_status("connected")
            except Exception as err:
                self._set_status("error", str(err))
                raise

    async def async_save_favorite(self, text: str) -> None:
        text = text.strip()
        if not text:
            raise HomeAssistantError("Favorite text cannot be empty")
        if text not in self.favorites:
            self.favorites.append(text)
            await self._store.async_save({"favorites": self.favorites})
            self._notify()

    async def async_delete_favorite(self, text: str) -> None:
        if text in self.favorites:
            self.favorites.remove(text)
            await self._store.async_save({"favorites": self.favorites})
            self._notify()
