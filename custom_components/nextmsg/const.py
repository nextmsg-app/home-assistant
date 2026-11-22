"""Constants for the NextMsg integration."""

import re
from typing import Final

DOMAIN: Final = "nextmsg"

CONF_CODE: Final = "code"
CONF_CHANNEL: Final = "channel"

SUBENTRY_TYPE_CHANNEL: Final = "channel"
DEFAULT_CHANNEL: Final = "home"

# Name shown for this agent under Settings → Agents in the app
AGENT_NAME: Final = "Home Assistant"

# Channel tags as the API accepts them: 1-32 characters, a-z, 0-9, - and _
CHANNEL_RE: Final = re.compile(r"^[a-z0-9_-]{1,32}$")
