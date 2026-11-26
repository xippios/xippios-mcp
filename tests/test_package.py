"""The host's own package checks.

Core's family check (``xippios.core.testing.family``) reads a source's ``_client`` and
``tasks``, which the host does not have (ADR-0026, decision 1), so the checks that apply
to the host are written here, the one on its imports of core among them.
"""

import ast
import re
import tomllib
from collections.abc import Iterator
from functools import cache
from importlib.metadata import distribution, entry_points, version
from importlib.resources import files
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

import xippios.mcp
from xippios.mcp.cli import main

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION = "xippios-mcp"


@pytest.fixture(scope="module")
def project() -> dict[str, Any]:
    with (ROOT / "pyproject.toml").open("rb") as file:
        data: dict[str, Any] = tomllib.load(file)
    return data


def _one_minor(requirement: Requirement) -> bool:
    """``~=X.Y.Z`` (or ``~=X.Y.0``), alone: one minor, the bound of conventions §12."""
    specs = list(requirement.specifier)
    return (
        len(specs) == 1
        and specs[0].operator == "~="
        and re.fullmatch(r"\d+\.\d+\.\d+", specs[0].version) is not None
    )


def _lower_bound_only(requirement: Requirement) -> bool:
    specs = list(requirement.specifier)
    return len(specs) == 1 and specs[0].operator == ">="


def test_no_namespace_init() -> None:
    """``src/xippios/`` is a PEP 420 namespace package (conventions §1)."""
    assert not (ROOT / "src" / "xippios" / "__init__.py").exists()
    assert (ROOT / "src" / "xippios" / "mcp" / "__init__.py").is_file()


def test_py_typed_ships() -> None:
    assert files("xippios.mcp").joinpath("py.typed").is_file()


def test_version_is_the_distributions() -> None:
    assert isinstance(Version(xippios.mcp.__version__), Version)
    assert xippios.mcp.__version__ == version(DISTRIBUTION)


def test_core_bound_to_one_minor(project: dict[str, Any]) -> None:
    runtime = [Requirement(r) for r in project["project"]["dependencies"]]
    core = [r for r in runtime if r.name == "xippios-core"]
    assert len(core) == 1
    assert core[0].extras == {"mcp"}
    assert _one_minor(core[0])

    dev = [Requirement(r) for r in project["dependency-groups"]["dev"]]
    testing = [r for r in dev if r.name == "xippios-core"]
    assert len(testing) == 1
    assert testing[0].extras == {"testing"}
    assert testing[0].specifier == core[0].specifier


def test_other_runtime_dependencies_take_lower_bounds(project: dict[str, Any]) -> None:
    """Conventions §11: lower bounds only, but for core."""
    runtime = [Requirement(r) for r in project["project"]["dependencies"]]
    others = [r for r in runtime if r.name != "xippios-core"]
    assert others
    for requirement in others:
        assert _lower_bound_only(requirement), str(requirement)


def test_each_extra_is_one_source_package_with_a_lower_bound(project: dict[str, Any]) -> None:
    """ADR-0026, decision 9: one extra per package, a ``>=`` floor and no upper bound.

    A source joins as an extra once it has released on the host's core minor; ``all`` is
    the extra the image installs.
    """
    extras: dict[str, list[str]] = project["project"]["optional-dependencies"]
    assert "all" in extras
    sources = {name: specs for name, specs in extras.items() if name != "all"}
    for name, specs in sources.items():
        assert len(specs) == 1, name
        requirement = Requirement(specs[0])
        assert requirement.name == f"xippios-{name}"
        assert not requirement.extras
        assert requirement.marker is None
        assert _lower_bound_only(requirement), str(requirement)


def test_all_is_the_union_of_the_extras(project: dict[str, Any]) -> None:
    extras: dict[str, list[str]] = project["project"]["optional-dependencies"]
    union = {str(Requirement(s)) for name, specs in extras.items() if name != "all" for s in specs}
    every = [str(Requirement(s)) for s in extras["all"]]
    assert len(every) == len(set(every))
    assert set(every) == union


# The extras of 0.2.0: the three sources that proved core 0.5.0 with the host, by the
# maintainer's decision of 2026-11-24. A later release lists all twelve.

FLOORS = {"faostat": "0.3.0", "cashctrl": "0.6.0", "usda-esr": "0.4.0"}
"""Each proving source's first release on core 0.5, as PyPI holds it: its extra's floor."""
SHARED = "xippios-usda-fas"
"""The shared package that sdk-usda-esr depends on, which the host neither names nor loads."""
PYPI = {"registry": "https://pypi.org/simple"}


def test_the_extras_are_the_proving_sources_at_their_floors(project: dict[str, Any]) -> None:
    extras: dict[str, list[str]] = project["project"]["optional-dependencies"]
    sources = {name: specs for name, specs in extras.items() if name != "all"}
    assert sources == {name: [f"xippios-{name}>={floor}"] for name, floor in FLOORS.items()}


def _locked() -> dict[str, list[dict[str, Any]]]:
    """The entries of ``uv.lock`` by package name, one each unless a marker splits one."""
    with (ROOT / "uv.lock").open("rb") as file:
        lock: dict[str, Any] = tomllib.load(file)
    locked: dict[str, list[dict[str, Any]]] = {}
    for entry in lock["package"]:
        locked.setdefault(entry["name"], []).append(entry)
    return locked


def test_the_lock_resolves_the_proving_sources_from_pypi_on_one_core_minor(
    project: dict[str, Any],
) -> None:
    """Every package comes from PyPI at one version, the sources above their floors.

    No ``[tool.uv.sources]`` pins a commit or a path, and the lock holds no ``git``, ``path``
    or ``url`` source: ``publish.yml`` refuses a core pinned to git, and an image builds from
    the lock alone.
    """
    locked = _locked()
    for slug, floor in FLOORS.items():
        entries = locked.get(f"xippios-{slug}", [])
        assert len(entries) == 1, f"xippios-{slug}: {len(entries)} entries in uv.lock"
        [source] = entries
        assert source["source"] == PYPI, slug
        assert Version(source["version"]) >= Version(floor), slug
    [core] = locked["xippios-core"]
    [bound] = [
        Requirement(spec)
        for spec in project["project"]["dependencies"]
        if Requirement(spec).name == "xippios-core"
    ]
    assert core["source"] == PYPI
    assert bound.specifier.contains(core["version"])
    assert "sources" not in project.get("tool", {}).get("uv", {})
    [own] = locked.pop(DISTRIBUTION)
    assert own["source"] == {"editable": "."}
    elsewhere = {name for name, entries in locked.items() for e in entries if e["source"] != PYPI}
    assert elsewhere == set()


def test_the_shared_package_comes_with_usda_esr_alone() -> None:
    locked = _locked()
    [shared] = locked[SHARED]
    assert shared["source"] == PYPI
    dependents = {
        name
        for name, entries in locked.items()
        for entry in entries
        for dependency in entry.get("dependencies", [])
        if dependency["name"] == SHARED
    }
    assert dependents == {"xippios-usda-esr"}


def test_entry_point(project: dict[str, Any]) -> None:
    assert project["project"]["scripts"] == {"xippios-mcp": "xippios.mcp.cli:main"}
    installed = entry_points(group="console_scripts", name="xippios-mcp")
    assert [ep.value for ep in installed] == ["xippios.mcp.cli:main"]
    assert installed["xippios-mcp"].dist is not None
    assert installed["xippios-mcp"].dist.name == distribution(DISTRIBUTION).name


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        main(["--help"])
    assert exited.value.code == 0
    out = capsys.readouterr().out
    assert out.startswith("usage: xippios-mcp")
    for option in ("--config", "--stdio ENDPOINT", "--http", "--host", "--port"):
        assert option in out


def test_cli_without_config(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        main([])
    assert exited.value.code == 2
    assert "--config" in capsys.readouterr().err


def test_cli_with_a_missing_config(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    path = tmp_path / "host.toml"
    with pytest.raises(SystemExit) as exited:
        main(["--config", str(path)])
    assert exited.value.code == 2
    assert f"{path}: no such file" in capsys.readouterr().err


# The host is a render of sdk-template's general shape, so a template release reaches it by
# `copier update` (sdk-template ADR-0003, decision 9).

TEMPLATE = "https://github.com/xippios/sdk-template.git"


def _answers() -> dict[str, str]:
    """The answers of ``.copier-answers.yml``, which copier writes one plain line each."""
    answers: dict[str, str] = {}
    for line in (ROOT / ".copier-answers.yml").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition(": ")
            answers[key] = value
    return answers


def test_the_host_records_the_templates_general_shape() -> None:
    answers = _answers()
    assert answers["_src_path"] == TEMPLATE
    assert answers["shape"] == "general"
    assert answers["repository_name"] == DISTRIBUTION
    assert answers["source_slug"] == answers["import_path"] == "mcp"


# The host imports nothing private of core and no module of core outside its pinned lists,
# the __all__ of core's six __init__.py files (sdk-core ADR-0063, decision 4; ADR-0059).

CORE = "xippios.core"
LISTS = (
    "xippios.core",
    "xippios.core.client",
    "xippios.core.mcp",
    "xippios.core.http",
    "xippios.core.testing",
    "xippios.core.refresh",
)
OWN_CODE = ("src", "tests", "scripts")


@cache
def _pinned() -> dict[str, frozenset[str]]:
    """Each pinned list of the installed core, read by ``ast`` and never imported.

    ``xippios.core.http`` needs core's ``http`` extra, which the host does not install, so
    no list is imported.
    """
    spec = find_spec(CORE)
    assert spec is not None
    assert spec.origin is not None
    root = Path(spec.origin).parent
    pinned: dict[str, frozenset[str]] = {}
    for module in LISTS:
        init = root.joinpath(*module.split(".")[2:], "__init__.py")
        tree = ast.parse(init.read_text(encoding="utf-8"))
        [names] = [
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
            )
        ]
        pinned[module] = frozenset(names)
    return pinned


def _dotted(node: ast.expr) -> str | None:
    """``a.b.c`` for an attribute chain on a name, else ``None``."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return None if base is None else f"{base}.{node.attr}"
    return None


def _outside(dotted: str) -> bool:
    """Whether the dotted path of core, a module or a module's name, leaves the lists.

    Within the lists: a pinned module, or a name of a pinned module's ``__all__``.
    """
    pinned = _pinned()
    if dotted in pinned:
        return False
    module, _, name = dotted.rpartition(".")
    return module not in pinned or name not in pinned[module]


def _in_core(dotted: str) -> bool:
    return dotted == CORE or dotted.startswith(f"{CORE}.")


def _violations(source: str) -> list[str]:
    """Each import of core in ``source`` outside the pinned lists, ``<line>: <dotted>``.

    An attribute chain is found once, though each of its inner attributes names it again.
    """
    return list(dict.fromkeys(_found(source)))


def _bound(tree: ast.Module) -> dict[str, str]:
    """Each name that an import of ``tree`` binds to a path of core, by the path.

    ``import xippios.core.mcp as m`` binds ``m``, ``from xippios.core import mcp`` binds
    ``mcp`` and ``from xippios import core`` binds ``core``, each to the dotted path it
    names; ``import xippios.core.mcp`` binds ``xippios``, which a chain spells whole.
    """
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname and _in_core(alias.name):
                    bound[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                dotted = f"{node.module}.{alias.name}"
                if _in_core(dotted):
                    bound[alias.asname or alias.name] = dotted
    return bound


def _resolved(dotted: str, bound: dict[str, str]) -> str:
    """``dotted`` with its first name replaced by the path of core that an import bound."""
    head, _, rest = dotted.partition(".")
    if head not in bound:
        return dotted
    return f"{bound[head]}.{rest}" if rest else bound[head]


def _found(source: str) -> Iterator[str]:
    tree = ast.parse(source)
    bound = _bound(tree)
    for node in ast.walk(tree):
        found: list[str] = []
        if isinstance(node, ast.Import):
            found = [alias.name for alias in node.names if _in_core(alias.name)]
        elif isinstance(node, ast.ImportFrom) and node.module and _in_core(node.module):
            found = [f"{node.module}.{alias.name}" for alias in node.names]
        elif isinstance(node, ast.Attribute):
            chain = _dotted(node)
            dotted = None if chain is None else _resolved(chain, bound)
            if dotted is not None and dotted.startswith(f"{CORE}."):
                # The longest pinned module the chain starts with, and the part after it.
                parts = dotted.split(".")
                depth = max(n for n in range(2, len(parts) + 1) if ".".join(parts[:n]) in LISTS)
                found = [".".join(parts[: depth + 1])]
        yield from (
            f"{getattr(node, 'lineno', 0)}: {dotted}" for dotted in found if _outside(dotted)
        )


def _own_files() -> list[Path]:
    return sorted(path for folder in OWN_CODE for path in (ROOT / folder).rglob("*.py"))


def test_the_lists_are_read_from_core() -> None:
    pinned = _pinned()
    assert set(pinned) == set(LISTS)
    assert {"ToolSet", "build_server", "register_tasks", "LOOPBACK_HOSTS"} <= pinned[
        "xippios.core.mcp"
    ]
    assert "ConfigError" in pinned[CORE]


@pytest.mark.parametrize(
    ("source", "found"),
    [
        pytest.param("from xippios.core.mcp import ToolSet, build_server\n", [], id="pinned"),
        pytest.param("from xippios.core import ConfigError, tool_name\n", [], id="root"),
        pytest.param("import xippios.core.mcp\nxippios.core.mcp.ToolSet\n", [], id="attribute"),
        pytest.param("from xippios.core import mcp\n", [], id="a pinned module by name"),
        pytest.param(
            "from xippios.core.mcp.server import register_tasks\n",
            ["1: xippios.core.mcp.server.register_tasks"],
            id="an unpinned module",
        ),
        pytest.param(
            "from xippios.core._tasks import is_bulk_task\n",
            ["1: xippios.core._tasks.is_bulk_task"],
            id="a private module",
        ),
        pytest.param(
            "from xippios.core.mcp import cli\n",
            ["1: xippios.core.mcp.cli"],
            id="a module by a pinned path",
        ),
        pytest.param(
            "\nfrom xippios.core.mcp.cli import LOOPBACK_HOSTS\n",
            ["2: xippios.core.mcp.cli.LOOPBACK_HOSTS"],
            id="a pinned name by its module",
        ),
        pytest.param(
            "import xippios.core.mcp.server\n",
            ["1: xippios.core.mcp.server"],
            id="import of an unpinned module",
        ),
        pytest.param(
            "import xippios.core.mcp\nxippios.core.mcp.server.register_tasks\n",
            ["2: xippios.core.mcp.server"],
            id="an attribute chain",
        ),
        pytest.param(
            "from xippios.core.mcp import _held\n",
            ["1: xippios.core.mcp._held"],
            id="a private name",
        ),
        pytest.param(
            "from xippios.core import mcp\nmcp.server.register_tasks\n",
            ["2: xippios.core.mcp.server"],
            id="a chain on a pinned module imported by name",
        ),
        pytest.param(
            "import xippios.core.mcp as m\nm.cli.LOOPBACK_HOSTS\n",
            ["2: xippios.core.mcp.cli"],
            id="a chain on a module's alias",
        ),
        pytest.param(
            "from xippios import core\ncore._tasks.is_bulk_task\n",
            ["2: xippios.core._tasks"],
            id="a chain on core imported from the namespace",
        ),
        pytest.param(
            "import xippios.core as c\nc.mcp.server\n",
            ["2: xippios.core.mcp.server"],
            id="a chain on core's alias",
        ),
        pytest.param(
            "from xippios.core import mcp\nmcp.ToolSet\n",
            [],
            id="a pinned name on a pinned module imported by name",
        ),
        pytest.param(
            "import xippios.core.mcp as m\nm.ToolSet.from_tasks\n",
            [],
            id="a pinned name on a module's alias",
        ),
        pytest.param(
            "from xippios.core.mcp import ToolSet\nToolSet.from_tasks\n",
            [],
            id="an attribute of a pinned name",
        ),
    ],
)
def test_an_import_outside_the_lists_is_found(source: str, found: list[str]) -> None:
    assert _violations(source) == found


def test_the_host_imports_core_by_its_pinned_lists_alone() -> None:
    """Every file of the package, its tests and its scripts (sdk-core ADR-0063, decision 4)."""
    files = _own_files()
    assert ROOT / "src" / "xippios" / "mcp" / "servers.py" in files
    outside = {
        str(path.relative_to(ROOT)): found
        for path in files
        if (found := _violations(path.read_text(encoding="utf-8")))
    }
    assert outside == {}
