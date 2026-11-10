"""MQTT manager for PlantSense."""

import logging

import homeassistant.helpers.device_registry as dr
from homeassistant.components import mqtt
from homeassistant.components.mqtt.models import ReceiveMessage
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, ConfigEntryState
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import discovery_flow
from homeassistant.util.json import JsonObjectType, json_loads_object

from custom_components.plant_sense.const import (
    DISCOVERY_NAME,
    DISCOVERY_SERIAL,
    DOMAIN,
    MQTT_SUBSCRIBE_TOPIC,
)
from custom_components.plant_sense.data import PlantSenseData
from custom_components.plant_sense.helpers import build_unique_id

_LOGGER = logging.getLogger(__name__)


class MqttManager:
    """Manages the MQTT subscription for PlantSense devices."""

    _unsubscribe_mqtt: CALLBACK_TYPE | None

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize MqttManager."""
        self._hass = hass
        self._unsubscribe_mqtt = None

    async def connect(self) -> None:
        """
        Subscribe to the PlantSense MQTT topic.

        The HA MQTT client restores all subscriptions after a broker reconnect, so
        there is no need to watch the connection state here.
        """
        if self._unsubscribe_mqtt is not None:
            return
        self._unsubscribe_mqtt = await mqtt.client.async_subscribe(
            self._hass,
            MQTT_SUBSCRIBE_TOPIC,
            self._async_mqtt_callback,
        )
        _LOGGER.debug("Subscribed to %s.", MQTT_SUBSCRIBE_TOPIC)

    def _is_plant_sense_message(self, json_message: JsonObjectType) -> bool:
        return json_message.get("model") == "PlantSense" and "id" in json_message

    def is_connected(self) -> bool:
        return self._unsubscribe_mqtt is not None

    def disconnect(self) -> None:
        """Unsubscribe from the MQTT topic."""
        if self._unsubscribe_mqtt is not None:
            self._unsubscribe_mqtt()
            self._unsubscribe_mqtt = None

    def _start_discovery(self, device_id: str, name: str) -> None:
        _LOGGER.info("Starting discovery for '%s' (%s).", name, device_id)
        discovery_flow.async_create_flow(
            self._hass,
            DOMAIN,
            context={"source": SOURCE_INTEGRATION_DISCOVERY},
            data={DISCOVERY_SERIAL: device_id, DISCOVERY_NAME: name},
        )

    async def _async_mqtt_callback(self, message: ReceiveMessage) -> None:
        """Parse incoming MQTT payload and route it to the right coordinator."""
        try:
            json_message = json_loads_object(message.payload)
        except ValueError:
            _LOGGER.info("Error parsing JSON from message: %s", message)
            return

        if "hex" in json_message:
            hex_data = json_message.get("hex")
            if isinstance(hex_data, str):
                try:
                    json_data = json_loads_object(bytes.fromhex(hex_data))
                except ValueError:
                    _LOGGER.info("Hex data was not a json object: %s", message)
                    return

                json_message.update(json_data)
            else:
                _LOGGER.error("Hex data was not a string.")

        if self._is_plant_sense_message(json_message):
            await self._handle_message(json_message)
        else:
            _LOGGER.info("Message is not from a PlantSense Device.")

    async def _handle_message(self, json_message: JsonObjectType) -> None:
        """Handle a message from the PlantSense."""
        device_serial = json_message.get("id")
        name = json_message.get("name")

        if not isinstance(device_serial, str):
            _LOGGER.error("Invalid device id in message.")
            return

        if not isinstance(name, str):
            name = "-"

        device_registry = dr.async_get(self._hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, build_unique_id(device_serial))}
        )

        if device is None:
            _LOGGER.warning("No device found for serial '%s'", device_serial)
            self._start_discovery(device_serial, name)
            return

        for entry_id in device.config_entries:
            config_entry = self._hass.config_entries.async_get_entry(entry_id)
            if (
                config_entry
                and config_entry.domain == DOMAIN
                and config_entry.state is ConfigEntryState.LOADED
                and config_entry.runtime_data is not None
                and isinstance(config_entry.runtime_data, PlantSenseData)
                and config_entry.runtime_data.coordinator is not None
            ):
                await config_entry.runtime_data.coordinator.handle_message(json_message)
