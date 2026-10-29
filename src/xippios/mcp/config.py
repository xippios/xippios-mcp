"""The host's config file: its endpoints, their packages, tool lists and auth (ADR-0026).

The file is TOML, read with ``tomllib`` (Johannes, 2026-10-29). Each table under
``[endpoints]`` is one endpoint, served at ``/<name>/mcp`` over HTTP::

    [endpoints.agriculture]
    packages = ["usda-nass", "usda-psd", "comtrade"]
    exclude = { usda-nass = ["get_counts"] }
    auth = "bearer"
    token_env = "XIPPIOS_MCP_AGRICULTURE_TOKEN"
    allow_remote = false

    [endpoints.accounting-write]
    packages = ["cashctrl:write"]
    auth = "none"

``load_config`` checks the file's shape and nothing that needs a package: the known
slugs, the task names and the servers are checked when the endpoints are built
(``xippios.mcp.servers``). It reads no environment variable: ``token_env`` names one,
and the bearer reads it when it serves (conventions §7). Every refusal is a
``ConfigError`` naming the file, the endpoint and the key. A message repeats slugs and
task names, and from the build a package's ``server.name``, but never the value of
``token_env``, ``auth`` or ``allow_remote``, nor the value of an unknown key. The build
re-raises a refusal of core's ``register_tasks`` as ``BuildError``, a ``ValueError``,
with the file, the endpoint and the package prefixed.
"""

import json
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from xippios.core import ConfigError

__all__ = ["Endpoint", "HostConfig", "PackageRef", "load_config", "refusal"]

WRITE_SUFFIX = ":write"
"""The suffix that names a package's write server, ``cashctrl:write``."""

_ENDPOINT_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
# A token variable ends in _TOKEN, so the family's leak rule names it by its suffix, as it
# names _API_KEY, _REFRESH_TOKEN and _SECRET (gap, row 309 (e)).
_TOKEN_VARIABLE = re.compile(r"[A-Z][A-Z0-9_]*_TOKEN")
_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_TOP_KEYS = ("endpoints",)
_ENDPOINT_KEYS = ("packages", "include", "exclude", "auth", "token_env", "allow_remote")
_LISTS = ("include", "exclude")


@dataclass(frozen=True, slots=True)
class PackageRef:
    """One entry of an endpoint's ``packages``: a package and which of its servers.

    Attributes:
        slug: The package's slug, the host's extra and the source's slug, e.g.
            ``"usda-nass"``.
        write: True for ``<slug>:write``, the package's write server.
    """

    slug: str
    write: bool = False

    def __str__(self) -> str:
        return f"{self.slug}{WRITE_SUFFIX}" if self.write else self.slug


@dataclass(frozen=True, slots=True)
class Endpoint:
    """One table under ``[endpoints]``.

    Attributes:
        name: The table's name, e.g. ``"agriculture"``; served at ``/<name>/mcp``.
        packages: The packages it serves, in the file's order; all of them write
            servers or none.
        include: Per package slug, the only tasks that become its tools.
        exclude: Per package slug, tasks that do not become tools.
        auth: ``"bearer"``, the default, or ``"none"``.
        token_env: The environment variable that holds the bearer token, a name ending
            in ``_TOKEN`` and never a value, e.g. ``"XIPPIOS_MCP_AGRICULTURE_TOKEN"``;
            ``None`` with ``auth = "none"``.
        allow_remote: Whether the endpoint may be served beyond loopback when the
            loopback rule would keep it there (ADR-0026, decision 5).
        path: The config file it was read from, named in every refusal.
    """

    name: str
    packages: tuple[PackageRef, ...]
    include: Mapping[str, frozenset[str]]
    exclude: Mapping[str, frozenset[str]]
    auth: Literal["bearer", "none"]
    token_env: str | None
    allow_remote: bool
    path: Path

    @property
    def write(self) -> bool:
        """True when the endpoint serves write servers; a group never mixes the two."""
        return self.packages[0].write


@dataclass(frozen=True, slots=True)
class HostConfig:
    """The config file, read and checked.

    Attributes:
        endpoints: Per endpoint name, its endpoint, in the file's order.
        path: The file it was read from.
    """

    endpoints: Mapping[str, Endpoint]
    path: Path


def _key(parts: Sequence[str]) -> str:
    """``parts`` as a TOML dotted key, a part that is no bare key quoted."""
    return ".".join(part if _BARE_KEY.fullmatch(part) else json.dumps(part) for part in parts)


def refusal(path: Path, keys: Sequence[str], problem: str) -> ConfigError:
    """The ``ConfigError`` for ``problem`` at the dotted key ``keys`` of the file ``path``.

    Args:
        path: The config file, e.g. ``Path("host.toml")``.
        keys: The key the problem is at, e.g. ``("endpoints", "agriculture", "packages")``.
        problem: What is wrong, without a value the key might hold.
    """
    return ConfigError(f"{path}: {_key(keys)}: {problem}")


def load_config(path: Path) -> HostConfig:
    """Read and check the host's config file.

    Args:
        path: The TOML file, e.g. ``Path("host.toml")``.

    Raises:
        ConfigError: The file is missing or no TOML, or a key is unknown, missing or
            malformed; the message names the file, the endpoint and the key.
    """
    data = _read(path)
    unknown = [key for key in data if key not in _TOP_KEYS]
    if unknown:
        raise refusal(path, unknown[:1], "unknown key; the file holds [endpoints] only")
    tables = data.get("endpoints")
    if tables is None:
        raise refusal(path, ["endpoints"], "missing; name an endpoint as [endpoints.<name>]")
    if not isinstance(tables, dict):
        raise refusal(path, ["endpoints"], "must be a table of endpoints, [endpoints.<name>]")
    if not tables:
        raise refusal(path, ["endpoints"], "names no endpoint")
    endpoints = {name: _endpoint(path, name, table) for name, table in tables.items()}
    return HostConfig(endpoints=MappingProxyType(endpoints), path=path)


def _read(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except FileNotFoundError as exc:
        raise ConfigError(f"{path}: no such file") from exc
    except OSError as exc:
        raise ConfigError(f"{path}: cannot be read: {exc.strerror}") from exc
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{path}: is no TOML: not UTF-8") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: is no TOML: {exc}") from exc


def _endpoint(path: Path, name: str, table: Any) -> Endpoint:
    here = ["endpoints", name]
    if not _ENDPOINT_NAME.fullmatch(name):
        raise refusal(
            path,
            here,
            "an endpoint name is lower-case letters, digits and hyphens, starting with a "
            "letter or a digit; it becomes the path /<name>/mcp",
        )
    if not isinstance(table, dict):
        raise refusal(path, here, "must be a table, [endpoints.<name>]")
    for key in table:
        if key not in _ENDPOINT_KEYS:
            raise refusal(
                path, [*here, key], f"unknown key; an endpoint has {', '.join(_ENDPOINT_KEYS)}"
            )
    packages = _packages(path, here, table.get("packages"))
    slugs = [ref.slug for ref in packages]
    lists = {kind: _lists(path, [*here, kind], table.get(kind), slugs) for kind in _LISTS}
    both = sorted(set(lists["include"]) & set(lists["exclude"]))
    if both:
        raise refusal(
            path,
            [*here, "include", both[0]],
            "include and exclude both name this package; give one of them",
        )
    auth, token_env = _auth(path, here, table)
    allow_remote = table.get("allow_remote", False)
    if not isinstance(allow_remote, bool):
        raise refusal(path, [*here, "allow_remote"], "must be true or false")
    return Endpoint(
        name=name,
        packages=packages,
        include=MappingProxyType(lists["include"]),
        exclude=MappingProxyType(lists["exclude"]),
        auth=auth,
        token_env=token_env,
        allow_remote=allow_remote,
        path=path,
    )


def _packages(path: Path, here: list[str], value: Any) -> tuple[PackageRef, ...]:
    key = [*here, "packages"]
    if value is None:
        raise refusal(path, key, 'missing; name the packages, e.g. packages = ["usda-nass"]')
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise refusal(path, key, 'must be a list of package names, e.g. ["usda-nass"]')
    if not value:
        raise refusal(path, key, "names no package")
    refs: list[PackageRef] = []
    for item in value:
        slug, colon, suffix = item.partition(":")
        if colon and f":{suffix}" != WRITE_SUFFIX:
            raise refusal(
                path, key, f"{item}: the one suffix is {WRITE_SUFFIX}, for a write server"
            )
        if not slug:
            raise refusal(path, key, f"{item}: names no package")
        refs.append(PackageRef(slug=slug, write=bool(colon)))
    if len({ref.write for ref in refs}) > 1:
        raise refusal(
            path,
            key,
            "mixes write servers (<slug>:write) and read servers; a group never mixes read "
            "and write tools (ADR-0026, decision 4), so give each its own endpoint",
        )
    seen: set[str] = set()
    for ref in refs:
        if ref.slug in seen:
            raise refusal(path, key, f"{ref.slug}: named twice")
        seen.add(ref.slug)
    return tuple(refs)


def _lists(path: Path, key: list[str], value: Any, slugs: list[str]) -> dict[str, frozenset[str]]:
    """``include`` or ``exclude``: per package slug, a list of task names."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise refusal(
            path,
            key,
            'must be a table of task names by package, e.g. { usda-nass = ["get_counts"] }',
        )
    lists: dict[str, frozenset[str]] = {}
    for slug, names in value.items():
        if slug not in slugs:
            raise refusal(
                path,
                [*key, slug],
                f"names no package of the endpoint; key a list by a package's slug, one of: "
                f"{', '.join(slugs)}",
            )
        if not isinstance(names, list) or not all(isinstance(n, str) and n for n in names):
            raise refusal(path, [*key, slug], 'must be a list of task names, e.g. ["get_counts"]')
        if not names:
            problem = (
                "includes no task; leave the package out instead"
                if key[-1] == "include"
                else "excludes no task; leave the list out instead"
            )
            raise refusal(path, [*key, slug], problem)
        twice = sorted({n for n in names if names.count(n) > 1})
        if twice:
            raise refusal(path, [*key, slug], f"{twice[0]}: named twice")
        lists[slug] = frozenset(names)
    return lists


def _auth(
    path: Path, here: list[str], table: dict[str, Any]
) -> tuple[Literal["bearer", "none"], str | None]:
    raw = table.get("auth", "bearer")
    auth: Literal["bearer", "none"]
    if raw == "bearer":
        auth = "bearer"
    elif raw == "none":
        auth = "none"
    else:
        raise refusal(path, [*here, "auth"], 'must be "bearer", the default, or "none"')
    token_env = table.get("token_env")
    key = [*here, "token_env"]
    example = f"XIPPIOS_MCP_{here[-1].upper().replace('-', '_')}_TOKEN"
    if token_env is None:
        if auth == "bearer":
            raise refusal(
                path,
                key,
                'missing; auth = "bearer", the default, needs the name of the environment '
                f'variable that holds the token, e.g. token_env = "{example}", or '
                'auth = "none"',
            )
        return auth, None
    if auth == "none":
        raise refusal(path, key, 'is given with auth = "none"; drop it or set auth = "bearer"')
    # The value is never repeated in a message: a token pasted here by mistake stays out
    # of the log (ADR-0005; conventions §7).
    if not isinstance(token_env, str) or not _TOKEN_VARIABLE.fullmatch(token_env):
        raise refusal(
            path,
            key,
            "must name an environment variable that ends in _TOKEN, upper-case letters, "
            f"digits and underscores starting with a letter, e.g. {example}, so the leak rule "
            "names it by its suffix (the value is not shown here, in case it is the token)",
        )
    return auth, token_env
