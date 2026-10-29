"""The HTTP transport: every endpoint at ``/<name>/mcp`` in one Starlette app.

``build_app`` mounts each endpoint's server at ``/<name>`` with the mcp SDK's
streamable-HTTP path ``/mcp``, so an endpoint answers at ``/<name>/mcp``, wraps the
endpoints with ``auth = "bearer"`` in the bearer (``xippios.mcp.auth``), and enters
every server's session manager in the app's one lifespan, since Starlette runs no
lifespan of a mounted app (gap, row 310 (f)). ``serve_http`` serves the app with
uvicorn.

Before it mounts anything, ``build_app`` applies the checks that need the bind host or
the whole set of endpoints (ADR-0026, decision 5; gap, row 310):

- An endpoint with ``auth = "none"`` that serves a write server is served on a loopback
  host only, unless it sets ``allow_remote = true``: core's ``main`` keeps a write
  server on loopback without ``--allow-remote`` (ADR-0014, decision 9), and the host
  does not run ``main``, so it applies the rule itself (queue row 296).
- A package's own server object serves one HTTP endpoint: ``streamable_http_app``
  replaces the server's one session manager, so a second mount would take the first's
  (gap, row 310 (d)).
- The ``[http]`` table's ``allowed_hosts`` and ``allowed_origins`` become the mcp SDK's
  ``TransportSecuritySettings``; without them the SDK's own default applies, its Host
  and Origin checks on a loopback bind host and none beyond (gap, row 310 (b)).
"""

import contextlib
from collections.abc import AsyncIterator, Mapping

import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import ASGIApp

# Outside core's public surface: queue row 297 decides whether core 0.4.0 exports
# quiet_request_logging from xippios.core.mcp.
from xippios.core.mcp.server import quiet_request_logging

from xippios.mcp.auth import Bearer, token_digest
from xippios.mcp.config import HostConfig, HttpConfig, refusal
from xippios.mcp.servers import Built

__all__ = ["MCP_PATH", "build_app", "serve_http", "transport_security"]

# A private copy of core's _LOOPBACK_HOSTS (xippios.core.mcp.cli), as sdk-google-mail
# carries one (ADR-0025, D-a). Queue row 282 brings the loopback option into core 0.4.0,
# the host its second consumer, which is ADR-0023 decision 2's entry rule; until then
# each consumer keeps its copy with this comment naming the row (ADR-0023, decision 4).
# Exactly the mcp SDK's own list (mcp 2.3.0): for these hosts, without
# transport_security, the SDK turns on its DNS-rebinding protection (Host and Origin
# checks), which is why the match is exact.
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
"""The bind hosts an ``auth = "none"`` write endpoint is served on without ``allow_remote``."""

MCP_PATH = "/mcp"
"""The mcp SDK's streamable-HTTP path, under each endpoint's ``/<name>``."""


def transport_security(http: HttpConfig) -> TransportSecuritySettings | None:
    """The mcp SDK's Host and Origin settings for the ``[http]`` table.

    Args:
        http: The config's ``[http]`` table, e.g.
            ``HttpConfig(allowed_hosts=("mcp.example.com",))``.

    Returns:
        ``None`` when the table names no host, so the SDK applies its own default for
        the bind host; otherwise the SDK's DNS-rebinding protection with the table's
        lists.
    """
    if not http.allowed_hosts:
        return None
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(http.allowed_hosts),
        allowed_origins=list(http.allowed_origins),
    )


def build_app(config: HostConfig, built: Mapping[str, Built], *, host: str) -> Starlette:
    """Check the endpoints for HTTP on ``host`` and mount them in one Starlette app.

    Reads the bearer token of every endpoint with ``auth = "bearer"`` from the variable
    its ``token_env`` names, once; the app holds the tokens' digests only.

    Args:
        config: The config, from ``load_config``.
        built: Per endpoint name, its server, from ``build_all(config)``.
        host: The address uvicorn binds, e.g. ``"127.0.0.1"`` or ``"0.0.0.0"``.

    Raises:
        ConfigError: An ``auth = "none"`` write endpoint on a host beyond loopback
            without ``allow_remote = true``; a package's own server on two endpoints; or
            a bearer endpoint whose token variable is unset or empty. The message names
            the file, the endpoint and the key, never a token.
    """
    _check_loopback(config, built, host)
    _check_mounted_once(config, built)
    digests = {
        name: token_digest(endpoint)
        for name, endpoint in config.endpoints.items()
        if endpoint.auth == "bearer"
    }
    security = transport_security(config.http)
    routes: list[Mount] = []
    managers: list[StreamableHTTPSessionManager] = []
    for name in config.endpoints:
        server = built[name].server
        app: ASGIApp = server.streamable_http_app(
            streamable_http_path=MCP_PATH, transport_security=security, host=host
        )
        managers.append(server.session_manager)  # the one the call above created
        if name in digests:
            app = Bearer(app, digests[name])
        routes.append(Mount(f"/{name}", app=app))

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with contextlib.AsyncExitStack() as stack:
            for manager in managers:
                await stack.enter_async_context(manager.run())
            yield

    return Starlette(routes=routes, lifespan=lifespan)


def _check_loopback(config: HostConfig, built: Mapping[str, Built], host: str) -> None:
    if host in _LOOPBACK_HOSTS:
        return
    for name, endpoint in config.endpoints.items():
        if endpoint.auth == "none" and built[name].write and not endpoint.allow_remote:
            raise refusal(
                config.path,
                ["endpoints", name, "auth"],
                f'is "none" on a write server, which then carries no authentication, and '
                f"--host {host} is beyond loopback; serve it on a loopback --host "
                f'({", ".join(_LOOPBACK_HOSTS)}), set auth = "bearer" with a token_env, or '
                "set allow_remote = true and put it behind a gateway",
            )


def _check_mounted_once(config: HostConfig, built: Mapping[str, Built]) -> None:
    first: dict[int, str] = {}
    for name in config.endpoints:
        server = built[name].server
        other = first.setdefault(id(server), name)
        if other != name:
            raise refusal(
                config.path,
                ["endpoints", name, "packages"],
                f"mounts the package's own server {server.name}, which endpoints.{other} "
                "mounts too, and one server object serves one HTTP endpoint; give one of "
                "the two an include or exclude list, which makes its server one the host "
                "builds, or drop one",
            )


def serve_http(app: Starlette, host: str, port: int) -> None:
    """Serve ``app`` with uvicorn on ``host`` and ``port`` until the process is stopped.

    uvicorn's access log names the client address, the method, the path with its query
    string and the status of each request, never a header, so never a bearer token; the
    httpx and httpcore loggers are quieted again after uvicorn configured logging
    (ADR-0005).

    Args:
        app: The app from ``build_app``.
        host: The bind address, e.g. ``"127.0.0.1"``.
        port: The port, e.g. ``8000``.
    """
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    quiet_request_logging()
    uvicorn.Server(config).run()
