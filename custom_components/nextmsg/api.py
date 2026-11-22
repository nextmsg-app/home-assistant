"""Small client for the NextMsg API (https://api.nextmsg.app/openapi.json)."""

from __future__ import annotations

import re
from typing import Any, Final

import aiohttp

API_URL: Final = "https://api.nextmsg.app"
TIMEOUT: Final = aiohttp.ClientTimeout(total=15)

# The send key from the app (nextmsg_live_) or an agent key (nextmsg_agent_)
KEY_RE: Final = re.compile(r"^nextmsg_(live|agent)_[0-9a-f]{48}$")


class NextMsgError(Exception):
    """Base error. The message is the API's own explanation, when there is one."""


class NextMsgConnectionError(NextMsgError):
    """The API could not be reached or answered with a server error."""


class NextMsgAuthError(NextMsgError):
    """The key is wrong, rotated or revoked (401)."""


class NextMsgInvalidCode(NextMsgError):
    """The pickup code is wrong, already used or expired (400 on claim)."""


class NextMsgTooManyAgents(NextMsgError):
    """The inbox already has the most agents it can have (409 on claim)."""


class NextMsgInvalidMessage(NextMsgError):
    """The message or channel was rejected (400 or 413 on send)."""


class NextMsgLimitReached(NextMsgError):
    """The free monthly limit is reached (402)."""


class NextMsgRateLimited(NextMsgError):
    """Too many requests, or the Pro daily fair-use limit (429)."""


async def _error_text(response: aiohttp.ClientResponse) -> str:
    """The API's error message, or the HTTP status."""
    try:
        body: Any = await response.json(content_type=None)
    except ValueError, aiohttp.ClientError:
        body = None
    if isinstance(body, dict) and isinstance(body.get("error"), str):
        return body["error"]
    return f"HTTP {response.status}"


async def claim_code(session: aiohttp.ClientSession, code: str, name: str) -> str:
    """Exchange a pickup code from the app for a new agent key."""
    try:
        async with session.post(
            f"{API_URL}/v1/agent/claim",
            json={"code": code.strip(), "name": name[:40]},
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
            allow_redirects=False,
        ) as response:
            if response.status == 200:
                body: Any = await response.json(content_type=None)
                key = body.get("send_key") if isinstance(body, dict) else None
                if not isinstance(key, str) or not KEY_RE.match(key):
                    raise NextMsgConnectionError("Unexpected answer from NextMsg")
                return key
            text = await _error_text(response)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise NextMsgConnectionError(str(err) or type(err).__name__) from err
    if response.status == 400:
        raise NextMsgInvalidCode(text)
    if response.status == 409:
        raise NextMsgTooManyAgents(text)
    if response.status == 429:
        raise NextMsgRateLimited(text)
    raise NextMsgConnectionError(text)


class NextMsgClient:
    """Sends messages with one key."""

    def __init__(self, session: aiohttp.ClientSession, key: str) -> None:
        """Initialize the client."""
        self._session = session
        self._key = key

    async def send(self, message: str, channel: str) -> None:
        """Send a push to the phone."""
        try:
            async with self._session.post(
                f"{API_URL}/v1/send",
                json={"message": message, "channel": channel},
                headers={"Authorization": f"Bearer {self._key}"},
                timeout=TIMEOUT,
                allow_redirects=False,
            ) as response:
                if response.status == 200:
                    return
                text = await _error_text(response)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise NextMsgConnectionError(str(err) or type(err).__name__) from err
        if response.status == 401:
            raise NextMsgAuthError(text)
        if response.status in (400, 413):
            raise NextMsgInvalidMessage(text)
        if response.status == 402:
            raise NextMsgLimitReached(text)
        if response.status == 429:
            raise NextMsgRateLimited(text)
        raise NextMsgConnectionError(text)
