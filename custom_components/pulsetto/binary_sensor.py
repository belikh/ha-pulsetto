"""Binary sensors: charging + active session."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .client import PulsettoClient
from .const import DOMAIN
from .entity import PulsettoEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    client: PulsettoClient = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PulsettoChargingSensor(client, entry.entry_id),
            PulsettoActiveSensor(client, entry.entry_id),
        ]
    )


class PulsettoChargingSensor(PulsettoEntity, BinarySensorEntity):
    """True while the `u` probe reports charging."""

    _attr_name = "Charging"
    _attr_device_class = BinarySensorDeviceClass.PLUG

    def __init__(self, client: PulsettoClient, entry_id: str) -> None:
        super().__init__(client, entry_id)
        self._attr_unique_id = f"{entry_id}-charging"

    async def async_update(self) -> None:
        await self._client.query_charging()

    @property
    def is_on(self) -> bool | None:
        return self._client.charging


class PulsettoActiveSensor(PulsettoEntity, BinarySensorEntity):
    """True while the client believes a documented session is running.

    Session state is tracked client-side (start/stop sequences), since the
    device's own status notifications (mode:/BR:/Batt:) don't encode a
    simple in-session flag.
    """

    _attr_name = "Active session"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, client: PulsettoClient, entry_id: str) -> None:
        super().__init__(client, entry_id)
        self._attr_unique_id = f"{entry_id}-active"

    async def async_update(self) -> None:
        await self._client.poll_status()

    @property
    def is_on(self) -> bool | None:
        return self._client.session_active
