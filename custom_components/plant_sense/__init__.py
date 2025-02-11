"""The PlantSense integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components import mqtt
from homeassistant.const import Platform

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_SERIAL
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

    coordinator = PlantSenseCoordinator(
        hass, entry.unique_id, entry.data[CONF_DEVICE_SERIAL]
    )
    await coordinator.connect()
    entry.runtime_data = PlantSenseData(coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
