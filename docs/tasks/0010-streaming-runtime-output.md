# Vera 流式 RuntimeOutput 实施计划

> **供 Agent 执行（For agentic workers）：** REQUIRED SUB-SKILL: 使用 `superpowers:executing-plans` 按 Task 顺序实施；只使用一个主实现 Agent，每个生产增量独立提交。

**状态：** Done

**目标分支：** `feature/streaming-runtime-output`

**目标：** 在不改变持久 Event、恢复 Journal 和旧 `handle()` 消费者语义的前提下，为 Vera Core 增加模型文本流式输出。

**架构：** `VeraRuntime.stream()` 输出 `EventEnvelope | StreamFrame`；`StreamFrame` 只承载瞬时 `assistant.delta`，最终完整文本仍由持久 `assistant.message` 表达。ModelAdapter 提供向后兼容的流式接口，OpenAI-compatible Adapter 聚合文本和 Tool Call chunk 后再交给 Runtime。

**技术栈：** Python 3.12、Pydantic 2、OpenAI Python Client 2.x、pytest、Ruff、Mypy、uv。

**规格：** [阶段三富交互 Terminal UI](../specs/2026-09-11-rich-terminal-ui.md)

## 全局约束

- 开始前确认阶段二任务 0005–0009 已合并，并从最新干净 `main` 创建目标分支。
- `EventEnvelope` 继续是唯一持久事实；Stream Frame 不写 Journal、Snapshot 或 ConversationContext。
- `VeraRuntime.handle()` 继续只返回持久 Event，既有测试和 `vera run ... --json` 输出不得改变。
- Tool Call chunk 完整聚合和参数校验前不能执行工具。
- `ModelAdapter` 在阶段二是 `Protocol`（非 ABC）；默认 `stream()` 用函数/混入或文档约定的协议扩展实现，`FakeModelAdapter` 位于 `src/vera/models/base.py`（无 `tests/fakes.py`）。
- 在 `ModelCapabilities` 增加 `streaming: bool = False`；`streaming=False` 时 Runtime/Adapter 走 `complete()` 包装路径。
- 流式完成路径必须复用阶段二 `RetryPolicy` / `_complete_with_retry` 语义：瞬时错误有限重试，且不重复工具、审批、写入或验证副作用；抛出 `ModelProviderError`。
- `ContractCodec` 不编码 StreamFrame。
- 不运行 `tests/live`，不读取真实 Key，不修改 `VeraTestDemo`。

---

### Task 1：固定 StreamFrame 和 RuntimeOutput 契约

**文件：**

- Create: `src/vera/contracts/streaming.py`
- Modify: `src/vera/contracts/__init__.py`
- Modify: `tests/contracts/test_models.py`
- Create: `tests/contracts/test_streaming.py`

**接口：**

- Produces: `StreamFrameType.ASSISTANT_DELTA`
- Produces: `StreamFrame(schema_version, run_id, stream_id, index, type, payload)`
- Produces: `RuntimeOutput = EventEnvelope | StreamFrame`
- Produces: `is_transient(output: RuntimeOutput) -> TypeGuard[StreamFrame]`

- [x] **Step 1：编写 round-trip、非法索引和 payload 测试**

```python
def test_stream_frame_round_trips() -> None:
    frame = StreamFrame(
        run_id="run_1",
        stream_id="stream_1",
        index=0,
        type=StreamFrameType.ASSISTANT_DELTA,
        payload={"text": "你"},
    )

    assert StreamFrame.model_validate_json(frame.model_dump_json()) == frame
    assert is_transient(frame) is True


def test_assistant_delta_requires_non_empty_text() -> None:
    with pytest.raises(ValidationError):
        StreamFrame(
            run_id="run_1",
            stream_id="stream_1",
            index=0,
            type=StreamFrameType.ASSISTANT_DELTA,
            payload={"text": ""},
        )
```

再覆盖负 index、空 run/stream ID、未知 type、非字符串 text 和额外字段拒绝。

- [x] **Step 2：运行测试并确认类型不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/contracts/test_streaming.py tests/contracts/test_models.py -v
```

- [x] **Step 3：实现冻结契约**

```python
class StreamFrameType(StrEnum):
    ASSISTANT_DELTA = "assistant.delta"


class StreamFrame(ContractModel):
    schema_version: Literal[1] = 1
    run_id: str = Field(min_length=1)
    stream_id: str = Field(min_length=1)
    index: int = Field(ge=0)
    type: StreamFrameType
    payload: dict[str, JsonValue]

    @model_validator(mode="after")
    def validate_delta(self) -> Self:
        text = self.payload.get("text")
        if self.type is StreamFrameType.ASSISTANT_DELTA and (
            not isinstance(text, str) or not text
        ):
            raise ValueError("assistant.delta requires non-empty text")
        return self
```

`RuntimeOutput` 只定义联合类型，不给 Stream Frame 增加 Event sequence、timestamp 或持久标志。

- [x] **Step 4：运行契约与静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/contracts -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/contracts tests/contracts
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交契约**

```bash
git add src/vera/contracts tests/contracts docs/tasks/0010-streaming-runtime-output.md
git commit -m "feat: define transient stream frames"
```

---

### Task 2：增加 ModelAdapter 流式兼容接口和聚合器

**文件：**

- Modify: `src/vera/models/base.py`
- Modify: `src/vera/models/capabilities.py`
- Create: `src/vera/models/streaming.py`
- Create: `tests/models/test_streaming.py`

**接口：**

- Produces: `ModelCapabilities.streaming: bool = False`
- Produces: `ModelTextDelta(text: str)`
- Produces: `ModelStreamCompleted(turn: ModelTurn)`
- Produces: `ModelStreamItem = ModelTextDelta | ModelStreamCompleted`
- Extends: `ModelAdapter` Protocol with optional `stream(request) -> Iterator[ModelStreamItem]`
- Produces: `ModelStreamAccumulator.push(chunk) / finish() -> ModelTurn`

- [x] **Step 1：编写默认 Adapter 与聚合器测试**

```python
def test_default_stream_wraps_complete(fake_adapter, request) -> None:
    fake_adapter.queue_turn(ModelTurn(text="完成"))

    items = tuple(fake_adapter.stream(request))

    assert items == (ModelStreamCompleted(turn=ModelTurn(text="完成")),)


def test_accumulator_never_exposes_partial_tool_call() -> None:
    accumulator = ModelStreamAccumulator()
    accumulator.push(tool_chunk(index=0, name="read_", arguments='{"pa'))
    accumulator.push(tool_chunk(index=0, name="file", arguments='th":"a.py"}'))

    turn = accumulator.finish(finish_reason="tool_calls")

    assert turn.tool_calls[0].name == "read_file"
    assert turn.tool_calls[0].arguments == {"path": "a.py"}
```

再测试中文 delta 顺序、多个 Tool Call index、重复 finish、缺失 finish、非法 JSON 参数和 usage/request ID 只在完成时出现。

- [x] **Step 2：运行测试并观察接口缺失**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/models/test_streaming.py -v
```

- [x] **Step 3：实现默认兼容流和纯聚合器**

```python
class ModelAdapter(Protocol):
    @property
    def capabilities(self) -> ModelCapabilities: ...

    def complete(self, request: ModelRequest) -> ModelTurn: ...

    def stream(self, request: ModelRequest) -> Iterator[ModelStreamItem]:
        yield ModelStreamCompleted(turn=self.complete(request))
```

`FakeModelAdapter.stream()` 同样默认包装 `complete()`。聚合器只接收已规范化 chunk，不依赖 OpenAI SDK 类型；`finish()` 对不完整 Tool Call 抛脱敏 `ModelProviderError(code=INVALID_RESPONSE)`。

- [x] **Step 4：运行模型回归与静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/models tests/runtime -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/models tests/models
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Adapter 接口**

```bash
git add src/vera/models tests/models \
  docs/tasks/0010-streaming-runtime-output.md
git commit -m "feat: add model streaming interface"
```

---

### Task 3：实现 OpenAI-compatible streaming 映射

**文件：**

- Modify: `src/vera/models/openai_compatible.py`
- Modify: `tests/models/test_openai_compatible.py`
- Create: `tests/fixtures/providers/deepseek/stream_text.jsonl`
- Create: `tests/fixtures/providers/deepseek/stream_tool_call.jsonl`
- Create: `tests/fixtures/providers/glm/stream_text.jsonl`
- Create: `tests/fixtures/providers/glm/stream_tool_call.jsonl`

**接口：**

- Consumes: `ModelStreamAccumulator`
- Produces: `OpenAICompatibleAdapter.stream(request)`
- Guarantee: Provider 对象和原始异常文本不离开 Adapter

- [x] **Step 1：编写离线 Fixture conformance 测试**

```python
@pytest.mark.parametrize("provider", ["deepseek", "glm"])
def test_provider_stream_reconstructs_final_text(provider, stream_client) -> None:
    adapter = OpenAICompatibleAdapter(
        provider_config(provider), client=stream_client(provider, "stream_text.jsonl")
    )

    items = tuple(adapter.stream(model_request()))

    assert "".join(item.text for item in items if isinstance(item, ModelTextDelta)) == "完成"
    assert isinstance(items[-1], ModelStreamCompleted)
    assert items[-1].turn.text == "完成"
```

Tool Call Fixture 断言 name/arguments 可跨 chunk 聚合，且 Adapter 不产生可执行的中间 Tool Call。再覆盖 timeout、rate limit、空 choices 和连接中断后的标准错误码。

- [x] **Step 2：运行测试并确认仍走 complete**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/models/test_openai_compatible.py -k stream -v
```

- [x] **Step 3：实现 SDK chunk 到规范化 item 的单向转换**

使用 `client.chat.completions.create(..., stream=True)`。每个非空文本 chunk 产生 `ModelTextDelta` 并进入聚合器；Tool Call delta 只进入聚合器。收到 finish reason 后产生唯一 `ModelStreamCompleted`。异常继续复用阶段二标准化错误映射和 RetryPolicy，不把原异常字符串放入 item。

- [x] **Step 4：运行供应商离线回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/models -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/models tests/models
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交兼容实现**

```bash
git add src/vera/models/openai_compatible.py tests/models tests/fixtures/providers \
  docs/tasks/0010-streaming-runtime-output.md
git commit -m "feat: stream OpenAI-compatible turns"
```

---

### Task 4：让 Runtime 在保持旧接口时输出瞬时帧

**文件：**

- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/runtime/context.py`
- Modify: `src/vera/cli_driver.py`
- Create: `tests/runtime/test_streaming_output.py`
- Modify: `tests/runtime/test_discovery_loop.py`
- Modify: `tests/runtime/test_safe_editing_flow.py`

**接口：**

- Produces: `VeraRuntime.stream(command: CoreCommand) -> Iterator[RuntimeOutput]`
- Preserves: `VeraRuntime.handle(command: CoreCommand) -> Iterator[EventEnvelope]`
- Produces: `drive_run_stream(runtime, command, decide, emit) -> tuple[EventEnvelope, ...]`

- [x] **Step 1：编写流式、Journal 和兼容测试**

```python
def test_stream_emits_transient_deltas_and_one_durable_message(runtime_fixture) -> None:
    runtime, command, journal = runtime_fixture.text_stream(["你", "好"])

    outputs = tuple(runtime.stream(command))

    frames = [item for item in outputs if isinstance(item, StreamFrame)]
    events = [item for item in outputs if isinstance(item, EventEnvelope)]
    assert [frame.index for frame in frames] == [0, 1]
    assert "".join(frame.payload["text"] for frame in frames) == "你好"
    assert next(event for event in events if event.type == "assistant.message").payload["text"] == "你好"
    assert all(event.type != "assistant.delta" for event in journal.read_all())
```

再断言 `tuple(runtime.handle(command))` 与旧 Fake complete 路径的持久 Event 完全一致；stream 中断产生 run.failed，partial 不进入 ConversationContext；Tool Call 只执行一次；Retry 不重复已经完成的本地副作用。

- [x] **Step 2：运行测试并确认 stream 不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/runtime/test_streaming_output.py tests/runtime/test_discovery_loop.py -v
```

- [x] **Step 3：提取单一执行生成器**

```python
def handle(self, command: CoreCommand) -> Iterator[EventEnvelope]:
    for output in self.stream(command):
        if isinstance(output, EventEnvelope):
            yield output
```

`stream()` 成为唯一 Agent loop 实现。它为每个 assistant turn 生成 `stream_id`，按接收顺序发 Frame，只有 `ModelStreamCompleted` 才创建持久 `assistant.message`。Approval、Checkpoint、Apply、Verification、Recovery 继续只产生持久 Event。

- [x] **Step 4：运行 Runtime、恢复与 CLI 回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/runtime tests/recovery tests/cli -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests/runtime tests/recovery tests/cli
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Runtime 流**

```bash
git add src/vera/runtime src/vera/cli_driver.py tests/runtime tests/recovery tests/cli \
  docs/tasks/0010-streaming-runtime-output.md
git commit -m "feat: stream transient runtime output"
```

---

### Task 5：完成任务 0010 离线验收与合并

**文件：**

- Create: `docs/evals/streaming-runtime-output.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/tasks/0010-streaming-runtime-output.md`

**接口：**

- Evidence: 契约、Adapter、Runtime、恢复隔离和旧接口兼容结果

- [x] **Step 1：运行完整质量门禁**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

- [x] **Step 2：记录真实证据并提交**

记录测试数、覆盖率、Fixture、未运行 live 和已知限制；将本任务标记 Done。

```bash
git add docs/evals/streaming-runtime-output.md docs/STATUS.md \
  docs/tasks/0010-streaming-runtime-output.md
git commit -m "test: verify streaming runtime output"
```

- [x] **Step 3：本地合并并复核**

```bash
git switch main
git merge --no-ff feature/streaming-runtime-output \
  -m "merge: add Vera streaming runtime output"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
git branch -d feature/streaming-runtime-output
```

无 remote 时不执行 push。确认 `main` 干净后才开始任务 0011。
