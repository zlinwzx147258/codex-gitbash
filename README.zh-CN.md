# Codex Git Bash for Windows（中文说明）

这是一个基于 [OpenAI Codex](https://github.com/openai/codex) 的非官方 Windows
下游构建仓库。它的目标是让 Codex CLI 在 Windows 上把 **Git Bash** 当作原生
Agent Shell 使用，而不是由 PowerShell 包一层再调用 Bash。

> [!WARNING]
> 这不是 OpenAI 官方发行版。产品能力、账号登录、使用条款及官方支持请以
> [OpenAI Codex](https://github.com/openai/codex) 为准。

[English README](README.md) · [启动器说明](docs/git-bash.md) · [发行版](https://github.com/zlinwzx147258/codex-gitbash/releases)

## 下载并启动

1. 在本仓库的 **Releases** 页面下载最新预发行版中的
   `codex-gitbash-windows-x64-*.zip`。
2. 解压到你自己管理的目录。
3. 打开 **Git Bash**，进入解压目录，执行：

```bash
./codex-gitbash.sh
```

启动器会自动为这次运行传入：

```toml
[windows]
agent_shell = "git-bash"
```

因此 Codex 的 Agent 命令会直接通过 Git Bash 执行。

### 带危险模式启动

如果你明确需要跳过审批和沙箱：

```bash
./codex-gitbash.sh --dangerously-bypass-approvals-and-sandbox
```

该参数会显著扩大命令可执行范围，只应在你信任当前工作目录、提示词和工具的
前提下使用。

### 已有本机源码构建

当前机器的本地启动器位于：

```bash
/h/tools/内核处理二号区/codex/bin/codex-gitbash.sh
```

例如：

```bash
"/h/tools/内核处理二号区/codex/bin/codex-gitbash.sh" \
  --dangerously-bypass-approvals-and-sandbox
```

不要直接运行 `codex-gitbash.exe`；应通过 `codex-gitbash.sh` 启动，确保 Git
Bash 配置被正确传入。

## 配置、插件与官方 Codex 是否共用？

共用。此构建使用和官方 Codex CLI 相同的用户目录：

```text
~/.codex
```

因此登录状态、`config.toml`、插件、skills、hooks 和 MCP 配置都会沿用。它不会
替换 npm 安装的 `codex` 命令，也不会复制一份新的 Codex 用户配置目录。

如果希望在自己的 `~/.codex/config.toml` 中永久选择 Git Bash，可设置：

```toml
[windows]
agent_shell = "git-bash"
```

## 自动跟进官方更新

GitHub Actions 工作流 **Build Codex Git Bash for Windows** 会在每天
03:17 UTC（中国标准时间 11:17）检查上游 `openai/codex` 的 `main`：

- 上游没有新提交：跳过完整编译；
- 上游有新提交：把 Git Bash 补丁重放到新上游、编译 Windows x64 二进制，并发布
  新的预发行版；
- 也可在 GitHub 的 **Actions** 页面手动运行工作流。

上游变更后必须重新编译 Rust/MSVC 二进制；工作流已经缓存 Rust 依赖和构建产物，
后续构建通常会比首次冷编译更快。

## 项目边界

- 上游项目、官方安装方式和完整功能说明：
  [OpenAI Codex](https://github.com/openai/codex)
- 本仓库只维护 Windows 原生 Git Bash Agent Shell 补丁、启动器和自动发布流程。
- 源代码继续遵循仓库中的 [Apache-2.0 许可证](LICENSE)。
