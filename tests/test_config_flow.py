"""Tests for the config and options flows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.plant_sense.const import (
    CONF_DEVICE_SERIAL,
    DISCOVERY_NAME,
    DISCOVERY_SERIAL,
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

from .common import DEVICE_NAME, SERIAL, UNIQUE_ID

if TYPE_CHECKING:
    from collections.abc import Generator

    from homeassistant.core import HomeAssistant


@pytest.fixture(autouse=True)
def no_entry_setup() -> Generator[MagicMock]:
    """Don't set up the entry created by a flow (that's covered elsewhere)."""
    with patch(
        "custom_components.plant_sense.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


# --- user flow ----------------------------------------------------------------


async def test_user_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_SERIAL: f"  {SERIAL} "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == UNIQUE_ID
    assert result["data"] == {CONF_DEVICE_SERIAL: SERIAL}
    assert result["result"].unique_id == UNIQUE_ID


async def test_user_flow_rejects_empty_serial(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_SERIAL: "   "}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_DEVICE_SERIAL: "invalid_serial"}

    # The user can correct the input.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_SERIAL: SERIAL}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=UNIQUE_ID).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_SERIAL: SERIAL}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# --- integration discovery ------------------------------------------------------


async def test_discovery_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={DISCOVERY_SERIAL: SERIAL, DISCOVERY_NAME: DEVICE_NAME},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "integration_discovery_confirm"
    assert result["description_placeholders"] == {
        "devicename": DEVICE_NAME,
        "serial": SERIAL,
    }

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"PlantSense {DEVICE_NAME}"
    assert result["data"] == {CONF_DEVICE_SERIAL: SERIAL}
    assert result["result"].unique_id == UNIQUE_ID


async def test_discovery_without_name(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={DISCOVERY_SERIAL: SERIAL},
    )
    assert result["description_placeholders"]["devicename"] == "-"


async def test_discovery_already_configured(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=UNIQUE_ID).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={DISCOVERY_SERIAL: SERIAL, DISCOVERY_NAME: DEVICE_NAME},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize("serial", ["", None])
async def test_discovery_without_serial(
    hass: HomeAssistant, serial: str | None
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={DISCOVERY_SERIAL: serial},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_flow_while_discovery_in_progress(hass: HomeAssistant) -> None:
    """Adding a device manually that is already discovered points to the discovery."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={DISCOVERY_SERIAL: SERIAL, DISCOVERY_NAME: DEVICE_NAME},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_DEVICE_SERIAL: SERIAL}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_in_progress"

    # The discovered flow is still there and can be confirmed.
    (flow,) = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


# --- options flow -----------------------------------------------------------------

SYNCED_OPTIONS: dict[str, Any] = {
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


def _form_input(**changes: Any) -> dict[str, Any]:
    """Return what the options form submits when only ``changes`` were edited."""
    values = {
        key: value
        for key, value in SYNCED_OPTIONS.items()
        if key != OPTIONS_UPDATE_CONFIG
    }
    return values | changes


async def _submit_options(
    hass: HomeAssistant, options: dict[str, Any], user_input: dict[str, Any]
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=UNIQUE_ID,
        data={CONF_DEVICE_SERIAL: SERIAL},
        options=options,
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    return entry


async def test_options_form_defaults(hass: HomeAssistant) -> None:
    """The form is pre-filled with the current options."""
    options = SYNCED_OPTIONS | {OPTIONS_SSID: "Net", OPTIONS_AUTO_UPDATE: True}
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=UNIQUE_ID, data={}, options=options
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert defaults == {
        key: value for key, value in options.items() if key != OPTIONS_UPDATE_CONFIG
    }


@pytest.mark.parametrize(
    "changes",
    [
        {OPTIONS_UPDATE_NAME: "Rosemary"},
        {OPTIONS_UPDATE_TEST_MODE: True},
        {OPTIONS_MOI_DRY: 2600},
        {OPTIONS_MOI_WET: 650},
        {OPTIONS_SSID: "MyNetwork"},
        {OPTIONS_WIFI_PWD: "secret"},
    ],
)
async def test_device_option_change_schedules_push(
    hass: HomeAssistant, changes: dict[str, Any]
) -> None:
    entry = await _submit_options(hass, SYNCED_OPTIONS, _form_input(**changes))
    assert entry.options[OPTIONS_UPDATE_CONFIG] is True
    for key, value in changes.items():
        assert entry.options[key] == value


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {OPTIONS_ENABLE_TEST: True},
        {OPTIONS_AUTO_UPDATE: True},
    ],
)
async def test_ha_only_option_change_does_not_push(
    hass: HomeAssistant, changes: dict[str, Any]
) -> None:
    entry = await _submit_options(hass, SYNCED_OPTIONS, _form_input(**changes))
    assert entry.options[OPTIONS_UPDATE_CONFIG] is False


async def test_unset_options_are_not_a_change(hass: HomeAssistant) -> None:
    """Submitting form defaults for never-stored options must not trigger a push."""
    stored = {
        key: value
        for key, value in SYNCED_OPTIONS.items()
        if key not in (OPTIONS_SSID, OPTIONS_WIFI_PWD, OPTIONS_AUTO_UPDATE)
    }
    entry = await _submit_options(
        hass, stored, _form_input(**{OPTIONS_ENABLE_TEST: True})
    )
    assert entry.options[OPTIONS_UPDATE_CONFIG] is False
    assert entry.options[OPTIONS_ENABLE_TEST] is True


async def test_pending_push_is_kept(hass: HomeAssistant) -> None:
    """Saving without device changes keeps an already pending push."""
    entry = await _submit_options(
        hass,
        SYNCED_OPTIONS | {OPTIONS_UPDATE_CONFIG: True},
        _form_input(),
    )
    assert entry.options[OPTIONS_UPDATE_CONFIG] is True
