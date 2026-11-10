"""Base entity plumbing for Pulsetto platforms."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .client import PulsettoClient
from .const import DOMAIN, MANUFACTURER


class PulsettoEntity(Entity):
    """Shared base: one device = one config entry's client."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, client: PulsettoClient, entry_id: str) -> None:
        self._client = client
        self._entry_id = entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Pulsetto",
            manufacturer=MANUFACTURER,
            sw_version=client.fw_version,
        )

    @property
    def available(self) -> bool:
        return self._client.connected

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._client.add_listener(self._handle_client_update))

    @callback
    def _handle_client_update(self) -> None:
        self.async_write_ha_state()
