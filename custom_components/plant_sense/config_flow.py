"""Config flow for PlantSense integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from custom_components.plant_sense.helpers import build_unique_id

from .const import (
    CONF_DEVICE_SERIAL,
    DISCOVERY_NAME,
    DISCOVERY_SERIAL,
    DOMAIN,
    OPTIONS_AUTO_UPDATE,
    OPTIONS_ENABLE_TEST,
    OPTIONS_MOI_DRY,
    OPTIONS_MOI_WET,
    OPTIONS_SSID,
    OPTIONS_UPDATE_CONFIG,
    OPTIONS_UPDATE_NAME,
    OPTIONS_UPDATE_TEST_MODE,
    OPTIONS_WIFI_PWD,
)

if TYPE_CHECKING:
    from homeassistant.helpers.typing import DiscoveryInfoType

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEVICE_SERIAL): str,
    }
)


class PlantSenseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PlantSense."""

    VERSION = 1
    _discovery_serial: str | None = None
    _discovery_unique_id: str | None = None
    _discovery_name: str = "-"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
            )

        device_unique_id = build_unique_id(user_input[CONF_DEVICE_SERIAL])

        await self.async_set_unique_id(device_unique_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title=device_unique_id, data=user_input)

    @staticmethod
    @callback
    def async_get_options_flow(
        entry: ConfigEntry,
    ) -> OptionsFlow:
        """Get option flow."""
        return OptionsFlowHandler(entry)

    async def async_step_integration_discovery(
        self, discovery_info: DiscoveryInfoType
    ) -> ConfigFlowResult:
        """Handle integration discovery."""
        self._discovery_serial = discovery_info[DISCOVERY_SERIAL]

        if (self._discovery_serial is None) or (self._discovery_serial == ""):
            return self.async_abort(reason="no_devices_found")

        self._discovery_unique_id = build_unique_id(self._discovery_serial)
        self._discovery_name = discovery_info.get(DISCOVERY_NAME, "-")

        # We do not want to raise on progress as integration_discovery takes
        # precedence over other discovery flows since we already have the keys.
        #
        # After we do discovery we will abort the flows that do not have the keys
        # below unless the user is already setting them up.
        await self.async_set_unique_id(
            self._discovery_unique_id, raise_on_progress=False
        )
        self._abort_if_unique_id_configured()

        return await self.async_step_integration_discovery_confirm()

    async def async_step_integration_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a confirmation of discovered integration."""
        if self._discovery_serial is None or self._discovery_unique_id is None:
            return self.async_abort(reason="no_devices_found")

        if user_input is not None:
            return self.async_create_entry(
                title=f"PlantSense {self._discovery_name}",
                data={CONF_DEVICE_SERIAL: self._discovery_serial},
            )

        placeholders = {
            "devicename": self._discovery_name,
            "serial": self._discovery_serial,
        }

        self.context["title_placeholders"] = placeholders

        self._set_confirm_only()
        return self.async_show_form(
            step_id="integration_discovery_confirm",
            description_placeholders=placeholders,
        )


class OptionsFlowHandler(OptionsFlow):
    """Options flow handler for new API."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize option."""
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Display option dialog."""
        if user_input is not None:
            config_fields = [
                OPTIONS_UPDATE_NAME,
                OPTIONS_UPDATE_TEST_MODE,
                OPTIONS_MOI_DRY,
                OPTIONS_MOI_WET,
                OPTIONS_SSID,
                OPTIONS_WIFI_PWD,
            ]
            config_changed = any(
                user_input.get(key) != self.entry.options.get(key)
                for key in config_fields
            )
            options = {**user_input}
            options[OPTIONS_UPDATE_CONFIG] = (
                True
                if config_changed
                else self.entry.options.get(OPTIONS_UPDATE_CONFIG, False)
            )
            return self.async_create_entry(title="", data=options)

        enable_test = self.entry.options.get(OPTIONS_ENABLE_TEST, False)
        test_mode = self.entry.options.get(OPTIONS_UPDATE_TEST_MODE, False)
        name = self.entry.options.get(OPTIONS_UPDATE_NAME, "")
        moi_dry = self.entry.options.get(OPTIONS_MOI_DRY, 0)
        moi_wet = self.entry.options.get(OPTIONS_MOI_WET, 0)
        ssid = self.entry.options.get(OPTIONS_SSID, "")
        wifi_pwd = self.entry.options.get(OPTIONS_WIFI_PWD, "")
        auto_update = self.entry.options.get(OPTIONS_AUTO_UPDATE, False)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(OPTIONS_ENABLE_TEST, default=enable_test): bool,
                    vol.Optional(OPTIONS_UPDATE_NAME, default=name): str,
                    vol.Optional(OPTIONS_UPDATE_TEST_MODE, default=test_mode): bool,
                    vol.Optional(OPTIONS_MOI_DRY, default=moi_dry): int,
                    vol.Optional(OPTIONS_MOI_WET, default=moi_wet): int,
                    vol.Optional(OPTIONS_SSID, default=ssid): str,
                    vol.Optional(OPTIONS_WIFI_PWD, default=wifi_pwd): str,
                    vol.Optional(OPTIONS_AUTO_UPDATE, default=auto_update): bool,
                }
            ),
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
