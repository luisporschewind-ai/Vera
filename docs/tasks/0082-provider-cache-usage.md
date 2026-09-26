# Provider 上下文缓存用量 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** In progress（离线自动门禁通过；原生终端手工验收待执行）
**Goal:** 在多厂商 BYOK 主路径中如实记录 Provider 返回的缓存命中/未命中输入 token，并在单个 Run 的 `/usage` 中安全汇总。
**Architecture:** 适配器将厂商用量字段归一化为可选 `ModelUsage` 字段，Runtime 现有 `model.completed` 传播结构化事实，Session 聚合已完成调用，CLI 呈现同一结构；稳定前缀用回归测试约束，不改变消息顺序。
**Tech Stack:** Python 3.13、Pydantic、OpenAI Python Client、pytest、Ruff、Mypy。
**Spec:** [Provider 上下文缓存用量](../specs/2026-09-25-provider-context-cache-usage.md)；前置 [0081](0081-byok-model-configuration.md)。

## Global Constraints

- 仅在 0081 的 BYOK 主路径验证通过后实施；Core 不推算价格、节省金额或本地缓存键。
- 未识别/缺失/无效的明细保持未知，不解释为零；现有 `input_tokens`、`output_tokens`、`total_tokens` 原义不变。
- `provider_default` 不发 `stream_options`；`include_usage` 仅影响明确选择它的流式 Profile。
- 保持 Runtime 的 system → 项目说明 → Skill → 会话 → 当前目标顺序与现有安全/审批/恢复契约。
- 不使用真实 Key 或真实 Provider；无提交、合并、推送授权。

## Review Focus

1. OpenAI SDK 把额外字段放在 `model_extra` 时仍可解析，但对象的非数值字段不可当作 token；任务 1 测试。
2. 流式最后一个只有 `usage`、无 `choices` 的块仍被捕获；任务 1 测试。
3. 旧 Journal 混入新调用时缓存汇总全部 unavailable，但旧总量仍可计算；任务 2 测试。
4. 明细合计超出输入或布尔值充当整数时不能污染总量；任务 1/2 测试。
5. 零输入与中断流不能产生看似真实的命中率；任务 2/3 测试。

## 文件与接口图

| 单元 | 职责 |
| --- | --- |
| `src/vera/models/base.py` | `ModelUsage` 的两个可选缓存字段 |
| `src/vera/models/provider_usage.py` | `parse_provider_usage(value: object) -> ModelUsage`，只解析响应事实 |
| `src/vera/models/openai_compatible.py` | 流式与非流式调用统一用量解析 |
| `src/vera/session/queries.py` | `usage_snapshot` 对单 Run 的严格聚合 |
| `src/vera/session/controller.py`, `src/vera/cli_session.py`, `src/vera/cli_plain_session.py`, `src/vera/cli_json_session.py` | `/usage` Event 与 Plain/JSON 显示结构化用量 |
| `src/vera/runtime/engine.py` | 仅核对现有 `model.completed` 序列化是否保留可选字段，必要时最小修改 |

### Task 1：Provider 用量归一化

**Files:** Modify `src/vera/models/base.py`, `src/vera/models/openai_compatible.py`; Create `src/vera/models/provider_usage.py`; Test `tests/models/test_openai_compatible.py`, `tests/models/test_openai_stream.py`, `tests/models/test_provider_usage.py`。

**Interfaces:** `ModelUsage.cache_hit_input_tokens: int | None = None`、`cache_miss_input_tokens: int | None = None`；`parse_provider_usage(value: object) -> ModelUsage`。解析模块内部定义 `read_field(value: object, name: str) -> object`（兼容 dict、属性与 `model_extra`）和 `nonnegative_int(value: object) -> int | None`（只接收 `type(value) is int`）。

- [ ] **Step 1: 写失败测试。** 构造 dict、属性对象及 SDK `model_extra`：DeepSeek 顶层 hit/miss；OpenAI 嵌套 `prompt_tokens_details.cached_tokens`；仅 hit + 有效总输入时推导 miss；GLM 只有总量时两个字段皆 `None`；bool、负数、超总量、合计不等于总量时两个字段皆 `None`。流末纯 usage 块仍记录，非流式同规则。
  ```python
  usage = parse_provider_usage({"prompt_tokens": 100, "completion_tokens": 5,
      "total_tokens": 105, "prompt_tokens_details": {"cached_tokens": 60}})
  assert (usage.cache_hit_input_tokens, usage.cache_miss_input_tokens) == (60, 40)
  assert parse_provider_usage({"prompt_tokens": 100,
      "prompt_cache_hit_tokens": True}).cache_hit_input_tokens is None
  ```
- [ ] **Step 2: 运行红灯。** `/Users/admin/Vera/.venv/bin/python -m pytest tests/models/test_provider_usage.py tests/models/test_openai_compatible.py tests/models/test_openai_stream.py -q`；新增字段与解析接口应失败。
- [ ] **Step 3: 最小实现。** 对支持 dict/属性/`model_extra` 的读取函数仅接收 `type(value) is int` 的非负数；校验缓存明细与总输入一致后构造 `ModelUsage`；在 `_turn_from_response` 与 `stream` 的每个 usage 块调用同一解析函数，流结束而无 usage 时仍保留 `None`。
  ```python
  hit = nonnegative_int(read_field(value, "prompt_cache_hit_tokens"))
  if hit is None:
      hit = nonnegative_int(read_field(read_field(value, "prompt_tokens_details"), "cached_tokens"))
  miss = nonnegative_int(read_field(value, "prompt_cache_miss_tokens"))
  if hit is not None and miss is None and total_input is not None and hit <= total_input:
      miss = total_input - hit
  ```
- [ ] **Step 4: 运行绿灯。** 重跑 Step 2；验证请求参数仍遵循 Profile 的 `stream_usage_mode`。

### Task 2：Journal 兼容与单 Run 聚合

**Files:** Modify `src/vera/session/queries.py`; Test `tests/session/test_queries.py`, `tests/runtime/test_streaming_output.py`。

**Interfaces:** `usage_snapshot(events: tuple[EventEnvelope, ...]) -> dict[str, object]` 在原四项后增加 `cache_hit_input_tokens`、`cache_miss_input_tokens`、`cache_hit_percent`。

- [ ] **Step 1: 写失败测试。** 新旧 `model.completed` 混合、全新有效明细、零输入、缺失/无效/布尔字段、部分 `usage` 缺失，验证原四项保持独立计算；新字段仅在每次调用全部有效且输入合计大于零时显示一位小数百分比。Runtime/Journal round trip 保留可选字段；旧事件无需迁移。
  ```python
  snapshot = usage_snapshot((old_completed_event, new_completed_event))
  assert snapshot["input_tokens"] == 200
  assert snapshot["cache_hit_input_tokens"] == "unavailable"
  assert snapshot["cache_hit_percent"] == "unavailable"
  ```
- [ ] **Step 2: 运行红灯。** `/Users/admin/Vera/.venv/bin/python -m pytest tests/session/test_queries.py tests/runtime/test_streaming_output.py -q`，新增断言应失败。
- [ ] **Step 3: 最小实现。** 聚合缓存字段前逐调用验证两个缓存计数与该调用输入总量一致；任何一次缺失只使三个缓存输出 `"unavailable"`，不篡改总量；百分比 `round(100 * hits / inputs, 1)`。`model.completed.usage` 继续由 `turn.usage.model_dump()` 产生，必要时只调整排除 `None` 的策略以保持旧 Journal 可读。
  ```python
  valid = all(type(hit) is int and type(miss) is int and hit >= 0 and miss >= 0
              and hit + miss == input_count for hit, miss, input_count in per_call_cache)
  percent = round(100 * total_hits / total_inputs, 1) if valid and total_inputs else "unavailable"
  ```
- [ ] **Step 4: 运行绿灯。** 重跑 Step 2；检查序列化结果无原始 Provider 对象或 Key。

### Task 3：CLI 契约与稳定前缀

**Files:** Modify `src/vera/session/controller.py`, `src/vera/cli_session.py`, `src/vera/cli_plain_session.py`, `src/vera/cli_json_session.py`（仅实际显示 `/usage` 的路径）； Test `tests/cli/test_plain_session.py`, `tests/cli/test_json_session.py`, `tests/runtime/test_project_instructions.py`, `tests/runtime/test_skills.py`。

- [ ] **Step 1: 写失败测试。** Plain `/usage` 继续展示原四项并追加缓存明细/命中率或 `unavailable`，JSON 保留相同字段；连续 ModelRequest 在相同 system、项目说明、Skill Snapshot、会话历史下前缀相同，当前目标与工具结果只追加；变化的 Skill/摘要可改变前缀。中断流无完成用量时显示 unavailable。
  ```python
  assert second_request.messages[:len(first_request.messages)] == first_request.messages
  assert plain_usage.count("cache_hit_input_tokens") == 1
  assert json_usage["cache_hit_input_tokens"] == cache_snapshot["cache_hit_input_tokens"]
  ```
- [ ] **Step 2: 运行红灯。** 运行实际 CLI 与 Runtime 前缀测试文件；新增断言应失败于未呈现缓存字段或缺少前缀约束。
- [ ] **Step 3: 最小实现。** 仅在 `/usage` Plain 渲染路径增加三个字段；JSON 直接传递 `usage_snapshot`；Runtime 消息顺序若已满足测试则不改产品代码；不引入缓存名称、重新排序或 Prompt 本地缓存。
  ```python
  for field in ("cache_hit_input_tokens", "cache_miss_input_tokens", "cache_hit_percent"):
      lines.append(f"{field}: {snapshot[field]}")
  ```
- [ ] **Step 4: 运行绿灯。** 运行相同聚焦测试；检查 `model.completed` 和 Plain/JSON 输出均无 Key/原始响应。

### Task 4：整体验收与记录

**Files:** Modify `docs/tasks/0082-provider-cache-usage.md`, `docs/STATUS.md`; Test affected model/runtime/session/CLI suites。

- [ ] **Step 1: 运行受影响 suite。** `/Users/admin/Vera/.venv/bin/python -m pytest tests/models tests/runtime tests/session tests/cli -q`；记录真实结果与仅因环境造成的阻断。
- [ ] **Step 2: 静态与差异检查。** `/Users/admin/Vera/.venv/bin/python -m ruff check src/vera tests`、`/Users/admin/Vera/.venv/bin/python -m ruff format --check src/vera tests`、`/Users/admin/Vera/.venv/bin/python -m mypy src`、`git diff --check`、`git status --short --branch`、`git diff`。
- [ ] **Step 3: 记录结论。** 在任务及 `docs/STATUS.md` 写明已验证的离线行为、未进行的真实 Provider 命中/计费测试、用户手工 CLI 验收状态；不把缓存命中推断为发送 token 下降或上下文窗口增加。

## 自查

- 覆盖：两种 Provider 缓存字段、缺失/无效、流式/非流式、旧 Journal、Run 汇总、Plain/JSON、稳定前缀和完整离线门禁分别在任务 1-4 中验证。
- 执行方式：在用户审阅本计划及 0081 后，单主 Agent 使用 `superpowers:executing-plans` 串行实施；不创建本地提交。

## 实施记录（2026-09-26）

- Provider 用量解析已支持 DeepSeek 的命中/未命中字段及 OpenAI 的 `cached_tokens`；不完整、无效或不一致数据保留为 unavailable。流式末尾只有 usage 的块会进入统计。
- `usage_snapshot` 按单个 Run 汇总，保留旧输入/输出/总量字段；Plain `/usage` 与结构化事件显示缓存命中、未命中与命中比例。Runtime 稳定前缀回归测试通过。
- 评测 canonical JSON 省略未知缓存字段 `null`，同时保留已报告的缓存事实，维持旧快照兼容。
- 受影响离线测试曾有 `432 passed`；修复评测 canonical JSON 兼容后，全量可运行非 live 套件为 `1297 passed, 2 deselected`。4 个打包/安装 smoke 用例因隔离网络无法解析 PyPI 的 `hatchling` 未能启动。
- Ruff check、Ruff format check、Mypy `src/vera` 与 `git diff --check` 通过。只读子代理复核受当前额度限制未能启动；主 Agent 完成了代码路径与最终差异自查。用户已完成真实 Provider 请求并确认手工测试步骤均通过；未验证供应商计费明细，命中统计也不代表传输 Token 减少或上下文窗口增加。
- 2026-09-26 用户手工真实调用结果：GLM Run 显示 `calls=1, input=1182, output=29`，缓存命中 `0`、未命中 `1182`、命中率 `0.0%`；DeepSeek Run 显示 `calls=1, input=1376, output=455`，命中 `1024`、未命中 `352`、命中率 `74.4%`。这验证了两种 Provider 的当前 usage 输出可进入 CLI 汇总；这些结果是单次观察，不承诺未来命中比例。
- 用户确认这轮手工测试步骤均通过。
