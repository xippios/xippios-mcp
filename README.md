# xippios-mcp

The self-hosted MCP host of the [xippios SDK family](https://github.com/xippios). It
serves the MCP tools of the family's packages from one process, by endpoint and group:
an endpoint mounts a package's own server, read or write, and a group combines several
packages' tools on one endpoint, never read and write tools together. It runs on stdio
locally and on streamable HTTP on a server, each endpoint with its own auth, a bearer
token by default; the secrets stay in the environment, never in the config file.

The config, the transports and the bearer come with the next steps: for now
`xippios-mcp --config <path>` stops with exit status 2 and serves nothing.

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
who wants fewer calls per tool call excludes those tools from the endpoint.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
