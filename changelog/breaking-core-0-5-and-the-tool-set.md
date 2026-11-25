- The host adopts xippios-core 0.5.0 (`~=0.5.0`) and applies conventions 1.30, and serves
  each package from its tool set, `<path>.mcp.build()` or `mcp_write.build()` for
  `<slug>:write`, so it serves the sources released on core 0.5 and none before, and its
  nine extras leave until those releases. Every endpoint builds a server of its own, one
  package alone with the package's instructions and version, and an `auth = "none"`
  endpoint whose package writes or holds its read server to loopback is served on loopback
  unless `allow_remote = true`. An installed package whose slug is lower-case letters and
  digits joined by hyphens is served, and in a group one source's key name no longer turns
  another source's data into `REDACTED`.
  (ADR-0001, https://github.com/xippios/sdk-core/issues/476,
  https://github.com/xippios/sdk-core/issues/485)
