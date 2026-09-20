# 任务 0065：Git Hooks、恢复与分支实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** In progress；已完成本地切片提交 `6d0e37f`、`aeec20e`，依赖 0064 已满足
**Goal：** 完成 Commit Hooks/签名边界、崩溃幂等恢复和安全的 branch create/switch，使原生 Git 达到阶段退出范围。
**Architecture：** Hook 授权绑定 hook 路径、内容 hash、Git 配置和 Policy；Commit Receipt 记录预期新 OID。Recovery 只在能证明结果时补记或重试，否则 manual_required。分支动作使用精确旧 HEAD/工作树事实做 CAS 式校验。
**Tech Stack：** Python 3.12、系统 Git CLI、OperationReceipt/Recovery、pytest failpoints。
**Spec：** `docs/specs/2026-09-17-native-git-capability.md`

## Files

- Create: `src/vera/git/hooks.py`
- Create: `src/vera/git/branches.py`
- Create: `src/vera/recovery/git.py`
- Modify: `src/vera/git/commit.py`
- Modify: `src/vera/git/service.py`
- Modify: `src/vera/persistence/operation_receipt.py`
- Modify: `src/vera/recovery/classifier.py`
- Modify: `src/vera/recovery/resume.py`
- Modify: `src/vera/tools/git.py`
- Test: `tests/git/test_hooks_and_signing.py`
- Test: `tests/git/test_branches.py`
- Test: `tests/recovery/test_git_recovery.py`
- Modify: `tests/e2e/test_crash_recovery.py`

## Interfaces

```python
class GitHookEntry(ContractModel):
    name: str
    relative_path: str
    content_hash: str
    executable: bool

class GitHookFacts(ContractModel):
    hooks_path: str
    hooks: tuple[GitHookEntry, ...]
    facts_hash: str

class GitBranchPlan(ContractModel):
    action_id: str
    operation: Literal["create", "switch"]
    branch_name: str
    expected_head_oid: str
    expected_worktree_hash: str
    policy_hash: str
```

## Steps

- [x] **Step 1: 写 Hook facts/授权测试** — 默认 `.git/hooks`、`core.hooksPath`、不可执行/符号链接/变更内容；untrusted deny，trusted 首次 approval。
- [x] **Step 2: 实现 Hook 检测与审批绑定** — 不使用 `--no-verify`；Hook 输出沿用有界子进程通道；Hook 修改 plan 外路径或 index 返回 `git_hook_changed_scope`。
- [x] **Step 3: 写签名测试** — 覆盖 commit.gpgSign、SSH 配置事实和不可用签名的稳定错误；不修改配置、不静默降级。
- [x] **Step 4: 写 Commit 崩溃矩阵** — 覆盖 receipt 写入失败后的补记、不重复 Commit，以及第三方 HEAD 变化进入 `manual_required`。
- [x] **Step 5: 扩展 Receipt/Recovery** — operation 支持 `git_commit/git_branch`；receipt 保存旧/新 OID、tree、路径和剩余 staged diff facts，不含 message。
- [x] **Step 6: 写 branch create/switch Red 测试** — 覆盖非法名称、dirty、已存在/缺失、HEAD stale 和 clean-state 边界；禁止 `-f` 与隐式新建。
- [x] **Step 7: 实现 branch tools** — `git_branch_create`/`git_branch_switch` 通过 ToolExecutor，稳定事实校验、默认 approval、完成后验证 HEAD/branch。
- [ ] **Step 8: 客户端与恢复对照** — 待补 Run 级 Git pending operation 快照、结构化 started/completed/recovered/manual_required 事件及 TUI/Plain/JSON 对照。
- [x] **Step 9: 运行局部与共同门禁** — 受影响测试 `48 passed`；全量 non-live `1286 passed, 2 deselected, 4 errors`，4 个 error 均为 DNS 无法解析 PyPI `hatchling` 的打包/e2e setup 阻塞；Ruff/format/Mypy/diff 通过。
- [x] **Step 10: 提交（仅用户授权后）** — 当前切片提交 `6d0e37f`、`aeec20e`；任务仍未完成，待 Step 8。

## Done

- Hook 和签名不会被静默跳过或降级；授权随事实变化失效。
- 崩溃恢复不重复 Commit，无法证明时停止。
- branch create/switch 精确、可审阅，不包含 delete/revert/remote/history rewrite。

当前剩余：把 Git 操作状态纳入 Run 级恢复快照与结构化事件，并让客户端共享同一恢复事实；完成前不得把 0065 标记 Done 或进入 0066。
