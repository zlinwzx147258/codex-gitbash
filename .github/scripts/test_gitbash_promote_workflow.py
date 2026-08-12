#!/usr/bin/env python3

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "gitbash-promote-release.yml"


class GitBashPromoteWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_promotes_only_after_successful_build(self) -> None:
        self.assertIn("workflow_run", self.workflow)
        self.assertIn("Build Codex Git Bash for Windows", self.workflow)
        self.assertIn(
            "github.event.workflow_run.conclusion == 'success'",
            self.workflow,
        )
        self.assertIn("permissions:", self.workflow)
        self.assertIn("contents: write", self.workflow)

    def test_promotion_patches_newest_release_to_latest_formal(self) -> None:
        self.assertIn("select(.draft == false)][0].id", self.workflow)
        self.assertIn("-f make_latest=true", self.workflow)
        self.assertIn("-f prerelease=false", self.workflow)
        self.assertNotIn("GITBASH_RELEASE_TOKEN", self.workflow)


if __name__ == "__main__":
    unittest.main()
