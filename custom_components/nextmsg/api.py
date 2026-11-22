"""Small client for the NextMsg API (https://api.nextmsg.app/openapi.json)."""

from __future__ import annotations

import re
from typing import Any, Final

import aiohttp

API_URL: Final = "https://api.nextmsg.app"
TIMEOUT: Final = aiohttp.ClientTimeout(total=15)

# Every NextMsg key, whether copied from the app or got with a code
KEY_RE: Final = re.compile(r"^nextmsg_live_[0-9a-f]{48}$")


class NextMsgError(Exception):
    """Base error. The message is the API's own explanation, when there is one."""


class NextMsgConnectionError(NextMsgError):
    """The API could not be reached or answered with a server error."""


class NextMsgAuthError(NextMsgError):
    """The key is wrong, rotated or revoked (401)."""


class NextMsgInvalidCode(NextMsgError):
    """The pickup code is wrong, already used or expired (400 on claim)."""


class NextMsgKeyLimit(NextMsgError):
    """The inbox has no key left (409 on claim).

    `pro_helps` is True for `key_limit_free` (Free: 2 keys, Pro: 20) and False for
    `key_limit_max` (Pro inbox at 20).
    """

    def __init__(self, text: str, pro_helps: bool) -> None:
        """Initialize the error."""
        super().__init__(text)
        self.pro_helps = pro_helps


class NextMsgInvalidMessage(NextMsgError):
    """The message or channel was rejected (400 or 413 on send)."""


class NextMsgLimitReached(NextMsgError):
    """The free monthly limit is reached (402)."""


class NextMsgRateLimited(NextMsgError):
    """Too many requests, or the Pro daily fair-use limit (429)."""


async def _error(response: aiohttp.ClientResponse) -> tuple[str, str | None]:
    """The API's error message (or the HTTP status) and its error code, if any."""
    try:
        body: Any = await response.json(content_type=None)
    except ValueError, aiohttp.ClientError:
        body = None
    if not isinstance(body, dict):
        return f"HTTP {response.status}", None
    text = body.get("error")
    code = body.get("code")
    return (
        text if isinstance(text, str) else f"HTTP {response.status}",
        code if isinstance(code, str) else None,
    )


async def claim_code(session: aiohttp.ClientSession, code: str, name: str) -> str:
    """Exchange a pickup code from the app for a new key of its own."""
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
            text, code = await _error(response)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise NextMsgConnectionError(str(err) or type(err).__name__) from err
    if response.status == 400:
        raise NextMsgInvalidCode(text)
    if response.status == 409:
        raise NextMsgKeyLimit(text, pro_helps=code != "key_limit_max")
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
                text, _ = await _error(response)
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
