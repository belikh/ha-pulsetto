"""Base entity plumbing for Pulsetto platforms."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .client import PulsettoClient
from .const import DOMAIN, MANUFACTURER


class PulsettoEntity(Entity):
    """Shared base: one device = one config entry's client."""

    def __init__(self, client: PulsettoClient, entry_id: str) -> None:
        self._client = client
        self._entry_id = entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Pulsetto Device",
            manufacturer=MANUFACTURER,
            sw_version=client.fw_version,
        )
