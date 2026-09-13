# 阶段六执行顺序

**状态：** In progress
**执行就绪：** 阶段五自动门禁已完成后（人工 dogfood 仍未完成；用户授权开始阶段六自动任务）
**目标分支前缀：** `phase-6/`
**上游规格：** [CLI 产品化与体验完善](../specs/2026-09-12-cli-productization-and-polish.md)

## Cursor 执行规则

1. 只有阶段五全部退出条件满足后才能开始；每项从最新干净 `main` 建独立分支。
2. 严格按 0025 → 0026 → 0027 → 0028 → 0029 执行，每项独立测试、文档、提交和合并。
3. 新 Slash Command 必须先有结构化 `SessionAction`/结果，再接入 TUI、Plain、JSON；Widget 不拥有业务或权限逻辑。
4. 会话历史只驻留当前进程，退出即清空；不得顺手增加长期记忆、直接 Shell、插件或桌面端。
5. 不读取真实 Provider Key，不改用户工程；终端人工验收由用户明确执行并记录。
6. 自动测试通过不得把阶段六标为 `Complete`。任务 0029 在 0025–0028 完成后只能进入 `Ready for manual acceptance`。
7. 未经用户确认「CLI 版本达到预期，可以封存」，不得开始阶段七，也不得引入 Wails、Tauri、Electron 或任何桌面端代码。
8. Textual Pilot、快照和自动测试不能代替 Terminal.app 与真实工程中的人工体验结论。

## 顺序与完成定义

| 顺序 | 任务 | 完成定义 |
|---|---|---|
| 1 | [0025 Composer、历史、粘贴与单条队列](0025-composer-history-paste-and-queue.md) | 输入不丢失、不误提交，队列不跨审批边界 |
| 2 | [0026 路径引用、命令目录与诊断](0026-path-mentions-commands-and-diagnostics.md) | `@path` 与 7 个新增命令共享结构化 Catalog |
| 3 | [0027 时间线、Diff、审批与错误体验](0027-timeline-diff-approval-and-errors.md) | 重要事实突出、默认焦点安全、错误可行动 |
| 4 | [0028 终端兼容、可访问性与性能](0028-terminal-compatibility-accessibility-performance.md) | 小终端、无色、CJK、长输出与退出恢复通过 |
| 5 | [0029 阶段六产品验收](0029-phase-6-product-acceptance.md) | 自动矩阵完成后停在 `Ready for manual acceptance`；仅用户确认封存后才关闭阶段 |

## 每项任务的共同门禁

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

阶段六实现与真实终端验收必须分开记录。Cursor 不得用 Textual Pilot 或快照结果代替用户在 Terminal.app 的产品走查。

任务 0025–0028 已合并。任务 0029 自动矩阵与 wheel smoke 已完成，状态为 `Ready for manual acceptance`。缺少用户确认「CLI 版本达到预期，可以封存」时，不能写成 `Done` 或把阶段六改为 `Complete`。人工体验中发现的输入、对话、工具展示、Diff、审批、错误、恢复、性能和终端兼容问题，继续开阶段六修正任务，不得开始阶段七。
