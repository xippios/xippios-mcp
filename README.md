# xippios-mcp

The self-hosted MCP host of the [xippios SDK family](https://github.com/xippios). It
serves the MCP tools of the family's packages from one process, by endpoint and group:
an endpoint mounts a package's own server, read or write, and a group combines several
packages' tools on one endpoint, never read and write tools together. It runs on stdio
locally and on streamable HTTP on a server, each endpoint with its own auth, a bearer
token by default; the secrets stay in the environment, never in the config file.

`xippios-mcp --config <path>` checks a config, builds every endpoint's server and lists
the endpoints; `--stdio <endpoint>` serves one endpoint on stdio, and `--http` serves
every endpoint over streamable HTTP, each with its bearer (see Serving). A Docker image,
built from this repository, serves them from a container (see Docker).

## Install

```bash
uv add "xippios-mcp[all]"          # the host with every package below
uv add "xippios-mcp[usda-nass]"    # or one extra per package you serve
```

## Packages

Each package is an extra with a lower bound only, so the host installs every package at
its latest release.

| Extra | Distribution | Lower bound | Servers | Tools |
| --- | --- | --- | --- | --- |
| `cashctrl` | `xippios-cashctrl` | `>=0.3.0` | read and write | 24 read, 11 write |
| `comtrade` | `xippios-comtrade` | `>=0.2.0` | read | 19 |
| `eurostat` | `xippios-eurostat` | `>=0.2.0` | read | 13 |
| `faostat` | `xippios-faostat` | `>=0.1.0` | read | 7 |
| `usda-esmis` | `xippios-usda-esmis` | `>=0.2.0` | read | 9 |
| `usda-esr` | `xippios-usda-esr` | `>=0.2.0` | read | 10 |
| `usda-gats` | `xippios-usda-gats` | `>=0.2.0` | read | 20 |
| `usda-nass` | `xippios-usda-nass` | `>=0.2.0` | read | 16 |
| `usda-psd` | `xippios-usda-psd` | `>=0.3.0` | read | 12 |

The tools are each package's `tasks.__all__` (`tasks_write.__all__` for a write server)
less its `BULK_TASKS`, which are Python-only, counted at the version of the lower bound;
a later release may add tools. `all` installs the nine. `xippios-usda-wasde` joins
later: its 0.1.1 needs `xippios-usda-esmis` below 0.2.

### The ceilings of usda-nass and usda-gats

`--split-years` of `xippios-usda-nass-mcp` and `--series-months` of
`xippios-usda-gats-mcp` are options of those packages' own entry points, which the host
does not run. The host therefore serves the ceilings the packages keep in Python: a
split `usda_nass_get_data` spans up to 20 years, at up to two keyed calls a year (the
entry point's default is 5 years), and `usda_gats_get_census_export_series`,
`usda_gats_get_census_import_series` and `usda_gats_get_census_reexport_series` span up
to 60 months, at one call a month (the entry point's default is 24 months). An operator
who wants fewer calls per tool call leaves those tools out with an endpoint's `exclude`
list (see Configuration).

## Configuration

The host reads one TOML file that names its endpoints. Each `[endpoints.<name>]` table
is one endpoint, which the HTTP transport serves at `/<name>/mcp`:

```toml
[endpoints.agriculture]                        # served at /agriculture/mcp
packages = ["usda-nass", "usda-psd", "comtrade"]
exclude = { usda-nass = ["get_counts"] }       # or include = { ... }; exact task names
auth = "bearer"                                # the default; or "none"
token_env = "XIPPIOS_MCP_AGRICULTURE_TOKEN"    # a name ending in _TOKEN, never a value
allow_remote = false                           # the default

[endpoints.accounting-write]
packages = ["cashctrl:write"]
auth = "none"
```

- An endpoint that names one package and no list serves that package's own server, as
  the package builds it: `xippios.<package>.mcp.server`, or `mcp_write.server` for
  `<slug>:write`, with its instructions and result caps.
- A group, several packages, or an endpoint with an `include` or `exclude` list is a
  server the host builds, named `xippios-<endpoint>`: each package's tools under their
  own names (`usda_nass_get_data`), with the package's result caps for the tools it
  keeps.
- Read and write never mix: an endpoint's packages are all `<slug>:write` or none, and
  the host refuses a group that mixes them.
- `include` and `exclude` are keyed by package slug and name exact task names, a task
  function's `__name__` (`get_counts`, not `usda_nass_get_counts`); a package takes one
  of the two, and an empty list is refused. A name that is no tool of the package is
  refused, a task in the package's `BULK_TASKS` among them, since a bulk task is
  Python-only and no tool.
- `auth` is `"bearer"` by default, or `"none"`. With the bearer, `token_env` names the
  environment variable that holds the token, a name ending in `_TOKEN`
  (`XIPPIOS_MCP_<ENDPOINT>_TOKEN`), and the token itself stays in the environment, never
  in the file. The host reads the variable once, when `--http` starts, and never on
  stdio or when it lists. `allow_remote` is `false` by default; it lets an `auth =
  "none"` write endpoint beyond loopback (see The loopback rule).
- An optional `[http]` table names the `Host` and `Origin` values the HTTP transport
  accepts behind a reverse proxy (see Behind a reverse proxy).

Check a config before serving it:

```bash
xippios-mcp --config host.toml
```

It loads the file, builds every endpoint and prints one line per endpoint; for
[`docs/host.example.toml`](docs/host.example.toml), the sample above, with the packages
at the lower bounds:

```text
agriculture: read, 46 tools of usda-nass, usda-psd, comtrade
accounting-write: write, 11 tools of cashctrl
```

A key, package or task the host refuses stops it with exit status 2 and a message that
names the file, the endpoint and the key. The list runs neither the mounted-once check
nor the loopback check of Serving, which need `--http` and its `--host`.

A server the host builds carries none of the packages' own instructions: its
instructions are one sentence naming its packages and their tool counts. No endpoint
takes a package's command-line options, such as cashctrl's `--org` lock or the ceilings
above, since the host runs no package's entry point. The package contract of the next
template release gives the host what it needs to carry them, in its 0.2.0.

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
nothing. A package's own server serves one HTTP endpoint: two endpoints that each name
`usda-nass` alone are refused, and an `include` or `exclude` list on one of them makes
its server one the host builds.

### The bearer

An endpoint with `auth = "bearer"` answers a request without the token with `401` and
`WWW-Authenticate: Bearer realm="xippios-mcp"`, and one with a wrong token with
`error="invalid_token"` added; such a request never reaches the endpoint. The token is
the value of the variable `token_env` names, read once when `--http` starts: an unset or
empty variable stops the host with exit status 2. The host keeps the token's SHA-256
digest only, compares in constant time, and never logs the token or the `Authorization`
header. A random token will do, `openssl rand -hex 32` for instance, set in the
environment of the host and of the client.

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
The host advertises no `resource_metadata` and is no authorization server, so claude.ai
needs one in front of the host, which 0.1.0 leaves out (ADR-0026, decision 10).

### The loopback rule

An endpoint with `auth = "none"` that serves a write server, `cashctrl:write` for
instance, carries no authentication, so `--http` serves it on a loopback `--host` only,
`127.0.0.1`, `localhost` or `::1`, as a package's own entry point keeps its write server
(ADR-0014, decision 9). On another `--host` the host refuses to start unless the
endpoint sets `allow_remote = true`, and then a gateway in front of it has to
authenticate. A read endpoint with `auth = "none"`, and every bearer endpoint, is served
on any host.

A read server that its package holds to loopback, as sdk-google-mail holds its own, is
not held there by the host's 0.1.0: the host reads the packages' loopback option from
its 0.2.0 on (queue row 282). Until then, keep an `auth = "none"` endpoint of such a
package on a loopback `--host`, or give it the bearer.

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

The repository builds an image of the host with every package of `all`, at the versions
`uv.lock` pins, the set the tests run against. 0.1.0 publishes no image to a registry:
build it from a checkout.

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
packages = ["usda-nass", "usda-psd", "comtrade"]
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
An `auth = "none"` write endpoint is refused there unless it sets `allow_remote = true`
(see The loopback rule), and then nothing authenticates it but a gateway in front;
prefer the bearer. Beyond loopback the mcp SDK checks no `Host` or `Origin` header, so
behind a reverse proxy the config's `[http]` table names the values to accept (see
Behind a reverse proxy).

## Licence

Apache-2.0. See [LICENSE](LICENSE).
