# xippios-mcp — instructions for Claude Code

`xippios-mcp` is the self-hosted MCP host of the xippios SDK family: it serves the MCP
tools of the family's packages on one server, by endpoint and group (ADR-0026). It is a
public package that is no source: no tasks, no `api/`, no fixtures and no
`docs/upstream/` snapshot (ADR-0026, decision 1), and the one repository, package and
session of the family not named `sdk-*`. The config, the transports, the bearer and the
image come in the next steps.

## What this package is

| | |
| --- | --- |
| Repository | `xippios/xippios-mcp`; PyPI `xippios-mcp`; session `xippios-mcp` |
| Import path | `xippios.mcp`; `src/xippios/` is a PEP 420 namespace package (conventions §1) |
| Entry point | `xippios-mcp = "xippios.mcp.cli:main"`, `--config <path>` required |
| Core | `xippios-core[mcp]~=0.3.0`, one minor (conventions §12), and `xippios-core[testing]~=0.3.0` in the dev group; `mcp`, `starlette` and `uvicorn`, which the host imports itself, with lower bounds at core's lock (conventions §11) |
| Sources | extras, not dependencies, each with a `>=` floor and no upper bound (ADR-0026, decision 9): `cashctrl` (`xippios-cashctrl>=0.3.0`), `comtrade` (`>=0.2.0`), `eurostat` (`>=0.2.0`), `faostat` (`>=0.1.0`), `usda-esmis` (`>=0.2.0`), `usda-esr` (`>=0.2.0`), `usda-gats` (`>=0.2.0`), `usda-nass` (`>=0.2.0`), `usda-psd` (`>=0.3.0`); `all` is their union. `usda-wasde` joins later (Johannes, 2026-10-29): its 0.1.1 bounds `xippios-usda-esmis` below 0.2, so the ten together do not resolve |

### What 0.1.0 reads of a package

By ADR-0026, decision 8: `xippios.<pkg>.mcp.server` (`xippios.<pkg>.mcp_write.server`
for a write server) and its `server.name`, as the packages have them today. For a
server the host builds itself, a group or an endpoint with a tool list, it reads
`tasks.__all__`, `tasks_write.__all__` and `MCP_CAPS` (Johannes, 2026-10-29, question
2; queue row 306). The package contract of template v0.4.0, a public `build(**options)`
among it, is the host's 0.2.0 interface (queue row 284).

### Core internals

The host takes `register_tasks`, `is_write_server` and `quiet_request_logging` from
`xippios.core.mcp.server`, outside core's public surface (the five `__all__` lists of
core's `__init__.py` files), and each such import carries a comment naming queue row
297, where core 0.4.0 decides whether `xippios.core.mcp` exports them. Every `MCPServer`
the host constructs is followed by `quiet_request_logging()`, and the host calls it
again before serving: constructing an `MCPServer` sets root logging to `INFO`, and httpx
logs every request URL at `INFO`, which can carry a key or a tenant host (ADR-0005).

## Layout

```
src/xippios/mcp/
  __init__.py      public surface: __version__
  py.typed         PEP 561 marker; consumers' mypy --strict needs it
  _version.py      __version__ from distribution metadata
  cli.py           the xippios-mcp entry point, main(argv); --config stops with exit
                   status 2 until the config loader lands
tests/
  conftest.py      enables xippios.core.testing.plugin, which keeps the run offline
  test_package.py  the host's own checks: the namespace level, py.typed, __version__, the
                   core bound, the extras' floors and their union, the entry point, the CLI
.github/workflows/ ci.yml (the required ci check, with the CHANGELOG step), publish.yml
                   (the release train: tag, build, PyPI), gates.yml (the merge gates as
                   jobs, off until GATES_CALLER is 1)
.claude/commands/  release-prep
```

Core's family check (`xippios.core.testing.family`) imports a package's `_client` and
`tasks`, which the host does not have, so `tests/test_package.py` carries the checks
that apply here.

## Read first, in this order

1. ADR-0026, the host ADR: decision 1 says which conventions bind the host,
   https://github.com/xippios/sdk-core/blob/main/docs/adr/0026-the-host-xippios-mcp.md
2. The family conventions and ADRs:
   https://github.com/xippios/sdk-core/blob/main/docs/conventions.md and
   https://github.com/xippios/sdk-core/tree/main/docs/adr
3. What a PR must satisfy,
   https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and what the
   reviewer checks it against,
   https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md; the items
   written for a source are not applicable here (ADR-0026, decision 1; queue row 302).
4. This file. The workspace's own `CLAUDE.md` applies as well when you work from it.

## Commands

```bash
uv sync --all-extras               # the host with every source package
uv run pytest                      # offline; no test calls a tool

uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pre-commit run --all-files
```

The offline run is core's plugin's (ADR-0013): it refuses the network in every test not
marked `live`, so nothing reaches an upstream though every source package is installed.
The host has no live tests and no `live.yml`: the packages' own live runs cover their
tasks.

## Scaffolded by hand

The host was scaffolded by hand from template v0.3.0 on 2026-10-29 (D109 (2); ADR-0026,
decision 1), since the template renders sources only:

- Copied byte for byte: `.github/workflows/ci.yml`, `.github/workflows/gates.yml`,
  `.github/workflows/publish.yml`, `.github/PULL_REQUEST_TEMPLATE.md`,
  `.pre-commit-config.yaml`, `.secrets.baseline`, `.gitignore`, `.python-version` and
  `.claude/settings.json`.
- Ported by hand: `pyproject.toml`, `src/xippios/mcp/__init__.py` and `_version.py`,
  `tests/conftest.py`, `README.md`, `CHANGELOG.md`, `.claude/commands/release-prep.md`,
  and the family rules of `.claude/family.md` this file keeps.
- Not taken: `live.yml`, `siblings.yml`, `.gitattributes`, `.copier-answers.yml`,
  `.claude/family.md`, the commands but `release-prep`, `scripts/`, `docs/upstream/`,
  the package's modules but `__init__.py` and `_version.py`, and the family, task and
  live tests. `LICENSE` is the repository's own.

There is no copier answers file, so `copier update` does not run here: a template
release is ported by hand until the host flavour of the scaffold (queue row 284) exists.

## Workflow rules

- Branch from `main` as `feature/<topic>`, `fix/<topic>`, `chore/<topic>` or `docs/<topic>`.
  Never commit to `main`.
- Commit small, with Conventional Commits messages (`feat(cli): add --config`).
- Open the PR with `gh pr create`; the body is the definition-of-done checklist from
  `.github/PULL_REQUEST_TEMPLATE.md`, ticked honestly: an item written for a source
  (tasks, wrappers, fixtures, `docs/upstream/`) is ticked as not applicable with
  ADR-0026, decision 1, as its reason (queue row 302). The body lists assumptions and
  open questions, counts the live calls the PR spent (keyed calls by number; `none` is a
  count) and ends, after the checklist, with a `## Decisions taken` block: one line per
  decision the session made, each backed by a convention, an ADR, a coordination rule, a
  dated decision of Johannes's or `gap, row N`.
- Every PR but a release or Dependabot's adds an entry under Unreleased in
  `CHANGELOG.md`; `ci.yml` fails without one (conventions §12).
- Releases follow the release train (conventions §12): `/release-prep` opens a release
  PR that changes no file but `pyproject.toml`, `uv.lock`, `CHANGELOG.md`, `README.md`,
  `CLAUDE.md` and `docs/handover.md`. Its merge runs `publish.yml`, which tags the
  version on the merge commit, and Johannes approves the `pypi` run.
- If a convention seems wrong, say so in the PR and follow it anyway; changing it is a
  PR against `sdk-core/docs/conventions.md` plus an ADR.

## Never

- Never read or print `.envrc`, `.env`, or any variable ending in `_API_KEY`,
  `_REFRESH_TOKEN` or `_SECRET`.
- Never write a key or a token into a file or a commit: the secrets stay in the
  environment (conventions §7; ADR-0026, decision 2).
- Never add a task, an endpoint wrapper or a fixture here, and never rename or re-map a
  package's tools: the host serves what the packages define (ADR-0026, decision 1;
  ADR-0003).
- Never construct an `MCPServer` without calling `quiet_request_logging()` right after
  it (ADR-0005).
- Never add `src/xippios/__init__.py`.
- Never tag, merge, release, force-push, or touch `gh secret`: a release PR's merge tags
  through `publish.yml`, and Johannes approves the `pypi` run. The one exception is
  enabling auto-merge on a `chore/template-update*` or `chore/release-*` PR whose merge
  class is `auto`, after the reviewer's `ready` (ADR-0018, amendment (e)).

## When something is unclear

Prefer the smallest change that satisfies the documents above, state the assumption in
the PR description, and stop rather than guess at a package's interface or the host's
public API shape.
