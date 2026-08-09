#!/usr/bin/env python3

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
CHECKOUT_SHA = "de0fac2e4500dabe0009e67214ff5f5447ce83dd"
DOWNLOAD_ARTIFACT_SHA = "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"
EXPLICIT_LEASE_PUSH = (
    'git push --force-with-lease="refs/heads/main:$PATCH_BASE_SHA" '
    'origin "$SOURCE_SHA_FULL:refs/heads/main"'
)


def indentation(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def extract_named_steps(workflow: str) -> dict[str, str]:
    lines = workflow.splitlines()
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
            raise AssertionError(f"duplicate workflow step name: {name}")
        steps[name] = "\n".join(lines[index:end])
    return steps


def extract_named_run_blocks(workflow: str) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for name, step in extract_named_steps(workflow).items():
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


@unittest.skipUnless(
    shutil.which("git") and shutil.which("bash"), "git and bash required"
)
class GitBashUpstreamWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        cls.steps = extract_named_steps(cls.workflow)
        cls.run_blocks = extract_named_run_blocks(cls.workflow)

    def test_sync_dedupes_by_source_archive_across_paginated_releases(self) -> None:
        step = self.steps["Rebase the patch onto openai/codex main"]
        sync = self.run_blocks["Rebase the patch onto openai/codex main"]

        self.assertIn("GH_TOKEN: ${{ github.token }}", step)
        self.assertNotIn("GITBASH_RELEASE_TOKEN", step)
        self.assertIn("gh api --paginate", sync)
        self.assertIn(
            '"repos/$GITHUB_REPOSITORY/releases?per_page=100"',
            sync,
        )
        self.assertIn(".[] | .assets[]?.name", sync)
        self.assertIn('grep -Fxq "$archive_name"', sync)
        self.assertNotIn("releases/tags/$tag", sync)
        self.assertRegex(
            sync,
            re.compile(
                r'if \[\[ "\$\{\{ inputs\.force_build \}\}" == "true" \]\]; then\s+'
                r"should_build=true"
            ),
        )

    def test_build_exports_and_uploads_source_bundle_independently(self) -> None:
        expected_output_lines = (
            "should_advance: ${{ steps.sync.outputs.should_advance }}",
            "source_bundle_artifact: ${{ steps.sync.outputs.source_bundle_artifact }}",
            "source_bundle_name: ${{ steps.sync.outputs.source_bundle_name }}",
        )
        for line in expected_output_lines:
            with self.subTest(line=line):
                self.assertIn(line, self.workflow)

        sync = self.run_blocks["Rebase the patch onto openai/codex main"]
        self.assertIn(
            'should_advance=false\nif [[ "$source_sha_full" != "$patch_base_sha" ]]; then\n  should_advance=true\nfi',
            sync,
        )
        for output in (
            "should_advance",
            "source_bundle_artifact",
            "source_bundle_name",
        ):
            with self.subTest(output=output):
                self.assertIn(f"printf '{output}=%s\\n'", sync)

        create_step = self.steps["Create and verify rebased source bundle"]
        upload_step = self.steps["Upload rebased source bundle"]
        self.assertIn(
            "if: ${{ steps.sync.outputs.should_advance == 'true' }}",
            create_step,
        )
        self.assertIn(
            "if: ${{ steps.sync.outputs.should_advance == 'true' }}",
            upload_step,
        )
        self.assertNotIn("should_build", create_step)
        self.assertNotIn("should_build", upload_step)

    def test_advance_job_has_exact_gating_permissions_and_lease(self) -> None:
        job = extract_job(self.workflow, "advance_main")
        compact = compact_whitespace(job)

        self.assertIn("needs: [build, release]", job)
        self.assertIn("always()", job)
        self.assertIn("needs.build.result == 'success'", job)
        self.assertIn("needs.build.outputs.should_advance == 'true'", job)
        self.assertIn(
            "github.repository == 'zlinwzx147258/codex-gitbash'",
            job,
        )
        self.assertIn("github.ref == 'refs/heads/main'", job)
        self.assertIn(
            "needs.release.result == 'success' || ( needs.release.result == 'skipped' && needs.build.outputs.should_build == 'false' )",
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
        self.assertIn("name: ${{ needs.build.outputs.source_bundle_artifact }}", job)

        push_step = self.steps["Advance main with exact compare-and-swap"]
        push = self.run_blocks["Advance main with exact compare-and-swap"]
        self.assertIn(
            "if: ${{ steps.prepare.outputs.already_advanced != 'true' }}", push_step
        )
        self.assertIn(EXPLICIT_LEASE_PUSH, push)
        self.assertEqual(push.count("git push "), 1)
        self.assertIsNone(re.search(r"(?:^|\s)--force(?:\s|$)", push))

        prepare = self.run_blocks["Prepare exact rebased source"]
        self.assertNotIn("GITBASH_RELEASE_TOKEN", prepare)
        self.assertNotIn("GH_TOKEN", prepare)
        self.assertNotRegex(prepare, r"(?:^|\s)(?:\./)?\.github/")
        self.assertNotRegex(prepare, r"(?:^|\s)(?:python|just)(?:\s|$)")

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
            self.run_blocks["Create and verify rebased source bundle"],
            fixture.build,
            {
                "PATCH_BASE_SHA": fixture.patch_base_sha,
                "SOURCE_SHA_FULL": fixture.source_sha,
                "SOURCE_BUNDLE_NAME": fixture.bundle_name,
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def run_prepare_block(
        self,
        fixture: GitRepositoryFixture,
        checkout: Path,
        *,
        source_sha: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self.run_shell(
            self.run_blocks["Prepare exact rebased source"],
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
            self.run_blocks["Advance main with exact compare-and-swap"],
            checkout,
            {
                "PATCH_BASE_SHA": fixture.patch_base_sha,
                "SOURCE_SHA_FULL": fixture.source_sha,
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
