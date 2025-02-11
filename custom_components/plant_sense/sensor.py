import logging
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    ENTITY_ID_FORMAT,
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, async_generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PlantSenseComponent, PlantSenseCoordinator

if TYPE_CHECKING:
    from .data import PlantSenseData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add sensors for passed config_entry in HA."""
    data: PlantSenseData = config_entry.runtime_data
    sensor_list = [
        GenericPlantSenseSensor(
            hass=hass,
            coordinator=data.coordinator,
            device_class=SensorDeviceClass.BATTERY,
            unit_of_measurement=PERCENTAGE,
            id_suffix="battery",
            name="Battery",
            value_key="batPct",
        ),
        GenericPlantSenseSensor(
            hass=hass,
            coordinator=data.coordinator,
            device_class=SensorDeviceClass.MOISTURE,
            unit_of_measurement=PERCENTAGE,
            id_suffix="moisture",
            name="Moisture",
            value_key="moi",
        ),
        GenericPlantSenseSensor(
            hass=hass,
            coordinator=data.coordinator,
            device_class=SensorDeviceClass.HUMIDITY,
            unit_of_measurement=PERCENTAGE,
            id_suffix="humidity",
            name="Humidity",
            value_key="hum",
        ),
        GenericPlantSenseSensor(
            hass=hass,
            coordinator=data.coordinator,
            device_class=SensorDeviceClass.TEMPERATURE,
            unit_of_measurement=UnitOfTemperature.CELSIUS,
            id_suffix="temperature",
            name="Temperature",
            value_key="tempc",
        ),
        GenericPlantSenseSensor(
            hass=hass,
            coordinator=data.coordinator,
            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
            unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
            id_suffix="rssi",
            name="RSSI",
            value_key="rssi",
        ),
        GenericPlantSenseSensor(
            hass=hass,
            coordinator=data.coordinator,
            device_class=None,
            unit_of_measurement="",
            id_suffix="snr",
            name="SNR",
            value_key="snr",
            icon="mdi:wifi",
        ),
        GenericPlantSenseSensor(
            hass=hass,
            coordinator=data.coordinator,
            device_class=None,
            unit_of_measurement="",
            id_suffix="test",
            name="Test",
            value_key="test",
        ),
        GenericPlantSenseSensor(
            hass=hass,
            coordinator=data.coordinator,
            device_class=None,
            unit_of_measurement="V",
            id_suffix="battery_volt",
            name="Battery",
            value_key="bat",
        ),
    ]
    async_add_entities(sensor_list)


class GenericPlantSenseSensor(SensorEntity, PlantSenseComponent):
    """Representation of a Sensor."""

    _name: str
    _value_key: str
    _coordinator: PlantSenseCoordinator

    def __init__(  # noqa: PLR0913
        self,
        hass: HomeAssistant,
        coordinator: PlantSenseCoordinator,
        device_class: SensorDeviceClass | None,
        unit_of_measurement: str,
        name: str,
        id_suffix: str,
        value_key: str,
        icon: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._attr_should_poll = False
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_unique_id = f"{coordinator.device_id}_{id_suffix}"
        self._attr_icon = icon

        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, f"{coordinator.device_id}_{id_suffix}", hass=hass
        )

        self._name = name
        self._value_key = value_key

    async def update_async(self) -> None:
        if self._coordinator.data is None:
            return

        value = self._coordinator.data.get(self._value_key)
        if value is not None:
            self._attr_native_value = value
            await self.async_update_ha_state(force_refresh=True)

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return f"{self._coordinator.device_name} {self._name}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return self._coordinator.device_info

    @property
    def available(self) -> bool:
        """Return True if roller and hub is available."""
        return True

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._coordinator.register_component(self)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._coordinator.remove_component(self)
