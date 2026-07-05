"""Event entity that fires when a channel's stream starts or ends."""

from __future__ import annotations

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ChzzkCoordinator
from .entity import ChzzkEntity

EVENT_STARTED = "started"
EVENT_ENDED = "ended"

DESCRIPTION = EventEntityDescription(
    key="stream",
    translation_key="stream",
    event_types=[EVENT_STARTED, EVENT_ENDED],
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coords: dict[str, ChzzkCoordinator] = hass.data[DOMAIN]["coordinators"]
    async_add_entities(ChzzkStreamEvent(c) for c in coords.values())


class ChzzkStreamEvent(ChzzkEntity, EventEntity):
    """Fires ``started``/``ended`` when the channel's live status flips."""

    def __init__(self, coordinator: ChzzkCoordinator) -> None:
        super().__init__(coordinator, DESCRIPTION)
        data = coordinator.data
        # None until the first real transition is observed, so a channel
        # that's already live when the entity is created doesn't fire a
        # spurious "started" event on the next poll.
        self._last_is_live: bool | None = data.live.is_live if data else None

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if data is not None:
            is_live = data.live.is_live
            if self._last_is_live is not None and is_live != self._last_is_live:
                self._trigger_event(EVENT_STARTED if is_live else EVENT_ENDED)
            self._last_is_live = is_live
        super()._handle_coordinator_update()
