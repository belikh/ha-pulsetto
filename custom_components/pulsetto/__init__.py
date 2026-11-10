"""Setup and services for the Pulsetto BLE integration."""

from __future__ import annotations

import asyncio

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import ble
from .client import PulsettoClient
from .const import DOMAIN

PLATFORMS = ["binary_sensor", "button", "number", "sensor"]

SIDE_VALUES = list(ble.SIDE_COMMANDS)
LED_VALUES = [ble.LED_LOW, ble.LED_MED, ble.LED_HIGH]

STIMULATE_SCHEMA = vol.Schema(
    {
        vol.Required("side"): vol.In(SIDE_VALUES),
        vol.Required("level"): vol.All(vol.Coerce(int), vol.Range(min=0, max=9)),
        vol.Optional("time"): vol.All(vol.Coerce(int), vol.Range(min=1, max=3600)),
    }
)
LEVEL_SCHEMA = vol.Schema(
    {vol.Required("level"): vol.All(vol.Coerce(int), vol.Range(min=0, max=9))}
)
LED_SCHEMA = vol.Schema({vol.Required("brightness"): vol.In(LED_VALUES)})

OPTIONAL_ADDRESS = {
    vol.Optional("address"): str,
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    address = entry.data["address"]
    client = PulsettoClient(hass, address)
    await client.connect()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    client: PulsettoClient | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if client is not None:
        await client.disconnect()
    return ok


def _get_client(hass: HomeAssistant, call) -> PulsettoClient:
    clients = list(hass.data.get(DOMAIN, {}).values())
    if not clients:
        raise vol.Invalid("No Pulsetto device configured")
    address = call.data.get("address")
    if address:
        for client in clients:
            if client.address == address:
                return client
        raise vol.Invalid(f"Pulsetto device {address} is not configured")
    return clients[0]


async def _svc_stimulate(call) -> None:
    client = _get_client(call.hass, call)
    side = call.data["side"]
    level = int(call.data["level"])
    duration = call.data.get("time")
    if level == 0:
        # level 0 masks the device; per the doc that pauses without ending
        await client.stop_session()
        return
    await client.start_session(level=level, side=side)
    if duration:
        async def _later_stop():
            await asyncio.sleep(duration)
            if client.connected:
                await client.stop_session()

        call.hass.async_create_task(_later_stop())


async def _svc_stop(call) -> None:
    client = _get_client(call.hass, call)
    await client.stop_session()


async def _svc_level(call) -> None:
    client = _get_client(call.hass, call)
    level = int(call.data["level"])
    if level == 0:
        await client.stop_session()
    else:
        await client.send_level(level, wait_reply=False)


async def _svc_led(call) -> None:
    client = _get_client(call.hass, call)
    brightness = call.data["brightness"]
    await client.send_command(ble.Command(brightness), wait_reply=False)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.services.async_register(DOMAIN, "stimulate", _svc_stimulate, schema=STIMULATE_SCHEMA)
    hass.services.async_register(DOMAIN, "stop", _svc_stop)
    hass.services.async_register(DOMAIN, "set_level", _svc_level, schema=LEVEL_SCHEMA)
    hass.services.async_register(DOMAIN, "set_led", _svc_led, schema=LED_SCHEMA)
    return True
