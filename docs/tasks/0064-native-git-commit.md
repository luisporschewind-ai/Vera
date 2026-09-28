# 任务 0064：GitCommitPlan 与精确提交实施计划

> 2026-09-26 文档对齐：本记录来自 `codex/phase-8-tooling-policy-git`（核对时 HEAD `5b6d789`）。实现及验证属于该隔离分支，尚未合入 `main`；同步文档不代表代码集成或本轮重新测试。下文提交/推送表述保留各任务完成时的历史边界，当前分支状态见阶段八执行计划。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** Done；本地提交 `de93fb2`、`781e756`，未合并、未推送
**Goal：** 让 Vera 提交当前 Run 的精确已验证路径，不夹带或丢失用户既有 index 内容，并对结果进行反向验证。
**Architecture：** Planner 绑定 HEAD、branch、index fingerprint、目标路径/hash、验证与 Policy；Committer 在真实 index 上执行 path-scoped 事务，副作用前保存 Vera 私有 index backup，失败时只在事实仍匹配时恢复。成功后验证 commit tree 和剩余 staged diff，再写 Receipt。
**Tech Stack：** Python 3.12、系统 Git CLI、ProcessSupervisor、PrivateWriter/OperationReceipt、pytest 临时仓库。
**Spec：** `docs/specs/2026-09-17-native-git-capability.md`

## Files

- Create: `src/vera/git/commit_plan.py`
- Create: `src/vera/git/commit.py`
- Modify: `src/vera/git/models.py`
- Modify: `src/vera/git/service.py`
- Modify: `src/vera/tools/git.py`
- Modify: `src/vera/persistence/operation_receipt.py`
- Modify: `src/vera/runtime/engine.py`
- Test: `tests/git/test_commit_plan.py`
- Test: `tests/git/test_commit_transaction.py`
- Test: `tests/runtime/test_git_commit_tool.py`

## Interfaces

```python
class GitCommitPlan(ContractModel):
    plan_id: str
    run_id: str
    action_ids: tuple[str, ...]
    workspace_identity: str
    repository_root: str
    workspace_prefix: str
    head_oid: str
    branch: str
    index_fingerprint: str
    paths: tuple[str, ...]
    before_hashes: dict[str, str]
    after_hashes: dict[str, str]
    staged_diff_hash: str
    commit_message_hash: str
    verification_status: str
    policy_hash: str

class GitCommitResult(ContractModel):
    plan_id: str
    old_head_oid: str
    new_head_oid: str
    tree_oid: str
    committed_paths: tuple[str, ...]
    remaining_staged_diff_hash: str

class GitCommitter:
    def execute(self, plan: GitCommitPlan, message: str) -> GitCommitResult: ...
```

## Steps

- [x] **Step 1: 写 Plan Red 测试** — 空路径、workspace 外、detached/unborn/conflict/operation state、验证失败、目标原有 staged 内容稳定拒绝。
- [x] **Step 2: 实现 Planner** — 读取 HEAD/branch/index/path facts，规范化 literal pathspec，计算 index/staged/message/policy hash。
- [x] **Step 3: 冻结系统 Git pathspec 行为测试** — 临时仓库覆盖 modified/new/delete/rename、其他 staged、Unicode/空格/前导 `-` 和多路径顺序。
- [x] **Step 4: 写事务失败测试** — pre-commit 失败后断言 index 字节和无关 staged 内容保持不变。
- [x] **Step 5: 实现 index backup 与事务** — backup 写 Vera 私有 run 目录并 `0600`；使用 path-scoped `git add -A` 与 `git commit --only`。
- [x] **Step 6: 实现提交消息安全** — 拒绝控制字符、超限和秘密命中；使用 Vera 私有 `0600` 临时文件，不修改身份。
- [x] **Step 7: 结果反向验证** — 校验新 Commit 父 OID、路径集合、目标 after hash 和剩余 staged diff。
- [x] **Step 8: 接入 Policy/Approval** — `git_commit` 进入 ToolExecutor 的 Policy、Approval、plan hash 与 Receipt 管线。
- [x] **Step 9: Runtime/客户端测试** — `git_commit` 通过 ToolExecutor 成功提交并保留无关 staged 内容；通用 bash Git 写入继续返回 `use_native_git_tool`。
- [x] **Step 10: 运行局部与共同门禁** — 局部 22 passed；共同 non-live 1268 passed、2 deselected，4 个 wheel/e2e setup 因 DNS 无法解析 PyPI 的 `hatchling`。
- [x] **Step 11: 提交（仅用户授权后）** — `de93fb2`，路径矩阵补充 `781e756`。

## Done

- 精确 Commit 不夹带其他 staged/unstaged 内容，不自动修改身份、签名或 remote。
- HEAD/index/path/Policy 变化使旧计划 stale。
- 失败先恢复 Vera 私有 index backup；恢复失败返回 `manual_required`，不猜测成功。

Hook 授权、签名策略、崩溃后的幂等补记以及 branch create/switch 仍属于后续任务 0065，不由本任务提前实现。
