Prepare the release of xippios-mcp: $ARGUMENTS

Expected argument: the new version, e.g. `0.2.0`. This command prepares the release PR
and nothing else; its merge is the release (the release train, conventions §12). The
merge runs `publish.yml`, which tags `v<version>` on the merge commit, builds, and waits
at the `pypi` environment until Johannes approves the run. No session and no human pushes
the tag.

A release PR changes only `pyproject.toml`, `uv.lock`, `CHANGELOG.md`, `README.md`,
`CLAUDE.md` and `docs/handover.md`, the subset of conventions §12; the `merge-class` check
makes any other changed path `human`. What a release needs beyond the subset is a PR of
its own, merged before this one. The host has no packaged reference data, no sibling
check and no live tests. The PR meets the definition of done,
https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and the
reviewer judges it against
https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md; the items
written for a source are not applicable (ADR-0026, decision 1; queue row 302).

1. **No git pin.** If `pyproject.toml` has a `[tool.uv.sources]` block, the host cannot
   be released as it is: remove it, with the bound it needs, in a PR of its own, merged
   before this one. `publish.yml` refuses to tag a release with the block as well.
2. Work on a branch `chore/release-<version>` from an up-to-date `main`. If `main` moves
   while the PR is open, merge `origin/main` into the branch, never force-push; the
   squash merge flattens the merge commit.
3. SemVer check: pre-1.0, a breaking change bumps the minor. A change that breaks the
   host's public surface, its entry point and options among it, is a breaking change.
   Read `CHANGELOG.md`
   Unreleased and confirm the version matches what is in it; say so in the PR if it does
   not.
4. `pyproject.toml`: set `version`, the version `publish.yml` tags, then `uv lock`. A
   first release keeps the scaffold's `0.1.0`: its CHANGELOG section alone makes the
   merge a release.
5. `CHANGELOG.md`: move everything under Unreleased into a `## [<version>] - <today>`
   section, leave an empty Unreleased above it. `publish.yml` tags only a version whose
   section has this heading, and the section becomes the tag's message, so it says
   internal labels (decisions, queue rows, plan items) in plain words. The date is the
   merge's, which is the tag's: if the merge slips to a later day, re-date the heading in
   a commit of its own before it.
6. README: the extras table and the install snippets are current.
7. Run the full suite: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run pre-commit run --all-files`.
8. Open the PR, its body as the definition of done says. After the reviewer's `ready`,
   if the `merge-class` check says `auto`, the session enables auto-merge here, as
   `.claude/settings.json` allows; every other `gh pr merge` meets the permission
   prompt: `gh pr merge --auto --squash -R xippios/xippios-mcp <number>`. GitHub merges
   once `ci` is green and review threads are resolved; a `human` release waits for
   Johannes (ADR-0018, amendment (e)). Then stop and report: the merge tags
   `v<version>` through `publish.yml`, and Johannes approves the `pypi` run in the
   Actions tab. A first release needs the PyPI pending publisher (owner xippios,
   repository xippios-mcp, workflow `publish.yml`, environment `pypi`) before that
   approval; name it in the report if the release is `0.1.0`.
