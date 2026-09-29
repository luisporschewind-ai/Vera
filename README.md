# Vera

**简体中文** | [English](README.en.md)

Vera 是一款正在开发的本地桌面 Coding Agent，旨在通过过程透明、按需审批的工作流，帮助用户理解、修改、验证和恢复本地代码工程。

本仓库是 Vera 的正式产品工作区。`main` 已包含独立于界面的 Core、内部 CLI、持久化会话、Skills、自带密钥（BYOK）模型配置、缓存用量报告，以及阶段八工具集、Policy v2 和原生 Git 代码。代码合入不等于阶段验收完成。真实模型、安装和人工验收的进展分别记录在[当前状态](docs/STATUS.md)中。

## 开发方向

已确定的交付顺序是：

1. 构建不依赖界面的 Vera Agent Core。
2. 通过内部 `vera-cli` 开发、测试和验收 Core。
3. 在代表性工程中加固 Core 的安全性与可靠性。
4. 打磨 CLI 和 TUI，直到日常工作流成熟且可预期。
5. 通过结构化协议让桌面应用接入同一个 Core。
6. 完成私下验证后，准备稳定的正式发布版本。

CLI 是内部开发与验收入口，不是 Vera 最终的产品形态。Electron 是桌面端首选基线；若实际测量未通过门槛，则考虑 Tauri。桌面端实现仍受前置验收条件约束，详见 [ADR-0013](docs/decisions/ADR-0013-electron-desktop-baseline.md) 和[路线图](docs/ROADMAP.md)。

## 项目文档

- [产品定义](docs/PRODUCT.md)
- [路线图](docs/ROADMAP.md)
- [当前状态](docs/STATUS.md)
- [产品规格](docs/specs/README.md)
- [架构决策](docs/decisions/README.md)
- [任务记录](docs/tasks/README.md)
- [Agent 工作约定](AGENTS.md)

## 当前开发状态

Vera 源码仓库已公开，产品仍处于 Core 优先的开发阶段，尚未正式发布。当前 CLI 是内部开发入口，可用于检查、提议、审批、应用、验证和回滚变更。各阶段的验收状态以[当前状态](docs/STATUS.md)为准。

## CLI 快速开始

在仓库根目录运行：

```bash
uv sync --extra dev
uv run vera                 # TTY 默认 TUI
uv run vera --plain         # 逐行人类模式
uv run vera --json          # NDJSON Session
uv run vera run "goal" --json
uv run vera eval validate --json
uv run vera eval list
uv run vera eval run --suite offline --json
uv run vera config show
```

如需在开发期间从其他目录调用 `vera`，先在仓库根目录安装可编辑版本：

```bash
uv tool install --editable .
cd /path/to/your/project
vera
```

请在要处理的工程目录中运行 `vera`。不带参数的命令会开启持久化会话，显示版本、模型、工作区、Git、会话与审批边界等状态信息。你可以直接提问、在当前会话中延续上下文，或请求安全的代码变更。对需要审批的操作，请先检查 Diff，再明确选择 `approve`、`reject` 或 `cancel`。

常用会话命令：

- `/help` — 查看命令列表
- `/status` / `/context` / `/permissions` — 查看会话状态
- `/new` / `/clear` — 重置对话上下文
- `/compact [focus]` — 通过 Core 汇总上下文，不调用工具
- `/model [profile]` — 查看或切换当前模型配置
- `/runs` / `/show` / `/rollback` — 查看或回滚之前的运行
- `/recover [run-id]` — 只读检查中断的运行
- `/resume <run-id>` — 从安全的审批或验证边界继续
- `/abandon <run-id>` — 放弃中断的运行，不对工作区产生副作用
- `/exit` — 退出会话

也可以使用单次运行命令 `vera run "goal"`，包括供非交互式 Event 输出使用的 `--json` 模式。使用 `vera recover list|show|resume|abandon` 检查或继续恢复；`--json` 仅输出 Event JSON Lines。

离线评测是 Core 的一个客户端，不衡量真实模型的效果。它使用随项目提供的 Fake Model 测试集（14 个固定用例），不会调用真实 Provider：

```bash
uv run vera eval validate --json
uv run vera eval list --json
uv run vera eval run plain-answer --json --output ./eval-evidence
uv run vera eval run --suite offline --json --output ./eval-suite
```

`--json` 恰好输出一份报告文档。证据写入指定的 `--output` 父目录；默认写入 Vera 私有状态目录中的 `evals/`。目录结构为 `<evaluation_id>/{report.json,files.json,events.jsonl}`，目录权限为 `0700`，文件权限为 `0600`。退出码：`0` 表示通过，`2` 表示 Ctrl+C，`4` 表示用例失败或超时，`5` 表示配置、测试集、协议或证据错误。

本地 wheel 安装、升级和配置错误请参阅 [INSTALL.md](docs/INSTALL.md)。代表性工程的人工操作步骤（仅由用户执行）请参阅[阶段五人工检查清单](docs/evals/phase-5-representative-project-manual-checklist.md)。

Provider 凭据和真实服务测试均需主动启用；CLI 不会打印 API Key。验证命令受工作区权限约束，并在策略要求时保留独立的审批边界。

`Coding-harness` 是已停用的 Vera 原型，可用于查阅经验和证据，但不是正式实现的基础，也不得从本仓库修改它。

项目尚未选定开源许可证；公开发布条款仍待决定。
