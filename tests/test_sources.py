"""The proving sources, each served where it is installed beside the host.

sdk-faostat, sdk-cashctrl and sdk-usda-esr are the three sources that prove xippios-core 0.5.0
with the host before its release (https://github.com/xippios/sdk-core/issues/485), and the
host's extras. The run installs them, ``uv sync --all-extras`` as CI runs it, and the first
test fails where one is missing, so CI never skips the rest. Every other test runs where the
sources it names are installed and skips where one is not, so a run on the invented sources of
``tests/example`` alone fails that one test and skips the rest. A source loads by its ``build()``,
and every endpoint the host builds of it lists its tools under the names and with the input
schemas of the source's own ``server``, both reached through ``mcp.Client`` in-process, as a
client reaches them. Each call is one that the source answers or refuses before any request:
it runs inside a recorder that counts the requests reaching httpcore's connection pools and the
audit events of CPython's ``socket`` module, and the test asserts that it counted none.
``CONFIG`` is the config of the report of 2026-11-25 under ``docs/reports/``, which records a
run of this module.
"""

import json
import os
import re
import socket
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import cache
from importlib import import_module
from importlib.metadata import metadata
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from mcp import Client
from mcp.server.mcpserver import MCPServer
from xippios.core import ConfigError, tool_name
from xippios.core.mcp import ToolSet
from xippios.core.testing import mcp_call_text

from xippios.mcp.cli import main
from xippios.mcp.config import PackageRef, load_config
from xippios.mcp.packages import import_path, load_package
from xippios.mcp.servers import Built, build_endpoint

SOURCES = ("faostat", "cashctrl", "usda-esr")
"""The proving sources' slugs; a later release of the host serves all twelve sources."""
SAMPLE = Path(__file__).resolve().parents[1] / "docs" / "host.example.toml"
"""The README's sample config."""

CONFIG = """\
[endpoints.faostat]
packages = ["faostat"]
auth = "none"

[endpoints.cashctrl]
packages = ["cashctrl"]
auth = "none"

[endpoints.usda-esr]
packages = ["usda-esr"]
auth = "none"

[endpoints.agriculture]
packages = ["faostat", "usda-esr"]
auth = "none"

[endpoints.cashctrl-write]
packages = ["cashctrl:write"]
auth = "none"
"""
"""One endpoint for each source, a group of two read tool sets and sdk-cashctrl's write one."""

_SOCKET_EVENTS = frozenset(
    {
        "socket.connect",
        "socket.getaddrinfo",
        "socket.gethostbyname",
        "socket.sendmsg",
        "socket.sendto",
    }
)
"""The audit events of a connection opened, a name resolved or a datagram sent."""
_RECORDING: list[list[str]] = []
"""The socket events of the recorder that runs, if one does."""


def _installed(slug: str) -> bool:
    try:
        return find_spec(import_path(slug)) is not None
    except ModuleNotFoundError:  # a parent of a nested path, xippios.usda say, is missing
        return False


def _needs(*slugs: str) -> pytest.MarkDecorator:
    """Skip the test unless every source of ``slugs`` is installed beside the host."""
    missing = [slug for slug in slugs if not _installed(slug)]
    return pytest.mark.skipif(bool(missing), reason=f"not installed: {', '.join(missing)}")


TOOL_SETS = (
    PackageRef("faostat"),
    PackageRef("cashctrl"),
    PackageRef("cashctrl", write=True),
    PackageRef("usda-esr"),
)
"""Each tool set of the proving sources: the three read ones and sdk-cashctrl's write one."""
REFS = [pytest.param(ref, id=str(ref), marks=_needs(ref.slug)) for ref in TOOL_SETS]


def _endpoint(ref: PackageRef) -> str:
    """The endpoint of ``CONFIG`` that serves ``ref`` alone."""
    return f"{ref.slug}-write" if ref.write else ref.slug


def _adapter(ref: PackageRef) -> Any:
    """The source's own ``mcp`` module, or ``mcp_write`` for ``<slug>:write``."""
    return import_module(f"{import_path(ref.slug)}.{'mcp_write' if ref.write else 'mcp'}")


def _own(ref: PackageRef) -> MCPServer:
    """The source's own ``server``, the one its entry point serves."""
    server: MCPServer = _adapter(ref).server
    return server


async def _schemas(server: MCPServer) -> dict[str, dict[str, Any]]:
    """The tools that ``server`` lists, by name in its order, each with its input schema."""
    async with Client(server) as client:
        listed = await client.list_tools()
    return {tool.name: tool.input_schema for tool in listed.tools}


def _config(tmp_path: Path) -> Path:
    path = tmp_path / "host.toml"
    path.write_text(CONFIG, encoding="utf-8")
    return path


def _build(tmp_path: Path, name: str) -> Built:
    return build_endpoint(load_config(_config(tmp_path)).endpoints[name])


def _without_variables(slug: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every variable that the source's ``ENV_VARS`` names, a pattern's by its form.

    Only the names are read: a key is removed where one is set, and never read.
    """
    for entry in _adapter(PackageRef(slug)).ENV_VARS:
        form = re.sub(r"<[A-Z]+>", "[A-Z0-9_]+", re.escape(entry.name_or_pattern))
        for name in [name for name in os.environ if re.fullmatch(form, name)]:
            monkeypatch.delenv(name)


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if _RECORDING and event in _SOCKET_EVENTS:
        _RECORDING[-1].append(event)


@cache
def _hooked() -> None:
    """Add the audit hook, once: Python offers no way to remove one."""
    sys.addaudithook(_audit)


@dataclass
class Sent:
    """What a recorded block handed over, by the two means the recorder counts.

    Attributes:
        requests: The requests that reached httpcore's connection pools, where httpx's
            default transports hand a request over; respx answers each without sending it.
        sockets: The audit events that CPython's ``socket`` module raised for a connection,
            a lookup or a datagram, e.g. ``["socket.getaddrinfo"]``.
    """

    requests: int = 0
    sockets: list[str] = field(default_factory=list)


@contextmanager
def _recorded() -> Iterator[Sent]:
    """Count what the block hands over: at httpcore's pools by respx, and the socket events."""
    _hooked()
    sent = Sent()
    with respx.mock(assert_all_mocked=False) as router:
        _RECORDING.append(sent.sockets)
        try:
            yield sent
        finally:
            _RECORDING.pop()
            sent.requests = router.calls.call_count


def test_the_run_installs_every_source_of_the_extras() -> None:
    """The host's extras are the proving sources, and the run installs each of them."""
    extras = metadata("xippios-mcp").get_all("Provides-Extra") or []
    assert sorted(extra for extra in extras if extra != "all") == sorted(SOURCES)
    missing = [slug for slug in SOURCES if not _installed(slug)]
    assert missing == [], "uv sync --all-extras installs xippios-mcp[all]"


@pytest.mark.skipif(
    not any(_installed(slug) for slug in SOURCES), reason="no proving source is installed"
)
def test_the_recorder_counts_a_request_and_a_lookup() -> None:
    """The zeros of the calls below count: a request and a lookup are recorded here."""
    with _recorded() as sent:
        httpx.get("https://example.invalid/")  # answered by respx, never sent
        socket.getaddrinfo("127.0.0.1", 443)  # a numeric host: no resolver is asked
    assert (sent.requests, sent.sockets) == (1, ["socket.getaddrinfo"])


# Each tool set by its build(), and an endpoint of it as the source's own server lists it.


@pytest.mark.parametrize("ref", REFS)
def test_a_source_loads_by_its_build(ref: PackageRef) -> None:
    package = load_package(ref)
    assert isinstance(package.tool_set, ToolSet)
    assert package.tool_set.read_only is not ref.write
    own: ToolSet = _adapter(ref).build()
    assert package.tools == tuple(tool_name(own.source, fn) for fn in own.tasks)


@pytest.mark.anyio
@pytest.mark.parametrize("ref", REFS)
async def test_an_endpoint_lists_the_tools_of_the_sources_own_server(
    ref: PackageRef, tmp_path: Path
) -> None:
    built = _build(tmp_path, _endpoint(ref))
    own = _own(ref)
    assert built.server is not own
    assert (built.server.name, built.server.version, built.server.instructions) == (
        own.name,
        own.version,
        own.instructions,
    )
    assert (built.write, built.held) == (
        ref.write,
        ref.write or _adapter(ref).build().loopback_only,
    )
    ours, theirs = await _schemas(built.server), await _schemas(own)
    assert list(ours) == list(theirs)
    assert ours == theirs
    assert list(ours) == list(built.tools)


@pytest.mark.anyio
@_needs("faostat", "usda-esr")
async def test_a_group_of_two_read_tool_sets(tmp_path: Path) -> None:
    built = _build(tmp_path, "agriculture")
    faostat, esr = _own(PackageRef("faostat")), _own(PackageRef("usda-esr"))
    assert (built.server.name, built.write, built.held) == ("xippios-agriculture", False, False)
    theirs = await _schemas(faostat) | await _schemas(esr)
    ours = await _schemas(built.server)
    assert list(ours) == list(theirs)
    assert ours == theirs
    instructions = built.server.instructions or ""
    assert instructions.startswith(
        f"The xippios-mcp endpoint agriculture serves {len(theirs)} read-only tools of faostat "
    )
    assert f"\n\n## faostat\n\n{faostat.instructions}\n\n## usda-esr\n\n" in instructions
    assert instructions.endswith(f"## usda-esr\n\n{esr.instructions}")


@pytest.mark.anyio
@_needs(*SOURCES)
async def test_the_list_mode_prints_each_endpoint_with_its_tool_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    count = {str(ref): len(await _schemas(_own(ref))) for ref in TOOL_SETS}
    main(["--config", str(_config(tmp_path))])
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.splitlines() == [
        f"faostat: read, {count['faostat']} tools of faostat",
        f"cashctrl: read, {count['cashctrl']} tools of cashctrl",
        f"usda-esr: read, {count['usda-esr']} tools of usda-esr",
        f"agriculture: read, {count['faostat'] + count['usda-esr']} tools of faostat, usda-esr",
        f"cashctrl-write: write, {count['cashctrl:write']} tools of cashctrl",
    ]


@_needs("faostat", "usda-esr", "cashctrl")
def test_the_sample_config_builds_from_the_extras(capsys: pytest.CaptureFixture[str]) -> None:
    """The README's sample, ``docs/host.example.toml``, names sources of the extras alone.

    So an operator who installs ``xippios-mcp[all]`` checks it as the README says, and it
    builds every endpoint where 0.1.0's sample named sources that 0.2.0 cannot install.
    """
    endpoints = load_config(SAMPLE).endpoints.values()
    assert {ref.slug for endpoint in endpoints for ref in endpoint.packages} <= set(SOURCES)
    main(["--config", str(SAMPLE)])
    captured = capsys.readouterr()
    assert captured.err == ""
    assert [line.partition(",")[0] for line in captured.out.splitlines()] == [
        "agriculture: read",
        "accounting-write: write",
    ]


@_needs("usda-esr")
def test_an_endpoint_of_the_shared_package_is_refused(tmp_path: Path) -> None:
    """``xippios-usda-fas`` comes with sdk-usda-esr and runs no server, so the host serves none."""
    assert _installed("usda-fas")
    path = tmp_path / "host.toml"
    path.write_text('[endpoints.fas]\npackages = ["usda-fas"]\nauth = "none"\n', encoding="utf-8")
    with pytest.raises(ConfigError) as refused:
        build_endpoint(load_config(path).endpoints["fas"])
    assert str(refused.value).endswith(
        "endpoints.fas.packages: usda-fas: xippios.usda.fas has no xippios.usda.fas.mcp, "
        "the module of a source's MCP server"
    )


# One call for each source, with nothing counted: an answer from a table the package carries,
# or a refusal before any request, with none of the source's variables set.


async def _recorded_call(
    built: Built,
    tool: str,
    arguments: dict[str, Any],
    record_property: Callable[[str, object], None],
) -> str:
    """Call ``tool`` inside the recorder, assert that it counted nothing, and return its text.

    The text is kept as the test's property ``answer``, which ``--junitxml`` writes, so a
    run records what each call answered.
    """
    with _recorded() as sent:
        text = await mcp_call_text(built.server, tool, arguments)
    record_property("answer", text)
    assert (sent.requests, sent.sockets) == (0, [])
    return text


@pytest.mark.anyio
@_needs("faostat")
async def test_faostat_answers_an_area_list_from_its_packaged_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
) -> None:
    _without_variables("faostat", monkeypatch)
    built = _build(tmp_path, "faostat")
    arguments = {"domain_code": "QCL", "search": "germany"}
    text = await _recorded_call(built, "faostat_list_areas", arguments, record_property)
    assert not text.startswith("error:"), text
    answer = json.loads(text)
    assert [(row["code"], row["label"]) for row in answer["data"]] == [("79", "Germany")]
    assert (answer["meta"]["source"], answer["meta"]["endpoint"]) == ("faostat", "getCodeList")


@pytest.mark.anyio
@_needs("usda-esr")
async def test_usda_esr_answers_its_regions_from_its_packaged_list(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
) -> None:
    _without_variables("usda-esr", monkeypatch)
    built = _build(tmp_path, "usda-esr")
    text = await _recorded_call(built, "usda_esr_list_regions", {}, record_property)
    assert not text.startswith("error:"), text
    answer = json.loads(text)
    assert answer["data"]
    assert all(set(row) == {"region_id", "region_name"} for row in answer["data"])
    meta = answer["meta"]
    assert (meta["source"], meta["endpoint"]) == ("usda-esr", "ESRData_GetRegions")


@pytest.mark.anyio
@_needs("cashctrl")
async def test_cashctrl_refuses_an_undeclared_organisation_before_any_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
) -> None:
    _without_variables("cashctrl", monkeypatch)
    built = _build(tmp_path, "cashctrl")
    arguments = {"org": "demo"}
    text = await _recorded_call(built, "cashctrl_list_currencies", arguments, record_property)
    assert text.startswith("error: InvalidRequestError: unknown tenant 'demo'; no tenant is "), text
    assert text.endswith("Nothing was sent."), text
