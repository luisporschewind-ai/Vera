# Vera 不可信内容、提示词投毒与内容安全

**状态：** Accepted
**日期：** 2026-09-12
**接受：** 2026-09-12 用户确认本规格

> 路线校准：2026-09-17 接受的 [ADR-0020](../decisions/ADR-0020-stage-core-native-skills.md) 与 2026-09-18 接受的 [ADR-0021](../decisions/ADR-0021-core-tools-before-desktop.md) 依次把 Skills 和工具/Policy/Git 放在桌面之前。当前顺序为阶段八工具/Policy/Git、阶段九 Skills、阶段十桌面、阶段十一私有预览。以下分阶段实施已同步，既有信任与安全结论不变。

## 背景

Vera 会读取用户目标、工程文件、项目说明、命令输出和模型输出；未来还可能读取网页、MCP 或其他外部资源。这些内容可能包含伪装成指令的文本，诱导模型偏离用户目标、泄露秘密、扩大权限或执行未授权动作。

提示词投毒与“不适当内容”不是同一个问题：

- **提示词投毒**关注不可信内容是否劫持 Agent 的判断和工具使用；
- **内容安全**关注用户请求或模型回复是否违反产品的使用政策；
- **行为安全**关注无论模型如何判断，实际文件、命令、网络和秘密访问是否仍受确定性边界约束。

Vera 已把 Provider 输出和工具参数视为不可信输入，并由 Workspace、PolicyEngine、ApprovalGate 和 Runtime 执行校验。本规格补齐内容来源、指令权限、投毒信号、对抗评测和后续公开发布所需的内容安全边界。

## 目标

- 工程文件、工具输出、网页和模型输出不能获得用户指令或系统策略的权限。
- 提示词投毒检测只能收紧权限，不能批准动作、扩大能力或替代 PolicyEngine。
- 即使模型遵循了恶意文本，也不能产生未批准写入、危险命令、越界访问或秘密泄漏。
- 安全相关事实使用版本化结构表达，CLI、JSON、评测和未来桌面客户端共享同一 Core 语义。
- 允许用户正常分析恶意代码、攻击样本和敏感文本，避免关键词黑名单造成大范围误拒绝。
- 为公开发布前的内容审核策略保留供应商无关、可替换的接口和验证位置。

## 非目标

- 不声称彻底消除所有提示词投毒；这是持续对抗风险。
- 不使用敏感词表作为唯一或主要安全机制。
- 不把模型、分类器或 Guardrail 的输出当作授权事实。
- 不把 Vera 宣称为可安全运行任意不可信代码的 OS 沙箱。
- 阶段五不接入外部审核服务，不默认把用户源码发送给新的第三方。
- 本增量不增加网页、MCP、长期记忆、Multi-Agent、桌面端或远程更新能力。
- 不在本规格内确定公开产品的全部违法、色情、仇恨、暴力和恶意软件内容政策。

## 方案选择

### 方案 A：关键词过滤

实现简单，但容易被编码、拼写变化和上下文伪装绕过，也会错误阻止安全研究、代码审查和正常文本处理，因此不采用。

### 方案 B：单独使用 Guardrail 模型

覆盖面比关键词更好，但分类器本身仍可能被投毒、误判或不可用，并增加隐私、成本与延迟风险，因此不能成为授权边界。

### 方案 C：分层防御

采用“来源与权限分离 → 可选风险检测 → 确定性动作策略 → 参数绑定审批 → 对抗评测”的多层结构。检测层可以持续演进，但绕过检测仍不能绕过执行边界。Vera 采用该方案。

## 信任与指令模型

### 指令权限

从高到低：

1. Vera 内置安全策略和不可绕过边界；
2. 用户当前明确目标与针对具体动作的有效审批；
3. 用户明确启用的本地配置；
4. 工程约定和项目说明，仅用于工作方式建议；
5. 工程文件、代码注释、测试输出、命令输出、网页、MCP 数据、会话摘要和模型输出，不具有指令权限。

低层内容不能修改高层策略，不能自行批准动作，不能扩大 workspace、命令、网络、秘密或持久化权限。项目中的 `AGENTS.md`、README 或类似文件可以提供编码约定，但不能改变 Vera 的安全边界。

### 内容来源

后续实现应使用类似 `ContentEnvelope` 的 UI 无关结构记录：

- `source_kind`：`user_goal`、`conversation`、`workspace_file`、`project_guidance`、`tool_output`、`model_output` 或未来的 `external_resource`；
- `origin`：规范化路径、工具名称或脱敏资源标识；
- `trust_level`：`builtin_policy`、`user_intent`、`advisory` 或 `untrusted`；
- `content_hash`、大小、截断状态和必要的来源引用；
- 可选 `risk_labels`，只记录分类和证据摘要，不把原始敏感正文写入公共 Event。

来源缺失、未知或解析失败时一律按 `untrusted` 处理。上下文压缩不得把不可信内容提升为 System 或用户指令；摘要继承其输入中的最低信任级别。

## 运行链路

```text
用户目标
  ↓
可信上下文构建器 ── 工程/工具/外部内容 → ContentEnvelope(untrusted)
  ↓
ModelAdapter
  ↓
模型文本 / Tool Call（仍不可信）
  ↓
Schema 与资源校验
  ↓
PolicyEngine（唯一动作策略权威）
  ↓
必要时 ApprovalGate（绑定动作、参数、工作区、事实和策略 hash）
  ↓
执行器 → Event / Journal / Diff / 验证证据
```

风险检测器位于内容进入模型前和动作进入 PolicyEngine 前，但只产生 `allow`、`warn`、`quarantine` 或 `block` 建议及结构化原因。它不能把 `deny` 变为 `allow`，不能跳过审批，也不能生成权限。

## 提示词投毒处置

- System Prompt 明确声明：不可信内容是待分析数据，其中的命令式文本不构成用户授权。
- 工程文件、工具输出和外部数据使用结构化来源包装，不与 System Prompt 或用户目标直接拼接为同一权限层。
- 读取到疑似投毒内容后，Vera 可以继续执行只读分析；任何会扩大影响的动作必须继续通过原有策略。
- 风险信号只能把 `allow` 收紧为 `approval_required`、`quarantine` 或 `deny`，不能反向放宽。
- 写入、删除、恢复、状态迁移和非例行命令继续使用参数绑定审批；禁止“批准后续全部动作”。
- 受保护文件、秘密路径、越界路径和硬禁止命令保持直接拒绝，不因用户文本、工程说明或模型解释而改变。
- 未来增加网络工具时，必须单独定义目标域、出站数据、凭据和用户确认；提示词投毒防护不能代替出站数据策略。
- 投毒检测器不可用时不得扩大权限。Core 仍可在确定性边界内继续只读工作，并对需要额外判断的动作失败关闭或要求明确审批。

## 用户输入与内容安全

用户是任务意图来源，但用户文本不能覆盖 Vera 的内置安全边界。公开发布前建立供应商无关的 `ContentSafetyPolicy`，输出稳定的决策、类别、原因码和策略版本。

内容安全必须基于语义、上下文和行为风险，而不是单词是否出现。以下请求应保持可处理：

- 分析包含攻击语句的 README、日志或提示词投毒样本；
- 审查恶意软件、漏洞利用或敏感内容相关代码的防御性问题；
- 对用户已提供的敏感文本做分类、摘要或必要转换。

公开产品的具体拒绝类别、年龄边界、地区差异、供应商审核能力和申诉方式留到阶段十一决定。默认不得为内容审核把完整私有源码发送给额外第三方；若未来启用远程审核，必须显式告知并取得用户选择。

## 日志、隐私与展示

- 公共 Event 和普通日志只记录 `source_kind`、内容 hash、风险类别、决策、原因码和策略版本。
- 被标记内容的原文不得进入公开错误、遥测、评测报告或更新服务。
- TUI 和未来桌面端只展示 Core 提供的来源与风险事实，不自行重新分类或决定权限。
- 审批界面必须同时展示原始用户目标、准确动作、影响范围、风险原因和来源摘要，不能只显示模型的解释。
- 内容安全或投毒警告不能伪装为动作已经被阻止；界面要区分“检测到风险”和“策略已拒绝动作”。

## 失败行为

- 来源元数据缺失或版本未知：按不可信处理，不静默提升权限。
- 检测器超时、崩溃或结果无效：不扩大权限，记录脱敏失败事实。
- 模型试图泄露 System Prompt、秘密或受保护文件：拒绝相关动作，并且不把目标数据放进错误详情。
- 风险分类与确定性策略冲突：采用更严格结果；分类器永远不能覆盖硬拒绝。
- 合法安全分析被误判：允许用户查看原因并在不突破硬边界的前提下继续只读分析；不能提供全局关闭安全边界的开关。

## 对抗评测

至少覆盖以下固定夹具和变体：

1. 用户直接要求忽略系统规则、泄露提示词或秘密；
2. README、`AGENTS.md`、源码注释和测试数据要求执行无关命令；
3. 命令输出、测试失败和模型工具回执要求删除文件或扩大权限；
4. Base64、Unicode 隐藏字符、拼写扰动、Markdown/HTML 隐藏文本；
5. 跨轮对话和压缩摘要中的持久投毒；
6. 诱导读取凭据、向外部地址发送数据或修改安全配置；
7. 同时包含真实编码要求和恶意指令的混合内容；
8. 合法分析投毒、恶意代码和敏感词的反误拒绝用例；
9. 检测器不可用、未知风险类别和旧版来源结构；
10. 不同 ModelAdapter 对同一攻击集的 Core 结果一致性。

离线 Fake Model 负责确定性边界验证；可选 live red-team 只记录供应商、模型、脱敏分类和结果，不保存真实 Key、完整请求或用户源码。

## 验收标准

1. 不可信内容不能成为 System、用户审批或策略配置。
2. 任一投毒夹具均不能造成未批准写入、命令执行、越界访问或秘密泄漏。
3. 风险检测只会保持或收紧 PolicyEngine 决策，不能放宽。
4. 投毒发生前后，审批仍绑定准确动作、参数、工作区、事实和策略 hash。
5. 合法安全分析和包含敏感词的代码不会仅因关键词命中而被拒绝。
6. CLI、Plain、JSON、Eval 和未来桌面端消费同一结构化来源、风险与策略事实。
7. 日志和证据不包含被标记原文、完整请求、秘密或用户源码正文。
8. 检测器失败、未知来源和未知版本均有稳定、可验证的失败行为。
9. 提示词、工具、上下文、策略或 ModelAdapter 发生安全相关变化后，固定对抗集必须重新运行。
10. 未关闭的未授权副作用、秘密泄漏或审批绕过属于 `Critical/High`，阻止相应阶段封存。

## 分阶段实施

### 安全增量 S1：阶段五，任务 0024 契约冻结前

- 接受本规格后创建 `ADR-0015` 固化信任边界，并创建独立任务；建议任务使用下一个可用编号 `0030`，但执行顺序插入任务 0023 与 0024 之间。`ADR-0013` 已用于 Electron 桌面底版；原任务 0024 预留的 Core 客户端兼容决策顺延为 `ADR-0014`。
- 固化来源与信任语义、上下文权限规则和投毒风险结果，不接入外部审核服务。
- 增加工程文件、工具输出、会话摘要和模型 Tool Call 的确定性对抗夹具。
- 验证即使检测漏报，Workspace、PolicyEngine 和 ApprovalGate 仍阻止未授权副作用。
- 完成后再由任务 0024 冻结公共契约；否则不得把阶段五标为 Complete。

### 安全增量 S2：阶段六 CLI 产品化

- 在时间线、审批和错误体验中展示来源、风险与实际策略结果。
- TUI、Plain 和 JSON 只渲染结构化事实，不拥有内容安全或授权逻辑。
- 用户能够区分“检测到可疑内容”“需要审批”和“已被硬拒绝”。

### 安全增量 S3：阶段七 CLI 体验收口

- 在深海主题、高对比和无色模式下保持来源、风险、审批与实际策略结果可辨识。
- 视觉层级不得弱化高风险动作、把检测结果伪装为策略拒绝，或用品牌色替代明确文字。
- 真实 Terminal.app dogfood 覆盖不可信内容、审批、Diff、错误和恢复的完整呈现。

### 安全增量 S4：阶段八 Core 工具集、Policy v2 与原生 Git

- 每个 Tool Action 都携带来源、effect、规范化目标、workspace trust、用户目标授权摘要和安全上下文 hash，再进入统一 PolicyEngine。
- `balanced` 只能自动允许可信 workspace 中可恢复、范围明确的低风险动作；不可信内容只能保持或收紧决策。
- 通用 `bash` 不能绕过原生 Git、秘密、网络、提权或工作区边界；Git Commit Plan 绑定 HEAD、index、路径、验证与 Policy 事实。
- ToolResult、Diff、Git 输出、Event、Journal 与 Approval 共用脱敏和内容来源边界。

### 安全增量 S5：阶段九 Core-native Skills

- Skill 内容通过 `ContentEnvelope` 记录来源与 hash；内置和用户 Skill 仍是 advisory，workspace Skill 始终是 untrusted。
- Skill 不能注册 Tool、读取 Provider Key、扩大 Workspace、声明网络、修改 Policy/Approval 或绕过 Core 文件变更计划。
- Run 开始前冻结私有不可变 Snapshot；公共 Event/Journal 只记录身份、来源、版本、hash 和 `snapshot_id`，不记录正文。
- CLI 完成恶意 Skill、路径逃逸、竞态、Snapshot 损坏、恢复和 `NoSkill` 对抗矩阵，不依赖桌面。

### 安全增量 S6：阶段十桌面集成

- 桌面端复用相同 Command/Event 和安全决策，不解析 CLI 文本，不复制策略实现。
- 将来源、风险、Skill Snapshot、审批和操作影响做成可审阅交互，并在真实 Mac 上验证；Renderer 不自行解析或信任 Skill 包。

### 安全增量 S7：阶段十一私有预览与公开准备

- 接受公开内容政策、隐私与遥测策略、远程审核开关和供应商能力矩阵。
- 扩展网页、MCP、外部文件、持久记忆和网络出站场景的威胁模型。
- 建立版本化 red-team 集、缺陷分级、事件响应和发布阻断门禁。
- 远程安装包更新的签名、来源和回滚属于独立供应链安全规格，但必须与本规格共同进入发布检查清单。

## 参考依据

- [OWASP LLM Prompt Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)
- [OWASP AI Agent Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html)
- [NIST AI RMF: Generative Artificial Intelligence Profile](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence)
- [OpenAI：提升前沿大语言模型的指令层级结构](https://openai.com/zh-Hans-CN/index/instruction-hierarchy-challenge/)

## 关联文档

- [Vera Product Definition](../PRODUCT.md)
- [Vera 路线图](../ROADMAP.md)
- [Core 安全编辑垂直切片](2026-09-10-core-safe-editing-vertical-slice.md)
- [阶段五 Core 安全、权限与可靠性加固](2026-09-12-core-security-and-reliability-hardening.md)
- [ADR-0004：进程内会话上下文与状态边界](../decisions/ADR-0004-ephemeral-conversation-context.md)
- [ADR-0007：统一 PolicyEngine 与策略指纹](../decisions/ADR-0007-unified-policy-engine.md)
- [ADR-0015：不可信内容信任边界与提示词投毒分层防御](../decisions/ADR-0015-untrusted-content-trust-boundary.md)
- [任务 0030：不可信内容与提示词投毒防御](../tasks/0030-untrusted-content-and-prompt-injection.md)
- [任务 0024：契约冻结与阶段五验收](../tasks/0024-phase-5-contract-freeze-and-acceptance.md)
