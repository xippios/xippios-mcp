- The host is a render of sdk-template v0.5.0's general shape, where 0.1.0 was scaffolded by
  hand, so a template release reaches it by `copier update`: its CI, release train, changelog
  fragments under `changelog/`, decision records under `docs/adr/` with their index, dated
  reports under `docs/reports/`, the organization's checks and `/release-prep` are the
  template's, and the image builds in a workflow of the host's own, `docker.yml`. The README
  lists the documents the host follows under `## Documents` and says what each workflow does
  under `## Workflows`, and `.claude/settings.json` allows no push, no pull request and no
  merge. The host depends on `xippios-core[mcp]~=0.5.0`, is updated to sdk-template v0.5.0
  and applies conventions 1.30.
  (https://github.com/xippios/sdk-template/releases/tag/v0.5.0,
  https://github.com/xippios/xippios-mcp/issues/16,
  https://github.com/xippios/xippios-mcp/issues/25)
