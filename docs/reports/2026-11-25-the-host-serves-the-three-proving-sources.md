# The host serves sdk-faostat, sdk-cashctrl and sdk-usda-esr on core 0.5.0's candidate, 2026-11-25

On the candidate of xippios-core 0.5.0, the host loads each of the three sources that prove
that release (https://github.com/xippios/sdk-core/issues/485) by its `build()` and serves it
as the source's own server does: one endpoint for each source, one group of sdk-faostat's and
sdk-usda-esr's read tool sets, and sdk-cashctrl's write tool set list their tools under the
names and with the input schemas of the sources' own `server`. The list mode prints each
endpoint with its tool count. One call of each source went through the host and sent no
request: sdk-faostat and sdk-usda-esr answered from the lists they carry, and sdk-cashctrl
refused an organisation that no variable declares. No key was in the environment of the run.
Core's candidate, the three sources' `build()` and `server`, and the host's own code fitted as
they stand: nothing changed for the run, and it found no misfit.

## Basis

The commits of the run:

- xippios-core: its 0.5.0 candidate, sdk-core's `main` at
  [4060d96](https://github.com/xippios/sdk-core/commit/4060d9615012b09487d87a51064c610de34be069),
  which the host's manifest pinned and its lock held at the host's commit below. xippios-core
  0.5.0 is released at
  [a2730f6](https://github.com/xippios/sdk-core/commit/a2730f6ac48420c5de324b437b8e8852b587ee67),
  whose `src/` and `pyproject.toml` are those of the candidate.
- sdk-faostat at
  [68d7777](https://github.com/xippios/sdk-faostat/commit/68d7777a83dac7210969b2064993d1d80dc4e2c5)
  and sdk-cashctrl at
  [f72c58f](https://github.com/xippios/sdk-cashctrl/commit/f72c58fba4d0b3775ac3effd6c6ff6c6e2a39c05),
  each on that candidate and rendered from sdk-template's `main` at
  [3e75893](https://github.com/xippios/sdk-template/commit/3e75893a7325f356cd792a32fa74b5be3fb86428).
- [sdk-usda-esr](https://github.com/xippios/sdk-usda-esr) at the local commit
  `08683722ffa121ebaf0e9c9e81d8b148f38c7de4`, on the same candidate and template commit, and
  xippios-usda-fas, the shared package that sdk-usda-esr depends on and the host does not load,
  at the local commit `f3f02faf5f2b059c2d7299d28a1b7e83247bdeeb` of its repository,
  sdk-usda-fas. Neither commit was pushed on the day of this report, so each is named by its
  full hash.
- The host at the local commit `1ed0f1fc2e2f17619af113812a2922503c97e2d5`, never pushed: the
  host's code on the candidate above, with `tests/test_sources.py` as the pull request that
  adds this report adds it.

The run took CPython 3.12.15 on Linux. The host's environment is its lock at that commit,
made by `uv sync --all-extras --frozen`. The host's manifest and lock name none of the three
sources, which join as extras after their releases, so the three were installed beside the
host from their commits, each from a local clone of its repository:

```bash
uv pip install --python .venv/bin/python \
  "xippios-faostat[mcp] @ git+file://<clone of sdk-faostat>@68d7777a83dac7210969b2064993d1d80dc4e2c5" \
  "xippios-cashctrl[mcp] @ git+file://<clone of sdk-cashctrl>@f72c58fba4d0b3775ac3effd6c6ff6c6e2a39c05" \
  "xippios-usda-esr[mcp] @ git+file://<clone of sdk-usda-esr>@08683722ffa121ebaf0e9c9e81d8b148f38c7de4"
```

uv kept the host's core at the candidate
[4060d96](https://github.com/xippios/sdk-core/commit/4060d9615012b09487d87a51064c610de34be069)
and took xippios-usda-fas from the commit that sdk-usda-esr's `[tool.uv.sources]` names. The run, from the host's checkout:

```bash
env -i TMPDIR=<a temporary directory> .venv/bin/python -m pytest -v --junitxml=<report> tests/test_sources.py
env -i TMPDIR=<a temporary directory> .venv/bin/xippios-mcp --config <config>
```

`env -i` hands each command no variable but `TMPDIR`. The `<config>` of the second holds
`CONFIG` of `tests/test_sources.py`, the config that the tests build their endpoints from:

```toml
[endpoints.faostat]
packages = ["faostat"]
auth = "none"

[endpoints.cashctrl]
packages = ["cashctrl"]
auth = "none"

[endpoints.usda-esr]
packages = ["usda-esr"]
auth = "none"

[endpoints.agriculture]
packages = ["faostat", "usda-esr"]
auth = "none"

[endpoints.cashctrl-write]
packages = ["cashctrl:write"]
auth = "none"
```

The 14 tests of the module passed. The answers quoted below are the property `answer` that
each call's test recorded in the run's JUnit report, laid out over lines here.

## Each source by its build(), as its own server lists it

`load_package` imports `xippios.<slug>` and calls its `mcp.build()`, or `mcp_write.build()`
for `cashctrl:write`, and gets the source's `ToolSet` of the kind the entry names, with the
tools that the source's tool set holds. The endpoint that serves one tool set is a server of
the host's own, not the source's `server` object, and it carries that `server`'s name, version
and instructions. Its tools, listed through `mcp.Client` in-process, are the tools that the
source's own `server` lists: the same names, in the same order, with equal input schemas.

| Endpoint | Tool set | Tools | Server and version | Held to loopback |
| --- | --- | --- | --- | --- |
| `faostat` | sdk-faostat's read tool set | 7 | `xippios-faostat` 0.2.0 | no |
| `cashctrl` | sdk-cashctrl's read tool set | 25 | `xippios-cashctrl` 0.5.0 | no |
| `usda-esr` | sdk-usda-esr's read tool set | 7 | `xippios-usda-esr` 0.3.0 | no |
| `cashctrl-write` | sdk-cashctrl's write tool set | 14 | `xippios-cashctrl` 0.5.0 | yes, a write tool set |

A version is that of the source's manifest at its commit, before its release on core 0.5.0.
None of the three declares an option hook, so the defaults that an endpoint applies set
nothing here (ADR-0001, decision 7), and none of the read tool sets declares the hold to
loopback (ADR-0001, decision 4).

## The group of two read tool sets

`agriculture` is one server of the host's, `xippios-agriculture` at the host's version, read
and not held, with 14 tools: sdk-faostat's 7 and sdk-usda-esr's 7, in the config's order,
under the names and with the input schemas of the two sources' own servers. Its instructions
open with the host's sentence, "The xippios-mcp endpoint agriculture serves 14 read-only tools
of faostat (7) and usda-esr (7), each named with its package's slug as prefix", and give each
source's own instructions under `## faostat` and `## usda-esr` (ADR-0001, decision 7).

## The list mode

`xippios-mcp --config <config>` printed, with exit status 0:

```text
faostat: read, 7 tools of faostat
cashctrl: read, 25 tools of cashctrl
usda-esr: read, 7 tools of usda-esr
agriculture: read, 14 tools of faostat, usda-esr
cashctrl-write: write, 14 tools of cashctrl
```

The test of the list mode asserts the same lines, each count taken from the tools that the
source's own server lists.

## One call of each source that sends nothing

Each call went through its source's endpoint as a client calls a tool, with none of the
source's variables set: the run's environment held none, and the test removes each variable
that the source's `ENV_VARS` names, a pattern's by its form, reading names alone.

`faostat_list_areas` with `{"domain_code": "QCL", "search": "germany"}` was answered from the
area list of QCL that sdk-faostat carries, fetched on 2026-10-29:

```json
{
  "data": [
    {"code": "79", "label": "Germany", "parent": null, "aggregate_type": "0", "columns": {}}
  ],
  "meta": {
    "source": "faostat",
    "endpoint": "getCodeList",
    "retrieved_at": "2026-10-29T07:06:41Z",
    "published_at": null,
    "published_at_naive": false,
    "vintage": null,
    "request": {"lang": "en", "dimension_id": "area", "domain_code": "QCL", "search": "germany"},
    "total": null,
    "tenant": null
  }
}
```

`usda_esr_list_regions` with `{}` was answered from the regions list that sdk-usda-esr
carries, fetched on 2026-10-28, its 12 regions:

```json
{
  "data": [
    {"region_id": 10, "region_name": "AFRICA"},
    {"region_id": 7, "region_name": "CHINA"},
    {"region_id": 3, "region_name": "EASTERN EUROPE"},
    {"region_id": 1, "region_name": "EUROPEAN UNION - 27"},
    {"region_id": 4, "region_name": "FORMER SOVIET UNION-12"},
    {"region_id": 8, "region_name": "INDIA"},
    {"region_id": 5, "region_name": "JAPAN"},
    {"region_id": 9, "region_name": "OTHER ASIA AND OCEANIA"},
    {"region_id": 2, "region_name": "OTHER EUROPE"},
    {"region_id": 6, "region_name": "TAIWAN"},
    {"region_id": 99, "region_name": "UNKNOWN"},
    {"region_id": 11, "region_name": "WESTERN HEMISPHERE"}
  ],
  "meta": {
    "source": "usda-esr",
    "endpoint": "ESRData_GetRegions",
    "retrieved_at": "2026-10-28T19:19:53Z",
    "published_at": null,
    "published_at_naive": false,
    "vintage": null,
    "request": {},
    "total": null,
    "tenant": null
  }
}
```

`cashctrl_list_currencies` with `{"org": "demo"}` was refused before any request, the answer
flagged as an error, since no variable declares the organisation:

```text
error: InvalidRequestError: unknown tenant 'demo'; no tenant is declared; set CASHCTRL_ORGS and, per name, CASHCTRL_<NAME>_SUBDOMAIN and CASHCTRL_<NAME>_API_KEY; 'demo' is declared by CASHCTRL_DEMO_SUBDOMAIN and CASHCTRL_DEMO_API_KEY alone. Nothing was sent.
```

## How the run knows that nothing was sent

1. Each call ran inside the test module's recorder, and it counted nothing. Its respx router
   sits on httpcore's connection pools, through which every httpx client sends, the clients of
   core by which the sources send among them, and answers each request itself, so none leaves;
   it counted no request in any of the three calls. Python's audit events `socket.connect`,
   `socket.getaddrinfo`, `socket.gethostbyname`, `socket.sendto` and `socket.sendmsg`, which a
   connection or a lookup raises in any library, counted none either. The recorder's own test
   counted one request through httpx and one lookup of a numeric host in the same run, so its
   zeros are counts, not a blind spot.
2. Below the recorder, core's pytest plugin, which the host's tests load, refuses every request
   that reaches httpcore's pools in a test not marked `live` (sdk-core ADR-0035), so no request
   could have left in this run.
3. The answers say so themselves: the `meta.retrieved_at` of sdk-faostat's and sdk-usda-esr's
   answers are the days their lists were fetched, about four weeks before the run, and sdk-cashctrl's
   refusal ends "Nothing was sent." and names the variables that would declare `demo`, none of
   which was set.
4. The list mode builds every endpoint and calls no tool.

## What the run does not cover

- A transport: the tools were listed and called through `mcp.Client` in-process, as the
  host's tests reach a server; `--stdio` and `--http` serve the same servers.
- A call that sends a request: the run held no key and called no upstream, by design. The
  sources' own live runs cover their requests.
