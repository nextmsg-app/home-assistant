"""Notify entities for NextMsg: one per channel."""

from __future__ import annotations

from typing import override

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NextMsgConfigEntry
from .api import (
    NextMsgAuthError,
    NextMsgError,
    NextMsgInvalidMessage,
    NextMsgLimitReached,
    NextMsgRateLimited,
)
from .const import CONF_CHANNEL, DOMAIN, SUBENTRY_TYPE_CHANNEL

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NextMsgConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add one notify entity per channel."""
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE_CHANNEL:
            continue
        async_add_entities(
            [NextMsgNotifyEntity(entry, subentry)], config_subentry_id=subentry_id
        )


class NextMsgNotifyEntity(NotifyEntity):
    """Sends to one channel of the inbox."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "channel"
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, entry: NextMsgConfigEntry, subentry: ConfigSubentry) -> None:
        """Initialize the entity."""
        self._entry = entry
        self._channel: str = subentry.data[CONF_CHANNEL]
        self._attr_unique_id = f"{entry.entry_id}_{subentry.subentry_id}"
        self._attr_device_info = DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, f"{entry.entry_id}_{subentry.subentry_id}")},
            manufacturer="NextMsg",
            model="Channel",
            name=f"NextMsg {self._channel}",
            configuration_url="https://nextmsg.app/docs",
        )

    @override
    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Send a push. A title is shown in bold on the first line."""
        text = f"**{title.strip()}**\n{message}" if title and title.strip() else message
        try:
            await self._entry.runtime_data.send(text, self._channel)
        except NextMsgInvalidMessage as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_message",
                translation_placeholders={"error": str(err)},
            ) from err
        except NextMsgAuthError as err:
            self._entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except NextMsgLimitReached as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="limit_reached"
            ) from err
        except NextMsgRateLimited as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="rate_limited",
                translation_placeholders={"error": str(err)},
            ) from err
        except NextMsgError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
