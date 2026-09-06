"""Connection lifecycle regression tests with simulated HA and BLE boundaries."""

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture
def manager_module(monkeypatch):
    # Keep HA optional for the CLI suite; load the real manager with only its
    # HA boundary stubbed, and use the installed Bleak/connector implementations.
    modules = {
        name: ModuleType(name)
        for name in (
            "homeassistant", "homeassistant.components",
            "homeassistant.components.bluetooth", "homeassistant.core",
            "homeassistant.exceptions", "homeassistant.helpers",
            "homeassistant.helpers.storage", "fichero_test_integration",
        )
    }
    root = Path(__file__).parents[1] / "custom_components" / "fichero_printer"
    modules["fichero_test_integration"].__path__ = [str(root)]
    modules["homeassistant.core"].HomeAssistant = object
    modules["homeassistant.exceptions"].HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    modules["homeassistant.helpers.storage"].Store = Mock()
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    name = "fichero_test_integration.manager"
    spec = importlib.util.spec_from_file_location(name, root / "manager.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def session(manager_module):
    target = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", name="FICHERO_test")
    manager_module.bluetooth.async_ble_device_from_address = Mock(return_value=target)
    manager = manager_module.FicheroManager(Mock(), SimpleNamespace(entry_id="test", data={}))
    manager._press_switchbot = AsyncMock()
    return manager, target


def client(missing=False):
    return SimpleNamespace(
        is_connected=True,
        services=SimpleNamespace(get_characteristic=Mock(return_value=None if missing else object())),
        start_notify=AsyncMock(), clear_cache=AsyncMock(), disconnect=AsyncMock(),
    )


def test_recovers_missing_gatt_services(manager_module, session):
    manager, target = session
    stale, fresh = client(missing=True), client()
    manager_module.establish_connection = AsyncMock(side_effect=[stale, fresh])
    asyncio.run(manager._connect_to_printer(target))
    stale.clear_cache.assert_awaited_once()
    stale.disconnect.assert_awaited_once()
    stale.start_notify.assert_not_awaited()
    assert manager.client is fresh
    assert manager.status == "connected"
    calls = manager_module.establish_connection.call_args_list
    assert calls[0].kwargs["use_services_cache"] is True
    assert calls[1].kwargs["use_services_cache"] is False
    assert manager_module.bluetooth.async_ble_device_from_address.call_count == 2


def test_missing_services_retry_is_bounded(manager_module, session):
    manager, target = session
    first, second = client(True), client(True)
    manager_module.establish_connection = AsyncMock(side_effect=[first, second])
    with pytest.raises(manager_module.HomeAssistantError, match="GATT services unavailable"):
        asyncio.run(manager._connect_to_printer(target))
    assert manager.client is None
    first.disconnect.assert_awaited_once()
    second.disconnect.assert_awaited_once()
    second.clear_cache.assert_not_awaited()


@pytest.mark.parametrize("error", [RuntimeError("notify failed"), asyncio.CancelledError()])
def test_notification_failure_or_cancellation_releases_client(manager_module, session, error):
    manager, target = session
    connection = client()
    connection.start_notify.side_effect = error
    manager_module.establish_connection = AsyncMock(return_value=connection)
    with pytest.raises(type(error)):
        asyncio.run(manager._connect_to_printer(target))
    connection.disconnect.assert_awaited_once()
    assert manager.client is None


def test_old_disconnect_callback_does_not_clear_new_session(session):
    manager, _ = session
    old, current = client(), client()
    manager.client = current
    manager._on_disconnect(old)
    assert manager.client is current
    manager._on_disconnect(current)
    assert manager.client is None


def test_unload_releases_ble_without_switchbot(session):
    manager, _ = session
    connection = client()
    manager.client = connection
    asyncio.run(manager.async_disconnect(power_off=False))
    connection.disconnect.assert_awaited_once()
    manager._press_switchbot.assert_not_awaited()
    assert manager.client is None
    assert manager.status == "disconnected"


def test_success_does_not_clear_cache_or_disconnect(manager_module, session):
    manager, target = session
    connection = client()
    manager_module.establish_connection = AsyncMock(return_value=connection)
    asyncio.run(manager._connect_to_printer(target))
    connection.clear_cache.assert_not_awaited()
    connection.disconnect.assert_not_awaited()
    assert manager.connected


@pytest.mark.parametrize("wrapped", [False, True])
def test_bredr_failure_selects_le_and_retries(manager_module, session, wrapped):
    manager, target = session
    error = manager_module.BleakDBusError("org.bluez.Error.BREDR.ProfileUnavailable", ["No more profiles to connect to"])
    if wrapped:
        error = manager_module.BleakError(f"Connection failed: {error}")
    connection = client()
    manager_module.establish_connection = AsyncMock(side_effect=[error, connection])
    manager_module.prefer_le = AsyncMock(return_value=True)
    asyncio.run(manager._connect_to_printer(target))
    manager_module.prefer_le.assert_awaited_once_with(target)
    assert manager.connected


def test_bredr_unsupported_reports_actionable_error(manager_module, session):
    manager, target = session
    manager_module.establish_connection = AsyncMock(side_effect=manager_module.BleakDBusError(
        "org.bluez.Error.BREDR.ProfileUnavailable", ["No more profiles to connect to"]))
    manager_module.prefer_le = AsyncMock(return_value=False)
    with pytest.raises(manager_module.HomeAssistantError, match="PreferredBearer"):
        asyncio.run(manager._connect_to_printer(target))
    assert manager_module.establish_connection.await_count == 1


def test_switchbot_press_actually_connects_without_monitor(manager_module, session, monkeypatch):
    manager, target = session
    manager.entry.data = {"startup_delay": 0}
    manager._resolve_printer = AsyncMock(return_value=target)
    connection = client()
    manager_module.establish_connection = AsyncMock(return_value=connection)
    asyncio.run(manager.async_connect())
    manager._press_switchbot.assert_awaited_once()
    assert manager.connected
    # Another connect must not turn an already-connected printer off.
    asyncio.run(manager.async_connect())
    assert manager._press_switchbot.await_count == 1


def test_wake_failure_preserves_bluez_error(manager_module, session):
    manager, target = session
    manager.entry.data = {"startup_delay": 0}
    manager._resolve_printer = AsyncMock(return_value=target)
    manager._connect_to_printer = AsyncMock(side_effect=RuntimeError("BlueZ diagnostic"))
    with pytest.raises(manager_module.HomeAssistantError, match="BlueZ diagnostic"):
        asyncio.run(manager.async_connect())
    assert manager.last_error == "BlueZ diagnostic"
    manager._press_switchbot.assert_awaited_once()


@pytest.mark.parametrize("fails", [False, True])
def test_bluez_sets_only_target_preferred_bearer(manager_module, monkeypatch, fails):
    import dbus_fast
    import dbus_fast.aio
    bluez = sys.modules["fichero_test_integration.bluez"]
    monkeypatch.setattr(bluez.sys, "platform", "linux")
    bus = SimpleNamespace(connect=AsyncMock(), disconnect=Mock(), call=AsyncMock(return_value=SimpleNamespace(
        message_type=dbus_fast.MessageType.ERROR if fails else dbus_fast.MessageType.METHOD_RETURN,
        error_name="org.freedesktop.DBus.Error.UnknownProperty", body=[])))
    factory = Mock(return_value=bus)
    monkeypatch.setattr(dbus_fast.aio, "MessageBus", factory)
    device = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", details={"path": "/org/bluez/hci1/dev_AA_BB_CC_DD_EE_FF"})
    assert asyncio.run(bluez.prefer_le(device)) is (not fails)
    message = bus.call.call_args.args[0]
    assert message.path == device.details["path"]
    assert message.member == "Set"
    assert message.body[:2] == ["org.bluez.Device1", "PreferredBearer"]
    assert message.body[2].value == "le"
    bus.disconnect.assert_called_once()


def test_bluez_never_changes_local_host_for_proxy(manager_module, monkeypatch):
    import dbus_fast.aio
    bluez = sys.modules["fichero_test_integration.bluez"]
    monkeypatch.setattr(bluez.sys, "platform", "linux")
    factory = Mock()
    monkeypatch.setattr(dbus_fast.aio, "MessageBus", factory)
    device = SimpleNamespace(address="AA:BB:CC:DD:EE:FF", details={"source": "esphome-proxy"})
    assert asyncio.run(bluez.prefer_le(device)) is False
    factory.assert_not_called()
