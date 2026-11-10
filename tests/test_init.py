"""Tests for setting up and unloading the PlantSense integration."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_sense.const import (
    CONF_DEVICE_SERIAL,
    DOMAIN,
    DOMAIN_MQTT_MANAGER,
    MQTT_SUBSCRIBE_TOPIC,
)
from custom_components.plant_sense.coordinator import PlantSenseCoordinator
from custom_components.plant_sense.data import PlantSenseData
from custom_components.plant_sense.helpers import build_unique_id

from .common import SERIAL, UNIQUE_ID, async_send, data_message

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant


def _second_entry() -> MockConfigEntry:
    serial = "112233445566"
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=build_unique_id(serial),
        title="PlantSense Second",
        data={CONF_DEVICE_SERIAL: serial},
    )


async def test_setup_entry(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """Setting up an entry subscribes to MQTT and creates device and entities."""
    entry = setup_integration
    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, PlantSenseData)
    assert isinstance(entry.runtime_data.coordinator, PlantSenseCoordinator)

    mqtt_mock.async_subscribe.assert_called()
    assert any(
        call.args[0] == MQTT_SUBSCRIBE_TOPIC
        for call in mqtt_mock.async_subscribe.call_args_list
    )
    assert hass.data[DOMAIN][DOMAIN_MQTT_MANAGER].is_connected()

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, UNIQUE_ID)})
    assert device is not None
    assert device.serial_number == SERIAL
    assert device.manufacturer == "Jean-Richard"
    assert device.model == "PlantSense"

    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    platforms = {entity.domain for entity in entities}
    assert platforms == {"sensor", "button", "update"}
    expected_entity_count = 15  # 12 sensors, 2 buttons, 1 update
    assert len(entities) == expected_entity_count


async def test_setup_retries_when_mqtt_unavailable(
    hass: HomeAssistant, mqtt_mock: MagicMock, config_entry: MockConfigEntry
) -> None:
    """If the MQTT client is not available, setup is retried later."""
    config_entry.add_to_hass(hass)
    with patch(
        "custom_components.plant_sense.mqtt.async_wait_for_mqtt_client",
        return_value=False,
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert DOMAIN_MQTT_MANAGER not in hass.data.get(DOMAIN, {})


async def test_entries_share_one_mqtt_manager(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """A second device reuses the existing subscription."""
    manager = hass.data[DOMAIN][DOMAIN_MQTT_MANAGER]
    subscribe_calls = mqtt_mock.async_subscribe.call_count

    second = _second_entry()
    second.add_to_hass(hass)
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()

    assert hass.data[DOMAIN][DOMAIN_MQTT_MANAGER] is manager
    assert mqtt_mock.async_subscribe.call_count == subscribe_calls


async def test_unload_last_entry_releases_subscription(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """Unloading keeps the subscription while other entries are still loaded."""
    second = _second_entry()
    second.add_to_hass(hass)
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()
    manager = hass.data[DOMAIN][DOMAIN_MQTT_MANAGER]

    assert await hass.config_entries.async_unload(second.entry_id)
    await hass.async_block_till_done()
    assert second.state is ConfigEntryState.NOT_LOADED
    assert manager.is_connected()

    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()
    assert setup_integration.state is ConfigEntryState.NOT_LOADED
    assert not manager.is_connected()
    assert DOMAIN_MQTT_MANAGER not in hass.data[DOMAIN]

    # Messages are no longer processed: no discovery flow for unknown devices.
    await async_send(hass, data_message(id="ffeeddccbbaa"))
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


async def test_reload_after_unload_resubscribes(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """Setting the entry up again after a full unload subscribes again."""
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_setup(setup_integration.entry_id)
    await hass.async_block_till_done()

    assert hass.data[DOMAIN][DOMAIN_MQTT_MANAGER].is_connected()
    await async_send(hass, data_message())
    assert hass.states.get("sensor.plantsense_aabbccddeeff_battery").state == "87"
