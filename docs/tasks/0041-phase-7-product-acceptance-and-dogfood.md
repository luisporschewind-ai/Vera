# 任务 0041：阶段七产品验收与个人 dogfood

> 供主实现 Agent 执行：按 `superpowers:verification-before-completion` 收口；真实 Terminal.app 和真实工程结论只能由用户确认。

**状态：** Ready for manual acceptance
**执行就绪：** 是；任务 0040 已完成
**分支：** `phase-7/0041-product-acceptance`
**依赖：** 任务 0034–0040、0043
**规格：** [阶段七 CLI 体验收口](../specs/2026-09-13-cli-experience-and-personal-dogfood.md)、[持久化对话会话](../specs/2026-09-13-persistent-conversation-sessions.md)、[项目指令与 `VERA.md` 初始化](../specs/2026-09-14-project-instructions-and-vera-init.md)

## 目标与边界

形成阶段七自动门禁、仓库外 wheel、真实 Terminal.app、真实工程和持续个人使用证据，关闭阻断缺陷。自动测试完成后最多标记 `Ready for manual acceptance`；只有用户原文确认「CLI 版本达到预期，可以封存」才能关闭阶段七。

## 实施步骤

### 1. 验收追踪表

- [x] 新增 `docs/evals/phase-7-cli-product-acceptance.md`，逐项映射三份阶段七规格的验收标准、自动证据、人工证据、缺陷和最终状态。
- [x] 新增 `docs/evals/phase-7-manual-dogfood.md`，初始所有真实终端项为 `Not run`，字段固定为日期、环境、工程、步骤、预期、实际、严重度和脱敏证据。
- [x] 严重度固定为：Critical（权限/数据/错误应用）、High（主流程不可用/输入丢失/状态误导）、Medium（高频摩擦）、Low（视觉细节）。

### 2. 阶段七离线产品矩阵

- [x] 新增 `tests/e2e/test_phase_7_product_matrix.py`，用 Fake Model 和临时 state/workspace 覆盖新建、两轮对话、修改、审批、验证、退出、continue、再次修改、历史 run 查看。
- [x] 加入失败矩阵：无历史 continue、错误 ID、workspace 不匹配、尾部截断、中间损坏、未来版本、保存失败、恢复超限、缺失 run 证据。
- [x] 加入视觉/交互矩阵：三主题、60×16/80×24/120×40、CJK、Resize、运行/审批/验证/失败/恢复、长历史、用户消息滚动锚点与原始时间、Composer 箭头与焦点、下方上下文/模型/推理状态带、审批卡上下空白。尺寸与主题拆成两组参数，避免 3×3 全组合拖慢共同门禁。
- [x] 对 TUI、Plain、JSON 和一次性模式比较结构化事实，快照只验证展示。

### 3. 仓库外 wheel 与升级回归

- [x] 扩展 `scripts/smoke_installed_wheel.py` 或新增 `scripts/smoke_phase_7_cli.py`，从 `/private/tmp` 全新 venv 安装本地 wheel。
- [x] 使用显式临时 `VERA_STATE_DIR`/workspace，清除所有 Provider Key；覆盖 `vera --help`、new、continue、resume id、非 TTY picker、session inspect/repair dry-run、Plain、JSON 和现有 `vera run/eval`。
- [x] 验证升级保留 v1 Journal，可重建列表；未知未来版本拒绝，测试不得触碰真实私有状态目录。

### 4. 真实 Terminal.app 走查

- [x] 用户在原生 Terminal.app 完成：新会话 → 两轮理解工程 → 代码修改 → 审批 → Diff → 验证 → 退出 → `-c` → 指代前文继续修改 → 查看旧 run。
- [x] 用户再完成：`-r` 选择历史、明确 ID 恢复、`/compact` 后重启、`/new`、`/clear`、取消、失败、恢复、无 Git 目录和 dirty workspace。
- [x] 对 60×16、Resize、`NO_COLOR`、`TERM=dumb`、CJK、复制、滚动和异常退出逐项记录实际结果；滚动已确认用户消息锚点替换正确。120×40 未单独定档；`VERA_NO_ANIMATIONS` 未单独跑。
- [x] 人工确认 Composer 左侧箭头不进入实际输入，底部状态带左右信息在 80×24 连续可读；Provider 没有显式推理强度时显示“模型默认/不可用”，上下文短条旁显示当前会话预算已用/上限字节而非仅百分比。
- [x] 人工确认状态、工具、Diff、审批、验证和失败形成对话主轴/证据层级，审批卡上下没有中断性空白；不得只以单张截图通过。
- [ ] 不把 Textual Pilot、SVG、快照或 Codex 内嵌终端当作 Terminal.app 证据。

### 5. 持续个人 dogfood

- [ ] 在至少 5 个不同自然日、2 个真实工程中累计至少 20 个完成/失败/取消 Run；其中至少 5 次为跨进程继续或恢复。
- [ ] 每次只记录脱敏摩擦与必要日志引用，不把私有源码、提示或凭据提交到仓库。
- [ ] Critical/High 必须在阶段七建立修正任务、复验并关闭；Medium 必须明确“本阶段修复、用户接受或后续任务”，Low 可汇总。
- [ ] 新缺陷若属于 Core 正确性/可靠性，仍在阶段七修复，但不得借机扩展 Multi-Agent、RAG、插件或桌面范围。

### 6. 最终门禁与状态更新

- [x] 运行完整自动门禁并把实际命令、计数、耗时和失败/重跑原因写入验收文档。
- [x] 更新 `docs/STATUS.md`、`docs/ROADMAP.md` 和本任务文件；没有用户封存原文时只写 `Ready for manual acceptance`。
- [x] 向用户汇报已验证、人工待验和遗留缺陷，等待用户本人决定是否封存。
- [ ] 只有收到用户原文「CLI 版本达到预期，可以封存」后，才把任务/阶段七标记完成，并把阶段八从门禁角度改为可规划；该句本身不自动授权阶段八实施。

## 自动验证

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache env -u DEEPSEEK_API_KEY -u GLM_API_KEY -u VERA_LIVE_API_KEY VERA_PROVIDER_ENV_FILE=/private/tmp/vera-no-provider-file uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/e2e/test_phase_7_product_matrix.py tests/pty tests/performance -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build --out-dir /private/tmp/vera-phase7-acceptance-dist
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run python scripts/smoke_installed_wheel.py --dist /private/tmp/vera-phase7-acceptance-dist --workspace /private/tmp/vera-phase7-acceptance-workspace
git diff --check
```

自动证据完成但人工 dogfood 或封存确认未完成时，可提交自动验收记录：

```bash
git commit -m "docs: record phase seven CLI acceptance"
```

提交不得声称阶段七已完成。

## 验收标准

- 三份阶段七规格的每条标准都有真实证据、明确 `Not run/Blocked` 或关联缺陷。
- wheel 在仓库外、临时私有状态与无 Provider Key 条件下完成全入口回归。
- 真实 Terminal.app 与真实工程的持续 dogfood 无未关闭 Critical/High，Medium 均有处置。
- 用户未给出精确封存原文前，阶段七不标记 Complete，阶段八不开始。

## 验证证据

- 完整非 live：`1068 passed, 2 deselected, 7 warnings in 728.48s`。
- 聚焦：`tests/e2e/test_phase_7_product_matrix.py tests/pty tests/performance` → `22 passed in 36.36s`。
- `ruff check` / `ruff format --check` / `mypy src` / `git diff --check` 通过。
- `uv build --out-dir /private/tmp/vera-phase7-acceptance-dist` 产出 `vera_agent-0.1.0` sdist 与 wheel。
- 仓库外 smoke 退出码 0；使用临时 `VERA_STATE_DIR`，未读真实 Key，未改真实工程。
- PTY JSON `-r` 探针超时从 5s 调整为 20s，避免冷启动 SIGTERM 假失败。
- 阶段七状态：Ready for manual acceptance。任务本身未标 Done。

## 未决

- [docs/evals/phase-7-manual-dogfood.md](../evals/phase-7-manual-dogfood.md) 第 1–4 项走查已过。发现 38–41、43–49 已关闭。发现 42 Low、发现 50–52 High 未关。20 次 dogfood 未完成（已记 10/20，VeraTestDemo + Python 示例、2 个自然日、3 次跨进程）。
- 未收到「CLI 版本达到预期，可以封存」。不得开始阶段八，不得引入 Electron。
