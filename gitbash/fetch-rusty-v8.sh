#!/usr/bin/env bash
# Fetches the Codex-built rusty_v8 prebuilt so `cargo build` can link V8 on
# Windows without compiling V8 from source.
#
# The `v8` crate's build script downloads a prebuilt static library, but the
# pointer-compression sandbox profile Codex uses is published only by
# openai/codex (release tag rusty-v8-v<version>), not by denoland. This script
# downloads and verifies the archive for the locked crate version and prints
# the environment exports the build needs:
#
#   eval "$(./gitbash/fetch-rusty-v8.sh)"
#   cargo build --release --bin codex   # in codex-rs/
#
# Usage: fetch-rusty-v8.sh [target-triple] [download-dir]
# Defaults: x86_64-pc-windows-msvc, <repo>/.tmp/rusty_v8/<v8-version>
set -euo pipefail

target="${1:-x86_64-pc-windows-msvc}"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
lockfile="$repo_root/codex-rs/Cargo.lock"

version="$(awk '/^name = "v8"$/ { found = 1; next } found && /^version = / { gsub(/"/, "", $3); print $3; exit }' "$lockfile")"
if [[ -z "$version" ]]; then
  echo "fetch-rusty-v8: could not find the v8 crate in $lockfile" >&2
  exit 1
fi

# The cache is keyed by version: the artifact names carry only the profile and
# the target, so sharing one directory across versions would silently relink a
# stale library after a rebase bumps the crate.
download_dir="${2:-$repo_root/.tmp/rusty_v8/$version}"

if command -v sha256sum > /dev/null 2>&1; then
  sha256_of() { sha256sum "$1" | cut -d ' ' -f 1; }
  sha256_check() { sha256sum -c -; }
else
  sha256_of() { shasum -a 256 "$1" | cut -d ' ' -f 1; }
  sha256_check() { shasum -a 256 -c -; }
fi

profile="ptrcomp_sandbox_release"
base_url="https://github.com/openai/codex/releases/download/rusty-v8-v${version}"
if [[ "$target" == *-pc-windows-msvc ]]; then
  archive_name="rusty_v8_${profile}_${target}.lib.gz"
else
  archive_name="librusty_v8_${profile}_${target}.a.gz"
fi
binding_name="src_binding_${profile}_${target}.rs"
checksums_name="rusty_v8_${profile}_${target}.sha256"

mkdir -p "$download_dir"

# The manifest is the only thing the archive is checked against, so trusting a
# copy fetched from the same release would catch transport corruption and
# nothing else. Anchor it to the checksum committed in the repository, exactly
# as upstream's setup-rusty-v8 action does, and re-fetch it every run so the
# anchor is always applied.
trusted_manifests="$repo_root/third_party/v8/rusty_v8_${version//./_}_release_manifests.sha256"
if [[ ! -f "$trusted_manifests" ]]; then
  echo "fetch-rusty-v8: no trusted manifest checksums for v8 $version at $trusted_manifests" >&2
  exit 1
fi

echo "fetch-rusty-v8: downloading $checksums_name (v8 $version)" >&2
curl -fsSL --retry 3 "$base_url/$checksums_name" -o "$download_dir/$checksums_name.part"
mv "$download_dir/$checksums_name.part" "$download_dir/$checksums_name"

expected_manifest="$(grep -F "  $checksums_name" "$trusted_manifests" | cut -d ' ' -f 1)"
actual_manifest="$(sha256_of "$download_dir/$checksums_name")"
if [[ -z "$expected_manifest" || "$actual_manifest" != "$expected_manifest" ]]; then
  rm -f "$download_dir/$checksums_name"
  echo "fetch-rusty-v8: $checksums_name does not match the checksum committed in $trusted_manifests" >&2
  exit 1
fi

# A manifest that lists only one file would let the check below pass while
# leaving the other file -- possibly the static library -- unverified.
if [[ "$(tr -d '\r' < "$download_dir/$checksums_name" | grep -c .)" -ne 2 ]]; then
  rm -f "$download_dir/$checksums_name"
  echo "fetch-rusty-v8: expected exactly two checksums in $checksums_name" >&2
  exit 1
fi

for name in "$archive_name" "$binding_name"; do
  if [[ ! -s "$download_dir/$name" ]]; then
    echo "fetch-rusty-v8: downloading $name (v8 $version)" >&2
    curl -fsSL --retry 3 "$base_url/$name" -o "$download_dir/$name.part"
    mv "$download_dir/$name.part" "$download_dir/$name"
  fi
done

# Release manifests may use CRLF line endings. A failure discards the payload
# so the next run re-downloads instead of re-checking the same bad bytes.
if ! (cd "$download_dir" && tr -d '\r' < "$checksums_name" | sha256_check >&2); then
  rm -f "$download_dir/$archive_name" "$download_dir/$binding_name"
  echo "fetch-rusty-v8: checksum verification failed; the downloads were discarded" >&2
  exit 1
fi

printf 'export RUSTY_V8_ARCHIVE=%q\n' "$download_dir/$archive_name"
printf 'export RUSTY_V8_SRC_BINDING_PATH=%q\n' "$download_dir/$binding_name"
