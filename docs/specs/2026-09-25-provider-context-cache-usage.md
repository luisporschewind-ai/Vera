# Provider 上下文缓存用量与稳定前缀

**状态：** Accepted（用户于 2026-09-25 确认）
**日期：** 2026-09-25
**所属范围：** Core 模型用量增强；依赖同 worktree 的 BYOK 多厂商配置规格，不改变阶段八、阶段九或阶段十入口状态

## 目的

让 Vera 在用户自带密钥（BYOK）、多 Provider Profile 的模式下，如实记录各 Provider 返回的输入缓存命中与未命中 token，供 CLI 和未来客户端通过同一 Core 事实查看；保持重复请求的稳定前缀，使支持前缀缓存的 Provider 有机会命中。缓存命中可能降低部分输入的计费和延迟，但不减少请求发送的输入 token，也不增加上下文窗口容量。

本规格的第一版只处理观测与已存在前缀的稳定性。是否进一步重排 Context，必须由实际命中数据和语义回归证明，不能为了命中率改变指令信任级别、审批或恢复语义。

## 当前事实

- `Runtime._seed_context` 依次放入固定 system、项目说明、所选 Skill、会话历史和本轮目标；同一 Run 的后续 ModelRequest 携带先前消息及新增工具回合。
- `VeraConfig.providers` 已支持多个 Profile，每项使用 `base_url`、`model` 和 `api_key_env`；`/model` 可以在 Run 之间切换 Profile。私有环境文件的允许字段目前仅覆盖 DeepSeek/GLM；本次先按[BYOK 多厂商配置](2026-09-25-byok-model-configuration.md)建立用户可配置的 Profile、Key 入口和 OpenAI 主路径，再接入缓存用量。
- `OpenAICompatibleAdapter` 在非流式和带用量的流式块读取 `prompt_tokens`、`completion_tokens`、`total_tokens`，但丢弃缓存明细。
- `ModelUsage`、`model.completed` 和 `/usage` 目前只有总输入、输出、总 token。`/status` 的上下文指标是字节占用，与 Provider token 用量不同。
- DeepSeek Chat Completions 的缓存默认开启，按已持久化的相同输入前缀尽力命中；响应 `usage` 可包含 `prompt_cache_hit_tokens` 与 `prompt_cache_miss_tokens`。当前 DeepSeek 文档说明流式最后一块带完整 `usage`，不要求新增 `stream_options`。
- OpenAI Chat Completions 的用量可包含 `prompt_tokens_details.cached_tokens`；流式完整用量须通过 `stream_options.include_usage` 请求。GLM 的官方公开示例展示总 token 用量；目前没有足够证据把缓存明细视为其通用返回契约。

## BYOK 与多厂商原则

- Profile 是用户明确选择的模型入口。Key 仍由本地受控配置引用，不能写入模型请求事实、Event、用量汇总、缓存标识或日志；Provider 切换不跨 Profile 复用任何 Vera 自建缓存。
- Core 的 `ModelUsage`、`model.completed` 和 `/usage` 只表达统一的 token 事实。Provider 字段名、流式用量请求方式和可用性由适配层处理；不要求所有厂商提供缓存明细，也不把缺失解释为零命中。
- 当前 `/usage` 按单个 Run 汇总，Run 的 `run.started.model_profile` 是归属依据。未来跨 Run 的统计需按 Profile 和模型分组，不混合不同厂商的命中率或价格。
- 不发送通用“缓存名称”。例如 OpenAI 的 `prompt_cache_key` 属于其专用请求能力，DeepSeek 的上下文缓存由服务端自动管理；是否采用某个厂商的显式缓存参数需独立验证和规划。

## 范围与契约

1. `ModelUsage` 增加可选非负整数 `cache_hit_input_tokens`、`cache_miss_input_tokens`。它们来自 Provider 报告的本次请求用量，或在其总输入与命中值一致时由两者相减得到；不得通过本地估算提示词预测。未知保持 `None`。已有三个总量字段含义不变。
2. 适配器按已知响应形状读取缓存明细：DeepSeek 的 `prompt_cache_hit_tokens`、`prompt_cache_miss_tokens`，以及 OpenAI Chat Completions 的 `prompt_tokens_details.cached_tokens`。只有在总输入有效且不小于命中值时，才计算缺失的未命中值。无效、布尔值、负数、超过总输入或两项合计不等于总输入的明细均整体视为不可用，不污染已有总量。未识别的厂商字段保持未知，不做猜测。流式与非流式遵循同一解析规则。
3. 使用 BYOK 规格定义的 `ProviderConfig.stream_usage_mode`：`provider_default` 不发送可选参数，只读取 Provider 自行返回的用量；`include_usage` 仅在流式请求发送 `stream_options={"include_usage": true}`。流被中断或 Provider 未返回终块用量时保持未知，不以已收到文本估算。不得因一个厂商需要该参数就无条件发给其他兼容端点。
4. `model.completed.usage` 以可选字段附加缓存明细；旧 Journal 仍可读取。不得把原始 Provider 响应、完整提示词、Provider Key 或缓存键写入 Event、Session Journal、日志和错误。
5. `/usage` 对单个 Run 的已完成调用汇总缓存明细。仅当每次调用都提供一致有效的总输入、命中与未命中数据时，分别给出 `cache_hit_input_tokens`、`cache_miss_input_tokens` 合计，以及 `cache_hit_percent`（按 `100 × 命中 / 总输入` 保留一位小数）；任一调用缺失时，这三项均为 `unavailable`，原有总量仍独立计算。零输入时命中率为 `unavailable`。Plain 与 JSON 呈现同一结构化事实；旧四项展示保持兼容。
6. 不增加本地模型输出缓存、缓存名称或手工清理控制；不引入统一价格表或“节省金额”推算。价格、缓存条件和保留时间按厂商及模型变化，未来费用展示另立规格。

## 前缀策略

- 保留现有 system → 项目说明 → Skill → 会话 → 当前目标的安全顺序，及既有 ContentEnvelope、Snapshot、压缩与 Context 上限规则。
- 用确定性测试固定：相同的 system、项目说明、Skill Snapshot 与会话历史在连续请求中产生相同前缀；当前目标和新增工具结果只追加在其后。项目说明、Skill 或摘要变化时，允许命中区间缩短，不伪造命中结果。
- 工具定义及其顺序若参与 Provider 缓存匹配，以真实 Provider 用量验证后再决定是否调整；本轮不修改工具注册、Schema、Runtime 消息排列或压缩触发条件。

## 验收

- 离线 fixture 覆盖 DeepSeek 顶层明细、OpenAI 嵌套明细及显式流式用量、GLM/通用兼容端点只有总量、无明细、无效明细、混合旧/新 Journal、零输入、连续请求稳定前缀。验证不同 Profile 的可选流式参数不串用，Key 和原始响应不进入事实输出。
- 受影响的 Model、Runtime、Session、CLI、JSON/Plain 契约测试，以及 Ruff、Mypy、`git diff --check` 通过；测试不读取真实 Key、不调用真实 Provider。
- 可选的真实 Provider 小预算对照测试须由用户另行授权并提供可用的 BYOK 配置；没有真实结果时，只报告离线契约和结构稳定性，不声称实测命中率或节省金额。

## 参考

- [BYOK 多厂商模型配置](2026-09-25-byok-model-configuration.md)
- [DeepSeek Context Caching](https://api-docs.deepseek.com/guides/kv_cache/)
- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
- [OpenAI Chat Completions API](https://platform.openai.com/docs/api-reference/chat)
