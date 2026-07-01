"""Shared base entity for Chzzk: device grouping, attribution, name composition."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN, MANUFACTURER
from .coordinator import ChzzkCoordinator


class ChzzkEntity(CoordinatorEntity[ChzzkCoordinator]):
    """Base class — all entities share one device per channel."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ChzzkCoordinator, description: EntityDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.channel_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.channel_id)},
            entry_type=DeviceEntryType.SERVICE,
            manufacturer=MANUFACTURER,
            name=coordinator.channel_name,
            configuration_url=f"https://chzzk.naver.com/{coordinator.channel_id}",
        )

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None
