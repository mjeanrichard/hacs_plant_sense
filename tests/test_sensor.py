"""Tests for the PlantSense sensor entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNKNOWN,
)
from homeassistant.helpers import entity_registry as er

from custom_components.plant_sense.const import (
    OPTIONS_UPDATE_CONFIG,
    OPTIONS_UPDATE_NAME,
)

from .common import CONFIG_VERSION, async_send, config_message, data_message

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

PREFIX = "sensor.plantsense_aabbccddeeff"


@pytest.mark.parametrize(
    ("suffix", "state", "unit", "device_class", "state_class"),
    [
        ("battery", "87", "%", SensorDeviceClass.BATTERY, SensorStateClass.MEASUREMENT),
        (
            "moisture",
            "42",
            "%",
            SensorDeviceClass.MOISTURE,
            SensorStateClass.MEASUREMENT,
        ),
        (
            "humidity",
            "55.2",
            "%",
            SensorDeviceClass.HUMIDITY,
            SensorStateClass.MEASUREMENT,
        ),
        (
            "temperature",
            "21.5",
            "°C",
            SensorDeviceClass.TEMPERATURE,
            SensorStateClass.MEASUREMENT,
        ),
        (
            "rssi",
            "-71",
            "dB",
            SensorDeviceClass.SIGNAL_STRENGTH,
            SensorStateClass.MEASUREMENT,
        ),
        ("snr", "9.5", None, None, SensorStateClass.MEASUREMENT),
        (
            "battery_volt",
            "3.91",
            "V",
            SensorDeviceClass.VOLTAGE,
            SensorStateClass.MEASUREMENT,
        ),
        ("moisture_raw", "1800", None, None, SensorStateClass.MEASUREMENT),
        ("test", "False", None, None, None),
    ],
)
async def test_measurement_sensors(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    suffix: str,
    state: str,
    unit: str | None,
    device_class: SensorDeviceClass | None,
    state_class: SensorStateClass | None,
) -> None:
    entity_id = f"{PREFIX}_{suffix}"
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    await async_send(hass, data_message(), gateway_fields={"rssi": -71, "snr": 9.5})

    sensor = hass.states.get(entity_id)
    assert sensor.state == state
    assert sensor.attributes.get(ATTR_UNIT_OF_MEASUREMENT) == unit
    assert sensor.attributes.get(ATTR_DEVICE_CLASS) == device_class
    assert sensor.attributes.get("state_class") == state_class


async def test_diagnostic_entities(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    registry = er.async_get(hass)
    for suffix in ("rssi", "snr", "test", "battery_volt", "moisture_raw"):
        entry = registry.async_get(f"{PREFIX}_{suffix}")
        assert entry.entity_category == er.EntityCategory.DIAGNOSTIC
    for suffix in ("battery", "moisture", "humidity", "temperature"):
        assert registry.async_get(f"{PREFIX}_{suffix}").entity_category is None


async def test_unique_ids(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    registry = er.async_get(hass)
    assert (
        registry.async_get(f"{PREFIX}_battery").unique_id
        == "PlantSense-aabbccddeeff_battery"
    )


async def test_missing_or_invalid_values_keep_last_state(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    await async_send(hass, data_message())
    message = data_message(moi={"nested": 1}, hum=None)
    del message["batPct"]
    await async_send(hass, message)

    assert hass.states.get(f"{PREFIX}_battery").state == "87"
    assert hass.states.get(f"{PREFIX}_moisture").state == "42"
    assert hass.states.get(f"{PREFIX}_humidity").state == "55.2"


async def test_sensor_names_follow_device_name(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    await async_send(hass, data_message())
    state = hass.states.get(f"{PREFIX}_battery")
    assert state.attributes[ATTR_FRIENDLY_NAME] == "PlantSense Basil Battery"

    await async_send(hass, config_message(v=CONFIG_VERSION + 1, name="Rosemary"))
    state = hass.states.get(f"{PREFIX}_battery")
    assert state.attributes[ATTR_FRIENDLY_NAME] == "PlantSense Rosemary Battery"


async def test_config_status_sensor(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    entity_id = f"{PREFIX}_config_pending"
    assert hass.states.get(entity_id).state == "synced"

    hass.config_entries.async_update_entry(
        setup_integration,
        options={
            **setup_integration.options,
            OPTIONS_UPDATE_NAME: "Rosemary",
            OPTIONS_UPDATE_CONFIG: True,
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "pending"

    await async_send(hass, config_message(v=CONFIG_VERSION + 1, name="Rosemary"))
    assert hass.states.get(entity_id).state == "synced"


async def test_config_version_sensor(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    entity_id = f"{PREFIX}_config_version"
    assert hass.states.get(entity_id).state == str(CONFIG_VERSION)

    await async_send(hass, config_message(v=CONFIG_VERSION + 2))
    assert hass.states.get(entity_id).state == str(CONFIG_VERSION + 2)


async def test_wifi_configured_sensor(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    entity_id = f"{PREFIX}_wifi_configured"
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    await async_send(hass, config_message(wifiSet=False))
    assert hass.states.get(entity_id).state == "not_configured"

    await async_send(hass, config_message(wifiSet=True))
    assert hass.states.get(entity_id).state == "configured"
