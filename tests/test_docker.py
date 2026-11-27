"""The host's image workflow, ``docker.yml``: its three steps run against stubs, and its file.

Its one job, ``docker``, builds the image, smoke-tests it and, for a release alone, publishes it
to ``ghcr.io/xippios/xippios-mcp`` under the manifest's version without a ``v`` (the
maintainer's decisions of 2026-11-26 and 2026-11-27,
https://github.com/xippios/xippios-mcp/issues/38 and
https://github.com/xippios/xippios-mcp/issues/42). Each step's script runs here under
``bash -e``, as the runner runs it, with ``docker``, ``gh``, ``git`` and ``curl`` replaced by
stubs that record their arguments, so no test builds an image or reaches a registry.
"""

import os
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
DOCKER = WORKFLOWS / "docker.yml"
IMAGE = "ghcr.io/xippios/xippios-mcp"
SOURCE = "https://github.com/xippios/xippios-mcp"
LABEL = "org.opencontainers.image"
HEAD = "a" * 40
"""The commit that the stub of ``git`` names as the one checked out."""
OTHER = "b" * 40
RELEASE = {"EVENT": "workflow_run", "RUN_ID": "7", "STUB_PUBLISH": "success", "STUB_TAGGED": HEAD}
"""A run after a run of Publish whose job ``publish`` succeeded, its tag on the commit built."""

STUBS = {
    "docker": """printf 'docker\\t%s\\n' "$*" >> "$CALLS"
case "$1" in
  login) cat >> "$CALLS.stdin" ;;
  run) case "$*" in *--detach*) echo 0123 ;; esac ;;
esac
""",
    "gh": """printf 'gh\\t%s\\n' "$*" >> "$CALLS"
printf '%s\\n' "$STUB_PUBLISH"
""",
    "git": """printf 'git\\t%s\\n' "$*" >> "$CALLS"
case "$1" in
  rev-parse) echo "$STUB_HEAD" ;;
  ls-remote) if [ -n "$STUB_TAGGED" ]; then printf '%s\\t%s\\n' "$STUB_TAGGED" "$3"; fi ;;
esac
exit 0
""",
    "curl": """printf 'curl\\t%s\\n' "$*" >> "$CALLS"
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--dump-header" ]; then headers="$2"; fi
  shift
done
printf 'HTTP/1.1 %s\\r\\n%s\\r\\n' "$STUB_STATUS" "$STUB_CHALLENGE" > "$headers"
printf '%s' "$STUB_STATUS"
""",
}
"""Each stub records its arguments, one call a line, joined by tabs."""


@dataclass(frozen=True)
class Step:
    condition: str | None
    env: dict[str, str]
    script: str


@dataclass(frozen=True)
class Ran:
    status: int
    stdout: str
    calls: list[list[str]]
    output: dict[str, str]
    stdin: str


def _step(name: str) -> Step:
    """The step ``name`` of the job: its ``if``, its ``env`` and its script, dedented."""
    lines = DOCKER.read_text(encoding="utf-8").splitlines()
    assert f"      - name: {name}" in lines, f"docker.yml has no step {name}"
    start = lines.index(f"      - name: {name}") + 1
    end = next(
        (
            n
            for n in range(start, len(lines))
            if lines[n].startswith("      - ") or (lines[n] and not lines[n].startswith(" " * 8))
        ),
        len(lines),
    )
    block = lines[start:end]
    run = block.index("        run: |")
    condition = next((line[12:] for line in block[:run] if line.startswith("        if: ")), None)
    env = dict(re.findall(r"^ {10}([A-Z][A-Z0-9_]*): (.+)$", "\n".join(block[:run]), re.M))
    return Step(condition, env, "".join(f"{line[10:]}\n" for line in block[run + 1 :]))


def _run(name: str, tmp_path: Path, **env: str) -> Ran:
    """Step ``name``'s script under ``bash -e`` in the checkout, its commands stubbed."""
    work = tmp_path / name
    stubs = work / "bin"
    stubs.mkdir(parents=True)
    for command, body in STUBS.items():
        stub = stubs / command
        stub.write_text(f"#!/bin/sh\nIFS='\t'\n{body}", encoding="utf-8")
        stub.chmod(0o755)
    script = work / "step.sh"
    script.write_text(_step(name).script, encoding="utf-8")
    calls, output, stdin = work / "calls", work / "output", work / "calls.stdin"
    calls.touch()
    output.touch()
    done = subprocess.run(
        ["bash", "-e", str(script)],
        cwd=ROOT,
        env={
            "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
            "CALLS": str(calls),
            "GITHUB_OUTPUT": str(output),
            "GITHUB_REPOSITORY": "xippios/xippios-mcp",
            "GITHUB_ACTOR": "a-maintainer",
            "RUNNER_TEMP": str(work),
            "STUB_HEAD": HEAD,
            "STUB_STATUS": "401",
            "STUB_CHALLENGE": 'www-authenticate: Bearer realm="xippios-mcp"',
            **env,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return Ran(
        status=done.returncode,
        stdout=done.stdout,
        calls=[line.split("\t") for line in calls.read_text(encoding="utf-8").splitlines()],
        output=dict(
            line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines() if line
        ),
        stdin=stdin.read_text(encoding="utf-8") if stdin.exists() else "",
    )


def _build(ran: Ran) -> list[str]:
    [build] = [call for call in ran.calls if call[:2] == ["docker", "build"]]
    return build


def _values(call: list[str], option: str) -> list[str]:
    return [call[n + 1] for n, arg in enumerate(call) if arg == option]


def _labels(call: list[str]) -> dict[str, str]:
    labels = _values(call, "--label")
    found = dict(label.split("=", 1) for label in labels)
    assert len(found) == len(labels)
    return found


@pytest.fixture(scope="module")
def version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as file:
        found: str = tomllib.load(file)["project"]["version"]
    return found


def test_a_release_pushes_its_image_tagged_with_the_manifests_version(
    version: str, tmp_path: Path
) -> None:
    assert str(Version(version)) == version
    assert not version.startswith("v")
    built = _run("build", tmp_path, **RELEASE)
    assert built.status == 0, built.stdout
    jobs = '.jobs[] | select(.name == "publish") | .conclusion'
    assert ["gh", "api", "repos/xippios/xippios-mcp/actions/runs/7/jobs", "--jq", jobs] in (
        built.calls
    )
    assert ["git", "ls-remote", "origin", f"refs/tags/v{version}^{{}}"] in built.calls
    build = _build(built)
    assert _values(build, "--tag") == ["xippios-mcp:ci", f"{IMAGE}:{version}"]
    assert build[-1] == "."
    assert built.output == {"image": f"{IMAGE}:{version}"}

    token = "a-test-value"  # pragma: allowlist secret
    published = _run("publish", tmp_path, IMAGE=built.output["image"], TOKEN=token)
    assert published.status == 0, published.stdout
    assert published.calls == [
        ["docker", "login", "ghcr.io", "--username", "a-maintainer", "--password-stdin"],
        ["docker", "push", f"{IMAGE}:{version}"],
        ["docker", "logout", "ghcr.io"],
    ]
    assert published.stdin == f"{token}\n"


def test_the_released_image_carries_its_source_version_and_revision(
    version: str, tmp_path: Path
) -> None:
    assert _labels(_build(_run("build", tmp_path, **RELEASE))) == {
        f"{LABEL}.source": SOURCE,
        f"{LABEL}.revision": HEAD,
        f"{LABEL}.version": version,
    }


@pytest.mark.parametrize(
    "event",
    [
        pytest.param({"EVENT": "pull_request"}, id="a pull request"),
        pytest.param({"EVENT": "workflow_dispatch"}, id="a dispatch"),
        pytest.param(
            {"EVENT": "workflow_run", "RUN_ID": "8", "STUB_PUBLISH": "skipped"},
            id="a run of Publish that released nothing",
        ),
    ],
)
def test_a_build_of_no_release_publishes_nothing(event: dict[str, str], tmp_path: Path) -> None:
    built = _run("build", tmp_path, **event)
    assert built.status == 0, built.stdout
    build = _build(built)
    assert _values(build, "--tag") == ["xippios-mcp:ci"]
    assert _labels(build) == {f"{LABEL}.source": SOURCE, f"{LABEL}.revision": HEAD}
    assert built.output == {"image": ""}
    assert _step("publish").condition == "steps.build.outputs.image != ''"
    assert not [call for call in built.calls if call[:2] == ["git", "ls-remote"]]
    if event["EVENT"] != "workflow_run":
        assert not [call for call in built.calls if call[0] == "gh"]


@pytest.mark.parametrize("tagged", [OTHER, ""], ids=["another commit", "no tag"])
def test_a_release_whose_tag_names_another_commit_builds_nothing(
    tagged: str, tmp_path: Path
) -> None:
    built = _run("build", tmp_path, **{**RELEASE, "STUB_TAGGED": tagged})
    assert built.status == 1
    assert "does not name the commit built" in built.stdout
    assert not [call for call in built.calls if call[0] == "docker"]
    assert built.output == {}


@pytest.mark.parametrize(
    ("status", "challenge", "passes"),
    [
        pytest.param("401", 'www-authenticate: Bearer realm="xippios-mcp"', True, id="401"),
        pytest.param("401", "www-authenticate: Basic", False, id="401 without the bearer"),
        pytest.param("200", "", False, id="200"),
    ],
)
def test_the_smoke_step_expects_the_bearers_401_and_removes_its_container(
    status: str, challenge: str, passes: bool, tmp_path: Path
) -> None:
    smoked = _run("smoke", tmp_path, STUB_STATUS=status, STUB_CHALLENGE=challenge)
    assert (smoked.status == 0) is passes, smoked.stdout
    docker = [call[1:] for call in smoked.calls if call[0] == "docker"]
    assert docker[0] == ["run", "--rm", "xippios-mcp:ci", "--help"]
    assert docker[1][:2] == ["run", "--detach"]
    assert docker[1][-1] == "xippios-mcp:ci"
    assert docker[-2:] == [["logs", "xippios-mcp-smoke"], ["rm", "--force", "xippios-mcp-smoke"]]
    assert len([call for call in smoked.calls if call[0] == "curl"]) == (2 if passes else 1)


def test_the_workflow_runs_after_publish_on_its_commit_with_the_jobs_token() -> None:
    """No paths filter on ``pull_request``: the organization's ruleset requires ``docker``.

    A run on ``main`` has a concurrency group of its own, so no release's run waits behind
    another run of ``main`` or is cancelled by one.
    """
    workflows = {path.name: path.read_text(encoding="utf-8") for path in WORKFLOWS.glob("*.yml")}
    docker = workflows["docker.yml"]
    assert workflows["publish.yml"].startswith("name: Publish\n")
    assert (
        "\non:\n  pull_request:\n  workflow_run:\n    workflows: [Publish]\n"
        "    types: [completed]\n  workflow_dispatch:\n\npermissions:\n  contents: read\n"
    ) in docker
    assert (
        "\n  group: ${{ github.workflow }}-"
        "${{ github.ref == 'refs/heads/main' && github.run_id || github.ref }}\n"
    ) in docker
    assert "\n  docker:\n    name: docker\n" in docker
    assert (
        "\n    permissions:\n      contents: read\n      actions: read\n      packages: write\n"
    ) in docker
    assert (
        "\n          ref: ${{ github.event.workflow_run.head_sha }}\n"
        "          persist-credentials: false\n"
    ) in docker
    for marker in ("packages: write", "docker login", "docker push"):
        assert {name for name, text in workflows.items() if marker in text} == {"docker.yml"}
        assert docker.count(marker) == 1, marker
    assert _step("build").env == {
        "EVENT": "${{ github.event_name }}",
        "RUN_ID": "${{ github.event.workflow_run.id }}",
        "GH_TOKEN": "${{ github.token }}",
    }
    assert _step("smoke").env == {}
    assert _step("publish").env == {
        "IMAGE": "${{ steps.build.outputs.image }}",
        "TOKEN": "${{ secrets.GITHUB_TOKEN }}",
    }
