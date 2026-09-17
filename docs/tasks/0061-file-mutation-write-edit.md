# 任务 0061：write/edit 与多动作文件变更实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** Planned；已授权串行实施，依赖 0060 完成
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

- [ ] **Step 1: 写 Planner Red 测试** — 覆盖 create/replace、唯一 exact edit、零匹配、多匹配、非 UTF-8、symlink、缺失父目录、before hash 不符和路径逃逸。
- [ ] **Step 2: 运行 Red** — `uv run pytest tests/workspace/test_file_mutation.py -q`；预期模块不存在。
- [ ] **Step 3: 实现计划生成** — `FileMutationPlanner.plan_write()`/`plan_edit()` 只读事实并生成 Diff；不写文件、不创建父目录、不批准自身。
- [ ] **Step 4: 写 apply/rollback 测试** — 动作前重新检查事实；原子写入；Checkpoint 先于副作用；失败恢复字节；同 receipt 重放不二次写入。
- [ ] **Step 5: 实现 Applier 与 Receipt 扩展** — `OperationReceipt.operation` 增加 `file_mutation` 的版本化读写；旧 receipt decoder 不变，未知 future version 拒绝。
- [ ] **Step 6: 写 Runtime 多动作失败测试** — 同一 Run 连续 `edit → read → write → verification`；每步有 action_id，累计 Diff 包含两个文件，模型收到每次 ToolResult。
- [ ] **Step 7: 接入 `write/edit`** — 在 ToolExecutor 中将输入转为计划；`balanced + trusted + implementation goal` 可自动应用，其他情况生成参数绑定 Approval。
- [ ] **Step 8: 写恢复分类测试** — before 仍在=可重试、after 已在且 receipt 匹配=补记完成、第三种字节=manual_required；不得重复写入。
- [ ] **Step 9: 旧 Change Set 兼容回归** — legacy fixture、pending approval、partial apply、rollback 场景继续按旧 decoder 恢复；新代码不重写旧 Journal。
- [ ] **Step 10: 运行局部与共同门禁** — `uv run pytest tests/workspace/test_file_mutation.py tests/runtime/test_write_edit_tools.py tests/recovery/test_file_mutation_resume.py tests/persistence/test_legacy_state.py -q` 后运行共同门禁。
- [ ] **Step 11: 提交（仅用户授权后）** — 提交信息 `feat: add recoverable write and edit tools`。

## Done

- `write/edit` 可多次执行，零/多匹配稳定失败，不静默模糊编辑。
- 每个动作可独立检查、撤销和恢复；累计 Diff 不丢失动作身份。
- 新旧恢复格式并存，崩溃不会重复文件副作用。
