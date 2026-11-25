"""The mount: one MCP server per endpoint, built from its packages' tool sets.

Every endpoint gets a server of its own, built from the tool sets its packages' ``build()``
returns (sdk-core ADR-0063, decision 4; ADR-0001 of this package). An endpoint that names
one package and no tool list serves ``build_server(tool_set)``, the server the package's
own entry point serves: named ``xippios-<source>``, with the package's instructions,
version and caps. A group, several packages, or an endpoint with an include or exclude
list is one ``MCPServer`` named ``xippios-<endpoint>``, on which ``register_tasks``
registers each package's tool set, narrowed to the list first, so the tools keep their
names (``usda_nass_get_data``) and their package's caps. Whether the server writes and
whether it is held to loopback come from the tool sets' ``read_only`` and
``loopback_only`` (sdk-core ADR-0063, decision 5). The host wraps no tool and reads no
answer: an error answer reaches the client as the package's tool returned it (ADR-0026,
decision 6).
"""

from dataclasses import dataclass

from mcp.server.mcpserver import MCPServer
from xippios.core import ConfigError, tool_name
from xippios.core.mcp import ToolSet, build_server, quiet_request_logging, register_tasks

from xippios.mcp._version import __version__
from xippios.mcp.config import Endpoint, HostConfig, PackageRef, refusal
from xippios.mcp.packages import Package, load_package

__all__ = ["BuildError", "Built", "build_all", "build_endpoint"]


class BuildError(ValueError):
    """Core refused a package's tool set while the host built an endpoint.

    Its ``ValueError`` (a write task without ``confirm``, a cap whose task is absent),
    raised when the package's ``build()`` or the host's narrowed copy makes the tool set,
    re-raised with the file, the endpoint and the package prefixed, so the command line
    tells it from an unrelated ``ValueError``.
    """


@dataclass(frozen=True, slots=True)
class Built:
    """An endpoint's server, ready to serve.

    Attributes:
        server: The server the host built for the endpoint.
        write: True for a write server: its tool sets write.
        held: True when a tool set of it writes or is ``loopback_only``, so the server is
            held to loopback unless authenticated or allowed (sdk-core ADR-0063,
            decision 5).
        tools: The tool names it serves, e.g. ``("usda_nass_get_data", ...)``.
    """

    server: MCPServer
    write: bool
    held: bool
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
    """The server ``endpoint`` serves, built from its packages' tool sets.

    Args:
        endpoint: An endpoint of ``load_config``'s result.

    Raises:
        ConfigError: A package is not installed, has no write server for ``:write`` or
            no ``build()``, or its tool set is not the write or read one the entry names;
            or a name of an include or exclude list is no task of its package. The
            message names the file, the endpoint and the key.
        BuildError: Core refused a package's tool set; the message names the file, the
            endpoint and the package.
    """
    packages = [_load(endpoint, ref) for ref in endpoint.packages]
    if len(packages) == 1 and not endpoint.include and not endpoint.exclude:
        tool_set = packages[0].tool_set
        return _built(build_server(tool_set), [tool_set])
    tool_sets = [_narrowed(endpoint, package) for package in packages]
    server = MCPServer(
        f"xippios-{endpoint.name}",
        version=__version__,
        instructions=_instructions(endpoint, tool_sets),
    )
    quiet_request_logging()
    for tool_set in tool_sets:
        register_tasks(server, tool_set)
    return _built(server, tool_sets)


def _built(server: MCPServer, tool_sets: list[ToolSet]) -> Built:
    return Built(
        server=server,
        write=any(not tool_set.read_only for tool_set in tool_sets),
        held=any(not tool_set.read_only or tool_set.loopback_only for tool_set in tool_sets),
        tools=tuple(tool_name(ts.source, fn) for ts in tool_sets for fn in ts.tasks),
    )


def _load(endpoint: Endpoint, ref: PackageRef) -> Package:
    try:
        return load_package(ref)
    except ConfigError as exc:
        raise refusal(endpoint.path, ["endpoints", endpoint.name, "packages"], str(exc)) from exc
    except ValueError as exc:
        raise BuildError(f"{endpoint.path}: endpoints.{endpoint.name}: {ref}: {exc}") from exc


def _narrowed(endpoint: Endpoint, package: Package) -> ToolSet:
    slug = package.ref.slug
    include, exclude = endpoint.include.get(slug), endpoint.exclude.get(slug)
    try:
        return package.narrowed(include=include, exclude=exclude)
    except ConfigError as exc:
        kind = "include" if include is not None else "exclude" if exclude is not None else None
        key = ["endpoints", endpoint.name, *([kind, slug] if kind else ["packages"])]
        raise refusal(endpoint.path, key, str(exc)) from exc
    except ValueError as exc:
        raise BuildError(
            f"{endpoint.path}: endpoints.{endpoint.name}: {package.ref}: {exc}"
        ) from exc


def _instructions(endpoint: Endpoint, tool_sets: list[ToolSet]) -> str:
    """One sentence on what the endpoint serves, from its packages and their tool counts."""
    parts = [f"{tool_set.source} ({len(tool_set.tasks)})" for tool_set in tool_sets]
    served = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
    total = sum(len(tool_set.tasks) for tool_set in tool_sets)
    kind = "write" if endpoint.write else "read-only"
    sentence = (
        f"The xippios-mcp endpoint {endpoint.name} serves {total} {kind} tools of {served}, "
        "each named with its package's slug as prefix"
    )
    if endpoint.write:
        sentence += "; every tool takes confirm and returns a preview unless confirm is true"
    return sentence + "."
