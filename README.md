# Codex Git Bash for Windows

[![Build Codex Git Bash for Windows](https://github.com/zlinwzx147258/codex-gitbash/actions/workflows/gitbash-upstream-build.yml/badge.svg)](https://github.com/zlinwzx147258/codex-gitbash/actions/workflows/gitbash-upstream-build.yml)
[![Latest release](https://img.shields.io/github/v/release/zlinwzx147258/codex-gitbash?label=release&sort=date)](https://github.com/zlinwzx147258/codex-gitbash/releases/latest)

> [!IMPORTANT]
> **Unofficial downstream build.** This is a Windows-focused fork of
> [OpenAI Codex](https://github.com/openai/codex) that lets the Codex CLI run
> its agent commands through **Git for Windows Bash** instead of PowerShell.
> It is not an OpenAI-maintained distribution: product features, sign-in,
> billing, terms of use and support all come from upstream.

[中文文档](README.zh-CN.md) · [Reference](docs/git-bash.md) · [Latest release](https://github.com/zlinwzx147258/codex-gitbash/releases/latest) · [Upstream Codex](https://github.com/openai/codex)

## Why

On Windows, Codex runs its `exec_command` tool through PowerShell. If your
day-to-day work happens in Git Bash (POSIX paths, GNU coreutils, shell
scripts), the model has to translate every command and frequently gets it
wrong. This fork adds a single configuration option:

```toml
[windows]
agent_shell = "git-bash"   # default: "power-shell"
```

When it is enabled, Codex:

- resolves the `bash.exe` of a real **Git for Windows** install (the one on
  `PATH` first, then the standard install locations), never WSL or a Microsoft
  Store app-execution alias;
- runs every agent command in that shell;
- tells the model to use POSIX syntax and `/c/...` style paths, with Git Bash
  specific safety rules instead of the PowerShell ones.

Everything else is unchanged upstream Codex.

## Install and run

1. Download `codex-gitbash-windows-x64-<source>.zip` from the
   [latest release](https://github.com/zlinwzx147258/codex-gitbash/releases/latest).
2. Extract it anywhere you like, for example `~/apps/codex-gitbash`.
3. Open **Git Bash** and start Codex through the launcher:

```bash
cd ~/apps/codex-gitbash
./codex-gitbash.sh
```

`codex-gitbash.sh` starts the bundled `codex-gitbash.exe` with
`windows.agent_shell = "git-bash"` applied for that one run. Every other
argument is passed straight to Codex:

```bash
./codex-gitbash.sh --dangerously-bypass-approvals-and-sandbox
./codex-gitbash.sh exec "summarize this repo"
```

Optional alias so that `codex-gitbash` works from any directory:

```bash
echo "alias codex-gitbash='$HOME/apps/codex-gitbash/codex-gitbash.sh'" >> ~/.bashrc
source ~/.bashrc
```

Notes:

- The build shares the normal `~/.codex` user state (sign-in, `config.toml`,
  plugins, skills, hooks, MCP servers) with an official Codex CLI install and
  does not replace an installed `codex` command.
- To make Git Bash the default without the launcher, add the `[windows]`
  snippet above to `~/.codex/config.toml` and run `codex-gitbash.exe`
  directly.
- Requirements: 64-bit Windows 10/11 and [Git for Windows](https://gitforwindows.org/).
  The binaries are not code-signed, so SmartScreen may ask once.

### What is in the archive

| File                              | Purpose                                                       |
| --------------------------------- | ------------------------------------------------------------- |
| `codex-gitbash.sh`                | Launcher; selects Git Bash and starts the CLI                 |
| `codex-gitbash.exe`               | Patched Codex CLI (`codex.exe` renamed to avoid PATH clashes) |
| `codex-code-mode-host.exe`        | Code Mode helper, resolved next to the CLI                    |
| `codex-command-runner.exe`        | Windows sandbox helper, resolved next to the CLI              |
| `codex-windows-sandbox-setup.exe` | Windows sandbox helper, resolved next to the CLI              |
| `BUILD-METADATA.txt`              | Codex version, upstream commit, rebased source commit         |
| `SHA256SUMS.txt`                  | Checksums; verify with `sha256sum -c SHA256SUMS.txt`          |

## How the automation works

The [Build Codex Git Bash for Windows](.github/workflows/gitbash-upstream-build.yml)
workflow runs daily at 03:17 UTC (11:17 China Standard Time) and can be started
manually from the **Actions** tab:

1. **sync** rebases this fork's patch onto the current `openai/codex` `main`.
   Nothing happens if upstream did not move.
2. **build** compiles the rebased source for `x86_64-pc-windows-msvc` with the
   Rust toolchain pinned by upstream, then smoke-tests the result through the
   launcher. A cold build takes about 90 minutes; dependency artifacts are
   cached between runs.
3. **release** publishes the archive as the latest GitHub release. The tag
   `gitbash-base-<baseline>-upstream-<upstream>` records the fork commit the
   patch was taken from and the upstream commit it was rebased onto.
4. **advance_main** fast-forwards this repository's `main` to the released
   source with an exact compare-and-swap, so `main` is always
   "reviewed patch + upstream main". Expect `main` to be rewritten daily; use
   `git pull --rebase` or re-clone rather than merging. This step needs a
   credential with the workflow permission (see below); without it the run
   still succeeds and only warns that the fast-forward was skipped.
5. **report** opens (or updates) an issue titled *Automated Git Bash build is
   failing* whenever a step fails, including the list of conflicting files
   when the patch no longer rebases cleanly, and closes it after the next
   successful run. Nothing broken is ever published.

### Repository setup the pipeline expects

- **Issues enabled**, so the tracking issue can be filed.
- A `GITBASH_RELEASE_TOKEN` secret holding a token with **Contents: write**
  and **Workflows: write** (a classic PAT needs `repo` and `workflow`).
  Publishing falls back to the built-in job token, but only a token with the
  workflow permission may push a rebase that carries upstream's own
  `.github/workflows` files, which is what step 4 does. Without that
  permission everything is still built and published; the run summary just
  notes that `main` was not fast-forwarded, and you can do it by hand:

  ```bash
  git fetch upstream main && git rebase upstream/main
  git push --force-with-lease origin main
  ```

## Build from source

```bash
git clone https://github.com/zlinwzx147258/codex-gitbash.git
cd codex-gitbash
eval "$(./gitbash/fetch-rusty-v8.sh)"        # prebuilt V8 for the locked crate version
cd codex-rs
export LIBSQLITE3_FLAGS=SQLITE_DISABLE_INTRINSIC
cargo build --release --bin codex
cd ..
./gitbash/codex-gitbash.sh --version
```

You need the Rust toolchain named in `codex-rs/rust-toolchain.toml` (rustup
installs it automatically) and the MSVC Build Tools. Codex links V8; the
`fetch-rusty-v8.sh` helper downloads and verifies the prebuilt that upstream
publishes for the locked `v8` crate version and prints the two environment
exports the build script needs (the same thing upstream's CI does). The
launcher finds a local build under `codex-rs/target/`; point
`CODEX_GITBASH_EXE` at any other `codex.exe` to override. To also use the
Windows sandbox and Code Mode from a source build, add
`--bin codex-code-mode-host --bin codex-command-runner --bin codex-windows-sandbox-setup`
to the build command.

Run the fork's tests with:

```bash
cd codex-rs
cargo test -p codex-shell-command
RUST_MIN_STACK=8388608 cargo test -p codex-core --lib --   shell_spec windows_agent_shell spec_plan_tests::exec_command_guidance
python3 -m unittest discover -s ../.github/scripts -p 'test_gitbash_*.py'
```

## Keeping up with upstream by hand

When the daily run reports a rebase conflict:

```bash
git remote add upstream https://github.com/openai/codex.git   # once
git fetch upstream main
git rebase upstream/main            # fix conflicts in the fork commits only
just write-config-schema            # if config types changed
git push --force-with-lease origin main
```

Then re-run the workflow from the Actions tab. The fork's changes are kept as
a few focused commits on top of upstream (`feat(windows)`, `ci`, `docs`) so
conflicts stay small.

## What this fork changes

| Area                                                              | Change                                                            |
| ----------------------------------------------------------------- | ----------------------------------------------------------------- |
| `codex-rs/config/src/types.rs`, `codex-rs/core/config.schema.json` | `[windows].agent_shell = "power-shell" \| "git-bash"`             |
| `codex-rs/shell-command/src/shell_detect.rs`                      | Git for Windows Bash discovery (`git_bash_shell`)                 |
| `codex-rs/core/src/session/session.rs`                            | Selects Git Bash as the session shell when configured             |
| `codex-rs/core/src/tools/…/shell_spec.rs`, `spec_plan.rs`         | Git Bash variant of the `exec_command` description and safety rules |
| `gitbash/`                                                        | Launcher, package README and the `fetch-rusty-v8.sh` build helper |
| `.github/workflows/gitbash-*.yml`, `.github/scripts/test_gitbash_*.py` | Daily rebase, build, release and tracking-issue automation with tests |

Documentation for the option itself lives in [docs/git-bash.md](docs/git-bash.md).

## Troubleshooting

- **`run this script from Git Bash`** – the launcher relies on Git for
  Windows' MSYS environment (`cygpath`); it does not work from WSL, cmd or
  PowerShell.
- **`windows.agent_shell is set to git-bash, but Git Bash could not be found`** –
  install [Git for Windows](https://gitforwindows.org/) or make sure its
  `git.exe` is on `PATH`; portable installs are found through `PATH`.
- **`no Codex executable found`** – keep `codex-gitbash.sh` next to
  `codex-gitbash.exe`, or set `CODEX_GITBASH_EXE`.
- **The model still writes PowerShell** – check that Codex is really running
  with the option (the `exec_command` tool description starts with
  "Windows safety rules (Git Bash)"), and that no `windows.agent_shell`
  override in a profile or `-c` flag switches it back.

## License

Apache-2.0, unchanged from upstream. See [LICENSE](LICENSE) and
[NOTICE](NOTICE). For everything about Codex itself use the
[official documentation](https://developers.openai.com/codex).
