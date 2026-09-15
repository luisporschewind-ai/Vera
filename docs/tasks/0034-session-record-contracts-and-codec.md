# 任务 0034：会话记录契约与 Codec

> 供主实现 Agent 执行：按 `superpowers:test-driven-development` 实施；完成前使用 `superpowers:verification-before-completion` 复核。

**状态：** Planned
**执行就绪：** 否；等待阶段六关闭及阶段七实施计划接受
**分支：** `phase-7/0034-session-record-contracts`
**依赖：** 任务 0033、任务 0042 与阶段六关闭
**规格：** [持久化对话会话](../specs/2026-09-13-persistent-conversation-sessions.md)

## 目标与边界

建立独立于 TUI 与现有 JSON Session 协议的磁盘记录契约，冻结 `session_format_version=1`、五类 Record Payload、连续序号和兼容解码行为。本任务不创建目录、不追加文件、不接入 `SessionController`。

## 公开类型

在 `src/vera/contracts/sessions.py` 定义：

```python
SessionRecordType = Literal[
    "session.created",
    "turn.committed",
    "context.compacted",
    "session.renamed",
    "session.closed",
]

class ConversationTurn(BaseModel):
    user_text: str
    assistant_text: str
    run_id: str | None
    terminal_state: str

class ConversationSessionRecord(BaseModel):
    session_format_version: Literal[1]
    record_id: str
    session_id: str
    sequence: int
    timestamp: datetime
    type: SessionRecordType
    payload: SessionCreatedPayload | TurnCommittedPayload | ContextCompactedPayload | SessionRenamedPayload | SessionClosedPayload
```

每种 Payload 使用 `extra="forbid"`、冻结模型和与 `type` 对应的字面量鉴别字段。`session.created` 固定保存 `workspace_identity`、规范化 `workspace_root` 和创建时间，并允许仅在修复副本中出现的 `repaired_from_session_id`、`repaired_through_sequence` 与 `source_digest`；`turn.committed` 只保存 `ConversationTurn`，不得嵌入完整 Event、Diff 或工具输出。

在 `src/vera/persistence/session_codec.py` 定义：

```python
class SessionCodec:
    def encode_record(self, record: ConversationSessionRecord) -> bytes: ...
    def decode_line(self, line: str, *, expected_session_id: str, expected_sequence: int) -> ConversationSessionRecord: ...
```

编码输出为确定性 UTF-8 JSON，不含尾随换行；Journal 层负责添加换行。解码器分类返回既有 `JournalCorrupt` / `StateVersionError`，但使用会话专属错误 code：`unsupported_session_version`、`session_id_mismatch`、`session_sequence_mismatch`、`invalid_session_record`。

## 实施步骤

### 1. 冻结契约模型

- [ ] 新增 `tests/contracts/test_session_records.py`，先覆盖五种有效 Record、空白文本、负 sequence、payload/type 不匹配、extra 字段和模型冻结。
- [ ] 运行 `uv run pytest tests/contracts/test_session_records.py -q`，确认因模块不存在而失败。
- [ ] 新增 `src/vera/contracts/sessions.py`，只实现使测试通过的模型与验证器。
- [ ] 明确 `ConversationTurn.terminal_state` 只允许 `completed|failed|cancelled|recovery|response`，避免任意 UI 文案成为磁盘契约。

### 2. 实现确定性 Codec

- [ ] 新增 `tests/persistence/test_session_codec.py`，覆盖稳定 key 顺序、UTC 时间、Unicode/CJK、Redactor 已处理后的文本、版本、ID、sequence 和错误分类。
- [ ] 运行测试并确认缺少 `SessionCodec` 的预期失败。
- [ ] 新增 `src/vera/persistence/session_codec.py`，复用 `parse_json_object`/Pydantic 验证约定，但不调用文件系统。
- [ ] 解码未知未来版本时只返回 `StateVersionError`，不得尝试按 v1 猜测或写回。

### 3. 冻结兼容夹具

- [ ] 新增 `tests/fixtures/state/sessions/v1-valid/session.jsonl`，包含 created、renamed、turn、compacted、closed 的最小连续序列。
- [ ] 新增 `tests/fixtures/state/sessions/v2-future/session.jsonl`，仅用于证明未来版本失败关闭。
- [ ] 在 `tests/persistence/test_session_codec.py` 从夹具读取每行，验证 v1 可重放、v2 不被误解码。
- [ ] 检查夹具不含真实路径、Key、Token 或用户源码。

## 局部验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/contracts/test_session_records.py tests/persistence/test_session_codec.py -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src/vera/contracts/sessions.py src/vera/persistence/session_codec.py
git diff --check
```

再运行[阶段七共同门禁](phase-7-execution-order.md)，更新本任务验证证据后提交：

```bash
git commit -m "feat: define persistent conversation session records"
```

## 验收标准

- 五类记录具有严格、版本化、确定性的磁盘表示。
- 会话磁盘记录与 `vera.session.protocol.SessionRecord` 名称和职责清楚分离。
- 未知版本、错误 ID、断裂 sequence 和 payload/type 不一致均失败关闭。
- 契约不包含完整工具、Diff、审批、Checkpoint 或 Provider Payload。
