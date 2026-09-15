# 任务 0035：安全 Session Journal、Store 与修复副本

> 供主实现 Agent 执行：按 `superpowers:test-driven-development` 实施；所有损坏与权限行为先写负例。

**状态：** Planned
**执行就绪：** 否；等待任务 0034 完成
**分支：** `phase-7/0035-session-journal-store`
**依赖：** 任务 0034
**规格：** [持久化对话会话](../specs/2026-09-13-persistent-conversation-sessions.md)、[ADR-0016](../decisions/ADR-0016-persistent-conversation-sessions.md)

## 目标与边界

实现 `sessions/<session-id>/session.jsonl` 的唯一写入口，覆盖私有权限、无符号链接、追加 `fsync`、workspace 绑定、列表/最近项、损坏分类和“从有效尾部前缀创建新副本”。本任务不接入 Controller，也不自动修复或原地改写旧 Journal。

## 公开接口

在 `src/vera/persistence/session_store.py` 定义：

```python
class LoadedConversationSession(BaseModel):
    session_id: str
    workspace_root: Path
    title: str
    records: tuple[ConversationSessionRecord, ...]
    model_messages: tuple[ConversationMessage, ...]
    history_messages: tuple[ConversationMessage, ...]
    compaction_count: int
    updated_at: datetime

class ConversationSessionSummary(BaseModel):
    session_id: str
    title: str
    updated_at: datetime
    message_count: int
    latest_run_id: str | None
    latest_run_state: str | None
    recoverable: bool

class SessionRepairPlan(BaseModel):
    source_session_id: str
    valid_through_sequence: int
    failure_code: str
    repairable_tail_only: bool

class ConversationSessionStore:
    def create(self, workspace: Path) -> LoadedConversationSession: ...
    def append_turn(self, session_id: str, turn: ConversationTurn) -> ConversationSessionRecord: ...
    def append_compaction(self, session_id: str, summary: str, through_sequence: int) -> ConversationSessionRecord: ...
    def rename(self, session_id: str, title: str) -> ConversationSessionRecord: ...
    def close(self, session_id: str, reason: str) -> ConversationSessionRecord: ...
    def load(self, session_id: str, workspace: Path) -> LoadedConversationSession: ...
    def list_for_workspace(self, workspace: Path) -> tuple[ConversationSessionSummary, ...]: ...
    def latest_for_workspace(self, workspace: Path) -> LoadedConversationSession | None: ...
    def inspect_repair(self, session_id: str, workspace: Path) -> SessionRepairPlan: ...
    def create_repaired_copy(self, plan: SessionRepairPlan, workspace: Path) -> LoadedConversationSession: ...
```

Store 构造函数接收 `state_dir`、`installation_id`、`Redactor` 和可注入的 ID/时钟工厂。`RuntimeDependencies` 在 `src/vera/bootstrap.py` 增加已创建的 `installation_id` 字段，Store 使用既有 `workspace_identity(workspace, installation_id)`，不得生成第二个 installation id。

## 实施步骤

### 1. 安全追加原语

- [ ] 扩展 `tests/persistence/test_private_writer.py`，先覆盖 append 新建/已有文件、`0700/0600`、文件和父目录符号链接、短写、flush/fsync 失败、写入中断后原前缀保持可读。
- [ ] 在 `src/vera/persistence/private_writer.py` 新增专用 `PrivateAppendWriter.append_line(path, data)`；使用无跟随符号链接的打开方式、单次完整行追加、`flush`/`fsync` 后才返回。
- [ ] 不改变 `PrivateAtomicWriter.write_bytes` 的“不得覆盖已有文件”语义。

### 2. Session Journal 严格读取与追加

- [ ] 新增 `tests/persistence/test_session_journal.py`，覆盖空文件、连续记录、尾部不完整 JSON、尾部完整但非法 JSON、中间损坏、空洞 sequence、错误 session id 和未来版本。
- [ ] 新增 `src/vera/persistence/session_journal.py`；读取不得沿用 Run Journal 对末尾残片的静默忽略行为。
- [ ] 尾部不完整且此前连续时返回可修复分类；中间损坏、矛盾记录和编码错误返回 `manual_required`，且不跳过坏行继续投影。
- [ ] 每次追加先经 Redactor、Codec 和期望 sequence 验证，再写入一条完整 JSONL；成功后才更新内存记录缓存。

### 3. Store 创建、加载、发现与投影

- [ ] 新增 `tests/persistence/test_session_store.py`，先覆盖创建、确定性标题、追加 turn/compaction/rename/close、按更新时间排序、当前 workspace 过滤、最近会话和缺失 run 证据标记。
- [ ] 新增 `src/vera/persistence/session_store.py`，以合法 `sessions/` 子目录与 Journal 为权威发现来源；第一版不引入必须存在的索引。
- [ ] 恢复投影从最后一个有效 `context.compacted` 开始构造 `model_messages`，同时从完整记录构造有界 `history_messages`。
- [ ] 标题由第一条有效用户输入的首个非空行确定性裁剪生成，不调用模型。
- [ ] workspace identity 不匹配时在投影消息前失败；不得用路径字符串近似匹配。

### 4. 非破坏修复副本

- [ ] 新增 `tests/persistence/test_session_repair.py`，覆盖仅尾部截断可计划、中间损坏不可计划、计划被源文件变化作废、新副本有新 session id、原文件字节完全不变。
- [ ] `inspect_repair` 只读返回有效前缀边界和源文件摘要；`create_repaired_copy` 再次校验摘要后创建新 Journal，并记录修复来源元数据。
- [ ] 禁止原地 truncate、覆盖、rename 原 Journal 或自动执行修复。

### 5. Runtime 依赖传递

- [ ] 新增 `tests/test_bootstrap.py`，断言同一 `installation_id` 同时供 Runtime 与 Session Store 使用。
- [ ] 修改 `src/vera/bootstrap.py` 的 `RuntimeDependencies`，显式携带 `installation_id`；更新现有 Fake 构造器而不读取真实用户状态。

## 局部验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/persistence/test_private_writer.py tests/persistence/test_session_journal.py tests/persistence/test_session_store.py tests/persistence/test_session_repair.py tests/test_bootstrap.py -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src/vera/persistence/private_writer.py src/vera/persistence/session_journal.py src/vera/persistence/session_store.py src/vera/bootstrap.py
git diff --check
```

再运行共同门禁，更新证据后提交：

```bash
git commit -m "feat: add secure conversation session storage"
```

## 验收标准

- 创建、追加、加载、列表和最近会话只通过 Store 完成。
- 成功返回前完成脱敏、严格校验、私有权限和 `fsync`。
- workspace 不匹配、未来版本和中间损坏都不向模型返回消息。
- 只有明确尾部截断可创建新修复副本，原 Journal 永不改变。
