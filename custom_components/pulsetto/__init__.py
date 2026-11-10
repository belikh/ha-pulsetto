"""Setup and services for the Pulsetto BLE integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.service import async_register_admin_service

from . import ble
from .client import PulsettoClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

POLL_INTERVAL = timedelta(seconds=30)

PLATFORMS = ["binary_sensor", "button", "number", "sensor"]

SIDE_VALUES = list(ble.SIDE_COMMANDS)
LED_VALUES = [ble.LED_LOW, ble.LED_MED, ble.LED_HIGH]

OPTIONAL_ADDRESS = {
    vol.Optional("address"): str,
}

STIMULATE_SCHEMA = vol.Schema(
    {
        **OPTIONAL_ADDRESS,
        vol.Required("side"): vol.In(SIDE_VALUES),
        vol.Required("level"): vol.All(vol.Coerce(int), vol.Range(min=0, max=9)),
        vol.Optional("time"): vol.All(vol.Coerce(int), vol.Range(min=1, max=3600)),
    }
)
LEVEL_SCHEMA = vol.Schema(
    {
        **OPTIONAL_ADDRESS,
        vol.Required("level"): vol.All(vol.Coerce(int), vol.Range(min=0, max=9)),
    }
)
LED_SCHEMA = vol.Schema(
    {**OPTIONAL_ADDRESS, vol.Required("brightness"): vol.In(LED_VALUES)}
)
STOP_SCHEMA = vol.Schema({**OPTIONAL_ADDRESS})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    address = entry.data["address"]
    client = PulsettoClient(hass, address)
    try:
        await client.connect()
    except Exception as err:  # bleak raises many types on connect failure
        await client.disconnect()
        raise ConfigEntryNotReady(f"Cannot connect to Pulsetto: {err}") from err
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client

    async def _poll(_now) -> None:
        if not client.connected:
            try:
                await client.connect()
            except Exception as err:  # device out of range; retry next tick
                _LOGGER.debug("Reconnect failed: %s", err)
                return
        try:
            await client.poll_status()
        except Exception as err:
            _LOGGER.debug("Status poll failed: %s", err)

    entry.async_on_unload(async_track_time_interval(hass, _poll, POLL_INTERVAL))

    async def _stop_on_shutdown(_event) -> None:
        await _stop_if_active(client)

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop_on_shutdown)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _stop_if_active(client: PulsettoClient) -> None:
    """Send the stop sequence so unload or shutdown never leaves output running."""
    if client.connected and client.session_active:
        try:
            await client.stop_session()
        except Exception as err:
            _LOGGER.warning("Could not stop session on shutdown: %s", err)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    client: PulsettoClient | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if client is not None:
        await _stop_if_active(client)
        await client.disconnect()
    return ok


def _get_client(hass: HomeAssistant, call) -> PulsettoClient:
    clients = list(hass.data.get(DOMAIN, {}).values())
    if not clients:
        raise ServiceValidationError("No Pulsetto device configured")
    address = call.data.get("address")
    if address:
        for client in clients:
            if client.address == address:
                return client
        raise ServiceValidationError(f"Pulsetto device {address} is not configured")
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
        client.schedule_stop(duration)


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
    async_register_admin_service(hass, DOMAIN, "stimulate", _svc_stimulate, schema=STIMULATE_SCHEMA)
    async_register_admin_service(hass, DOMAIN, "stop", _svc_stop, schema=STOP_SCHEMA)
    async_register_admin_service(hass, DOMAIN, "set_level", _svc_level, schema=LEVEL_SCHEMA)
    async_register_admin_service(hass, DOMAIN, "set_led", _svc_led, schema=LED_SCHEMA)
    return True
