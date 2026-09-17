# 验收：阶段六 CLI 产品化

> 后续关系：[ADR-0017](../decisions/ADR-0017-insert-cli-experience-stage.md) 保留本报告作为阶段六自动基线证据；最终 CLI 体验、个人 dogfood 和用户封存确认已经移至阶段七。

**规格：** [2026-09-12-cli-productization-and-polish](../specs/2026-09-12-cli-productization-and-polish.md)  
**任务：** [0029](../tasks/0029-phase-6-product-acceptance.md)  
**日期：** 2026-09-16
**结果：** 阶段六基线成立（自动矩阵与 wheel smoke 通过；Terminal.app 走查第 1–7 项主路径已过；发现 1–37 的 Critical/High 已复验。CLI 封存确认归阶段七）

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

2026-09-16 复跑：产品测试 `922 passed, 2 deselected`；共享 uv cache 曾缺 WHEEL 元数据导致两项 smoke 失败，重建 cache 后 `test_built_wheel_contains_runnable_corpus` 与 `test_smoke_installed_wheel_outside_repo` 通过。`ruff`/`mypy`/`git diff --check` 通过。

## 17 条退出条件

| # | 条件 | 栏 | 说明 |
|---|---|---|---|
| 1 | 首次启动可发现输入、帮助、模型、工作区和权限边界 | 自动验证且通过 | 自动 Catalog/`/help`；Terminal.app 走查第 1 项；发现 1 复验通过 |
| 2 | 多行、历史、反向搜索、粘贴、Unicode、外部编辑器、单条排队 | 自动验证且通过 | 任务 0025；走查第 2 项主路径已过。`Ctrl+R`/`Ctrl+G` 按用户决定不进主线 |
| 3 | `@path` 不逃逸、不跟随不可信链接、不暗示批准 | 自动验证且通过 | 任务 0026；发现 22/23 复验通过 |
| 4 | 保留命令兼容，新增 7 个命令统一 Catalog | 自动验证且通过 | 任务 0026；产品矩阵再断言可发现性 |
| 5 | 工具/日志、Diff/审批、验证、恢复、失败层次 | 自动验证且通过 | 任务 0027/0032/0033；走查第 3–4 项 |
| 6 | Diff 可导航复制，审批默认安全，过期不可用 | 自动验证且通过 | 任务 0027；发现 24/27/28 复验通过 |
| 7 | 取消与退出不重复副作用，退出恢复终端 | 自动验证且通过 | 任务 0027/0028 PTY；走查第 4/6 项；发现 10/29 复验通过 |
| 8 | TUI、Plain、JSON、一次性语义与退出码对齐 | 自动验证且通过 | `tests/e2e/test_phase_6_product_matrix.py`；走查第 7 项 |
| 9 | `/doctor` 脱敏诊断，配置与异常不泄漏秘密 | 自动验证且通过 | 产品矩阵与 wheel `/doctor`；走查第 5 项；发现 31 复验通过 |
| 10 | 三种主题、禁用动画、小终端、CJK、键盘-only | 自动验证且通过 | 任务 0028；走查第 6 项；发现 17/21/26 复验通过 |
| 11 | macOS Terminal.app 必过，其他终端有清晰结果 | 自动验证且通过 | Terminal.app 走查第 1–7 项已过；iTerm2/Warp/Linux/Windows Terminal 保持明确 `Not run` |
| 12 | 性能门槛或已接受环境差异 | 自动验证且通过 | 任务 0028 时间线预算 |
| 13 | 必要真实终端复验无未关闭 Critical/High | 自动验证且通过 | [人工走查](phase-6-manual-walkthrough.md) 发现 1–37 中 High 均已复验 |
| 14 | 完整非 live、PTY、Pilot、快照、静态门禁、wheel smoke | 自动验证且通过 | 2026-09-16：产品测试 922 passed / 2 deselected；重建 uv cache 后 wheel smoke 2 passed |
| 15 | 未读真实 Key、未改未授权工程、无桌面框架 | 自动验证且通过 | 测试清除供应商环境；无 Electron/Wails/Tauri 代码 |
| 16 | 任务 0031–0033 等修正已记录验证，未引入桌面框架 | 自动验证且通过 | 0031–0033 均为 Done；视觉冻结于 `25faf71` |
| 17 | 任务 0042 隔离 Profile、审批绑定、清理与真实 Xcode 回归 | 自动验证且通过 | `940bd29`/`c51909d`；发现 35–37 复验通过 |

## 已接受限制与 Medium/Low

- iTerm2 / Warp / 常见 Linux 终端 / Windows Terminal 兼容结论未测（Medium，明确 `Not run`）。Terminal.app 已走查。
- TUI `/doctor` `/config` 曾走通用 status 摘要（Medium，发现 31；Terminal.app 复验通过）。
- 阶段五真实 dogfood 与三类工程走查仍不足，不阻塞阶段六，但不改变阶段五 Ready for manual acceptance。
- `VeraTestDemo` Git 索引残留旧 `AD build/`，未取消暂存、未改 `.gitignore`。

## 明确未做

- 未将阶段七标为 Complete，未开始阶段八，未引入桌面框架
- 未读取真实 Provider Key，未跑 live
- 未用 Textual Pilot 或快照代替人工体验结论
- 未收到阶段七封存原文「CLI 版本达到预期，可以封存」

## 任务 0042 验证产物隔离（2026-09-15）

自动部分已提交 `940bd29`。Planner 在 Change Set hash 与命令审批前生成最终 `VerificationCommand`；Runner 只执行已规划命令，并把 Xcode/SwiftPM/pytest/Mypy/Ruff/Git/tsc 产物写到 workspace 外临时根。未知写入型命令失败关闭。

- 聚焦测试与 `ruff`/`mypy`/`git diff --check` 通过。完整非 live `919 passed, 2 deselected`。
- 2026-09-15 Terminal.app 真实 `xcodebuild` 隔离复验通过：产物在 `/private/tmp/vera-verification/.../000`，工程根未重建 `build/`。
- 发现 36：2026-09-16 Terminal.app 复验通过；command 卡展示最终 argv、`Profile xcode`、产物根。
- 发现 37：模型注入 `artifact_plan` 曾使 propose 失败；`ProposalInput` 已剥离，重启后提出成功。
- Git 索引残留旧 `AD build/`，未取消暂存。不把外部产物隔离称为 OS 沙箱。
