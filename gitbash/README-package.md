# Codex Git Bash for Windows

> Unofficial Windows build of [OpenAI Codex](https://github.com/openai/codex)
> that runs the agent's commands through **Git for Windows Bash** instead of
> PowerShell. Not an OpenAI-maintained distribution.

## Run

Open **Git Bash**, change into this folder and start:

```bash
./codex-gitbash.sh
```

The launcher starts `codex-gitbash.exe` with the equivalent of

```toml
[windows]
agent_shell = "git-bash"
```

for this one invocation. Every other argument is passed straight to Codex, for
example `./codex-gitbash.sh --dangerously-bypass-approvals-and-sandbox`.

To make Git Bash the default without the launcher, put the snippet above into
`~/.codex/config.toml` and run `codex-gitbash.exe` directly.

## What is in this folder

| File                              | Purpose                                                        |
| --------------------------------- | -------------------------------------------------------------- |
| `codex-gitbash.sh`                | Launcher; selects Git Bash and starts the CLI                  |
| `codex-gitbash.exe`               | Patched Codex CLI (`codex.exe` renamed to avoid PATH clashes)  |
| `codex-code-mode-host.exe`        | Code Mode helper, resolved next to the CLI                     |
| `codex-command-runner.exe`        | Windows sandbox helper, resolved next to the CLI               |
| `codex-windows-sandbox-setup.exe` | Windows sandbox helper, resolved next to the CLI               |
| `BUILD-METADATA.txt`              | Exact patch baseline, upstream and rebased source commits      |
| `SHA256SUMS.txt`                  | Checksums; verify with `sha256sum -c SHA256SUMS.txt`           |

This build shares the normal `~/.codex` user state (sign-in, `config.toml`,
plugins, skills, hooks, MCP servers) with an official Codex CLI install and does
not replace an installed `codex` command.

Documentation, source and automation: <https://github.com/zlinwzx147258/codex-gitbash>
