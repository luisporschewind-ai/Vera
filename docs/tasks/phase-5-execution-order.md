# 阶段五执行顺序

**状态：** In progress
**执行就绪：** 是
**目标分支前缀：** `phase-5/`
**上游规格：** [Core 安全、权限与可靠性加固](../specs/2026-09-12-core-security-and-reliability-hardening.md)

## Cursor 执行规则

1. 从最新且干净的 `main` 为每个任务建立独立分支；同一任务只允许一个主实现 Agent 修改工作树。
2. 严格按 0020 → 0021 → 0022 → 0023 → 提示词投毒安全增量 → 0024 执行。安全增量的规格当前为 Draft；用户接受后使用下一个可用任务编号建立独立任务。每项通过完整门禁并合并后，下一项才从新的 `main` 开始。
3. 每个行为变化都先写失败测试，再做最小实现；同步更新任务、规格、ADR 或证据。
4. 不读取真实 Provider Key，不运行 live 测试，不修改用户工程，不引入桌面框架。
5. 不以降低 Workspace、PolicyEngine、ApprovalGate 或恢复约束来让测试通过。
6. 每个任务只提交该任务文件；提交前检查 `git diff`、`git diff --check` 和工作树状态。

## 顺序与完成定义

| 顺序 | 任务 | 完成定义 |
|---|---|---|
| 1 | [0020 文件系统与审批事实加固](0020-workspace-filesystem-and-approval-hardening.md) | 路径、特殊文件、竞态、私有写入和审批过期负例通过 |
| 2 | [0021 命令、进程与秘密加固](0021-command-process-and-secret-hardening.md) | 环境、进程组、输出上限和脱敏边界统一 |
| 3 | [0022 状态、恢复与长会话加固](0022-state-recovery-and-long-run-hardening.md) | 损坏状态失败关闭、恢复幂等、内存有界 |
| 4 | [0023 代表性工程与安装升级](0023-representative-projects-and-install-upgrade.md) | 三类夹具和仓库外 wheel/升级路径通过 |
| 5 | [提示词投毒安全增量（Draft）](../specs/2026-09-12-untrusted-content-and-prompt-injection-defense.md) | 规格接受后建立独立任务；来源/信任契约和对抗门禁通过 |
| 6 | [0024 契约冻结与阶段验收](0024-phase-5-contract-freeze-and-acceptance.md) | 自动门禁完成；人工 dogfood 证据满足后才可关闭阶段 |

## 每项任务的共同门禁

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

若自动实现已完成但缺少用户真实终端或 20 次连续 dogfood 证据，只能标记为 `Ready for manual acceptance`，不能写成 `Done` 或把阶段五改为 `Complete`。
