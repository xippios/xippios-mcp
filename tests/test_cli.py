"""The entry point with a config: one line per endpoint, or the refusal and exit status 2."""

from pathlib import Path
from types import ModuleType

import pytest
from xippios.cashctrl import tasks_write as cashctrl_tasks_write
from xippios.comtrade import tasks as comtrade_tasks
from xippios.usda.nass import tasks as nass_tasks

import xippios.mcp.cli
from xippios.mcp.cli import main

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "docs" / "host.example.toml"


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
