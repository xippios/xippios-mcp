"""``load_config``: the config file's shape, checked before any package is imported."""

from pathlib import Path

import pytest
from xippios.core import ConfigError

from xippios.mcp.config import PackageRef, load_config

GOOD = """
[endpoints.agriculture]
packages = ["usda-nass", "usda-psd"]
exclude = { usda-nass = ["get_counts"] }
token_env = "XIPPIOS_MCP_AGRICULTURE_TOKEN"

[endpoints.trade]
packages = ["comtrade"]
include = { comtrade = ["get_data", "list_partners"] }
auth = "bearer"
token_env = "XIPPIOS_MCP_TRADE_TOKEN"

[endpoints.accounting-write]
packages = ["cashctrl:write"]
auth = "none"
allow_remote = true
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "host.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _refused(path: Path) -> str:
    with pytest.raises(ConfigError) as refused:
        load_config(path)
    message = str(refused.value)
    assert message.startswith(f"{path}: "), message
    return message


def test_a_good_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # token_env names a variable the loader never reads: unset, the file still loads.
    monkeypatch.delenv("XIPPIOS_MCP_AGRICULTURE_TOKEN", raising=False)
    path = _write(tmp_path, GOOD)
    config = load_config(path)
    assert config.path == path
    assert list(config.endpoints) == ["agriculture", "trade", "accounting-write"]

    agriculture = config.endpoints["agriculture"]
    assert agriculture.name == "agriculture"
    assert agriculture.packages == (PackageRef("usda-nass"), PackageRef("usda-psd"))
    assert dict(agriculture.exclude) == {"usda-nass": frozenset({"get_counts"})}
    assert dict(agriculture.include) == {}
    assert agriculture.auth == "bearer"
    assert agriculture.token_env == "XIPPIOS_MCP_AGRICULTURE_TOKEN"
    assert agriculture.allow_remote is False
    assert agriculture.write is False
    assert agriculture.path == path

    trade = config.endpoints["trade"]
    assert dict(trade.include) == {"comtrade": frozenset({"get_data", "list_partners"})}

    accounting = config.endpoints["accounting-write"]
    assert accounting.packages == (PackageRef("cashctrl", write=True),)
    assert str(accounting.packages[0]) == "cashctrl:write"
    assert accounting.auth == "none"
    assert accounting.token_env is None
    assert accounting.allow_remote is True
    assert accounting.write is True


def test_the_config_is_read_only(tmp_path: Path) -> None:
    config = load_config(_write(tmp_path, GOOD))
    with pytest.raises(TypeError):
        config.endpoints["other"] = config.endpoints["trade"]  # type: ignore[index]
    with pytest.raises(TypeError):
        config.endpoints["agriculture"].exclude["usda-psd"] = frozenset()  # type: ignore[index]


def test_a_missing_file(tmp_path: Path) -> None:
    assert "no such file" in _refused(tmp_path / "absent.toml")


def test_a_file_that_is_no_toml(tmp_path: Path) -> None:
    assert "is no TOML" in _refused(_write(tmp_path, "[endpoints.agriculture\n"))


def test_a_file_that_is_not_utf8(tmp_path: Path) -> None:
    path = tmp_path / "host.toml"
    path.write_bytes(b"[endpoints.agriculture]\npackages = ['\xff']\n")
    assert "is no TOML" in _refused(path)


def _endpoint(body: str, name: str = "agriculture") -> str:
    return f"[endpoints.{name}]\n{body}\n"


NASS = 'packages = ["usda-nass"]\nauth = "none"'
"""An endpoint body that loads, for the cases that break one key of it."""

# (case, file text, the dotted key the message names, a fragment of the message)
REFUSALS = [
    ("no endpoints table", "", "endpoints", "missing"),
    ("an empty endpoints table", "[endpoints]\n", "endpoints", "names no endpoint"),
    ("endpoints not a table", "endpoints = 3\n", "endpoints", "must be a table"),
    ("an unknown top key", f"port = 8000\n{_endpoint(NASS)}", "port", "unknown key"),
    (
        "an upper-case endpoint name",
        _endpoint(NASS, "Agriculture"),
        "endpoints.Agriculture",
        "lower-case",
    ),
    (
        "an endpoint name with a space",
        _endpoint(NASS, '"agri culture"'),
        'endpoints."agri culture"',
        "lower-case",
    ),
    (
        "an endpoint name starting with a hyphen",
        _endpoint(NASS, "-agriculture"),
        "endpoints.-agriculture",
        "starting with a letter or a digit",
    ),
    (
        "an endpoint that is no table",
        "endpoints = { agriculture = 3 }\n",
        "endpoints.agriculture",
        "must be a table",
    ),
    (
        "an unknown endpoint key",
        _endpoint(f"{NASS}\nport = 8000"),
        "endpoints.agriculture.port",
        "unknown key",
    ),
    (
        "packages missing",
        _endpoint('auth = "none"'),
        "endpoints.agriculture.packages",
        "missing",
    ),
    (
        "packages empty",
        _endpoint('packages = []\nauth = "none"'),
        "endpoints.agriculture.packages",
        "names no package",
    ),
    (
        "packages not a list",
        _endpoint('packages = "usda-nass"\nauth = "none"'),
        "endpoints.agriculture.packages",
        "must be a list of package names",
    ),
    (
        "packages not strings",
        _endpoint('packages = ["usda-nass", 3]\nauth = "none"'),
        "endpoints.agriculture.packages",
        "must be a list of package names",
    ),
    (
        "an empty package name",
        _endpoint('packages = [""]\nauth = "none"'),
        "endpoints.agriculture.packages",
        "must be a list of package names",
    ),
    (
        "a slug named twice",
        _endpoint('packages = ["usda-nass", "usda-psd", "usda-nass"]\nauth = "none"'),
        "endpoints.agriculture.packages",
        "usda-nass: named twice",
    ),
    (
        "a suffix other than :write",
        _endpoint('packages = ["cashctrl:read"]\nauth = "none"'),
        "endpoints.agriculture.packages",
        "cashctrl:read: the one suffix is :write",
    ),
    (
        ":write without a slug",
        _endpoint('packages = [":write"]\nauth = "none"'),
        "endpoints.agriculture.packages",
        ":write: names no package",
    ),
    (
        "a group that mixes write and read",
        _endpoint('packages = ["cashctrl:write", "usda-nass"]\nauth = "none"'),
        "endpoints.agriculture.packages",
        "a group never mixes read and write tools",
    ),
    (
        "a package's read and write servers together",
        _endpoint('packages = ["cashctrl", "cashctrl:write"]\nauth = "none"'),
        "endpoints.agriculture.packages",
        "a group never mixes read and write tools",
    ),
    (
        "include and exclude for one package",
        _endpoint(
            f'{NASS}\ninclude = {{ usda-nass = ["get_data"] }}\n'
            'exclude = { usda-nass = ["get_counts"] }'
        ),
        "endpoints.agriculture.include.usda-nass",
        "include and exclude both name this package",
    ),
    (
        "a list keyed by a package the endpoint does not name",
        _endpoint(f'{NASS}\nexclude = {{ usda-psd = ["get_data"] }}'),
        "endpoints.agriculture.exclude.usda-psd",
        "names no package of the endpoint",
    ),
    (
        "a list keyed by the write suffix",
        _endpoint(
            'packages = ["cashctrl:write"]\nauth = "none"\n'
            'exclude = { "cashctrl:write" = ["delete_person"] }'
        ),
        'endpoints.agriculture.exclude."cashctrl:write"',
        "names no package of the endpoint; key a list by a package's slug, one of: cashctrl",
    ),
    (
        "lists that are no table",
        _endpoint(f'{NASS}\nexclude = ["get_counts"]'),
        "endpoints.agriculture.exclude",
        "must be a table of task names by package",
    ),
    (
        "a list that is no list",
        _endpoint(f'{NASS}\nexclude = {{ usda-nass = "get_counts" }}'),
        "endpoints.agriculture.exclude.usda-nass",
        "must be a list of task names",
    ),
    (
        "a list of no strings",
        _endpoint(f"{NASS}\ninclude = {{ usda-nass = [3] }}"),
        "endpoints.agriculture.include.usda-nass",
        "must be a list of task names",
    ),
    (
        "an empty include list",
        _endpoint(f"{NASS}\ninclude = {{ usda-nass = [] }}"),
        "endpoints.agriculture.include.usda-nass",
        "includes no task",
    ),
    (
        "a task named twice in a list",
        _endpoint(f'{NASS}\nexclude = {{ usda-nass = ["get_counts", "get_counts"] }}'),
        "endpoints.agriculture.exclude.usda-nass",
        "get_counts: named twice",
    ),
    (
        "an unknown auth",
        _endpoint('packages = ["usda-nass"]\nauth = "basic"'),
        "endpoints.agriculture.auth",
        'must be "bearer", the default, or "none"',
    ),
    (
        "an auth that is no string",
        _endpoint('packages = ["usda-nass"]\nauth = false'),
        "endpoints.agriculture.auth",
        'must be "bearer", the default, or "none"',
    ),
    (
        "the default bearer without token_env",
        _endpoint('packages = ["usda-nass"]'),
        "endpoints.agriculture.token_env",
        'missing; auth = "bearer", the default',
    ),
    (
        "an explicit bearer without token_env",
        _endpoint('packages = ["usda-nass"]\nauth = "bearer"'),
        "endpoints.agriculture.token_env",
        'e.g. token_env = "XIPPIOS_MCP_AGRICULTURE_TOKEN"',
    ),
    (
        "a token_env that is no string",
        _endpoint('packages = ["usda-nass"]\ntoken_env = 3'),
        "endpoints.agriculture.token_env",
        "must name an environment variable that ends in _TOKEN",
    ),
    (
        "a lower-case token_env",
        _endpoint('packages = ["usda-nass"]\ntoken_env = "xippios_mcp_agriculture_token"'),
        "endpoints.agriculture.token_env",
        "must name an environment variable that ends in _TOKEN",
    ),
    (
        "a token_env without the _TOKEN suffix",
        _endpoint('packages = ["usda-nass"]\ntoken_env = "XIPPIOS_MCP_AGRICULTURE"'),
        "endpoints.agriculture.token_env",
        "so the leak rule names it by its suffix",
    ),
    (
        "a token_env that is the suffix alone",
        _endpoint('packages = ["usda-nass"]\ntoken_env = "_TOKEN"'),
        "endpoints.agriculture.token_env",
        "ends in _TOKEN",
    ),
    (
        "a token_env with auth none",
        _endpoint(f'{NASS}\ntoken_env = "XIPPIOS_MCP_AGRICULTURE_TOKEN"'),
        "endpoints.agriculture.token_env",
        'is given with auth = "none"',
    ),
    (
        "allow_remote that is no bool",
        _endpoint(f'{NASS}\nallow_remote = "yes"'),
        "endpoints.agriculture.allow_remote",
        "must be true or false",
    ),
]


@pytest.mark.parametrize(
    ("text", "key", "fragment"),
    [pytest.param(text, key, fragment, id=case) for case, text, key, fragment in REFUSALS],
)
def test_refusals(tmp_path: Path, text: str, key: str, fragment: str) -> None:
    message = _refused(_write(tmp_path, text))
    assert f": {key}: " in message, message
    assert fragment in message, message


def test_a_refused_token_env_is_not_repeated(tmp_path: Path) -> None:
    """A token pasted where the variable's name goes stays out of the message."""
    pasted = "not-a-variable-but-a-pasted-value-0123456789"
    text = _endpoint(f'packages = ["usda-nass"]\ntoken_env = "{pasted}"')
    message = _refused(_write(tmp_path, text))
    assert pasted not in message
    assert "the value is not shown here" in message


def test_an_unknown_key_names_the_key_not_its_value(tmp_path: Path) -> None:
    value = "a-value-that-stays-out-of-the-message"
    message = _refused(_write(tmp_path, _endpoint(f'{NASS}\ntoken = "{value}"')))
    assert "endpoints.agriculture.token: unknown key" in message
    assert value not in message
