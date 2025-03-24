"""The PlantSense integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components import mqtt
from homeassistant.const import Platform

from .const import DOMAIN, DOMAIN_MQTT_MANAGER
from .mqtt_manager import MqttManager

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

from .coordinator import PlantSenseCoordinator
from .data import PlantSenseData

PLATFORMS: list[Platform] = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PlantSense from a config entry."""
    # Make sure MQTT integration is enabled and the client is available.
    if not await mqtt.async_wait_for_mqtt_client(hass):
        _LOGGER.error("MQTT integration is not available")
        return False

    domain_data = hass.data.setdefault(DOMAIN, {})
    if DOMAIN_MQTT_MANAGER not in domain_data:
        mqtt_manager: MqttManager = MqttManager(hass)
        domain_data[DOMAIN_MQTT_MANAGER] = mqtt_manager
    else:
        mqtt_manager = domain_data[DOMAIN_MQTT_MANAGER]

    if not mqtt_manager.is_connected():
        await mqtt_manager.connect()

    coordinator = PlantSenseCoordinator(hass, entry)
    entry.runtime_data = PlantSenseData(coordinator=coordinator)
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading entry %s", entry.entry_id)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry if options change."""
    _LOGGER.debug("Reloading entry %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)
