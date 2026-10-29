"""The mount: one MCP server per endpoint, the package's own or one the host builds.

An endpoint that names one package and no tool list serves that package's own server,
the object ``<path>.mcp.server`` (``<path>.mcp_write.server`` for ``<slug>:write``) as
the package built it, its instructions, caps and read and write split included
(ADR-0026, decision 3). A group, several packages, or an endpoint with an include or
exclude list is one ``MCPServer`` the host builds: per package, the kept names of
``tasks.__all__`` registered with core's ``register_tasks`` under the config's slug,
which equals the package's source slug, so the tools keep their names
(``usda_nass_get_data``), and ``MCP_CAPS`` cut to the kept tasks first, since
``register_tasks`` refuses a cap whose task is absent (Johannes, 2026-10-29, G5 question
2; queue row 306). The host wraps no tool and reads no answer: an error answer reaches the
client as the package's tool returned it (ADR-0026, decision 6).
"""

from dataclasses import dataclass

from mcp.server.mcpserver import MCPServer
from xippios.core import ConfigError
from xippios.core.mcp import tool_name

# Outside core's public surface: queue row 297 decides whether core 0.4.0 exports
# register_tasks, is_write_server and quiet_request_logging from xippios.core.mcp.
from xippios.core.mcp.server import is_write_server, quiet_request_logging, register_tasks

from xippios.mcp._version import __version__
from xippios.mcp.config import Endpoint, HostConfig, PackageRef, refusal
from xippios.mcp.packages import Package, load_package

__all__ = ["BuildError", "Built", "build_all", "build_endpoint"]


class BuildError(ValueError):
    """Core's ``register_tasks`` refused a package's tasks for a server the host builds.

    Its ``ValueError`` (a cap whose task is absent, a write task without ``confirm``),
    re-raised with the file, the endpoint and the package prefixed, so the command line
    tells it from an unrelated ``ValueError``.
    """


@dataclass(frozen=True, slots=True)
class Built:
    """An endpoint's server, ready to serve.

    Attributes:
        server: The package's own server, or the one the host built.
        write: True for a write server (core's ``is_write_server``).
        host_built: True when the host built the server: a group or a tool list.
        tools: The tool names it serves, e.g. ``("usda_nass_get_data", ...)``.
    """

    server: MCPServer
    write: bool
    host_built: bool
    tools: tuple[str, ...]


def build_all(config: HostConfig) -> dict[str, Built]:
    """Build every endpoint of ``config``, in the file's order.

    Args:
        config: The checked config, e.g. ``load_config(Path("host.toml"))``.

    Raises:
        ConfigError: See ``build_endpoint``.
        BuildError: See ``build_endpoint``.
    """
    return {name: build_endpoint(endpoint) for name, endpoint in config.endpoints.items()}


def build_endpoint(endpoint: Endpoint) -> Built:
    """The server ``endpoint`` serves, checked against its packages.

    Args:
        endpoint: An endpoint of ``load_config``'s result.

    Raises:
        ConfigError: A package is unknown, not installed or has no write server for
            ``:write``; a name of an include or exclude list is no tool of its package;
            or a package's own server is not the write or read server the entry names.
            The message names the file, the endpoint and the key.
        BuildError: ``register_tasks`` refused a package's tasks, a cap or a write task
            without ``confirm``; the message names the file, the endpoint and the package.
    """
    packages = [_load(endpoint, ref) for ref in endpoint.packages]
    if len(packages) == 1 and not endpoint.include and not endpoint.exclude:
        return _package_built(endpoint, packages[0])
    return _host_built(endpoint, packages)


def _load(endpoint: Endpoint, ref: PackageRef) -> Package:
    try:
        return load_package(ref)
    except ConfigError as exc:
        raise refusal(endpoint.path, ["endpoints", endpoint.name, "packages"], str(exc)) from exc


def _package_built(endpoint: Endpoint, package: Package) -> Built:
    # The package's own object, shared by every endpoint that mounts it alone: its
    # streamable_http_app replaces the server's one session manager, so the HTTP
    # transport (the next step) refuses mounting one package-built server on two
    # endpoints.
    server = package.server
    if is_write_server(server) != package.ref.write:
        kind = "a write server" if is_write_server(server) else "a read server"
        raise refusal(
            endpoint.path,
            ["endpoints", endpoint.name, "packages"],
            f"{package.ref}: the package's server {server.name} is {kind}",
        )
    tools = tuple(tool_name(package.ref.slug, package.functions[name]) for name in package.tools)
    return Built(server=server, write=package.ref.write, host_built=False, tools=tools)


def _kept(endpoint: Endpoint, package: Package) -> tuple[str, ...]:
    slug = package.ref.slug
    include, exclude = endpoint.include.get(slug), endpoint.exclude.get(slug)
    try:
        return package.kept(include=include, exclude=exclude)
    except ConfigError as exc:
        kind = "include" if include is not None else "exclude" if exclude is not None else None
        key = ["endpoints", endpoint.name, *([kind, slug] if kind else ["packages"])]
        raise refusal(endpoint.path, key, str(exc)) from exc


def _host_built(endpoint: Endpoint, packages: list[Package]) -> Built:
    selected = [(package, _kept(endpoint, package)) for package in packages]
    server = MCPServer(
        f"xippios-{endpoint.name}",
        version=__version__,
        instructions=_instructions(endpoint, [(p.ref.slug, len(kept)) for p, kept in selected]),
    )
    quiet_request_logging()
    names: list[str] = []
    for package, kept in selected:
        caps = {name: cap for name, cap in (package.caps or {}).items() if name in kept}
        try:
            names += register_tasks(
                server,
                package.ref.slug,
                [package.functions[name] for name in kept],
                caps=caps or None,
                read_only=not package.ref.write,
            )
        except ValueError as exc:
            raise BuildError(
                f"{endpoint.path}: endpoints.{endpoint.name}: {package.ref}: {exc}"
            ) from exc
    return Built(server=server, write=endpoint.write, host_built=True, tools=tuple(names))


def _instructions(endpoint: Endpoint, counts: list[tuple[str, int]]) -> str:
    """One sentence on what the endpoint serves, from its packages and their tool counts."""
    parts = [f"{slug} ({count})" for slug, count in counts]
    served = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
    total = sum(count for _, count in counts)
    kind = "write" if endpoint.write else "read-only"
    sentence = (
        f"The xippios-mcp endpoint {endpoint.name} serves {total} {kind} tools of {served}, "
        "each named with its package's slug as prefix"
    )
    if endpoint.write:
        sentence += "; every tool takes confirm and returns a preview unless confirm is true"
    return sentence + "."
