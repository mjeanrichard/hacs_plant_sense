"""Button platform for PlantSense."""

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ENTITY_ID_FORMAT, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PlantSenseCoordinator

if TYPE_CHECKING:
    from .data import PlantSenseData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add button entities for passed config_entry in HA."""
    data: PlantSenseData = config_entry.runtime_data
    async_add_entities(
        [CancelConfigPushButton(hass=hass, coordinator=data.coordinator)]
    )


class CancelConfigPushButton(ButtonEntity):
    """Button to cancel a pending config push and revert to confirmed device values."""

    _coordinator: PlantSenseCoordinator

    def __init__(self, hass: HomeAssistant, coordinator: PlantSenseCoordinator) -> None:
        """Initialize the button."""
        self._coordinator = coordinator
        self._attr_should_poll = False
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_unique_id = f"{coordinator.device_id}_cancel_config_push"
        self._attr_icon = "mdi:cancel"
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, f"{coordinator.device_id}_cancel_config_push", hass=hass
        )

    @property
    def name(self) -> str:
        return f"{self._coordinator.device_name} Cancel Config Push"

    @property
    def available(self) -> bool:
        return self._coordinator.config_pending

    @property
    def device_info(self) -> DeviceInfo:
        return self._coordinator.device_info

    async def async_press(self) -> None:
        await self._coordinator.async_abort_config_push()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.entry.add_update_listener(self._handle_entry_update)
        )

    async def _handle_entry_update(
        self, _hass: HomeAssistant, _entry: ConfigEntry
    ) -> None:
        self.async_write_ha_state()
