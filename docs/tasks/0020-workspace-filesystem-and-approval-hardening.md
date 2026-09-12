# 任务 0020：文件系统与审批事实加固

> 供 Cursor 执行：按 `superpowers:executing-plans` 逐项实施；新行为必须执行 Red → Green → Refactor。

**状态：** Planned
**执行就绪：** 是
**分支：** `phase-5/0020-filesystem-approval-hardening`
**依赖：** 最新干净 `main`
**规格：** [阶段五 Core 加固](../specs/2026-09-12-core-security-and-reliability-hardening.md)

## 目标与边界

消除路径解析与实际读写之间的事实漂移；拒绝符号链接替换、特殊文件和 workspace 逃逸；让审批绑定当前文件事实并在事实变化后过期；让私有证据写入不改动既有父目录权限。

不增加新工具、不改变正常审批 UX、不修改用户工程，不把 Vera 描述为 OS 沙箱。

## 设计约束

- `WorkspacePaths` 仍是路径边界的单一权威，读写器必须消费它返回的受检事实。
- 引入不可变 `PathFact`：规范路径、相对路径、存在性、文件类型、device/inode、mode、size、mtime_ns 和内容 hash（适用时）。
- 写入前在打开后的文件描述符上复核事实；平台不支持的字段显式记录为 unavailable，不能假装相等。
- 只允许普通文件和不存在的新文件目标；FIFO、Socket、设备、目录替文件及逃逸链接失败关闭。
- Approval target hash 包含规范动作、目标、workspace identity、policy hash 和 `PathFact` 摘要。
- 私有文件创建使用 `O_CREAT|O_EXCL`、`0600` 和同目录原子替换；绝不 `chmod` 调用者预先存在的父目录。

## 实施步骤

### 1. 建立路径事实负例

**修改：**

- `src/vera/workspace/paths.py`
- `tests/workspace/test_paths.py`
- 新增 `tests/workspace/test_path_facts.py`

**测试先行：**

1. 覆盖 `..`、绝对路径、Unicode 文件名、workspace 内链接和逃逸链接。
2. 覆盖 FIFO、Unix Socket、目录冒充文件；设备文件只做类型判定，不读写真实设备。
3. 在检查后替换 inode、普通文件替换成链接时，旧 `PathFact` 验证失败。
4. 运行 `uv run pytest tests/workspace/test_paths.py tests/workspace/test_path_facts.py -q`，确认新用例因缺少事实模型失败。

**最小实现：**

- 在 `paths.py` 增加 `PathFact`、`WorkspacePaths.inspect_read()`、`inspect_mutation()` 与 `revalidate()`。
- 使用 `lstat` 区分链接和特殊文件；所有错误映射为稳定 workspace 错误码。
- 保留现有 `resolve_read/resolve_mutation` 兼容入口，但内部委托新 API。

### 2. 让 Change Set、Apply 和 Checkpoint 复核同一事实

**修改：**

- `src/vera/workspace/changeset.py`
- `src/vera/workspace/apply.py`
- `src/vera/workspace/checkpoint.py`
- `tests/workspace/test_changeset.py`
- `tests/workspace/test_apply.py`
- `tests/workspace/test_checkpoint.py`

**测试先行：**

1. Change Set 建立后替换目标 inode、链接目标或文件类型，apply 必须零写入失败。
2. 多文件 Change Set 中任一事实变化，预检在第一笔写入前失败。
3. Checkpoint 拒绝非普通文件和变化后的基线；部分失败仍能恢复已经触达的文件。
4. 确认失败用例后，在 `BuiltChangeSet` 保存不可变事实摘要，在 `_preflight` 和打开后的 fd 上复核。

### 3. 审批绑定与过期矩阵

**修改：**

- `src/vera/contracts/approvals.py`
- `src/vera/runtime/approval.py`
- `src/vera/runtime/engine.py`
- `docs/decisions/ADR-0007-unified-policy-engine.md`
- `tests/runtime/test_approval.py`
- `tests/runtime/test_safe_editing_flow.py`

**测试先行：**

1. 重复、未知、跨 run、跨 workspace、policy hash 变化和路径事实变化的 approval 全部失败关闭。
2. 拒绝、取消和过期审批不创建 Checkpoint、不写文件、不启动验证。
3. 兼容读取旧 schema，但旧审批在缺少事实绑定时不得直接授权新写入。

**最小实现：**

- 升级 approval schema，增加 `fact_hash` 和明确的 expiry reason。
- `ApprovalGate.resolve()` 只记录用户决定；Runtime 在产生副作用前重新计算 workspace、policy 与事实 hash。
- 输出结构化 `approval.expired`，Presenter 仅展示，不决定是否允许。

### 4. 私有原子写入器

**修改：**

- 新增 `src/vera/persistence/private_writer.py`
- `src/vera/evals/evidence.py`
- `src/vera/evals/runner.py`
- `tests/persistence/test_private_writer.py`
- `tests/evals/test_evidence.py`
- `tests/evals/test_runner.py`

**测试先行：**

1. 既有父目录 mode 在发布前后完全相同。
2. 新文件为 `0600`，临时目录/新建目录为 `0700`；链接目标、重复目标和竞态创建失败关闭。
3. suite report 与单 case 证据均使用原子替换，失败不留下半文件。

**最小实现：**

- 提供 `PrivateAtomicWriter.write_bytes(path, data)`；只管理自己创建的精确文件和临时项。
- EvidenceWriter 和 suite report 复用该实现，删除各自权限与写入分支。

## 验证与提交

先运行全部聚焦测试，再运行[阶段五共同门禁](phase-5-execution-order.md)。额外执行：

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/workspace tests/persistence tests/runtime/test_approval.py tests/runtime/test_safe_editing_flow.py tests/evals/test_evidence.py tests/evals/test_runner.py -q
```

检查 Diff 中没有宽松的异常吞噬、`follow_symlinks=True`、`shell=True` 或对既有父目录的 `chmod`。更新本任务状态和验证结果后提交：

```bash
git commit -m "feat: harden workspace facts and approvals"
```

## 验收标准

- 全部特殊路径和竞态负例失败关闭且零未批准副作用。
- 审批事实变化后必须重新生成，旧审批不能跨 run/workspace 使用。
- 证据与 suite report 私有、原子，既有父目录权限不变。
- 公共字段变更有 schema 兼容测试，四个 Core 客户端无需解析文本。
