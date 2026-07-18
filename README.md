# Codex Git Bash for Windows

> [!IMPORTANT]
> **Unofficial downstream build.** This repository is a Windows-focused fork of
> [OpenAI Codex](https://github.com/openai/codex). It adds a configurable
> **native Git Bash** agent shell and is not an OpenAI-maintained distribution.

[中文说明](README.zh-CN.md) · [Git Bash launcher reference](docs/git-bash.md) · [Releases](https://github.com/zlinwzx147258/codex-gitbash/releases) · [Upstream Codex](https://github.com/openai/codex)

## Run Codex natively through Git Bash

1. Open this repository's latest **pre-release** and download the asset named
   `codex-gitbash-windows-x64-*.zip`.
2. Extract the archive anywhere you control.
3. From **Git Bash**, run the included launcher:

```bash
./codex-gitbash.sh
```

The launcher starts the bundled Windows executable with:

```toml
[windows]
agent_shell = "git-bash"
```

It intentionally uses Git Bash for Codex's agent commands while retaining the
same user state as the official CLI (`~/.codex`): sign-in, configuration,
plugins, skills, hooks, and MCP settings are shared.

To use the local checkout built on this machine instead, run:

```bash
/h/tools/内核处理二号区/codex/bin/codex-gitbash.sh
```

To start with Codex's approval and sandbox bypass flag:

```bash
./codex-gitbash.sh --dangerously-bypass-approvals-and-sandbox
```

> Do not start `codex-gitbash.exe` directly: use `codex-gitbash.sh` so the Git
> Bash shell setting is always supplied.

## What this fork changes

- Adds the `windows.agent_shell = "git-bash"` configuration option.
- Detects and launches Git Bash as the Windows agent shell.
- Provides `codex-gitbash.sh`, a safe launcher that enables the setting for one
  invocation without replacing the npm-installed `codex` command.
- Automatically rebases the reviewed patch on the current upstream `main`,
  builds a Windows x64 executable, and publishes a pre-release when upstream
  changes.

The source remains an OpenAI Codex derivative under the repository's existing
[Apache-2.0 license](LICENSE). This fork's Git Bash-specific changes live on
its `main` branch and are documented in the release metadata.

## Automatic upstream builds

The **Build Codex Git Bash for Windows** workflow checks upstream daily at
03:17 UTC (11:17 China Standard Time) and skips the expensive Rust build when
there is no new upstream commit. You can also run it manually from the
**Actions** tab. A changed upstream revision requires a fresh Windows/MSVC
compile; the workflow caches Rust dependencies and build artifacts to speed up
later runs.

## Upstream Codex documentation

For the official product, account, IDE, API, authentication, and general CLI
documentation, use the upstream resources:

- [Codex documentation](https://developers.openai.com/codex)
- [OpenAI Codex source repository](https://github.com/openai/codex)
- [Contributing guide](docs/contributing.md)
- [Installing and building from source](docs/install.md)
