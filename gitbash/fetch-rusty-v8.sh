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
# Defaults: x86_64-pc-windows-msvc, <repo>/.tmp/rusty_v8
set -euo pipefail

target="${1:-x86_64-pc-windows-msvc}"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
download_dir="${2:-$repo_root/.tmp/rusty_v8}"
lockfile="$repo_root/codex-rs/Cargo.lock"

version="$(awk '/^name = "v8"$/ { found = 1; next } found && /^version = / { gsub(/"/, "", $3); print $3; exit }' "$lockfile")"
if [[ -z "$version" ]]; then
  echo "fetch-rusty-v8: could not find the v8 crate in $lockfile" >&2
  exit 1
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
for name in "$archive_name" "$binding_name" "$checksums_name"; do
  if [[ ! -s "$download_dir/$name" ]]; then
    echo "fetch-rusty-v8: downloading $name (v8 $version)" >&2
    curl -fsSL --retry 3 "$base_url/$name" -o "$download_dir/$name.part"
    mv "$download_dir/$name.part" "$download_dir/$name"
  fi
done

# Release manifests may use CRLF line endings.
(cd "$download_dir" && tr -d '\r' < "$checksums_name" | sha256sum -c - >&2)

printf 'export RUSTY_V8_ARCHIVE=%q\n' "$download_dir/$archive_name"
printf 'export RUSTY_V8_SRC_BINDING_PATH=%q\n' "$download_dir/$binding_name"
