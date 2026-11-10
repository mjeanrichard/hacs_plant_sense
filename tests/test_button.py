"""Tests for the PlantSense button entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.button import SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE

from custom_components.plant_sense.const import (
    DATA_LAST_CONFIG_VERSION,
    OPTIONS_UPDATE_CONFIG,
    OPTIONS_UPDATE_NAME,
    OPTIONS_WIFI_PWD,
)

from .common import DEVICE_NAME, async_send, data_message, published_commands

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

CANCEL = "button.plantsense_aabbccddeeff_cancel_config_push"
FETCH = "button.plantsense_aabbccddeeff_fetch_device_config"


async def _press(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    await hass.async_block_till_done()


async def _schedule_push(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            OPTIONS_UPDATE_NAME: "Rosemary",
            OPTIONS_WIFI_PWD: "secret",
            OPTIONS_UPDATE_CONFIG: True,
        },
    )
    await hass.async_block_till_done()


async def test_cancel_button_availability_follows_pending_push(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    assert hass.states.get(CANCEL).state == STATE_UNAVAILABLE

    await _schedule_push(hass, setup_integration)
    assert hass.states.get(CANCEL).state != STATE_UNAVAILABLE


async def test_cancel_button_reverts_options(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    entry = setup_integration
    await _schedule_push(hass, entry)

    await _press(hass, CANCEL)

    assert entry.options[OPTIONS_UPDATE_CONFIG] is False
    assert entry.options[OPTIONS_UPDATE_NAME] == DEVICE_NAME
    assert entry.options[OPTIONS_WIFI_PWD] == ""
    assert hass.states.get(CANCEL).state == STATE_UNAVAILABLE

    # Nothing is pushed on the next contact.
    await async_send(hass, data_message())
    assert published_commands(mqtt_mock) == []


async def test_fetch_button_requests_config_on_next_contact(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    entry = setup_integration
    await _schedule_push(hass, entry)

    await _press(hass, FETCH)

    assert DATA_LAST_CONFIG_VERSION not in entry.data
    assert entry.options[OPTIONS_UPDATE_CONFIG] is False
    assert published_commands(mqtt_mock) == []  # nothing until the device is online

    await async_send(hass, data_message())
    assert published_commands(mqtt_mock) == [
        {"id": "aabbccddeeff", "cmd": "get_config"}
    ]


@pytest.mark.parametrize("entity_id", [CANCEL, FETCH])
async def test_button_names(
    hass: HomeAssistant, setup_integration: MockConfigEntry, entity_id: str
) -> None:
    name = hass.states.get(entity_id).attributes["friendly_name"]
    assert name.startswith(f"PlantSense {DEVICE_NAME} ")
