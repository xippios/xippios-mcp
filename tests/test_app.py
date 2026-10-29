"""The HTTP transport: the mount at ``/<name>/mcp``, the bearer, the Host check and the
startup refusals that need the bind host.

Requests reach the Starlette app in-process through httpx2's ``ASGITransport``, which
runs no lifespan, so each test enters the app's lifespan itself; MCP sessions run on the
mcp SDK's own streamable-HTTP client over that transport. No test binds a port: uvicorn
is reached only with ``Server.run`` stubbed. The token below is a test value set with
``monkeypatch.setenv``; it never leaves the test.
"""

import contextlib
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
import uvicorn
import xippios.usda.nass.mcp
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from xippios.core import ConfigError
from xippios.core.mcp import cli as core_cli

from xippios.mcp.app import _LOOPBACK_HOSTS, build_app, serve_http, transport_security
from xippios.mcp.config import HttpConfig, load_config
from xippios.mcp.servers import build_all

TOKEN = "test-bearer-for-the-unit-tests-only"  # pragma: allowlist secret
VARIABLE = "XIPPIOS_MCP_AGRICULTURE_TOKEN"
BASE = "http://127.0.0.1:8000"
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}

TWO = f"""
[endpoints.agriculture]
packages = ["usda-nass", "comtrade"]
token_env = "{VARIABLE}"

[endpoints.open]
packages = ["usda-nass"]
auth = "none"
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "host.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _app(tmp_path: Path, text: str, host: str = "127.0.0.1") -> Starlette:
    config = load_config(_write(tmp_path, text))
    return build_app(config, build_all(config), host=host)


def _refused(tmp_path: Path, text: str, host: str = "127.0.0.1") -> str:
    with pytest.raises(ConfigError) as refused:
        _app(tmp_path, text, host)
    message = str(refused.value)
    assert message.startswith(f"{tmp_path / 'host.toml'}: endpoints."), message
    return message


@contextlib.asynccontextmanager
async def _served(app: Starlette) -> AsyncIterator[httpx2.ASGITransport]:
    """The app's lifespan entered, every session manager running, and a transport to it."""
    async with app.router.lifespan_context(app):
        yield httpx2.ASGITransport(app=app)


@contextlib.asynccontextmanager
async def _session(
    transport: httpx2.ASGITransport, path: str, headers: dict[str, str] | None = None
) -> AsyncIterator[Client]:
    """An MCP session with the initialize handshake, over the in-process transport."""
    async with (
        httpx2.AsyncClient(transport=transport, base_url=BASE, headers=headers) as http,
        Client(streamable_http_client(f"{BASE}{path}", http_client=http), mode="legacy") as mcp,
    ):
        yield mcp


async def _post(
    transport: httpx2.ASGITransport, path: str, headers: dict[str, str] | None = None
) -> httpx2.Response:
    async with httpx2.AsyncClient(transport=transport, base_url=BASE) as http:
        return await http.post(path, json=INITIALIZE, headers={**MCP_HEADERS, **(headers or {})})


@pytest.mark.anyio
async def test_each_endpoint_at_its_path_with_its_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(VARIABLE, TOKEN)
    config = load_config(_write(tmp_path, TWO))
    built = build_all(config)
    app = build_app(config, built, host="127.0.0.1")
    async with _served(app) as transport:
        missing = await _post(transport, "/agriculture/mcp")
        assert missing.status_code == 401
        assert missing.headers["www-authenticate"] == 'Bearer realm="xippios-mcp"'

        wrong = await _post(transport, "/agriculture/mcp", {"Authorization": "Bearer wrong"})
        assert wrong.status_code == 401
        assert wrong.headers["www-authenticate"] == (
            'Bearer realm="xippios-mcp", error="invalid_token"'
        )

        right = {"Authorization": f"Bearer {TOKEN}"}
        async with _session(transport, "/agriculture/mcp", right) as mcp:
            assert mcp.server_info is not None
            assert mcp.server_info.name == "xippios-agriculture"
            listed = await mcp.list_tools()
        assert sorted(tool.name for tool in listed.tools) == sorted(built["agriculture"].tools)

        async with _session(transport, "/open/mcp") as mcp:  # auth = "none": no header
            assert mcp.server_info is not None
            assert mcp.server_info.name == xippios.usda.nass.mcp.server.name
            listed = await mcp.list_tools()
        assert sorted(tool.name for tool in listed.tools) == sorted(built["open"].tools)

        # The bearer guards the whole mount, a path the endpoint does not serve included.
        assert (await _post(transport, "/agriculture/other")).status_code == 401
        assert (await _post(transport, "/open/other")).status_code == 404


@pytest.mark.anyio
async def test_a_raw_initialize_on_an_open_endpoint(tmp_path: Path) -> None:
    app = _app(tmp_path, '[endpoints.open]\npackages = ["usda-nass"]\nauth = "none"\n')
    async with _served(app) as transport:
        response = await _post(transport, "/open/mcp")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_the_loopback_default_refuses_a_foreign_host(tmp_path: Path) -> None:
    """Without [http], the mcp SDK checks Host and Origin itself on a loopback bind."""
    app = _app(tmp_path, '[endpoints.open]\npackages = ["usda-nass"]\nauth = "none"\n')
    async with _served(app) as transport:
        foreign = await _post(transport, "/open/mcp", {"Host": "mcp.example.com"})
        origin = await _post(transport, "/open/mcp", {"Origin": "https://evil.example.com"})
    assert (foreign.status_code, foreign.text) == (421, "Invalid Host header")
    assert (origin.status_code, origin.text) == (403, "Invalid Origin header")


@pytest.mark.anyio
async def test_beyond_loopback_without_http_there_is_no_host_check(tmp_path: Path) -> None:
    app = _app(
        tmp_path, '[endpoints.open]\npackages = ["usda-nass"]\nauth = "none"\n', host="0.0.0.0"
    )
    async with _served(app) as transport:
        response = await _post(transport, "/open/mcp", {"Host": "anything.example.com"})
    assert response.status_code == 200


@pytest.mark.anyio
async def test_allowed_hosts_and_origins(tmp_path: Path) -> None:
    text = (
        '[endpoints.open]\npackages = ["usda-nass"]\nauth = "none"\n\n[http]\n'
        'allowed_hosts = ["mcp.example.com"]\nallowed_origins = ["https://mcp.example.com"]\n'
    )
    app = _app(tmp_path, text, host="0.0.0.0")
    async with _served(app) as transport:
        allowed = await _post(
            transport,
            "/open/mcp",
            {"Host": "mcp.example.com", "Origin": "https://mcp.example.com"},
        )
        foreign = await _post(transport, "/open/mcp", {"Host": "evil.example.com"})
        loopback = await _post(transport, "/open/mcp")  # the list replaces the default
        origin = await _post(
            transport, "/open/mcp", {"Host": "mcp.example.com", "Origin": "https://evil.com"}
        )
    assert allowed.status_code == 200
    assert (foreign.status_code, foreign.text) == (421, "Invalid Host header")
    assert loopback.status_code == 421
    assert (origin.status_code, origin.text) == (403, "Invalid Origin header")


@pytest.mark.anyio
async def test_the_bearer_runs_before_the_host_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(VARIABLE, TOKEN)
    text = (
        f'[endpoints.agriculture]\npackages = ["usda-nass"]\ntoken_env = "{VARIABLE}"\n\n'
        '[http]\nallowed_hosts = ["mcp.example.com"]\n'
    )
    app = _app(tmp_path, text)
    async with _served(app) as transport:
        anonymous = await _post(transport, "/agriculture/mcp", {"Host": "evil.example.com"})
        foreign = await _post(
            transport,
            "/agriculture/mcp",
            {"Host": "evil.example.com", "Authorization": f"Bearer {TOKEN}"},
        )
        allowed = await _post(
            transport,
            "/agriculture/mcp",
            {"Host": "mcp.example.com", "Authorization": f"Bearer {TOKEN}"},
        )
    assert anonymous.status_code == 401
    assert foreign.status_code == 421
    assert allowed.status_code == 200


def test_transport_security() -> None:
    assert transport_security(HttpConfig()) is None
    settings = transport_security(
        HttpConfig(allowed_hosts=("mcp.example.com",), allowed_origins=("https://x.example",))
    )
    assert settings == TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["mcp.example.com"],
        allowed_origins=["https://x.example"],
    )


# The loopback rule (ADR-0026, decision 5; queue row 296).

WRITE_NONE = '[endpoints.accounting-write]\npackages = ["cashctrl:write"]\nauth = "none"\n'


def test_the_loopback_hosts_are_cores() -> None:
    """The host's copy (queue row 282) stays core's private list, exactly."""
    assert _LOOPBACK_HOSTS == core_cli._LOOPBACK_HOSTS


def test_an_open_write_endpoint_beyond_loopback_is_refused(tmp_path: Path) -> None:
    message = _refused(tmp_path, WRITE_NONE, host="0.0.0.0")
    assert message.startswith(f"{tmp_path / 'host.toml'}: endpoints.accounting-write.auth: ")
    assert '"none" on a write server' in message
    assert "--host 0.0.0.0 is beyond loopback" in message
    assert "set allow_remote = true" in message
    assert 'auth = "bearer"' in message


@pytest.mark.parametrize("host", _LOOPBACK_HOSTS)
def test_an_open_write_endpoint_on_loopback(tmp_path: Path, host: str) -> None:
    assert isinstance(_app(tmp_path, WRITE_NONE, host=host), Starlette)


def test_an_open_write_endpoint_with_allow_remote(tmp_path: Path) -> None:
    app = _app(tmp_path, f"{WRITE_NONE}allow_remote = true\n", host="0.0.0.0")
    assert isinstance(app, Starlette)


def test_a_bearer_write_endpoint_beyond_loopback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XIPPIOS_MCP_ACCOUNTING_WRITE_TOKEN", TOKEN)
    text = (
        '[endpoints.accounting-write]\npackages = ["cashctrl:write"]\n'
        'token_env = "XIPPIOS_MCP_ACCOUNTING_WRITE_TOKEN"\n'
    )
    assert isinstance(_app(tmp_path, text, host="0.0.0.0"), Starlette)


def test_an_open_read_endpoint_beyond_loopback(tmp_path: Path) -> None:
    text = '[endpoints.open]\npackages = ["usda-nass"]\nauth = "none"\n'
    assert isinstance(_app(tmp_path, text, host="0.0.0.0"), Starlette)


def test_the_loopback_check_runs_before_a_token_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bearer endpoint whose variable is unset does not hide the loopback refusal."""
    monkeypatch.delenv(VARIABLE, raising=False)
    text = f'[endpoints.agriculture]\npackages = ["usda-nass"]\ntoken_env = "{VARIABLE}"\n\n'
    message = _refused(tmp_path, f"{text}{WRITE_NONE}", host="0.0.0.0")
    assert message.startswith(f"{tmp_path / 'host.toml'}: endpoints.accounting-write.auth: ")
    assert VARIABLE not in message


def test_the_loopback_match_is_exact(tmp_path: Path) -> None:
    """127.0.0.2 is loopback too, but the SDK turns its Host check on for the three only."""
    assert "127.0.0.2" in _refused(tmp_path, WRITE_NONE, host="127.0.0.2")


# One package's own server on one HTTP endpoint (gap, row 310 (d)).

TWICE = """
[endpoints.first]
packages = ["usda-nass"]
auth = "none"

[endpoints.second]
packages = ["usda-nass"]
auth = "none"
"""


def test_a_packages_own_server_on_two_endpoints_is_refused(tmp_path: Path) -> None:
    message = _refused(tmp_path, TWICE)
    assert message.startswith(f"{tmp_path / 'host.toml'}: endpoints.second.packages: ")
    assert "which endpoints.first mounts too" in message
    assert xippios.usda.nass.mcp.server.name in message
    assert "an include or exclude list" in message


@pytest.mark.anyio
async def test_a_list_on_one_of_the_two_makes_it_build(tmp_path: Path) -> None:
    app = _app(tmp_path, f'{TWICE}exclude = {{ usda-nass = ["get_counts"] }}\n')
    async with _served(app) as transport:
        for path in ("/first/mcp", "/second/mcp"):
            async with _session(transport, path) as mcp:
                listed = await mcp.list_tools()
            names = {tool.name for tool in listed.tools}
            assert ("usda_nass_get_counts" in names) is (path == "/first/mcp")


def test_the_static_checks_run_before_a_token_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal that needs no token comes first, so an operator fixes the file first."""
    monkeypatch.delenv("XIPPIOS_MCP_FIRST_TOKEN", raising=False)
    text = TWICE.replace('auth = "none"', 'token_env = "XIPPIOS_MCP_FIRST_TOKEN"', 1)
    assert "which endpoints.first mounts too" in _refused(tmp_path, text)


def test_a_missing_token_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(VARIABLE, raising=False)
    message = _refused(tmp_path, TWO)
    assert message.startswith(f"{tmp_path / 'host.toml'}: endpoints.agriculture.token_env: ")
    assert f"{VARIABLE} is not set or is empty" in message


def test_serve_http_hands_the_app_to_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    """``Server.run`` is stubbed: no port is bound."""
    served: list[uvicorn.Config] = []

    def run(self: uvicorn.Server, sockets: Any = None) -> None:
        served.append(self.config)

    monkeypatch.setattr(uvicorn.Server, "run", run)
    logging.getLogger("httpx").setLevel(logging.INFO)
    app = Starlette()
    serve_http(app, "127.0.0.1", 8765)
    [config] = served
    assert (config.app, config.host, config.port) == (app, "127.0.0.1", 8765)
    assert logging.getLogger("httpx").level == logging.WARNING
