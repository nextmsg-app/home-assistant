"""Config flow for NextMsg."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import logging
from typing import Any, override

import probatio

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    KEY_RE,
    NextMsgAuthError,
    NextMsgClient,
    NextMsgError,
    NextMsgInvalidCode,
    NextMsgInvalidMessage,
    NextMsgKeyLimit,
    NextMsgLimitReached,
    NextMsgRateLimited,
    claim_code,
)
from .const import (
    AGENT_NAME,
    CHANNEL_RE,
    CONF_CHANNEL,
    CONF_CODE,
    DEFAULT_CHANNEL,
    DOMAIN,
    SUBENTRY_TYPE_CHANNEL,
)

_LOGGER = logging.getLogger(__name__)

CONNECTED_MESSAGE = "Home Assistant is connected to NextMsg."

CODE_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))
KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
CHANNEL_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))


def _unique_id(key: str) -> str:
    """A stable id for a key that doesn't reveal it."""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _normalize_channel(value: str) -> str:
    return value.strip().lower()


class NextMsgConfigFlow(ConfigFlow, domain=DOMAIN):
    """Connect Home Assistant to a NextMsg inbox."""

    VERSION = 1

    @classmethod
    @callback
    @override
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Channels are added as subentries."""
        return {SUBENTRY_TYPE_CHANNEL: ChannelSubentryFlow}

    @property
    def _replacing_key(self) -> bool:
        return self.source in (SOURCE_REAUTH, SOURCE_RECONFIGURE)

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose how to connect."""
        return self.async_show_menu(step_id="user", menu_options=["code", "key"])

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """The key stopped working (rotated or revoked)."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explain why, then connect again."""
        return self.async_show_menu(
            step_id="reauth_confirm", menu_options=["code", "key"]
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Connect with another code or key."""
        return self.async_show_menu(step_id="reconfigure", menu_options=["code", "key"])

    async def async_step_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Connect with a pickup code from the app."""
        errors: dict[str, str] = {}
        if user_input is not None:
            channel = _normalize_channel(user_input.get(CONF_CHANNEL, DEFAULT_CHANNEL))
            if not self._replacing_key and not CHANNEL_RE.match(channel):
                errors[CONF_CHANNEL] = "invalid_channel"
            else:
                try:
                    key = await claim_code(
                        async_get_clientsession(self.hass),
                        user_input[CONF_CODE],
                        f"{AGENT_NAME} ({self.hass.config.location_name})"
                        if self.hass.config.location_name
                        else AGENT_NAME,
                    )
                except NextMsgInvalidCode:
                    errors[CONF_CODE] = "invalid_code"
                except NextMsgKeyLimit as err:
                    errors["base"] = (
                        "key_limit_free" if err.pro_helps else "key_limit_max"
                    )
                except NextMsgRateLimited:
                    errors["base"] = "rate_limited"
                except NextMsgError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                else:
                    return await self._async_finish(key, channel)

        schema: dict[Any, Any] = {probatio.Required(CONF_CODE): CODE_SELECTOR}
        if not self._replacing_key:
            schema[probatio.Required(CONF_CHANNEL, default=DEFAULT_CHANNEL)] = (
                CHANNEL_SELECTOR
            )
        return self.async_show_form(
            step_id="code",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(schema), user_input
            ),
            errors=errors,
        )

    async def async_step_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Connect with the send key or an agent key, checked with a first message."""
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_API_KEY].strip()
            channel = _normalize_channel(
                user_input.get(CONF_CHANNEL, self._existing_channel())
            )
            if not KEY_RE.match(key):
                errors[CONF_API_KEY] = "invalid_key"
            elif not CHANNEL_RE.match(channel):
                errors[CONF_CHANNEL] = "invalid_channel"
            else:
                client = NextMsgClient(async_get_clientsession(self.hass), key)
                try:
                    await client.send(CONNECTED_MESSAGE, channel)
                except NextMsgLimitReached:
                    pass  # The key is valid, the inbox is just out of free messages
                except NextMsgAuthError:
                    errors[CONF_API_KEY] = "invalid_auth"
                except NextMsgRateLimited:
                    errors["base"] = "rate_limited"
                except NextMsgInvalidMessage:
                    errors[CONF_CHANNEL] = "invalid_channel"
                except NextMsgError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected exception")
                    errors["base"] = "unknown"
                if not errors:
                    return await self._async_finish(key, channel)

        schema: dict[Any, Any] = {
            probatio.Required(probatio.Secret(CONF_API_KEY)): KEY_SELECTOR
        }
        if not self._replacing_key:
            schema[probatio.Required(CONF_CHANNEL, default=DEFAULT_CHANNEL)] = (
                CHANNEL_SELECTOR
            )
        suggested = {k: v for k, v in (user_input or {}).items() if k != CONF_API_KEY}
        return self.async_show_form(
            step_id="key",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(schema), suggested
            ),
            errors=errors,
        )

    def _existing_channel(self) -> str:
        """A channel of the entry whose key is replaced, for the check message."""
        if self.source == SOURCE_REAUTH:
            entry = self._get_reauth_entry()
        elif self.source == SOURCE_RECONFIGURE:
            entry = self._get_reconfigure_entry()
        else:
            return DEFAULT_CHANNEL
        for subentry in entry.subentries.values():
            if subentry.subentry_type == SUBENTRY_TYPE_CHANNEL:
                return subentry.data[CONF_CHANNEL]
        return DEFAULT_CHANNEL

    async def _async_finish(self, key: str, channel: str) -> ConfigFlowResult:
        unique_id = _unique_id(key)
        if self.source == SOURCE_REAUTH:
            return self.async_update_and_abort(
                self._get_reauth_entry(),
                unique_id=unique_id,
                data_updates={CONF_API_KEY: key},
            )
        if self.source == SOURCE_RECONFIGURE:
            return self.async_update_and_abort(
                self._get_reconfigure_entry(),
                unique_id=unique_id,
                data_updates={CONF_API_KEY: key},
            )
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="NextMsg",
            data={CONF_API_KEY: key},
            subentries=[
                {
                    "subentry_type": SUBENTRY_TYPE_CHANNEL,
                    "data": {CONF_CHANNEL: channel},
                    "title": channel,
                    "unique_id": channel,
                }
            ],
        )


class ChannelSubentryFlow(ConfigSubentryFlow):
    """Add a channel: each gets its own notify entity and tab in the app."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a channel."""
        errors: dict[str, str] = {}
        if user_input is not None:
            channel = _normalize_channel(user_input[CONF_CHANNEL])
            if not CHANNEL_RE.match(channel):
                errors[CONF_CHANNEL] = "invalid_channel"
            else:
                for subentry in self._get_entry().subentries.values():
                    if subentry.unique_id == channel:
                        return self.async_abort(reason="already_configured")
                return self.async_create_entry(
                    title=channel, data={CONF_CHANNEL: channel}, unique_id=channel
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema({probatio.Required(CONF_CHANNEL): CHANNEL_SELECTOR}),
                user_input,
            ),
            errors=errors,
        )
