# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0: breaking changes bump the minor).

## [Unreleased]

### Added

- Scaffold, by hand from [sdk-template](https://github.com/xippios/sdk-template) v0.3.0:
  the package `xippios.mcp` on `xippios-core[mcp]` 0.3, one extra per source package with
  a lower bound and `all` their union, the `xippios-mcp` entry point with `--config`,
  which serves nothing yet, the host's package checks, CI and the release train, in
  which a release PR's merge tags and publishes.
- The config, its startup checks and the mount: `xippios-mcp --config <path>` reads a
  TOML file of `[endpoints.<name>]` tables, checks every key, builds each endpoint's
  server and prints one line per endpoint; a refusal names the file, the endpoint and
  the key and exits with status 2. One package without a list serves the package's own
  server; a group or an endpoint with an `include` or `exclude` list is a server the
  host builds, named `xippios-<endpoint>`, with the packages' tools under their own
  names and their result caps. Read and write never share an endpoint, a list names
  exact task names, and `token_env` names a variable ending in `_TOKEN`. A sample config
  is in `docs/host.example.toml`.
