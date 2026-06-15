"""Sensor entities for Chzzk channels."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ChzzkCoordinator, ChzzkData
from .entity import ChzzkEntity


@dataclass(kw_only=True, frozen=True)
class ChzzkSensorEntityDescription(SensorEntityDescription):
    """Pairs a Home Assistant entity description with a value extractor."""

    value_fn: Callable[[ChzzkData], str | int | float | datetime | None]


SENSORS: tuple[ChzzkSensorEntityDescription, ...] = (
    ChzzkSensorEntityDescription(
        key="title",
        translation_key="title",
        icon="mdi:format-title",
        value_fn=lambda d: d.live.title,
    ),
    ChzzkSensorEntityDescription(
        key="category",
        translation_key="category",
        icon="mdi:tag",
        value_fn=lambda d: d.live.category_value,
    ),
    ChzzkSensorEntityDescription(
        key="viewers",
        translation_key="viewers",
        icon="mdi:account-eye",
        native_unit_of_measurement="viewers",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.live.concurrent_user_count if d.live.is_live else None,
    ),
    ChzzkSensorEntityDescription(
        key="started_at",
        translation_key="started_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.live.open_date if d.live.is_live else None,
    ),
    ChzzkSensorEntityDescription(
        key="followers",
        translation_key="followers",
        icon="mdi:account-multiple",
        native_unit_of_measurement="followers",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.channel.follower_count,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coords: dict[str, ChzzkCoordinator] = hass.data[DOMAIN]["coordinators"]
    entities: list[ChzzkSensor] = []
    for coord in coords.values():
        entities.extend(ChzzkSensor(coord, desc) for desc in SENSORS)
    async_add_entities(entities)


class ChzzkSensor(ChzzkEntity, SensorEntity):
    entity_description: ChzzkSensorEntityDescription

    def __init__(
        self,
        coordinator: ChzzkCoordinator,
        description: ChzzkSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator, description)

    @property
    def native_value(self) -> str | int | float | datetime | None:
        data = self.coordinator.data
        if data is None:
            return None
        return self.entity_description.value_fn(data)
