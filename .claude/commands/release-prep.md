Prepare the release of xippios-mcp: $ARGUMENTS

Expected argument: the new version, e.g. `0.2.0`. This command prepares the release's
pull request and nothing else; that pull request is the release (the release train,
conventions §12). Once it is on `main`, `publish.yml` tags `v<version>` on the merge
commit, builds, and waits at the `pypi` environment until a maintainer approves the run;
then the trusted publisher uploads. The tag comes from that workflow alone.

The release's pull request changes only the files of conventions §12: `pyproject.toml`,
`uv.lock`, `CHANGELOG.md`, `README.md`, `CLAUDE.md` and the fragments under
`changelog/`, which it deletes. §12 also names `docs/handover.md`, which is sdk-core's
file and not one the host has. What a release needs beyond these files comes in a pull
request of its own before it, the removal of a git pin among it (step 1). A template
release is ported by hand in a pull request of its own as well, never in a release's, as
`## Scaffolded by hand` in `CLAUDE.md` says. The host has no packaged reference data, no
sibling check and no live tests: the packages' own live runs cover their tasks. The
release meets sdk-core's definition of done,
https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and its review
checklist, https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md; an
item written for a source (tasks, wrappers, fixtures, `docs/upstream/`) does not apply
to the host (sdk-core ADR-0026, decision 1).

1. **No git pin.** If `pyproject.toml` has a `[tool.uv.sources]` block, the host depends
   on an unreleased package and cannot be released as it is. Find the release that
   carries the pinned change (stop and report if there is none yet), and in a change of
   its own remove the block and raise the bound to that release: for xippios-core
   `~=X.Y.Z`, still one minor (conventions §12), for a source package its `>=` floor
   (sdk-core ADR-0026, decision 9). Then `uv lock`, the checks and a changelog fragment
   under `changelog/` that names the new bound, in a pull request of its own before the
   release's. `publish.yml` refuses to tag a pinned release as well.
2. SemVer check: pre-1.0, a breaking change bumps the minor. A change that breaks the
   host's public surface, its entry point, its options and its config keys among it, is
   a breaking change. Read the fragments under `changelog/` and what `## [Unreleased]`
   holds, where there is one, and confirm that the version matches them; say so in the
   pull request if it does not.
3. `pyproject.toml`: set `version`, the version `publish.yml` tags, then `uv lock`.
4. `CHANGELOG.md`: write `## [<version>] - <today>` in place of `## [Unreleased]`, or
   above the last release where there is none, and assemble its section from the
   fragments under `changelog/` and what `## [Unreleased]` held, as `changelog/README.md`
   lays it out. The repository keeps no script for it: copy each fragment's bullet into
   the section by hand, then delete the fragments it took; `changelog/README.md` stays.
   `publish.yml` tags only a version whose section has this heading, and the section
   becomes the tag's message. The date is the tag's, the day the pull request reaches
   `main`: if that slips to a later day, re-date the heading in a commit of its own
   before it.
5. README: the extras table, its lower bounds and tool counts, and the install snippets
   are current.
6. Run the checks,
   `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run pre-commit run --all-files`
   and `python3 scripts/adr_index.py --check`, then build the image and run it as
   `ci.yml`'s `docker` job does, since the image installs what `uv.lock` pins:
   `docker build -t xippios-mcp . && docker run --rm xippios-mcp --help`.
7. **The report.** The release's pull request names the version and the bump's reason.
   Then stop: once it is on `main`, `publish.yml` tags `v<version>` and waits for a
   maintainer's approval of the `pypi` run.
