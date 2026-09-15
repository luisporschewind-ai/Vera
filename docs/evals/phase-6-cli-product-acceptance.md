# 验收：阶段六 CLI 产品化

> 后续关系：[ADR-0017](../decisions/ADR-0017-insert-cli-experience-stage.md) 保留本报告作为阶段六自动基线证据；最终 CLI 体验、个人 dogfood 和用户封存确认已经移至阶段七。

**规格：** [2026-09-12-cli-productization-and-polish](../specs/2026-09-12-cli-productization-and-polish.md)  
**任务：** [0029](../tasks/0029-phase-6-product-acceptance.md)  
**日期：** 2026-09-13  
**结果：** Ready for manual acceptance（自动矩阵与 wheel smoke 通过；Terminal.app 与真实工程走查未运行）

## 质量门禁

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

自动证据（2026-09-13）：

- 完整非 live：`736 passed, 2 deselected, 4 warnings in 197.38s`
- 聚焦：`tests/e2e/test_phase_6_product_matrix.py` 与 `tests/performance` 通过；`tests/pty` 已包含在完整非 live 中通过（沙箱复跑会因 `out of pty devices` 失败，不计入产品回归）
- `ruff check` / `ruff format --check` / `mypy src` 通过
- `uv build` 产出 `vera_agent-0.1.0` sdist 与 wheel
- `scripts/smoke_installed_wheel.py` 通过（`--plain`、`--json`、`vera run`、`vera eval`、帮助与 `/doctor`）；本机沙箱将 dist/venv 放在仓库 `tmp/`（gitignored），语义与任务指定的 `/private/tmp` 隔离 smoke 相同
- `git diff --check` 无空白错误
- warning 来自既有 `tests/pty` 的 `forkpty` DeprecationWarning

## 16 条退出条件

| # | 条件 | 栏 | 说明 |
|---|---|---|---|
| 1 | 首次启动可发现输入、帮助、模型、工作区和权限边界 | 未运行/受阻 | 自动 Catalog/`/help` 已覆盖；Terminal.app 首启见走查第 1 项 |
| 2 | 多行、历史、反向搜索、粘贴、Unicode、外部编辑器、单条排队 | 自动验证且通过 | 任务 0025；真实键盘手感仍待走查第 2 项 |
| 3 | `@path` 不逃逸、不跟随不可信链接、不暗示批准 | 自动验证且通过 | 任务 0026 |
| 4 | 保留命令兼容，新增 7 个命令统一 Catalog | 自动验证且通过 | 任务 0026；产品矩阵再断言可发现性 |
| 5 | 工具/日志、Diff/审批、验证、恢复、失败层次 | 自动验证且通过 | 任务 0027；真实阅读层次待走查第 3–4 项 |
| 6 | Diff 可导航复制，审批默认安全，过期不可用 | 自动验证且通过 | 任务 0027 |
| 7 | 取消与退出不重复副作用，退出恢复终端 | 自动验证且通过 | 任务 0027/0028 PTY；真实 Terminal.app 退出待走查第 6 项 |
| 8 | TUI、Plain、JSON、一次性语义与退出码对齐 | 自动验证且通过 | `tests/e2e/test_phase_6_product_matrix.py` |
| 9 | `/doctor` 脱敏诊断，配置与异常不泄漏秘密 | 自动验证且通过 | 产品矩阵与 wheel `/doctor`；人工分享体验待走查第 5 项 |
| 10 | 三种主题、禁用动画、小终端、CJK、键盘-only | 自动验证且通过 | 任务 0028 Pilot/能力探测；真实 CJK/主题待走查第 6 项 |
| 11 | macOS Terminal.app 必过，其他终端有清晰结果 | 未运行/受阻 | [兼容矩阵](phase-6-terminal-compatibility-matrix.md) 真实终端均为 `Not run` |
| 12 | 性能门槛或已接受环境差异 | 自动验证且通过 | 任务 0028 时间线预算；人工体感待走查 |
| 13 | 人工走查无 Critical/High 交互缺陷 | 未运行/受阻 | [人工走查](phase-6-manual-walkthrough.md) 七项全部 `Not run` |
| 14 | 完整非 live、PTY、Pilot、快照、静态门禁、wheel smoke | 自动验证且通过 | 见质量门禁；Pilot/快照只证明展示，不代签封存 |
| 15 | 未读真实 Key、未改未授权工程、无桌面框架 | 自动验证且通过 | 测试清除供应商环境；无 Electron/Wails/Tauri 代码 |
| 16 | 用户确认「CLI 版本达到预期，可以封存」 | 未运行/受阻 | 未收到原文确认 |

## 已接受限制与 Medium/Low

- 真实 Terminal.app / iTerm2 / Warp / Linux / Windows Terminal 兼容结论未测（Medium，明确 `Not run`）。
- TUI `/doctor` `/config` 曾走通用 status 摘要（Medium，发现 31；Terminal.app 复验通过）。
- 阶段五真实 dogfood 与三类工程走查仍不足，不阻塞阶段六自动部分，但不改变阶段五 Ready for manual acceptance。

## 明确未做

- 未把任务 0029 或阶段六标为 Done/Complete
- 当时未开始旧编号阶段七（现阶段八）的桌面集成，未引入桌面框架
- 未读取真实 Provider Key，未跑 live
- 未用 Textual Pilot 或快照代替人工体验结论

## 任务 0042 验证产物隔离（2026-09-15）

自动部分已在分支 `phase-6/0042-verification-artifact-isolation` 落地，未提交。Planner 在 Change Set hash 与命令审批前生成最终 `VerificationCommand`；Runner 只执行已规划命令，并把 Xcode/SwiftPM/pytest/Mypy/Ruff/Git/tsc 产物写到 workspace 外临时根。未知写入型命令失败关闭。

- 聚焦测试与 `ruff`/`mypy`/`git diff --check` 通过。完整非 live `919 passed, 2 deselected`。
- 两项既有 wheel smoke 因共享 `/private/tmp/vera-uv-cache` 缺少依赖 WHEEL 元数据失败，与隔离实现无关。
- 真实 Terminal.app 对 `VeraTestDemo` 的 `xcodebuild` 隔离回归未跑；既有 `build/` 仍为发现，未清理。
- 阶段六保持 `In progress`。不把外部产物隔离称为 OS 沙箱。
