# 任务 0061：write/edit 与多动作文件变更实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** Done；用户已明确要求直接推进，使用同一隔离工作树串行实施
**Goal：** 实现可重复调用、可检查、可恢复的 `write/edit`，用动作级 `FileMutationPlan` 支撑多动作 Run 和累计 Diff，同时保留旧 Change Set 恢复能力。
**Architecture：** `FileMutationPlanner` 生成绑定 path fact、before/after hash 和 Diff 的不可变计划；ToolExecutor 经 Policy 后调用 `FileMutationApplier`。每个动作独立 Checkpoint/Receipt，Run 只聚合事实，不把多个文件压回单一 Change Set。
**Tech Stack：** Python 3.12、Pydantic 2、现有 WorkspacePaths/Checkpoint/ChangeSet/Recovery、pytest。
**Spec：** `docs/specs/2026-09-17-core-tooling-and-risk-tiered-policy.md`

## Files

- Create: `src/vera/contracts/file_mutations.py`
- Create: `src/vera/workspace/mutation.py`
- Create: `src/vera/tools/file_mutation.py`
- Modify: `src/vera/workspace/apply.py`
- Modify: `src/vera/workspace/checkpoint.py`
- Modify: `src/vera/persistence/operation_receipt.py`
- Modify: `src/vera/persistence/recovery_snapshot.py`
- Modify: `src/vera/recovery/classifier.py`
- Modify: `src/vera/recovery/resume.py`
- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/runtime/context.py`
- Test: `tests/workspace/test_file_mutation.py`
- Test: `tests/runtime/test_write_edit_tools.py`
- Test: `tests/recovery/test_file_mutation_resume.py`
- Modify: `tests/persistence/test_legacy_state.py`

## Interfaces

```python
class FileMutationPlan(ContractModel):
    schema_version: Literal[1] = 1
    action_id: str
    run_id: str
    operation: Literal["create", "replace", "edit"]
    path: str
    before_hash: str
    after_hash: str
    target_facts_hash: str
    unified_diff: str
    content_hash: str

class ExactEditInput(BaseModel):
    path: str
    old_text: str
    new_text: str
    expected_before_hash: str | None = None
```

## Steps

- [x] **Step 1: 写 Planner Red 测试** — 覆盖 create/replace、唯一 exact edit、零匹配、多匹配、非 UTF-8、symlink、缺失父目录、before hash 不符和路径逃逸。
- [x] **Step 2: 运行 Red** — `uv run pytest tests/workspace/test_file_mutation.py -q`；已观察到模块缺失的预期失败。
- [x] **Step 3: 实现计划生成** — `FileMutationPlanner.plan_write()`/`plan_edit()` 只读事实并生成 Diff；不写文件、不创建父目录、不批准自身。
- [x] **Step 4: 写 apply/rollback 测试** — 动作前重新检查事实；原子写入；Checkpoint 先于副作用；失败恢复字节；同 receipt 重放不二次写入。
- [x] **Step 5: 实现 Applier 与 Receipt 扩展** — `OperationReceipt.operation` 增加 `file_mutation` 的版本化读写；旧 receipt decoder 不变，未知 future version 拒绝。
- [x] **Step 6: 写 Runtime 多动作失败测试** — 同一 Run 连续 `edit → read → write`，每步有 action_id，累计 Diff 包含两个文件，模型收到每次 ToolResult；verification 继续复用既有 Core 路径。
- [x] **Step 7: 接入 `write/edit`** — 在 ToolExecutor 中将输入转为计划；`balanced + trusted + implementation goal` 可自动应用，其他情况生成参数绑定 Approval。
- [x] **Step 8: 写恢复分类测试** — before 仍在=可重试、after 已在且 receipt 匹配=补记完成、第三种字节=manual_required；不得重复写入。
- [x] **Step 9: 旧 Change Set 兼容回归** — legacy fixture、pending approval、partial apply、rollback 场景继续按旧 decoder 恢复；新代码不重写旧 Journal。
- [x] **Step 10: 运行局部与共同门禁** — 局部测试、共同 non-live、Ruff、格式、Mypy、wheel/sdist 与 `git diff --check` 均已通过。
- [x] **Step 11: 提交（仅用户授权后）** — 实现提交 `f35b2e1 feat: add recoverable write and edit tools`；审查修复提交 `3b1fe2f fix: close file mutation safety gaps`。

## Done

- `write/edit` 可多次执行，零/多匹配稳定失败，不静默模糊编辑。
- 每个动作可独立检查、撤销和恢复；累计 Diff 不丢失动作身份。
- 新旧恢复格式并存，崩溃不会重复文件副作用。

## 当前证据与待完成项

- 2026-09-19：Planner、Checkpoint-before-effect Applier、动作级 Receipt、Runtime `write/edit`、审批恢复、累计 Diff 与兼容清单已接入；补齐落盘前输出上限、Checkpoint 绑定回滚和父目录竞态保护；相关 workspace/runtime/recovery/persistence/contracts/tools/CLI/presentation 分组 `555 passed`；Ruff、格式、Mypy 与 `git diff --check` 通过。
- 实现与本地审查修复已提交；真实 Terminal.app 独立 `VERA_STATE_DIR` 下完成首屏与窄窗口视觉走查，品牌、工作区/模型信息、输入框和状态栏无裁切；最新共同 non-live 为 `1208 passed, 2 deselected, 6 warnings`，Ruff、格式、Mypy、wheel/sdist 与 `git diff --check` 均通过；0062 仍未启动，等待用户重新授权。
