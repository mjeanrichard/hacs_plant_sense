# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A HACS (Home Assistant Community Store) custom integration for **PlantSense** — a DIY IoT plant monitor that communicates via LoRa radio bridged to MQTT through an [OpenMQTTGateway](https://docs.openmqttgateway.com/) LilyGO board. The integration receives sensor data over MQTT and exposes it as Home Assistant entities.

## Commands

**Install dependencies:**
```bash
scripts/setup
# or directly:
python3 -m pip install -r requirements.txt
```

**Lint and format (fix in place):**
```bash
scripts/lint
# which runs:
ruff format .
ruff check . --fix
```

**Check only (CI mode, no changes):**
```bash
python3 -m ruff check .
python3 -m ruff format . --check
```

**Run Home Assistant locally with the integration:**
```bash
scripts/develop
# Starts HA at http://localhost:8123 with config/ as the config dir
# Sets PYTHONPATH so custom_components/ is picked up without symlinking
```

There are no automated tests — validation is done via `hassfest` (HA's manifest validator) and the HACS action, both run in CI.

## Architecture

### MQTT message flow

```
LoRa device  →  OpenMQTTGateway (LilyGO)  →  MQTT broker  →  HA MQTT integration
                                                                      ↓
                                                               MqttManager
                                                               (subscribes to topic)
                                                                      ↓
                                                        PlantSenseCoordinator (per device)
                                                                      ↓
                                                          GenericPlantSenseSensor entities
```

**`MqttManager`** (`mqtt_manager.py`) — singleton per HA instance (stored in `hass.data[DOMAIN][DOMAIN_MQTT_MANAGER]`). Subscribes once to `devices/OMG_LILYGO/LORAtoMQTT/#`. Incoming messages may contain hex-encoded JSON in a `"hex"` field; the manager decodes it, merges it into the top-level dict, then routes to the right coordinator by looking up the `"id"` field in the device registry. If the device is unknown, it triggers integration discovery so the user can confirm it.

**`PlantSenseCoordinator`** (`coordinator.py`) — one per config entry / physical device. Handles two message types dispatched by `MqttManager.handle_message()`:
- `"data"` — pushes sensor readings to all registered `PlantSenseComponent` objects and handles config-sync logic (sends config to device if a push is pending, or requests config from device if HA's stored version is behind the device's version).
- `"config"` — updates the config entry title, options, and device name when the device reports a newer config version.

Config is pushed/pulled via a second MQTT topic: `devices/OMG_LILYGO/commands/MQTTtoLORA` (LoRa commands are JSON-in-JSON strings).

**`GenericPlantSenseSensor`** (`sensor.py`) — implements both `SensorEntity` and `PlantSenseComponent`. Each sensor reads a single key from `coordinator.last_data`. Registers itself with the coordinator on `async_added_to_hass` and deregisters on `async_will_remove_from_hass`. The coordinator calls `update_async()` on every registered component when new data arrives (`_attr_should_poll = False`).

**Config flow** (`config_flow.py`) — supports both manual entry (user supplies serial number) and automatic integration discovery (triggered by `MqttManager` when an unknown device is seen). Unique ID is `PlantSense-{serial}`. Options flow exposes test-mode toggle and config-push controls.

### Key data identifiers

- **MQTT subscribe topic:** `devices/OMG_LILYGO/LORAtoMQTT/#`
- **MQTT command topic:** `devices/OMG_LILYGO/commands/MQTTtoLORA`
- **Device unique ID:** `PlantSense-{serial}` (built by `helpers.build_unique_id`)
- **Message fields:** `id` (serial), `name`, `msg` (`"data"` or `"config"`), `v` (config version), `test` (bool), sensor keys: `batPct`, `bat`, `moi`, `hum`, `tempc`, `rssi`, `snr`

### Config entry storage

- `entry.data`: `CONF_DEVICE_SERIAL`, `DATA_LAST_CONFIG_VERSION`
- `entry.options`: `OPTIONS_UPDATE_NAME`, `OPTIONS_UPDATE_CONFIG` (pending push flag), `OPTIONS_UDPATE_TEST_MODE`, `OPTIONS_ENABLE_TEST`
- `entry.runtime_data`: `PlantSenseData(coordinator=...)` — set during `async_setup_entry`

## Linting rules

Ruff is configured in `.ruff.toml` with `select = ["ALL"]`. Notable suppressions: `D100`/`D101`/`D102` (public docstrings not required), `ANN401` (typing.Any allowed). Target Python 3.12.

### Ruff cache permission issue (devcontainer)

The `.ruff_cache/` directory can end up with root-owned subdirectories inside the devcontainer, causing `ruff` to fail with `Permission denied` when creating temp files. `scripts/lint` sets `RUFF_CACHE_DIR=/tmp/ruff_cache` to avoid this. When running ruff manually in CI-check mode, do the same:

```bash
RUFF_CACHE_DIR=/tmp/ruff_cache python3 -m ruff check .
RUFF_CACHE_DIR=/tmp/ruff_cache python3 -m ruff format . --check
```

## Dev environment notes

- **Devcontainer Python version:** 3.13 (`mcr.microsoft.com/devcontainers/python:3.13`)
- **HA dev dependency:** `requirements.txt` pins `homeassistant==2026.2.3` (the version used for local development and testing).
- **HA minimum version (HACS):** `hacs.json` sets `"homeassistant": "2025.12.3"` — the oldest HA release the integration supports.
- **Integration has no external Python requirements** — `manifest.json` `"requirements": []` is empty; the integration only uses HA built-ins and the `mqtt` component.
- **Dependabot** watches GitHub Actions, pip, and devcontainer features weekly.

## JSON protocol (raw LoRa, no LoRaWAN)

**Uplink — data:**
```json
{"model":"PlantSense","msg":"data","id":"<mac>","name":"<name>",
 "tempc":<float>,"hum":<float>,"bat":<float>,"batPct":<int>,
 "moi":<int>,"moiRaw":<int>,"test":<bool>,"idx":<uint>,"v":<uint>,"fw":"<version>"}
```

**Uplink — wifi:**
```json
{"model":"PlantSense","msg":"wifi","id":"<mac>","name":"<name>",
 "test":<bool>,"wifiRssi":<int>,"uptime":<uint>,"fw":"<version>"}
```

**Downlink — set config:**
```json
{"id":"<mac>","cmd":"set_config","name":"...","sleep":300,"wait":10,
 "txPower":15,"retransmits":2,"test":false,"moiDry":2700,"moiWet":700}
```
All fields optional. `moiDry`/`moiWet` are raw ADC millivolt readings; observe `moiRaw` in data packets under dry and wet conditions to determine values.

**Downlink — get config:**
```json
{"id":"<mac>","cmd":"get_config"}
```

**Uplink — config response:**
```json
{"model":"PlantSense","msg":"config","id":"<mac>","name":"<name>",
 "test":<bool>,"sleep":<int>,"retx":<uint>,"wait":<uint>,"pwr":<uint>,
 "moiDry":<uint>,"moiWet":<uint>,"v":<uint>,"fw":"<version>"}
```

Gateway used: OpenMQTTGateway on a LilyGO board.
