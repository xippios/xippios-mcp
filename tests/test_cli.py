"""The entry point with a config: serve on stdio or HTTP, or list one line per endpoint;
a refusal exits with status 2.

Nothing is served: ``--stdio`` hands the endpoint's server to its ``run``, stubbed, and
``--http`` hands the app to ``serve_http``, stubbed, so no test binds a port. The token
below is a test value set with ``monkeypatch.setenv``; it never leaves the test. The
packages are the invented sources under ``tests/example``.
"""

import argparse
import logging
from pathlib import Path
from typing import Any

import pytest
import xippios.example.api.mcp
import xippios.example.mcp
import xippios.example.mcp_write
from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from xippios.core import ConfigError
from xippios.example import tasks as example_tasks
from xippios.example import tasks_write as example_tasks_write

import xippios.mcp.cli
from xippios.mcp.cli import main

TOKEN = "test-bearer-for-the-unit-tests-only"  # pragma: allowlist secret
VARIABLE = "XIPPIOS_MCP_AGRICULTURE_TOKEN"
BEARER = f'[endpoints.agriculture]\npackages = ["example"]\ntoken_env = "{VARIABLE}"\n'
OPEN_API = '[endpoints.trade]\npackages = ["example-api"]\nauth = "none"\n'
READ = len(xippios.example.mcp.build().tasks)
API = len(xippios.example.api.mcp.build().tasks)
WRITE = len(xippios.example.mcp_write.build().tasks)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "host.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_good_config_lists_its_endpoints(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(
        tmp_path,
        """
[endpoints.trade]
packages = ["example", "example-api"]
exclude = { example-api = ["get_record"] }
token_env = "XIPPIOS_MCP_TRADE_TOKEN"

[endpoints.accounting-write]
packages = ["example:write"]
auth = "none"
""",
    )
    main(["--config", str(path)])  # returns: exit status 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.splitlines() == [
        f"trade: read, {READ + API - 1} tools of example, example-api",
        f"accounting-write: write, {WRITE} tools of example",
    ]


def test_a_bad_config_exits_2_with_the_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(
        tmp_path, '[endpoints.agriculture]\npackages = ["example:write", "example-api"]\n'
    )
    with pytest.raises(SystemExit) as exited:
        main(["--config", str(path)])
    assert exited.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert f"xippios-mcp: error: {path}: endpoints.agriculture.packages: mixes" in captured.err


def test_a_refusal_that_needs_the_package_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(
        tmp_path,
        '[endpoints.agriculture]\npackages = ["example"]\nauth = "none"\n'
        'include = { example = ["get_serie"] }\n',
    )
    with pytest.raises(SystemExit) as exited:
        main(["--config", str(path)])
    assert exited.value.code == 2
    err = capsys.readouterr().err
    assert f"{path}: endpoints.agriculture.include.example: get_serie: no task" in err


def create_thing(name: str) -> None:
    """A write task without ``confirm``, which core's tool set refuses when it is built."""


def test_a_refusal_of_the_tool_set_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(example_tasks_write, "create_thing", create_thing)
    path = _write(
        tmp_path, '[endpoints.accounting-write]\npackages = ["example:write"]\nauth = "none"\n'
    )
    with pytest.raises(SystemExit) as exited:
        main(["--config", str(path)])
    assert exited.value.code == 2
    err = capsys.readouterr().err
    assert (
        f"error: {path}: endpoints.accounting-write: example:write: ValueError: "
        "example_create_thing: no parameter confirm"
    ) in err


def test_a_declaration_of_the_wrong_type_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Core's ``TypeError`` for it ends as a refusal, never as a traceback."""
    monkeypatch.setattr(example_tasks, "MCP_CAPS", ["list_regions"])
    path = _write(tmp_path, '[endpoints.agriculture]\npackages = ["example"]\nauth = "none"\n')
    with pytest.raises(SystemExit) as exited:
        main(["--config", str(path)])
    assert exited.value.code == 2
    err = capsys.readouterr().err
    assert (
        f"error: {path}: endpoints.agriculture: example: TypeError: "
        "xippios.example.tasks.MCP_CAPS is a mapping, got list"
    ) in err


def test_the_list_applies_the_hooks_at_their_defaults(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The list builds every endpoint as it is served, the packages' option hooks applied."""
    path = _write(tmp_path, '[endpoints.agriculture]\npackages = ["example"]\nauth = "none"\n')
    assert example_tasks.SERIES.value == 20
    main(["--config", str(path)])
    assert capsys.readouterr().out == f"agriculture: read, {READ} tools of example\n"
    assert example_tasks.SERIES.value == 5


def test_a_refusal_of_a_hook_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(namespace: argparse.Namespace) -> None:
        raise ConfigError("EXAMPLE_REGION is not set; set it to a region's code")

    monkeypatch.setattr(example_tasks, "mcp_apply_options", refuse)
    path = _write(tmp_path, '[endpoints.agriculture]\npackages = ["example"]\nauth = "none"\n')
    with pytest.raises(SystemExit) as exited:
        main(["--config", str(path)])
    assert exited.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        f"xippios-mcp: error: {path}: endpoints.agriculture: example: ConfigError: "
        "EXAMPLE_REGION is not set"
    ) in captured.err


def test_an_unrelated_value_error_is_no_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ValueError the build does not raise as BuildError propagates: no exit status 2."""

    def build_all(config: object) -> None:
        raise ValueError("a bug in a package's import")

    monkeypatch.setattr(xippios.mcp.cli, "build_all", build_all)
    path = _write(tmp_path, '[endpoints.agriculture]\npackages = ["example"]\nauth = "none"\n')
    with pytest.raises(ValueError, match="a bug in a package's import"):
        main(["--config", str(path)])


def _exits_2(argv: list[str], capsys: pytest.CaptureFixture[str]) -> str:
    with pytest.raises(SystemExit) as exited:
        main(argv)
    assert exited.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    return captured.err


class _Served:
    """A stub for ``serve_http`` or a server's ``run``: records the call, serves nothing."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


class _Run(_Served):
    """A stub for ``MCPServer.run``: records the server's name and the call."""

    def __get__(self, server: MCPServer, owner: type[MCPServer]) -> Any:
        return lambda *args, **kwargs: self(server.name, *args, **kwargs)


@pytest.fixture
def serve_http(monkeypatch: pytest.MonkeyPatch) -> _Served:
    served = _Served()
    monkeypatch.setattr(xippios.mcp.cli, "serve_http", served)
    return served


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch) -> _Served:
    """``run`` of every ``MCPServer``: an endpoint's server is one the host builds."""
    served = _Run()
    monkeypatch.setattr(MCPServer, "run", served)
    return served


# --stdio ENDPOINT


def test_stdio_serves_the_one_endpoint_without_its_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    run: _Served,
    serve_http: _Served,
) -> None:
    monkeypatch.delenv(VARIABLE, raising=False)  # stdio reads no token variable
    logging.getLogger("httpx").setLevel(logging.INFO)
    path = _write(tmp_path, f"{BEARER}\n{OPEN_API}")
    main(["--config", str(path), "--stdio", "agriculture"])
    assert run.calls == [(("xippios-example",), {"transport": "stdio"})]
    assert serve_http.calls == []
    assert logging.getLogger("httpx").level == logging.WARNING  # quieted before serving
    captured = capsys.readouterr()
    assert captured.out == ""  # no endpoint list: stdout is the MCP stream


def test_stdio_with_an_unknown_endpoint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], run: _Served
) -> None:
    path = _write(tmp_path, f"{BEARER}\n{OPEN_API}")
    err = _exits_2(["--config", str(path), "--stdio", "agricultre"], capsys)
    assert f"{path}: --stdio agricultre: no endpoint of the config" in err
    assert "the configured ones: agriculture, trade" in err
    assert run.calls == []


def test_stdio_and_http_together(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path, BEARER)
    err = _exits_2(["--config", str(path), "--stdio", "agriculture", "--http"], capsys)
    assert "not allowed with argument" in err


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param(["--host", "0.0.0.0"], id="host"),
        pytest.param(["--port", "9000"], id="port"),
        pytest.param(["--stdio", "agriculture", "--port", "9000"], id="port with stdio"),
    ],
)
def test_host_and_port_need_http(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], extra: list[str], run: _Served
) -> None:
    path = _write(tmp_path, BEARER)
    err = _exits_2(["--config", str(path), *extra], capsys)
    assert "--host and --port apply to --http only" in err
    assert run.calls == []


# --http


def test_http_serves_every_endpoint_on_the_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    serve_http: _Served,
) -> None:
    monkeypatch.setenv(VARIABLE, TOKEN)
    logging.getLogger("httpx").setLevel(logging.INFO)
    path = _write(tmp_path, f"{BEARER}\n{OPEN_API}")
    main(["--config", str(path), "--http"])
    [(args, kwargs)] = serve_http.calls
    app, host, port = args
    assert isinstance(app, Starlette)
    assert (host, port, kwargs) == ("127.0.0.1", 8000, {})
    assert [route.path for route in app.routes] == ["/agriculture", "/trade"]  # type: ignore[attr-defined]
    assert logging.getLogger("httpx").level == logging.WARNING
    captured = capsys.readouterr()
    assert captured.out == ""
    assert TOKEN not in captured.err


def test_http_on_a_host_and_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, serve_http: _Served
) -> None:
    monkeypatch.setenv(VARIABLE, TOKEN)
    path = _write(tmp_path, BEARER)
    main(["--config", str(path), "--http", "--host", "0.0.0.0", "--port", "9000"])
    [(args, _)] = serve_http.calls
    assert args[1:] == ("0.0.0.0", 9000)


@pytest.mark.parametrize("value", [None, ""], ids=["unset", "empty"])
def test_http_with_a_missing_or_empty_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    serve_http: _Served,
    value: str | None,
) -> None:
    if value is None:
        monkeypatch.delenv(VARIABLE, raising=False)
    else:
        monkeypatch.setenv(VARIABLE, value)
    path = _write(tmp_path, BEARER)
    err = _exits_2(["--config", str(path), "--http"], capsys)
    assert f"{path}: endpoints.agriculture.token_env: {VARIABLE} is not set or is empty" in err
    assert serve_http.calls == []


def test_http_refuses_an_open_write_endpoint_beyond_loopback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    serve_http: _Served,
) -> None:
    monkeypatch.setenv(VARIABLE, TOKEN)
    path = _write(
        tmp_path, f'{BEARER}\n[endpoints.books]\npackages = ["example:write"]\nauth = "none"\n'
    )
    err = _exits_2(["--config", str(path), "--http", "--host", "0.0.0.0"], capsys)
    assert f"{path}: endpoints.books.auth: " in err
    assert "--host 0.0.0.0 is beyond loopback" in err
    assert TOKEN not in err
    assert serve_http.calls == []


def test_http_serves_one_package_alone_on_two_endpoints(
    tmp_path: Path, serve_http: _Served
) -> None:
    text = '[endpoints.a]\npackages = ["example"]\nauth = "none"\n'
    path = _write(tmp_path, text + text.replace("endpoints.a", "endpoints.b"))
    main(["--config", str(path), "--http"])
    [(args, _)] = serve_http.calls
    assert [route.path for route in args[0].routes] == ["/a", "/b"]


def test_a_port_that_is_no_number(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path, BEARER)
    assert "--port: invalid int value" in _exits_2(
        ["--config", str(path), "--http", "--port", "http"], capsys
    )
