# Native Git Bash on Windows

This fork adds a `windows.agent_shell` option to Codex CLI so its agent commands
can execute through **Git Bash** on Windows.

> This is an unofficial downstream build of [OpenAI Codex](https://github.com/openai/codex),
> not an OpenAI-maintained distribution.

## Supported entry point

Use the included launcher from Git Bash:

```bash
./codex-gitbash.sh
```

The launcher starts the packaged `codex-gitbash.exe` with the equivalent of:

```toml
[windows]
agent_shell = "git-bash"
```

Do not launch `codex-gitbash.exe` directly unless you have set the configuration
in your own `~/.codex/config.toml`; direct execution bypasses the launcher's
one-invocation override.

## Persistent configuration

To make Git Bash the default native agent shell for a custom build, put this in
`~/.codex/config.toml`:

```toml
[windows]
agent_shell = "git-bash"
```

The launcher is still the simplest way to guarantee the setting for a single
run without changing user configuration.

## Shared Codex user state

This build intentionally uses the normal `~/.codex` directory. It shares your
sign-in, configuration, plugins, skills, hooks, and MCP definitions with an
official Codex CLI installation. It does not replace the npm-installed
`codex` command.

## Local checkout

From a source checkout, run:

```bash
./bin/codex-gitbash.sh
```

On the maintained build machine, the local launcher is located at:

```bash
/h/tools/内核处理二号区/codex/bin/codex-gitbash.sh
```

Arguments pass through unchanged:

```bash
./bin/codex-gitbash.sh --dangerously-bypass-approvals-and-sandbox
```

### Tutorial: optional manual `codex` alias on the maintained build machine

> **This is a manual tutorial, not an installer.** The repository and launcher
> never create this alias or modify `~/.bashrc`. In an already open Git Bash
> window, you may choose to paste this command yourself:

```bash
alias codex='/h/tools/内核处理二号区/codex/bin/codex-gitbash.sh'
```

Only after you manually run it do these invoke the custom build:

```bash
codex
codex --dangerously-bypass-approvals-and-sandbox
```

The alias is temporary and disappears when that Git Bash window closes. To
remove it earlier without changing files, run:

```bash
unalias codex
```

If you personally choose to persist it for future Git Bash sessions, manually
run the following optional, idempotent command. The project does not run it for
you:

```bash
grep -qxF "alias codex='/h/tools/内核处理二号区/codex/bin/codex-gitbash.sh'" ~/.bashrc \
  || echo "alias codex='/h/tools/内核处理二号区/codex/bin/codex-gitbash.sh'" >> ~/.bashrc
source ~/.bashrc
```
