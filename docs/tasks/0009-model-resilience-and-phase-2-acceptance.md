# Vera ModelAdapter 韧性与阶段二验收实施计划

> **供 Cursor Agent 执行：** 使用单一主实现 Agent，严格按 TDD 顺序执行。每个生产增量独立提交；最后完成阶段二全链路验收和本地合并。

**状态：** Done

**目标分支：** `feature/model-resilience-phase2`

**目标：** 为 ModelAdapter 增加能力声明、稳定错误分类、最多两次的有限重试和用量证据，并用恢复、兼容、策略及供应商故障矩阵完成阶段二验收。

**架构：** Adapter 负责把供应商对象映射为 `ModelTurn` 或 `ModelProviderError`；Runtime 根据 `RetryPolicy` 决定是否再次调用并发出结构化 Event。重试只包围模型请求，不包含工具、审批、写入或验证；能力不足在请求前失败。

**技术栈：** Python 3.12、OpenAI Python Client 2.x、Pydantic 2、Typer、pytest、Ruff、Mypy、uv；不新增依赖。

**规格：** [阶段二总规格](../specs/2026-09-11-phase-2-recovery-compatibility-policy.md)

**架构决策：** [ADR-0008](../decisions/ADR-0008-model-capabilities-and-errors.md)

**依赖：** 任务 0005–0008 已合并到 `main`。

## 全局约束

- 编码 Agent 请求必须声明支持 Tool Calling；compact 请求不要求。
- 标准错误码固定为 configuration、authentication、network、timeout、rate_limited、service、invalid_response、capability_mismatch。
- 默认 `max_attempts=2`，表示首次请求加最多一次重试。
- 只有 network、timeout、rate_limited 和明确 5xx service 错误可重试。
- 认证、配置、无效响应和能力不匹配不重试。
- Retry-After 只有成功解析且不超过 `max_delay_seconds=2.0` 时使用；否则使用有上限退避。
- 每个新 attempt 产生独立 Event；usage 缺失用 null，不填零。
- 不自动切换 Profile 或供应商。
- 不重复本地工具、审批、Change Set、恢复或验证。
- 默认与验收均不运行 `tests/live`，不读取真实 Key。

## 文件结构

```text
src/vera/models/
├── capabilities.py
├── errors.py
├── retry.py
├── base.py
└── openai_compatible.py
src/vera/runtime/engine.py
src/vera/config.py
src/vera/bootstrap.py
src/vera/cli_presenter.py

tests/
├── models/
│   ├── test_capabilities.py
│   ├── test_errors.py
│   ├── test_retry.py
│   ├── test_adapter_conformance.py
│   └── test_openai_compatible.py
├── fixtures/providers/{deepseek,glm}/
├── runtime/test_model_resilience.py
└── e2e/test_phase_2_reliability.py
```

---

### Task 1：固定模型能力与错误契约

**文件：**

- Create: `src/vera/models/capabilities.py`
- Create: `src/vera/models/errors.py`
- Modify: `src/vera/models/base.py`
- Modify: `src/vera/config.py`
- Create: `tests/models/test_capabilities.py`
- Create: `tests/models/test_errors.py`
- Modify: `tests/test_config.py`

**接口：**

- Produces: `ModelCapabilities(tool_calling, parallel_tool_calls, context_tokens, usage, request_id)`
- Produces: `ModelErrorCode`
- Produces: `ModelProviderError(code, message, retry_after_seconds=None, status_code=None, request_id=None)`
- Produces: `safe_error_payload(error: ModelProviderError, attempt: int) -> dict[str, JsonValue]`
- Produces: `ProviderConfig.capabilities`
- Extends: `ModelAdapter.capabilities: ModelCapabilities`

- [x] **Step 1：编写能力和错误序列化测试**

```python
def test_coding_capability_requires_tool_calling() -> None:
    capabilities = ModelCapabilities(tool_calling=False)
    assert capabilities.supports_request(has_tools=True) is False
    assert capabilities.supports_request(has_tools=False) is True


def test_provider_error_never_exposes_cause_text() -> None:
    error = ModelProviderError(
        code=ModelErrorCode.AUTHENTICATION,
        message="provider authentication failed",
        status_code=401,
    )
    assert error.retryable is False
    assert "secret" not in str(error).lower()
```

配置测试覆盖默认 OpenAI-compatible profile `tool_calling=True`、用户显式关闭、非法负 token 上限、项目配置不能声明 Provider capability。

- [x] **Step 2：运行测试并确认类型不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/models/test_capabilities.py tests/models/test_errors.py tests/test_config.py -v
```

- [x] **Step 3：实现冻结能力和稳定错误码**

```python
class ModelErrorCode(StrEnum):
    CONFIGURATION = "provider_configuration_error"
    AUTHENTICATION = "provider_authentication_error"
    NETWORK = "provider_network_error"
    TIMEOUT = "provider_timeout"
    RATE_LIMITED = "provider_rate_limited"
    SERVICE = "provider_service_error"
    INVALID_RESPONSE = "provider_invalid_response"
    CAPABILITY_MISMATCH = "capability_mismatch"
```

ModelProviderError 只接收已脱敏 message；映射时使用 `raise mapped_error from provider_exception` 保留本进程异常链，但异常链不进入 Event。`retryable` 仅对 NETWORK/TIMEOUT/RATE_LIMITED 及 status>=500 的 SERVICE 为 True。`safe_error_payload()` 只返回 code、message、attempt、status_code、request_id 和 retry_after_seconds。

- [x] **Step 4：运行模型、配置与静态检查**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/models tests/test_config.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/models src/vera/config.py tests/models
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交能力契约**

```bash
git add src/vera/models src/vera/config.py tests/models tests/test_config.py \
  docs/tasks/0009-model-resilience-and-phase-2-acceptance.md
git commit -m "feat: define model capabilities and errors"
```

---

### Task 2：标准化 OpenAI-compatible 错误和响应证据

**文件：**

- Modify: `src/vera/models/openai_compatible.py`
- Modify: `src/vera/models/base.py`
- Modify: `tests/models/test_openai_compatible.py`
- Create: `tests/fixtures/providers/deepseek/text.json`
- Create: `tests/fixtures/providers/deepseek/tool_call.json`
- Create: `tests/fixtures/providers/glm/text.json`
- Create: `tests/fixtures/providers/glm/tool_call.json`
- Create: `tests/models/test_adapter_conformance.py`

**接口：**

- Produces: `ModelTurn.provider_request_id: str | None = None`
- Guarantee: Adapter 只抛 `ModelProviderError`

- [x] **Step 1：编写供应商 Fixture conformance 测试**

```python
@pytest.mark.parametrize("provider", ["deepseek", "glm"])
def test_fixture_tool_call_conforms(provider: str, fixture_client) -> None:
    adapter = OpenAICompatibleAdapter(
        provider_config(provider), client=fixture_client(provider, "tool_call.json")
    )
    turn = adapter.complete(model_request_with_tools())
    assert turn.tool_calls[0].name == "read_file"
    assert turn.usage is not None
```

错误映射参数化覆盖 OpenAI Client 的 AuthenticationError、APITimeoutError、APIConnectionError、RateLimitError、APIStatusError(500)，以及空 choices、未知 finish_reason、非法 tool arguments。断言错误码、retryable、status/request ID 和消息脱敏。

- [x] **Step 2：运行测试并确认当前只返回 ModelAdapterError**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/models/test_openai_compatible.py tests/models/test_adapter_conformance.py -v
```

- [x] **Step 3：实现异常映射**

按最具体异常到一般异常排序捕获 OpenAI SDK 类型；从 SDK 对象只提取 status code、合法 Retry-After 和 request ID。未知异常映射 NETWORK 仅限连接类；其他未知异常映射 SERVICE 且默认不重试。解析错误统一 INVALID_RESPONSE。

`ModelTurn.provider_request_id` 从响应 `_request_id` 或 headers 安全提取；不存在为 None。Fixture 必须完全脱敏，不复制真实响应正文。

- [x] **Step 4：运行模型全回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/models -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/models tests/models
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交适配器标准化**

```bash
git add src/vera/models tests/models tests/fixtures/providers \
  docs/tasks/0009-model-resilience-and-phase-2-acceptance.md
git commit -m "feat: normalize compatible model providers"
```

---

### Task 3：实现有限 RetryPolicy

**文件：**

- Create: `src/vera/models/retry.py`
- Create: `tests/models/test_retry.py`
- Modify: `src/vera/config.py`
- Modify: `tests/test_config.py`

**接口：**

- Produces: `RetryPolicy(max_attempts=2, base_delay_seconds=0.25, max_delay_seconds=2.0)`
- Produces: `should_retry(error, attempt) -> bool`
- Produces: `delay_seconds(error, attempt) -> float`
- Produces: `Limits.max_model_attempts: int = 2`

- [x] **Step 1：编写重试表和退避上限测试**

```python
@pytest.mark.parametrize(
    ("code", "status", "expected"),
    [
        (ModelErrorCode.NETWORK, None, True),
        (ModelErrorCode.TIMEOUT, None, True),
        (ModelErrorCode.RATE_LIMITED, 429, True),
        (ModelErrorCode.SERVICE, 503, True),
        (ModelErrorCode.SERVICE, 400, False),
        (ModelErrorCode.AUTHENTICATION, 401, False),
        (ModelErrorCode.INVALID_RESPONSE, None, False),
    ],
)
def test_retry_matrix(code, status, expected) -> None:
    error = ModelProviderError(code=code, message="safe", status_code=status)
    assert RetryPolicy(max_attempts=2).should_retry(error, attempt=1) is expected
    assert RetryPolicy(max_attempts=2).should_retry(error, attempt=2) is False
```

测试 Retry-After 0.5 使用 0.5，Retry-After 60 截到 2.0，指数退避不超过 2.0，max_attempts 小于 1 配置失败，项目配置只能降低。

- [x] **Step 2：运行测试并确认 RetryPolicy 不存在**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/models/test_retry.py tests/test_config.py -v
```

- [x] **Step 3：实现纯重试计算**

Policy 不调用 sleep，只返回决定和延迟。Runtime 注入 `sleep: Callable[[float], None]` 后执行等待，测试使用记录器。随机 jitter 本阶段不加入，保证确定性。

- [x] **Step 4：运行配置与模型回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/models tests/test_config.py -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src/vera/models src/vera/config.py tests/models
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 RetryPolicy**

```bash
git add src/vera/models/retry.py src/vera/config.py \
  tests/models/test_retry.py tests/test_config.py \
  docs/tasks/0009-model-resilience-and-phase-2-acceptance.md
git commit -m "feat: bound model request retries"
```

---

### Task 4：把能力、重试和 usage Event 接入 Runtime

**文件：**

- Modify: `src/vera/runtime/engine.py`
- Modify: `src/vera/bootstrap.py`
- Modify: `src/vera/cli_presenter.py`
- Create: `tests/runtime/test_model_resilience.py`
- Modify: `tests/runtime/test_discovery_loop.py`

**接口：**

- Produces: `model.retrying`、`model.failed`
- Extends: `model.requested.payload.attempt`
- Extends: `model.completed.payload` usage/request_id/duration_ms

- [x] **Step 1：编写能力失败与有限重试测试**

```python
def test_transient_failure_retries_once_without_repeating_tools(runtime_factory) -> None:
    adapter = ScriptedErrorAdapter(
        [
            provider_error(ModelErrorCode.TIMEOUT),
            ModelTurn(assistant_text="ok", finish_reason="stop"),
        ]
    )
    runtime, clock = runtime_factory(adapter, max_attempts=2)
    events = tuple(runtime.handle(start_run()))

    assert [event.type for event in events].count("model.retrying") == 1
    assert len(adapter.requests) == 2
    assert not any(event.type == "tool.started" for event in events)
    assert clock.sleeps == [0.25]
```

再测试认证不重试、两次 timeout 后 model.failed、Tool Calling capability mismatch 在 adapter 调用前失败、compact 可使用无 tool 能力、成功 Event 的 null usage、request ID 和 duration。

- [x] **Step 2：运行测试并确认 Runtime 折叠为 model_error**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  tests/runtime/test_model_resilience.py tests/runtime/test_discovery_loop.py -v
```

- [x] **Step 3：实现单模型调用边界**

提取：

```python
def _complete_with_retry(
    self, context: RunContext, request: ModelRequest
) -> Generator[EventEnvelope, None, ModelTurn | None]:
    for attempt in range(1, self.retry_policy.max_attempts + 1):
        yield self._event(context, "model.requested", {"attempt": attempt})
        try:
            turn = self.adapter.complete(request)
        except ModelProviderError as error:
            if not self.retry_policy.should_retry(error, attempt):
                yield self._event(context, "model.failed", safe_error_payload(error, attempt))
                return
            delay = self.retry_policy.delay_seconds(error, attempt)
            yield self._event(context, "model.retrying", {"attempt": attempt, "delay": delay})
            self.sleep(delay)
            continue
        return turn
    return None
```

调用方使用 `turn = yield from self._complete_with_retry(context, request)`，返回 None 时结束当前 run。能力检查发生在首次 model.requested 前。成功 model.completed 记录 finish_reason、tool count、usage 可空字段、request ID、attempt 和 duration_ms。任何原异常字符串不得进入 Payload。

- [x] **Step 4：运行 Runtime、恢复与模型回归**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest tests/runtime tests/recovery tests/models -v
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests/runtime tests/models
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
```

- [x] **Step 5：提交 Runtime 韧性**

```bash
git add src/vera/runtime/engine.py src/vera/bootstrap.py src/vera/cli_presenter.py \
  tests/runtime/test_model_resilience.py tests/runtime/test_discovery_loop.py \
  docs/tasks/0009-model-resilience-and-phase-2-acceptance.md
git commit -m "feat: retry transient model failures safely"
```

---

### Task 5：阶段二全链路验收与收口

**文件：**

- Create: `tests/e2e/test_phase_2_reliability.py`
- Create: `docs/evals/phase-2-reliability-core.md`
- Modify: `README.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/STATUS.md`
- Modify: `docs/tasks/phase-2-execution-order.md`
- Modify: `docs/tasks/0009-model-resilience-and-phase-2-acceptance.md`

- [x] **Step 1：编写阶段二 12 条退出条件 E2E 对照**

`tests/e2e/test_phase_2_reliability.py` 使用临时工作区、临时状态目录、Fake Model、Fake Clock 和 failpoint。至少包含：审批恢复、验证恢复、partial apply 批准恢复、UNKNOWN 停止、重复 resume 幂等、legacy 查看、future reject、策略变化审批失效、DeepSeek/GLM Fixture、瞬时重试不重复工具、JSON recovery、普通对话/安全编辑回归。

```python
def test_retry_then_resume_never_duplicates_local_side_effects(phase2_fixture) -> None:
    phase2_fixture.model.timeout_once_then_propose()
    run_id = phase2_fixture.start_and_crash_after_apply()
    result = phase2_fixture.new_process().resume(run_id)

    assert result.terminal_state == "completed"
    assert phase2_fixture.writer.count("app.py") == 1
    assert phase2_fixture.verifier.count == 1
```

- [x] **Step 2：运行完整质量门禁**

```bash
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest \
  -m "not live" --cov=vera --cov-report=term-missing
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv build
git diff --check
```

全部退出码为 0，覆盖率至少 90%，live 测试明确排除。

- [x] **Step 3：执行仓库外离线 CLI 验收**

使用 editable 安装、假的完整 Provider 环境和临时 `VERA_STATE_DIR`。只执行本地 `/status`、`/recover`、`vera recover list --json`、legacy 查看、迁移 dry-run 和 `/permissions`；不输入自然语言，不发网络请求。输出不得出现测试 Key、Base URL、Snapshot 正文或绝对私有状态文件内容。

- [x] **Step 4：更新阶段文档**

验收记录逐条对应总规格 12 条退出条件，记录每份任务提交、测试数、覆盖率、静态检查、构建、仓库外验收、未执行 live 和已知限制。将任务 0009、阶段二执行索引标记 Complete；ROADMAP 阶段一和阶段二标记 Complete，阶段三为下一阶段；STATUS 记录真实分支和无 remote 状态。

- [x] **Step 5：提交阶段二验收**

```bash
git add tests/e2e/test_phase_2_reliability.py README.md docs/ROADMAP.md \
  docs/STATUS.md docs/evals/phase-2-reliability-core.md \
  docs/tasks/phase-2-execution-order.md \
  docs/tasks/0009-model-resilience-and-phase-2-acceptance.md
git commit -m "test: verify phase two reliability core"
```

- [x] **Step 6：合并回 main 并最终复核**

```bash
git switch main
git merge --no-ff feature/model-resilience-phase2 \
  -m "merge: complete Vera phase two"
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run pytest -m "not live" -q
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run ruff format --check src tests
UV_CACHE_DIR=/private/tmp/vera-uv-cache uv run mypy src
git branch -d feature/model-resilience-phase2
```

无 remote 时只记录本地合并，不宣称 push。真实供应商回归由用户后续明确执行。
