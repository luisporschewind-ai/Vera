# 任务 0066：阶段八验收与真实 dogfood 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** Planned；已授权串行实施，依赖 0059–0065 完成
**Goal：** 用离线矩阵、安装态、PTY 和三类真实工程证明 Pi 对齐工具、Policy v2 与原生 Git 达到个人使用标准，并关闭阶段八。
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

- [ ] **Step 1: 写 E2E Red 矩阵** — 每组至少一个 allow、approval、deny/stale/failed 负例；测试只用临时 workspace/state 和 Fake Model，不读取真实 Key。
- [ ] **Step 2: 运行矩阵并分类缺口** — `uv run pytest tests/e2e/test_phase_8_tooling_policy.py tests/e2e/test_phase_8_native_git.py tests/e2e/test_phase_8_client_parity.py -q`；任何失败回到拥有该行为的 0059–0065，不在验收任务堆旁路修复。
- [ ] **Step 3: PTY 验收** — 80×24 与 60×16 覆盖 trust、三作用域审批、累计 Diff、bash 截断、Git Commit/Hook approval/recovery；无色模式保留文字语义。
- [ ] **Step 4: wheel smoke** — 从 `/private/tmp/vera-phase8-venv` 安装新 wheel，在仓库外临时项目跑 canonical read/write/edit、拒绝 shell 语法、只读 Git 和精确 Commit；环境清除 Provider Key。
- [ ] **Step 5: 完整自动门禁** — 运行阶段八共同 pytest/Ruff/format/Mypy/build/diff-check，记录精确数量、耗时、warnings、未运行 live。
- [ ] **Step 6: Python 真实工程 dogfood** — 在安全副本完成调查、两次 edit、pytest/ruff、Diff、精确 Commit、branch create/switch；比较 workspace manifest 和 index 保全。
- [ ] **Step 7: Node/TypeScript 真实工程 dogfood** — 完成多文件修改、测试/typecheck、依赖安装审批负例、Commit；确认 `node_modules`/构建产物策略与验证隔离。
- [ ] **Step 8: Swift/Xcode 真实工程 dogfood** — 使用 workspace 外 DerivedData，完成源码 edit、xcodebuild、Diff、Commit；工程根不新增 build/cache。
- [ ] **Step 9: 安全对抗** — 恶意 README/AGENTS/Skill/tool output 诱导 sudo、secret、curl、git push、reset/clean、hook 变化全部不能提升权限。
- [ ] **Step 10: 记录证据** — `docs/evals/phase-8-tooling-policy-git.md` 逐条对应两份规格验收标准，区分 verified、blocked、not run、assumption，不记录秘密或私有源码。
- [ ] **Step 11: 用户验收门** — 自动和真实证据满足后请用户确认阶段八结果；没有明确确认时 ROADMAP/STATUS 最多为 `Ready for manual acceptance`。
- [ ] **Step 12: 文档收口与提交（仅用户授权后）** — 用户确认后将任务/阶段标为 Done/Complete，提交信息 `docs: record phase eight tooling acceptance`；不自动开始阶段九 Skills。

## Done

- 两份规格全部验收条目都有可追溯证据。
- 低风险日常工作无重复审批，高风险/外部/不可恢复边界清楚。
- 三类真实工程无未关闭 Critical/High，工作区和 Git index 无隐藏污染。
- 用户确认阶段八后才 Complete；阶段九仍需独立实施授权。
