# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [Unreleased]

### Added

- Scaffold, by hand from [sdk-template](https://github.com/xippios/sdk-template) v0.3.0:
  the package `xippios.mcp` on `xippios-core[mcp]` 0.3, one extra per source package with
  a lower bound and `all` their union, the `xippios-mcp` entry point with `--config`, the
  host's package checks, CI and the release train, in which a release PR's merge tags
  and publishes.
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
  variable `token_env` names, and an unset or empty one stops the host with exit status
  2. An `auth = "none"` write endpoint is served on a loopback host only, unless it sets
  `allow_remote = true`; a package's own server serves one HTTP endpoint; and an
  optional `[http]` table names the `Host` and `Origin` values accepted behind a reverse
  proxy.
- The Docker image: `docker build -t xippios-mcp .` installs this checkout with
  `uv.lock`, every package of `all`, on `python:3.12-slim` and uv 0.13.6, both pinned by
  digest. It runs as the non-root user `xippios`, reads the config the operator mounts
  at `/etc/xippios-mcp/host.toml`, serves `--http` on `0.0.0.0:8000`, and takes every
  token from the environment by name. CI builds the image and runs `--help` in a
  `docker` job that the `ci` check requires; no image is published to a registry.
