# BYOK 多厂商模型配置

**状态：** Accepted（用户于 2026-09-25 确认）
**日期：** 2026-09-25
**所属范围：** Core 与 CLI 的独立补充能力；阶段八、阶段九状态不变，阶段十 GUI 入口门禁不变

## 目的与用户体验

用户可以像在模型选择器中一样看到 Vera 提供的模型目录，启用需要的模型、调整显示顺序并设置默认模型。用户也可以输入自己的 Provider API Key，然后在 CLI 中直接选用；未来 GUI 用同一 Core 配置服务完成开关、排序、默认项和隐藏输入 Key 的交互。首版覆盖 DeepSeek、GLM、OpenAI 的 Chat Completions 兼容主路径，并允许用户添加其他 OpenAI-compatible Profile。

用户已选择继续使用本地私有环境文件与 `api_key_env` 引用。CLI 必须提供简单的交互式配置入口，不能要求用户把 Key 放到命令参数、Shell 历史、工程文件或普通 TOML/JSON 配置中。本规格不加入 GUI 框架或页面；未来 GUI 消费 Core 的目录、配置动作和状态，不直接读写 Key 文件。

> 2026-09-26 状态对齐：本规格已在 `d616283` 实施，并通过 `9354bb3` 合入 `main`；用户手工验收已通过，安装态阻断见任务 0084/0085。下节保留规格接受时的基线问题，不代表当前代码仍存在这些缺口。

## 接受时基线与需修正的边界

- `VeraConfig.providers` 已支持多个 Profile，`/model` 可以在 Run 之间切换；现有装配仍按配置字典首项选默认，缺少启用状态、显式排序和受控默认项。
- `load_provider_environment` 只允许固定的 DeepSeek/GLM 环境变量名，启动时先读取私有文件，再加载配置；这不足以让用户配置 OpenAI 或自定义 Provider 的 Key。
- `load_config` 当前会把工程 `.vera/config.toml` 与用户配置中的 `providers` 合并。工程内容不能成为 Provider endpoint 与凭据引用的权威来源；此处需要收紧，并同步澄清既有 Core 首版规格中的配置优先级描述。
- `OpenAICompatibleAdapter` 已复用 OpenAI Python Client，但 OpenAI Chat Completions 的部分模型要求 `max_completion_tokens`；现有请求固定发送 `max_tokens`。不同厂商的流式用量参数也不同。

## Core 数据与配置来源

1. 只读内置 `ModelCatalog` 提供版本化目录条目：`profile_id`、`provider_id`、显示名、`model_id`、官方 endpoint 模板、必要的请求参数能力。初始目录包含 DeepSeek `deepseek-flash`、GLM `glm-4.6`、OpenAI `gpt-4.1-mini` 与 `gpt-4.1`；GLM endpoint 由用户选择其账号所属区域，不能静默猜测。目录是候选项，不保证用户账号有权限；允许添加自定义 OpenAI-compatible Profile。目录不存价格、Key 或自动网络发现结果。
2. 用户本地 `platformdirs.user_config_path("Vera") / "model_profiles.json"` 是版本化托管文件，保存启用状态、顺序、默认 Profile 和自定义 Profile，不保存 Key。CLI/未来 GUI 均通过 `ProviderConfigurationService` 修改，由 Core 做校验、原子写入和重新读取；不要让两个客户端各自解析或改写 JSON。已有用户级 `config.toml` 中的 Provider Profile 保持可读，作为兼容来源；托管设置同名时优先于旧用户配置，不静默覆盖旧文件。
3. 每个 Profile 指向 `api_key_env`，多个同厂商模型可共用同一 Key 引用。实际 Key 只存在于进程环境或用户选择的私有 Provider 环境文件。默认沿用当前文件位置与 `VERA_PROVIDER_ENV_FILE` 覆盖，以保持旧安装兼容；CLI 的 Key 设置动作写入该私有文件，文件必须是当前用户拥有的常规文件、无符号链接且权限为 `0600`，以原子替换保存，不丢失文件中其他已允许的配置。显式进程环境变量仍优先于文件值；配置界面只显示 `configured`、`missing` 或 `overridden_by_environment`，不显示 Key 或其片段。
4. 启动时先从**用户可信配置**确定允许加载的 `api_key_env` 名称，再解析私有文件；保留旧 DeepSeek/GLM 环境变量入口。工程配置、项目指令、Skill、工具输出和模型文本都不能新增允许读取的 Key 名称。`api_key_env` 必须符合大写环境变量名语法，并以 `_API_KEY`、`_TOKEN` 或 `_SECRET` 结尾，使既有子进程环境过滤规则能识别并剔除它；私有文件不执行 Shell 语法。
5. 工程 `.vera/config.toml` 不得定义或覆盖 `providers`、Key 引用、endpoint、模型目录、启用顺序或默认项；遇到这些字段明确拒绝。工程配置既有的限制收紧能力保留。用户通过 CLI 显式 `--model`、会话 `/model` 或用户本地默认项选模型；模型请求只发往该用户 Profile 的 endpoint。此规则修订了既有首版规格中的“项目配置可选择供应商和模型”，原因见 [ADR-0022](../decisions/ADR-0022-user-owned-byok-provider-configuration.md)。
6. 如果运行工作区包含实际使用的私有 Key 文件，BYOK Run 必须拒绝启动；不能仅依赖文件工具的后缀过滤，因为结构化 bash/验证进程也可能读取工作区文件。CLI Key 设置不以当前目录作为密钥文件位置；它可从任意工作目录执行，并在用户随后选择的运行工作区触发上述检查。该边界使用规范化真实路径检查，并覆盖符号链接指向与包含关系。

## 可选模型和请求能力

- `ProviderConfigurationService` 向客户端返回目录与有效 Profile 的结构化摘要：`enabled`、`position`、`default`、Key 状态、配置有效性和可用性原因码。`/model` 只列出和选择已启用且配置有效的 Profile；没有可运行 Profile 时给出设置指引，不静默切换厂商。
- Profile 明确声明 `output_token_parameter`：`max_tokens`（默认）或 `max_completion_tokens`，以及 `stream_usage_mode`：`provider_default`（默认）或 `include_usage`。适配器据此发送参数，不从模型名称猜测。内置目录为 OpenAI 条目选 `max_completion_tokens` 和 `include_usage`；DeepSeek/GLM 条目保留兼容默认值。自定义 Profile 可由用户选择这些受限选项。
- Profile endpoint 对远端必须使用 HTTPS，且不得包含 URL 用户信息、查询参数或片段；已有用户级本地 HTTP 兼容配置可继续使用，但工程配置不能引入或修改它。自定义远端地址、模型名与 Key 引用在保存前明确显示供用户审阅。Provider 返回的能力错误应给出可诊断原因，不把未知模型或账号无权限说成 Key 错误。
- 目录版本升级只添加或更新内置候选，不重置用户启用状态、排序、自定义项或默认项。内置条目撤销时保留用户配置并标记不可用；不自动改用另一家 Provider。

## CLI 配置入口

- `vera models list`：按用户顺序显示目录和自定义 Profile、开关、默认标记、Key 状态；不显示 Key 值或完整私有文件路径。
- `vera models setup`：交互式选择厂商和模型，确认 endpoint，隐藏输入 Key，可选择启用并设为默认；非 TTY 明确拒绝输入 Key 的步骤。Key 不接受命令行参数、标准输出回显或日志记录。
- `vera models enable|disable <profile-id>`、`vera models move <profile-id> --before <other-id>`、`vera models default <profile-id>`：由 Core 服务原子更新非秘密配置。禁用当前默认项时要求先选新默认项；活动 Run 不受配置修改影响，下一个 Run 才生效。
- `vera models key set <profile-id>`：根据该 Profile 的 `api_key_env`，仅在 TTY 隐藏输入并更新私有文件；成功后只报告状态。已有 `vera config show` 与 Session 状态继续脱敏，不输出 Key、Key 片段、原始 Provider 异常或完整请求。

## 验收与边界

- 使用假 Key 和临时 HOME/配置目录覆盖三个内置厂商及自定义 Profile 的启用、排序、默认、切换、缺 Key、Key 更新、权限错误、损坏文件与旧配置兼容；验证 CLI、Plain/JSON 和 Core 返回一致。
- 用离线 Provider fixture 覆盖 DeepSeek、GLM、OpenAI 的文本、Tool Call、流式与请求参数；不以离线 fixture 声称真实账号连通。真实 BYOK smoke 只能由用户显式发起并持有 Key。
- 重点验证恶意工程配置不能改 endpoint 或 `api_key_env`，包含私有文件的工作区被拒绝，Key 不进入 Event、Journal、Snapshot、Diff、日志、报错、子进程环境或测试输出；`config show` 与诊断路径也必须脱敏。
- 本任务不加入账号登录、云端 Key 托管、自动供应商切换、价格表、模型市场、GUI 代码或阶段十依赖。缓存用量的统一契约由同 worktree 的[独立规格](2026-09-25-provider-context-cache-usage.md)定义，并在 BYOK 主路径后实施。

## 参考

- [Vera Core 首版规格](2026-09-10-core-safe-editing-vertical-slice.md)
- [ModelAdapter 能力与错误 ADR](../decisions/ADR-0008-model-capabilities-and-errors.md)
- [OpenAI Chat Completions API](https://platform.openai.com/docs/api-reference/chat)
- [DeepSeek 模型文档](https://api-docs.deepseek.com/quick_start/pricing/)
- [Z.AI GLM API 示例](https://docs.z.ai/guides/capabilities/mcp-call)
