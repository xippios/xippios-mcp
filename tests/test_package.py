"""The host's own package checks.

Core's family check (``xippios.core.testing.family``) reads a source's ``_client`` and
``tasks``, which the host does not have (ADR-0026, decision 1), so the checks that apply
to the host are written here.
"""

import re
import tomllib
from importlib.metadata import distribution, entry_points, version
from importlib.resources import files
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
    """ADR-0026, decision 9: one extra per package, a ``>=`` floor and no upper bound."""
    extras: dict[str, list[str]] = project["project"]["optional-dependencies"]
    sources = {name: specs for name, specs in extras.items() if name != "all"}
    assert sources
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
    assert "--config" in out


def test_cli_without_config(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exited:
        main([])
    assert exited.value.code == 2
    assert "--config" in capsys.readouterr().err


def test_cli_with_config_serves_nothing_yet(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    with pytest.raises(SystemExit) as exited:
        main(["--config", str(tmp_path / "host.toml")])
    assert exited.value.code == 2
    assert "config loader" in capsys.readouterr().err
