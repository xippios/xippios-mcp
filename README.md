# xippios-mcp

The self-hosted MCP host of the [xippios SDK family](https://github.com/xippios). It
serves the MCP tools of the family's packages from one process, by endpoint and group:
an endpoint serves a package's tool set, read or write, as the package's own server
does, and a group combines several packages' tools on one endpoint, never read and write
tools together. It runs on stdio
locally and on streamable HTTP on a server, each endpoint with its own auth, a bearer
token by default; the secrets stay in the environment, never in the config file.

`xippios-mcp --config <path>` checks a config, builds every endpoint's server and lists
the endpoints; `--stdio <endpoint>` serves one endpoint on stdio, and `--http` serves
every endpoint over streamable HTTP, each with its bearer (see Serving). A Docker image,
built from this repository, serves them from a container (see Docker).

## Install

```bash
uv add 'xippios-mcp[faostat]'     # the host and a package it serves, by its extra
uv add 'xippios-mcp[all]'         # the host and every package of the table below
```

## Packages

The host runs on `xippios-core` 0.5 and serves every source package of the family that
is installed beside it and released on that core minor: a package is named by its slug,
`usda-nass`, and imported as `xippios.usda.nass`. Its extras are the three sources that
proved core 0.5.0 with the host, where 0.1.0 named nine on core 0.3, and the next release
lists all twelve sources of the family. Each extra takes a lower bound alone, at the
source's first release on core 0.5, so the host installs each at its latest release on
that minor, and `all` installs the three.

| Extra | Distribution | Lower bound | Servers | Tools |
| --- | --- | --- | --- | --- |
| `cashctrl` | `xippios-cashctrl` | `>=0.6.0` | read and write | 25 read, 14 write |
| `faostat` | `xippios-faostat` | `>=0.3.0` | read | 7 |
| `usda-esr` | `xippios-usda-esr` | `>=0.4.0` | read | 7 |

The tools of a package are those of its tool set, what its `mcp.build()` returns
(`mcp_write.build()` for a write server): its tasks less its `BULK_TASKS`, which are
Python-only, each with its own result cap, counted at the version of the lower bound; a
later release may add tools. Another source released on core 0.5 is served once it is
installed beside the host, with no extra of its own. `xippios-usda-esr` brings
`xippios-usda-fas`, the code that the sources of USDA's Foreign Agricultural Service share,
as its dependency: it runs no server, so the host serves nothing of it, and an endpoint
that names `usda-fas` is refused.

Before their releases the host served the three from their commits on core 0.5.0's
candidate, as
[the report of 2026-11-25](https://github.com/xippios/xippios-mcp/blob/main/docs/reports/2026-11-25-the-host-serves-the-three-proving-sources.md)
records, and `tests/test_sources.py` serves each of them from the releases that `uv.lock`
pins.

### The ceilings of usda-nass and usda-gats

`--split-years` of `xippios-usda-nass-mcp` and `--series-months` of
`xippios-usda-gats-mcp` are options of those packages' own entry points, and each
package's tool set carries the hooks that apply them. The host applies every package's
hooks with the defaults that its entry point parses from an empty command line, so it
serves the ceilings that the entry points serve without options: a split
`usda_nass_get_data` spans up to 5 years, at up to two keyed calls a year, where the
package's Python API spans 20, and `usda_gats_get_census_export_series`,
`usda_gats_get_census_import_series` and `usda_gats_get_census_reexport_series` span up
to 24 months, at one call a month, where it spans 60; a longer range is refused. As
with the entry point, the ceiling holds for the whole process, every endpoint that
serves the package included. The config sets no option of a package: a higher ceiling
is the package's own entry point's, run with its option.

## Configuration

The host reads one TOML file that names its endpoints. Each `[endpoints.<name>]` table
is one endpoint, which the HTTP transport serves at `/<name>/mcp`:

```toml
[endpoints.agriculture]                        # served at /agriculture/mcp
packages = ["faostat", "usda-esr"]
exclude = { faostat = ["list_bulk_datasets"] } # or include = { ... }; exact task names
auth = "bearer"                                # the default; or "none"
token_env = "XIPPIOS_MCP_AGRICULTURE_TOKEN"    # a name ending in _TOKEN, never a value
allow_remote = false                           # the default

[endpoints.accounting-write]
packages = ["cashctrl:write"]
auth = "none"
```

- An endpoint that names one package serves the server of that package's tool set,
  `xippios.<package>.mcp.build()`, or `mcp_write.build()` for `<slug>:write`, as the
  package's own entry point serves it, with its instructions, version and result caps:
  named `xippios-<slug>`, or `xippios-<endpoint>` with an `include` or `exclude` list,
  which narrows its tools. Each endpoint has a server of its own, so one package may
  serve several endpoints.
- A group, several packages, is a server the host builds, named `xippios-<endpoint>`:
  each package's tools under their own names (`faostat_get_data`), with the package's
  result caps for the tools it keeps. Its instructions open with one sentence naming its
  packages and their tool counts, then give each package's own instructions under a
  heading of its slug, `## faostat`.
- An `include` or `exclude` list narrows a package's tools and leaves its instructions
  whole, on an endpoint of one package and in a group alike, so they may name a tool that
  the endpoint does not serve, a listing tool they say to call first, say. The host does
  not cut them: a package's instructions are its own prose, which the host could change
  only by writing for the package, and the host serves what a package defines, its tools
  under their names and its text as it stands.
- Every endpoint applies its packages' option hooks with the defaults of their entry
  points, as those run without options (see The ceilings of usda-nass and usda-gats).
- Read and write never mix: an endpoint's packages are all `<slug>:write` or none, and
  the host refuses a group that mixes them.
- `include` and `exclude` are keyed by package slug and name exact task names, a task
  function's `__name__` (`list_bulk_datasets`, not `faostat_list_bulk_datasets`); a
  package takes one of the two, and an empty list is refused. A name that is no tool of
  the package is refused, a task in the package's `BULK_TASKS` among them, since a bulk
  task is Python-only and no tool.
- A package's slug is lower-case letters and digits, its words joined by hyphens; one
  that is not installed is refused with the package to install.
- `auth` is `"bearer"` by default, or `"none"`. With the bearer, `token_env` names the
  environment variable that holds the token, a name ending in `_TOKEN`
  (`XIPPIOS_MCP_<ENDPOINT>_TOKEN`), and the token itself stays in the environment, never
  in the file. The host reads the variable once, when `--http` starts, and never on
  stdio or when it lists. `allow_remote` is `false` by default; it lets an `auth =
  "none"` endpoint that is held to loopback serve beyond it (see The loopback rule).
- An optional `[http]` table names the `Host` and `Origin` values the HTTP transport
  accepts behind a reverse proxy (see Behind a reverse proxy).

Check a config before serving it:

```bash
xippios-mcp --config host.toml
```

It loads the file, builds every endpoint and prints one line per endpoint, with the
tool count of the packages installed; for
[`docs/host.example.toml`](https://github.com/xippios/xippios-mcp/blob/main/docs/host.example.toml),
the sample above:

```text
agriculture: read, <n> tools of faostat, usda-esr
accounting-write: write, <n> tools of cashctrl
```

A key, package or task the host refuses stops it with exit status 2 and a message that
names the file, the endpoint and the key. A package whose tool set core refuses, or
whose option hook refuses its defaults, stops it the same way, the message naming the
file, the endpoint and the package: the list builds every endpoint as it is served, the
hooks applied. The list runs no loopback check of Serving, which needs `--http` and its
`--host`.

The host binds no tenant: a multi-tenant package, cashctrl say, is served for every
tenant its environment declares, and each of its tools takes the tenant as an argument,
where its own entry point's `--org` binds one.

## Serving

### stdio

```bash
xippios-mcp --config host.toml --stdio agriculture
```

serves the one endpoint `agriculture` on stdio, for an MCP client that starts the host
as its own process. stdio has no auth: the host reads no token variable, and an
endpoint's `auth`, `token_env` and `allow_remote` apply to HTTP only. In Claude Code:

```bash
claude mcp add agriculture -- xippios-mcp --config host.toml --stdio agriculture
```

with the config's absolute path in place of `host.toml` when Claude Code runs in another
directory.

### Streamable HTTP

```bash
xippios-mcp --config host.toml --http --host 127.0.0.1 --port 8000
```

serves every endpoint of the config from one process, each at
`http://127.0.0.1:8000/<name>/mcp`: `http://127.0.0.1:8000/agriculture/mcp` for the
sample. `--host` defaults to `127.0.0.1` and `--port` to 8000; both need `--http`, and
`--http` and `--stdio` exclude each other. Before it serves, the host reads each bearer
endpoint's token and applies the checks below; a refusal exits with status 2 and serves
nothing.

### The bearer

An endpoint with `auth = "bearer"` answers a request without the token with `401` and
`WWW-Authenticate: Bearer realm="xippios-mcp"`, and one with a wrong token with
`error="invalid_token"` added; such a request never reaches the endpoint. The token is
the value of the variable `token_env` names, read once when `--http` starts: an unset or
empty variable stops the host with exit status 2, and so does a value with leading or
trailing whitespace, which no token a client sends can match. The host keeps the token's
SHA-256 digest only, compares in constant time, and never logs the token or the
`Authorization` header. A random token will do, `openssl rand -hex 32` for instance, set
in the environment of the host and of the client.

In Claude Code:

```bash
claude mcp add --transport http agriculture http://127.0.0.1:8000/agriculture/mcp \
  --header 'Authorization: Bearer ${XIPPIOS_MCP_AGRICULTURE_TOKEN}'
```

In single quotes the shell passes `${XIPPIOS_MCP_AGRICULTURE_TOKEN}` on as written, and
Claude Code expands it from its own environment when it connects, so the token stays out
of Claude Code's config; in double quotes the shell would write the token itself into
the config. Claude Code reads some well-known credential variables as empty in a remote
server's headers (its own, a cloud provider's, others such as `NPM_TOKEN`); a name of
the operator's own, such as `XIPPIOS_MCP_AGRICULTURE_TOKEN`, is outside that set and
expands as written. When a token does not arrive, `claude --debug-file <file>` logs
`never expanded toward a remote server` for a covered name.

The bearer does not serve claude.ai. claude.ai signs in with OAuth: it starts on a `401`
that names a `resource_metadata` document, and it needs an OAuth authorization server.
The host advertises no `resource_metadata` and is no authorization server, so
claude.ai needs one in front of the host, which 0.1.0 leaves out (sdk-core ADR-0026,
decision 10).

### The loopback rule

A write server, `cashctrl:write` for instance, and a read server that its package holds
to loopback, as sdk-google-mail holds its own, are held to loopback by their tool sets.
An endpoint with `auth = "none"` that serves such a server, or a group with one such
package, carries no authentication, so `--http` serves it on a loopback `--host` only,
`127.0.0.1`, `localhost` or `::1`, as a package's own entry point keeps its server
(sdk-core ADR-0063, decision 5). On another `--host` the host refuses to start unless
the endpoint sets `allow_remote = true`, and then a gateway in front of it has to
authenticate. Any other read endpoint with `auth = "none"`, and every bearer endpoint,
is served on any host.

### Behind a reverse proxy

On a loopback `--host` the mcp SDK checks the `Host` and `Origin` headers itself and
accepts loopback values only, which keeps a web page from reaching the host through DNS
rebinding. Beyond loopback it checks neither, unless the config names what to accept:

```toml
[http]
allowed_hosts = ["mcp.example.com"]            # the Host values the proxy forwards
allowed_origins = ["https://mcp.example.com"]  # browser origins, if any
```

The lists replace the SDK's loopback default for every endpoint: a request whose `Host`
is not listed gets `421`, and one with an `Origin` that is not listed gets `403`; a
request without `Origin` passes. `"<host>:*"` accepts any port, so add `"127.0.0.1:*"`
to keep clients that connect directly. Both keys are optional, but `allowed_origins`
needs `allowed_hosts`. Without the table, a host bound beyond loopback gets no `Host`
check.

## Docker

The repository builds an image of the host with every package of `all`, sdk-faostat,
sdk-cashctrl and sdk-usda-esr, at the versions `uv.lock` pins. 0.1.0 publishes no image to a
registry: build it from a checkout.

```bash
docker build -t xippios-mcp .
```

The image runs `xippios-mcp --config /etc/xippios-mcp/host.toml --http --host 0.0.0.0
--port 8000` as the non-root user `xippios` (uid 10001), and holds no config, key or
token. The operator mounts the config, a file that user can read, and passes every
token by its variable's name, so the value comes from the operator's environment and
stays out of the command line. For a config with one bearer endpoint:

```toml
[endpoints.agriculture]
packages = ["faostat", "usda-esr"]
auth = "bearer"
token_env = "XIPPIOS_MCP_AGRICULTURE_TOKEN"
```

```bash
docker run --rm -p 8000:8000 \
  -v "$PWD/host.toml:/etc/xippios-mcp/host.toml:ro" \
  -e XIPPIOS_MCP_AGRICULTURE_TOKEN \
  xippios-mcp
```

serves it at `http://127.0.0.1:8000/agriculture/mcp`. The variables the packages read
themselves, their keys among them, are passed the same way, by name; each package's
README names its own. Arguments after the image name replace the image's own, so

```bash
docker run --rm -v "$PWD/host.toml:/etc/xippios-mcp/host.toml:ro" xippios-mcp \
  --config /etc/xippios-mcp/host.toml
```

checks the mounted config and lists its endpoints without serving them.

Inside the container the host binds `0.0.0.0`, beyond loopback, so every endpoint is
remote, whichever interface `-p` publishes the port on: give every endpoint the bearer.
An `auth = "none"` endpoint held to loopback is refused there unless it sets
`allow_remote = true` (see The loopback rule), and then nothing authenticates it but a
gateway in front; prefer the bearer. Beyond loopback the mcp SDK checks no `Host` or `Origin` header, so
behind a reverse proxy the config's `[http]` table names the values to accept (see
Behind a reverse proxy).

## Workflows

`ci.yml` runs ruff, its format check, mypy, pytest and pre-commit on Python 3.12, 3.13 and
3.14, requires a changelog entry of every pull request but Dependabot's and refuses a
fixture file over 256 KiB that a pull request adds or changes. It runs on every pull request
and, called by `publish.yml`, once for a release, and its job `ci` is the check the
organization's ruleset requires. It is handed no secret, and no variable switches it off.

`docker.yml` is the host's own workflow beside those the template renders: on every pull
request it builds the image of Docker above from the checkout, runs its `--help`, then
serves it as an operator does, with a mounted config of two bearer endpoints over the three
sources of `all`, and expects `401` and the bearer's challenge from each for a request
without a token, the check `docker`. Each request is retried for about 30 seconds while the
server starts, and a `401` is the answer, never retried: the host serves only once it has
built every endpoint. The job stops after 15 minutes, and a newer push to the pull request
cancels the run still going. It pushes no image and logs in to no registry
(sdk-core ADR-0026, decision 2). It is handed no secret, since the run makes its own random
tokens and masks them in the log, and no variable switches it off.

`publish.yml` is the release train (conventions §12): on a push to `main` whose
`pyproject.toml` names a version that has no tag yet and has its section in `CHANGELOG.md`,
it runs `ci.yml`, refuses a core pinned to git, tags the merge commit, builds the package
and, once a reviewer of the environment `pypi` approves the run, publishes it to PyPI by
trusted publishing. Every push to `main` and a dispatch start it, and a push that brings no
release ends quietly. It is handed no secret: the step that tells a release is handed the
job's token as `GH_TOKEN`, the tag goes with the job's token and PyPI trusts the workflow
itself. Its job `tag` holds the one checkout of the repository that keeps its credentials,
since it pushes the tag with the job's token; every other checkout sets
`persist-credentials: false` (conventions §13). No variable switches it off.

`conventions.yml` calls the organization's review of a pull request against the documents
listed under Documents below, the check `conventions / conventions`, when a pull request
opens, is pushed to, reopens or is edited, and on a push to `main` or a dispatch the review
of the range of commits, `range / range`. It hands the review the organization's
secret of the model's key, by name. A variable `WORKFLOW_CONVENTIONS` of `off`, the
repository's over the organization's, switches both off.

`adr-index.yml` calls the organization's check of the ADR index, `adr-index / adr-index`,
which runs `scripts/adr_index.py --check`, when a pull request opens, is pushed to or
reopens. It hands over nothing, and the called workflow reads its switch itself: a variable
`WORKFLOW_ADR_INDEX` of `off`, the repository's over the organization's, skips the check.

## Documents

- sdk-core: [docs/conventions.md](https://github.com/xippios/sdk-core/blob/main/docs/conventions.md) — the conventions of the xippios packages: their layout, names, results, tests and releases, which bind the host as far as sdk-core ADR-0026 says.
- sdk-core: [docs/adr.md](https://github.com/xippios/sdk-core/blob/main/docs/adr.md) — the index of the family's architecture decisions, which the conventions cite.
- sdk-core: [docs/definition-of-done.md](https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md) — what a change satisfies before its pull request is opened.
- sdk-core: [docs/review-checklist.md](https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md) — what the review of a pull request checks, in order.
- sdk-core: [docs/adr/0026-the-host-xippios-mcp.md](https://github.com/xippios/sdk-core/blob/main/docs/adr/0026-the-host-xippios-mcp.md) — the host's design decisions, and in decision 1 which of the conventions bind a package that is no source.
- xippios-mcp: [docs/adr.md](https://github.com/xippios/xippios-mcp/blob/main/docs/adr.md) — the index of this package's own decisions, generated from the records in `docs/adr/`.

## Licence

Apache-2.0. See [LICENSE](https://github.com/xippios/xippios-mcp/blob/main/LICENSE).
