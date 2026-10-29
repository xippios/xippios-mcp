# xippios-mcp

The self-hosted MCP host of the [xippios SDK family](https://github.com/xippios). It
serves the MCP tools of the family's packages from one process, by endpoint and group:
an endpoint mounts a package's own server, read or write, and a group combines several
packages' tools on one endpoint, never read and write tools together. It runs on stdio
locally and on streamable HTTP on a server, each endpoint with its own auth, a bearer
token by default; the secrets stay in the environment, never in the config file.

The config and the mount are here: `xippios-mcp --config <path>` checks the config,
builds every endpoint's server and lists the endpoints. The transports and the bearer
come with the next steps; until then the host serves nothing.

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
  of the two. A name that is no tool of the package is refused, a task in the package's
  `BULK_TASKS` among them, since a bulk task is Python-only and no tool.
- `auth` is `"bearer"` by default, or `"none"`. With the bearer, `token_env` names the
  environment variable that holds the token, a name ending in `_TOKEN`
  (`XIPPIOS_MCP_<ENDPOINT>_TOKEN`), and the token itself stays in the environment, never
  in the file. `allow_remote` is `false` by default. The host checks the shape of the
  three now and reads no variable; the bearer and the loopback rule come with the HTTP
  transport.

Check a config before serving it:

```bash
xippios-mcp --config host.toml
```

It loads the file, builds every endpoint and prints one line per endpoint; for
[`docs/host.example.toml`](docs/host.example.toml), the sample above:

```text
agriculture: read, 46 tools of usda-nass, usda-psd, comtrade
accounting-write: write, 11 tools of cashctrl
```

A key, package or task the host refuses stops it with exit status 2 and a message that
names the file, the endpoint and the key.

A server the host builds carries none of the packages' own instructions: its
instructions are one sentence naming its packages and their tool counts. No endpoint
takes a package's command-line options, such as cashctrl's `--org` lock or the ceilings
above, since the host runs no package's entry point. The package contract of the next
template release gives the host what it needs to carry them, in its 0.2.0.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
