"""Binary sensor for the live-streaming state."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ChzzkCoordinator
from .entity import ChzzkEntity

DESCRIPTION = BinarySensorEntityDescription(
    key="streaming",
    translation_key="streaming",
    device_class=BinarySensorDeviceClass.RUNNING,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coords: dict[str, ChzzkCoordinator] = hass.data[DOMAIN]["coordinators"]
    async_add_entities(ChzzkStreamingBinarySensor(c) for c in coords.values())


class ChzzkStreamingBinarySensor(ChzzkEntity, BinarySensorEntity):
    """`on` while the channel is live."""

    def __init__(self, coordinator: ChzzkCoordinator) -> None:
        super().__init__(coordinator, DESCRIPTION)

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if data is None:
            return None
        return data.live.is_live

    @property
    def entity_picture(self) -> str | None:
        data = self.coordinator.data
        if data is None:
            return None
        # Prefer the live thumbnail while streaming, fall back to the avatar.
        return data.live.live_image_url or data.channel.channel_image_url

    @property
    def extra_state_attributes(self) -> dict[str, str | int | bool | None]:
        data = self.coordinator.data
        if data is None:
            return {}
        return {
            "channel_id": data.channel.channel_id,
            "channel_url": f"https://chzzk.naver.com/{data.channel.channel_id}",
            "live_url": (
                f"https://chzzk.naver.com/live/{data.channel.channel_id}"
                if data.live.is_live
                else None
            ),
            "adult": data.live.adult,
            "verified": data.channel.verified_mark,
        }
