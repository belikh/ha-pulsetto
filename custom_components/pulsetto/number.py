"""Number platform: stimulation intensity, 0-9 (0 pauses the session)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .client import PulsettoClient
from .const import DOMAIN
from .entity import PulsettoEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    client: PulsettoClient = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PulsettoIntensityNumber(client, entry.entry_id)])


class PulsettoIntensityNumber(PulsettoEntity, RestoreNumber, NumberEntity):
    """Direct `1`..`9` level writes per the doc; `0` pauses output."""

    _attr_translation_key = "intensity"
    _attr_native_min_value = 0
    _attr_native_max_value = 9
    _attr_native_step = 1
    _attr_mode = "slider"

    def __init__(self, client: PulsettoClient, entry_id: str) -> None:
        super().__init__(client, entry_id)
        self._attr_unique_id = f"{entry_id}-intensity"
        self._attr_native_value = 0

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number()
        if last is not None:
            self._attr_native_value = last.native_value

    async def async_set_native_value(self, value: float) -> None:
        level = int(value)
        await self._client.send_level(level, wait_reply=False)
        self._attr_native_value = level
        self.async_write_ha_state()
