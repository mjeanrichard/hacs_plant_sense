"""Constants for the PlantSense integration."""

DOMAIN = "plant_sense"

CONF_MQTT_ROOT = "MQTT_ROOT_TOPIC"
CONF_DEVICE_SERIAL = "DEVICE_SERIAL"

OPTIONS_UPDATE_NAME = "name"
OPTIONS_UPDATE_CONFIG = "update_config"
OPTIONS_UPDATE_TEST_MODE = "update_test_mode"
OPTIONS_ENABLE_TEST = "enable_test"
OPTIONS_MOI_DRY = "moi_dry"
OPTIONS_MOI_WET = "moi_wet"
OPTIONS_SSID = "ssid"
OPTIONS_WIFI_PWD = "wifi_pwd"  # noqa: S105
OPTIONS_AUTO_UPDATE = "auto_update"

FIRMWARE_GITHUB_REPO = "mjeanrichard/LoraSensor"
FIRMWARE_CHECK_INTERVAL_HOURS = 4

DATA_LAST_CONFIG_VERSION = "config_version"
DATA_CONFIRMED_NAME = "confirmed_name"
DATA_CONFIRMED_TEST_MODE = "confirmed_test_mode"
DATA_CONFIRMED_MOI_DRY = "confirmed_moi_dry"
DATA_CONFIRMED_MOI_WET = "confirmed_moi_wet"

DOMAIN_MQTT_MANAGER = "mqtt_manager"

DISCOVERY_SERIAL = "discovery_serial_number"
DISCOVERY_NAME = "discovery_name"
