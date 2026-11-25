# ADR-0001: The endpoint from a package's tool set

Status: Accepted · Date: 2026-11-24 · Decided by https://github.com/xippios/sdk-core/issues/485 ·
Amended 2026-11-25 by https://github.com/xippios/xippios-mcp/issues/27

## Context

The host's 0.1.0 read three things of a package, on xippios-core 0.3: its module-level
`server`, which an endpoint of one package mounted as the package built it, and, for a server
the host built itself, `tasks.__all__` and `MCP_CAPS`, with core's private `is_bulk_task` to
leave the bulk tasks out (sdk-core ADR-0026, decision 8). It took `register_tasks`,
`is_write_server` and `quiet_request_logging` from `xippios.core.mcp.server` and kept a private
copy of core's loopback hosts, outside core's public surface. Because an endpoint of one
package mounted the package's own server object, which serves one HTTP endpoint, the host
refused that package alone on two endpoints. A package was known by the host's extras. A
server the host built itself carried one sentence of the host's as its instructions and none
of a package's, and no endpoint ran a package's option hooks, so the host served
sdk-usda-nass's split up to the 20 years of its Python API where the package's entry point
serves 5 (sdk-core ADR-0026, amendment 2026-10-30, part (a)).

Core 0.5.0 makes the tool set the one way to build and run a source's server: a source's
`build()` returns its `ToolSet`, `build_server(tool_set)` and `register_tasks(server,
tool_set)` take a tool set alone, a tool set is checked when it is built and holds tools
alone, and `is_write_server` and `is_loopback_only` leave, since the tool set's `read_only` and
`loopback_only` say the same (https://github.com/xippios/sdk-core/issues/476, sdk-core
ADR-0063). The maintainer's answer on https://github.com/xippios/sdk-core/issues/485 has the
host read a source's tool set and import nothing private of core, and sdk-core ADR-0063,
decisions 4 and 5, states what a host reads and that it applies the hold to loopback itself.
The tool set carries the package's two option hooks, `apply_options` takes the parsed options
alone, and `option_defaults()` gives the options that the entry point hands it from an empty
command line, so a host applies the hooks without a server and without a command line
(sdk-core ADR-0063, decision 4). This record states how the host reads a package and builds
an endpoint from 0.2.0 on.

## Decision

1. **A package is read by its tool set.** The host calls `<path>.mcp.build()`, or
   `<path>.mcp_write.build()` for `<slug>:write`, without arguments, and reads the `ToolSet`
   it returns: its tools, `tool_name(tool_set.source, fn)` for each `fn` of its `tasks`, their
   caps, its instructions and version, and its `read_only` and `loopback_only`. It reads no
   module-level `server`, no `tasks.__all__`, no `MCP_CAPS` and no bulk task of a package. A
   module without `build`, a `build()` that returns anything but a `ToolSet`, and a tool set
   of the other kind than the entry names are refused at startup. A `ValueError` or a
   `TypeError` raised at the package's import or by its `build()` is re-raised with the file,
   the endpoint, the package and the error's class: core refuses a declaration with these
   two plain classes, so a package's own error of either class ends so too.
2. **A package is known by its import path.** A slug has the form of conventions §1,
   lower-case letters and digits with its words joined by hyphens, and names the package at
   `xippios.<slug>`, each hyphen a dot; a package that is installed is served. The host's
   extras say what `all` installs and what the hint for a missing package names.
3. **Every endpoint builds a server of its own.** An endpoint of one package serves
   `build_server(tool_set)`, the server that the package's own entry point serves, with its
   instructions, version and caps, under the package's name without a list; with an include
   or exclude list it serves `build_server(narrowed, name="xippios-<endpoint>")` of the
   narrowed tool set. A group is one `MCPServer` named `xippios-<endpoint>`, on which
   `register_tasks` registers each package's tool set. A list narrows a tool set by
   `dataclasses.replace`, its caps cut to the kept tasks, which core checks as a new tool
   set. No package's module object is mounted, so one package may serve several endpoints
   alone, and the check that refused it leaves.
4. **The write rule and the hold to loopback are the tool sets'.** A server writes when its
   tool sets write, and it is held to loopback when one of them writes or is
   `loopback_only`. An endpoint with `auth = "none"` that is held is served over HTTP on a
   host of core's `LOOPBACK_HOSTS` only, unless it sets `allow_remote = true`; a bearer
   endpoint carries authentication and is served on any host (sdk-core ADR-0026, decision 5;
   ADR-0063, decision 5).
5. **Core is imported by its pinned lists alone.** Every name of core that the host's
   package, tests and scripts import comes from one of the six `__all__` lists of core's
   `__init__.py` files, by that list's module path, and none is private. A test of the host
   reads every import of its own files with `ast` and fails on any other, so the line is held
   by a check.
6. **The tests stand on invented sources.** The host's tests serve `example` and its nested
   `example-api` under `tests/example`, which have a source's files as core's package contract
   has them and send no request, so the host's tests wait for no real source.
7. **An endpoint carries its packages' instructions and their option defaults.** An endpoint
   of one package shows that package's instructions and version, with a list too, where its
   server is `build_server(tool_set, name=...)` of the narrowed tool set, named
   `xippios-<endpoint>`. A group's server shows the host's version, and its instructions open
   with the host's sentence, which names its packages with their tool counts, and then name
   each package's own under a heading of its slug, in the config's order; a package without
   instructions gets no heading. A list narrows a package's tools and leaves its
   instructions whole, on an endpoint of one package and in a group alike, so they may name
   a tool that the endpoint does not serve: the host changes no text of a package, as it
   renames none of its tools. Before an endpoint's server is built, the host applies each tool set's `apply_options` to its `option_defaults()`, the
   options that its entry point parses from an empty command line, so the package's options
   hold at the values its entry point holds without options, for the whole process as the
   entry point's do. A config sets no option of a package. An option without a default,
   which `option_defaults()` refuses with `ValueError`, and a `XippiosError` or `ValueError`
   that the hook raises are refused at startup with the file, the endpoint, the package and
   the error's class, where the entry point would exit with status 2 (sdk-core ADR-0063,
   decision 4).

## Consequences

- The host serves the sources released on core 0.5 and none on an earlier core minor, so its
  extras leave until the sources release, and `all` installs none in the meantime.
- A name of an include or exclude list that is a bulk task is refused as no task of the
  package, since the tool set holds no bulk task; the refusal says that a task of
  `BULK_TASKS` is no tool.
- A read package that declares the hold to loopback, sdk-google-mail's, is held on an
  `auth = "none"` endpoint, where 0.1.0 left that to the operator.
- An endpoint of one package shows the package's own instructions and version, with a list
  too, and a group's instructions name each package's own under its slug. Both stand whole
  under a list, so they may name a tool that the endpoint does not serve.
- The host serves the ceilings that the packages' entry points serve without options,
  sdk-usda-nass's split of 5 years and sdk-usda-gats's series of 24 months, where 0.1.0
  served the 20 years and 60 months of their Python APIs, and a ceiling holds for every call
  in the host's process. The list mode applies the hooks too, since it builds every endpoint.
- A package's options set per endpoint would need more than the hooks, whose values are the
  process's, one for all the endpoints that serve the package; 0.2.0 sets none.
- The host's copy of the loopback hosts, its imports from `xippios.core.mcp.server` and
  `xippios.core._tasks`, and the mounted-once check leave.
