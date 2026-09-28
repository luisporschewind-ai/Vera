# 任务 0066：阶段八验收与真实 dogfood 实施计划

> 2026-09-26 文档对齐：本记录来自 `codex/phase-8-tooling-policy-git`（核对时 HEAD `5b6d789`）。实现及验证属于该隔离分支，尚未合入 `main`；同步文档不代表代码集成或本轮重新测试。下文提交/推送表述保留各任务完成时的历史边界，当前分支状态见阶段八执行计划。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** Ready for manual acceptance；自动证据已形成，等待真实 Terminal.app 与用户确认
**Goal：** 用离线矩阵、安装态、PTY 和三类真实工程形成 Pi 对齐工具、Policy v2 与原生 Git 的阶段八验收证据；用户确认后才关闭阶段八。
**Architecture：** 新增阶段八 E2E/安全矩阵和固定 Fake Model 脚本，所有客户端消费同一 Core 事实；自动证据只形成 Ready for manual acceptance，真实 Terminal.app 和用户确认才允许 Complete。
**Tech Stack：** pytest、PTY、uv build/wheel、Terminal.app、Python/Node/Swift 安全副本、系统 Git。
**Spec：** 两份阶段八 Accepted 规格与 `docs/tasks/phase-8-execution-order.md`

## Files

- Create: `tests/e2e/test_phase_8_tooling_policy.py`
- Create: `tests/e2e/test_phase_8_native_git.py`
- Create: `tests/e2e/test_phase_8_client_parity.py`
- Create: `tests/pty/test_phase_8_tooling.py`
- Modify: `scripts/smoke_installed_wheel.py`
- Create: `docs/evals/phase-8-tooling-policy-git.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/tasks/phase-8-execution-order.md`
- Modify: this task

## Acceptance Matrix

```text
A  read/grep/find/ls canonical tools and legacy decoder
B  trusted balanced write/edit without repeated approval
C  untrusted/review/high-risk approval and forbidden denial
D  structured bash timeout/cancel/output/secret/shell-negative cases
E  multi-action Diff, Checkpoint, receipt, stale and crash recovery
F  git status/diff/log/show/branch-list special repository states
G  exact commit with mixed index/new/delete/rename/special paths
H  hooks/signing/identity/recovery/branch create/switch
I  TUI/Plain/JSON/Event/Journal/CompatibilityManifest parity
J  Python, Node/TypeScript, Swift/Xcode Terminal.app dogfood
```

## Steps

- [x] **Step 1: 写 E2E Red 矩阵** — 每组至少一个 allow、approval、deny/stale/failed 负例；测试只用临时 workspace/state 和 Fake Model，不读取真实 Key。
- [x] **Step 2: 运行矩阵并分类缺口** — 阶段八新增 E2E/PTY 共 `10 passed`；发现的 clean-install 循环导入回到 Core 修复并回归。
- [x] **Step 3: PTY 验收** — 阶段八 PTY 覆盖 plain Git boundary、文字语义和无 ANSI；完整非 live 通过，人工尺寸矩阵仍待 Terminal.app。
- [x] **Step 4: wheel smoke** — 仓库外临时 dist/workspace 安装态运行 canonical read/write/edit、shell deny、Git init/status/exact commit，`All checks passed!`。
- [x] **Step 5: 完整自动门禁** — `1307 passed, 2 deselected, 8 warnings`；Ruff、format、Mypy、wheel/sdist、diff-check 均通过；live 未运行。
- [x] **Step 6: Python 真实工程 dogfood** — 安全副本完成 edit、pytest/ruff、原生精确 Commit `5e702ba`、branch create/switch，工作区干净。
- [ ] **Step 7: Node/TypeScript 真实工程 dogfood** — edit 已完成；Node `.ts` 测试发现 0 个测试，离线 `tsc` 为 `ENOTCACHED`，待真实 TypeScript runner/compiler 环境复验。
- [x] **Step 8: Swift/Xcode 真实工程 dogfood** — 安全副本使用 workspace 外 DerivedData，`xcodebuild` 在 `CODE_SIGNING_ALLOWED=NO` 模拟器边界下成功，原生精确 Commit `78afaed`，工程根无 DerivedData。
- [x] **Step 9: 安全对抗** — 恶意/不可信边界的 shell、Git push、hook、secret 与恢复专项通过；安全/拒绝/崩溃恢复/Bash/Git/恢复专项 `35 passed`。
- [x] **Step 10: 记录证据** — 已创建 `docs/evals/phase-8-tooling-policy-git.md`，逐条区分 verified、blocked、not run、assumption，不记录秘密或私有源码。
- [ ] **Step 11: 用户验收门** — 自动和真实证据满足后请用户确认阶段八结果；没有明确确认时 ROADMAP/STATUS 最多为 `Ready for manual acceptance`。
- [ ] **Step 12: 文档收口与提交（仅用户授权后）** — 用户确认后将任务/阶段标为 Done/Complete，提交信息 `docs: record phase eight tooling acceptance`；不自动开始阶段九 Skills。

## Done

- 两份规格全部验收条目都有可追溯证据。
- 低风险日常工作无重复审批，高风险/外部/不可恢复边界清楚。
- 三类真实工程无未关闭 Critical/High，工作区和 Git index 无隐藏污染。
- 用户确认阶段八后才 Complete；阶段九已于 2026-09-21 获得单独并行实施授权；该授权不关闭阶段八门禁。
