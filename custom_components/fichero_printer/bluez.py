"""Targeted BlueZ dual-mode recovery without resetting the shared adapter."""

import asyncio
import logging
import re
import sys

_LOGGER = logging.getLogger(__name__)


async def prefer_le(device) -> bool:
    """Select LE for a local dual-mode printer, if BlueZ supports the property."""
    if sys.platform != "linux" or not isinstance(device.details, dict):
        return False
    path = device.details.get("path", "")
    # Remote proxy devices must never cause a local D-Bus mutation.
    expected = device.address.upper().replace(":", "_")
    if not isinstance(path, str) or not re.fullmatch(r"/org/bluez/hci\d+/dev_" + re.escape(expected), path):
        return False

    from dbus_fast import BusType, Message, MessageType, Variant
    from dbus_fast.aio import MessageBus

    bus = None
    try:
        bus = MessageBus(bus_type=BusType.SYSTEM)
        async with asyncio.timeout(5):
            await bus.connect()
            reply = await bus.call(Message(
                destination="org.bluez", path=path,
                interface="org.freedesktop.DBus.Properties", member="Set",
                signature="ssv",
                body=["org.bluez.Device1", "PreferredBearer", Variant("s", "le")],
            ))
            if reply.message_type == MessageType.ERROR:
                _LOGGER.debug("BlueZ LE preference unavailable: %s %s", reply.error_name, reply.body)
                return False
            return True
    except Exception:
        _LOGGER.debug("Could not set printer's BlueZ LE preference", exc_info=True)
        return False
    finally:
        if bus is not None:
            bus.disconnect()
