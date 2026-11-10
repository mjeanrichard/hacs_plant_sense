"""The PlantSense integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components import mqtt
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, DOMAIN_MQTT_MANAGER
from .mqtt_manager import MqttManager

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

from .coordinator import PlantSenseCoordinator
from .data import PlantSenseData

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.SENSOR, Platform.UPDATE]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PlantSense from a config entry."""
    # Make sure MQTT integration is enabled and the client is available.
    if not await mqtt.async_wait_for_mqtt_client(hass):
        msg = "MQTT integration is not available"
        raise ConfigEntryNotReady(msg)

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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading entry %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    still_loaded = [
        other
        for other in hass.config_entries.async_loaded_entries(DOMAIN)
        if other.entry_id != entry.entry_id
    ]
    if not still_loaded:
        mqtt_manager: MqttManager | None = hass.data.get(DOMAIN, {}).pop(
            DOMAIN_MQTT_MANAGER, None
        )
        if mqtt_manager is not None:
            mqtt_manager.disconnect()

    return True
