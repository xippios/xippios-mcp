Prepare the release of xippios-mcp: $ARGUMENTS

Expected argument: the new version, e.g. `0.2.0`. This command prepares the release's
pull request and nothing else; that pull request is the release (the release train,
conventions §12). Once it is on `main`, `publish.yml` tags `v<version>` on the merge
commit, builds, and waits at the `pypi` environment until a maintainer approves the run;
then the trusted publisher uploads. The tag comes from that workflow alone.

The release's pull request changes only the files of conventions §12: `pyproject.toml`,
`uv.lock`, `CHANGELOG.md`, `README.md`, `CLAUDE.md` and the fragments under
`changelog/`, which it deletes. §12 also names `docs/handover.md`, which is sdk-core's
file and not one this package must have. A template release is taken in a pull request of
its own, never in a release's:
`uvx --from 'copier>=9.19' copier update --defaults --vcs-ref=<tag>`, its conflicts resolved
and the Hand-apply entries of sdk-template's `CHANGELOG.md` since the tag
`.copier-answers.yml` names ported by hand (conventions §15). `pyproject.toml` is this
package's own, which no update writes: a new core minor raises its bound there by hand in
that pull request, and a pin of core leaves it by hand in a pull request of its own before
the release's, since `publish.yml` refuses to tag a pinned release. The pull request of the
update has a fragment that names the core bound, the template's tag and the conventions'
version as they stand after the update, changed or not, and is `breaking` where the update
brings a core minor and `changed` where it brings none (conventions §15 item 9). The release
meets sdk-core's definition of done,
https://github.com/xippios/sdk-core/blob/main/docs/definition-of-done.md, and its review
checklist, https://github.com/xippios/sdk-core/blob/main/docs/review-checklist.md.

1. **SemVer**, by conventions §12: an adoption of a core minor is a breaking
   change, whatever else the release brings, and its fragment is `breaking`. Read the
   fragments under `changelog/` and what `## [Unreleased]` holds, which
   `python3 -I scripts/changelog_assemble.py --notes` prints as the section will hold
   them, writing nothing, and confirm that the version matches them; say so in the pull
   request if it does not.
2. **The version.** `version` in `pyproject.toml` is the version `publish.yml` tags, and
   `uv.lock` holds it on this package's own entry. Step 3's script sets both and runs no
   `uv lock`, so the release builds nothing and reaches no index. A first release keeps
   the scaffold's `0.1.0`: its CHANGELOG section alone makes it a release.
3. **The section.** Run
   `python3 -I scripts/release_prepare.py <version> --date <YYYY-MM-DD>`, the date
   today's in UTC. It writes `## [<version>] - <date>` into `CHANGELOG.md` in place of
   `## [Unreleased]`, or above the last release where there is none, assembles its section
   from the fragments under `changelog/` and what `## [Unreleased]` held, as
   `changelog/README.md` lays it out, deletes the fragments it took, the README kept, and
   sets the version of step 2. The release rewords and regroups no entry: a wrong one
   is corrected in its fragment, by a pull request before the release's (conventions §12).
   `publish.yml` tags only a version whose section has this heading, and the section
   becomes the tag's message. The date is the tag's, the day the pull request reaches
   `main`: if that slips to a later day, the same command with that day's `--date`
   re-dates the heading alone, in a commit of its own before it.
4. README: install snippets are current.
5. Run the checks,
   `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest && uv run pre-commit run --all-files`.
6. **The report.** The release's pull request names the version. Then stop: once it is on
   `main`, `publish.yml` tags `v<version>` and waits for a maintainer's approval of the
   `pypi` run. A first release needs PyPI's pending publisher before that approval, with
   project name `xippios-mcp`, the distribution's name in `pyproject.toml`,
   owner `xippios`, repository `xippios-mcp`, workflow `publish.yml` and
   environment `pypi`: a publisher that names another project fails the upload for good,
   the tag stands without a release, and only a patch release recovers. Name the
   publisher in the report if the release is `0.1.0`.
