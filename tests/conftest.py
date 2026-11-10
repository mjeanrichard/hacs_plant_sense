"""Shared fixtures for the PlantSense tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.util.async_ import get_scheduled_timer_handles
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_sense.const import (
    CONF_DEVICE_SERIAL,
    DATA_CONFIRMED_MOI_DRY,
    DATA_CONFIRMED_MOI_WET,
    DATA_CONFIRMED_NAME,
    DATA_CONFIRMED_TEST_MODE,
    DATA_LAST_CONFIG_VERSION,
    DOMAIN,
    OPTIONS_AUTO_UPDATE,
    OPTIONS_ENABLE_TEST,
    OPTIONS_MOI_DRY,
    OPTIONS_MOI_WET,
    OPTIONS_SSID,
    OPTIONS_UPDATE_CONFIG,
    OPTIONS_UPDATE_NAME,
    OPTIONS_UPDATE_TEST_MODE,
    OPTIONS_WIFI_PWD,
)

from .common import CONFIG_VERSION, DEVICE_NAME, RELEASES_URL, SERIAL, UNIQUE_ID

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.test_util.aiohttp import (
        AiohttpClientMocker,
    )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow loading custom_components/ in every test."""


@pytest.fixture(autouse=True)
def no_command_delay() -> Generator[None]:
    """Don't wait before publishing downlink commands."""
    with patch("custom_components.plant_sense.coordinator.COMMAND_DELAY_SECONDS", 0):
        yield


@pytest.fixture
def release_tag() -> str:
    """Latest firmware release tag on GitHub (override with parametrize)."""
    return "v1.0"


@pytest.fixture(autouse=True)
def github_release(
    aioclient_mock: AiohttpClientMocker, release_tag: str
) -> AiohttpClientMocker:
    """Answer the firmware update entity's GitHub request (no network in tests)."""
    aioclient_mock.get(
        RELEASES_URL,
        json={
            "tag_name": release_tag,
            "html_url": f"https://github.com/mjeanrichard/LoraSensor/releases/{release_tag}",
            "body": "Release notes",
        },
    )
    return aioclient_mock


@pytest.fixture
async def mqtt_mock(
    hass: HomeAssistant, mqtt_mock: MagicMock
) -> AsyncGenerator[MagicMock]:
    """
    Wrap the harness' mqtt_mock and stop HA's MQTT misc-loop timer afterwards.

    The mocked paho client "opens" a socket on connect but never closes it, so
    the MQTT client's periodic misc timer would otherwise be reported as a
    lingering timer. Only that timer is cancelled; all other lingering timers
    still fail the test.
    """
    yield mqtt_mock
    for handle in get_scheduled_timer_handles(hass.loop):
        if "_async_start_misc_periodic" in repr(handle):
            handle.cancel()


@pytest.fixture
def entry_data() -> dict[str, Any]:
    """Config entry data of a device whose config has been synced."""
    return {
        CONF_DEVICE_SERIAL: SERIAL,
        DATA_LAST_CONFIG_VERSION: CONFIG_VERSION,
        DATA_CONFIRMED_NAME: DEVICE_NAME,
        DATA_CONFIRMED_TEST_MODE: False,
        DATA_CONFIRMED_MOI_DRY: 2700,
        DATA_CONFIRMED_MOI_WET: 700,
    }


@pytest.fixture
def entry_options() -> dict[str, Any]:
    """Config entry options matching the synced device config."""
    return {
        OPTIONS_ENABLE_TEST: False,
        OPTIONS_UPDATE_NAME: DEVICE_NAME,
        OPTIONS_UPDATE_TEST_MODE: False,
        OPTIONS_MOI_DRY: 2700,
        OPTIONS_MOI_WET: 700,
        OPTIONS_SSID: "",
        OPTIONS_WIFI_PWD: "",
        OPTIONS_AUTO_UPDATE: False,
        OPTIONS_UPDATE_CONFIG: False,
    }


@pytest.fixture
def config_entry(
    entry_data: dict[str, Any], entry_options: dict[str, Any]
) -> MockConfigEntry:
    """Return a (not yet added) PlantSense config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=UNIQUE_ID,
        title=f"PlantSense {DEVICE_NAME}",
        data=entry_data,
        options=entry_options,
    )


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, mqtt_mock: MagicMock, config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up MQTT and the PlantSense config entry."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    mqtt_mock.async_publish.reset_mock()
    return config_entry
