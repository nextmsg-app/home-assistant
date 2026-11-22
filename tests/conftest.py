"""Fixtures for NextMsg tests."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nextmsg.const import (
    CONF_CHANNEL,
    DOMAIN,
    SUBENTRY_TYPE_CHANNEL,
)
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_API_KEY

SEND_KEY = "nextmsg_live_" + "a" * 48
AGENT_KEY = "nextmsg_agent_" + "b" * 48
SEND_URL = "https://api.nextmsg.app/v1/send"
CLAIM_URL = "https://api.nextmsg.app/v1/agent/claim"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/ in every test."""
    return


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """An entry with the agent key and the home channel."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="NextMsg",
        data={CONF_API_KEY: AGENT_KEY},
        unique_id="existing",
        subentries_data=[
            ConfigSubentryData(
                subentry_type=SUBENTRY_TYPE_CHANNEL,
                data={CONF_CHANNEL: "home"},
                title="home",
                unique_id="home",
            )
        ],
    )
