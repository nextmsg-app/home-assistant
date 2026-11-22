"""The NextMsg integration: push notifications to your phone."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NextMsgClient

PLATFORMS: list[Platform] = [Platform.NOTIFY]

type NextMsgConfigEntry = ConfigEntry[NextMsgClient]


async def async_setup_entry(hass: HomeAssistant, entry: NextMsgConfigEntry) -> bool:
    """Set up NextMsg from a config entry.

    Nothing is checked here: the API has no way to test a key without sending a
    message. A key that stopped working starts reauthentication on the next send.
    """
    entry.runtime_data = NextMsgClient(
        async_get_clientsession(hass), entry.data[CONF_API_KEY]
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: NextMsgConfigEntry
) -> None:
    """Reload after a new key or a channel was added or removed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: NextMsgConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
