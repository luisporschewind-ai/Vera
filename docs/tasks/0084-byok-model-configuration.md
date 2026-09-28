# BYOK 多厂商模型配置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**状态：** In progress（实现及用户手工验收已完成并合入 `main`；打包/安装 smoke 环境阻断待复核）
**Goal:** 用户在 CLI 中查看、启用、排序和选择 DeepSeek、GLM、OpenAI 及自定义模型，并通过隐藏输入把自己的 Key 安全写入私有文件，Core 为未来 GUI 提供相同配置动作。
**Architecture:** `ProviderConfigurationService` 管理用户拥有的模型目录状态和 Key 引用；`load_config` 只从可信用户配置装配 Provider，`build_runtime` 按显式默认或选择建模。CLI 只调用服务，不直接解析或编辑配置文件。缓存用量在 [0085](0085-provider-cache-usage.md) 接续实施。
**Tech Stack:** Python 3.12（以 `pyproject.toml` 声明为准）、Pydantic、Typer、OpenAI Python Client、platformdirs、pytest、Ruff、Mypy。
**Spec:** [BYOK 多厂商模型配置](../specs/2026-09-25-byok-model-configuration.md)、[ADR-0022](../decisions/ADR-0022-user-owned-byok-provider-configuration.md)。

## 2026-09-28 集成校准

阶段八拆分合入后，Bootstrap 曾回退到旧的 Provider 装配路径，使默认 Profile、私有 Key 文件和 `/model` 列表入口与本规格不一致。本次隔离分支恢复已验收的 Core 配置服务接线，并保留阶段八新增工具注册。原用户手工验收属于 2026-09-26 基线；集成版由用户在 `main` 复验，本轮不运行回归。

## 当前交付与证据口径（2026-09-26）

实现提交 `d616283` 已通过 `9354bb3` 合入 `main`，原隔离 worktree 已不在当前注册列表。用户 GLM/DeepSeek 请求与手工验收已通过。可运行非 live 套件记录为 `1297 passed, 2 deselected`；4 个打包/安装 smoke 用例因无法获取 `hatchling` 未启动，因此不写成全量门禁全部通过。

下列分步清单保留原实施计划；未勾选项不等于代码未实现，也不证明每个 Red 步骤已执行。完成事实以文末实施记录为准。原 worktree、离线测试和 Git 授权约束描述的是实施时边界；后续用户亲自真实调用及已授权合并的事实见本节，不构成本轮提交或推送授权。

## Global Constraints

- 只在当前 `codex/provider-cache-usage` worktree 实施；不修改 `/Users/admin/Vera` 的脏工作区，不创建 GUI/阶段十代码。
- 用户明确选择本地私有环境文件与 `api_key_env` 引用；Key 不进命令参数、非秘密 JSON/TOML、Event、Journal、Snapshot、日志或错误。
- 工程 `.vera/config.toml` 不得定义或覆盖 Provider、模型选择、endpoint、Key 引用、启用顺序和默认项。
- 本次只用假 Key 和离线 Provider fixture；不得调用真实 Provider。未获本次提交、合并或推送授权，不执行这些 Git 操作。
- 任务须更新文档和验收记录；每个任务通过聚焦测试后再进入下一个任务。

## Review Focus

1. 同名旧用户 Profile 与托管目录同时存在：托管选择优先，旧文件仍可读且不被改写；由任务 2 测试。
2. 私有 Key 文件是符号链接、非当前用户拥有或权限放宽：读写都拒绝且不泄漏路径/值；由任务 3 测试。
3. 工作区经符号链接包含实际 Key 文件：启动失败，且失败发生在构造模型客户端之前；由任务 4 测试。
4. 禁用默认模型、损坏托管 JSON 或无可用 Key：明确失败，不静默回退或发请求；由任务 2/4/5 测试。
5. 非 TTY 输入 Key 或 CLI 输出/异常含 Key：拒绝或脱敏；由任务 5 测试。

## 文件与接口图

| 单元 | 职责 |
| --- | --- |
| `src/vera/provider_catalog.py` | 内置只读候选、目录版本和官方 endpoint 选择；GLM 区域需用户显式指定 |
| `src/vera/provider_configuration.py` | `ProviderConfigurationService`、托管 JSON 版本模型、结构化摘要、原子写入和目录动作 |
| `src/vera/provider_credentials.py` | 环境名校验、私有文件解析/原子 Key 写入、Key 状态与路径隔离 |
| `src/vera/config.py` | `ProviderConfig` 请求能力字段、用户级兼容合并和工程配置拒绝 |
| `src/vera/bootstrap.py` | 用户选择解析、Key 文件加载、工作区隔离、缺 Key 拒绝 |
| `src/vera/models/openai_compatible.py` | Profile 指定的 token 上限参数及流式用量参数 |
| `src/vera/cli_models.py`, `src/vera/cli.py` | Typer `models` 命令；未来 GUI 只复用 Core 服务 |
| `src/vera/session/controller.py` | `/model` 仅列出/切换已启用有效 Profile |

### Task 1：可信来源与请求能力契约

**Files:** Modify `src/vera/config.py`; Test `tests/test_config.py`, `tests/models/test_openai_compatible.py`, `tests/models/test_openai_stream.py`。

**Interfaces:** `ProviderConfig.output_token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"`；`ProviderConfig.stream_usage_mode: Literal["provider_default", "include_usage"] = "provider_default"`。

- [ ] **Step 1: 写失败测试。** 在 `tests/test_config.py` 增加工程 `[providers.evil]`、`model` 和 `api_key_env` 被 `UnsafeProjectConfig` 拒绝，用户级旧 Profile 保持可读；在模型测试中以 fake client 断言 OpenAI Profile 发送 `max_completion_tokens`，且仅 `include_usage` 流请求发送 `stream_options={"include_usage": True}`。
  ```python
  with pytest.raises(UnsafeProjectConfig):
      load_config(workspace_with_project_provider, {})
  assert fake_client.calls[0]["max_completion_tokens"] == 256
  assert fake_client.calls[0]["stream_options"] == {"include_usage": True}
  ```
- [ ] **Step 2: 运行红灯。** `/Users/admin/Vera/.venv/bin/python -m pytest tests/test_config.py tests/models/test_openai_compatible.py tests/models/test_openai_stream.py -q`；新增断言应失败于工程配置仍可覆盖或请求仍发 `max_tokens`。
- [ ] **Step 3: 最小实现。** 将 `providers`、`model`、`model_profile` 和目录/Key 选择字段放入工程配置禁用集；在 `ProviderConfig` 定义两个 `Literal` 字段，适配器请求构造统一使用 `kwargs[self.provider.output_token_parameter] = request.max_output_tokens`，仅流式且 `include_usage` 时附加 `stream_options`。确保旧 Profile 缺省行为不变。
  ```python
  output_token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
  stream_usage_mode: Literal["provider_default", "include_usage"] = "provider_default"
  kwargs[self.provider.output_token_parameter] = request.max_output_tokens
  if self.provider.stream_usage_mode == "include_usage":
      kwargs["stream_options"] = {"include_usage": True}  # only in stream()
  ```
- [ ] **Step 4: 运行绿灯。** 重跑 Step 2 命令；再运行 `/Users/admin/Vera/.venv/bin/python -m mypy src/vera/config.py src/vera/models/openai_compatible.py`。

### Task 2：目录、托管配置和 Core 配置动作

**Files:** Create `src/vera/provider_catalog.py`, `src/vera/provider_configuration.py`; Modify `src/vera/config.py`; Test `tests/test_provider_configuration.py`, `tests/test_config.py`。

**Interfaces:** `ProviderConfigurationService(path: Path | None = None)` 暴露 `path: Path`，提供 `list_profiles() -> tuple[ProfileSummary, ...]`、`enable(profile_id: str)`、`disable(profile_id: str)`、`move_before(profile_id: str, other_id: str)`、`set_default(profile_id: str)`、`add_custom(profile: ProviderConfig, profile_id: str)`；`effective_providers(legacy: Mapping[str, ProviderConfig]) -> dict[str, ProviderConfig]` 与 `default_profile() -> str | None` 供 `load_config`/bootstrap 使用。`ProfileSummary` 在本任务包含 ID、厂商、模型、endpoint、启用、顺序、默认和配置有效性；任务 3 从可信凭据接口补充 Key 状态，未来 GUI 只消费最终结构化摘要。

- [ ] **Step 1: 写失败测试。** 用临时 `path` 写版本 1 JSON；断言目录初始候选为 DeepSeek、GLM、两个 OpenAI 模型，初始无静默可运行默认；启用、移动、设置默认后重建服务可保留顺序；同名旧 Profile 被托管覆盖；新增自定义 Profile 经保存/重载有效；未知版本或损坏 JSON 明确报 `ConfigurationError` 且原文件不变；禁用当前默认失败。
  ```python
  service = ProviderConfigurationService(path=tmp_path / "model_profiles.json")
  service.enable("openai-gpt-4.1-mini")
  service.set_default("openai-gpt-4.1-mini")
  assert ProviderConfigurationService(path=service.path).default_profile() == "openai-gpt-4.1-mini"
  ```
- [ ] **Step 2: 运行红灯。** `/Users/admin/Vera/.venv/bin/python -m pytest tests/test_provider_configuration.py tests/test_config.py -q`；新增模块/接口缺失应失败。
- [ ] **Step 3: 最小实现。** 目录条目使用稳定 `profile_id`；GLM 条目在选择区域 endpoint 前标记不可运行；托管 JSON 仅存非秘密选择，`version=1`。读取时验证 schema、重复 ID、顺序引用、默认存在/已启用；写入用同目录 `0600` 临时文件、flush/fsync、`os.replace`，不覆写旧用户 TOML；`load_config` 合并可信用户 Profile 与托管设置，工程字段先验证再合并。
  ```python
  payload = {"version": 1, "enabled": enabled_ids, "order": ordered_ids,
             "default": default_id, "custom_profiles": custom_profiles}
  with os.fdopen(fd, "w", encoding="utf-8") as handle:
      json.dump(payload, handle, ensure_ascii=False)
      handle.flush()
      os.fsync(handle.fileno())
  os.replace(temporary_path, self.path)
  ```
- [ ] **Step 4: 运行绿灯。** 重跑 Step 2；用测试检查文件内不含 Key 值，`git diff --check`。

### Task 3：私有 Key 文件与状态

**Files:** Create `src/vera/provider_credentials.py`; Modify `src/vera/config.py`, `src/vera/provider_configuration.py`; Test `tests/test_provider_credentials.py`, `tests/test_provider_configuration.py`, `tests/test_config.py`。

**Interfaces:** `provider_env_path() -> Path`；`read_provider_environment(allowed_names: frozenset[str], path: Path | None = None) -> dict[str, str]`；`set_provider_key(name: str, value: str, path: Path | None = None) -> None`；`key_status(name: str, file_values: Mapping[str, str]) -> Literal["configured", "missing", "overridden_by_environment"]`。旧 `load_provider_environment` 包装读入并 `os.environ.setdefault`，调用时传入可信 Profile 派生的名称。

- [ ] **Step 1: 写失败测试。** 临时文件覆盖旧 DeepSeek/GLM 名称、OpenAI 和自定义合法 `_API_KEY`/`_TOKEN`/`_SECRET`；断言不在可信配置的名称被拒绝；`$(...)`、重复字段、换行 Key、符号链接、owner 错误、非 `0600`、目录路径均拒绝；更新一个 Key 后其他允许字段不丢失，显式进程环境优先；错误消息和状态均不含 Key。
  ```python
  set_provider_key("OPENAI_API_KEY", "fake-new-key", path=private_file)
  values = read_provider_environment(frozenset({"OPENAI_API_KEY", "GLM_API_KEY"}), private_file)
  assert values["OPENAI_API_KEY"] == "fake-new-key"
  assert "fake-new-key" not in str(key_status("OPENAI_API_KEY", values))
  ```
- [ ] **Step 2: 运行红灯。** `/Users/admin/Vera/.venv/bin/python -m pytest tests/test_provider_credentials.py tests/test_config.py -q`。
- [ ] **Step 3: 最小实现。** 用严格大写环境名正则与后缀校验；`lstat` + 不跟随链接的文件打开验证常规文件、owner 和 `0600`；沿用无 Shell 解析；目录 `0700`、临时文件 `0600`、flush/fsync/replace；禁止重复键和多行值；只在可信配置读完后确定允许名。服务摘要通过 `key_status` 补上 Key 状态与可用性原因码。保留旧 DeepSeek/GLM 变量入口与非 Key 兼容字段。错误仅给稳定原因码/行号。
  ```python
  if not re.fullmatch(r"[A-Z][A-Z0-9_]*(?:_API_KEY|_TOKEN|_SECRET)", name):
      raise ConfigurationError("invalid_key_reference", "invalid key reference")
  if stat.S_ISLNK(path.lstat().st_mode):
      raise UnsafeProviderEnvironment("provider environment file must be regular")
  ```
- [ ] **Step 4: 运行绿灯。** 重跑 Step 2；验证 `tests/test_config.py` 原有私有文件测试仍通过。

### Task 4：Runtime 选择和工作区隔离

**Files:** Modify `src/vera/bootstrap.py`, `src/vera/session/controller.py`; Test `tests/test_bootstrap.py`, `tests/session/test_controller.py`。

**Interfaces:** `build_runtime(workspace: Path, model_profile: str | None = None)` 保持签名；内部只从服务获取已启用、有效、Key 已配置的 Profile；显式选择优先于用户默认，均不存在时抛 `ConfigurationError("missing_provider_config", ...)`。

- [ ] **Step 1: 写失败测试。** 假 Key + 临时配置目录验证显式 Profile、用户默认、禁用/缺 Key/无默认均不构造 client；Key 文件处于工作区内或工作区经符号链接指向其父目录时失败；工作区外正常。旧用户配置在无托管设置时有明确兼容选择路径，不静默选字典首项以外的厂商。
  ```python
  with pytest.raises(ConfigurationError, match="provider_key_in_workspace"):
      build_runtime(workspace_containing_private_file, "openai-gpt-4.1-mini")
  assert fake_client_factory.call_count == 0
  ```
- [ ] **Step 2: 运行红灯。** `/Users/admin/Vera/.venv/bin/python -m pytest tests/test_bootstrap.py tests/session -q`，仅新增断言预期失败。
- [ ] **Step 3: 最小实现。** 先加载可信用户配置/托管 Profile，确定允许 Key 名，读私有文件，再校验选择与 Key；解析实际文件和工作区真实路径，包含或相同则拒绝。通过验证后才创建 `OpenAICompatibleAdapter`。`/model` 使用 Core 摘要显示有效候选并通过既有 RuntimeBuilder 切换，不把 Key 状态之外的秘密写入 session Event。
  ```python
  workspace_root = workspace.resolve(strict=True)
  private_file = provider_env_path().resolve(strict=True)
  if private_file == workspace_root or workspace_root in private_file.parents:
      raise ConfigurationError("provider_key_in_workspace", "provider key file is inside workspace")
  ```
- [ ] **Step 4: 运行绿灯。** 重跑 Step 2；验证无自动跨厂商回退的 fake client 调用计数。

### Task 5：CLI 配置流程与安全输出

**Files:** Create `src/vera/cli_models.py`; Modify `src/vera/cli.py`, `src/vera/cli_session.py`（若 Plain `/model` 需要摘要）； Test `tests/cli/test_models.py`, `tests/cli/test_config.py`。

**Interfaces:** `models_app: typer.Typer` 包含 `list`、`setup`、`enable`、`disable`、`move --before`、`default`、`key set`；所有修改调用 `ProviderConfigurationService`，Key 修改调用 Core 凭据接口。

- [ ] **Step 1: 写失败测试。** Typer `CliRunner` 以临时目录和假 Key 测目录、启用/移动/默认、自定义 Profile 创建入口、`setup` 内置模型与 GLM 区域、隐藏 Key 输入、非 TTY 拒绝 Key 步骤；断言 stdout/stderr、`config show`、JSON/Plain 事件及异常文本无 Key 和私有文件绝对路径。
  ```python
  result = runner.invoke(app, ["models", "list"])
  assert result.exit_code == 0
  assert "fake-private-key" not in result.output
  assert str(private_file) not in result.output
  ```
- [ ] **Step 2: 运行红灯。** `/Users/admin/Vera/.venv/bin/python -m pytest tests/cli/test_models.py tests/cli/test_config.py -q`。
- [ ] **Step 3: 最小实现。** 命令参数不接受 Key；`typer.prompt(..., hide_input=True)` 前验证 stdin TTY；展示可审阅 endpoint、model、Key 引用后执行服务动作；`models list` 只输出结构化摘要，异常映射稳定错误码；`config show` 仅输出非秘密字段。`setup` 允许内置选择及自定义端点（远端 HTTPS、无 userinfo/query/fragment；用户级旧本地 HTTP 兼容）。
  ```python
  if not sys.stdin.isatty():
      raise ConfigurationError("key_input_requires_tty", "key input requires a terminal")
  value = typer.prompt("API Key", hide_input=True, confirmation_prompt=True)
  set_provider_key(profile.api_key_env, value)
  typer.echo("Key: configured")
  ```
- [ ] **Step 4: 运行绿灯。** 重跑 Step 2；运行 `/Users/admin/Vera/.venv/bin/python -m ruff check src/vera tests`、`/Users/admin/Vera/.venv/bin/python -m ruff format --check src/vera tests`、`/Users/admin/Vera/.venv/bin/python -m mypy src`。

### Task 6：离线主路径与任务记录

**Files:** Modify `docs/tasks/0084-byok-model-configuration.md`, `docs/STATUS.md`; Test `tests/models/test_openai_compatible.py`, `tests/models/test_openai_stream.py`, `tests/cli/test_models.py`, `tests/test_bootstrap.py`。

- [ ] **Step 1: 增加离线契约测试。** 假客户端对 DeepSeek、GLM、OpenAI Profile 各覆盖文本、Tool Call 和流式请求能力；断言 OpenAI 使用 `max_completion_tokens` 与 `include_usage`，DeepSeek/GLM 不串用参数；测试不访问真实网络。
- [ ] **Step 2: 运行红灯并修正实际缺口。** 运行四组聚焦测试；若新增断言失败，定位具体 Provider 映射，按 Task 1-5 的接口修正。
- [ ] **Step 3: 验证并记录。** 运行受影响的 config/bootstrap/model/session/CLI suite、Ruff、Mypy、`git diff --check`；检查 `git status --short --branch` 与 `git diff`，在本任务和 `docs/STATUS.md` 只记录真实结果、阻断项及手工验收缺口，不宣称真实账号连通或 GUI 已实现。

## 自查

- 覆盖：目录/排序/默认/兼容来源、Key 安全、工程信任边界、运行选择、请求能力、CLI 与离线多厂商主路径分别由任务 1-6 验证。
- 执行方式：用户先审阅计划后确认实施；在隔离 worktree 由单主 Agent 串行实施。无提交授权，验证不包含 commit。

## 实施记录（2026-09-25）

- 已在 `codex/provider-cache-usage` 中实现目录、用户托管 Profile、CLI 配置、私有 Key 文件与 Runtime 选择；未加入 GUI 代码。
- 离线受影响测试：设置 `PATH=/Users/admin/Vera/.venv/bin:$PATH` 后 `299 passed`。第一次未补齐 PATH 时两项验证工具相关测试失败；相同两项在补齐 PATH 后通过。
- Ruff check、Ruff format check、Mypy `src/vera` 与 `git diff --check` 通过。CLI 隐藏输入由 CliRunner 验证；用户随后在原生终端完成模型配置与真实 Provider 请求，并确认本轮手工测试步骤均通过。
- 后续缓存用量集成后，BYOK/缓存受影响集合曾有 `432 passed`；修复评测 canonical JSON 向后兼容后，全量可运行非 live 套件为 `1297 passed, 2 deselected`。4 个打包/安装 smoke 用例因隔离网络无法解析 PyPI 的 `hatchling` 未能启动。
- 最终 Ruff check、Ruff format check、Mypy `src/vera` 与 `git diff --check` 通过。只读子代理复核受当前额度限制未能启动；主 Agent 完成了代码路径与最终差异自查。用户确认本轮手工测试步骤通过，包含 GLM/DeepSeek 真实请求 smoke。
- 2026-09-26 用户在 Terminal 中完成真实 Provider smoke：`glm-4.6` 与 `deepseek-flash` 均完成一次 Run，分别返回输出 Token 29 与 455。DeepSeek 对“只回答连通测试成功”的请求选择解释而未照抄；这是回答内容，不是 Provider 请求失败。用户随后确认本轮手工测试步骤均通过。
