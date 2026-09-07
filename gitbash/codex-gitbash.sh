#!/usr/bin/env bash
# Codex Git Bash for Windows launcher.
#
# Starts the patched Codex CLI with Git for Windows Bash selected as the agent
# shell for this one invocation (equivalent to `[windows] agent_shell = "git-bash"`
# in ~/.codex/config.toml). All arguments are passed through to Codex.
#
# The same script is shipped inside the release archive (next to
# codex-gitbash.exe) and lives in the source tree (gitbash/codex-gitbash.sh),
# where it also finds a locally built codex.exe under codex-rs/target.
#
# Override the executable with CODEX_GITBASH_EXE=/path/to/codex.exe.
set -euo pipefail

die() {
  printf 'codex-gitbash: %s\n' "$1" >&2
  exit "${2:-1}"
}

# Git for Windows runs bash inside an MSYS2 environment where /usr/bin is the
# Git install's usr\bin directory. Anything else (WSL, cmd, PowerShell) cannot
# provide the shell Codex is configured to use.
if [[ -z "${MSYSTEM:-}" || ! -x /usr/bin/bash.exe ]]; then
  die "run this script from Git Bash (Git for Windows), not WSL or another shell." 127
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
candidates=()
if [[ -n "${CODEX_GITBASH_EXE:-}" ]]; then
  candidates+=("$CODEX_GITBASH_EXE")
fi
candidates+=(
  # Release archive layout.
  "$script_dir/codex-gitbash.exe"
  # Source checkout: locally built binaries.
  "$script_dir/../codex-rs/target/x86_64-pc-windows-msvc/release/codex.exe"
  "$script_dir/../codex-rs/target/release/codex.exe"
  "$script_dir/../codex-rs/target/debug/codex.exe"
  # Source checkout with an unpacked release next to the tree.
  "$script_dir/../bin/codex-gitbash.exe"
)

codex_exe=""
for candidate in "${candidates[@]}"; do
  if [[ -x "$candidate" ]]; then
    codex_exe="$candidate"
    break
  fi
done
if [[ -z "$codex_exe" ]]; then
  die "no Codex executable found. Extract a release archive next to this script, build with \`cargo build --release -p codex-cli --bin codex\` in codex-rs/, or set CODEX_GITBASH_EXE." 127
fi

# Make Git for Windows tools (GNU coreutils, git, ssh, ...) win over same-named
# Windows executables for everything Codex spawns. MSYS2 converts these POSIX
# entries to Windows paths when it starts native programs such as codex.exe.
export PATH="/usr/bin:/mingw64/bin:$PATH"
exec "$codex_exe" -c 'windows.agent_shell="git-bash"' "$@"
