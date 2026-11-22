"""Tests for sending with the NextMsg notify entity."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.nextmsg.diagnostics import async_get_config_entry_diagnostics
from homeassistant.components.notify import (
    ATTR_MESSAGE,
    ATTR_TITLE,
    DOMAIN as NOTIFY_DOMAIN,
    SERVICE_SEND_MESSAGE,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .conftest import AGENT_KEY, SEND_URL

ENTITY_ID = "notify.nextmsg_home"


@pytest.fixture
async def loaded(hass: HomeAssistant, config_entry: MockConfigEntry) -> MockConfigEntry:
    """Set up the entry."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


async def _send(hass: HomeAssistant, message: str, title: str | None = None) -> None:
    data = {ATTR_ENTITY_ID: ENTITY_ID, ATTR_MESSAGE: message}
    if title is not None:
        data[ATTR_TITLE] = title
    await hass.services.async_call(
        NOTIFY_DOMAIN, SERVICE_SEND_MESSAGE, data, blocking=True
    )


async def test_send(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry
) -> None:
    """A message goes to the entity's channel with the key in the header."""
    aioclient_mock.post(SEND_URL, json={"success": True, "id": "1", "status": "queued"})
    await _send(hass, "Garage door open")
    _, url, body, headers = aioclient_mock.mock_calls[0]
    assert str(url) == SEND_URL
    assert body == {"message": "Garage door open", "channel": "home"}
    assert headers["Authorization"] == f"Bearer {AGENT_KEY}"
    assert hass.states.get(ENTITY_ID).state != "unknown"


async def test_send_with_title(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry
) -> None:
    """A title becomes a bold first line."""
    aioclient_mock.post(SEND_URL, json={"success": True})
    await _send(hass, "Door open for 10 minutes", title="Garage")
    assert (
        aioclient_mock.mock_calls[0][2]["message"]
        == "**Garage**\nDoor open for 10 minutes"
    )


async def test_invalid_message(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry
) -> None:
    """A message the API rejects is a validation error with the API's reason."""
    aioclient_mock.post(SEND_URL, status=400, json={"error": "Message is too long"})
    with pytest.raises(ServiceValidationError) as err:
        await _send(hass, "x" * 700)
    assert err.value.translation_key == "invalid_message"
    assert err.value.translation_placeholders == {"error": "Message is too long"}


async def test_revoked_key_starts_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry
) -> None:
    """A 401 fails the action and asks the user to connect again."""
    aioclient_mock.post(
        SEND_URL, status=401, json={"error": "Invalid or revoked agent key"}
    )
    with pytest.raises(HomeAssistantError) as err:
        await _send(hass, "hello")
    assert err.value.translation_key == "invalid_auth"
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


@pytest.mark.parametrize(
    ("status", "key"),
    [(402, "limit_reached"), (429, "rate_limited"), (502, "cannot_connect")],
)
async def test_send_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    loaded: MockConfigEntry,
    status: int,
    key: str,
) -> None:
    """Other failures are action errors with their own message."""
    aioclient_mock.post(SEND_URL, status=status, json={"error": "nope"})
    with pytest.raises(HomeAssistantError) as err:
        await _send(hass, "hello")
    assert err.value.translation_key == key


async def test_network_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, loaded: MockConfigEntry
) -> None:
    """No connection is an action error, not a crash."""
    aioclient_mock.post(SEND_URL, exc=TimeoutError())
    with pytest.raises(HomeAssistantError) as err:
        await _send(hass, "hello")
    assert err.value.translation_key == "cannot_connect"


async def test_unload(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    """The entry unloads cleanly."""
    assert await hass.config_entries.async_unload(loaded.entry_id)
    assert loaded.state is ConfigEntryState.NOT_LOADED


async def test_diagnostics(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    """Diagnostics never include the key."""
    result = await async_get_config_entry_diagnostics(hass, loaded)
    assert result == {"key_type": "agent", "channels": ["home"]}
    assert AGENT_KEY not in str(result)
