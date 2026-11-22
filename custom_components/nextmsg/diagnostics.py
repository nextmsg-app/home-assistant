"""Diagnostics for NextMsg. The key is never included."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import NextMsgConfigEntry
from .const import CONF_CHANNEL


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NextMsgConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        "channels": sorted(
            subentry.data[CONF_CHANNEL] for subentry in entry.subentries.values()
        ),
    }
