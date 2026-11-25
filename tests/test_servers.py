"""The mount: each endpoint's server, built from its packages' tool sets.

The packages are the invented sources under ``tests/example``: ``example``, with a read and
a write tool set, and the nested ``example-api``, a read tool set alone. Every server is
reached through ``mcp.Client(server)`` in-process, as core's ``mcp_call`` reaches one, so
the middleware runs as it does for a real client. The expected names are read from the
packages' own ``build()`` here, never typed in where the package gives them.
"""

import argparse
import sys
from importlib import import_module
from pathlib import Path
from types import ModuleType

import pytest
import xippios.example.api.mcp
import xippios.example.api.tasks
import xippios.example.mcp
import xippios.example.mcp_write
from mcp import Client
from mcp.types import TextContent, Tool
from xippios.core import ConfigError, InvalidRequestError, ResultCap, tool_name
from xippios.core.mcp import ToolSet
from xippios.core.testing import mcp_call, mcp_call_text
from xippios.example import tasks as example_tasks
from xippios.example import tasks_write as example_tasks_write

import xippios.mcp.packages
from xippios.mcp import __version__
from xippios.mcp.config import PackageRef, load_config
from xippios.mcp.packages import import_path, load_package
from xippios.mcp.servers import BuildError, Built, build_endpoint


def _tools(tool_set: ToolSet) -> list[str]:
    """The tool names of ``tool_set``, as core names them."""
    return [tool_name(tool_set.source, fn) for fn in tool_set.tasks]


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


# What the host reads of a package: its tool set, by its build() (sdk-core ADR-0063,
# decision 4).


def test_a_package_is_read_by_its_build() -> None:
    package = load_package(PackageRef("example"))
    assert isinstance(package.tool_set, ToolSet)
    assert package.tool_set.read_only is True
    assert package.tools == tuple(_tools(xippios.example.mcp.build()))
    assert package.tasks == ("get_series", "list_regions")


def test_a_write_package_is_read_by_the_write_build() -> None:
    package = load_package(PackageRef("example", write=True))
    assert package.tool_set.read_only is False
    assert package.tools == ("example_create_thing", "example_delete_thing")


def test_a_nested_package_by_its_import_path() -> None:
    assert import_path("example-api") == "xippios.example.api"
    package = load_package(PackageRef("example-api"))
    assert package.tool_set.source == "example-api"
    assert package.tools == ("example_api_get_record", "example_api_list_kinds")


@pytest.mark.parametrize("slug", ["example", "example-api"])
def test_a_tool_set_is_built_without_the_packages_variables(
    slug: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The host holds no ``_client.py``, so core's plugin sets no placeholder of a key for
    the packages it loads: building a tool set needs none of the variables that the package
    contract's ``mcp.ENV_VARS`` names, each removed here, never read."""
    adapter = import_module(f"{import_path(slug)}.mcp")
    for variable in adapter.ENV_VARS:
        monkeypatch.delenv(variable.name_or_pattern, raising=False)
    assert load_package(PackageRef(slug)).tools


def test_the_narrowed_tool_set_drops_the_caps_of_the_tasks_it_drops() -> None:
    package = load_package(PackageRef("example"))
    assert dict(package.tool_set.caps) == dict(example_tasks.MCP_CAPS)
    kept = package.narrowed(exclude=frozenset({"list_regions"}))
    assert [fn.__name__ for fn in kept.tasks] == ["get_series"]
    assert dict(kept.caps) == {}
    included = package.narrowed(include=frozenset({"list_regions"}))
    assert [fn.__name__ for fn in included.tasks] == ["list_regions"]
    assert dict(included.caps) == {"list_regions": example_tasks.MCP_CAPS["list_regions"]}
    assert (included.source, included.version, included.instructions) == (
        package.tool_set.source,
        package.tool_set.version,
        package.tool_set.instructions,
    )


# One package without a list: its tool set's server, as its entry point builds it.


@pytest.mark.anyio
async def test_one_package_serves_its_tool_sets_server(tmp_path: Path) -> None:
    built = _build(tmp_path, 'packages = ["example"]')
    own = xippios.example.mcp.server
    assert built.server is not own  # built by the host, never the package's module object
    assert (built.server.name, built.server.version) == (own.name, own.version)
    assert built.server.name == "xippios-example"
    assert built.server.instructions == example_tasks.MCP_INSTRUCTIONS
    assert (built.write, built.held) == (False, False)
    tools = await _listed(built)
    assert list(tools) == _tools(xippios.example.mcp.build())
    async with Client(own) as client:
        theirs = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert {name: tool.input_schema for name, tool in tools.items()} == {
        name: tool.input_schema for name, tool in theirs.items()
    }


def test_each_endpoint_builds_a_server_of_its_own(tmp_path: Path) -> None:
    first = _build(tmp_path, 'packages = ["example"]')
    second = _build(tmp_path, 'packages = ["example"]')
    assert first.server is not second.server


@pytest.mark.anyio
async def test_a_bulk_task_is_no_tool(tmp_path: Path) -> None:
    assert "download_regions" in example_tasks.__all__
    assert "download_regions" in example_tasks.BULK_TASKS
    tools = await _listed(_build(tmp_path, 'packages = ["example"]'))
    assert "example_download_regions" not in tools


@pytest.mark.anyio
async def test_the_write_server_alone(tmp_path: Path) -> None:
    built = _build(tmp_path, 'packages = ["example:write"]', name="accounting-write")
    assert (built.write, built.held) == (True, True)
    assert built.server.name == "xippios-example"
    assert built.server.instructions == example_tasks_write.MCP_INSTRUCTIONS
    tools = await _listed(built)
    assert list(tools) == ["example_create_thing", "example_delete_thing"]
    for tool in tools.values():
        assert tool.annotations is not None
        assert (tool.annotations.read_only_hint, tool.annotations.destructive_hint) == (
            False,
            True,
        )


@pytest.mark.anyio
async def test_a_read_package_that_declares_the_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(example_tasks, "MCP_LOOPBACK_ONLY", True, raising=False)
    built = _build(tmp_path, 'packages = ["example"]')
    assert (built.write, built.held) == (False, True)
    group = _build(tmp_path, 'packages = ["example-api", "example"]')
    assert (group.write, group.held) == (False, True)


# A group, or one package with a list: one server the host builds, a tool set per package.


@pytest.mark.anyio
async def test_a_group_with_an_exclude_list(tmp_path: Path) -> None:
    body = 'packages = ["example", "example-api"]\nexclude = { example = ["get_series"] }'
    built = _build(tmp_path, body)
    assert (built.write, built.held) == (False, False)
    tools = await _listed(built)
    expected = _tools(xippios.example.mcp.build()) + _tools(xippios.example.api.mcp.build())
    assert list(tools) == [name for name in expected if name != "example_get_series"]
    assert "example_api_get_record" in tools  # the list names example's task only
    for tool in tools.values():
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True


@pytest.mark.anyio
async def test_a_host_built_server_names_itself_and_its_packages(tmp_path: Path) -> None:
    built = _build(tmp_path, 'packages = ["example", "example-api"]')
    assert built.server.name == "xippios-agriculture"
    assert built.server.version == __version__
    async with Client(built.server) as client:
        info, instructions = client.server_info, client.instructions
    assert info is not None
    assert info.name == "xippios-agriculture"
    assert instructions is not None
    assert "example (2) and example-api (2)" in instructions
    assert "read-only" in instructions


@pytest.mark.anyio
async def test_an_include_list(tmp_path: Path) -> None:
    built = _build(tmp_path, 'packages = ["example"]\ninclude = { example = ["list_regions"] }')
    assert built.server.name == "xippios-agriculture"
    assert list(await _listed(built)) == ["example_list_regions"]


@pytest.mark.anyio
async def test_a_kept_tool_keeps_its_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The package's own cap of a tool it keeps applies on a server the host builds."""
    body = 'packages = ["example", "example-api"]'
    answer = await mcp_call(_build(tmp_path, body).server, "example_list_regions", {})
    assert [region["code"] for region in answer["data"]] == ["N", "S"]
    monkeypatch.setitem(example_tasks.MCP_CAPS, "list_regions", ResultCap(max_rows=1))
    answer = await mcp_call(_build(tmp_path, body).server, "example_list_regions", {})
    assert [region["code"] for region in answer["data"]] == ["N"]


@pytest.mark.anyio
async def test_the_write_server_with_an_exclude_list(tmp_path: Path) -> None:
    built = _build(
        tmp_path,
        'packages = ["example:write"]\nexclude = { example = ["delete_thing"] }',
        name="accounting-write",
    )
    assert (built.write, built.held) == (True, True)
    assert built.server.name == "xippios-accounting-write"
    assert built.server.instructions is not None
    assert "confirm" in built.server.instructions
    tools = await _listed(built)
    assert list(tools) == ["example_create_thing"]
    for tool in tools.values():
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is False


# What an endpoint carries of its packages: their instructions and version, and their option
# hooks applied at the defaults of their entry points (ADR-0001, decision 7).

LISTED = [
    ('packages = ["example"]\ninclude = { example = ["get_series"] }', xippios.example.mcp),
    (
        'packages = ["example:write"]\nexclude = { example = ["delete_thing"] }',
        xippios.example.mcp_write,
    ),
]


@pytest.mark.anyio
@pytest.mark.parametrize(("body", "adapter"), LISTED)
async def test_one_package_with_a_list_shows_its_instructions_and_version(
    tmp_path: Path, body: str, adapter: ModuleType
) -> None:
    own = adapter.build()
    built = _build(tmp_path, body)
    async with Client(built.server) as client:
        info, instructions = client.server_info, client.instructions
    assert info is not None
    assert (info.name, info.version) == ("xippios-agriculture", own.version)
    assert own.version != __version__  # the package's, not the host's
    assert instructions == own.instructions


@pytest.mark.anyio
async def test_a_groups_instructions_name_each_packages_own_under_its_slug(
    tmp_path: Path,
) -> None:
    read, api = xippios.example.mcp.build(), xippios.example.api.mcp.build()
    built = _build(tmp_path, 'packages = ["example-api", "example"]')
    async with Client(built.server) as client:
        info, instructions = client.server_info, client.instructions
    assert info is not None
    assert info.version == __version__  # a group's server is the host's
    assert instructions == (
        "The xippios-mcp endpoint agriculture serves 4 read-only tools of example-api (2) and "
        "example (2), each named with its package's slug as prefix. Each package's own "
        "instructions follow under its slug.\n\n"
        f"## example-api\n\n{api.instructions}\n\n"
        f"## example\n\n{read.instructions}"
    )


def test_a_package_without_instructions_gets_no_heading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(xippios.example.api.tasks, "MCP_INSTRUCTIONS", None)
    built = _build(tmp_path, 'packages = ["example", "example-api"]')
    assert built.server.instructions is not None
    assert built.server.instructions.endswith(f"## example\n\n{example_tasks.MCP_INSTRUCTIONS}")
    assert "## example-api" not in built.server.instructions
    monkeypatch.setattr(example_tasks, "MCP_INSTRUCTIONS", None)
    alone = _build(tmp_path, 'packages = ["example", "example-api"]').server.instructions
    assert alone == (
        "The xippios-mcp endpoint agriculture serves 4 read-only tools of example (2) and "
        "example-api (2), each named with its package's slug as prefix."
    )


def test_a_list_leaves_a_packages_instructions_whole(tmp_path: Path) -> None:
    """The host changes no text of a package, so a list may drop a tool that the package's
    instructions name: here example_list_regions, which they say to call first."""
    own = example_tasks.MCP_INSTRUCTIONS
    assert "example_list_regions" in own
    alone = _build(tmp_path, 'packages = ["example"]\ninclude = { example = ["get_series"] }')
    assert alone.tools == ("example_get_series",)
    assert alone.server.instructions == own
    group = _build(
        tmp_path, 'packages = ["example", "example-api"]\nexclude = { example = ["list_regions"] }'
    )
    assert "example_list_regions" not in group.tools
    assert group.server.instructions is not None
    assert f"## example\n\n{own}" in group.server.instructions


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body",
    [
        'packages = ["example"]',
        'packages = ["example-api", "example"]',
        'packages = ["example"]\ninclude = { example = ["get_series"] }',
    ],
)
async def test_an_endpoint_applies_the_hooks_at_their_defaults(tmp_path: Path, body: str) -> None:
    """The example's hook sets the ceiling of 5 where its module holds 20, as its entry
    point does without options, so the endpoint refuses the sixth period before the task
    answers."""
    assert example_tasks.SERIES.value == example_tasks.SERIES.most == 20
    assert xippios.example.mcp.build().option_defaults().max_periods == 5
    built = _build(tmp_path, body)
    arguments = {"region_code": "N", "periods": 5}
    answer = await mcp_call(built.server, "example_get_series", arguments)
    assert [point["period"] for point in answer["data"]] == [1, 2, 3, 4, 5]
    async with Client(built.server) as client:
        result = await client.call_tool("example_get_series", {**arguments, "periods": 6})
    assert result.is_error is True
    [content] = result.content
    assert isinstance(content, TextContent)
    assert content.text.startswith(
        "error: InvalidRequestError: 6 periods asked; one call fetches at most 5 periods"
    ), content.text  # the opening alone: the rest of the sentence is core's to word


def test_the_ceiling_holds_for_the_whole_process(tmp_path: Path) -> None:
    """As the entry point's does: the hook sets the module's ceiling, so a Python call in the
    host's process is held to it too, and so is every endpoint that serves the package."""
    assert len(example_tasks.get_series("N", periods=6).data) == 6
    _build(tmp_path, 'packages = ["example-api"]')  # a package without hooks changes nothing
    assert example_tasks.SERIES.value == 20
    _build(tmp_path, 'packages = ["example"]')
    assert example_tasks.SERIES.value == 5
    with pytest.raises(InvalidRequestError, match="6 periods asked"):
        example_tasks.get_series("N", periods=6)


def add_region(parser: argparse.ArgumentParser) -> None:
    """An option hook whose option has no default, which an empty command line leaves unset."""
    parser.add_argument("--region", required=True)


def test_an_option_without_a_default_is_refused_with_the_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(example_tasks, "mcp_add_options", add_region)
    with pytest.raises(BuildError) as refused:
        _build(tmp_path, 'packages = ["example-api", "example"]')
    assert str(refused.value).startswith(
        f"{tmp_path / 'host.toml'}: endpoints.agriculture: example: ValueError: example: "
        "add_options needs a default for each of its options"
    ), str(refused.value)
    assert "--region" in str(refused.value)


@pytest.mark.parametrize(
    "error",
    [
        ConfigError("EXAMPLE_REGION is not set; set it to a region's code"),
        ValueError("EXAMPLE_REGION is not set; set it to a region's code"),
    ],
)
def test_a_hook_that_refuses_its_defaults_is_refused_with_the_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    """Where the entry point would exit with status 2, the host refuses the endpoint, never
    with a traceback that ends the packages it serves beside it."""

    def refuse(namespace: argparse.Namespace) -> None:
        assert namespace.max_periods == 5  # the parsed options alone, at their defaults
        raise error

    monkeypatch.setattr(example_tasks, "mcp_apply_options", refuse)
    with pytest.raises(BuildError) as refused:
        _build(tmp_path, 'packages = ["example"]\ninclude = { example = ["list_regions"] }')
    assert str(refused.value) == (
        f"{tmp_path / 'host.toml'}: endpoints.agriculture: example: {type(error).__name__}: "
        "EXAMPLE_REGION is not set; set it to a region's code"
    )
    assert refused.value.__cause__ is error


# The pass-through (ADR-0026, decision 6): an answer reaches the client as the package's
# tool gives it, a refusal of core's middleware and a task's own error alike.


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body", ['packages = ["example"]', 'packages = ["example", "example-api"]']
)
async def test_an_undeclared_argument_is_refused_before_the_tool_runs(
    tmp_path: Path, body: str
) -> None:
    built = _build(tmp_path, body)
    async with Client(built.server) as client:
        result = await client.call_tool("example_get_series", {"region": "N"})
    assert result.is_error is True
    [content] = result.content
    assert isinstance(content, TextContent)
    text = content.text
    assert text.startswith("error: InvalidRequestError: region: Not an argument of this tool"), text
    assert text.endswith("Nothing was sent.")


@pytest.mark.anyio
async def test_a_tasks_error_is_flagged_as_the_package_gives_it(tmp_path: Path) -> None:
    built = _build(tmp_path, 'packages = ["example", "example-api"]')
    async with Client(built.server) as client:
        result = await client.call_tool("example_get_series", {"region_code": "X"})
    assert result.is_error is True
    [content] = result.content
    assert isinstance(content, TextContent)
    assert content.text.startswith(
        "error: InvalidRequestError: region_code 'X': no region of example"
    )
    assert "the tool example_list_regions" in content.text


@pytest.mark.anyio
async def test_a_preview_without_confirm(tmp_path: Path) -> None:
    built = _build(tmp_path, 'packages = ["example:write"]', name="accounting-write")
    text = await mcp_call_text(built.server, "example_create_thing", {"name": "first"})
    assert '"performed":false' in text.replace(" ", "")


# The refusals that need the package.


def test_a_package_that_is_not_installed(tmp_path: Path) -> None:
    message = _refused(tmp_path, 'packages = ["nothing"]')
    assert "endpoints.agriculture.packages: nothing: not installed" in message
    assert "install xippios-nothing" in message


def test_the_install_hint_names_the_hosts_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulated with a ``None`` entry in ``sys.modules``, as an absent package raises."""
    monkeypatch.setitem(sys.modules, "xippios.example", None)
    monkeypatch.setattr(xippios.mcp.packages, "_extras", lambda: frozenset({"example"}))
    message = _refused(tmp_path, 'packages = ["example"]')
    assert "endpoints.agriculture.packages: example: not installed" in message
    assert "install xippios-mcp[example]" in message


def test_a_package_without_an_mcp_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "xippios.example.mcp", None)
    message = _refused(tmp_path, 'packages = ["example"]')
    expected = "endpoints.agriculture.packages: example: xippios.example has no xippios.example.mcp"
    assert expected in message


def test_write_on_a_package_without_a_write_server(tmp_path: Path) -> None:
    message = _refused(tmp_path, 'packages = ["example-api:write"]')
    assert (
        "endpoints.agriculture.packages: example-api:write: example-api has no write server "
        "(xippios.example.api.mcp_write)"
    ) in message


def test_a_package_without_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(xippios.example.mcp, "build")
    message = _refused(tmp_path, 'packages = ["example"]')
    assert "example: xippios.example.mcp holds no build()" in message


def test_a_build_that_returns_a_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The form before the package contract, a server where the tool set belongs."""
    monkeypatch.setattr(xippios.example.mcp, "build", lambda: xippios.example.mcp.server)
    message = _refused(tmp_path, 'packages = ["example"]')
    assert "example: xippios.example.mcp.build() returns MCPServer, not a ToolSet" in message


def test_a_write_build_that_returns_a_read_tool_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(xippios.example.mcp_write, "build", xippios.example.mcp.build)
    message = _refused(tmp_path, 'packages = ["example:write"]')
    assert "example:write: xippios.example.mcp_write.build() returns a read tool set" in message


def test_a_read_build_that_returns_a_write_tool_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(xippios.example.mcp, "build", xippios.example.mcp_write.build)
    message = _refused(tmp_path, 'packages = ["example"]')
    assert "example: xippios.example.mcp.build() returns a write tool set" in message


def test_a_broken_install_is_no_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A module the package imports, missing, propagates: it is no config problem."""

    def import_module(name: str) -> ModuleType:
        raise ModuleNotFoundError(f"No module named {name!r}", name="a_dependency")

    monkeypatch.setattr(xippios.mcp.packages, "import_module", import_module)
    with pytest.raises(ModuleNotFoundError):
        _build(tmp_path, 'packages = ["example"]')


def test_an_unknown_task(tmp_path: Path) -> None:
    message = _refused(tmp_path, 'packages = ["example"]\nexclude = { example = ["get_serie"] }')
    assert "endpoints.agriculture.exclude.example: get_serie: no task of example" in message
    assert "one of: get_series, list_regions" in message


def test_a_tool_name_is_no_task_name(tmp_path: Path) -> None:
    message = _refused(
        tmp_path, 'packages = ["example"]\ninclude = { example = ["example_get_series"] }'
    )
    assert "endpoints.agriculture.include.example: example_get_series: no task" in message
    assert "without the source prefix" in message


@pytest.mark.parametrize("kind", ["include", "exclude"])
def test_a_bulk_task_named_in_a_list_is_refused(tmp_path: Path, kind: str) -> None:
    message = _refused(
        tmp_path, f'packages = ["example"]\n{kind} = {{ example = ["download_regions"] }}'
    )
    expected = f"endpoints.agriculture.{kind}.example: download_regions: no task of example"
    assert expected in message
    assert "a task of BULK_TASKS is no tool" in message


def test_a_list_that_keeps_no_tool(tmp_path: Path) -> None:
    message = _refused(
        tmp_path, 'packages = ["example"]\nexclude = { example = ["get_series", "list_regions"] }'
    )
    assert "endpoints.agriculture.exclude.example: keeps no tool of example" in message


def create_thing(name: str) -> None:
    """A write task without ``confirm``, which core's tool set refuses when it is built."""


def test_a_refusal_of_the_tool_set_names_the_file_endpoint_and_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(example_tasks_write, "create_thing", create_thing)
    with pytest.raises(BuildError) as refused:
        _build(tmp_path, 'packages = ["example:write"]', name="accounting-write")
    assert isinstance(refused.value, ValueError)
    assert str(refused.value).startswith(
        f"{tmp_path / 'host.toml'}: endpoints.accounting-write: example:write: ValueError: "
        "example_create_thing: no parameter confirm"
    )


@pytest.mark.parametrize(
    ("declaration", "value", "message"),
    [
        pytest.param(
            "MCP_CAPS", ["list_regions"], "xippios.example.tasks.MCP_CAPS is a mapping", id="caps"
        ),
        pytest.param(
            "MCP_INSTRUCTIONS", 3, "xippios.example.tasks.MCP_INSTRUCTIONS is text", id="text"
        ),
        pytest.param(
            "MCP_LOOPBACK_ONLY",
            "yes",
            "xippios.example.tasks.MCP_LOOPBACK_ONLY is True or",
            id="hold",
        ),
    ],
)
def test_a_declaration_of_the_wrong_type_is_a_build_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, declaration: str, value: object, message: str
) -> None:
    """Core refuses it with a ``TypeError`` while the tool set is built (sdk-core ADR-0063,
    decision 7), which the host names with the file, the endpoint and the package."""
    monkeypatch.setattr(example_tasks, declaration, value, raising=False)
    for body in ('packages = ["example"]', 'packages = ["example-api", "example"]'):
        with pytest.raises(BuildError) as refused:
            _build(tmp_path, body)
        assert isinstance(refused.value.__cause__, TypeError)
        assert str(refused.value).startswith(
            f"{tmp_path / 'host.toml'}: endpoints.agriculture: example: TypeError: {message}"
        )


@pytest.mark.parametrize("error", [ValueError, TypeError])
def test_a_packages_own_error_names_its_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: type[Exception]
) -> None:
    """Core raises its refusals as plain ``ValueError`` and ``TypeError``, so the host cannot
    tell them from a package's own: each ends as a refusal that names its class."""

    def build() -> ToolSet:
        raise error("unsupported operand type(s) for +: 'int' and 'str'")

    monkeypatch.setattr(xippios.example.mcp, "build", build)
    with pytest.raises(BuildError) as refused:
        _build(tmp_path, 'packages = ["example"]')
    assert isinstance(refused.value.__cause__, error)
    assert str(refused.value) == (
        f"{tmp_path / 'host.toml'}: endpoints.agriculture: example: {error.__name__}: "
        "unsupported operand type(s) for +: 'int' and 'str'"
    )
