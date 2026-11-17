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
| Core | `xippios-core[mcp]~=0.3.0`, one minor (conventions §12), and `xippios-core[testing]~=0.3.0` in the dev group; `mcp`, `starlette` and `uvicorn`, which the host imports itself, with lower bounds at core's lock (conventions §11) |
| Sources | extras, not dependencies, each with a `>=` floor and no upper bound (sdk-core ADR-0026, decision 9): `cashctrl` (`xippios-cashctrl>=0.3.0`), `comtrade` (`>=0.2.0`), `eurostat` (`>=0.2.0`), `faostat` (`>=0.1.0`), `usda-esmis` (`>=0.2.0`), `usda-esr` (`>=0.2.0`), `usda-gats` (`>=0.2.0`), `usda-nass` (`>=0.2.0`), `usda-psd` (`>=0.3.0`); `all` is their union. `usda-wasde` joins later: its 0.1.1 bounds `xippios-usda-esmis` below 0.2, so the ten together do not resolve |

### What 0.1.0 reads of a package

By sdk-core ADR-0026, decision 8: `xippios.<pkg>.mcp.server`
(`xippios.<pkg>.mcp_write.server` for a write server) and its `server.name`, as the
packages have them today. For a server the host builds itself, a group or an endpoint
with a tool list, it reads `tasks.__all__`, `tasks_write.__all__` and `MCP_CAPS`, and
the slug it passes to `register_tasks` is the config's package key (the distribution
slug, equal to the package's `SOURCE`), never `server.name` (sdk-core ADR-0026,
amendment 2026-10-30, part (a)). The package contract of template v0.4.0, a public
`build(**options)` among it, is the host's interface from its first minor after core
0.4.0 and template v0.4.0, not from 0.2.0 (sdk-core ADR-0026, amendment 2026-10-30,
part (e); https://github.com/xippios/sdk-template/issues/81).

### The config

`load_config` reads a TOML file of `[endpoints.<name>]` tables (`packages`, `include` or
`exclude` per package by exact task name, `auth`, `token_env`, `allow_remote`) and checks
its shape; `build_all` checks what needs the packages and builds the servers. One package
without a list mounts the package's own server object; a group or a listed endpoint is an
`MCPServer` named `xippios-<endpoint>` that the host builds with `register_tasks` under
the package's slug, `MCP_CAPS` cut to the kept tasks, read and write never mixed. Every
refusal is core's `ConfigError` naming the file, the endpoint and the key; it repeats
slugs, task names and a package's `server.name`, but never the value of `token_env`,
`auth` or `allow_remote`, nor the value of an unknown key. A `ValueError` from
`register_tasks` is re-raised as `servers.BuildError`, a `ValueError`, with the file, the
endpoint and the package prefixed. `token_env` names a variable ending in `_TOKEN`,
which the host reads once, when `--http` starts. An optional `[http]` table names
`allowed_hosts` and `allowed_origins`.

### The transports and the bearer

`--stdio ENDPOINT` runs that endpoint's server on stdio, without auth and without reading
a token variable. `--http` builds one Starlette app (`app.build_app`): each endpoint's
`streamable_http_app` mounted at `/<name>` with the SDK's `/mcp` path, every session
manager entered in the app's one lifespan, served by uvicorn (`app.serve_http`). Before
it mounts, it refuses an `auth = "none"` write endpoint (core's `is_write_server`) on a
bind host beyond loopback without `allow_remote = true` (sdk-core ADR-0026, decision 5;
https://github.com/xippios/xippios-mcp/issues/6), and a package's own server on two
endpoints, since `streamable_http_app` replaces the server's one session manager
(https://github.com/xippios/xippios-mcp/issues/8). The loopback hosts are a private copy
of core's `_LOOPBACK_HOSTS`, `app._LOOPBACK_HOSTS`, until core carries the
`loopback_only` option (https://github.com/xippios/sdk-core/issues/167), as
sdk-google-mail carries one (sdk-core ADR-0023, decisions 2 and 4); a test keeps it equal
to core's. The `[http]` table becomes the SDK's `TransportSecuritySettings`; without it the
SDK's default for the bind host applies. A bearer endpoint is wrapped in `auth.Bearer`,
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

### Core internals

The host takes `register_tasks`, `is_write_server` and `quiet_request_logging` from
`xippios.core.mcp.server`, and `is_bulk_task` from `xippios.core._tasks`, outside core's
public surface (the five `__all__` lists of core's `__init__.py` files); each such import
carries a comment that says so, until core decides whether `xippios.core.mcp` exports
them (https://github.com/xippios/sdk-core/issues/170). Every `MCPServer` the host
constructs is followed by `quiet_request_logging()`, and the host calls it again before
serving: constructing an `MCPServer` sets root logging to `INFO`, and httpx logs every
request URL at `INFO`, which can carry a key or a tenant host (sdk-core ADR-0005).

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
  app.py           build_app: the loopback and mounted-once checks, the transport
                   security, one Mount per endpoint and the lifespan; serve_http (uvicorn)
  packages.py      known_slugs (the host's extras), import_path, load_package: a
                   package's tasks, server and caps, and the task-name checks
  servers.py       build_endpoint and build_all: the package's own server or one the
                   host builds (Built)
scripts/
  adr_index.py     writes docs/adr.md and docs/adr.json from the records in docs/adr/;
                   --check fails while either is stale
tests/
  conftest.py      enables xippios.core.testing.plugin, which keeps the run offline
  test_package.py  the host's own checks: the namespace level, py.typed, __version__, the
                   core bound, the extras' floors and their union, the entry point, the CLI
  test_config.py   load_config, the [http] table and every static refusal
  test_servers.py  the mount through mcp.Client in-process, the pass-through and the
                   refusals that need a package
  test_auth.py     the token variable and the bearer's answers
  test_app.py      MCP sessions over the app in-process (httpx2's ASGITransport inside
                   the lifespan), the Host check, the loopback and mounted-once
                   refusals, serve_http with uvicorn's Server.run stubbed
  test_cli.py      --stdio, --http (serve_http stubbed), the endpoint lines and exit
                   status 2; no test binds a port
docs/
  host.example.toml  the sample config, loaded and built by the tests
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
uv sync --all-extras               # the host with every source package
uv run pytest                      # offline; no tool reaches an upstream

uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
python3 scripts/adr_index.py --check   # the index matches the records in docs/adr/

docker build -t xippios-mcp .      # the image, as ci.yml's docker job builds it
```

The offline run is core's plugin's (sdk-core ADR-0013): it refuses the network in every
test not marked `live`, so nothing reaches an upstream though every source package is
installed.
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
- Never add a task, an endpoint wrapper or a fixture here, and never rename or re-map a
  package's tools: the host serves what the packages define (sdk-core ADR-0026,
  decision 1; sdk-core ADR-0003).
- Never construct an `MCPServer` without calling `quiet_request_logging()` right after
  it (sdk-core ADR-0005).
- Never add `src/xippios/__init__.py` (sdk-core ADR-0006).
- Never push a tag by hand: a release's tag comes from `publish.yml` alone
  (conventions §12).

## When something is unclear

Prefer the smallest change that satisfies the documents the README lists, state the
assumption in the pull request's description, and stop rather than guess at a package's
interface or the shape of the host's public API.
