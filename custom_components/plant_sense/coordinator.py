"""Coordinator for PlantSense."""

import asyncio
import logging

import homeassistant.helpers.device_registry as dr
from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import (
    DeviceEntry,
    DeviceInfo,
    DeviceRegistry,
)
from homeassistant.util.json import JsonObjectType

from custom_components.plant_sense.data import PlantSenseData

from .const import (
    CONF_DEVICE_SERIAL,
    DATA_LAST_CONFIG_VERSION,
    DOMAIN,
    OPTIONS_ENABLE_TEST,
    OPTIONS_UDPATE_TEST_MODE,
    OPTIONS_UPDATE_CONFIG,
    OPTIONS_UPDATE_NAME,
)

_LOGGER = logging.getLogger(__name__)


class PlantSenseComponent:
    async def update_async(self) -> None:
        pass


class PlantSenseCoordinator:
    """Coordinates Update from PlantSense."""

    _device_serial: str
    _device_id: str
    _components: list[PlantSenseComponent]
    _data: JsonObjectType | None

    _entry: ConfigEntry[PlantSenseData]
    _device_registry: DeviceRegistry
    _display_name: str
    _use_test_data: bool

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry[PlantSenseData]) -> None:
        """Initialize PlantSenseCoordinator."""
        self._entry = entry
        self._use_test_data = entry.options.get(OPTIONS_ENABLE_TEST, False)
        self.hass = hass
        self._device_serial = entry.data[CONF_DEVICE_SERIAL]
        self._device_id = entry.unique_id or ""
        self._data = None
        self._device_registry = dr.async_get(self.hass)
        self._display_name = entry.title
        self._components = []

    async def handle_message(self, json_message: JsonObjectType) -> None:
        """Handle a message from the PlantSense."""
        msg_type = json_message.get("msg")
        _LOGGER.info("Received message type '%s'.", msg_type)

        if msg_type == "data":
            await self._update_sensors(json_message)
        elif msg_type == "config":
            await self._update_config(json_message)

    async def _request_config(self) -> None:
        """Request the current configuration from the PlantSense."""
        _LOGGER.info("Requesting config for %s.", self._device_serial)
        await asyncio.sleep(0.1)
        await mqtt.client.async_publish(
            self.hass,
            "devices/OMG_LILYGO/commands/MQTTtoLORA",
            f'{{"message":"{{\\"id\\":\\"{self._device_serial}\\",\\"cmd\\":\\"get_config\\"}}"}}',
        )

    async def _update_config(self, json_message: JsonObjectType) -> None:
        """Update the configuration from the PlantSense."""
        new_config_version = json_message.get("v")
        if (not isinstance(new_config_version, int)) or new_config_version is None:
            new_config_version = 0

        new_name = json_message.get("name")
        if not isinstance(new_name, str):
            new_name = "unknown"

        test_mode = json_message.get("test")
        if not isinstance(test_mode, bool):
            test_mode = False

        old_config_version = int(self._entry.data[DATA_LAST_CONFIG_VERSION])
        if (not isinstance(old_config_version, int)) or old_config_version is None:
            old_config_version = 0

        if new_config_version > old_config_version:
            _LOGGER.info(
                "Configuration was updated to %s (from %s).",
                new_config_version,
                old_config_version,
            )

            self._display_name = f"PlantSense {new_name}"
            await self._update_device_name(self._display_name)

            options = {**self._entry.options}
            data = {**self._entry.data}

            options[OPTIONS_UPDATE_CONFIG] = False
            options[OPTIONS_UPDATE_NAME] = new_name
            options[OPTIONS_UDPATE_TEST_MODE] = test_mode

            data[DATA_LAST_CONFIG_VERSION] = new_config_version

            self.hass.config_entries.async_update_entry(
                self._entry, title=self._display_name, options=options, data=data
            )

    def register_component(self, component: PlantSenseComponent) -> None:
        self._components.append(component)

    def remove_component(self, component: PlantSenseComponent) -> None:
        self._components.remove(component)

    async def _update_sensors(self, json: JsonObjectType) -> None:
        """Update the Sensors with the new Data."""
        if json["test"] and not self._use_test_data:
            _LOGGER.info(
                "Skipping update for (%s) because it was test data...",
                self._device_serial,
            )
            return

        self._data = json

        device_config_version = json.get("v")
        if not isinstance(device_config_version, int):
            _LOGGER.warning("Device '%s' did not send a version.", self.device_id)
            device_config_version = 0

        try:
            ha_config_version = int(self._entry.data[DATA_LAST_CONFIG_VERSION])
        except (KeyError, ValueError):
            ha_config_version = 0

        if self._entry.options.get(OPTIONS_UPDATE_CONFIG, False):
            # There is a pending configuration update, sending it to the device.
            _LOGGER.info("Updating configuration for '%s'...", self._device_serial)
            await self._send_config_to_device()
        elif ha_config_version < device_config_version:
            _LOGGER.info(
                "Our configuration is outdated to (ours: %s, device %s).",
                ha_config_version,
                device_config_version,
            )
            await self._request_config()

        for component in self._components:
            await component.update_async()

    async def _update_device_name(self, new_name: str) -> None:
        """Update the name of the device."""
        device = self._get_device()
        if device is None:
            return

        self._device_registry.async_update_device(device.id, name=new_name)

    def _get_device(self) -> DeviceEntry | None:
        return self._device_registry.async_get_device(
            identifiers={(DOMAIN, self._device_id)}
        )

    async def _send_config_to_device(self) -> None:
        """Update the configuration of the PlantSense."""
        name = self._entry.options.get(OPTIONS_UPDATE_NAME)
        test_mode = self._entry.options.get(OPTIONS_UDPATE_TEST_MODE)

        await asyncio.sleep(0.1)
        await mqtt.client.async_publish(
            self.hass,
            "devices/OMG_LILYGO/commands/MQTTtoLORA",
            f'{{"message":"{{\\"id\\":\\"{self._device_serial}\\",\\"cmd\\":\\"set_config\\",\\"test\\":{test_mode},\\"name\\":\\"{name}\\"}}"}}',
        )

    @property
    def device_name(self) -> str:
        return self._display_name

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def last_data(self) -> JsonObjectType | None:
        return self._data

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return DeviceInfo(
            name=self.device_name,
            manufacturer="Jean-Richard",
            model="PlantSense",
            serial_number=self._device_serial,
            identifiers={(DOMAIN, self._device_id)},
        )
