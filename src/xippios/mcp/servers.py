"""The mount: one MCP server per endpoint, built from its packages' tool sets.

Every endpoint gets a server of its own, built from the tool sets its packages' ``build()``
returns (sdk-core ADR-0063, decision 4; ADR-0001 of this package). An endpoint of one
package serves ``build_server(tool_set)``, the server the package's own entry point serves,
with the package's instructions, version and caps: named ``xippios-<source>``, or
``xippios-<endpoint>`` with an include or exclude list, to which its tool set is narrowed.
A group, several packages, is one ``MCPServer`` named ``xippios-<endpoint>``, on which
``register_tasks`` registers each package's tool set, narrowed to its list, so the tools
keep their names (``usda_nass_get_data``) and their package's caps; its instructions open
with the host's sentence and name each package's own under its slug. Before a server is
built, each tool set's option hook is applied at the defaults of the package's entry point,
as that entry point applies it when it runs without options (ADR-0001, decision 7).
Whether the server writes and whether it is held to loopback come from the tool sets'
``read_only`` and ``loopback_only`` (sdk-core ADR-0063, decision 5). The host wraps no tool
and reads no answer: an error answer reaches the client as the package's tool returned it
(ADR-0026, decision 6).
"""

from dataclasses import dataclass

from mcp.server.mcpserver import MCPServer
from xippios.core import ConfigError, XippiosError, tool_name
from xippios.core.mcp import ToolSet, build_server, quiet_request_logging, register_tasks

from xippios.mcp._version import __version__
from xippios.mcp.config import Endpoint, HostConfig, PackageRef, refusal
from xippios.mcp.packages import Package, load_package

__all__ = ["BuildError", "Built", "build_all", "build_endpoint"]


class BuildError(ValueError):
    """A package's import, its ``build()``, the narrowed copy or its option hook raised.

    Every ``ValueError`` or ``TypeError`` raised at the import, by ``build()`` or by the
    narrowed copy: core's refusal of a declaration, a write task without ``confirm`` or
    ``MCP_CAPS`` no mapping say, and a package's own error alike, since core raises its
    refusals as these plain classes and the host cannot tell the two apart. And the
    ``ValueError`` of ``option_defaults()`` for an option without a default, or the
    ``XippiosError`` or ``ValueError`` of the package's option hook, applied at those
    defaults. Re-raised with the file, the endpoint, the package and the error's class
    prefixed, so the command line exits 2 with a message that names where it stands and
    what was raised; an error the build does not raise propagates as it is.
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
        BuildError: A package's import, its ``build()`` or the narrowed copy raised a
            ``ValueError`` or a ``TypeError``, core's refusal of a declaration among them,
            or its option hook refused the defaults; the message names the file, the
            endpoint, the package and the error's class.
    """
    packages = [_load(endpoint, ref) for ref in endpoint.packages]
    listed = bool(endpoint.include or endpoint.exclude)
    tool_sets = [
        _narrowed(endpoint, package) if listed else package.tool_set for package in packages
    ]
    for package, tool_set in zip(packages, tool_sets, strict=True):
        _apply_options(endpoint, package.ref, tool_set)
    if len(tool_sets) == 1:
        name = f"xippios-{endpoint.name}" if listed else None
        return _built(build_server(tool_sets[0], name=name), tool_sets)
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
    except (TypeError, ValueError) as exc:
        # The two classes by which core refuses a declaration while the tool set is built
        # (ToolSet.from_tasks); a package's own error of either class ends so too, its class
        # named, since the two cannot be told apart. No other class is caught.
        raise _refused(endpoint, ref, exc) from exc


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
        raise _refused(endpoint, package.ref, exc) from exc


def _refused(endpoint: Endpoint, ref: PackageRef, exc: Exception) -> BuildError:
    """The ``BuildError`` for ``exc``: the file, the endpoint, the package and its class."""
    return BuildError(
        f"{endpoint.path}: endpoints.{endpoint.name}: {ref}: {type(exc).__name__}: {exc}"
    )


def _apply_options(endpoint: Endpoint, ref: PackageRef, tool_set: ToolSet) -> None:
    """Apply the tool set's option hook as its entry point does when it runs without options.

    ``option_defaults()`` gives the options that the entry point parses from an empty
    command line, core's and the package's each at its default, and ``apply_options``
    takes them alone (sdk-core ADR-0063, decision 4). A hook sets what it sets for the
    whole process, as the entry point's does, a ceiling in force say; a tool set without
    the hook is served as it is.

    Raises:
        BuildError: ``option_defaults()`` met an option without a default, or the hook
            raised a ``XippiosError`` or a ``ValueError``, where the entry point would exit
            with status 2.
    """
    if tool_set.apply_options is None:
        return
    try:
        tool_set.apply_options(tool_set.option_defaults())
    except (XippiosError, ValueError) as exc:
        raise _refused(endpoint, ref, exc) from exc


def _instructions(endpoint: Endpoint, tool_sets: list[ToolSet]) -> str:
    """A group's instructions: the host's sentence, then each package's own under its slug.

    The sentence names what the endpoint serves, its packages with their tool counts. Each
    package's own instructions follow under a heading of its slug, ``## usda-nass``, in the
    config's order; a package without instructions gets no heading.
    """
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
    own = [f"## {ts.source}\n\n{ts.instructions}" for ts in tool_sets if ts.instructions]
    if not own:
        return f"{sentence}."
    return "\n\n".join(
        [f"{sentence}. Each package's own instructions follow under its slug.", *own]
    )
