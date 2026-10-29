"""The entry point with a config: serve on stdio or HTTP, or list one line per endpoint;
a refusal exits with status 2.

Nothing is served: ``--stdio`` hands the endpoint's server to its ``run``, stubbed, and
``--http`` hands the app to ``serve_http``, stubbed, so no test binds a port. The token
below is a test value set with ``monkeypatch.setenv``; it never leaves the test.
"""

import logging
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import xippios.usda.nass.mcp
from starlette.applications import Starlette
from xippios.cashctrl import tasks_write as cashctrl_tasks_write
from xippios.comtrade import tasks as comtrade_tasks
from xippios.usda.nass import tasks as nass_tasks

import xippios.mcp.cli
from xippios.mcp.cli import main

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "docs" / "host.example.toml"
TOKEN = "test-bearer-for-the-unit-tests-only"  # pragma: allowlist secret
VARIABLE = "XIPPIOS_MCP_AGRICULTURE_TOKEN"
BEARER = f'[endpoints.agriculture]\npackages = ["usda-nass"]\ntoken_env = "{VARIABLE}"\n'


def _count(tasks: ModuleType) -> int:
    """The tools of ``tasks.__all__``: ``BULK_TASKS`` left out."""
    bulk: frozenset[str] = getattr(tasks, "BULK_TASKS", frozenset())
    return len([name for name in tasks.__all__ if name not in bulk])


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
packages = ["usda-nass", "comtrade"]
exclude = { comtrade = ["get_counts"] }
token_env = "XIPPIOS_MCP_TRADE_TOKEN"

[endpoints.accounting-write]
packages = ["cashctrl:write"]
auth = "none"
""",
    )
    main(["--config", str(path)])  # returns: exit status 0
    captured = capsys.readouterr()
    assert captured.err == ""
    trade = _count(nass_tasks) + _count(comtrade_tasks) - 1
    write = _count(cashctrl_tasks_write)
    assert captured.out.splitlines() == [
        f"trade: read, {trade} tools of usda-nass, comtrade",
        f"accounting-write: write, {write} tools of cashctrl",
    ]


def test_the_sample_config(capsys: pytest.CaptureFixture[str]) -> None:
    main(["--config", str(SAMPLE)])
    lines = capsys.readouterr().out.splitlines()
    assert [line.split(":")[0] for line in lines] == ["agriculture", "accounting-write"]


def test_a_bad_config_exits_2_with_the_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, '[endpoints.agriculture]\npackages = ["cashctrl:write", "usda-nass"]\n')
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
        '[endpoints.agriculture]\npackages = ["usda-nass"]\nauth = "none"\n'
        'include = { usda-nass = ["get_count"] }\n',
    )
    with pytest.raises(SystemExit) as exited:
        main(["--config", str(path)])
    assert exited.value.code == 2
    err = capsys.readouterr().err
    assert f"{path}: endpoints.agriculture.include.usda-nass: get_count: no task" in err


def test_a_value_error_from_the_build_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """``register_tasks`` refuses a cap or a write task without confirm with a ValueError."""

    def build_all(config: object) -> None:
        raise ValueError("host.toml: endpoints.agriculture: usda-nass: caps names no task")

    monkeypatch.setattr(xippios.mcp.cli, "build_all", build_all)
    path = _write(tmp_path, '[endpoints.agriculture]\npackages = ["usda-nass"]\nauth = "none"\n')
    with pytest.raises(SystemExit) as exited:
        main(["--config", str(path)])
    assert exited.value.code == 2
    assert "error: host.toml: endpoints.agriculture: usda-nass: caps" in capsys.readouterr().err


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


@pytest.fixture
def serve_http(monkeypatch: pytest.MonkeyPatch) -> _Served:
    served = _Served()
    monkeypatch.setattr(xippios.mcp.cli, "serve_http", served)
    return served


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch) -> _Served:
    """``run`` of usda-nass's own server, the one an endpoint of usda-nass alone serves."""
    served = _Served()
    monkeypatch.setattr(xippios.usda.nass.mcp.server, "run", served)
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
    path = _write(
        tmp_path, f'{BEARER}\n[endpoints.trade]\npackages = ["comtrade"]\nauth = "none"\n'
    )
    main(["--config", str(path), "--stdio", "agriculture"])
    assert run.calls == [((), {"transport": "stdio"})]
    assert serve_http.calls == []
    assert logging.getLogger("httpx").level == logging.WARNING  # quieted before serving
    captured = capsys.readouterr()
    assert captured.out == ""  # no endpoint list: stdout is the MCP stream


def test_stdio_with_an_unknown_endpoint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], run: _Served
) -> None:
    path = _write(
        tmp_path, f'{BEARER}\n[endpoints.trade]\npackages = ["comtrade"]\nauth = "none"\n'
    )
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
    path = _write(
        tmp_path, f'{BEARER}\n[endpoints.trade]\npackages = ["comtrade"]\nauth = "none"\n'
    )
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
        tmp_path, f'{BEARER}\n[endpoints.books]\npackages = ["cashctrl:write"]\nauth = "none"\n'
    )
    err = _exits_2(["--config", str(path), "--http", "--host", "0.0.0.0"], capsys)
    assert f"{path}: endpoints.books.auth: " in err
    assert "--host 0.0.0.0 is beyond loopback" in err
    assert TOKEN not in err
    assert serve_http.calls == []


def test_http_refuses_a_packages_own_server_twice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], serve_http: _Served
) -> None:
    text = '[endpoints.a]\npackages = ["usda-nass"]\nauth = "none"\n'
    path = _write(tmp_path, text + text.replace("endpoints.a", "endpoints.b"))
    err = _exits_2(["--config", str(path), "--http"], capsys)
    assert f"{path}: endpoints.b.packages: " in err
    assert "which endpoints.a mounts too" in err
    assert serve_http.calls == []


def test_a_port_that_is_no_number(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path, BEARER)
    assert "--port: invalid int value" in _exits_2(
        ["--config", str(path), "--http", "--port", "http"], capsys
    )
