"""Tests for parsing and routing of MQTT uplinks."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_sense.const import (
    CONF_DEVICE_SERIAL,
    DATA_LAST_CONFIG_VERSION,
    DOMAIN,
)
from custom_components.plant_sense.helpers import build_unique_id

from .common import async_send, data_message

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant

BATTERY = "sensor.plantsense_aabbccddeeff_battery"
RSSI = "sensor.plantsense_aabbccddeeff_rssi"
SNR = "sensor.plantsense_aabbccddeeff_snr"
UNKNOWN_SERIAL = "ffeeddccbbaa"


def _discovery_flows(hass: HomeAssistant) -> list:
    return [
        flow
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        if flow["context"]["source"] == SOURCE_INTEGRATION_DISCOVERY
    ]


async def test_plain_json_message_is_routed(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A JSON uplink for a known device updates its sensors."""
    await async_send(hass, data_message())
    assert hass.states.get(BATTERY).state == "87"


async def test_hex_message_is_decoded_and_merged(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Hex-encoded payloads are decoded and merged with the gateway's own fields."""
    await async_send(
        hass,
        data_message(batPct=55),
        as_hex=True,
        gateway_fields={"rssi": -99, "snr": 4.25},
    )
    assert hass.states.get(BATTERY).state == "55"
    assert hass.states.get(RSSI).state == "-99"
    assert hass.states.get(SNR).state == "4.25"


async def test_hex_payload_wins_over_gateway_fields(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Fields inside the decoded payload override the outer message."""
    await async_send(
        hass, data_message(batPct=12), as_hex=True, gateway_fields={"batPct": 99}
    )
    assert hass.states.get(BATTERY).state == "12"


async def test_bytes_payload(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Raw bytes payloads are accepted as well."""
    await async_send(hass, json.dumps(data_message(batPct=33)).encode())
    assert hass.states.get(BATTERY).state == "33"


async def test_invalid_payloads_are_ignored(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Garbage on the topic must neither crash nor start discovery."""
    for payload in (
        "not json",
        "[1, 2, 3]",
        '"string"',
        json.dumps({"hex": "zz-not-hex"}),
        json.dumps({"hex": "5b315d"}),  # hex of "[1]" - not an object
        json.dumps({"hex": "ffff"}),  # not valid UTF-8 / JSON
        json.dumps({"model": "SomethingElse", "id": UNKNOWN_SERIAL}),
        json.dumps({"model": "PlantSense", "msg": "data"}),  # no id
        json.dumps({"model": "PlantSense", "msg": "data", "id": 1234}),
    ):
        await async_send(hass, payload)

    assert hass.states.get(BATTERY).state == "unknown"
    assert not _discovery_flows(hass)


async def test_non_string_hex_falls_back_to_outer_message(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A non-string 'hex' field is ignored and the outer message still handled."""
    await async_send(hass, data_message(hex=1234, batPct=21))
    assert hass.states.get(BATTERY).state == "21"


async def test_message_for_other_device_does_not_touch_entities(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Data from another device is not applied to this device's entities."""
    await async_send(hass, data_message(id=UNKNOWN_SERIAL))
    assert hass.states.get(BATTERY).state == "unknown"


async def test_unknown_device_starts_discovery_once(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """An unknown device triggers a single discovery flow, even if it keeps sending."""
    await async_send(hass, data_message(id=UNKNOWN_SERIAL, name="Fern"))
    await async_send(hass, data_message(id=UNKNOWN_SERIAL, name="Fern"))

    flows = _discovery_flows(hass)
    assert len(flows) == 1
    assert flows[0]["step_id"] == "integration_discovery_confirm"
    assert flows[0]["context"]["unique_id"] == build_unique_id(UNKNOWN_SERIAL)
    assert flows[0]["context"]["title_placeholders"] == {
        "devicename": "Fern",
        "serial": UNKNOWN_SERIAL,
    }


async def test_unknown_device_without_name(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A missing or invalid name falls back to '-'."""
    await async_send(hass, data_message(id=UNKNOWN_SERIAL, name=None))

    flows = _discovery_flows(hass)
    assert len(flows) == 1
    assert flows[0]["context"]["title_placeholders"]["devicename"] == "-"


async def test_message_for_unloaded_entry_is_ignored(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """A known device whose entry is not loaded is neither routed nor rediscovered."""
    other_serial = "112233445566"
    other = MockConfigEntry(
        domain=DOMAIN,
        unique_id=build_unique_id(other_serial),
        title="PlantSense Other",
        data={CONF_DEVICE_SERIAL: other_serial, DATA_LAST_CONFIG_VERSION: 1},
    )
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(other.entry_id)
    await hass.async_block_till_done()
    mqtt_mock.async_publish.reset_mock()

    await async_send(hass, data_message(id=other_serial, v=2))

    # No get_config was sent for the unloaded device and no new flow started.
    mqtt_mock.async_publish.assert_not_called()
    assert not _discovery_flows(hass)
