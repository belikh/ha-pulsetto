"""Buttons for one-shot device actions. Stop/ramp use write-with-response."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import ble
from .client import PulsettoClient
from .const import DOMAIN
from .entity import PulsettoEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    client: PulsettoClient = hass.data[DOMAIN][entry.entry_id]
    entities = [
        PulsettoSessionButton(client, entry.entry_id, "start_both", "Start session (both)", "start-both", lambda c: c.start_session(side="both")),
        PulsettoSessionButton(client, entry.entry_id, "start_left", "Start session (left)", "start-left", lambda c: c.start_session(side="left")),
        PulsettoSessionButton(client, entry.entry_id, "start_right", "Start session (right)", "start-right", lambda c: c.start_session(side="right")),
        PulsettoSessionButton(client, entry.entry_id, "stop", "Stop session", "stop", lambda c: c.stop_session()),
    ]
    async_add_entities(entities)


class PulsettoButton(PulsettoEntity, ButtonEntity):
    def __init__(self, client, entry_id, key, name):
        super().__init__(client, entry_id)
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry_id}-{key}"

    async def async_press(self) -> None:
        raise NotImplementedError


# NOTE: 'U' (DFU reboot) is intentionally NOT exposed as a button. It is a
# destructive command (reboots the device into the bootloader) and has no
# place in an automation-facing UI. DFU is documented for a separate,
# manually confirmed entry point.


class PulsettoSessionButton(PulsettoButton):
    def __init__(self, client, entry_id, key, name, _slug, action) -> None:
        super().__init__(client, entry_id, key, name)
        self._action = action

    async def async_press(self) -> None:
        await self._action(self._client)


async def _ramp(client: PulsettoClient, cmd) -> None:
    await client.send_command(cmd, wait_reply=False)
