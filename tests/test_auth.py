"""The bearer: the token's digest from the environment, and the 401 before the endpoint.

The token below is a test value set with ``monkeypatch.setenv``; it never leaves the
test. Requests reach the bearer in-process through httpx2's ``ASGITransport``.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx2
import pytest
from starlette.types import Message, Receive, Scope, Send
from xippios.core import ConfigError

from xippios.mcp.auth import REALM, Bearer, token_digest
from xippios.mcp.config import Endpoint, load_config

TOKEN = "test-bearer-for-the-unit-tests-only"  # pragma: allowlist secret
VARIABLE = "XIPPIOS_MCP_AGRICULTURE_TOKEN"
CHALLENGE = 'Bearer realm="xippios-mcp"'
INVALID = 'Bearer realm="xippios-mcp", error="invalid_token"'


def _endpoint(tmp_path: Path, body: str = f'token_env = "{VARIABLE}"') -> Endpoint:
    path = tmp_path / "host.toml"
    path.write_text(
        f'[endpoints.agriculture]\npackages = ["usda-nass"]\n{body}\n', encoding="utf-8"
    )
    return load_config(path).endpoints["agriculture"]


async def _echo(scope: Scope, receive: Receive, send: Send) -> None:
    """An endpoint that answers 200 with the header names it received."""
    names = sorted(key.decode() for key, _ in scope["headers"])
    body = json.dumps(names).encode()
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": body})


def _client() -> httpx2.AsyncClient:
    app = Bearer(_echo, hashlib.sha256(TOKEN.encode()).digest())
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    )


def test_the_digest_comes_from_the_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(VARIABLE, TOKEN)
    assert token_digest(_endpoint(tmp_path)) == hashlib.sha256(TOKEN.encode()).digest()


@pytest.mark.parametrize("value", [None, ""], ids=["unset", "empty"])
def test_a_missing_or_empty_variable_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(VARIABLE, raising=False)
    else:
        monkeypatch.setenv(VARIABLE, value)
    with pytest.raises(ConfigError) as refused:
        token_digest(_endpoint(tmp_path))
    message = str(refused.value)
    assert message.startswith(f"{tmp_path / 'host.toml'}: endpoints.agriculture.token_env: ")
    assert f"{VARIABLE} is not set or is empty" in message


@pytest.mark.parametrize(
    "value",
    [f" {TOKEN}", f"{TOKEN}\n", f"\t{TOKEN} ", "   "],
    ids=["leading", "trailing newline", "both", "blanks only"],
)
def test_a_value_with_surrounding_whitespace_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(VARIABLE, value)
    with pytest.raises(ConfigError) as refused:
        token_digest(_endpoint(tmp_path))
    message = str(refused.value)
    assert message.startswith(f"{tmp_path / 'host.toml'}: endpoints.agriculture.token_env: ")
    assert f"{VARIABLE} has leading or trailing whitespace" in message
    assert TOKEN not in message


def test_an_endpoint_without_a_bearer_has_no_digest(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match=r"endpoints\.agriculture\.auth: is \"none\""):
        token_digest(_endpoint(tmp_path, 'auth = "none"'))


def test_the_bearer_holds_the_digest_not_the_token() -> None:
    bearer = Bearer(_echo, hashlib.sha256(TOKEN.encode()).digest())
    held: dict[str, Any] = vars(bearer)
    assert TOKEN not in repr(held)
    assert TOKEN.encode() not in held.values()


@pytest.mark.anyio
async def test_a_request_without_a_token() -> None:
    async with _client() as client:
        response = await client.post("/mcp", json={})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == CHALLENGE
    assert "resource_metadata" not in response.headers["www-authenticate"]
    assert response.text == "Unauthorized\n"


@pytest.mark.anyio
async def test_a_wrong_token() -> None:
    async with _client() as client:
        response = await client.post("/mcp", json={}, headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == INVALID
    assert response.text == "Unauthorized\n"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "value",
    [
        pytest.param(f"Basic {TOKEN}", id="another scheme"),
        pytest.param("Bearer", id="the scheme without a token"),
        pytest.param("Bearer   ", id="the scheme and blanks"),
        pytest.param(TOKEN, id="the token without a scheme"),
    ],
)
async def test_no_bearer_credentials(value: str) -> None:
    async with _client() as client:
        response = await client.post("/mcp", json={}, headers={"Authorization": value})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == CHALLENGE


@pytest.mark.anyio
@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER"])
async def test_the_right_token_passes_without_its_header(scheme: str) -> None:
    async with _client() as client:
        response = await client.post(
            "/mcp", json={}, headers={"Authorization": f"{scheme} {TOKEN}"}
        )
    assert response.status_code == 200
    names = response.json()
    assert "authorization" not in names
    assert "content-type" in names  # the other headers pass through


def test_the_realm() -> None:
    assert REALM == "xippios-mcp"


@pytest.mark.anyio
async def test_a_lifespan_passes_through() -> None:
    seen: list[str] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope["type"])

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(message: Message) -> None:
        raise AssertionError("the bearer sends nothing for a lifespan")

    await Bearer(inner, b"digest")({"type": "lifespan"}, receive, send)
    assert seen == ["lifespan"]


@pytest.mark.anyio
async def test_a_websocket_without_the_token_is_closed() -> None:
    sent: list[Message] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        raise AssertionError("the endpoint must not see the request")

    async def receive() -> Message:
        return {"type": "websocket.connect"}

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {"type": "websocket", "path": "/mcp", "headers": []}
    await Bearer(inner, hashlib.sha256(TOKEN.encode()).digest())(scope, receive, send)
    assert sent == [{"type": "websocket.close", "code": 1008}]
