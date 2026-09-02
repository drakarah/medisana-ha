"""Binary sensor entities for the Medisana BS444 integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NUM_USERS
from .coordinator import MedisanaBS444Coordinator
from .parser import UserMeasurement


@dataclass(frozen=True, kw_only=True)
class MedisanaBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Medisana BS444 binary sensor entity."""

    value_fn: Callable[[UserMeasurement], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[MedisanaBinarySensorEntityDescription, ...] = (
    MedisanaBinarySensorEntityDescription(
        key="high_activity",
        translation_key="high_activity",
        icon="mdi:run",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda m: m.high_activity,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Medisana BS444 binary sensors from a config entry."""
    coordinator: MedisanaBS444Coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        MedisanaBS444BinarySensor(coordinator, entry, description, user_id)
        for user_id in range(1, NUM_USERS + 1)
        for description in BINARY_SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class MedisanaBS444BinarySensor(
    CoordinatorEntity[MedisanaBS444Coordinator], BinarySensorEntity
):
    """Representation of a single-user flag of the Medisana BS444 scale."""

    entity_description: MedisanaBinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MedisanaBS444Coordinator,
        entry: ConfigEntry,
        description: MedisanaBinarySensorEntityDescription,
        user_id: int,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._user_id = user_id
        self._attr_unique_id = f"{entry.unique_id}_user{user_id}_{description.key}"
        self._attr_translation_placeholders = {"user_id": str(user_id)}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title,
            manufacturer="Medisana",
            model="BS444",
        )
        if user_id > 1:
            self._attr_entity_registry_enabled_default = False

    @property
    def _measurement(self) -> UserMeasurement | None:
        return (self.coordinator.data or {}).get(self._user_id)

    @property
    def available(self) -> bool:
        return super().available and self._measurement is not None

    @property
    def is_on(self) -> bool | None:
        measurement = self._measurement
        if measurement is None:
            return None
        return self.entity_description.value_fn(measurement)
