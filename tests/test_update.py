"""Tests for the PlantSense firmware update entity."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.helpers.entity_component import async_update_entity
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .common import RELEASES_URL, async_send, data_message

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )
    from pytest_homeassistant_custom_component.typing import WebSocketGenerator

FIRMWARE = "update.plantsense_aabbccddeeff_firmware_update"


async def test_state_before_device_reported_firmware(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Latest version is known after setup; installed is unknown until contact."""
    state = hass.states.get(FIRMWARE)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["latest_version"] == "1.0"
    assert state.attributes["installed_version"] is None


@pytest.mark.parametrize(
    ("release_tag", "installed", "expected"),
    [
        ("v1.0", "1.0", STATE_OFF),
        ("v1.1", "1.0", STATE_ON),
        ("v1.1", "1.1-dev", STATE_OFF),  # the device would not install it
        ("v1.0", "1.1", STATE_OFF),
    ],
)
async def test_update_available(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    installed: str,
    expected: str,
) -> None:
    await async_send(hass, data_message(fw=installed))

    state = hass.states.get(FIRMWARE)
    assert state.state == expected
    assert state.attributes["installed_version"] == installed


async def test_release_attributes_and_notes(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    state = hass.states.get(FIRMWARE)
    assert (
        state.attributes["release_url"]
        == "https://github.com/mjeanrichard/LoraSensor/releases/v1.0"
    )

    client = await hass_ws_client(hass)
    await client.send_json(
        {"id": 1, "type": "update/release_notes", "entity_id": FIRMWARE}
    )
    result = await client.receive_json()
    assert result["success"]
    assert result["result"] == "Release notes"


async def test_github_polled_periodically(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    github_release: AiohttpClientMocker,
) -> None:
    calls = github_release.call_count
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=4, minutes=1))
    await hass.async_block_till_done()
    assert github_release.call_count == calls + 1


@pytest.mark.parametrize(
    "response",
    [
        {"status": 500},
        {"exc": TimeoutError()},
        {"text": "not json"},
        {"json": ["not", "an", "object"]},
    ],
)
async def test_github_failure_keeps_last_release(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    github_release: AiohttpClientMocker,
    response: dict,
) -> None:
    """A failed refresh must not wipe the known release (or block auto-update)."""
    github_release.clear_requests()
    github_release.get(RELEASES_URL, **response)

    await async_update_entity(hass, FIRMWARE)
    await hass.async_block_till_done()

    assert hass.states.get(FIRMWARE).attributes["latest_version"] == "1.0"
    coordinator = setup_integration.runtime_data.coordinator
    assert coordinator._latest_firmware_version == "1.0"


async def test_github_unavailable_at_startup(
    hass: HomeAssistant,
    github_release: AiohttpClientMocker,
    mqtt_mock: object,
    config_entry: MockConfigEntry,
) -> None:
    github_release.clear_requests()
    github_release.get(RELEASES_URL, status=404)

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(FIRMWARE)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["latest_version"] is None


@pytest.mark.parametrize("release_tag", [""])
async def test_release_without_tag(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    assert hass.states.get(FIRMWARE).attributes["latest_version"] is None
