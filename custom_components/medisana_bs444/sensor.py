"""Sensor entities for the Medisana BS444 integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfMass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NUM_USERS
from .coordinator import MedisanaBS444Coordinator
from .parser import UserMeasurement


@dataclass(frozen=True, kw_only=True)
class MedisanaSensorEntityDescription(SensorEntityDescription):
    """Describes a Medisana BS444 sensor entity."""

    value_fn: Callable[[UserMeasurement], float | int | None]


SENSOR_DESCRIPTIONS: tuple[MedisanaSensorEntityDescription, ...] = (
    MedisanaSensorEntityDescription(
        key="weight",
        translation_key="weight",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m: m.weight,
    ),
    MedisanaSensorEntityDescription(
        key="bmi",
        translation_key="bmi",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m: m.bmi,
    ),
    MedisanaSensorEntityDescription(
        key="kcal",
        translation_key="kcal",
        native_unit_of_measurement="kcal",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m: m.kcal,
    ),
    MedisanaSensorEntityDescription(
        key="fat",
        translation_key="fat",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m: m.fat,
    ),
    MedisanaSensorEntityDescription(
        key="tbw",
        translation_key="tbw",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m: m.tbw,
    ),
    MedisanaSensorEntityDescription(
        key="muscle",
        translation_key="muscle",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m: m.muscle,
    ),
    MedisanaSensorEntityDescription(
        key="bone",
        translation_key="bone",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m: m.bone,
    ),
    MedisanaSensorEntityDescription(
        key="age",
        translation_key="age",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda m: m.age or None,
    ),
    MedisanaSensorEntityDescription(
        key="size",
        translation_key="size",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda m: round(m.size * 100) if m.size else None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Medisana BS444 sensors from a config entry."""
    coordinator: MedisanaBS444Coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        MedisanaBS444Sensor(coordinator, entry, description, user_id)
        for user_id in range(1, NUM_USERS + 1)
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class MedisanaBS444Sensor(
    CoordinatorEntity[MedisanaBS444Coordinator], SensorEntity
):
    """Representation of a single-user metric of the Medisana BS444 scale."""

    entity_description: MedisanaSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MedisanaBS444Coordinator,
        entry: ConfigEntry,
        description: MedisanaSensorEntityDescription,
        user_id: int,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._user_id = user_id
        self._attr_unique_id = f"{entry.unique_id}_user{user_id}_{description.key}"
        self._attr_translation_placeholders = {"user_id": str(user_id)}
        # Only enable user 1's sensors by default; other users can be
        # enabled by whoever configures additional profiles on the scale.
        if user_id > 1:
            self._attr_entity_registry_enabled_default = False

    @property
    def _measurement(self) -> UserMeasurement | None:
        return (self.coordinator.data or {}).get(self._user_id)

    @property
    def available(self) -> bool:
        return super().available and self._measurement is not None

    @property
    def native_value(self) -> float | int | None:
        measurement = self._measurement
        if measurement is None:
            return None
        return self.entity_description.value_fn(measurement)
