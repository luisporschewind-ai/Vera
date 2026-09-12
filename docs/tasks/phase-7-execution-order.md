# 阶段七执行顺序

**状态：** Planned
**执行就绪：** 否；等待阶段五、阶段六 Complete 与用户 CLI 封存确认
**目标分支前缀：** `phase-7/`
**上游规格：** [桌面集成](../specs/2026-09-12-desktop-integration.md)
**进程架构：** [ADR-0014](../decisions/ADR-0014-desktop-core-process-boundary.md)
**桌面壳：** [Wails（ADR-0015）](../decisions/ADR-0015-select-wails-desktop-shell.md)

## 规划与执行边界

本文件当前只拆分未来任务，不授权实现。只有以下条件全部成立才能执行任务 0030：

1. 阶段五与任务 0024 为 `Complete/Done`，Core compatibility manifest、`docs/protocol.md` 和 `ADR-0013` 已合并。
2. 阶段六与任务 0029 为 `Complete/Done`。
3. 用户原文确认「CLI 版本达到预期，可以封存」。
4. 阶段七规格、ADR-0014 和 ADR-0015 均为 `Accepted`。
5. 本规划分支基于最终干净 `main` 重放核对，所有冲突先在文档中解决。

未满足前禁止运行 Wails/PyInstaller Spike、添加依赖或写桌面产品代码。

## Cursor 执行规则

1. 严格按 0030 → 0031 → 0032 → 0033 → 0034 → 0035 → 0036 → 0037 执行。
2. 每项从最新干净 `main` 建独立分支；每项只有一个主实现 Agent 修改工作树。
3. 行为变化先写失败测试，使用 Fake Model、临时 Workspace 和隔离私有状态。
4. 桌面端只发送结构化 Action、消费结构化 Event/StreamFrame/查询结果，不解析 CLI 文本或拼 Slash Command。
5. Renderer 不拥有文件、Shell、进程、Provider、Policy、审批、恢复或私有状态能力。
6. 不读取真实 Provider Key，不在自动测试使用用户工程或签名凭据。
7. 每项同步规格、ADR、任务和证据；提交前检查 final diff、`git diff --check` 和状态。
8. 任何 Core 契约缺口先回到规格/ADR，不在壳层复制业务逻辑。

## 顺序与完成定义

| 顺序 | 任务 | 完成定义 |
|---|---|---|
| 1 | [0030 桌面协议与 Core service](0030-desktop-protocol-and-core-service.md) | 框架无关 sidecar、framing、握手、幂等和 conformance 通过 |
| 2 | [0031 Wails 验证与 Spike](0031-desktop-framework-measurement-spikes.md) | Wails 硬门禁与 release artifact 通过；UI 独立决策 |
| 3 | [0032 壳基础、生命周期与 Workspace](0032-desktop-shell-lifecycle-and-workspace.md) | Wails 只通过窄桥监督 Core，完成选择/启动/attach/退出 |
| 4 | [0033 主工作流与安全审批 UI](0033-desktop-primary-workflow.md) | prompt、时间线、工具、Diff、审批和验证消费同一 Core |
| 5 | [0034 崩溃、恢复与回滚 UI](0034-desktop-crash-recovery-and-rollback.md) | Renderer attach、Core crash、恢复分类和回滚无猜测/重放 |
| 6 | [0035 Provider、配置、私有状态与日志](0035-desktop-config-secrets-and-logs.md) | SecretStore 与全出口 canary 通过，Renderer 不读取明文 |
| 7 | [0036 打包、签名、升级、迁移与卸载](0036-desktop-packaging-update-and-uninstall.md) | Intel macOS 整包、嵌套签名、离线升级/迁移/卸载安全 |
| 8 | [0037 阶段七验收](0037-phase-7-desktop-acceptance.md) | 自动和人工证据映射规格，平台声明不夸大 |

## 任务间门禁

### 0030 → 0031

- 桌面协议 golden/conformance 全部通过；
- sidecar 可由普通测试进程启动，不依赖桌面壳；
- compatibility manifest hash 可在握手中核对；
- 任务 0030 已合并到干净 `main`。

### 0031 → 0032

- Wails 在固定时间盒和场景下通过全部硬门禁；
- 所有原始测量、就绪评分、风险和限制仍可读取；
- 用户审阅 Wails 验证结果并批准进入任务 0032；
- UI 选择单独记录；
- 0032–0037 的框架特定路径和命令已由 0031 更新。

### 0035 → 0036

- canary secret 在 app、Core、Renderer、日志、State 和 crash fixture 中均无泄漏；
- Core/壳的版本与 state compatibility matrix 稳定；
- active run/approval 的 shutdown 行为已经验证。

### 0036 → 0037

- release artifact manifest、架构、签名结构和离线升级通过；
- Workspace 前后 hash 相同；
- 真实 Developer ID/notarization 若受凭据阻塞，状态明确为 `Blocked`，不得写 `Passed`。

## 每项共同自动门禁

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

任务 0032 之后还必须运行 0031 验证并写回本文件的 Wails/前端 lint、typecheck、unit、integration 和 release build 命令。这里不预写精确命令，因为 Wails stable major 和项目布局必须在执行日验证。

## 人工验收边界

- Cursor 可以生成脚本、Fixture 和 `Not run` 表，不能代替用户做真实视觉、TCC、Finder 启动或签名身份确认。
- Intel macOS 人工通过只更新该平台/架构。
- Apple Silicon、Windows、Linux 没有原生证据时保持 `Not tested`。
- 阶段七没有所有自动证据、用户人工桌面走查和无 Critical/High 结论时，任务 0037 只能是 `Ready for manual acceptance`，路线图阶段七不能标记 Complete。
