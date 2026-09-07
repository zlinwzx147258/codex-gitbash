# Codex Git Bash for Windows（中文说明）

[![Build Codex Git Bash for Windows](https://github.com/zlinwzx147258/codex-gitbash/actions/workflows/gitbash-upstream-build.yml/badge.svg)](https://github.com/zlinwzx147258/codex-gitbash/actions/workflows/gitbash-upstream-build.yml)
[![最新发行版](https://img.shields.io/github/v/release/zlinwzx147258/codex-gitbash?label=release&sort=date)](https://github.com/zlinwzx147258/codex-gitbash/releases/latest)

> [!IMPORTANT]
> **非官方下游构建。** 本仓库是 [OpenAI Codex](https://github.com/openai/codex)
> 的 Windows 分支：让 Codex CLI 在 Windows 上把 **Git for Windows 的 Bash**
> 当作 Agent Shell，而不是 PowerShell。它不是 OpenAI 官方发行版，产品功能、
> 登录、计费、使用条款和技术支持均以上游为准。

[English README](README.md) · [参考文档](docs/git-bash.md) · [最新发行版](https://github.com/zlinwzx147258/codex-gitbash/releases/latest) · [上游 Codex](https://github.com/openai/codex)

## 为什么需要它

Windows 上 Codex 的 `exec_command` 工具默认通过 PowerShell 执行命令。如果你的
日常工作都在 Git Bash 里（POSIX 路径、GNU coreutils、shell 脚本），模型就得把
每条命令“翻译”成 PowerShell，而且经常翻错。本分支只增加一个配置项：

```toml
[windows]
agent_shell = "git-bash"   # 默认值: "power-shell"
```

开启后 Codex 会：

- 查找真正的 **Git for Windows** `bash.exe`（优先 `PATH` 上的 git，其次标准安装
  位置），绝不会误选 WSL 或微软商店的应用执行别名；
- 所有 Agent 命令都在这个 shell 中运行；
- 在工具说明里告诉模型使用 POSIX 语法和 `/c/...` 风格路径，并用 Git Bash 版本的
  安全规则替换 PowerShell 规则。

除此之外与上游 Codex 完全一致。

## 安装与启动

1. 从[最新发行版](https://github.com/zlinwzx147258/codex-gitbash/releases/latest)
   下载 `codex-gitbash-windows-x64-<source>.zip`。
2. 解压到任意目录，例如 `~/apps/codex-gitbash`。
3. 打开 **Git Bash**，通过启动器运行：

```bash
cd ~/apps/codex-gitbash
./codex-gitbash.sh
```

`codex-gitbash.sh` 会以 `windows.agent_shell = "git-bash"` 启动同目录下的
`codex-gitbash.exe`，仅对本次运行生效；其余参数原样透传给 Codex：

```bash
./codex-gitbash.sh --dangerously-bypass-approvals-and-sandbox
./codex-gitbash.sh exec "总结一下这个仓库"
```

可选：加一个别名，在任意目录输入 `codex-gitbash` 即可启动：

```bash
echo "alias codex-gitbash='$HOME/apps/codex-gitbash/codex-gitbash.sh'" >> ~/.bashrc
source ~/.bashrc
```

说明：

- 本构建与官方 Codex CLI 共用 `~/.codex` 用户目录（登录状态、`config.toml`、
  插件、skills、hooks、MCP 配置），不会替换已安装的 `codex` 命令。
- 如果想不经启动器就默认使用 Git Bash，把上面的 `[windows]` 片段写进
  `~/.codex/config.toml`，然后直接运行 `codex-gitbash.exe`。
- 依赖：64 位 Windows 10/11 和 [Git for Windows](https://gitforwindows.org/)。
  二进制未做代码签名，SmartScreen 可能提示一次。

### 压缩包内容

| 文件                              | 用途                                                    |
| --------------------------------- | ------------------------------------------------------- |
| `codex-gitbash.sh`                | 启动器：选择 Git Bash 并启动 CLI                        |
| `codex-gitbash.exe`               | 打过补丁的 Codex CLI（由 `codex.exe` 改名，避免 PATH 冲突） |
| `codex-code-mode-host.exe`        | Code Mode 辅助程序，放在 CLI 旁即可被找到               |
| `codex-command-runner.exe`        | Windows 沙箱辅助程序                                    |
| `codex-windows-sandbox-setup.exe` | Windows 沙箱辅助程序                                    |
| `BUILD-METADATA.txt`              | Codex 版本、上游提交、变基后的源码提交                  |
| `SHA256SUMS.txt`                  | 校验和，可用 `sha256sum -c SHA256SUMS.txt` 验证         |

## 自动化流程

[Build Codex Git Bash for Windows](.github/workflows/gitbash-upstream-build.yml)
工作流每天 03:17 UTC（北京时间 11:17）自动运行，也可以在 **Actions** 页面手动
触发：

1. **sync**：把本分支的补丁变基到当前 `openai/codex` 的 `main` 上。上游没有
   新提交时直接结束。
2. **build**：用上游锁定的 Rust 工具链编译 `x86_64-pc-windows-msvc` 版本，然后
   通过启动器做冒烟测试。冷编译约 90 分钟，依赖产物会在多次运行之间缓存。
3. **release**：把压缩包发布为最新的 GitHub Release。标签
   `gitbash-base-<baseline>-upstream-<upstream>` 记录了补丁来自哪个分支提交、
   变基到了哪个上游提交。
4. **advance_main**：用精确的 compare-and-swap 把本仓库的 `main` 快进到已发布的
   源码，因此 `main` 始终等于“已审核的补丁 + 上游 main”。`main` 每天都会被
   重写，本地请用 `git pull --rebase` 或重新 clone，不要 merge。
5. **report**：任一步骤失败时自动创建（或更新）标题为
   *Automated Git Bash build is failing* 的 issue，补丁无法干净变基时会列出冲突
   文件；下次成功后自动关闭。坏掉的东西永远不会被发布。

### 仓库需要的配置

- **开启 Issues**，否则无法创建跟踪 issue。
- 一个 `GITBASH_RELEASE_TOKEN` secret，令牌需要 **Contents: write** 和
  **Workflows: write** 权限（classic PAT 则是 `repo` 和 `workflow`）。发布本身
  可以退回到内置的 job token，但第 4 步推送的变基提交会带上游自己的
  `.github/workflows` 文件，只有具备 workflow 权限的令牌才被允许推送。缺少它时
  发行版照常发布，只有 `main` 快进这一步会被报告为失败。

## 从源码构建

```bash
git clone https://github.com/zlinwzx147258/codex-gitbash.git
cd codex-gitbash
eval "$(./gitbash/fetch-rusty-v8.sh)"        # 下载锁定版本的 V8 预编译库
cd codex-rs
export LIBSQLITE3_FLAGS=SQLITE_DISABLE_INTRINSIC
cargo build --release --bin codex
cd ..
./gitbash/codex-gitbash.sh --version
```

需要 `codex-rs/rust-toolchain.toml` 指定的 Rust 工具链（rustup 会自动安装）和
MSVC Build Tools。Codex 会链接 V8：`fetch-rusty-v8.sh` 会按 `Cargo.lock` 里锁定的
`v8` 版本下载并校验上游发布的预编译库，然后输出构建脚本需要的两个环境变量
（与上游 CI 的做法相同）。启动器会在 `codex-rs/target/` 下寻找本地构建；也可以用
`CODEX_GITBASH_EXE` 指定任意 `codex.exe`。如果源码构建也要使用 Windows 沙箱和
Code Mode，在构建命令后追加
`--bin codex-code-mode-host --bin codex-command-runner --bin codex-windows-sandbox-setup`。

运行本分支相关的测试：

```bash
cd codex-rs
cargo test -p codex-shell-command
RUST_MIN_STACK=8388608 cargo test -p codex-core --lib --   shell_spec windows_agent_shell spec_plan_tests::exec_command_guidance
python3 -m unittest discover -s ../.github/scripts -p 'test_gitbash_*.py'
```

## 手动跟进上游

当每日构建报告变基冲突时：

```bash
git remote add upstream https://github.com/openai/codex.git   # 只需一次
git fetch upstream main
git rebase upstream/main            # 只需解决分支自己那几个提交里的冲突
just write-config-schema            # 配置类型有变化时
git push --force-with-lease origin main
```

然后在 Actions 页面重新运行工作流。分支的改动被整理成上游之上的少数几个提交
（`feat(windows)`、`ci`、`docs`），冲突范围尽量小。

## 本分支改了什么

| 位置                                                              | 改动                                                   |
| ----------------------------------------------------------------- | ------------------------------------------------------ |
| `codex-rs/config/src/types.rs`、`codex-rs/core/config.schema.json` | `[windows].agent_shell = "power-shell" \| "git-bash"`  |
| `codex-rs/shell-command/src/shell_detect.rs`                      | 查找 Git for Windows 的 Bash（`git_bash_shell`）        |
| `codex-rs/core/src/session/session.rs`                            | 配置为 git-bash 时用它作为会话 shell                    |
| `codex-rs/core/src/tools/…/shell_spec.rs`、`spec_plan.rs`         | `exec_command` 工具说明与安全规则的 Git Bash 版本      |
| `gitbash/`                                                        | 启动器、包内说明以及源码构建辅助脚本 `fetch-rusty-v8.sh` |
| `.github/workflows/gitbash-*.yml`、`.github/scripts/test_gitbash_*.py` | 每日变基、编译、发布、issue 跟踪的自动化及其测试   |

配置项本身的说明见 [docs/git-bash.md](docs/git-bash.md)。

## 常见问题

- **`run this script from Git Bash`**：启动器依赖 Git for Windows 的 MSYS 环境，
  不能在 WSL、cmd 或 PowerShell 里运行。
- **`windows.agent_shell is set to git-bash, but Git Bash could not be found`**：
  安装 [Git for Windows](https://gitforwindows.org/)，或确保它的 `git.exe` 在
  `PATH` 上；便携版也是通过 `PATH` 找到的。
- **`no Codex executable found`**：把 `codex-gitbash.sh` 和 `codex-gitbash.exe`
  放在同一目录，或设置 `CODEX_GITBASH_EXE`。
- **模型仍然写 PowerShell 命令**：确认 Codex 确实带着该选项运行（`exec_command`
  工具说明以 "Windows safety rules (Git Bash)" 开头），并检查没有 profile 或 `-c`
  参数把 `windows.agent_shell` 改回去。

## 许可证

与上游相同，Apache-2.0，见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。Codex 本身的
使用方式请查阅[官方文档](https://developers.openai.com/codex)。
