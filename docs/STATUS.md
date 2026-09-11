# Vera 状态

**更新日期：** 2026-09-11
**当前阶段：** 阶段 2——恢复、兼容性与策略扩展（规划完成，待实施）
**仓库状态：** 阶段 1 已在 `main` 完成并通过人工验收；阶段 2 规格、ADR 与任务 0005–0009 已本地合并到 `main`，可交给 Cursor 实施；暂无远程仓库，未推送。

## 已验证基线

- 工作目录：`/Users/admin/Vera`
- 当前分支：`main`
- 初始检查点：仓库治理与 SDD 基线
- Agent 实现：任务 0002–0004 的 Python Core、Runtime 和内部 CLI；任务 0004 离线验收、本地合并与用户人工验收已完成
- 依赖清单：`pyproject.toml`、`.python-version`、`uv.lock`

## 已完成任务

- [任务 0001：建立 Vera 仓库](tasks/0001-bootstrap-repository.md)
- 任务 0002 的离线实现与验收步骤已完成；更广泛真实供应商评测仍开放
- [任务 0003：交互式 CLI 会话](tasks/0003-interactive-cli-session.md)
- [任务 0004：普通对话、会话上下文与状态命令](tasks/0004-conversational-cli-and-session-status.md)

## 活动任务

- [阶段二执行顺序](tasks/phase-2-execution-order.md)
- [任务 0005：恢复事实与只读分类](tasks/0005-recovery-facts-and-classification.md)
- 后续依次执行任务 0006–0009；当前没有阶段二代码实现

## 最近验证

- 任务 0004：普通文本 `assistant.message` + `outcome=responded`；进程内 `ConversationContext`；`/new`、`/clear`、`/context`、`/status`、`/permissions`、`/compact`、`/model`
- 任务 0004 离线验收：129 项非 live 测试通过、2 项 live 排除，覆盖率 90%；Ruff、格式、Mypy、包构建通过
- 合并后复核：`pytest -m "not live"` 129 通过；Ruff、Mypy 通过
- 凭据边界：自动验收没有读取或使用用户 DeepSeek API Key，没有运行 live 测试；自动测试强制隔离真实供应商环境
- 仓库外启动：`uv tool install --editable` 后仅执行本地 Slash Command，输出不含测试 Key/Base URL
- 用户人工验收：2026-09-11 由用户本人按验证步骤完成测试，确认结果符合预期、无问题；Agent 未接触真实 Key
- 历史现象：普通问候曾以 `no_changes_proposed` 失败，现已修复为正常对话完成语义，并经人工确认
- Git：已本地合并 `feature/conversational-cli-session`，未推送（无 remote）
- 验收记录：[普通对话、会话上下文与状态命令](evals/conversational-cli-and-session-status.md)

## 已接受方向

- 正式开发只在本仓库进行。
- `/Users/admin/Coding-harness` 保持只读，仅作为原型参考。
- 产品交付遵循 Core-first、内部 CLI-first、桌面 later。
- 公开发布前先完成私有稳定性和评测证据。
- Runtime、Command/Event 契约、私有状态与 Checkpoint，以及进程内会话上下文设计已通过 ADR 接受。
- 阶段二采用确定性恢复、版本化 Codec、统一 PolicyEngine 和 ModelAdapter 有限重试设计。

## 仍待决策

- 更广泛的供应商行为和真实供应商评测阈值
- 评测语料与阈值
- 桌面框架
- 许可证与发布策略
- 退出后会话恢复与长期记忆

## 下一检查点

Cursor 从最新 `main` 创建 `feature/recovery-facts-classification`，按任务 0005 开始实施。任务 0005–0009 全部完成后进入阶段三评测，不提前进入桌面端。
