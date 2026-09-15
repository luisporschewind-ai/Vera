# 任务 0029：阶段六产品验收

> 供 Cursor 执行：按 `superpowers:verification-before-completion` 收口；真实 Terminal.app 走查必须由用户确认，不能用自动测试替代。

> 后续关系：[ADR-0017](../decisions/ADR-0017-insert-cli-experience-stage.md) 将最终 CLI 体验和用户封存门禁移至阶段七。本任务保留阶段六功能与可靠性基线证据；历史自动验收结果不被改写。

**状态：** Ready for phase-six closure（自动矩阵完成；后续修正任务仍在收口）
**执行就绪：** 任务 0025–0028 合并后
**分支：** `phase-6/0029-product-acceptance`
**依赖：** 任务 0025–0028 已合并
**规格：** [阶段六 CLI 产品化](../specs/2026-09-12-cli-productization-and-polish.md)

## 目标

对阶段六功能与可靠性条件逐项形成证据，执行模式一致性、安装包和真实终端走查。自动部分完成后通过真实使用发现的问题继续建立阶段六修正任务。

任务 0031–0033、任务 0042 及必要复验完成、没有未关闭的 Critical/High 正确性或可靠性问题后，本任务与阶段六才可关闭。阶段六关闭只允许进入阶段七 CLI 体验收口，不授权桌面实施。

## 实施步骤

### 1. 产品走查脚本与证据表

**修改：**

- 新增 `docs/evals/phase-6-cli-product-acceptance.md`
- 新增 `docs/evals/phase-6-manual-walkthrough.md`

人工脚本覆盖：

1. 陌生工程首启、帮助、模型、workspace 和安全边界；
2. 普通对话、`@path`、多行、历史搜索、长粘贴、外部编辑器和队列；
3. 单/多文件 Diff、复制、拒绝、批准、过期；
4. 验证成功/失败、取消、恢复、回滚；
5. `/doctor`、错误配置、无 Git、只读目录、Provider 不可用；
6. 小终端、无色、关闭动画、CJK、Resize、异常退出；
7. TUI、Plain、JSON、一次性模式语义对照。

每项记录环境、步骤、预期、实际、严重度和脱敏证据。初始值全部 `Not run`。

### 2. 自动产品矩阵

**修改：**

- 新增 `tests/e2e/test_phase_6_product_matrix.py`
- `tests/cli/test_driver.py`
- `tests/terminal/test_app.py`
- `tests/cli/test_plain_session.py`
- `tests/cli/test_json_session.py`

对同一离线场景断言命令可发现性、SessionAction、错误 code、审批事实、最终状态和退出码一致；TUI 快照只验证展示，不替代 Core 事实比较。

### 3. 仓库外 wheel 产品 smoke

**修改：**

- `scripts/smoke_installed_wheel.py`
- `docs/evals/phase-6-cli-product-acceptance.md`

从本地 wheel 在全新临时 venv、非仓库 cwd 验证默认 `vera` 路由、`--plain`、`--json`、`vera run`、`vera eval`、帮助与 `/doctor`。环境清除 Provider Key，网络不作为前提。

### 4. 最终分级和状态更新

**修改：**

- `docs/STATUS.md`
- `docs/ROADMAP.md`
- 本任务文件

逐项映射规格退出条件。任何误批准、输入丢失、终端损坏、状态误报或关键流程不可用视为 Critical/High，修复后重新走查。普通视觉建议可记录 Medium/Low。

自动矩阵、PTY、Textual Pilot、快照和 wheel smoke 只证明阶段六基线。它们不能代替已发现缺陷所要求的真实 Terminal.app 复验，也不能掩盖人工体验暴露的正确性或可靠性问题。

人工体验覆盖：输入、对话、工具展示、Diff、审批、错误、恢复、性能和终端兼容。发现的正确性与可靠性问题继续作为阶段六修正任务处理；Logo、品牌视觉、信息密度和长期使用质感进入阶段七。

阶段六关闭后，下一检查点是阶段七的持久化会话、TUI 视觉体验和个人长期 dogfood。只有用户在阶段七明确写出「CLI 版本达到预期，可以封存」，才能进入阶段八桌面集成。

任何情况下，阶段七封存前不得引入 Wails、Tauri、Electron 或其他桌面端代码与依赖。

## 验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/e2e/test_phase_6_product_matrix.py tests/pty tests/performance -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build --out-dir /private/tmp/vera-phase6-acceptance-dist
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/smoke_installed_wheel.py --dist /private/tmp/vera-phase6-acceptance-dist --workspace /private/tmp/vera-phase6-smoke-workspace
git diff --check
```

核对报告没有伪造人工结果或秘密后提交。若仍待人工体验，提交信息只记录自动证据，状态保持 `Ready for manual acceptance`：

```bash
git commit -m "docs: record phase six CLI product readiness"
```

## 验收标准

- 退出条件各有真实证据或明确 `Not run/Blocked`；自动通过不能掩盖真实使用发现的问题。
- 任务 0025–0028 完成后，0029 的自动矩阵形成阶段六基线。
- 人工体验中的输入、对话、工具展示、Diff、审批、错误、恢复、性能和终端兼容问题，继续作为阶段六修正任务。
- 任务 0031–0033、任务 0042 与必要复验完成、没有 Critical/High 正确性或可靠性问题后，阶段六才可关闭。
- 未经阶段七的「CLI 版本达到预期，可以封存」确认，不得开始阶段八或引入 Wails/Tauri/Electron 等桌面代码。
- Textual Pilot、快照或自动测试不得代替人工体验结论。
- 四种入口共享结构化语义，安装 wheel 在仓库外可用。

## 验证证据

日期：2026-09-13

- 完整非 live：`736 passed, 2 deselected, 4 warnings in 197.38s`
- 产品矩阵：同一离线编辑场景下 TUI controller / JSON / Plain / `drive_run` 的审批事实、终态与 run 退出码一致；`/help`、`/doctor` 事件类型对齐且不含秘密。
- wheel smoke：默认路由、`--plain`、`--json`、`vera run`、`vera eval`、`/doctor` 通过。
- 人工走查七项与 Terminal.app 兼容项保持 `Not run`。
- 自动验收当时停在 `Ready for manual acceptance`；后续由任务 0031–0033 和任务 0042 收口真实使用问题；未引入桌面代码。
