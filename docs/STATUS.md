# Vera 状态

**更新日期：** 2026-09-11
**当前阶段：** 阶段 1——Core 契约、安全编辑垂直切片与对话式 CLI
**仓库状态：** 普通对话、会话上下文与状态命令已在 `feature/conversational-cli-session` 完成离线验收，准备本地合并回 `main`；暂无远程仓库。

## 已验证基线

- 工作目录：`/Users/admin/Vera`
- 当前分支：`feature/conversational-cli-session`
- 初始检查点：仓库治理与 SDD 基线
- Agent 实现：任务 0002–0004 的 Python Core、Runtime 和内部 CLI；任务 0004 离线验收已完成
- 依赖清单：`pyproject.toml`、`.python-version`、`uv.lock`

## 已完成任务

- [任务 0001：建立 Vera 仓库](tasks/0001-bootstrap-repository.md)
- 任务 0002 的离线实现与验收步骤已完成；真实供应商和人工验收仍开放
- [任务 0003：交互式 CLI 会话](tasks/0003-interactive-cli-session.md)
- [任务 0004：普通对话、会话上下文与状态命令](tasks/0004-conversational-cli-and-session-status.md)

## 活动任务

- 无进行中的实现任务；下一增量待用户指定

## 最近验证

- 任务 0004：普通文本 `assistant.message` + `outcome=responded`；进程内 `ConversationContext`；`/new`、`/clear`、`/context`、`/status`、`/permissions`、`/compact`、`/model`
- 任务 0004 离线验收：129 项非 live 测试通过、2 项 live 排除，覆盖率 90%；Ruff、格式、Mypy、包构建通过
- 凭据边界：本轮没有读取或使用用户 DeepSeek API Key，没有运行 live 测试；自动测试强制隔离真实供应商环境
- 仓库外启动：`uv tool install --editable` 后仅执行本地 Slash Command，输出不含测试 Key/Base URL
- 历史现象：普通问候曾以 `no_changes_proposed` 失败，现已修复为正常对话完成语义
- 真实验证：DeepSeek 与 iOS 工程回归仍留给用户后续明确执行

## 已接受方向

- 正式开发只在本仓库进行。
- `/Users/admin/Coding-harness` 保持只读，仅作为原型参考。
- 产品交付遵循 Core-first、内部 CLI-first、桌面 later。
- 公开发布前先完成私有稳定性和评测证据。
- Runtime、Command/Event 契约、私有状态与 Checkpoint，以及进程内会话上下文设计已通过 ADR 接受。

## 仍待决策

- 更广泛的供应商行为和真实供应商评测阈值
- 评测语料与阈值
- 桌面框架
- 许可证与发布策略
- 退出后会话恢复与长期记忆

## 下一检查点

本地合并 `feature/conversational-cli-session` 回 `main` 后，由用户决定是否进行真实 DeepSeek 普通对话与 iOS 工程回归验收。
