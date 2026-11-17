- The workflow `gates.yml` is gone: it called two checks of a repository that no longer
  exists and failed at its start on every pull request. `organization.yml` calls the
  organization's checks in its place, the `ci` check accepts a fragment under `changelog/`
  as the entry, and the pull request template asks what a change was checked against.
  (https://github.com/xippios/xippios-mcp/issues/13,
  https://github.com/xippios/xippios-mcp/issues/15)
