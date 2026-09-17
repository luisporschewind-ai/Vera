# 任务 0063：原生 Git 只读能力实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** Planned；已授权串行实施，依赖 0062 完成
**Goal：** 提供稳定、结构化、无网络的 repository discovery、status/diff/log/show/branch-list 工具。
**Architecture：** `GitService` 只通过 ProcessSupervisor 执行固定 argv；Parser 只消费 Git 稳定机器格式。所有模型可见路径经过 workspace prefix 过滤，Git stderr 只作脱敏诊断。
**Tech Stack：** Python 3.12、系统 Git CLI、ProcessSupervisor、Pydantic 2、pytest 临时仓库。
**Spec：** `docs/specs/2026-09-17-native-git-capability.md`

## Files

- Create: `src/vera/git/__init__.py`
- Create: `src/vera/git/models.py`
- Create: `src/vera/git/discovery.py`
- Create: `src/vera/git/parsers.py`
- Create: `src/vera/git/service.py`
- Create: `src/vera/tools/git.py`
- Modify: `src/vera/bootstrap.py`
- Modify: `src/vera/contracts/compatibility.py`
- Test: `tests/git/conftest.py`
- Test: `tests/git/test_discovery.py`
- Test: `tests/git/test_parsers.py`
- Test: `tests/git/test_read_tools.py`

## Interfaces

```python
class GitStatusEntry(ContractModel):
    path: str
    original_path: str | None
    staged: str
    unstaged: str
    untracked: bool
    conflicted: bool
    submodule: str | None

class GitCommitSummary(ContractModel):
    oid: str
    parent_oids: tuple[str, ...]
    author_name: str
    authored_at: datetime
    subject: str

class GitBranchSummary(ContractModel):
    name: str
    current: bool
    oid: str
    upstream: str | None
    ahead: int
    behind: int

class GitRepositorySnapshot(ContractModel):
    repository_root: str
    workspace_prefix: str
    head_oid: str | None
    branch: str | None
    detached: bool
    unborn: bool
    upstream: str | None
    ahead: int
    behind: int
    operation_state: str
    entries: tuple[GitStatusEntry, ...]

class GitDiffResult(ContractModel):
    scope: Literal["working", "staged", "head", "range"]
    patch: str
    files: tuple[str, ...]
    truncated: bool

class GitShowResult(ContractModel):
    commit: GitCommitSummary
    files: tuple[str, ...]
    diff: GitDiffResult

class GitDiffRequest(ContractModel):
    scope: Literal["working", "staged", "head", "range"]
    base: str | None = None
    target: str | None = None
    paths: tuple[str, ...] = ()
    context_lines: int = 3
    stat_only: bool = False

class GitLogRequest(ContractModel):
    ref: str = "HEAD"
    limit: int = 20
    paths: tuple[str, ...] = ()

class GitShowRequest(ContractModel):
    ref: str
    paths: tuple[str, ...] = ()
    context_lines: int = 3

class GitService:
    def status(self) -> GitRepositorySnapshot: ...
    def diff(self, request: GitDiffRequest) -> GitDiffResult: ...
    def log(self, request: GitLogRequest) -> tuple[GitCommitSummary, ...]: ...
    def show(self, request: GitShowRequest) -> GitShowResult: ...
    def branches(self) -> tuple[GitBranchSummary, ...]: ...
```

## Steps

- [ ] **Step 1: 建立临时仓库 fixture** — helper 固定用户身份、禁用颜色/pager、创建普通仓库、子目录 workspace、linked worktree、detached/unborn/conflict 状态；不读取真实用户仓库。
- [ ] **Step 2: 写 discovery Red 测试** — `.git` 目录/文件、workspace 子目录、非仓库、bare、嵌套仓库、父目录在 workspace 外；断言不自动扩大 workspace。
- [ ] **Step 3: 实现 discovery** — 固定调用 `git rev-parse --show-toplevel --absolute-git-dir --is-bare-repository`，解析规范化路径并分类失败。
- [ ] **Step 4: 写 porcelain v2 parser 测试** — NUL 分隔 fixture 覆盖 staged/unstaged/untracked/rename/delete/conflict/submodule、Unicode、换行和前导 `-` 文件名。
- [ ] **Step 5: 实现 status** — 使用 `git status --porcelain=v2 -z --branch --untracked-files=all`，不解析本地化文本。
- [ ] **Step 6: 写 diff/log/show/branch 测试** — 固定输出上限、path filter、binary summary、明确 ref 先解析 OID、log 最大 20、branch upstream/ahead/behind。
- [ ] **Step 7: 实现只读 service** — 环境固定 `LC_ALL=C`、`GIT_PAGER=cat`、`GIT_OPTIONAL_LOCKS=0`；所有命令 `shell=False`、超时、有界输出、无网络。
- [ ] **Step 8: 注册原生工具** — `git_status/git_diff/git_log/git_show/git_branch_list` effects 为 workspace_read/process_execute；通用 `bash` 的只读 Git 可提示 canonical 工具但不产生写旁路。
- [ ] **Step 9: Event/兼容测试** — 结构化 snapshot/diff facts 不含仓库外路径、凭据或本地化 stderr；CompatibilityManifest 标为 additive。
- [ ] **Step 10: 运行局部与共同门禁** — `uv run pytest tests/git tests/tools/test_bash.py tests/contracts/test_compatibility_manifest.py -q` 后运行共同门禁。
- [ ] **Step 11: 提交（仅用户授权后）** — 提交信息 `feat: add native git read tools`。

## Done

- 五个只读 Git 工具在颜色、Pager、locale 和普通用户配置变化下语义稳定。
- 特殊仓库状态被明确分类，不访问远程、不扩张 workspace。
- 模型和客户端不解析 Git 人类输出。
