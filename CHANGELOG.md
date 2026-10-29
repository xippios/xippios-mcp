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
