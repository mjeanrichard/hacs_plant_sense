"""Helpers shared by the PlantSense tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from custom_components.plant_sense.const import FIRMWARE_GITHUB_REPO, MQTT_COMMAND_TOPIC
from custom_components.plant_sense.helpers import build_unique_id

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from homeassistant.core import HomeAssistant

SERIAL = "aabbccddeeff"
UNIQUE_ID = build_unique_id(SERIAL)
DEVICE_NAME = "Basil"
CONFIG_VERSION = 3

# Where OpenMQTTGateway publishes LoRa uplinks (matched by .../LORAtoMQTT/#).
GATEWAY_TOPIC = "devices/OMG_LILYGO/LORAtoMQTT"
RELEASES_URL = f"https://api.github.com/repos/{FIRMWARE_GITHUB_REPO}/releases/latest"


def data_message(**overrides: Any) -> dict[str, Any]:
    """Return a 'data' uplink as sent by the device (rssi/snr come from the gateway)."""
    return {
        "model": "PlantSense",
        "msg": "data",
        "id": SERIAL,
        "name": DEVICE_NAME,
        "tempc": 21.5,
        "hum": 55.2,
        "bat": 3.91,
        "batPct": 87,
        "moi": 42,
        "moiRaw": 1800,
        "test": False,
        "idx": 12,
        "v": CONFIG_VERSION,
        "fw": "1.0",
    } | overrides


def config_message(**overrides: Any) -> dict[str, Any]:
    """Return a 'config' uplink as sent by the device."""
    return {
        "model": "PlantSense",
        "msg": "config",
        "id": SERIAL,
        "name": DEVICE_NAME,
        "test": False,
        "sleep": 300,
        "retx": 2,
        "wait": 10,
        "pwr": 15,
        "moiDry": 2700,
        "moiWet": 700,
        "wifiSet": True,
        "v": CONFIG_VERSION,
        "fw": "1.0",
    } | overrides


async def async_send(
    hass: HomeAssistant,
    payload: dict[str, Any] | str | bytes,
    *,
    as_hex: bool = False,
    gateway_fields: dict[str, Any] | None = None,
) -> None:
    """Publish an uplink on the gateway topic the way OpenMQTTGateway does."""
    if isinstance(payload, dict):
        body = payload
        if as_hex:
            body = {"hex": json.dumps(payload).encode().hex()}
        body = body | (gateway_fields or {})
        payload = json.dumps(body)
    async_fire_mqtt_message(hass, GATEWAY_TOPIC, payload)
    await hass.async_block_till_done()


def published_commands(mqtt_mock: MagicMock) -> list[dict[str, Any]]:
    """Return the decoded LoRa downlink commands published so far."""
    commands = []
    for call in mqtt_mock.async_publish.call_args_list:
        topic, payload = call.args[0], call.args[1]
        assert topic == MQTT_COMMAND_TOPIC
        if isinstance(payload, bytes):
            payload = payload.decode()
        commands.append(json.loads(json.loads(payload)["message"]))
    return commands
