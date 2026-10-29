# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [Unreleased]

## [0.1.0] - 2026-10-29

The first release of xippios-mcp, the self-hosted MCP host of the xippios SDK family. It
serves the MCP tools of the family's packages from one process, by endpoint and group:
an endpoint serves one package's own server, or a server the host builds from one or
several packages' tools, never read and write tools together. It runs on stdio, or on
streamable HTTP, each endpoint with its own bearer token or none, and a Docker image
built from the repository serves it from a container.

### Added

- The scaffold, by hand from [sdk-template](https://github.com/xippios/sdk-template)
  v0.3.0: the package `xippios.mcp` on `xippios-core[mcp]` 0.3, the `xippios-mcp` entry
  point with `--config`, the host's package checks, CI, and the release workflow, in
  which the merge of a release pull request tags the version and publishes it to PyPI.
- One extra per source package, each with a lower bound and no upper bound, so that the
  host installs every package at its latest release, and `all` their union: `cashctrl`
  (`xippios-cashctrl>=0.3.0`), `comtrade` (`xippios-comtrade>=0.2.0`), `eurostat`
  (`xippios-eurostat>=0.2.0`), `faostat` (`xippios-faostat>=0.1.0`), `usda-esmis`
  (`xippios-usda-esmis>=0.2.0`), `usda-esr` (`xippios-usda-esr>=0.2.0`), `usda-gats`
  (`xippios-usda-gats>=0.2.0`), `usda-nass` (`xippios-usda-nass>=0.2.0`) and `usda-psd`
  (`xippios-usda-psd>=0.3.0`). `xippios-usda-wasde` joins in a later release, once its
  0.2.0 ships: its 0.1.1 needs `xippios-usda-esmis` below 0.2, so it does not install
  beside the other nine.
- The config, its startup checks and the mount: `xippios-mcp --config <path>` reads a
  TOML file of `[endpoints.<name>]` tables, checks every key, builds each endpoint's
  server and prints one line per endpoint; a refusal names the file, the endpoint and
  the key and exits with status 2. One package without a list serves the package's own
  server; a group or an endpoint with an `include` or `exclude` list is a server the
  host builds, named `xippios-<endpoint>`, with the packages' tools under their own
  names and their result caps. Read and write never share an endpoint, a list names
  exact task names, and `token_env` names a variable ending in `_TOKEN`. A sample config
  is in `docs/host.example.toml`.
- The transports and the bearer: `--stdio <endpoint>` serves one endpoint on stdio,
  without auth, and `--http` serves every endpoint at `/<name>/mcp` from one process on
  `--host` (default `127.0.0.1`) and `--port` (default 8000). An endpoint with
  `auth = "bearer"` answers a missing or wrong token with `401` and
  `WWW-Authenticate: Bearer realm="xippios-mcp"`; the token is read once from the
  variable `token_env` names, and an unset or empty one, or one with leading or trailing
  whitespace, stops the host with exit status 2. An `auth = "none"` write endpoint is
  served on a loopback host only, unless it sets `allow_remote = true`; a package's own
  server serves one HTTP endpoint; and an optional `[http]` table names the `Host` and
  `Origin` values accepted behind a reverse proxy.
- The Docker image: `docker build -t xippios-mcp .` installs this checkout with
  `uv.lock`, every package of `all`, on `python:3.12-slim` and uv 0.13.6, both pinned by
  digest. It runs as the non-root user `xippios`, reads the config the operator mounts
  at `/etc/xippios-mcp/host.toml`, serves `--http` on `0.0.0.0:8000`, and takes every
  token from the environment by name. CI builds the image and runs `--help` in a
  `docker` job that the `ci` check requires; no image is published to a registry.
