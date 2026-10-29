"""The bearer: one endpoint's token, checked before its MCP app sees a request.

An endpoint with ``auth = "bearer"``, the default, is served over HTTP behind
``Bearer``: a pure ASGI wrapper around the endpoint's app, which streams the MCP
transport's responses through untouched. A request without the token, or with a wrong
one, is answered ``401 Unauthorized`` with ``WWW-Authenticate: Bearer
realm="xippios-mcp"``, ``error="invalid_token"`` added for a wrong token (RFC 6750,
section 3), and never reaches the endpoint. No ``resource_metadata`` is advertised:
claude.ai's OAuth sign-in needs an authorization server in front of the host, outside
0.1.0 (ADR-0026, decision 10; gap, row 310 (a)).

The token is read once, when ``--http`` starts, from the environment variable the
endpoint's ``token_env`` names (conventions §7); a missing or empty variable is a
``ConfigError``. The wrapper holds the token's SHA-256 digest, never the token, and
compares the digest of the given token with ``hmac.compare_digest``, so the comparison
takes the same time whatever the given token is. The ``Authorization`` header is
removed before the request reaches the endpoint's app, so no package code and no log
behind the bearer holds it.
"""

import hashlib
import hmac
import os

from starlette.types import ASGIApp, Receive, Scope, Send

from xippios.mcp.config import Endpoint, refusal

__all__ = ["REALM", "Bearer", "token_digest"]

REALM = "xippios-mcp"
"""The realm every ``WWW-Authenticate`` challenge of the host names."""

_AUTHORIZATION = b"authorization"
_SCHEME = b"bearer"


def token_digest(endpoint: Endpoint) -> bytes:
    """The SHA-256 digest of ``endpoint``'s bearer token, read from the environment.

    Args:
        endpoint: An endpoint with ``auth = "bearer"``, whose ``token_env`` names the
            variable, e.g. ``"XIPPIOS_MCP_AGRICULTURE_TOKEN"``.

    Raises:
        ConfigError: The variable is unset or empty; the message names the file, the
            endpoint and the variable, never a value.
    """
    name = endpoint.token_env
    if name is None:
        raise refusal(
            endpoint.path,
            ["endpoints", endpoint.name, "auth"],
            'is "none"; the endpoint has no bearer token',
        )
    token = os.environ.get(name, "")
    if not token:
        raise refusal(
            endpoint.path,
            ["endpoints", endpoint.name, "token_env"],
            f"{name} is not set or is empty; set it to the endpoint's bearer token in the "
            "environment before serving it over --http",
        )
    return hashlib.sha256(token.encode()).digest()


class Bearer:
    """An ASGI app that serves ``app`` to requests carrying the endpoint's bearer token.

    Args:
        app: The endpoint's app, e.g. the Starlette app of
            ``server.streamable_http_app()``.
        digest: The token's SHA-256 digest, from ``token_digest``.
    """

    def __init__(self, app: ASGIApp, digest: bytes) -> None:
        self.app = app
        self._digest = digest

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass a request with the token to ``app``, without its ``Authorization``.

        Args:
            scope: The ASGI scope; a lifespan scope passes unchecked.
            receive: The ASGI receive channel.
            send: The ASGI send channel.
        """
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)  # lifespan: no request, nothing to check
            return
        given: bytes | None = None
        headers: list[tuple[bytes, bytes]] = []
        for key, value in scope["headers"]:
            if key.lower() == _AUTHORIZATION:
                if given is None:
                    given = _token(value)
            else:
                headers.append((key, value))
        if not given:
            await _refuse(scope, send, invalid=False)
            return
        if not hmac.compare_digest(hashlib.sha256(given).digest(), self._digest):
            await _refuse(scope, send, invalid=True)
            return
        await self.app({**scope, "headers": headers}, receive, send)


def _token(value: bytes) -> bytes:
    """The token of an ``Authorization`` value, ``b""`` unless the scheme is ``Bearer``."""
    scheme, _, token = value.strip().partition(b" ")
    return token.strip() if scheme.lower() == _SCHEME else b""


async def _refuse(scope: Scope, send: Send, *, invalid: bool) -> None:
    """Answer 401 with the bearer challenge; a websocket is closed before it opens."""
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1008})
        return
    challenge = f'Bearer realm="{REALM}"'
    if invalid:
        challenge += ', error="invalid_token"'
    body = b"Unauthorized\n"
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"www-authenticate", challenge.encode()),
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
