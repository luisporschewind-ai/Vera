# 任务 0065：Git Hooks、恢复与分支实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** Planned；已授权串行实施，依赖 0064 完成
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

- [ ] **Step 1: 写 Hook facts/授权测试** — 默认 `.git/hooks`、`core.hooksPath`、不可执行/符号链接/变更内容；untrusted deny，trusted 首次 approval，相同 hash workspace grant 命中，变化后失效。
- [ ] **Step 2: 实现 Hook 检测与审批绑定** — 不使用 `--no-verify`；Hook stdout/stderr 有界脱敏；Hook 修改 plan 外路径或 index 时返回 `git_hook_changed_scope`。
- [ ] **Step 3: 写签名测试** — commit.gpgSign、SSH/GPG 配置、不可交互签名失败；不得修改配置或静默改成 unsigned。
- [ ] **Step 4: 写 Commit 崩溃矩阵** — commit 前、Git 成功后 receipt 前、receipt 后 Event 前、HEAD 被第三方移动；断言分别可重试、补记成功、重放结果或 manual_required，绝不重复 Commit。
- [ ] **Step 5: 扩展 Receipt/Recovery** — operation 增加 `git_commit/git_branch`；receipt 保存旧/新 OID、tree hash、plan hash，公开恢复事实不含 message/凭据。
- [ ] **Step 6: 写 branch create/switch Red 测试** — 非法/ref 冲突名称、分支已存在/缺失、dirty、staged、活动 Run、detached、HEAD stale；禁止 `-f` 和隐式新建。
- [ ] **Step 7: 实现 branch tools** — `git_branch_create` 只在明确目标和稳定 HEAD 下创建；`git_branch_switch` 需要干净工作树、无待审批/活动副作用，默认 approval；完成后验证 HEAD/branch。
- [ ] **Step 8: 客户端与恢复对照** — TUI/Plain/JSON 展示 hook approval、commit recovery、branch changed 同一结构化事实，不解析 stderr。
- [ ] **Step 9: 运行局部与共同门禁** — `uv run pytest tests/git/test_hooks_and_signing.py tests/git/test_branches.py tests/recovery/test_git_recovery.py tests/e2e/test_crash_recovery.py -q` 后运行共同门禁。
- [ ] **Step 10: 提交（仅用户授权后）** — 提交信息 `feat: add git recovery and branch tools`。

## Done

- Hook 和签名不会被静默跳过或降级；授权随事实变化失效。
- 崩溃恢复不重复 Commit，无法证明时停止。
- branch create/switch 精确、可审阅，不包含 delete/revert/remote/history rewrite。
