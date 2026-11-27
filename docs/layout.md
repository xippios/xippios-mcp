# Layout

The files that every repository of the template's general shape holds are laid out once, in
sdk-template's README,
[The general part of a repository](https://github.com/xippios/sdk-template/blob/main/README.md#the-general-part-of-a-repository).
This file holds what `xippios-mcp` adds to them, a module, a script or a test of
its own, each with what it holds, and the change that adds one updates it.

The import path is `xippios.mcp` (sdk-core ADR-0006); `src/xippios/` is a
namespace package.

```
src/xippios/mcp/
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
tests/
  example/         the invented sources the tests serve, xippios.example and the nested
                   xippios.example.api, on pytest's pythonpath and mypy's path; they ship
                   in no distribution
  conftest.py      core's pytest plugin, and the example's ceiling set back after each test
  test_package.py  the host's own checks: the namespace level, py.typed, __version__, the
                   core bound, the extras of the three proving sources at their floors and
                   their union, the lock from PyPI on one core minor with xippios-usda-fas
                   as sdk-usda-esr's dependency alone, the entry point, the CLI, core
                   imported by its pinned lists alone, and the template's answers
  test_config.py   load_config, the [http] table and every static refusal
  test_servers.py  the tool sets read and the servers built, through mcp.Client
                   in-process, the pass-through and the refusals that need a package
  test_auth.py     the token variable and the bearer's answers
  test_app.py      MCP sessions over the app in-process (httpx2's ASGITransport inside
                   the lifespan), the Host check, the loopback refusals, serve_http with
                   uvicorn's Server.run stubbed
  test_cli.py      --stdio, --http (serve_http stubbed), the endpoint lines and exit
                   status 2; no test binds a port
  test_sources.py  the three sources of `all`, served from the releases the lock pins:
                   each by its build(), its endpoints listing the tools of its own
                   server, the list mode, the sample config built, and one call each that
                   counts no request
docs/
  host.example.toml  the sample config, of sources of the extras alone: loaded by
                   test_config.py and built by test_sources.py
  reports/2026-11-25-the-host-serves-the-three-proving-sources.md
                   the run of test_sources.py and the list mode on core 0.5.0's
                   candidate, with the commits of the host and the three sources
Dockerfile         the image: python:3.12-slim and uv by digest, `uv sync --locked` of
                   `all`, the non-root user xippios as USER 10001:10001, --http on
                   0.0.0.0:8000
.dockerignore      keeps .git, .venv, tests, .worktrees, the caches and any .env or
                   .envrc out of the build context
.github/workflows/
  docker.yml       the host's own workflow beside the rendered ones: the image built from
                   the checkout, its --help, and its server's 401 to a request without a
                   token, on every pull request
```

Core's family check (`xippios.core.testing.family`) holds no repository of the general
shape, and the host has no `_client` or `tasks` for it to import, so `tests/test_package.py`
carries the checks that apply here.
