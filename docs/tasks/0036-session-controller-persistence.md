# 任务 0036：Context 与 Controller 事务接入

> 供主实现 Agent 执行：按 `superpowers:test-driven-development` 实施；不得让 TUI、Plain 或 JSON 直接操作 Store。

**状态：** Done
**执行就绪：** 否；本任务已完成
**分支：** `phase-7/0036-session-controller-persistence`
**依赖：** 任务 0035
**规格：** [持久化对话会话](../specs/2026-09-13-persistent-conversation-sessions.md)

## 目标与边界

让 `SessionController` 使用同一个纯 Turn 投影同时提交 Session Journal 与内存 Context，固定“稳定终态 → 落盘并 fsync → 内存提交”的顺序，并完整处理压缩、新建、关闭和写入失败。本任务不增加 `-c/-r` 参数，不改视觉样式。

## 公开接口

新增 `src/vera/session/turns.py`：

```python
class ConversationTurnProjector:
    def from_response(self, user_text: str, assistant_text: str) -> ConversationTurn: ...
    def from_run(self, user_text: str, events: Sequence[EventEnvelope]) -> ConversationTurn: ...
```

扩展 `ConversationContext`：

```python
@classmethod
def restore(
    cls,
    max_bytes: int,
    *,
    session_id: str,
    messages: Sequence[ConversationMessage],
    compaction_count: int,
) -> ConversationContext: ...

def commit_turn(self, turn: ConversationTurn) -> None: ...
```

扩展 `SessionController.__init__`，显式接收 `session_store` 与 `loaded_session`；未传入时创建新持久化会话。新增结构化持久化状态：`saved|unsaved`、`source=new|continued|resumed`、最近错误 code。Store 写入失败不得改变已完成 Run/工作区事实，也不得伪装为成功保存。

## 实施步骤

### 1. 提取唯一 Turn 投影

- [x] 新增 `tests/session/test_turns.py`，覆盖普通回复、已应用变更、失败、取消、恢复、空助手消息、脱敏后事实和只引用 `run_id`。
- [x] 运行测试，确认缺少投影器而失败。
- [x] 新增 `src/vera/session/turns.py`，把现有 `ConversationContext` 中 Event 摘要逻辑迁移为纯投影；保留兼容调用直到 Controller 切换完成。
- [x] 断言 Turn 不包含 Event 列表、Diff、stdout/stderr、审批 Payload 或 Checkpoint。

### 2. Context 恢复与显式提交

- [x] 扩展 `tests/session/test_conversation.py`，覆盖指定 session id 恢复、摘要加后续消息、超限拒绝、compaction count、`commit_turn` 与自动容量折叠。
- [x] 实现 `ConversationContext.restore` 和 `commit_turn`；禁止调用方写私有字段。
- [x] 恢复内容超过当前限制时整体失败，不静默丢消息；引导在兼容版本中先压缩或新建。

### 3. 稳定终态事务顺序

- [x] 在 `tests/session/test_controller.py` 使用记录调用顺序的 Fake Store，先断言 `append_turn` 在 `commit_turn` 前完成。
- [x] 修改 `SessionController._finish_active_run`：只对稳定终态生成一次 Turn，Store 成功后提交内存；不得为审批暂停或未结束模型输出提交半轮。
- [x] 增加崩溃点测试：追加前失败不产生新 turn；追加中失败保留旧完整前缀；追加成功后进程崩溃可在重启时只恢复一次。
- [x] 队列 flush 必须在当前 Turn 的保存结果已明确后再启动下一 Run，不能把两轮合并。

### 4. `unsaved` 与退出警告

- [x] 测试 Session Journal 写入失败时：Run Journal 与工作区结果保留、当前进程可继续使用该轮内存、状态持续为 `unsaved`、关闭前再次发出结构化警告。
- [x] 实现 `session.persistence_changed` / `session.close_warning` Event；Payload 只含状态、错误 code 和可行动建议，不含秘密或原异常路径细节。
- [x] 后续任一成功写入不得自动宣称先前丢失轮次已经补存；必须保持 `unsaved`，直到用户新建或显式恢复到权威前缀。

### 5. 压缩、新建、清屏与关闭

- [x] 测试 `/compact` 先追加 `context.compacted` 再替换 Context；失败时磁盘和内存均保留原上下文。
- [x] 测试 `/new` 创建新持久化会话、旧会话保留；`/clear` 复用同一语义并额外请求清屏。
- [x] 测试正常 `/exit` 追加 `session.closed`；缺少 closed 记录仍可恢复，不把异常退出视为损坏。
- [x] 恢复用户消息写回 `PromptHistory`，但 Composer 自己的临时历史不得成为第二套磁盘权威。

### 6. 状态模型与三客户端契约

- [x] 扩展 `src/vera/session/models.py` 的 `ConversationStats`/`SessionStatus`，加入 source、title、persistent state、last saved sequence；更新 `tests/session/test_status.py`。
- [x] 更新 Plain/JSON/TUI controller Fake，但不在三个客户端内拼接 Session JSONL。
- [x] JSON Event 使用稳定字段；Plain/TUI 人类文案从结构化结果投影。

## 局部验证与提交

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/session/test_turns.py tests/session/test_conversation.py tests/session/test_controller.py tests/session/test_status.py tests/cli/test_plain_session.py tests/cli/test_json_session.py tests/terminal/test_app.py -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src/vera/session/turns.py src/vera/session/conversation.py src/vera/session/controller.py src/vera/session/models.py
git diff --check
```

再运行共同门禁，更新证据后提交：

```bash
git commit -m "feat: persist controller conversation turns"
```

## 验收标准

- 磁盘与内存只消费同一个 Turn 投影，且只在稳定终态提交。
- 正常路径严格先 fsync Session Journal，再更新内存 Context。
- 写入失败不回滚已完成工作，也不会隐藏 `unsaved` 风险。
- `/compact`、`/new`、`/clear`、`/exit` 的磁盘与内存语义一致。

## 验证证据（2026-09-16）

- 分支：`phase-7/0036-session-controller-persistence`
- 局部测试 67 passed：`test_turns`、`test_conversation`、`test_controller`、`test_status`、`test_plain_session`、`test_json_session`、`test_app`
- 完整非 live：`964 passed, 2 deselected`
- `ruff` / `mypy` 针对 session、presentation 与 CLI 相关文件通过
