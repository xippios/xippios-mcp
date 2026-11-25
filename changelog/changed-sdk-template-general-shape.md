- Takes by hand what sdk-template v0.3.4 gives a source, since no template renders the
  host: the README lists the documents the host follows under `## Documents`, its design
  decisions get `docs/adr/` with an index that `scripts/adr_index.py` writes, its dated
  reports `docs/reports/`, and its changelog entries are fragments under `changelog/`.
  `CLAUDE.md` and `/release-prep` say how a change is made and checked and name no tool
  for its pull request, and `.claude/settings.json` allows no push, no pull request and
  no merge. (https://github.com/xippios/sdk-template/releases/tag/v0.3.4,
  https://github.com/xippios/xippios-mcp/issues/16)
