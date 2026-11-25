# xippios-mcp — instructions for Claude Code

`xippios-mcp` is the self-hosted MCP host of the xippios SDK family: it serves the MCP
tools of the family's packages on one server, by endpoint and group (sdk-core ADR-0026).
It is a public package that is no source: no tasks, no `api/`, no fixtures and no
`docs/upstream/` snapshot (sdk-core ADR-0026, decision 1), and the one repository and
package of the family not named `sdk-*`. This file holds what an agent needs to work on
the host: the config, the mount, the transports, the bearer and the Docker image, its
layout, its commands and its rules. The documents it follows, sdk-core's conventions and
the host ADR among them, are listed under
[`## Documents` in the README](README.md#documents); read them before you change a file.
Decision 1 of the host ADR says which conventions bind the host, and an item of the
definition of done or the review checklist written for a source (tasks, wrappers,
fixtures, `docs/upstream/`) does not apply here (sdk-core ADR-0026, decision 1;
https://github.com/xippios/sdk-core/issues/172).

## What this package is

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
`token_env`, `auth` or `allow_remote`, nor the value of an unknown key. A `ValueError`
or a `TypeError` by which core refuses a declaration while a tool set is built, at the
package's import, by its `build()` or by the host's narrowed copy, is re-raised as
`servers.BuildError`, a `ValueError`, with the file, the endpoint and the package
prefixed. `token_env` names a variable ending in `_TOKEN`,
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
environment (https://github.com/xippios/xippios-mcp/issues/9). `ci.yml`'s `docker` job
builds it and runs `--help`; 0.1.0 pushes no image to a registry (sdk-core ADR-0026,
decision 2).

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
every request URL at `INFO`, which can carry a key or a tenant host (sdk-core ADR-0005).

## Layout

```
src/xippios/mcp/
  __init__.py      public surface: __version__
  py.typed         PEP 561 marker; consumers' mypy --strict needs it
  _version.py      __version__ from distribution metadata
  cli.py           the xippios-mcp entry point, main(argv): --config loaded and built,
                   then --stdio ENDPOINT, --http or the endpoint list; a refusal exits
                   with status 2
  config.py        load_config: the TOML file, HostConfig, Endpoint, PackageRef,
                   HttpConfig and the static checks
  auth.py          the bearer: token_digest (the token variable, read once) and Bearer,
                   the ASGI wrapper that answers 401
  app.py           build_app: the loopback check, the transport security, one Mount per
                   endpoint and the lifespan; serve_http (uvicorn)
  packages.py      import_path, load_package: a package's tool set by its build(), and
                   Package.narrowed, the copy under a tool list
  servers.py       build_endpoint and build_all: a server of its own for each endpoint,
                   one package's or a group's (Built)
scripts/
  adr_index.py     writes docs/adr.md and docs/adr.json from the records in docs/adr/;
                   --check fails while either is stale
tests/
  conftest.py      enables xippios.core.testing.plugin, which keeps the run offline
  example/         the invented sources the tests serve, xippios.example and the nested
                   xippios.example.api, on pytest's pythonpath and mypy's path; they ship
                   in no distribution
  test_package.py  the host's own checks: the namespace level, py.typed, __version__, the
                   core bound, the extras' floors and their union, the entry point, the
                   CLI, and core imported by its pinned lists alone
  test_config.py   load_config, the [http] table and every static refusal
  test_servers.py  the tool sets read and the servers built, through mcp.Client
                   in-process, the pass-through and the refusals that need a package
  test_auth.py     the token variable and the bearer's answers
  test_app.py      MCP sessions over the app in-process (httpx2's ASGITransport inside
                   the lifespan), the Host check, the loopback refusals, serve_http with
                   uvicorn's Server.run stubbed
  test_cli.py      --stdio, --http (serve_http stubbed), the endpoint lines and exit
                   status 2; no test binds a port
docs/
  host.example.toml  the sample config, loaded by the tests; its build needs the real
                   sources it names
  adr/             this package's design decisions, one NNNN-<slug>.md record each, laid
                   out in its README.md
  adr.md           the index of the decisions, written by scripts/adr_index.py, never by
                   hand
  adr.json         the same index, for machines
  reports/         dated reports, the evidence a decision cites, laid out in its
                   README.md
changelog/         the next release's changelog entries, one fragment per change, laid
                   out in its README.md
CHANGELOG.md       the releases, each section assembled from the fragments
Dockerfile         the image: python:3.12-slim and uv by digest, `uv sync --locked` of
                   `all`, the non-root user xippios as USER 10001:10001, --http on
                   0.0.0.0:8000
.dockerignore      keeps .git, .venv, tests, .worktrees, the caches and any .env or
                   .envrc out of the build context
.github/workflows/ ci.yml (the required ci check: the test matrix with the changelog and
                   fixture-size steps, and the docker job, which builds the image),
                   publish.yml (the release train: tag, build, PyPI), organization.yml
                   (the organization's checks from xippios/.github: conventions, a review
                   of a pull request against the documents the README lists, and
                   adr-index, which runs scripts/adr_index.py --check)
.claude/commands/  release-prep
```

Core's family check (`xippios.core.testing.family`) imports a package's `_client` and
`tasks`, which the host does not have, so `tests/test_package.py` carries the checks
that apply here.

## Commands

```bash
uv sync --all-extras               # the host, its dev tools and every source of `all`
uv run pytest                      # offline, on the invented sources of tests/example

uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
python3 scripts/adr_index.py --check   # the index matches the records in docs/adr/

docker build -t xippios-mcp .      # the image, as ci.yml's docker job builds it
```

The offline run is core's plugin's (sdk-core ADR-0013): it refuses the network in every
test not marked `live`, so nothing reaches an upstream, and the tests serve the invented
sources of `tests/example`, which send no request, so they wait for no real source
(ADR-0001, decision 6).
The host has no live tests and no `live.yml`: the packages' own live runs cover their
tasks.

## Scaffolded by hand

No template renders the host, since sdk-template renders sources only: it was scaffolded
by hand from sdk-template v0.3.0 on 2026-10-29 and brought to v0.3.4 by hand on
2026-11-17 (sdk-core ADR-0026, decision 1). Against v0.3.4:

- Copied byte for byte: `.github/workflows/organization.yml`,
  `.github/workflows/publish.yml`, `.github/PULL_REQUEST_TEMPLATE.md`,
  `.pre-commit-config.yaml`, `.secrets.baseline`, `.gitignore`, `.python-version`,
  `.claude/settings.json`, `docs/adr/README.md`, `docs/reports/README.md`,
  `changelog/README.md`, `scripts/adr_index.py`, `LICENSE` and
  `src/xippios/mcp/py.typed`.
- Ported by hand: `pyproject.toml`, `src/xippios/mcp/__init__.py` and `_version.py`,
  `tests/conftest.py`, `README.md` with its `## Documents`, `CHANGELOG.md`, `CLAUDE.md`,
  `.claude/commands/release-prep.md` and `.github/CODEOWNERS`.
- Changed: `.github/workflows/ci.yml` is v0.3.4's but in three places, which a port of
  a template release's `ci.yml` keeps (https://github.com/xippios/xippios-mcp/issues/9):
  the `docker` job, which builds the image and runs `--help`; the `ci` aggregator's
  `needs: [test, docker]`, with its check of `needs.docker.result` beside the test
  matrix's; and the aggregator's step, renamed "Require the whole matrix and the image
  build to pass".
- New, the host's own: the modules of `src/xippios/mcp/` but `__init__.py` and
  `_version.py`, the tests but `conftest.py`, `docs/host.example.toml`, `Dockerfile` and
  `.dockerignore`.
- Not taken: `live.yml`, `siblings.yml`, `.gitattributes`, `.copier-answers.yml`, the
  commands but `release-prep`, the scripts but `adr_index.py`, `docs/upstream/`, the
  package's modules but `__init__.py` and `_version.py`, and the family, task and live
  tests.

There is no copier answers file, so `copier update` does not run here. A template release
is ported by hand in a pull request of its own: each file above against the tag's render,
and the Hand-apply notes of sdk-template's
[CHANGELOG](https://github.com/xippios/sdk-template/blob/main/CHANGELOG.md) since v0.3.4,
until the host flavour of the scaffold exists
(https://github.com/xippios/sdk-template/issues/81).

## Workflow rules

- A change brings its tests, written before the code, and passes the checks above; its
  changelog entry is a fragment under `changelog/`, one file holding its bullet, as
  `changelog/README.md` lays it out (conventions §12). Commit subjects follow
  Conventional Commits (conventions §13): the rule binds a pull request's own commits,
  not the commit that lands the pull request on `main`, whose subject GitHub writes.
- A change reaches `main` in a pull request that meets sdk-core's definition of done as
  far as it binds the host, and states its assumptions and the live calls it spent:
  `none`, since the host has no live tests.
- A release is a pull request of its own, which `/release-prep` prepares (the release
  train, conventions §12).
- A convention that seems wrong is followed anyway and said in the pull request; changing
  it is a change of sdk-core's `docs/conventions.md` with an ADR.

## Never

- Never read or print `.envrc`, `.env`, or any variable ending in `_API_KEY`,
  `_REFRESH_TOKEN` or `_SECRET`.
- Never read, print or write the variable a config's `token_env` names, the bearer of an
  endpoint; its name ends in `_TOKEN`, which `load_config` enforces
  (https://github.com/xippios/xippios-mcp/issues/7). The host's code reads it in one
  place, `auth.token_digest`, once when `--http` starts, and keeps its digest only; tests
  set a test value of their own with `monkeypatch.setenv`, its literal marked
  `# pragma: allowlist secret`.
- Never log, print or echo a token or the `Authorization` header: the bearer strips the
  header before the endpoint's app, and a refusal names the variable, never its value.
- Never write a key, a token or another credential into a file or a commit: the secrets
  stay in the environment (conventions §7; sdk-core ADR-0026, decision 2).
- Never put a config, a key or a token into the image: the operator mounts the config
  and passes every variable by name (https://github.com/xippios/xippios-mcp/issues/9).
- Never add a task the host serves, an endpoint wrapper or a fixture here, and never
  rename or re-map a package's tools: the host serves what the packages define (sdk-core
  ADR-0026, decision 1; sdk-core ADR-0003). The invented sources of `tests/example` are
  the tests' stand-ins for a source, never served by the host's package.
- Never construct an `MCPServer` without calling `quiet_request_logging()` right after
  it (sdk-core ADR-0005).
- Never add `src/xippios/__init__.py` (sdk-core ADR-0006).
- Never push a tag by hand: a release's tag comes from `publish.yml` alone
  (conventions §12).

## When something is unclear

Prefer the smallest change that satisfies the documents the README lists, state the
assumption in the pull request's description, and stop rather than guess at a package's
interface or the shape of the host's public API.
