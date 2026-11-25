# xippios-mcp — instructions for Claude Code

`xippios-mcp` is the self-hosted MCP host for the xippios SDKs, a package of the xippios SDK
family, built on `xippios-core`. This file holds what an agent needs to work on the package:
its layout, its commands and what only it knows. The documents it follows, sdk-core's
conventions and the host ADR among them, are listed under
[`## Documents` in the README](README.md#documents); read them before you change a file. The
rules that no change breaks stand in `.claude/rules/never.md`, which Claude Code loads with
this file.

## Layout

What this package adds to the family's tree, and its import path, stand in `docs/layout.md`,
imported here:

@docs/layout.md

## Commands

```bash
uv sync --all-extras
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
python3 -I scripts/adr_index.py --check   # the index matches the records in docs/adr/

docker build -t xippios-mcp .      # the image, as docker.yml builds it
```

## Template updates

This repository is generated from sdk-template, at the tag `.copier-answers.yml` records. A
template release reaches it in a pull request of its own, with
`uvx --from 'copier>=9.19' copier update --defaults --vcs-ref=<tag>` (conventions §15). The
update never overwrites a file this package fills, those that `_skip_if_exists` lists in
sdk-template's [`copier.yml`](https://github.com/xippios/sdk-template/blob/main/copier.yml),
and sdk-template's
[CHANGELOG](https://github.com/xippios/sdk-template/blob/main/CHANGELOG.md) says, per
release, what to port into those by hand in the same pull request.

The update writes every other file it renders again, since they are the template's,
`.claude/rules/never.md` among them. This package keeps no text of its own in them: its own
words go into a file it fills. `pyproject.toml` is one it fills, its manifest once rendered,
so no update changes its dependencies, its scripts or its bound of `xippios-core`, which an
adoption of a core minor raises there by hand.

## What only this package knows

The host serves the MCP tools of the family's packages on one server, by endpoint and group
(sdk-core ADR-0026). It is a public package that is no source: no tasks, no `api/`, no
fixtures and no `docs/upstream/` snapshot (sdk-core ADR-0026, decision 1), and the one
repository and package of the family not named `sdk-*`. Decision 1 of the host ADR says which
conventions bind the host, and an item of the definition of done or the review checklist
written for a source (tasks, wrappers, fixtures, `docs/upstream/`) does not apply here
(sdk-core ADR-0026, decision 1; https://github.com/xippios/sdk-core/issues/172).

### What this package is

| | |
| --- | --- |
| Repository | `xippios/xippios-mcp`; PyPI `xippios-mcp` |
| Import path | `xippios.mcp`; `src/xippios/` is a PEP 420 namespace package (conventions §1) |
| Entry point | `xippios-mcp = "xippios.mcp.cli:main"`, `--config <path>` required; `--stdio ENDPOINT` serves one endpoint on stdio, `--http` (with `--host`, default `127.0.0.1`, and `--port`, default 8000) every endpoint at `/<name>/mcp`; without either it loads the config, builds every endpoint and prints one line per endpoint; a refusal exits with status 2 |
| Core | `xippios-core[mcp]~=0.5.0`, one minor (conventions §12), and `xippios-core[testing]~=0.5.0` in the dev group; `mcp`, `starlette` and `uvicorn`, which the host imports itself, with lower bounds at core's lock (conventions §11) |
| Sources | extras, not dependencies, each with a `>=` floor at the source's first release on core 0.5 and no upper bound (sdk-core ADR-0026, decision 9), and `all` their union. No source has released on core 0.5 yet, so the manifest names none and `all` is empty; a source that is installed is served all the same (ADR-0001, decision 2) |

### What the host reads of a package

Its tool set, by the package contract (ADR-0001; sdk-core ADR-0063, decision 4): the
host imports `xippios.<slug>`, each hyphen of the slug a dot, and calls
`<path>.mcp.build()`, or `<path>.mcp_write.build()` for `<slug>:write`, without
arguments. The `ToolSet` it returns holds the package's tools alone, its bulk tasks left
out, named `tool_name(tool_set.source, fn)` for each `fn` of `tool_set.tasks`, with
their caps, the package's instructions and version, its option hooks, and `read_only`
and `loopback_only`. The host reads no module-level `server`, no `tasks.__all__`, no
`MCP_CAPS` and no bulk task. A package is known by its import path, not by the host's
extras: a slug of conventions §1's form that is installed is served, and the extras say
what `all` installs and what the hint for a missing package names (`packages.py`).

### The config

`load_config` reads a TOML file of `[endpoints.<name>]` tables (`packages`, `include` or
`exclude` per package by exact task name, `auth`, `token_env`, `allow_remote`) and checks
its shape, a slug's form among it; `build_all` checks what needs the packages and builds
the servers, a server of its own for every endpoint (ADR-0001, decision 3). One package
without a list is `build_server(tool_set)`, the server its entry point serves; a group or
a listed endpoint is an `MCPServer` named `xippios-<endpoint>` on which `register_tasks`
registers each package's tool set, narrowed by `Package.narrowed`, a
`dataclasses.replace` copy with its caps cut to the kept tasks, read and write never
mixed. Every refusal is core's `ConfigError` naming the file, the endpoint and the key;
it repeats slugs, task names and a package's module names, but never the value of
`token_env`, `auth` or `allow_remote`, nor the value of an unknown key. Every
`ValueError` and `TypeError` raised at a package's import, by its `build()` or by the
host's narrowed copy, core's refusal of a declaration and a package's own error alike, is
re-raised as `servers.BuildError`, a `ValueError`, with the file, the endpoint, the
package and the error's class prefixed. `token_env` names a variable ending in `_TOKEN`,
which the host reads once, when `--http` starts. An optional `[http]` table names
`allowed_hosts` and `allowed_origins`.

### The transports and the bearer

`--stdio ENDPOINT` runs that endpoint's server on stdio, without auth and without reading
a token variable. `--http` builds one Starlette app (`app.build_app`): each endpoint's
`streamable_http_app` mounted at `/<name>` with the SDK's `/mcp` path, every session
manager entered in the app's one lifespan, served by uvicorn (`app.serve_http`). Every
endpoint has a server of its own, so `streamable_http_app`, which replaces a server's one
session manager, never meets a server twice. Before it mounts, it refuses an
`auth = "none"` endpoint held to loopback, `Built.held`, true when a tool set of it writes
or is `loopback_only`, on a bind host outside core's `LOOPBACK_HOSTS` without
`allow_remote = true` (sdk-core ADR-0026, decision 5; ADR-0063, decision 5;
https://github.com/xippios/xippios-mcp/issues/6). The `[http]` table becomes the SDK's
`TransportSecuritySettings`; without it the SDK's default for the bind host applies. A bearer endpoint is wrapped in `auth.Bearer`,
a pure ASGI wrapper that holds the token's SHA-256 digest (`auth.token_digest` reads the
variable once), compares with `hmac.compare_digest`, answers 401 with `WWW-Authenticate:
Bearer realm="xippios-mcp"` (`error="invalid_token"` for a wrong token) and no
`resource_metadata` (sdk-core ADR-0026, decision 10), and strips the `Authorization`
header before the endpoint's app (https://github.com/xippios/xippios-mcp/issues/8).

### The image

`Dockerfile` builds in two stages on `python:3.12-slim`, pinned by digest with the tag in
a comment above it, and takes uv from its release image `ghcr.io/astral-sh/uv`, pinned
the same way; both are bumped deliberately (conventions §13's pinning rule, read for
images; https://github.com/xippios/xippios-mcp/issues/9). The builder installs this
checkout with `uv sync --locked --no-dev --extra all --no-editable`, the tested set, and
the final stage carries the venv alone: it runs as the non-root user `xippios`, uid and
gid 10001, which `USER 10001:10001` names by number so that a Kubernetes `runAsNonRoot`
check can verify it without a `runAsUser`, reads `/etc/xippios-mcp/host.toml`, which
the operator mounts, serves `--http` on `0.0.0.0:8000` and takes every token from the
environment (https://github.com/xippios/xippios-mcp/issues/9). `docker.yml`, the host's
own workflow beside the rendered ones, which hold no job of one repository (sdk-template
ADR-0003, decision 8), builds it on every pull request and runs `--help`; 0.1.0 pushes no
image to a registry (sdk-core ADR-0026, decision 2).

### Core's names

The host takes every name of core from one of core's six pinned lists, the `__all__` of
the six `__init__.py` files of `xippios.core`, by that list's module path, and no private
name: `ToolSet`, `build_server`, `register_tasks`, `LOOPBACK_HOSTS` and
`quiet_request_logging` from `xippios.core.mcp`, and `ConfigError` and `tool_name` from
`xippios.core` (sdk-core ADR-0063, decision 4). `tests/test_package.py` reads every
import of the package, its tests and its scripts with `ast` and fails on any other
(ADR-0001, decision 5). Every `MCPServer` the host constructs is followed by
`quiet_request_logging()`, `build_server` calls it itself, and the host calls it again
before serving: constructing an `MCPServer` sets root logging to `INFO`, and httpx logs
every request URL at `INFO`, which can carry a key or a tenant host (sdk-core ADR-0030).

### The tests

The tests serve the invented sources of `tests/example`, which send no request, so they
wait for no real source (ADR-0001, decision 6). The host has no live tests and no
`live.yml`: the packages' own live runs cover their tasks, so a pull request of the host
counts its live calls as `none`.

### What the host never does

- Never read, print or write the variable a config's `token_env` names, the bearer of an
  endpoint; its name ends in `_TOKEN`, which `load_config` enforces
  (https://github.com/xippios/xippios-mcp/issues/7). The host's code reads it in one
  place, `auth.token_digest`, once when `--http` starts, and keeps its digest only; tests
  set a test value of their own with `monkeypatch.setenv`, its literal marked
  `# pragma: allowlist secret`.
- Never log, print or echo a token or the `Authorization` header: the bearer strips the
  header before the endpoint's app, and a refusal names the variable, never its value.
- Never put a config, a key or a token into the image: the operator mounts the config
  and passes every variable by name (https://github.com/xippios/xippios-mcp/issues/9).
- Never add a task the host serves, an endpoint wrapper or a fixture here, and never
  rename or re-map a package's tools: the host serves what the packages define (sdk-core
  ADR-0026, decision 1; sdk-core ADR-0028). The invented sources of `tests/example` are
  the tests' stand-ins for a source, never served by the host's package.
- Never construct an `MCPServer` without calling `quiet_request_logging()` right after
  it (sdk-core ADR-0005).
