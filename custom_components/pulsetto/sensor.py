"""Sensor platform: battery, computed from the `Batt:<volts>` reply."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .client import PulsettoClient
from .const import DOMAIN
from .entity import PulsettoEntity

SCAN_INTERVAL_SECONDS = 60  # doc: slower polling is fine when idle


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    client: PulsettoClient = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PulsettoBatterySensor(client, entry.entry_id)])


class PulsettoBatterySensor(PulsettoEntity, SensorEntity):
    """Percent charge per the documented (v-3.5)/0.4 calibration."""

    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, client: PulsettoClient, entry_id: str) -> None:
        super().__init__(client, entry_id)
        self._attr_unique_id = f"{entry_id}-battery"

    @property
    def extra_state_attributes(self) -> dict[str, float | str | None]:
        return {
            "voltage_v": self._client.battery_voltage,
            "fw_version": self._client.fw_version,
            "identity": self._client.identity,
        }

    async def async_update(self) -> None:
        await self._client.query_battery()
        self._attr_native_value = self._client.battery_percent
