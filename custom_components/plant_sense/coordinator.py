"""Coordinator for PlantSense."""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any

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
    DATA_CONFIRMED_MOI_DRY,
    DATA_CONFIRMED_MOI_WET,
    DATA_CONFIRMED_NAME,
    DATA_CONFIRMED_TEST_MODE,
    DATA_LAST_CONFIG_VERSION,
    DATA_WIFI_CONFIGURED,
    DOMAIN,
    MQTT_COMMAND_TOPIC,
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
from .helpers import is_newer_firmware

_LOGGER = logging.getLogger(__name__)

# Short delay before sending a downlink so the gateway has finished handling the
# uplink that triggered it.
COMMAND_DELAY_SECONDS = 0.1


class PlantSenseComponent(ABC):
    @abstractmethod
    async def update_async(self) -> None: ...


class PlantSenseCoordinator:
    """Coordinates Update from PlantSense."""

    _device_serial: str
    _device_id: str
    _components: list[PlantSenseComponent]
    _data: JsonObjectType | None

    _entry: ConfigEntry[PlantSenseData]
    _device_registry: DeviceRegistry
    _display_name: str
    _firmware_version: str | None
    _latest_firmware_version: str | None
    _wifi_configured: bool | None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry[PlantSenseData]) -> None:
        """Initialize PlantSenseCoordinator."""
        self._entry = entry
        self.hass = hass
        self._device_serial = entry.data.get(CONF_DEVICE_SERIAL, "")
        self._device_id = entry.unique_id or ""
        self._data = None
        self._device_registry = dr.async_get(self.hass)
        self._display_name = entry.title
        self._firmware_version = None
        self._latest_firmware_version = None
        wifi_configured = entry.data.get(DATA_WIFI_CONFIGURED)
        self._wifi_configured = (
            wifi_configured if isinstance(wifi_configured, bool) else None
        )
        self._components = []

    async def handle_message(self, json_message: JsonObjectType) -> None:
        """Handle a message from the PlantSense."""
        msg_type = json_message.get("msg")
        _LOGGER.info("Received message type '%s'.", msg_type)

        if msg_type == "data":
            await self._update_sensors(json_message)
            await self._handle_pending_commands(json_message)
        elif msg_type == "config":
            await self._update_config(json_message)
        elif msg_type == "wifi":
            await self._update_firmware_version(json_message)

    async def _publish_command(self, command: dict[str, Any]) -> None:
        """Publish a LoRa downlink command (JSON wrapped in a JSON string)."""
        await asyncio.sleep(COMMAND_DELAY_SECONDS)
        await mqtt.client.async_publish(
            self.hass,
            MQTT_COMMAND_TOPIC,
            json.dumps({"message": json.dumps(command)}),
        )

    async def _request_config(self) -> None:
        """Request the current configuration from the PlantSense."""
        _LOGGER.info("Requesting config for %s.", self._device_serial)
        await self._publish_command({"id": self._device_serial, "cmd": "get_config"})

    def _stored_config_version(self) -> int | None:
        """Return the config version last confirmed by the device, None if unknown."""
        version = self._entry.data.get(DATA_LAST_CONFIG_VERSION)
        if version is None:
            return None
        try:
            return int(version)
        except (ValueError, TypeError):
            return None

    async def _update_config(self, json_message: JsonObjectType) -> None:
        """Update the configuration from the PlantSense."""
        await self._update_firmware_version(json_message)
        self._update_wifi_configured(json_message)

        new_config_version = json_message.get("v", 0)
        if not isinstance(new_config_version, int):
            new_config_version = 0

        old_config_version = self._stored_config_version()
        if old_config_version == new_config_version:
            return

        new_name = str(json_message.get("name", "unknown"))

        test_mode = json_message.get("test", False)
        if not isinstance(test_mode, bool):
            test_mode = False

        moi_dry = json_message.get("moiDry")
        if not isinstance(moi_dry, int):
            moi_dry = None

        moi_wet = json_message.get("moiWet")
        if not isinstance(moi_wet, int):
            moi_wet = None

        _LOGGER.info(
            "Storing config version %s (replacing %s).",
            new_config_version,
            old_config_version,
        )

        self._display_name = f"PlantSense {new_name}"
        await self._update_device_name(self._display_name)

        options = {**self._entry.options}
        data = {**self._entry.data}

        options[OPTIONS_UPDATE_CONFIG] = False
        options[OPTIONS_UPDATE_NAME] = new_name
        options[OPTIONS_UPDATE_TEST_MODE] = test_mode
        # The WiFi password is only kept until the device has confirmed the
        # config; never store it permanently.
        options[OPTIONS_WIFI_PWD] = ""
        if moi_dry is not None:
            options[OPTIONS_MOI_DRY] = moi_dry
        if moi_wet is not None:
            options[OPTIONS_MOI_WET] = moi_wet

        data[DATA_LAST_CONFIG_VERSION] = new_config_version
        data[DATA_CONFIRMED_NAME] = new_name
        data[DATA_CONFIRMED_TEST_MODE] = test_mode
        if moi_dry is not None:
            data[DATA_CONFIRMED_MOI_DRY] = moi_dry
        if moi_wet is not None:
            data[DATA_CONFIRMED_MOI_WET] = moi_wet

        self.hass.config_entries.async_update_entry(
            self._entry, title=self._display_name, options=options, data=data
        )

        await self._notify_components()

    def _update_wifi_configured(self, json_message: JsonObjectType) -> None:
        """Track (and persist) whether WiFi credentials are set on the device."""
        wifi_set = json_message.get("wifiSet")
        if not isinstance(wifi_set, bool):
            return
        self._wifi_configured = wifi_set
        if self._entry.data.get(DATA_WIFI_CONFIGURED) != wifi_set:
            self.hass.config_entries.async_update_entry(
                self._entry, data={**self._entry.data, DATA_WIFI_CONFIGURED: wifi_set}
            )

    def register_component(self, component: PlantSenseComponent) -> None:
        self._components.append(component)

    def remove_component(self, component: PlantSenseComponent) -> None:
        self._components.remove(component)

    async def _notify_components(self) -> None:
        """Let every registered component refresh; one failure must not stop others."""
        for component in list(self._components):
            try:
                await component.update_async()
            except Exception:
                _LOGGER.exception("Error updating component %s", component)

    async def _update_sensors(self, json: JsonObjectType) -> None:
        """Update the Sensors with the new Data."""
        if json.get("test", False) and not self._entry.options.get(
            OPTIONS_ENABLE_TEST, False
        ):
            _LOGGER.info(
                "Skipping update for (%s) because it was test data...",
                self._device_serial,
            )
            return

        self._data = json
        await self._update_firmware_version(json)
        await self._notify_components()

    async def _handle_pending_commands(self, json: JsonObjectType) -> None:
        """Send any pending config or OTA commands now that the device is online."""
        device_config_version = json.get("v", 0)
        if not isinstance(device_config_version, int):
            _LOGGER.warning("Device '%s' did not send a version.", self.device_id)
            device_config_version = 0

        ha_config_version = self._stored_config_version()

        if ha_config_version != device_config_version:
            # Also covers a device whose config was never fetched (None): never push
            # a config built from form defaults before the device's values are known.
            _LOGGER.warning(
                "Config version mismatch (ours: %s, device: %s) — "
                "discarding pending changes and fetching config from device.",
                ha_config_version,
                device_config_version,
            )
            await self.async_abort_config_push()
            await self._request_config()
        elif self._entry.options.get(OPTIONS_UPDATE_CONFIG, False):
            _LOGGER.info("Updating configuration for '%s'...", self._device_serial)
            await self._send_config_to_device()
        elif self._should_auto_update():
            _LOGGER.info(
                "Auto-update: sending OTA version '%s' to '%s'.",
                self._latest_firmware_version,
                self._device_serial,
            )
            await self._send_ota_to_device(str(self._latest_firmware_version))

    def _should_auto_update(self) -> bool:
        """Return True if an OTA command should be sent on this contact."""
        if not self._entry.options.get(OPTIONS_AUTO_UPDATE, False):
            return False
        if self._latest_firmware_version is None or self._firmware_version is None:
            return False
        if self._wifi_configured is False:
            # The device downloads the firmware over WiFi; without credentials the
            # OTA attempt can only fail.
            return False
        return is_newer_firmware(self._latest_firmware_version, self._firmware_version)

    async def _update_device_name(self, new_name: str) -> None:
        """Update the name of the device."""
        device = self._get_device()
        if device is None:
            return

        self._device_registry.async_update_device(device.id, name=new_name)

    async def _update_firmware_version(self, json_message: JsonObjectType) -> None:
        fw = json_message.get("fw")
        if not isinstance(fw, str) or fw == self._firmware_version:
            return
        self._firmware_version = fw
        device = self._get_device()
        if device is not None:
            self._device_registry.async_update_device(device.id, sw_version=fw)

    def _get_device(self) -> DeviceEntry | None:
        return self._device_registry.async_get_device(
            identifiers={(DOMAIN, self._device_id)}
        )

    async def _send_config_to_device(self) -> None:
        """Update the configuration of the PlantSense."""
        name = self._entry.options.get(OPTIONS_UPDATE_NAME, "")
        test_mode = self._entry.options.get(OPTIONS_UPDATE_TEST_MODE, False)
        moi_dry = self._entry.options.get(OPTIONS_MOI_DRY, 0)
        moi_wet = self._entry.options.get(OPTIONS_MOI_WET, 0)
        ssid = self._entry.options.get(OPTIONS_SSID, "")
        wifi_pwd = self._entry.options.get(OPTIONS_WIFI_PWD, "")

        inner: dict[str, Any] = {
            "id": self._device_serial,
            "cmd": "set_config",
            "test": test_mode,
            "name": name,
            "moiDry": moi_dry,
            "moiWet": moi_wet,
        }
        if ssid:
            inner["ssid"] = ssid
        if wifi_pwd:
            inner["wifiPwd"] = wifi_pwd

        await self._publish_command(inner)

    async def async_abort_config_push(self) -> None:
        """Cancel a pending config push and revert options to last confirmed values."""
        if not self.config_pending:
            return

        data = self._entry.data
        options = {**self._entry.options}

        options[OPTIONS_UPDATE_CONFIG] = False
        # Discard any pending WiFi password; it is never stored permanently.
        options[OPTIONS_WIFI_PWD] = ""
        options[OPTIONS_UPDATE_NAME] = data.get(
            DATA_CONFIRMED_NAME, options.get(OPTIONS_UPDATE_NAME, "")
        )
        options[OPTIONS_UPDATE_TEST_MODE] = data.get(
            DATA_CONFIRMED_TEST_MODE, options.get(OPTIONS_UPDATE_TEST_MODE, False)
        )
        options[OPTIONS_MOI_DRY] = data.get(
            DATA_CONFIRMED_MOI_DRY, options.get(OPTIONS_MOI_DRY, 0)
        )
        options[OPTIONS_MOI_WET] = data.get(
            DATA_CONFIRMED_MOI_WET, options.get(OPTIONS_MOI_WET, 0)
        )

        self.hass.config_entries.async_update_entry(self._entry, options=options)

    async def _send_ota_to_device(self, version: str) -> None:
        """Publish an OTA update command to the device."""
        await self._publish_command(
            {"id": self._device_serial, "cmd": "ota", "version": version}
        )

    def set_latest_firmware_version(self, version: str | None) -> None:
        """Store the latest firmware version reported by the update entity."""
        self._latest_firmware_version = version

    async def async_schedule_fetch_device_config(self) -> None:
        """Forget the stored config version to force get_config on next contact."""
        data = {**self._entry.data}
        data.pop(DATA_LAST_CONFIG_VERSION, None)
        options = {**self._entry.options, OPTIONS_UPDATE_CONFIG: False}
        self.hass.config_entries.async_update_entry(
            self._entry, data=data, options=options
        )

    @property
    def config_pending(self) -> bool:
        return bool(self._entry.options.get(OPTIONS_UPDATE_CONFIG, False))

    @property
    def auto_update(self) -> bool:
        return bool(self._entry.options.get(OPTIONS_AUTO_UPDATE, False))

    @property
    def config_version(self) -> int:
        return self._stored_config_version() or 0

    @property
    def firmware_version(self) -> str | None:
        return self._firmware_version

    @property
    def wifi_configured(self) -> bool | None:
        return self._wifi_configured

    @property
    def entry(self) -> ConfigEntry[PlantSenseData]:
        return self._entry

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
            sw_version=self._firmware_version,
            identifiers={(DOMAIN, self._device_id)},
        )
