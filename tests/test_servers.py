"""The mount: each endpoint's server, the package's own or one the host builds.

Every server is reached through ``mcp.Client(server)`` in-process, as core's
``mcp_call`` reaches one, so the middleware runs as it does for a real client. No tool
reaches an upstream: the calls below are refused before a tool runs, and core's plugin
refuses the network in every test anyway. The expected counts are computed from the
packages' ``tasks.py`` here, never typed in.
"""

import sys
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from types import ModuleType

import pytest
import xippios.cashctrl.mcp
import xippios.cashctrl.mcp_write
import xippios.usda.nass.mcp
from mcp import Client
from mcp.types import Tool
from xippios.cashctrl import tasks as cashctrl_tasks
from xippios.cashctrl import tasks_write as cashctrl_tasks_write
from xippios.comtrade import tasks as comtrade_tasks
from xippios.core import ConfigError

# Outside core's public surface: queue row 297 decides whether core 0.4.0 exports
# is_write_server from xippios.core.mcp.
from xippios.core.mcp.server import is_write_server
from xippios.core.testing import mcp_call_text
from xippios.usda.nass import tasks as nass_tasks
from xippios.usda.psd import tasks as psd_tasks

import xippios.mcp.packages
from xippios.mcp import __version__
from xippios.mcp.config import load_config
from xippios.mcp.packages import import_path, known_slugs
from xippios.mcp.servers import BuildError, Built, build_all, build_endpoint

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "docs" / "host.example.toml"


def _tools(tasks: ModuleType) -> list[str]:
    """The task names of ``tasks.__all__`` that become tools: ``BULK_TASKS`` left out."""
    bulk: frozenset[str] = getattr(tasks, "BULK_TASKS", frozenset())
    return [name for name in tasks.__all__ if name not in bulk]


def _build(tmp_path: Path, body: str, name: str = "agriculture") -> Built:
    path = tmp_path / "host.toml"
    path.write_text(f'[endpoints.{name}]\nauth = "none"\n{body}\n', encoding="utf-8")
    return build_endpoint(load_config(path).endpoints[name])


def _refused(tmp_path: Path, body: str) -> str:
    with pytest.raises(ConfigError) as refused:
        _build(tmp_path, body)
    message = str(refused.value)
    assert message.startswith(f"{tmp_path / 'host.toml'}: endpoints.agriculture."), message
    return message


async def _listed(built: Built) -> dict[str, Tool]:
    async with Client(built.server) as client:
        listed = await client.list_tools()
    tools = {tool.name: tool for tool in listed.tools}
    assert sorted(tools) == sorted(built.tools)
    return tools


@pytest.mark.anyio
async def test_one_package_serves_its_own_server(tmp_path: Path) -> None:
    built = _build(tmp_path, 'packages = ["usda-nass"]')
    assert built.server is xippios.usda.nass.mcp.server
    assert built.host_built is False
    assert built.write is False
    tools = await _listed(built)
    assert len(tools) == len(_tools(nass_tasks))


@pytest.mark.anyio
async def test_a_group_with_an_exclude_list(tmp_path: Path) -> None:
    body = (
        'packages = ["usda-nass", "usda-psd", "comtrade"]\nexclude = { usda-nass = ["get_counts"] }'
    )
    built = _build(tmp_path, body)
    assert built.host_built is True
    assert built.write is False
    assert is_write_server(built.server) is False
    tools = await _listed(built)
    expected = len(_tools(nass_tasks)) + len(_tools(psd_tasks)) + len(_tools(comtrade_tasks)) - 1
    assert len(tools) == expected
    assert "usda_nass_get_counts" not in tools
    assert "comtrade_get_counts" in tools  # the list names usda-nass's task only
    for prefix, tasks in [("usda_nass_", nass_tasks), ("usda_psd_", psd_tasks)]:
        named = {name for name in tools if name.startswith(prefix)}
        assert named == {f"{prefix}{task}" for task in _tools(tasks)} - {"usda_nass_get_counts"}
    assert all(name.startswith(("usda_nass_", "usda_psd_", "comtrade_")) for name in tools)
    for tool in tools.values():
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True


@pytest.mark.anyio
async def test_a_host_built_server_names_itself_and_its_packages(tmp_path: Path) -> None:
    built = _build(tmp_path, 'packages = ["usda-nass", "usda-psd", "comtrade"]')
    assert built.server.name == "xippios-agriculture"
    assert built.server.version == __version__
    async with Client(built.server) as client:
        info, instructions = client.server_info, client.instructions
    assert info is not None
    assert info.name == "xippios-agriculture"
    assert instructions is not None
    for slug in ("usda-nass", "usda-psd", "comtrade"):
        assert slug in instructions
    assert f"usda-nass ({len(_tools(nass_tasks))})" in instructions
    assert "read-only" in instructions


@pytest.mark.anyio
async def test_an_include_list(tmp_path: Path) -> None:
    built = _build(
        tmp_path,
        'packages = ["usda-nass"]\ninclude = { usda-nass = ["get_data", "list_param_values"] }',
    )
    assert built.host_built is True
    assert built.server is not xippios.usda.nass.mcp.server
    tools = await _listed(built)
    assert set(tools) == {"usda_nass_get_data", "usda_nass_list_param_values"}


@pytest.mark.anyio
async def test_the_write_server_alone_is_the_packages_own(tmp_path: Path) -> None:
    built = _build(tmp_path, 'packages = ["cashctrl:write"]', name="accounting-write")
    assert built.server is xippios.cashctrl.mcp_write.server
    assert built.host_built is False
    assert built.write is True
    assert is_write_server(built.server) is True
    tools = await _listed(built)
    assert len(tools) == len(_tools(cashctrl_tasks_write))


@pytest.mark.anyio
async def test_the_write_server_with_an_exclude_list(tmp_path: Path) -> None:
    built = _build(
        tmp_path,
        'packages = ["cashctrl:write"]\nexclude = { cashctrl = ["delete_person"] }',
        name="accounting-write",
    )
    assert built.host_built is True
    assert built.write is True
    assert is_write_server(built.server) is True
    assert built.server.name == "xippios-accounting-write"
    assert built.server.instructions is not None
    assert "confirm" in built.server.instructions
    tools = await _listed(built)
    assert len(tools) == len(_tools(cashctrl_tasks_write)) - 1
    assert "cashctrl_delete_person" not in tools
    for tool in tools.values():
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is False


@pytest.mark.anyio
async def test_the_caps_are_cut_to_the_kept_tasks(tmp_path: Path) -> None:
    caps = cashctrl_tasks.MCP_CAPS
    assert "list_history" in caps
    # Uncut, register_tasks would refuse the cap of the excluded task with a ValueError.
    built = _build(tmp_path, 'packages = ["cashctrl"]\nexclude = { cashctrl = ["list_history"] }')
    tools = await _listed(built)
    assert "cashctrl_list_history" not in tools
    assert len(tools) == len(_tools(cashctrl_tasks)) - 1
    assert {f"cashctrl_{name}" for name in caps if name != "list_history"} <= set(tools)


def test_the_sample_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XIPPIOS_MCP_AGRICULTURE_TOKEN", raising=False)
    built = build_all(load_config(SAMPLE))
    assert list(built) == ["agriculture", "accounting-write"]
    assert built["agriculture"].host_built is True
    assert built["agriculture"].write is False
    assert built["accounting-write"].server is xippios.cashctrl.mcp_write.server
    assert built["accounting-write"].write is True


# The pass-through (ADR-0026, decision 6): arguments a tool's schema refuses are answered
# by core's middleware before the tool runs, as the family's text (conventions §8), and
# the host leaves the answer as it is.


@pytest.mark.anyio
async def test_a_refusal_on_a_package_built_server(tmp_path: Path) -> None:
    built = _build(tmp_path, 'packages = ["usda-nass"]')
    assert built.host_built is False
    text = await mcp_call_text(built.server, "usda_nass_list_param_values", {})
    assert text.startswith("error: InvalidRequestError: param:"), text


@pytest.mark.anyio
async def test_a_refusal_on_a_host_built_server(tmp_path: Path) -> None:
    built = _build(tmp_path, 'packages = ["usda-nass", "comtrade"]')
    assert built.host_built is True
    text = await mcp_call_text(built.server, "usda_nass_list_param_values", {"param": ["a"]})
    assert text.startswith("error: InvalidRequestError: param:"), text


# The refusals that need the package.


def test_an_unknown_package(tmp_path: Path) -> None:
    message = _refused(tmp_path, 'packages = ["usda-wasde"]')
    assert "endpoints.agriculture.packages: usda-wasde: no package of the host's" in message
    assert ", ".join(known_slugs()) in message


def test_an_unknown_task(tmp_path: Path) -> None:
    message = _refused(
        tmp_path, 'packages = ["usda-nass"]\nexclude = { usda-nass = ["get_count"] }'
    )
    assert "endpoints.agriculture.exclude.usda-nass: get_count: no task of usda-nass" in message
    assert ", ".join(_tools(nass_tasks)) in message


def test_a_tool_name_is_no_task_name(tmp_path: Path) -> None:
    message = _refused(
        tmp_path, 'packages = ["usda-nass"]\ninclude = { usda-nass = ["usda_nass_get_data"] }'
    )
    assert "endpoints.agriculture.include.usda-nass: usda_nass_get_data: no task" in message
    assert "without the source prefix" in message


@pytest.mark.parametrize("kind", ["include", "exclude"])
def test_a_bulk_task_is_no_tool(tmp_path: Path, kind: str) -> None:
    bulk = sorted(cashctrl_tasks.BULK_TASKS)[0]
    message = _refused(tmp_path, f'packages = ["cashctrl"]\n{kind} = {{ cashctrl = ["{bulk}"] }}')
    assert f"endpoints.agriculture.{kind}.cashctrl: {bulk}: in cashctrl's BULK_TASKS" in message
    assert "no tool" in message


def test_a_list_that_keeps_no_tool(tmp_path: Path) -> None:
    every = ", ".join(f'"{name}"' for name in _tools(nass_tasks))
    message = _refused(tmp_path, f'packages = ["usda-nass"]\nexclude = {{ usda-nass = [{every}] }}')
    assert "endpoints.agriculture.exclude.usda-nass: keeps no tool of usda-nass" in message


def test_write_on_a_package_without_a_write_server(tmp_path: Path) -> None:
    message = _refused(tmp_path, 'packages = ["usda-nass:write"]')
    assert "endpoints.agriculture.packages: usda-nass:write: usda-nass has no write server" in (
        message
    )


def test_a_missing_extra(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulated with a ``None`` entry in ``sys.modules``, which makes the import raise
    ``ModuleNotFoundError`` for the package, as an absent package does."""
    monkeypatch.setitem(sys.modules, "xippios.usda.nass", None)
    message = _refused(tmp_path, 'packages = ["usda-nass"]')
    assert "endpoints.agriculture.packages: usda-nass: not installed" in message
    assert "install xippios-mcp[usda-nass]" in message


def test_a_broken_install_is_no_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A module the package imports, missing, propagates: it is no config problem."""

    def import_module(name: str) -> ModuleType:
        raise ModuleNotFoundError(f"No module named {name!r}", name="a_dependency")

    monkeypatch.setattr(xippios.mcp.packages, "import_module", import_module)
    with pytest.raises(ModuleNotFoundError):
        _build(tmp_path, 'packages = ["usda-nass"]')


def test_a_package_server_that_is_not_the_one_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(xippios.cashctrl.mcp_write, "server", xippios.cashctrl.mcp.server)
    message = _refused(tmp_path, 'packages = ["cashctrl:write"]')
    assert "endpoints.agriculture.packages: cashctrl:write: the package's server" in message
    assert "is a read server" in message


def create_person(org: str) -> None:
    """A write task without ``confirm``, which ``register_tasks`` refuses."""


def test_a_refusal_of_register_tasks_names_the_file_endpoint_and_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cashctrl_tasks_write, "create_person", create_person)
    with pytest.raises(BuildError) as refused:
        _build(
            tmp_path,
            'packages = ["cashctrl:write"]\nexclude = { cashctrl = ["delete_person"] }',
            name="accounting-write",
        )
    assert isinstance(refused.value, ValueError)
    assert str(refused.value).startswith(
        f"{tmp_path / 'host.toml'}: endpoints.accounting-write: cashctrl:write: "
        "cashctrl_create_person: no parameter confirm"
    )


@pytest.mark.parametrize("slug", known_slugs())
def test_every_task_name_is_its_functions_name(slug: str) -> None:
    """The lists and MCP_CAPS are keyed by ``__name__``, as core's cap check reads them."""
    path = import_path(slug)
    names = ["tasks", "tasks_write"] if find_spec(f"{path}.tasks_write") else ["tasks"]
    for tasks in [import_module(f"{path}.{name}") for name in names]:
        for name in tasks.__all__:
            assert getattr(tasks, name).__name__ == name, f"{tasks.__name__}.{name}"


def test_a_package_without_a_module_level_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(xippios.usda.nass.mcp, "server")
    message = _refused(tmp_path, 'packages = ["usda-nass"]')
    assert "xippios.usda.nass.mcp holds no module-level server" in message
