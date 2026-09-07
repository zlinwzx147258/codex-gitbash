#!/usr/bin/env python3
"""Tests for .github/workflows/gitbash-upstream-build.yml.

The structural tests pin the safety properties of the pipeline (read-only
build, exact compare-and-swap advance, no privileged token where it is not
needed). The fixture tests execute the workflow's own shell blocks against
throwaway git repositories so the bundle/advance logic is verified for real.
"""

import os
import re
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "gitbash-upstream-build.yml"
CHECKS_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "gitbash-checks.yml"
LAUNCHER_PATH = ROOT / "gitbash" / "codex-gitbash.sh"
PACKAGE_README_PATH = ROOT / "gitbash" / "README-package.md"
CHECKOUT_SHA = "de0fac2e4500dabe0009e67214ff5f5447ce83dd"
DOWNLOAD_ARTIFACT_SHA = "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"
UPLOAD_ARTIFACT_SHA = "bbbca2ddaa5d8feaa63e36b76fdaad77386f024f"
EXPLICIT_LEASE_PUSH = (
    'git push --force-with-lease="refs/heads/main:$PATCH_BASE_SHA" '
    'origin "$SOURCE_SHA_FULL:refs/heads/main"'
)
JOB_NAMES = ("sync", "build", "release", "advance_main", "report")


def indentation(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def extract_named_steps(text: str) -> dict[str, str]:
    lines = text.splitlines()
    steps: dict[str, str] = {}
    for index, line in enumerate(lines):
        match = re.match(r"^( +)- name:\s*(.+?)\s*$", line)
        if match is None:
            continue

        step_indent = len(match.group(1))
        end = index + 1
        while end < len(lines):
            candidate = lines[end]
            if candidate.strip() and indentation(candidate) <= step_indent:
                break
            end += 1

        name = match.group(2)
        if name in steps:
            raise AssertionError(f"duplicate step name within one job: {name}")
        steps[name] = "\n".join(lines[index:end])
    return steps


def extract_named_run_blocks(text: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for name, step in extract_named_steps(text).items():
        lines = step.splitlines()
        for index, line in enumerate(lines):
            match = re.match(r"^( +)run:\s*\|\s*$", line)
            if match is None:
                continue

            run_indent = len(match.group(1))
            block_lines: list[str] = []
            for candidate in lines[index + 1 :]:
                if candidate.strip() and indentation(candidate) <= run_indent:
                    break
                block_lines.append(candidate)
            blocks[name] = textwrap.dedent("\n".join(block_lines)).strip() + "\n"
            break
    return blocks


def extract_job(workflow: str, job_name: str) -> str:
    lines = workflow.splitlines()
    marker = f"  {job_name}:"
    try:
        start = lines.index(marker)
    except ValueError as error:
        raise AssertionError(f"missing workflow job: {job_name}") from error

    end = start + 1
    while end < len(lines):
        if re.match(r"^  [A-Za-z0-9_-]+:\s*$", lines[end]):
            break
        end += 1
    return "\n".join(lines[start:end])


def compact_whitespace(value: str) -> str:
    return " ".join(value.split())


class GitRepositoryFixture:
    """A bare `origin`, a `build` clone with a rebased main, and helpers."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.remote = root / "origin.git"
        self.seed = root / "seed"
        self.build = root / "build"
        self.bundle_name = "rebased-source.bundle"

        self.git(root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.git(root, "init", "--initial-branch=main", str(self.seed))
        self.configure_identity(self.seed)

        self.write(self.seed, "shared.txt", "root\n")
        self.commit(self.seed, "root")
        self.write(self.seed, "upstream.txt", "old upstream\n")
        self.commit(self.seed, "old upstream")
        self.old_upstream_sha = self.rev_parse(self.seed, "HEAD")
        self.write(self.seed, "gitbash.patch", "git bash patch\n")
        self.commit(self.seed, "git bash patch")
        self.patch_base_sha = self.rev_parse(self.seed, "HEAD")
        self.git(self.seed, "remote", "add", "origin", str(self.remote))
        self.git(self.seed, "push", "origin", "main")

        self.git(root, "clone", str(self.remote), str(self.build))
        self.configure_identity(self.build)
        self.git(self.build, "branch", "upstream-next", self.old_upstream_sha)
        self.git(self.build, "switch", "upstream-next")
        self.write(self.build, "upstream.txt", "new upstream\n")
        self.commit(self.build, "new upstream")
        self.upstream_sha = self.rev_parse(self.build, "HEAD")
        self.git(self.build, "switch", "main")
        self.git(
            self.build,
            "rebase",
            "--onto",
            self.upstream_sha,
            self.old_upstream_sha,
            "main",
        )
        self.source_sha = self.rev_parse(self.build, "HEAD")

    def configure_identity(self, repository: Path) -> None:
        self.git(repository, "config", "user.name", "Workflow Test")
        self.git(repository, "config", "user.email", "workflow@example.com")

    def write(self, repository: Path, path: str, contents: str) -> None:
        (repository / path).write_text(contents, encoding="utf-8")

    def commit(self, repository: Path, message: str) -> None:
        self.git(repository, "add", ".")
        self.git(repository, "commit", "-m", message)

    def clone_for_advance(self, name: str = "advance") -> Path:
        checkout = self.root / name
        self.git(self.root, "clone", str(self.remote), str(checkout))
        self.configure_identity(checkout)
        bundle_dir = checkout / "source-bundle"
        bundle_dir.mkdir()
        shutil.copy2(
            self.build / "source-bundle" / self.bundle_name,
            bundle_dir / self.bundle_name,
        )
        return checkout

    def create_competing_commit(self) -> str:
        competitor = self.root / "competitor"
        self.git(self.root, "clone", str(self.remote), str(competitor))
        self.configure_identity(competitor)
        self.write(competitor, "race.txt", "competing main\n")
        self.commit(competitor, "competing main")
        competing_sha = self.rev_parse(competitor, "HEAD")
        self.git(competitor, "push", "origin", "main")
        return competing_sha

    def remote_main(self) -> str:
        return self.git_output(
            self.root,
            "--git-dir",
            str(self.remote),
            "rev-parse",
            "refs/heads/main",
        )

    def rev_parse(self, repository: Path, revision: str) -> str:
        return self.git_output(repository, "rev-parse", revision)

    def git(self, repository: Path, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        )

    def git_output(self, repository: Path, *args: str) -> str:
        return subprocess.check_output(
            ["git", *args],
            cwd=repository,
            stderr=subprocess.PIPE,
            text=True,
        ).strip()


class GitBashUpstreamWorkflowStructureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.jobs = {name: extract_job(cls.workflow, name) for name in JOB_NAMES}
        cls.steps = {name: extract_named_steps(job) for name, job in cls.jobs.items()}
        cls.run_blocks = {
            name: extract_named_run_blocks(job) for name, job in cls.jobs.items()
        }

    def test_workflow_is_read_only_by_default_and_serialized(self) -> None:
        head = self.workflow.split("jobs:", 1)[0]
        self.assertIn("permissions:\n  contents: read", head)
        self.assertIn("group: gitbash-upstream-build", head)
        self.assertIn("cancel-in-progress: false", head)
        self.assertIn('cron: "17 3 * * *"', head)
        self.assertIn("force_build:", head)

    def test_sync_rebases_reproducibly_and_reports_conflicts(self) -> None:
        job = self.jobs["sync"]
        step = self.steps["sync"]["Rebase the patch onto openai/codex main"]
        sync = self.run_blocks["sync"]["Rebase the patch onto openai/codex main"]

        self.assertIn("runs-on: ubuntu-latest", job)
        self.assertIn(f"uses: actions/checkout@{CHECKOUT_SHA}", job)
        self.assertIn("ref: main", job)
        self.assertIn("fetch-depth: 0", job)
        self.assertIn("persist-credentials: false", job)
        self.assertIn("GH_TOKEN: ${{ github.token }}", step)
        self.assertNotIn("GITBASH_RELEASE_TOKEN", job)

        self.assertIn("git rebase --committer-date-is-author-date upstream/main", sync)
        self.assertIn("rebase_state=conflict", sync)
        self.assertIn("git diff --name-only --diff-filter=U", sync)
        self.assertIn("git rebase --abort", sync)
        self.assertIn("conflicted_files<<CONFLICTS", sync)
        self.assertRegex(
            sync,
            re.compile(r'if \[\[ "\$rebase_state" == conflict \]\]; then.*?exit 1', re.S),
        )

    def test_sync_dedupes_by_source_archive_across_paginated_releases(self) -> None:
        step = self.steps["sync"]["Rebase the patch onto openai/codex main"]
        sync = self.run_blocks["sync"]["Rebase the patch onto openai/codex main"]

        self.assertIn("FORCE_BUILD: ${{ inputs.force_build }}", step)
        self.assertIn("gh api --paginate", sync)
        self.assertIn('"repos/$GITHUB_REPOSITORY/releases?per_page=100"', sync)
        self.assertIn(".[] | .assets[]?.name", sync)
        self.assertIn('grep -Fxq "$archive_name"', sync)
        self.assertNotIn("releases/tags/$tag", sync)
        self.assertRegex(
            sync,
            re.compile(r'if \[\[ "\$FORCE_BUILD" == "true" \]\]; then\s+should_build=true'),
        )

    def test_sync_exports_outputs_and_source_bundle(self) -> None:
        job = self.jobs["sync"]
        for output in (
            "rebase_state",
            "conflicted_files",
            "should_build",
            "should_advance",
            "patch_base_sha",
            "source_sha",
            "source_sha_full",
            "upstream_sha",
            "upstream_date",
            "artifact_name",
            "archive_name",
            "source_bundle_artifact",
            "source_bundle_name",
            "tag",
        ):
            with self.subTest(output=output):
                self.assertIn(
                    f"{output}: ${{{{ steps.sync.outputs.{output} }}}}", job
                )

        sync = self.run_blocks["sync"]["Rebase the patch onto openai/codex main"]
        self.assertIn(
            'should_advance=false\nif [[ "$source_sha_full" != "$patch_base_sha" ]]; then\n  should_advance=true\nfi',
            sync,
        )

        create_step = self.steps["sync"]["Create and verify rebased source bundle"]
        upload_step = self.steps["sync"]["Upload rebased source bundle"]
        for step in (create_step, upload_step):
            self.assertIn("if: ${{ steps.sync.outputs.should_advance == 'true' }}", step)
            self.assertNotIn("should_build", step)
        self.assertIn(f"uses: actions/upload-artifact@{UPLOAD_ARTIFACT_SHA}", upload_step)
        self.assertIn("retention-days: 1", upload_step)

    def test_build_uses_exact_source_and_follows_upstream_toolchain(self) -> None:
        job = self.jobs["build"]
        self.assertIn("needs: sync", job)
        self.assertIn("if: ${{ needs.sync.outputs.should_build == 'true' }}", job)
        self.assertIn("runs-on: windows-latest", job)
        self.assertIn("permissions:\n      contents: read", job)
        self.assertNotIn("GITBASH_RELEASE_TOKEN", job)
        self.assertNotIn("contents: write", job)

        checkout = self.run_blocks["build"]["Check out the exact rebased source"]
        self.assertIn('git bundle verify "$bundle_path"', checkout)
        self.assertIn('git fetch --no-tags "$bundle_path" refs/heads/main', checkout)
        self.assertIn('git merge-base --is-ancestor "$UPSTREAM_SHA" "$actual_source"', checkout)
        self.assertIn('git checkout --detach "$actual_source"', checkout)
        self.assertIn('[[ "$(git rev-parse HEAD)" != "$SOURCE_SHA_FULL" ]]', checkout)

        toolchain = self.run_blocks["build"]["Read the Rust toolchain pinned by upstream"]
        self.assertIn("codex-rs/rust-toolchain.toml", toolchain)
        install = self.steps["build"]["Install Rust toolchain"]
        self.assertIn("toolchain: ${{ steps.toolchain.outputs.channel }}", install)
        self.assertIn("targets: ${{ env.RELEASE_TARGET }}", install)

        v8 = self.steps["build"]["Configure rusty_v8 artifact overrides and verify checksums"]
        self.assertIn("uses: ./.github/actions/setup-rusty-v8", v8)
        self.assertIn("target: ${{ env.RELEASE_TARGET }}", v8)

        cache = self.steps["build"]["Restore Cargo registry and dependency build cache"]
        self.assertIn("uses: Swatinem/rust-cache@", cache)
        self.assertIn("workspaces: codex-rs -> target", cache)
        self.assertIn("cache-on-failure: true", cache)

    def test_build_smoke_tests_and_packages_launcher_from_the_tree(self) -> None:
        build = self.run_blocks["build"]["Build patched Codex CLI"]
        self.assertIn("LIBSQLITE3_FLAGS=SQLITE_DISABLE_INTRINSIC", build)
        # A restored cache can keep the `v8` fingerprint while dropping the
        # unpacked prebuilt, which breaks linking; rebuild that crate every run.
        self.assertIn('cargo clean --target "$RELEASE_TARGET" --release -p v8', build)
        # Binaries are selected by name only; `-p <crate>` breaks whenever
        # upstream renames a crate (windows-sandbox-rs -> codex-windows-sandbox).
        self.assertNotIn("-p codex", build)
        for binary in (
            "--bin codex",
            "--bin codex-code-mode-host",
            "--bin codex-command-runner",
            "--bin codex-windows-sandbox-setup",
        ):
            self.assertIn(binary, build)

        smoke = self.run_blocks["build"]["Smoke-test the build through the Git Bash launcher"]
        self.assertIn('"$release_dir/codex.exe" --version', smoke)
        self.assertIn("cp gitbash/codex-gitbash.sh", smoke)
        self.assertIn("./codex-gitbash.sh --version", smoke)

        package = self.run_blocks["build"]["Package Git Bash launcher"]
        for helper in (
            "codex-code-mode-host.exe",
            "codex-command-runner.exe",
            "codex-windows-sandbox-setup.exe",
        ):
            self.assertIn(f'cp "$release_dir/{helper}" "$output_dir/{helper}"', package)
        self.assertIn('cp "$release_dir/codex.exe" "$output_dir/codex-gitbash.exe"', package)
        self.assertIn('cp gitbash/codex-gitbash.sh "$output_dir/codex-gitbash.sh"', package)
        self.assertIn('cp gitbash/README-package.md "$output_dir/README-gitbash.md"', package)
        self.assertIn(
            "sha256sum codex-gitbash.exe codex-code-mode-host.exe codex-command-runner.exe codex-windows-sandbox-setup.exe codex-gitbash.sh README-gitbash.md BUILD-METADATA.txt > SHA256SUMS.txt",
            package,
        )
        self.assertIn("sha256sum -c SHA256SUMS.txt", package)
        for key in (
            "patch_baseline_commit=$PATCH_BASE_SHA",
            "upstream_main_commit=$UPSTREAM_SHA",
            "upstream_main_date=$UPSTREAM_DATE",
            "rebased_source_commit=$SOURCE_SHA_FULL",
            "codex_version=",
        ):
            self.assertIn(key, package)

    def test_release_publishes_verified_archive_as_latest(self) -> None:
        job = self.jobs["release"]
        release = self.run_blocks["release"]["Create or update the release"]

        self.assertIn("needs: [sync, build]", job)
        self.assertIn("if: ${{ needs.build.result == 'success' }}", job)
        self.assertIn("runs-on: ubuntu-latest", job)
        self.assertIn("contents: write", job)
        self.assertIn("GH_TOKEN: ${{ secrets.GITBASH_RELEASE_TOKEN || github.token }}", job)
        self.assertNotIn("actions/checkout", job)
        self.assertIn(f"uses: actions/download-artifact@{DOWNLOAD_ARTIFACT_SHA}", job)

        self.assertIn("sha256sum -c SHA256SUMS.txt", release)
        self.assertIn('gh release create "$TAG" "$ARCHIVE"', release)
        self.assertIn('--target "$PATCH_BASE_SHA"', release)
        self.assertIn("--latest", release)
        self.assertIn(
            'title="Codex Git Bash for Windows $UPSTREAM_DATE ($SOURCE_SHA)"', release
        )
        self.assertIn('gh release upload "$TAG" "$ARCHIVE" --clobber', release)
        self.assertNotIn("--prerelease\n", release)

    def test_advance_job_has_exact_gating_permissions_and_lease(self) -> None:
        job = self.jobs["advance_main"]
        compact = compact_whitespace(job)

        self.assertIn("needs: [sync, build, release]", job)
        self.assertIn("always()", job)
        self.assertIn("needs.sync.result == 'success'", job)
        self.assertIn("needs.sync.outputs.should_advance == 'true'", job)
        self.assertIn("github.repository == 'zlinwzx147258/codex-gitbash'", job)
        self.assertIn("github.ref == 'refs/heads/main'", job)
        self.assertIn(
            "needs.release.result == 'success' || ( needs.release.result == 'skipped' && needs.sync.outputs.should_build == 'false' )",
            compact,
        )
        self.assertIn("runs-on: ubuntu-latest", job)
        self.assertIn("permissions: actions: read contents: write", compact)
        self.assertNotIn("GITBASH_RELEASE_TOKEN", job)
        self.assertIn(f"uses: actions/checkout@{CHECKOUT_SHA}", job)
        self.assertIn("ref: main", job)
        self.assertIn("fetch-depth: 0", job)
        self.assertIn("token: ${{ github.token }}", job)
        self.assertIn(f"uses: actions/download-artifact@{DOWNLOAD_ARTIFACT_SHA}", job)
        self.assertIn("name: ${{ needs.sync.outputs.source_bundle_artifact }}", job)

        push_step = self.steps["advance_main"]["Advance main with exact compare-and-swap"]
        push = self.run_blocks["advance_main"]["Advance main with exact compare-and-swap"]
        self.assertIn(
            "if: ${{ steps.prepare.outputs.already_advanced != 'true' }}", push_step
        )
        self.assertIn(EXPLICIT_LEASE_PUSH, push)
        self.assertEqual(push.count("git push "), 1)
        self.assertIsNone(re.search(r"(?:^|\s)--force(?:\s|$)", push))

        prepare = self.run_blocks["advance_main"]["Prepare exact rebased source"]
        self.assertNotIn("GITBASH_RELEASE_TOKEN", prepare)
        self.assertNotIn("GH_TOKEN", prepare)
        self.assertNotRegex(prepare, r"(?:^|\s)(?:\./)?\.github/")
        self.assertNotRegex(prepare, r"(?:^|\s)(?:python|just)(?:\s|$)")

    def test_report_job_tracks_failures_in_an_issue(self) -> None:
        job = self.jobs["report"]
        report = self.run_blocks["report"]["Open, update or close the tracking issue"]

        self.assertIn("needs: [sync, build, release, advance_main]", job)
        self.assertIn("always()", job)
        self.assertIn("permissions:\n      issues: write", job)
        self.assertNotIn("contents: write", job)
        self.assertNotIn("actions/checkout", job)
        self.assertIn("GH_TOKEN: ${{ github.token }}", job)

        self.assertIn('title="Automated Git Bash build is failing"', report)
        self.assertIn("gh issue list --state open", report)
        self.assertIn('gh issue close "$existing"', report)
        self.assertIn('gh issue comment "$existing"', report)
        self.assertIn('gh issue create --title "$title"', report)
        self.assertIn('if [[ "$REBASE_STATE" == conflict ]]; then', report)
        self.assertIn('gh api "repos/$GH_REPO" --jq .has_issues', report)


class GitBashLauncherAssetsTest(unittest.TestCase):
    def test_launcher_and_package_readme_exist_and_agree(self) -> None:
        launcher = LAUNCHER_PATH.read_text(encoding="utf-8")
        readme = PACKAGE_README_PATH.read_text(encoding="utf-8")

        self.assertTrue(launcher.startswith("#!/usr/bin/env bash\n"))
        self.assertIn("set -euo pipefail", launcher)
        self.assertIn("windows.agent_shell=\"git-bash\"", launcher)
        self.assertIn("CODEX_GITBASH_EXE", launcher)
        self.assertIn('"$script_dir/codex-gitbash.exe"', launcher)
        self.assertNotIn("/c/Program Files/Git", launcher)
        self.assertNotIn("\r", launcher)

        for name in (
            "codex-gitbash.sh",
            "codex-gitbash.exe",
            "codex-code-mode-host.exe",
            "codex-command-runner.exe",
            "codex-windows-sandbox-setup.exe",
            "BUILD-METADATA.txt",
            "SHA256SUMS.txt",
        ):
            with self.subTest(name=name):
                self.assertIn(name, readme)

    def test_checks_workflow_runs_tests_and_lints_launcher(self) -> None:
        checks = CHECKS_WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", checks)
        self.assertIn(
            "shellcheck --severity=warning gitbash/codex-gitbash.sh gitbash/fetch-rusty-v8.sh",
            checks,
        )
        self.assertIn("./gitbash/fetch-rusty-v8.sh x86_64-pc-windows-msvc", checks)
        self.assertIn(
            "python3 -m unittest discover -s .github/scripts -p 'test_gitbash_*.py'",
            checks,
        )
        self.assertIn("runs-on: windows-latest", checks)
        self.assertIn("CODEX_GITBASH_EXE=", checks)
        self.assertIn("cargo test -p codex-shell-command", checks)
        self.assertIn('CODEX_REQUIRE_GIT_BASH: "1"', checks)


@unittest.skipUnless(
    shutil.which("git") and shutil.which("bash"), "git and bash required"
)
class GitBashUpstreamWorkflowFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.sync_blocks = extract_named_run_blocks(extract_job(workflow, "sync"))
        cls.build_blocks = extract_named_run_blocks(extract_job(workflow, "build"))
        cls.advance_blocks = extract_named_run_blocks(
            extract_job(workflow, "advance_main")
        )

    def test_successful_compare_and_swap_advances_main(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fixture = GitRepositoryFixture(Path(temp_dir))
            self.run_bundle_block(fixture)
            advance = fixture.clone_for_advance()

            prepare = self.run_prepare_block(fixture, advance)
            self.assertEqual(prepare.returncode, 0, prepare.stderr)
            self.assertIn(
                "already_advanced=false",
                (advance / "github-output.txt").read_text(encoding="utf-8"),
            )
            self.assertEqual(fixture.rev_parse(advance, "HEAD"), fixture.source_sha)
            symbolic_head = subprocess.run(
                ["git", "symbolic-ref", "-q", "HEAD"],
                cwd=advance,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(symbolic_head.returncode, 0)

            push = self.run_push_block(fixture, advance)
            self.assertEqual(push.returncode, 0, push.stderr)
            self.assertEqual(fixture.remote_main(), fixture.source_sha)

    def test_build_checks_out_exact_rebased_source_from_bundle(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fixture = GitRepositoryFixture(Path(temp_dir))
            self.run_bundle_block(fixture)
            build_checkout = fixture.clone_for_advance("build-checkout")

            result = self.run_build_checkout_block(fixture, build_checkout)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                fixture.rev_parse(build_checkout, "HEAD"), fixture.source_sha
            )

            wrong_source = fixture.clone_for_advance("build-wrong-source")
            result = self.run_build_checkout_block(
                fixture, wrong_source, source_sha=fixture.upstream_sha
            )
            self.assertNotEqual(result.returncode, 0)

    def test_build_checkout_without_bundle_requires_unchanged_baseline(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fixture = GitRepositoryFixture(Path(temp_dir))
            self.run_bundle_block(fixture)
            checkout = fixture.clone_for_advance("build-no-advance")

            unchanged = self.run_build_checkout_block(
                fixture,
                checkout,
                source_sha=fixture.patch_base_sha,
                should_advance="false",
            )
            self.assertEqual(unchanged.returncode, 0, unchanged.stderr)
            self.assertEqual(
                fixture.rev_parse(checkout, "HEAD"), fixture.patch_base_sha
            )

            mismatch = self.run_build_checkout_block(
                fixture, checkout, should_advance="false"
            )
            self.assertNotEqual(mismatch.returncode, 0)

    def test_already_advanced_main_is_verified_without_push(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fixture = GitRepositoryFixture(Path(temp_dir))
            self.run_bundle_block(fixture)
            first_advance = fixture.clone_for_advance("first-advance")
            prepare = self.run_prepare_block(fixture, first_advance)
            self.assertEqual(prepare.returncode, 0, prepare.stderr)
            push = self.run_push_block(fixture, first_advance)
            self.assertEqual(push.returncode, 0, push.stderr)

            already_advanced = fixture.clone_for_advance("already-advanced")
            prepare = self.run_prepare_block(fixture, already_advanced)

            self.assertEqual(prepare.returncode, 0, prepare.stderr)
            self.assertIn(
                "already_advanced=true",
                (already_advanced / "github-output.txt").read_text(encoding="utf-8"),
            )
            self.assertEqual(fixture.remote_main(), fixture.source_sha)

    def test_remote_race_rejects_push_and_preserves_competing_main(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fixture = GitRepositoryFixture(Path(temp_dir))
            self.run_bundle_block(fixture)
            advance = fixture.clone_for_advance()
            prepare = self.run_prepare_block(fixture, advance)
            self.assertEqual(prepare.returncode, 0, prepare.stderr)

            competing_sha = fixture.create_competing_commit()
            push = self.run_push_block(fixture, advance)

            self.assertNotEqual(push.returncode, 0)
            self.assertEqual(fixture.remote_main(), competing_sha)

    def test_source_mismatch_fails_before_push(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fixture = GitRepositoryFixture(Path(temp_dir))
            self.run_bundle_block(fixture)
            advance = fixture.clone_for_advance()

            prepare = self.run_prepare_block(
                fixture,
                advance,
                source_sha=fixture.upstream_sha,
            )

            self.assertNotEqual(prepare.returncode, 0)
            self.assertEqual(fixture.remote_main(), fixture.patch_base_sha)

    def run_bundle_block(self, fixture: GitRepositoryFixture) -> None:
        result = self.run_shell(
            self.sync_blocks["Create and verify rebased source bundle"],
            fixture.build,
            {
                "PATCH_BASE_SHA": fixture.patch_base_sha,
                "SOURCE_SHA_FULL": fixture.source_sha,
                "SOURCE_BUNDLE_NAME": fixture.bundle_name,
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def run_build_checkout_block(
        self,
        fixture: GitRepositoryFixture,
        checkout: Path,
        *,
        source_sha: str | None = None,
        should_advance: str = "true",
    ) -> subprocess.CompletedProcess[str]:
        return self.run_shell(
            self.build_blocks["Check out the exact rebased source"],
            checkout,
            {
                "PATCH_BASE_SHA": fixture.patch_base_sha,
                "SOURCE_SHA_FULL": source_sha or fixture.source_sha,
                "UPSTREAM_SHA": fixture.upstream_sha,
                "SHOULD_ADVANCE": should_advance,
                "SOURCE_BUNDLE_NAME": fixture.bundle_name,
            },
        )

    def run_prepare_block(
        self,
        fixture: GitRepositoryFixture,
        checkout: Path,
        *,
        source_sha: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self.run_shell(
            self.advance_blocks["Prepare exact rebased source"],
            checkout,
            {
                "PATCH_BASE_SHA": fixture.patch_base_sha,
                "SOURCE_SHA_FULL": source_sha or fixture.source_sha,
                "UPSTREAM_SHA": fixture.upstream_sha,
                "SOURCE_BUNDLE_NAME": fixture.bundle_name,
                "GITHUB_OUTPUT": "github-output.txt",
                "GITHUB_STEP_SUMMARY": "summary.md",
            },
        )

    def run_push_block(
        self,
        fixture: GitRepositoryFixture,
        checkout: Path,
    ) -> subprocess.CompletedProcess[str]:
        return self.run_shell(
            self.advance_blocks["Advance main with exact compare-and-swap"],
            checkout,
            {
                "PATCH_BASE_SHA": fixture.patch_base_sha,
                "SOURCE_SHA_FULL": fixture.source_sha,
                "ADVANCE_PUSH_ATTEMPTS": "1",
                "ADVANCE_PUSH_RETRY_SECONDS": "0",
            },
        )

    def run_shell(
        self,
        script: str,
        cwd: Path,
        extra_env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(extra_env)
        return subprocess.run(
            ["bash", "-c", script],
            cwd=cwd,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
