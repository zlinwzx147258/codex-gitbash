# `windows.agent_shell`: native Git Bash on Windows

This fork adds one option to the Codex CLI configuration so that agent commands
on Windows can run through **Git for Windows Bash** instead of PowerShell.

> Unofficial downstream build of [OpenAI Codex](https://github.com/openai/codex).
> See the [README](../README.md) for downloads and the automation that keeps
> this fork on top of upstream.

## Configuration

```toml
# ~/.codex/config.toml
[windows]
agent_shell = "git-bash"   # "power-shell" (default) | "git-bash"
```

The option lives next to the other `[windows]` settings (`sandbox`,
`sandbox_private_desktop`) and is ignored on non-Windows hosts. It can also be
supplied for a single run:

```bash
codex-gitbash.exe -c 'windows.agent_shell="git-bash"'
```

which is exactly what the shipped `codex-gitbash.sh` launcher does.

## What changes at runtime

| Setting                       | Session shell                     | `exec_command` description                             |
| ----------------------------- | --------------------------------- | ------------------------------------------------------ |
| unset / `"power-shell"`       | PowerShell 7, else Windows PowerShell | upstream PowerShell examples and Windows safety rules |
| `"git-bash"`                  | Git for Windows `bash.exe`        | POSIX examples and *Windows safety rules (Git Bash)*   |

- **Shell discovery** (`codex-rs/shell-command/src/shell_detect.rs`,
  `git_bash_shell`): Codex looks for `bash.exe` under a Git for Windows install
  root, trying in order the install that owns the first `git.exe` on `PATH`,
  `%LocalAppData%\Programs\Git`, `%ProgramW6432%\Git`, `%ProgramFiles%\Git`,
  `%ProgramFiles(x86)%\Git`, then the fixed `C:\Program Files\Git` paths. A
  root only counts if it contains both a `git.exe` and a `bash.exe`, so WSL's
  `bash.exe` in `System32`, Store app-execution aliases and the `mingw64`
  subdirectory that holds the real `git.exe` are all rejected.
- **Session shell** (`codex-rs/core/src/session/session.rs`): when the option
  is `git-bash`, the resolved Bash becomes the session's user shell. If no Git
  for Windows install is found, starting a session fails with
  `windows.agent_shell is set to git-bash, but Git Bash could not be found`
  rather than silently falling back to PowerShell.
- **Tool description** (`codex-rs/core/src/tools/handlers/shell_spec.rs`,
  `codex-rs/core/src/tools/spec_plan.rs`): the `exec_command` tool advertises
  Git Bash syntax, `/c/...` paths and Bash-specific safety rules whenever the
  environment that will execute the command reports a Bash shell on Windows.
  Multi-environment turns keep the neutral upstream wording.
- Everything else (sandboxing, approvals, MCP, Code Mode, the TUI) is
  unchanged upstream Codex. The Windows sandbox helpers ship next to the CLI
  in the release archive.

## Launcher reference

`gitbash/codex-gitbash.sh` (copied into every release archive as
`codex-gitbash.sh`):

- must run inside Git Bash (`MSYSTEM` set and `/usr/bin/bash.exe` present);
- picks the first executable of `CODEX_GITBASH_EXE`, `codex-gitbash.exe`
  beside the script, `codex-rs/target/x86_64-pc-windows-msvc/release/codex.exe`,
  `codex-rs/target/release/codex.exe`, `codex-rs/target/debug/codex.exe`,
  `bin/codex-gitbash.exe` (relative to a source checkout);
- prepends `/usr/bin:/mingw64/bin` to `PATH` so Git's GNU tools win over
  same-named Windows programs for everything Codex spawns;
- `exec`s the binary with `-c 'windows.agent_shell="git-bash"'` followed by
  your arguments. Exit code 127 means it could not find Git Bash or a Codex
  executable.

## Tests

```bash
cd codex-rs
cargo test -p codex-shell-command                      # discovery helpers
RUST_MIN_STACK=8388608 cargo test -p codex-core --lib -- \
  shell_spec windows_agent_shell exec_command_guidance
python3 -m unittest discover -s ../.github/scripts -p 'test_gitbash_*.py'
```

In Git Bash on Windows, `python3` often resolves to the Microsoft Store stub
that prints "Python was not found"; use `python` there.

`tests/git_bash_discovery.rs` runs real discovery on the current machine. It
reports what it found and passes when no Git for Windows install exists; set
`CODEX_REQUIRE_GIT_BASH=1` (as CI does) to make a missing install a failure.
`RUST_MIN_STACK` is needed because some upstream `codex-core` tests overflow
the default 2 MiB test stack in debug builds.

CI covers the same ground: the **Git Bash fork checks** workflow lints the
shell scripts, verifies formatting, runs the workflow unit tests, runs the
discovery tests on a Windows runner and the `codex-core` tool-spec tests on
Linux - where the guidance falls back to the host platform, so a Windows-only
run would miss half the behaviour. The release pipeline then checks that the
rebased tree still carries the patch and runs `codex-gitbash.sh --version`
against the freshly built binary before anything is published.
