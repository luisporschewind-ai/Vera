# 阶段六执行顺序

**状态：** In progress
**执行就绪：** 阶段五自动门禁已完成后（人工 dogfood 仍未完成；用户授权开始阶段六自动任务）
**目标分支前缀：** `phase-6/`
**上游规格：** [CLI 产品化与体验完善](../specs/2026-09-12-cli-productization-and-polish.md)

## Cursor 执行规则

1. 只有阶段五全部退出条件满足后才能开始；每项从最新干净 `main` 建独立分支。
2. 原计划按 0025 → 0026 → 0027 → 0028 → 0029 执行；真实走查修正按 0031 → 0032 → 0033 → 0042 收口，每项独立测试、文档、提交和合并。
3. 新 Slash Command 必须先有结构化 `SessionAction`/结果，再接入 TUI、Plain、JSON；Widget 不拥有业务或权限逻辑。
4. 本阶段不顺手增加持久化会话、长期记忆、直接 Shell、插件或桌面端；持久化会话按已接受规格归入阶段七。
5. 不读取真实 Provider Key；自动测试不修改真实用户工程。真实 dogfood 只允许已批准 Change Set 修改源码，验证派生产物必须按已接受规格写入 workspace 外 Vera 私有临时根。
6. 自动测试通过后仍需关闭当前阶段六修正任务及其必要复验；存在未关闭的 Critical/High 正确性或可靠性问题时不得标记阶段六 `Complete`。
7. 阶段六完成后进入阶段七 CLI 体验收口；未经用户确认「CLI 版本达到预期，可以封存」，不得开始阶段八，也不得引入 Wails、Tauri、Electron 或任何桌面端代码。
8. Textual Pilot、快照和自动测试不能代替 Terminal.app 与真实工程中的人工体验结论。

## 顺序与完成定义

| 顺序 | 任务 | 完成定义 |
|---|---|---|
| 1 | [0025 Composer、历史、粘贴与单条队列](0025-composer-history-paste-and-queue.md) | 输入不丢失、不误提交，队列不跨审批边界 |
| 2 | [0026 路径引用、命令目录与诊断](0026-path-mentions-commands-and-diagnostics.md) | `@path` 与 7 个新增命令共享结构化 Catalog |
| 3 | [0027 时间线、Diff、审批与错误体验](0027-timeline-diff-approval-and-errors.md) | 重要事实突出、默认焦点安全、错误可行动 |
| 4 | [0028 终端兼容、可访问性与性能](0028-terminal-compatibility-accessibility-performance.md) | 小终端、无色、CJK、长输出与退出恢复通过 |
| 5 | [0029 阶段六产品验收](0029-phase-6-product-acceptance.md) | 自动矩阵形成基线；真实使用发现的正确性与可靠性缺陷进入后续修正任务收口 |
| 6 | [0042 验证产物隔离与工作区无污染](0042-verification-artifact-isolation.md) | 最终验证计划在审批前形成，常见构建/缓存产物不留在用户 workspace |

## 每项任务的共同门禁

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

阶段六实现与真实终端复验必须分开记录。Cursor 不得用 Textual Pilot 或快照结果代替已发现缺陷所要求的 Terminal.app 复验。

任务 0025–0028 已合并，任务 0029 自动矩阵与 wheel smoke 已完成。人工体验中发现的输入、对话、工具展示、Diff、审批、错误、恢复、性能、终端兼容和验证产物污染问题，继续作为阶段六修正任务收口。任务 0031–0033、任务 0042 及必要复验完成、没有未关闭的 Critical/High 正确性或可靠性问题后，阶段六才能关闭并进入阶段七。

阶段七负责持久化会话、TUI 视觉识别、完整体验收口和个人长期 dogfood。用户最终封存确认属于阶段七；桌面集成已经顺延到阶段八。

当前修正：[任务 0031：CLI 版本身份与 `--version`](0031-cli-version-identity.md) 与 [任务 0032：时间线信息层次与错误保真](0032-timeline-and-error-fidelity.md) 已合入当前工作树；[任务 0033：用户消息、工具块与 tool_call_id](0033-cli-dogfood-bugs.md) 已 Done（视觉走查由用户停止，TUI 修正未提交）；[任务 0042：验证产物隔离与工作区无污染](0042-verification-artifact-isolation.md) 自动步骤已落地，待真实 Terminal.app Xcode 回归。
