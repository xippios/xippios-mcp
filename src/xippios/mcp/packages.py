"""The packages the host serves: the known slugs, their modules, tasks and servers.

A package is one of the host's extras, ``xippios-mcp[usda-nass]``; its slug is the
extra's name and its import path ``xippios.`` plus the slug with each hyphen turned into
a dot (conventions §1): ``usda-nass`` is ``xippios.usda.nass``, ``cashctrl`` is
``xippios.cashctrl``. What the host reads of a package is ADR-0026's decision 8 as
Johannes settled it on 2026-10-29 (G5, question 2; queue row 306): the package's own
server, ``<path>.mcp.server`` (``<path>.mcp_write.server`` for ``<slug>:write``), and,
for a server the host builds itself, ``tasks.__all__`` (``tasks_write.__all__``) and
``MCP_CAPS``.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import import_module
from importlib.metadata import metadata
from types import ModuleType
from typing import Any

from mcp.server.mcpserver import MCPServer
from xippios.core import ConfigError, ResultCap

# Outside core's public surface, as register_tasks and is_write_server are (queue row
# 297): the test register_tasks applies to skip a task in BULK_TASKS (ADR-0019).
from xippios.core._tasks import is_bulk_task

from xippios.mcp.config import WRITE_SUFFIX, PackageRef

__all__ = ["Package", "import_path", "known_slugs", "load_package"]

DISTRIBUTION = "xippios-mcp"
_UNION = "all"
"""The extra that installs every package, no package of its own."""


def known_slugs() -> tuple[str, ...]:
    """The slugs of the packages the host knows: its extras but ``all``, sorted."""
    extras = metadata(DISTRIBUTION).get_all("Provides-Extra") or []
    return tuple(sorted(extra for extra in extras if extra != _UNION))


def import_path(slug: str) -> str:
    """The import path of a package: ``xippios.`` and the slug, each hyphen a dot.

    Args:
        slug: The package's slug, e.g. ``"usda-nass"`` (``xippios.usda.nass``) or
            ``"cashctrl"`` (``xippios.cashctrl``).
    """
    return "xippios." + slug.replace("-", ".")


@dataclass(frozen=True, slots=True)
class Package:
    """A package's server and the tasks it is built from, as the host reads them.

    Attributes:
        ref: The config's entry, the slug and whether it is the write server.
        tasks: ``<path>.tasks``, or ``<path>.tasks_write`` for the write server.
        server: The package's own server, ``<path>.mcp.server`` or
            ``<path>.mcp_write.server``, as the package built it.
        functions: Per name of ``tasks.__all__``, the task function.
        tools: The names of ``tasks.__all__`` that become tools, in its order: those in
            ``BULK_TASKS`` left out (ADR-0019).
        caps: ``tasks.MCP_CAPS``, the tools' own result caps by task name, or ``None``.
    """

    ref: PackageRef
    tasks: ModuleType
    server: MCPServer
    functions: Mapping[str, Callable[..., Any]]
    tools: tuple[str, ...]
    caps: Mapping[str, ResultCap] | None

    def kept(
        self, *, include: frozenset[str] | None = None, exclude: frozenset[str] | None = None
    ) -> tuple[str, ...]:
        """The task names that become tools under an include or an exclude list.

        Args:
            include: The only tasks to keep, e.g. ``frozenset({"get_data"})``.
            exclude: The tasks to leave out, e.g. ``frozenset({"get_counts"})``.

        Raises:
            ConfigError: A name is in ``BULK_TASKS``, so no tool, or names no task of the
                package; or the lists keep no tool. The refusal of a name that is no task
                names the package's tools.
        """
        named = include if include is not None else exclude or frozenset()
        bulk = sorted(name for name in named if name in self.functions and name not in self.tools)
        if bulk:
            raise ConfigError(
                f"{', '.join(bulk)}: in {self.ref.slug}'s BULK_TASKS, Python-only and no tool "
                "(ADR-0019)"
            )
        unknown = sorted(named - set(self.tools))
        if unknown:
            raise ConfigError(
                f"{', '.join(unknown)}: no task of {self.ref}; a name is the task "
                f"function's __name__, without the source prefix, one of: "
                f"{', '.join(self.tools)}"
            )
        if include is not None:
            kept = tuple(name for name in self.tools if name in include)
        else:
            kept = tuple(name for name in self.tools if name not in named)
        if not kept:
            raise ConfigError(f"keeps no tool of {self.ref}; leave the package out instead")
        return kept


def load_package(ref: PackageRef) -> Package:
    """Import the package ``ref`` names and read its server and tasks.

    Args:
        ref: The config's entry, e.g. ``PackageRef("usda-nass")`` or
            ``PackageRef("cashctrl", write=True)``.

    Raises:
        ConfigError: The slug is no extra of the host's, the package is not installed,
            ``:write`` names a package without a write server, or the package's module
            holds no ``server``.
    """
    known = known_slugs()
    if ref.slug not in known:
        raise ConfigError(
            f"{ref.slug}: no package of the host's; the known ones: {', '.join(known)}"
        )
    path = import_path(ref.slug)
    try:
        import_module(path)
    except ModuleNotFoundError as exc:
        if exc.name is None or not (path == exc.name or path.startswith(f"{exc.name}.")):
            raise  # a module the package imports is missing: a broken install, no config
        raise ConfigError(f"{ref.slug}: not installed; install xippios-mcp[{ref.slug}]") from exc
    tasks_module, mcp_module = ("tasks_write", "mcp_write") if ref.write else ("tasks", "mcp")
    try:
        tasks = import_module(f"{path}.{tasks_module}")
        adapter = import_module(f"{path}.{mcp_module}")
    except ModuleNotFoundError as exc:
        if ref.write and exc.name in {f"{path}.{tasks_module}", f"{path}.{mcp_module}"}:
            raise ConfigError(
                f"{ref}: {ref.slug} has no write server ({path}.{mcp_module}); name it "
                f"without {WRITE_SUFFIX}"
            ) from exc
        raise
    server = getattr(adapter, "server", None)
    if not isinstance(server, MCPServer):
        raise ConfigError(
            f"{ref}: {adapter.__name__} holds no module-level server, which the host reads "
            "(ADR-0026, decision 8)"
        )
    functions = {name: getattr(tasks, name) for name in tasks.__all__}
    return Package(
        ref=ref,
        tasks=tasks,
        server=server,
        functions=functions,
        tools=tuple(name for name, fn in functions.items() if not is_bulk_task(fn)),
        caps=getattr(tasks, "MCP_CAPS", None),
    )
