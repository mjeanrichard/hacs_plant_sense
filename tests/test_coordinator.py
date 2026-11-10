"""Tests for the config sync, OTA and sensor update logic of the coordinator."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from homeassistant.helpers import device_registry as dr

from custom_components.plant_sense.const import (
    CONF_DEVICE_SERIAL,
    DATA_CONFIRMED_MOI_DRY,
    DATA_CONFIRMED_MOI_WET,
    DATA_CONFIRMED_NAME,
    DATA_CONFIRMED_TEST_MODE,
    DATA_LAST_CONFIG_VERSION,
    DATA_WIFI_CONFIGURED,
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
from custom_components.plant_sense.coordinator import PlantSenseComponent

from .common import (
    CONFIG_VERSION,
    DEVICE_NAME,
    SERIAL,
    UNIQUE_ID,
    async_send,
    config_message,
    data_message,
    published_commands,
)

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry

BATTERY = "sensor.plantsense_aabbccddeeff_battery"

GET_CONFIG = {"id": SERIAL, "cmd": "get_config"}

# Options as they look after the user edited them in the options flow.
PENDING_OPTIONS = {
    OPTIONS_ENABLE_TEST: False,
    OPTIONS_UPDATE_NAME: "Rosemary",
    OPTIONS_UPDATE_TEST_MODE: True,
    OPTIONS_MOI_DRY: 2600,
    OPTIONS_MOI_WET: 650,
    OPTIONS_SSID: "MyNetwork",
    OPTIONS_WIFI_PWD: "secret",
    OPTIONS_AUTO_UPDATE: False,
    OPTIONS_UPDATE_CONFIG: True,
}


def _device(hass: HomeAssistant) -> dr.DeviceEntry:
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, UNIQUE_ID)})
    assert device is not None
    return device


# --- data messages & config version sync ------------------------------------


async def test_data_in_sync_sends_nothing(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """When the config versions match and nothing is pending, stay silent."""
    await async_send(hass, data_message())
    assert published_commands(mqtt_mock) == []


async def test_version_mismatch_requests_config(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """A device reporting a different config version is asked for its config."""
    await async_send(hass, data_message(v=CONFIG_VERSION + 1))
    assert published_commands(mqtt_mock) == [GET_CONFIG]


@pytest.mark.parametrize("entry_options", [PENDING_OPTIONS])
async def test_version_mismatch_discards_pending_push(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """A pending push is reverted to the confirmed values on version mismatch."""
    entry = setup_integration
    await async_send(hass, data_message(v=CONFIG_VERSION + 1))

    assert published_commands(mqtt_mock) == [GET_CONFIG]
    assert entry.options[OPTIONS_UPDATE_CONFIG] is False
    assert entry.options[OPTIONS_UPDATE_NAME] == DEVICE_NAME
    assert entry.options[OPTIONS_UPDATE_TEST_MODE] is False
    assert entry.options[OPTIONS_MOI_DRY] == 2700
    assert entry.options[OPTIONS_MOI_WET] == 700
    assert entry.options[OPTIONS_WIFI_PWD] == ""


@pytest.mark.parametrize("entry_data", [{CONF_DEVICE_SERIAL: SERIAL}])
@pytest.mark.parametrize("device_version", [0, 5])
async def test_never_synced_entry_requests_config(
    hass: HomeAssistant,
    mqtt_mock: MagicMock,
    setup_integration: MockConfigEntry,
    device_version: int,
) -> None:
    """A fresh entry fetches the device config, even if the device reports v=0."""
    await async_send(hass, data_message(v=device_version))
    assert published_commands(mqtt_mock) == [GET_CONFIG]


@pytest.mark.parametrize("entry_data", [{CONF_DEVICE_SERIAL: SERIAL}])
@pytest.mark.parametrize("entry_options", [PENDING_OPTIONS])
async def test_never_synced_entry_does_not_push_form_defaults(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """Options edited before the first sync are never pushed to the device."""
    await async_send(hass, data_message(v=0))
    assert published_commands(mqtt_mock) == [GET_CONFIG]
    assert setup_integration.options[OPTIONS_UPDATE_CONFIG] is False


@pytest.mark.parametrize(
    "entry_data",
    [{CONF_DEVICE_SERIAL: SERIAL, DATA_LAST_CONFIG_VERSION: "garbage"}],
)
async def test_corrupt_stored_version_requests_config(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    await async_send(hass, data_message())
    assert published_commands(mqtt_mock) == [GET_CONFIG]


@pytest.mark.parametrize("version", ["missing", str(CONFIG_VERSION), None])
async def test_missing_or_invalid_device_version_is_treated_as_zero(
    hass: HomeAssistant,
    mqtt_mock: MagicMock,
    setup_integration: MockConfigEntry,
    version: str | None,
) -> None:
    message = data_message(v=version)
    if version == "missing":
        del message["v"]
    await async_send(hass, message)
    assert published_commands(mqtt_mock) == [GET_CONFIG]


@pytest.mark.parametrize("entry_options", [PENDING_OPTIONS])
async def test_pending_config_is_pushed(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """With matching versions a pending config is sent, and resent until confirmed."""
    await async_send(hass, data_message())
    await async_send(hass, data_message())

    expected = {
        "id": SERIAL,
        "cmd": "set_config",
        "test": True,
        "name": "Rosemary",
        "moiDry": 2600,
        "moiWet": 650,
        "ssid": "MyNetwork",
        "wifiPwd": "secret",
    }
    assert published_commands(mqtt_mock) == [expected, expected]
    assert setup_integration.options[OPTIONS_UPDATE_CONFIG] is True


@pytest.mark.parametrize(
    "entry_options",
    [PENDING_OPTIONS | {OPTIONS_SSID: "", OPTIONS_WIFI_PWD: ""}],
)
async def test_pending_config_without_wifi(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """Empty WiFi credentials are not sent (so they don't wipe the device's)."""
    await async_send(hass, data_message())
    (command,) = published_commands(mqtt_mock)
    assert "ssid" not in command
    assert "wifiPwd" not in command


async def test_downlink_is_json_in_json(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """The gateway expects the LoRa command as a JSON string in 'message'."""
    await async_send(hass, data_message(v=CONFIG_VERSION + 1))
    payload = mqtt_mock.async_publish.call_args.args[1]
    if isinstance(payload, bytes):
        payload = payload.decode()
    assert (
        payload
        == '{"message": "{\\"id\\": \\"aabbccddeeff\\", \\"cmd\\": \\"get_config\\"}"}'
    )


# --- config messages ----------------------------------------------------------


@pytest.mark.parametrize("entry_options", [PENDING_OPTIONS])
async def test_new_config_is_stored(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """A config uplink with a new version updates entry, title and device."""
    entry = setup_integration
    await async_send(
        hass,
        config_message(
            v=CONFIG_VERSION + 1,
            name="Rosemary",
            test=True,
            moiDry=2600,
            moiWet=650,
            fw="1.1",
        ),
    )

    assert entry.title == "PlantSense Rosemary"
    assert entry.data[DATA_LAST_CONFIG_VERSION] == CONFIG_VERSION + 1
    assert entry.data[DATA_CONFIRMED_NAME] == "Rosemary"
    assert entry.data[DATA_CONFIRMED_TEST_MODE] is True
    assert entry.data[DATA_CONFIRMED_MOI_DRY] == 2600
    assert entry.data[DATA_CONFIRMED_MOI_WET] == 650
    assert entry.options[OPTIONS_UPDATE_CONFIG] is False
    assert entry.options[OPTIONS_UPDATE_NAME] == "Rosemary"
    assert entry.options[OPTIONS_UPDATE_TEST_MODE] is True
    assert entry.options[OPTIONS_MOI_DRY] == 2600
    assert entry.options[OPTIONS_MOI_WET] == 650
    # The WiFi password is dropped once the device has confirmed the config.
    assert entry.options[OPTIONS_WIFI_PWD] == ""
    assert entry.options[OPTIONS_SSID] == "MyNetwork"

    device = _device(hass)
    assert device.name == "PlantSense Rosemary"
    assert device.sw_version == "1.1"
    assert entry.runtime_data.coordinator.device_name == "PlantSense Rosemary"

    # Config is synced now: the next data packet doesn't trigger any command.
    await async_send(hass, data_message(v=CONFIG_VERSION + 1))
    assert published_commands(mqtt_mock) == []


@pytest.mark.parametrize("entry_options", [PENDING_OPTIONS])
async def test_same_config_version_is_ignored(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """A config uplink with the stored version doesn't touch the options."""
    entry = setup_integration
    await async_send(hass, config_message(name="Other"))

    assert entry.title == f"PlantSense {DEVICE_NAME}"
    assert entry.options[OPTIONS_UPDATE_CONFIG] is True
    assert entry.options[OPTIONS_UPDATE_NAME] == "Rosemary"
    assert entry.options[OPTIONS_WIFI_PWD] == "secret"


@pytest.mark.parametrize("entry_data", [{CONF_DEVICE_SERIAL: SERIAL}])
async def test_first_config_is_stored_even_for_version_zero(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    entry = setup_integration
    await async_send(hass, config_message(v=0, name="Mint"))

    assert entry.data[DATA_LAST_CONFIG_VERSION] == 0
    assert entry.options[OPTIONS_UPDATE_NAME] == "Mint"
    assert entry.options[OPTIONS_MOI_DRY] == 2700


async def test_config_without_calibration_keeps_existing_values(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    entry = setup_integration
    message = config_message(v=CONFIG_VERSION + 1)
    del message["moiDry"]
    del message["moiWet"]
    await async_send(hass, message)

    assert entry.options[OPTIONS_MOI_DRY] == 2700
    assert entry.options[OPTIONS_MOI_WET] == 700
    assert entry.data[DATA_CONFIRMED_MOI_DRY] == 2700


async def test_config_with_invalid_types(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Invalid field types fall back to safe defaults."""
    entry = setup_integration
    await async_send(
        hass,
        config_message(v="x", test="yes", moiDry="dry", moiWet=None, wifiSet="maybe"),
    )

    assert entry.data[DATA_LAST_CONFIG_VERSION] == 0
    assert entry.options[OPTIONS_UPDATE_TEST_MODE] is False
    assert entry.options[OPTIONS_MOI_DRY] == 2700
    assert entry.options[OPTIONS_MOI_WET] == 700
    assert entry.runtime_data.coordinator.wifi_configured is None


async def test_wifi_state_is_tracked_and_persisted(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """WiFi state updates from any config uplink and survives a reload."""
    entry = setup_integration
    # Same config version: options untouched, but WiFi state still recorded.
    await async_send(hass, config_message(wifiSet=True))
    assert entry.runtime_data.coordinator.wifi_configured is True
    assert entry.data[DATA_WIFI_CONFIGURED] is True

    await async_send(hass, config_message(wifiSet=False))
    assert entry.runtime_data.coordinator.wifi_configured is False

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.coordinator.wifi_configured is False


# --- data handling ------------------------------------------------------------


async def test_test_data_is_skipped_by_default(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """Test-mode data doesn't update sensors, but config sync still happens."""
    await async_send(hass, data_message(test=True, v=CONFIG_VERSION + 1))

    assert hass.states.get(BATTERY).state == "unknown"
    assert setup_integration.runtime_data.coordinator.last_data is None
    assert published_commands(mqtt_mock) == [GET_CONFIG]


@pytest.mark.parametrize(
    "entry_options", [{OPTIONS_ENABLE_TEST: True, OPTIONS_UPDATE_CONFIG: False}]
)
async def test_test_data_is_used_when_enabled(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    await async_send(hass, data_message(test=True))
    assert hass.states.get(BATTERY).state == "87"


async def test_firmware_version_from_data_and_wifi_messages(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    coordinator = setup_integration.runtime_data.coordinator

    await async_send(hass, data_message(fw="1.0"))
    assert coordinator.firmware_version == "1.0"
    assert _device(hass).sw_version == "1.0"

    await async_send(
        hass,
        {
            "model": "PlantSense",
            "msg": "wifi",
            "id": SERIAL,
            "name": DEVICE_NAME,
            "test": False,
            "wifiRssi": -60,
            "uptime": 12,
            "fw": "1.1",
        },
    )
    assert coordinator.firmware_version == "1.1"
    assert _device(hass).sw_version == "1.1"


async def test_unknown_message_type_is_ignored(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    await async_send(hass, data_message(msg="something"))
    assert hass.states.get(BATTERY).state == "unknown"
    assert published_commands(mqtt_mock) == []


async def test_failing_component_does_not_block_others(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """One broken component must not prevent the other entities from updating."""

    class Broken(PlantSenseComponent):
        async def update_async(self) -> None:
            msg = "boom"
            raise RuntimeError(msg)

    coordinator = setup_integration.runtime_data.coordinator
    broken = Broken()
    coordinator._components.insert(0, broken)  # run first

    await async_send(hass, data_message())
    assert hass.states.get(BATTERY).state == "87"

    coordinator.remove_component(broken)


# --- firmware auto-update -----------------------------------------------------

AUTO_UPDATE_OPTIONS: dict[str, Any] = {
    OPTIONS_AUTO_UPDATE: True,
    OPTIONS_UPDATE_CONFIG: False,
}


@pytest.mark.parametrize("entry_options", [AUTO_UPDATE_OPTIONS])
@pytest.mark.parametrize(
    ("release_tag", "installed", "expected"),
    [
        ("v1.1", "1.0", [{"id": SERIAL, "cmd": "ota", "version": "1.1"}]),
        ("v1.0", "1.0", []),
        ("v1.0", "1.0-dev", []),
        ("v1.1", "1.2-dev", []),
    ],
)
async def test_auto_update(
    hass: HomeAssistant,
    mqtt_mock: MagicMock,
    setup_integration: MockConfigEntry,
    installed: str,
    expected: list[dict[str, Any]],
) -> None:
    """OTA is only sent if the release is newer by the device's own rules."""
    await async_send(hass, data_message(fw=installed))
    assert published_commands(mqtt_mock) == expected


@pytest.mark.parametrize("release_tag", ["v1.1"])
async def test_no_auto_update_when_disabled(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    await async_send(hass, data_message(fw="1.0"))
    assert published_commands(mqtt_mock) == []


@pytest.mark.parametrize("entry_options", [AUTO_UPDATE_OPTIONS])
@pytest.mark.parametrize("release_tag", ["v1.1"])
async def test_no_auto_update_without_wifi(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """Without WiFi credentials the device can't download the firmware."""
    await async_send(hass, config_message(wifiSet=False))
    await async_send(hass, data_message(fw="1.0"))
    assert published_commands(mqtt_mock) == []


@pytest.mark.parametrize(
    "entry_options", [PENDING_OPTIONS | {OPTIONS_AUTO_UPDATE: True}]
)
@pytest.mark.parametrize("release_tag", ["v1.1"])
async def test_config_push_takes_precedence_over_ota(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    await async_send(hass, data_message(fw="1.0"))
    (command,) = published_commands(mqtt_mock)
    assert command["cmd"] == "set_config"


# --- coordinator API used by the buttons -----------------------------------------


@pytest.mark.parametrize("entry_options", [PENDING_OPTIONS])
async def test_abort_config_push(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    entry = setup_integration
    await entry.runtime_data.coordinator.async_abort_config_push()

    assert entry.options[OPTIONS_UPDATE_CONFIG] is False
    assert entry.options[OPTIONS_UPDATE_NAME] == DEVICE_NAME
    assert entry.options[OPTIONS_UPDATE_TEST_MODE] is False
    assert entry.options[OPTIONS_MOI_DRY] == 2700
    assert entry.options[OPTIONS_MOI_WET] == 700
    assert entry.options[OPTIONS_WIFI_PWD] == ""


async def test_abort_without_pending_push_is_noop(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    entry = setup_integration
    before = dict(entry.options)
    await entry.runtime_data.coordinator.async_abort_config_push()
    assert dict(entry.options) == before


@pytest.mark.parametrize("entry_options", [PENDING_OPTIONS])
async def test_schedule_fetch_device_config(
    hass: HomeAssistant, mqtt_mock: MagicMock, setup_integration: MockConfigEntry
) -> None:
    """After 'fetch', the next contact requests the config even if versions match."""
    entry = setup_integration
    coordinator = entry.runtime_data.coordinator
    await coordinator.async_schedule_fetch_device_config()

    assert DATA_LAST_CONFIG_VERSION not in entry.data
    assert coordinator.config_version == 0
    assert entry.options[OPTIONS_UPDATE_CONFIG] is False

    await async_send(hass, data_message())
    assert published_commands(mqtt_mock) == [GET_CONFIG]

    await async_send(hass, config_message(name="Thyme"))
    assert entry.data[DATA_LAST_CONFIG_VERSION] == CONFIG_VERSION
    assert entry.options[OPTIONS_UPDATE_NAME] == "Thyme"
