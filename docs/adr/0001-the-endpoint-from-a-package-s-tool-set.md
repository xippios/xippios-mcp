# ADR-0001: The endpoint from a package's tool set

Status: Accepted · Date: 2026-11-24 · Decided by https://github.com/xippios/sdk-core/issues/485

## Context

The host's 0.1.0 read three things of a package, on xippios-core 0.3: its module-level
`server`, which an endpoint of one package mounted as the package built it, and, for a server
the host built itself, `tasks.__all__` and `MCP_CAPS`, with core's private `is_bulk_task` to
leave the bulk tasks out (sdk-core ADR-0026, decision 8). It took `register_tasks`,
`is_write_server` and `quiet_request_logging` from `xippios.core.mcp.server` and kept a private
copy of core's loopback hosts, outside core's public surface. Because an endpoint of one
package mounted the package's own server object, which serves one HTTP endpoint, the host
refused that package alone on two endpoints. A package was known by the host's extras.

Core 0.5.0 makes the tool set the one way to build and run a source's server: a source's
`build()` returns its `ToolSet`, `build_server(tool_set)` and `register_tasks(server,
tool_set)` take a tool set alone, a tool set is checked when it is built and holds tools
alone, and `is_write_server` and `is_loopback_only` leave, since the tool set's `read_only` and
`loopback_only` say the same (https://github.com/xippios/sdk-core/issues/476, sdk-core
ADR-0063). The maintainer's answer on https://github.com/xippios/sdk-core/issues/485 has the
host read a source's tool set and import nothing private of core, and sdk-core ADR-0063,
decisions 4 and 5, states what a host reads and that it applies the hold to loopback itself.
This record states how the host reads a package and builds an endpoint from 0.2.0 on.

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
3. **Every endpoint builds a server of its own.** An endpoint of one package without a list
   serves `build_server(tool_set)`, the server that the package's own entry point serves,
   with its name, instructions, version and caps. A group, or an endpoint with an include or
   exclude list, is one `MCPServer` named `xippios-<endpoint>`, on which `register_tasks`
   registers each package's tool set; a list narrows a tool set by `dataclasses.replace`, its
   caps cut to the kept tasks, which core checks as a new tool set. No package's module
   object is mounted, so one package may serve several endpoints alone, and the check that
   refused it leaves.
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

## Consequences

- The host serves the sources released on core 0.5 and none on an earlier core minor, so its
  extras leave until the sources release, and `all` installs none in the meantime.
- A name of an include or exclude list that is a bulk task is refused as no task of the
  package, since the tool set holds no bulk task; the refusal says that a task of
  `BULK_TASKS` is no tool.
- A read package that declares the hold to loopback, sdk-google-mail's, is held on an
  `auth = "none"` endpoint, where 0.1.0 left that to the operator.
- An endpoint of one package shows the package's own instructions and version.
- The host's copy of the loopback hosts, its imports from `xippios.core.mcp.server` and
  `xippios.core._tasks`, and the mounted-once check leave.
