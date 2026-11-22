"""Tests for the NextMsg config flow."""

from __future__ import annotations

import json

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.nextmsg.const import CONF_CHANNEL, CONF_CODE, DOMAIN
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import AGENT_KEY, CLAIM_URL, SEND_KEY, SEND_URL


async def _start(hass: HomeAssistant, option: str) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": option}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == option
    return result["flow_id"]


async def test_code_flow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A pickup code becomes an agent key; the channel becomes a subentry."""
    hass.config.location_name = "Home"
    aioclient_mock.post(
        CLAIM_URL,
        json={"send_key": AGENT_KEY, "key_prefix": AGENT_KEY[:25], "name": "x"},
    )
    flow_id = await _start(hass, "code")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_CODE: " k73m-qx9p ", CONF_CHANNEL: " Garden "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "NextMsg"
    assert result["data"] == {CONF_API_KEY: AGENT_KEY}
    entry = result["result"]
    assert [s.data[CONF_CHANNEL] for s in entry.subentries.values()] == ["garden"]
    body = aioclient_mock.mock_calls[0][2]
    assert body == {"code": "k73m-qx9p", "name": "Home Assistant (Home)"}


@pytest.mark.parametrize(
    ("status", "field", "error"),
    [
        (400, CONF_CODE, "invalid_code"),
        (409, "base", "key_limit_free"),
        (429, "base", "rate_limited"),
        (503, "base", "cannot_connect"),
    ],
)
async def test_code_flow_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    field: str,
    error: str,
) -> None:
    """Claim errors are shown on the form, and the form can be sent again."""
    aioclient_mock.post(CLAIM_URL, status=status, json={"error": "nope"})
    flow_id = await _start(hass, "code")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_CODE: "AAAA-BBBB", CONF_CHANNEL: "home"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {field: error}

    aioclient_mock.clear_requests()
    aioclient_mock.post(CLAIM_URL, json={"send_key": AGENT_KEY})
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_CODE: "AAAA-BBBB", CONF_CHANNEL: "home"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_code_flow_bad_channel(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A channel the API wouldn't accept is caught before the code is used."""
    flow_id = await _start(hass, "code")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_CODE: "AAAA-BBBB", CONF_CHANNEL: "my channel!"}
    )
    assert result["errors"] == {CONF_CHANNEL: "invalid_channel"}
    assert aioclient_mock.call_count == 0


async def test_key_flow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A key is checked with a test message on the chosen channel."""
    aioclient_mock.post(SEND_URL, json={"success": True, "id": "1", "status": "queued"})
    flow_id = await _start(hass, "key")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_API_KEY: f" {SEND_KEY} ", CONF_CHANNEL: "home"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_API_KEY: SEND_KEY}
    _, _, body, headers = aioclient_mock.mock_calls[0]
    assert body == {
        "message": "Home Assistant is connected to NextMsg.",
        "channel": "home",
    }
    assert headers["Authorization"] == f"Bearer {SEND_KEY}"


@pytest.mark.parametrize(
    ("status", "field", "error"),
    [
        (401, CONF_API_KEY, "invalid_auth"),
        (429, "base", "rate_limited"),
        (500, "base", "cannot_connect"),
    ],
)
async def test_key_flow_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    field: str,
    error: str,
) -> None:
    """Send errors are shown on the form."""
    aioclient_mock.post(SEND_URL, status=status, json={"error": "nope"})
    flow_id = await _start(hass, "key")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_API_KEY: SEND_KEY, CONF_CHANNEL: "home"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {field: error}


async def test_key_flow_format(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A malformed key is caught without a request."""
    flow_id = await _start(hass, "key")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_API_KEY: "nextmsg_live_short", CONF_CHANNEL: "home"}
    )
    assert result["errors"] == {CONF_API_KEY: "invalid_key"}
    assert aioclient_mock.call_count == 0


async def test_key_flow_limit_reached(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """402 means the key is fine, the inbox is just out of free messages."""
    aioclient_mock.post(SEND_URL, status=402, json={"error": "Monthly limit"})
    flow_id = await _start(hass, "key")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_API_KEY: SEND_KEY, CONF_CHANNEL: "home"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_key_flow_already_configured(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The same key can't be added twice."""
    aioclient_mock.post(SEND_URL, json={"success": True})
    for expected in (FlowResultType.CREATE_ENTRY, FlowResultType.ABORT):
        flow_id = await _start(hass, "key")
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_API_KEY: SEND_KEY, CONF_CHANNEL: "home"}
        )
        assert result["type"] is expected
    assert result["reason"] == "already_configured"


async def test_reauth_with_code(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """Reauth replaces the key and keeps the channels."""
    config_entry.add_to_hass(hass)
    new_key = "nextmsg_live_" + "c" * 48
    aioclient_mock.post(CLAIM_URL, json={"send_key": new_key})
    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "code"}
    )
    assert CONF_CHANNEL not in result["data_schema"].schema
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CODE: "AAAA-BBBB"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_API_KEY] == new_key
    assert len(config_entry.subentries) == 1


async def test_reconfigure_with_key(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """Reconfigure checks the new key on an existing channel."""
    config_entry.add_to_hass(hass)
    aioclient_mock.post(SEND_URL, json={"success": True})
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "key"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: SEND_KEY}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_API_KEY] == SEND_KEY
    assert aioclient_mock.mock_calls[0][2]["channel"] == "home"


async def test_add_channel(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
) -> None:
    """A channel subentry adds a notify entity; duplicates are refused."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    async def add(channel: str):
        result = await hass.config_entries.subentries.async_init(
            (config_entry.entry_id, "channel"),
            context={"source": config_entries.SOURCE_USER},
        )
        return await hass.config_entries.subentries.async_configure(
            result["flow_id"], {CONF_CHANNEL: channel}
        )

    result = await add("Not valid")
    assert result["errors"] == {CONF_CHANNEL: "invalid_channel"}
    result = await add("garden")
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.states.get("notify.nextmsg_garden") is not None
    result = await add("home")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


def test_translations_are_valid_json() -> None:
    """The translation file parses (hassfest checks the rest in CI)."""
    with open("custom_components/nextmsg/translations/en.json", encoding="utf-8") as f:
        json.load(f)


async def test_code_flow_key_limit_max(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A Pro inbox at 20 keys gets its own message (buying Pro can't help)."""
    aioclient_mock.post(
        CLAIM_URL, status=409, json={"error": "full", "code": "key_limit_max"}
    )
    flow_id = await _start(hass, "code")
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_CODE: "AAAA-BBBB", CONF_CHANNEL: "home"}
    )
    assert result["errors"] == {"base": "key_limit_max"}
