"""Coordinator for PlantSense."""

import logging
from typing import Any

import homeassistant.helpers.device_registry as dr
from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import (
    DeviceEntry,
    DeviceInfo,
    DeviceRegistry,
)
from homeassistant.util.json import json_loads

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class PlantSenseComponent:
    async def update_async(self) -> None:
        pass


class PlantSenseCoordinator:
    """Coordinates Update from PlantSense."""

    _device_serial: str
    _device_id: str
    _components: list[PlantSenseComponent]
    data: Any

    _device_registry: DeviceRegistry
    _device_name: str

    def __init__(self, hass: HomeAssistant, device_id: str, device_serial: str) -> None:
        """Initialize PlantSenseCoordinator."""
        self.hass = hass
        self._device_serial = device_serial
        self._device_id = device_id
        self.data = None
        self._device_registry = dr.async_get(self.hass)
        self._device_name = f"PlantSense {self._device_serial}"
        self._components = []

    async def connect(self) -> None:
        device = self._get_device()
        if device is not None and device.name is not None:
            self._device_name = device.name

        @callback
        async def mqtt_callback(message: ReceiveMessage) -> None:
            """Pass MQTT payload to DROP API parser."""
            json_message = json_loads(message.payload)
            if (
                isinstance(json_message, dict)
                and json_message.get("model") == "PlantSense"
                and json_message.get("id") == self._device_serial
            ):
                await self._update_sensors(json_message)

        await mqtt.client.async_subscribe(
            self.hass,
            f"devices/OMG_LILYGO/LORAtoMQTT/{self._device_serial}",
            mqtt_callback,
        )

    def register_component(self, component: PlantSenseComponent) -> None:
        self._components.append(component)

    def remove_component(self, component: PlantSenseComponent) -> None:
        self._components.remove(component)

    async def _update_sensors(self, data: Any) -> None:
        """Update the Sensors with the new Data."""
        self.data = data
        self._device_name = f"PlantSense {data["name"]}"

        device = self._get_device()
        if device is not None and device.name != self._device_name:
            self._device_registry.async_update_device(device.id, name=self._device_name)

        for component in self._components:
            await component.update_async()

    def _get_device(self) -> DeviceEntry | None:
        return self._device_registry.async_get_device(
            identifiers={(DOMAIN, self._device_id)}
        )

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def device_id(self) -> str:
        return self._device_id

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
