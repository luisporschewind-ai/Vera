# Core 联网技术资料检索方案

**状态：** Accepted（方案方向）；未授权实施

**日期：** 2026-09-24

**接受：** 2026-09-24 用户确认本方案；服务选型、审批细则和实施顺序仍须在实施前决定

**定位：** 阶段八、九收口后的候选 Core 增量；与阶段十的先后顺序另行决定

## 目的与使用场景

让 Vera 在用户需要当前外部资料时，能够查找、核对并引用公开的官方技术文档、依赖版本说明和报错资料，辅助本地编码任务。优先验证三类问题：

1. 某个框架、SDK 或系统 API 的当前官方用法及适用版本；
2. 依赖的版本、迁移说明、兼容性或已公开的变更记录；
3. 一段非私密报错所对应的官方说明、已知问题或修复线索。

成功不是“模型给出看似新鲜的答案”，而是用户能看见检索何时发生、向谁发送了什么查询、答案依据哪些可访问来源，以及来源不充分时 Vera 明确说不知道。联网能力默认可关闭；离线时原有编码流程继续可用。

本方案只覆盖公开网页资料。登录网站、通用浏览器自动化、搜索个人云盘或企业知识库、任意 URL 抓取、持续爬虫、通用 MCP/插件宿主和网页内容长期索引均不在首版范围。

## 当前基线与阶段边界

- 当前 `main` 的 CLI 注册 `read_file`、`list_directory`、`search_text`；`search_text` 只搜索 Workspace 文件。模型 Provider 的网络请求不等于网页搜索。
- [阶段八工具与 Policy v2 规格](2026-09-17-core-tooling-and-risk-tiered-policy.md)预留 `network_access`、`external_service` effect，规定工具统一经过 Policy/Approval/Receipt/Event/Journal；当前风险表将“联网”列为 `high`、默认审批。本方案不能自行把联网改成自动允许。
- [阶段九 Skills 规格](2026-09-15-core-native-skills-system.md)限定 Skill 为工作方法内容，不允许它注册 Tool、声明网络、读取 Provider Key、修改 Policy/Approval 或执行包内脚本。未来可配套“如何检索和核对官方文档”的 Skill，但搜索能力由 Core 提供。
- 当前阶段八 In progress、阶段九 Ready for manual acceptance。本文件是后续规划，不修改 0059–0066 或 0067–0072 的验收范围，也不解除阶段十入口门禁。

## 方案选择

| 路径 | 优点 | 约束 | 本次结论 |
| --- | --- | --- | --- |
| 模型厂商托管搜索 | 接入和引用链较短 | 依赖特定模型 API；现有 Chat Completions 适配器不能直接提供各家的托管工具；Core 较难统一审计搜索细节 | 保留为将来的 Provider 专用适配能力，不作为首版基础 |
| 独立搜索 API + Core 工具 | 与模型供应商解耦；查询、审批、结果和引用可进入 Vera 的统一契约 | 需要单独配置搜索服务密钥、预算和失败处理 | **首版推荐** |
| 通用 MCP 或可执行插件 | 后续扩展多种服务方便 | 需要服务信任、工具发现、凭据、权限、版本和供应链设计；超出 Skills v1 | 不为单一搜索需求先建立通用宿主 |

首个服务候选为同时提供搜索和内容提取的 Tavily；Brave 和 Exa 作为对照。实施计划形成前，用相同的公开技术问题比较来源覆盖、官方结果排序、片段质量、错误语义、延迟、费用和使用条款，再把选择及替换条件写入实施决策。产品契约不得包含某一家服务的专有字段。这里不承诺搜索结果总是最新、完整或正确。

## Core 能力与数据流

首版提供两个受控模型工具：

```text
web_search(query, preferred_domains?, max_results?)
  -> WebSearchResult{query_id, searched_at, provider_id, results[]}

web_read_result(query_id, result_id)
  -> WebPageExcerpt{source_id, canonical_url, title, excerpt, fetched_at, ...}
```

`web_search` 返回有界的标题、规范 URL、摘要或提取片段、可选的发布日期、检索时间和稳定 `result_id`。`preferred_domains` 是检索提示或服务过滤条件，不等于官方身份认证。`web_read_result` 只能读取当前 Run 中一次搜索得到的 `result_id`，由搜索服务的内容提取能力取得有界正文片段；模型不能传任意 URL。每次工具调用都独立经过 Core Policy 和审计链。页面不存在、被封锁或内容不足时，返回稳定错误，不编造正文。

```text
用户目标 / 模型工具调用
  → 参数与查询内容检查
  → PolicyEngine / 必要时 ApprovalGate
  → Core ToolExecutor
  → WebResearchProvider 适配器
  → 结果规范化、去重、截断、来源标记
  → ToolResult / Event / Journal / Receipt
  → 模型据来源作答
```

`WebResearchProvider` 是 Core 内部接口，负责 `search` 和 `read_result`，不将服务 SDK 对象传入公共契约。首版只接入一家服务并保留 `DisabledWebResearchProvider`；未配置时工具不可用且有明确诊断，不自动切换到模型记忆、`bash curl` 或未知外部服务。CLI、Plain、JSON 与未来桌面端只消费 Core 的结构化结果，不自行联网或解析人类文本。

## 出站数据、权限与密钥

- 搜索是只读远端资料，但查询词会发送给第三方并可能计费；Tool effect 至少为 `network_access`、`external_service`。首版遵守现有联网 `high` 审批规则：审批卡展示服务、目的、实际查询词、结果上限和授权作用域。任何减少重复审批的规则须另行修改并接受 Policy 规格；不得把“可信 Workspace”解释成默认同意外传查询。
- 模型生成的查询先做长度、控制字符、明显凭据和受保护路径检查。不能把完整文件、Diff、环境变量、Provider Key、私有日志或未获授权的工作区内容拼入查询。确需引用项目片段时，必须由用户明确提供可外传内容和范围，另行评估；首版不支持自动上传代码片段。
- 搜索服务凭据与模型 Provider Key 分离，保存在 Vera 私有配置或系统凭据存储中。Core 适配器只通过受限凭据读取接口取得该服务的密钥；模型、Skill、工作区文件、公共 Event/Journal 和 ToolResult 均不能读取密钥。密钥不会由 `bash` 子进程继承。
- 审批绑定规范化查询、服务、Run 和参数摘要；暂停后若查询或服务改变，旧审批失效。搜索请求可能在超时前已发出并计费，不做不受控自动重试；恢复仅报告已知结果或要求重新发起，不能假称请求从未发生。
- 首版不向任意结果 URL 发起本机 HTTP 请求，不跟随模型提供的跳转链接。未来若加入通用 URL 打开，必须独立设计 DNS/重定向后的内网地址拒绝、协议和端口限制、内容类型、大小、时间、Cookie/认证和下载边界。

## 来源、引用与不可信内容

- `source_id` 绑定本次搜索的规范 URL、标题、片段 hash、检索时间、服务和可选发布日期。缺少发布日期时显示“未知”，不把检索时间当作发布时间。
- “官方来源”必须按明确的域名和产品归属规则核对；搜索排名、标题写有“official”或模型判断均不足以证明官方身份。答案应优先引用核对过的官方页面；非官方来源需标明类型。
- 搜索结果和网页正文经 `ContentEnvelope` 标为外部不可信内容。页面中的“忽略前述规则”“执行命令”“上传密钥”等文字只能作为资料，不得改变用户目标、工具权限或审批事实。
- 回答中每个关键的版本、API 或修复结论应指向实际返回的来源 URL；仅有摘要时注明依据摘要，证据不足时继续读取结果或说明未能确认。引用不得指向未进入本次 ToolResult 的页面。
- Event/Journal 默认记录可审计的调用事实、服务、来源 ID、状态、时间、计量和安全摘要；原始查询、正文及可能包含私密内容的片段只放在受限的 Run 私有状态中，并遵守现有 Redactor、保留和恢复规则。不得把完整网页永久纳入项目记忆。

## 预算、错误与用户体验

- Core 对单次 Run 设置搜索次数、每次结果数、读取次数、片段字节数、总输出量、请求超时和可选费用上限；具体默认值在实施计划中通过服务能力和 dogfood 数据确定，并写入可测试配置，不由模型提升。
- 区分 `web_research_disabled`、`search_provider_unconfigured`、`query_blocked`、`approval_required`、`network_unavailable`、`rate_limited`、`quota_exceeded`、`search_timeout`、`no_results`、`source_unavailable` 和 `content_truncated`。离线、空结果与错误不能被转换成成功搜索。
- CLI 展示“搜索中/已搜索”、服务、查询范围、来源数量、引用和错误摘要；Plain/JSON 提供相同事实。用户可关闭能力；关闭后不注册联网工具，也不创建搜索服务私有状态。

## 实施拆分与启动门禁

本方案不指定新的阶段编号，也不改变阶段十已经接受的入口。阶段八、九完成并经用户确认后，比较该能力与桌面工作的优先级；若决定先做，先更新路线图和必要 ADR。实际实施还需单独满足：

1. 本规格的方案方向已 Accepted；实施前确认与 Policy v2 的联网审批规则一致。任何自动放行提案必须在 Policy 规格中单独接受。
2. 用固定公开问题完成搜索服务比较，记录服务选择、费用上限、数据处理条款和密钥存放方案。
3. 编写任务级实施计划，按 Core 契约与假服务 → Policy/Approval/Receipt/恢复 → 单一服务适配器 → CLI/Plain/JSON → 安装态与真实 dogfood 切分可验收交付。
4. 用户独立授权实施。规格接受、服务比较或此规划文档本身都不授权写产品代码、配置真实密钥、调用付费 API 或变更阶段状态。

## 验收标准

离线自动矩阵至少覆盖：关闭能力时零网络与零额外状态；公开查询的审批及参数绑定；查询中含密钥/私有片段时阻断；结果规范化、去重、截断和时间字段；搜索后 `result_id` 绑定读取；外部页面提示词投毒；超时、断网、限额和恢复；TUI、Plain、JSON、Event/Journal 的事实一致；旧 Run 与 NoSkill 路径兼容。

经用户明确授权的真实服务验收，在隔离状态目录和公开样例上完成官方文档、依赖版本、非私密报错三组任务：每组检查来源可访问、结论与页面一致、版本与时间没有混淆、费用和出站查询可见。至少包含一组“找不到可靠官方证据”的负例，Vera 必须明确表达未确认。真实 API、真实 Provider 和最终使用体验不能由假服务绿测替代。

## 后续需确认的选择

- 第一服务及其可接受的费用、地区可用性和数据保留条款；
- 是否允许本 Run 内的受限重复搜索授权，以及相应的 Policy 规格变更；
- 官方域名核对规则如何维护，哪些文档站需要人工认可；
- 本能力与阶段十桌面集成的实施先后。

本次确认接受上述目标、Core 工具边界与安全原则，不预先选定服务、不放宽联网审批，也不确定本能力与阶段十的先后。以上选择未解决前，不进入任务级实施计划或请求实施授权。

## 参考

- [OpenAI Web Search 官方入门](https://platform.openai.com/docs/quickstart/make-your-first-api-request)
- [Anthropic 网页搜索工具](https://docs.anthropic.com/zh-CN/docs/agents-and-tools/tool-use/web-search-tool)
- [Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search) 与 [Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract)
- [Brave Search API](https://api-dashboard.search.brave.com/documentation) 与 [Exa Search](https://exa.ai/docs/reference/search)
- [MCP 工具声明的信任边界](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/)
- [OWASP SSRF 风险说明](https://community.owasp.org/attacks/Server_Side_Request_Forgery)
