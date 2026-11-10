"""Config flow for the Pulsetto BLE integration."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
import voluptuous as vol

from .const import CONF_ADDRESS, DOMAIN, NORDIC_UART_SERVICE

_SENTINEL = object()


class PulsettoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Discover Pulsetto devices by their Nordic UART service UUID."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, str] = {}
        self._errors: dict[str, str] = {}

    async def async_step_bluetooth(
        self, info: BluetoothServiceInfoBleak
    ) -> config_entries.ConfigFlowResult:
        """HA pushes devices matching the manifest bluetooth matchers."""
        await self.async_set_unique_id(info.address)
        self._abort_if_unique_id_configured()
        self._discovered[info.address] = info.name or info.address
        return await self.async_step_confirm(address=info.address)

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manual setup: pick from already-discovered BLE devices."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            if address in self._discovered:
                pass  # name recorded below; address is the unique id
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=self._discovered.get(address, address),
                data={CONF_ADDRESS: address},
            )

        for info in async_discovered_service_info(self.hass):
            if (
                NORDIC_UART_SERVICE in info.service_uuids
                or info.name.startswith("Pulsetto")
            ):
                self._discovered[info.address] = info.name or info.address

        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(self._discovered),
                }
            ),
        )

    async def async_step_confirm(
        self, address: str | None = None, name: str | None = None
    ) -> config_entries.ConfigFlowResult:
        """Second step when we came from the bluetooth async setup flow."""
        if address is None:
            return self.async_abort(reason="no_devices_found")
        if name:
            self._discovered[address] = name
        return self.async_create_entry(
            title=self._discovered.get(address, address),
            data={CONF_ADDRESS: address},
        )
