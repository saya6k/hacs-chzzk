"""The Chzzk integration — single entry, multiple channels."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import ChzzkClient
from .const import (
    CONF_CHANNEL_ID,
    CONF_CHANNEL_NAME,
    CONF_CHANNELS,
    CONF_NID_AUT,
    CONF_NID_SES,
    DOMAIN,
)
from .coordinator import ChzzkCoordinator
from .llm import async_register as async_register_llm
from .views import ChzzkChannelsView

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _collect_channels(entry: ConfigEntry) -> list[dict[str, str]]:
    """Read the channels list, merging in any legacy single-channel data."""
    channels = list(entry.options.get(CONF_CHANNELS, []))
    legacy_id = entry.data.get(CONF_CHANNEL_ID)
    if legacy_id and not any(c.get(CONF_CHANNEL_ID) == legacy_id for c in channels):
        channels.append(
            {
                CONF_CHANNEL_ID: legacy_id,
                CONF_CHANNEL_NAME: entry.data.get(CONF_CHANNEL_NAME, ""),
            }
        )
    return channels


def _cookies_from_entry(entry: ConfigEntry) -> dict[str, str]:
    cookies: dict[str, str] = {}
    if (val := entry.data.get(CONF_NID_AUT)):
        cookies["NID_AUT"] = val
    if (val := entry.data.get(CONF_NID_SES)):
        cookies["NID_SES"] = val
    return cookies


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async_register_llm(hass)
    hass.http.register_view(ChzzkChannelsView(hass))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    cookies = _cookies_from_entry(entry)
    session = async_get_clientsession(hass)
    client = ChzzkClient(session, cookies=cookies or None)

    coordinators: dict[str, ChzzkCoordinator] = {}
    for ch in _collect_channels(entry):
        channel_id = ch[CONF_CHANNEL_ID]
        coord = ChzzkCoordinator(
            hass,
            client,
            channel_id,
            ch.get(CONF_CHANNEL_NAME) or channel_id,
        )
        # Don't fail the entire entry if one channel can't refresh — the
        # coordinator will keep retrying and the unavailable entity will show
        # as such in the UI.
        try:
            await coord.async_config_entry_first_refresh()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("First refresh failed for %s", channel_id)
        coordinators[channel_id] = coord

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["entry_id"] = entry.entry_id
    hass.data[DOMAIN]["coordinators"] = coordinators

    # Drop stale devices for channels that were removed.
    _prune_orphan_devices(hass, entry, set(coordinators))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data.pop(DOMAIN, None)
    return unloaded


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when the channels list or cookies change in the options flow."""
    await hass.config_entries.async_reload(entry.entry_id)


def _prune_orphan_devices(
    hass: HomeAssistant, entry: ConfigEntry, live_channel_ids: set[str]
) -> None:
    """Remove HA devices for channels that no longer exist in the entry."""
    device_reg = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_reg, entry.entry_id):
        for domain, identifier in device.identifiers:
            if domain == DOMAIN and identifier not in live_channel_ids:
                device_reg.async_remove_device(device.id)
                _LOGGER.info("Removed orphan device for channel %s", identifier)
                break
