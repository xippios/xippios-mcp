"""The packages the host serves: each read by its tool set, which its ``build()`` returns.

A package is named by its slug, the source's slug, and imported at ``xippios.`` plus the
slug with each hyphen turned into a dot (conventions §1): ``usda-nass`` is
``xippios.usda.nass``, ``cashctrl`` is ``xippios.cashctrl``. A package that is installed is
served; the host's extras say what ``all`` installs and what the hint for a missing
package names. What the host reads of a package is the package contract (sdk-core
ADR-0063, decisions 2 and 4; ADR-0001 of this package): ``<path>.mcp.build()``, or
``<path>.mcp_write.build()`` for ``<slug>:write``, which returns the package's
``ToolSet``. The tool set holds the package's tools alone, its bulk tasks left out, with
their caps, its instructions and version, and whether it writes or is held to loopback.
"""

import dataclasses
from dataclasses import dataclass
from functools import cache
from importlib import import_module
from importlib.metadata import metadata

from xippios.core import ConfigError, tool_name
from xippios.core.mcp import ToolSet

from xippios.mcp.config import WRITE_SUFFIX, PackageRef

__all__ = ["Package", "import_path", "load_package"]

DISTRIBUTION = "xippios-mcp"
_UNION = "all"
"""The extra that installs every package, no package of its own."""


@cache
def _extras() -> frozenset[str]:
    """The host's extras but ``all``: the packages ``xippios-mcp[<slug>]`` installs."""
    extras = metadata(DISTRIBUTION).get_all("Provides-Extra") or []
    return frozenset(extra for extra in extras if extra != _UNION)


def _install_hint(slug: str) -> str:
    """What installs the package: the host's extra where it has one, else its distribution."""
    return f"{DISTRIBUTION}[{slug}]" if slug in _extras() else f"xippios-{slug}"


def import_path(slug: str) -> str:
    """The import path of a package: ``xippios.`` and the slug, each hyphen a dot.

    Args:
        slug: The package's slug, e.g. ``"usda-nass"`` (``xippios.usda.nass``) or
            ``"cashctrl"`` (``xippios.cashctrl``).
    """
    return "xippios." + slug.replace("-", ".")


@dataclass(frozen=True, slots=True)
class Package:
    """A package as the host reads it: the config's entry and the package's tool set.

    Attributes:
        ref: The config's entry, the slug and whether it is the write server.
        tool_set: What ``<path>.mcp.build()`` (``mcp_write.build()``) returned.
    """

    ref: PackageRef
    tool_set: ToolSet

    @property
    def tasks(self) -> tuple[str, ...]:
        """The task names of its tools, in the tool set's order, e.g. ``("get_data",)``."""
        return tuple(fn.__name__ for fn in self.tool_set.tasks)

    @property
    def tools(self) -> tuple[str, ...]:
        """Its tool names, ``tool_name(tool_set.source, fn)``, e.g. ``("usda_nass_get_data",)``."""
        return tuple(tool_name(self.tool_set.source, fn) for fn in self.tool_set.tasks)

    def narrowed(
        self, *, include: frozenset[str] | None = None, exclude: frozenset[str] | None = None
    ) -> ToolSet:
        """The tool set under an include or an exclude list, its caps cut to the kept tasks.

        A copy by ``dataclasses.replace``, which core checks as a new tool set, so a cap
        whose task the list drops is dropped with it (sdk-core ADR-0063, decision 4).

        Args:
            include: The only tasks to keep, e.g. ``frozenset({"get_data"})``.
            exclude: The tasks to leave out, e.g. ``frozenset({"get_counts"})``.

        Raises:
            ConfigError: A name is no task of the tool set, which names a task of
                ``BULK_TASKS`` too, since it is no tool; or the list keeps no tool. The
                refusal of a name names the package's tasks.
        """
        named = include if include is not None else exclude or frozenset()
        unknown = sorted(named - set(self.tasks))
        if unknown:
            raise ConfigError(
                f"{', '.join(unknown)}: no task of {self.ref}; a name is the task "
                "function's __name__, without the source prefix, and a task of BULK_TASKS "
                f"is no tool; one of: {', '.join(self.tasks)}"
            )
        if include is not None:
            kept = [fn for fn in self.tool_set.tasks if fn.__name__ in include]
        else:
            kept = [fn for fn in self.tool_set.tasks if fn.__name__ not in named]
        if not kept:
            raise ConfigError(f"keeps no tool of {self.ref}; leave the package out instead")
        names = {fn.__name__ for fn in kept}
        caps = {name: cap for name, cap in self.tool_set.caps.items() if name in names}
        return dataclasses.replace(self.tool_set, tasks=kept, caps=caps)


def load_package(ref: PackageRef) -> Package:
    """Import the package ``ref`` names and read its tool set by its ``build()``.

    Args:
        ref: The config's entry, e.g. ``PackageRef("usda-nass")`` or
            ``PackageRef("cashctrl", write=True)``.

    Raises:
        ConfigError: The package is not installed; it has no ``mcp`` module, or no
            ``mcp_write`` for ``:write``; the module holds no ``build``; or ``build()``
            returns no ``ToolSet``, or a read tool set for ``:write`` or a write one
            without it.
        ValueError: ``build()`` raised it: core refuses a declaration of the package's
            when its tool set is built, a write task without ``confirm`` say.
        TypeError: ``build()`` raised it: core refuses a declaration of another type,
            ``MCP_CAPS`` no mapping say.
    """
    path = import_path(ref.slug)
    try:
        import_module(path)
    except ModuleNotFoundError as exc:
        if exc.name is None or not (path == exc.name or path.startswith(f"{exc.name}.")):
            raise  # a module the package imports is missing: a broken install, no config
        raise ConfigError(f"{ref.slug}: not installed; install {_install_hint(ref.slug)}") from exc
    name = f"{path}.{'mcp_write' if ref.write else 'mcp'}"
    try:
        adapter = import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        if ref.write:
            raise ConfigError(
                f"{ref}: {ref.slug} has no write server ({name}); name it without {WRITE_SUFFIX}"
            ) from exc
        raise ConfigError(
            f"{ref}: {path} has no {name}, the module of a source's MCP server"
        ) from exc
    build = getattr(adapter, "build", None)
    if not callable(build):
        raise ConfigError(
            f"{ref}: {name} holds no build(), which returns the package's tool set "
            "(sdk-core ADR-0063, decision 2)"
        )
    tool_set = build()
    if not isinstance(tool_set, ToolSet):
        raise ConfigError(f"{ref}: {name}.build() returns {type(tool_set).__name__}, not a ToolSet")
    if tool_set.read_only == ref.write:
        kind = "a read tool set" if tool_set.read_only else "a write tool set"
        raise ConfigError(f"{ref}: {name}.build() returns {kind}")
    return Package(ref=ref, tool_set=tool_set)
