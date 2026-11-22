"""Diagnostics for NextMsg. The key is never included."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from . import NextMsgConfigEntry
from .const import CONF_CHANNEL


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NextMsgConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    key: str = entry.data[CONF_API_KEY]
    return {
        "key_type": "agent" if key.startswith("nextmsg_agent_") else "send",
        "channels": sorted(
            subentry.data[CONF_CHANNEL] for subentry in entry.subentries.values()
        ),
    }
