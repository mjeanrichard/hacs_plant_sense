"""Firmware update platform for PlantSense."""

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

import aiohttp
from homeassistant.components.update import (
    ENTITY_ID_FORMAT,
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo, async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import FIRMWARE_CHECK_INTERVAL_HOURS, FIRMWARE_GITHUB_REPO
from .coordinator import PlantSenseComponent, PlantSenseCoordinator

if TYPE_CHECKING:
    from .data import PlantSenseData

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(hours=FIRMWARE_CHECK_INTERVAL_HOURS)
PARALLEL_UPDATES = 1

_RELEASES_URL = f"https://api.github.com/repos/{FIRMWARE_GITHUB_REPO}/releases/latest"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add update entity for passed config_entry in HA."""
    data: PlantSenseData = config_entry.runtime_data
    async_add_entities(
        [PlantSenseFirmwareUpdate(hass=hass, coordinator=data.coordinator)],
        update_before_add=True,
    )


class PlantSenseFirmwareUpdate(UpdateEntity, PlantSenseComponent):
    """Update entity that tracks and installs PlantSense firmware releases."""

    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature.RELEASE_NOTES
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = True

    _release_notes_cache: str | None = None

    def __init__(self, hass: HomeAssistant, coordinator: PlantSenseCoordinator) -> None:
        """Initialize the firmware update entity."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.device_id}_firmware_update"
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, f"{coordinator.device_id}_firmware_update", hass=hass
        )

    @property
    def name(self) -> str:
        return f"{self._coordinator.device_name} Firmware"

    @property
    def installed_version(self) -> str | None:
        return self._coordinator.firmware_version

    @property
    def device_info(self) -> DeviceInfo:
        return self._coordinator.device_info

    async def update_async(self) -> None:
        """Refresh state when coordinator receives new MQTT data."""
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Fetch the latest firmware release from GitHub."""
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                _RELEASES_URL,
                headers={"Accept": "application/vnd.github+json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError):
            _LOGGER.warning(
                "Failed to fetch latest firmware version from GitHub (%s)",
                _RELEASES_URL,
            )
            self._attr_latest_version = None
            self._release_notes_cache = None
            return

        tag = data.get("tag_name", "")
        self._attr_latest_version = tag.lstrip("v") if tag else None
        self._attr_release_url = data.get("html_url")
        self._release_notes_cache = data.get("body")
        self._coordinator.set_latest_firmware_version(self._attr_latest_version)

    async def async_release_notes(self) -> str | None:
        return self._release_notes_cache

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_component(self)

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.remove_component(self)
