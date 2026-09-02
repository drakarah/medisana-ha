"""Config flow for the Medisana BS444 integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import (
    CONF_USE_TIME_OFFSET,
    DEFAULT_USE_TIME_OFFSET,
    DOMAIN,
    SERVICE_UUID,
)


class MedisanaBS444ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Medisana BS444."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, str] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a discovered Bluetooth device (e.g. via a Bluetooth proxy)."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name or discovery_info.address}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the discovered device."""
        assert self._discovery_info is not None
        if user_input is not None:
            return self._async_create_entry(
                self._discovery_info.address,
                self._discovery_info.name or self._discovery_info.address,
                user_input,
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self._discovery_info.name or self._discovery_info.address
            },
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USE_TIME_OFFSET, default=DEFAULT_USE_TIME_OFFSET
                    ): bool,
                }
            ),
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a manually initiated setup, listing already-discovered scales."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self._async_create_entry(
                address, self._discovered_devices.get(address, address), user_input
            )

        current_addresses = self._async_current_ids()
        for discovery_info in async_discovered_service_info(self.hass, connectable=True):
            if discovery_info.address in current_addresses:
                continue
            if SERVICE_UUID not in discovery_info.service_uuids:
                continue
            self._discovered_devices[discovery_info.address] = (
                discovery_info.name or discovery_info.address
            )

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(self._discovered_devices),
                    vol.Required(
                        CONF_USE_TIME_OFFSET, default=DEFAULT_USE_TIME_OFFSET
                    ): bool,
                }
            ),
        )

    def _async_create_entry(
        self, address: str, name: str, user_input: dict[str, Any]
    ) -> ConfigFlowResult:
        return self.async_create_entry(
            title=name,
            data={
                CONF_ADDRESS: address,
                CONF_USE_TIME_OFFSET: user_input[CONF_USE_TIME_OFFSET],
            },
        )
