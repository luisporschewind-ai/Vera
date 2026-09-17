# 任务 0064：GitCommitPlan 与精确提交实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** Planned；已授权串行实施，依赖 0063 完成
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

- [ ] **Step 1: 写 Plan Red 测试** — 仅允许当前 Run 成功动作路径；空路径、workspace 外、detached/unborn/conflict/operation state、缺身份、验证失败、目标原有 staged 内容全部稳定拒绝。
- [ ] **Step 2: 实现 Planner** — 读取 HEAD/branch/index/path facts，规范化 literal pathspec，计算 index/staged/message/policy hash；公开 Event 只含标题和摘要。
- [ ] **Step 3: 冻结系统 Git pathspec 行为测试** — 在临时仓库验证 modified/new/delete/rename、其他 staged、同路径 staged+unstaged、Unicode/空格/换行/前导 `-`；这些测试先于 Committer 实现。
- [ ] **Step 4: 写事务失败测试** — 在 `git add -A -- <paths>`、`git commit --only -F <0600-file> -- <paths>`、ref 更新和结果验证点注入失败，断言无关 index 字节不变或进入 manual_required。
- [ ] **Step 5: 实现 index backup 与事务** — backup 写 Vera 私有 run 目录并 `0600`；每一步前后重验 HEAD/index/paths；不使用 `git add .`、`git add -A` 无 pathspec或无 pathspec commit。
- [ ] **Step 6: 实现提交消息安全** — 拒绝 NUL/控制字符/超限和秘密命中；使用 Vera 私有临时文件，不启动 editor，不添加尾注，不修改 user.name/email。
- [ ] **Step 7: 结果反向验证** — 比较新 Commit 父 OID、路径集合、blob/mode、目标 after hash、剩余 staged diff 和无关 index；不一致返回 `git_commit_result_mismatch`。
- [ ] **Step 8: 接入 Policy/Approval** — 用户明确要求且 trusted、当前 Run、验证通过可 allow；模型自行建议或用户既有修改必须 approval/deny；Approval 绑定完整 plan hash。
- [ ] **Step 9: Runtime/客户端测试** — `git_commit` 成功、拒绝、stale、身份缺失和失败事件顺序一致；通用 `bash git commit` 返回 `use_native_git_tool`。
- [ ] **Step 10: 运行局部与共同门禁** — `uv run pytest tests/git/test_commit_plan.py tests/git/test_commit_transaction.py tests/runtime/test_git_commit_tool.py -q` 后运行共同门禁。
- [ ] **Step 11: 提交（仅用户授权后）** — 提交信息 `feat: add scoped native git commits`。

## Done

- 精确 Commit 不夹带其他 staged/unstaged 内容，不自动修改身份、签名或 remote。
- HEAD/index/path/Policy 变化使旧计划 stale。
- 失败有确定恢复或 manual_required，不猜测成功。
