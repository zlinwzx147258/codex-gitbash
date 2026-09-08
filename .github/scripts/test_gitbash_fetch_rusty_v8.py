#!/usr/bin/env python3
"""Tests for `gitbash/fetch-rusty-v8.sh`.

The script hands `cargo` the prebuilt V8 static library that gets linked into
the shipped binary, so its verification is the only thing standing between a
substituted release asset and the release archive. These tests run the real
script against a fake repository and a stubbed `curl`.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "gitbash" / "fetch-rusty-v8.sh"
TARGET = "x86_64-pc-windows-msvc"
PROFILE = "ptrcomp_sandbox_release"
ARCHIVE_NAME = f"rusty_v8_{PROFILE}_{TARGET}.lib.gz"
BINDING_NAME = f"src_binding_{PROFILE}_{TARGET}.rs"
MANIFEST_NAME = f"rusty_v8_{PROFILE}_{TARGET}.sha256"

CURL_STUB = """#!/bin/sh
# Serves $RELEASE_DIR instead of the network, mimicking curl's argument shape.
out=""
url=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    --retry) shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
name="${url##*/}"
if [ -f "$RELEASE_DIR/$name" ]; then
  cp "$RELEASE_DIR/$name" "$out"
else
  exit 22
fi
"""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FetchRustyV8Fixture:
    """A throwaway repository plus the release assets the script downloads."""

    def __init__(self, root: Path, version: str = "9.9.9") -> None:
        self.root = root
        self.version = version
        self.repo = root / "repo"
        self.release = root / "release"
        self.release.mkdir(parents=True, exist_ok=True)

        (self.repo / "gitbash").mkdir(parents=True, exist_ok=True)
        (self.repo / "codex-rs").mkdir(parents=True, exist_ok=True)
        (self.repo / "third_party" / "v8").mkdir(parents=True, exist_ok=True)
        shutil.copy2(SCRIPT_PATH, self.repo / "gitbash" / "fetch-rusty-v8.sh")
        (self.repo / "gitbash" / "fetch-rusty-v8.sh").chmod(0o755)
        self.write_lockfile(version)

        self.bin_dir = root / "bin"
        self.bin_dir.mkdir(exist_ok=True)
        stub = self.bin_dir / "curl"
        stub.write_text(CURL_STUB, encoding="utf-8", newline="\n")
        stub.chmod(0o755)

    def write_lockfile(self, version: str) -> None:
        self.version = version
        (self.repo / "codex-rs" / "Cargo.lock").write_text(
            '[[package]]\nname = "serde"\nversion = "1.0.0"\n\n'
            f'[[package]]\nname = "v8"\nversion = "{version}"\n',
            encoding="utf-8",
            newline="\n",
        )

    def publish(
        self,
        archive: bytes = b"real-archive",
        binding: bytes = b"// real binding\n",
        manifest_lines: list[str] | None = None,
        anchor_matches: bool = True,
    ) -> None:
        """Write the release assets and the checksum committed in the repo."""
        (self.release / ARCHIVE_NAME).write_bytes(archive)
        (self.release / BINDING_NAME).write_bytes(binding)

        if manifest_lines is None:
            manifest_lines = [
                f"{sha256(archive)}  {ARCHIVE_NAME}",
                f"{sha256(binding)}  {BINDING_NAME}",
            ]
        manifest = ("\n".join(manifest_lines) + "\n").encode()
        (self.release / MANIFEST_NAME).write_bytes(manifest)

        digest = sha256(manifest) if anchor_matches else sha256(b"a different manifest")
        anchor = (
            self.repo
            / "third_party"
            / "v8"
            / f"rusty_v8_{self.version.replace('.', '_')}_release_manifests.sha256"
        )
        anchor.write_text(f"{digest}  {MANIFEST_NAME}\n", encoding="utf-8", newline="\n")

    def run(self) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["RELEASE_DIR"] = str(self.release)
        env["PATH"] = str(self.bin_dir) + os.pathsep + env["PATH"]
        return subprocess.run(
            ["bash", str(self.repo / "gitbash" / "fetch-rusty-v8.sh"), TARGET],
            cwd=self.repo,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    def cache_dir(self) -> Path:
        return self.repo / ".tmp" / "rusty_v8" / self.version


class FetchRustyV8Test(unittest.TestCase):
    def test_verified_download_prints_the_build_exports(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fixture = FetchRustyV8Fixture(Path(temp_dir))
            fixture.publish()

            result = fixture.run()

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"export RUSTY_V8_ARCHIVE=", result.stdout)
            self.assertIn(f"export RUSTY_V8_SRC_BINDING_PATH=", result.stdout)
            # The cache is keyed by version so a later crate bump cannot reuse
            # these bytes.
            self.assertIn("9.9.9", result.stdout)
            self.assertEqual(
                (fixture.cache_dir() / ARCHIVE_NAME).read_bytes(), b"real-archive"
            )

    def test_manifest_that_does_not_match_the_committed_anchor_is_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fixture = FetchRustyV8Fixture(Path(temp_dir))
            fixture.publish(anchor_matches=False)

            result = fixture.run()

            # Verifying the archive against a manifest from the same release
            # would only prove the two agree, so the manifest itself has to be
            # anchored to a checksum committed in the repository.
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not match the checksum committed in", result.stderr)
            self.assertFalse((fixture.cache_dir() / MANIFEST_NAME).exists())

    def test_manifest_that_omits_the_archive_is_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fixture = FetchRustyV8Fixture(Path(temp_dir))
            binding = b"// real binding\n"
            # A manifest listing only the binding would make `sha256sum -c`
            # report OK while the static library went unchecked.
            fixture.publish(
                archive=b"TROJAN-ARCHIVE",
                binding=binding,
                manifest_lines=[f"{sha256(binding)}  {BINDING_NAME}"],
            )

            result = fixture.run()

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("expected exactly two checksums", result.stderr)

    def test_corrupt_archive_is_discarded_rather_than_cached(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fixture = FetchRustyV8Fixture(Path(temp_dir))
            fixture.publish()
            # The manifest is honest; the served archive is not.
            (fixture.release / ARCHIVE_NAME).write_bytes(b"corrupted-in-transit")

            result = fixture.run()

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("checksum verification failed", result.stderr)
            self.assertFalse((fixture.cache_dir() / ARCHIVE_NAME).exists())

    def test_a_version_bump_does_not_reuse_the_previous_download(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fixture = FetchRustyV8Fixture(Path(temp_dir))
            fixture.publish(archive=b"v8-9.9.9-archive")
            self.assertEqual(fixture.run().returncode, 0)
            old_cache = fixture.cache_dir()

            # A daily rebase onto upstream is what bumps the crate; the
            # artifact names carry no version, so only the cache path can keep
            # the old library from being relinked.
            fixture.write_lockfile("9.9.10")
            fixture.publish(archive=b"v8-9.9.10-archive")
            result = fixture.run()

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotEqual(old_cache, fixture.cache_dir())
            self.assertEqual(
                (fixture.cache_dir() / ARCHIVE_NAME).read_bytes(), b"v8-9.9.10-archive"
            )
            self.assertEqual(
                (old_cache / ARCHIVE_NAME).read_bytes(), b"v8-9.9.9-archive"
            )

    def test_a_version_without_a_committed_anchor_fails_closed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fixture = FetchRustyV8Fixture(Path(temp_dir))
            fixture.publish()
            fixture.write_lockfile("10.0.0")

            result = fixture.run()

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no trusted manifest checksums for v8 10.0.0", result.stderr)


if __name__ == "__main__":
    unittest.main()
