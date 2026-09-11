# Vera 阶段二：恢复、兼容性与策略扩展规格

**状态：** Accepted
**日期：** 2026-09-11

## 目标

阶段二把已经走通的 Vera Core 与 CLI 安全编辑链路加固为一个可恢复、可兼容、可解释、可继续扩展的最小 Agent Core。

本阶段仍以 CLI 作为第一完整客户端和验收载体。所有恢复、版本迁移、策略决策和供应商错误语义必须存在于 UI 无关的 Core 中；CLI 只发送结构化 Command、展示 Event 和收集用户批准。未来桌面客户端复用同一套能力，不重新实现 Agent 逻辑。

阶段二完成后，Vera 应能在进程中断或重启后回答以下问题：

- 哪些 run 未正常结束；
- 工作区是否发生过写入；
- 当前文件与 Checkpoint 处于什么可验证状态；
- 哪些流程可以安全继续；
- 哪些操作需要重新批准；
- 哪些状态无法自动判断，必须由用户处理；
- 当前数据、策略和模型供应商是否与本版本兼容。

## 阶段边界

### 本阶段包含

- 未完成 run 的启动扫描、恢复分类和结构化报告；
- 等待审批、应用完成后等待验证等稳定边界的跨进程恢复；
- 部分写入检测、经批准的 Checkpoint 恢复和未知状态隔离；
- Command、Event、Journal 和恢复快照的独立版本入口；
- 旧数据的向后读取、非破坏迁移和未来版本拒绝；
- 统一的路径、命令、审批与恢复策略引擎；
- 策略指纹及恢复时的策略重新判定；
- ModelAdapter 能力声明、错误分类、有限重试和用量证据；
- 对应的交互式 CLI、一次性 CLI、JSON Event 和离线故障注入测试。

### 本阶段不包含

- Wails、Tauri、Electron 或其他桌面客户端；
- 退出后恢复普通对话、长期记忆、RAG 或向量数据库；
- 从任意模型推理中间轮次继续生成；
- 自动批准 Change Set、验证命令或恢复写入；
- 自动切换供应商、模型路由、负载均衡或成本优化；
- Multi-Agent、后台任务、MCP 或插件市场；
- 自动 Git commit、push、Pull Request 或合并；
- 阶段三的 10–20 项综合 Agent Eval 语料库；
- 桌面打包、公开发布、账户、计费或云端远程执行。

## 总体原则

- **Core 优先：** 恢复和策略不是 CLI 特例，必须由 Core 提供结构化服务。
- **证据优先：** 只根据持久化 Event、恢复快照、Checkpoint 和当前文件哈希判定状态。
- **未知即停止：** 无法证明安全时返回 `manual_required`，不能猜测成功或自动覆盖。
- **启动只读：** 启动扫描只报告，不自动修改工作区或恢复文件。
- **稳定边界恢复：** 只恢复已经完整持久化、可以重新校验的步骤。
- **审批不可漂移：** 审批同时绑定目标、工作区与有效策略；任一变化都使审批失效。
- **历史不可改写：** Event Journal 保持追加写入，迁移不得重写历史事实。
- **向后兼容、向前拒绝：** 已知旧格式通过明确迁移读取，未知新格式失败关闭。
- **有限重试：** 只有确定为瞬时且尚未产生本地副作用的模型请求可以重试。
- **秘密隔离：** 状态、错误、迁移报告、日志和 CLI 输出不得包含真实供应商凭据。

## 总体架构

```text
CLI / 未来桌面客户端
          |
          v
版本化 Command -------------------------------+
          |                                    |
          v                                    |
     VeraRuntime                               |
       |    |    |                             |
       |    |    +--> ModelAdapter             |
       |    |          |- capabilities         |
       |    |          |- normalized errors    |
       |    |          `- usage evidence       |
       |    |                                  |
       |    +-------> PolicyEngine             |
       |               `- PolicyDecision       |
       |
       +----------> RecoveryCoordinator <-------+
                      |       |       |
                      |       |       +--> CheckpointStore
                      |       +----------> RecoverySnapshotStore
                      +------------------> EventJournal / StateCodec
```

`VeraRuntime` 继续是单次 run 的执行权威。`RecoveryCoordinator` 负责重启后的事实重建与允许动作计算，但不能绕过 Runtime、Workspace、Checkpoint 或 PolicyEngine 直接写文件。

## 一、确定性恢复主干

### 1.1 持久化事实

阶段一的 Event Journal 继续作为审计事实。阶段二增加私有 `RecoverySnapshot`，只在以下稳定边界完成原子写入：

1. run 已创建且尚未发生工作区写入；
2. 完整 Change Set 已生成，正在等待审批；
3. Checkpoint 已完整创建，尚未开始应用；
4. 文件应用已完成，正在等待验证命令审批；
5. 文件应用已完成，等待继续执行剩余验证；
6. run 到达终止状态。

快照至少包含：

- `snapshot_version`、`run_id`、`workspace_identity`；
- 原始版本化 `StartRun`；
- 当前稳定阶段和最后一个 Journal sequence；
- Change Set 的完整私有表示与 `content_hash`；
- Checkpoint 标识和清单哈希；
- 待审批对象、目标哈希和创建审批时的 `policy_hash`；
- 验证命令列表、当前索引和已完成结果摘要；
- 是否已经发生工作区写入；
- 创建时间、更新时间和 Vera 产品版本。

快照可以包含恢复所需的项目文本和修改后内容，因此只能存放在 Vera 私有状态目录，使用仅当前用户可读写的权限。它不能包含 API Key、认证头或环境变量值。

### 1.2 写入顺序

每个稳定边界使用以下顺序：

1. 完成当前内存状态校验；
2. 追加并持久化对应 Event；
3. 构造引用该 Event sequence 的完整快照；
4. 写入同目录临时文件；
5. flush 并在平台支持时同步文件；
6. 原子替换正式快照；
7. 才把 Event 和新状态暴露给客户端，并在下一项副作用前确认快照成功。

如果快照写入失败，不进入下一项可能产生副作用的步骤，并尽力追加明确失败 Event。Journal 中已经持久化但尚未被快照引用的尾部 Event 仍是事实；下次扫描通过 sequence、Journal 和文件哈希降级分类。终止快照写入失败时，Journal 同样保留已发生事实。

### 1.3 工作区身份

`workspace_identity` 由规范化绝对路径和本机 Vera 安装生成的稳定标识组成。恢复时必须重新解析路径并验证：

- 工作区仍存在且是目录；
- 规范化路径与记录一致；
- 没有通过符号链接改变边界；
- 当前用户仍可读取恢复所需文件；
- 所有受影响路径仍处于工作区内。

工作区移动或身份无法确认时，不自动续跑，状态为 `manual_required`。阶段二不自动搜索被移动的工程。

### 1.4 恢复分类

启动扫描必须产生以下稳定分类之一：

| 分类 | 条件 | 允许动作 |
|---|---|---|
| `resumable_approval` | 完整 Change Set、待审批对象、目标哈希和工作区状态均可验证，尚未写入 | 查看、重新判定策略、继续审批、放弃 |
| `resumable_verification` | 所有目标文件均为已批准的修改后哈希，Checkpoint 完整，仍有验证步骤 | 查看、重新判定命令策略、继续验证、保留现场 |
| `safe_to_abandon` | 可以证明没有工作区修改，且没有待处理恢复写入 | 标记放弃、基于原目标重新运行 |
| `recoverable_partial_apply` | 每个目标都精确匹配修改前或修改后哈希，出现两者混合，Checkpoint 完整 | 查看恢复计划、经批准恢复到修改前状态 |
| `manual_required` | 任一路径为未知哈希、快照损坏、Checkpoint 缺失、工作区身份变化或证据矛盾 | 只读报告，不自动写入 |
| `legacy_not_resumable` | 阶段一历史 run 没有恢复快照 | 查看 Journal、按既有规则手动回滚 |

扫描本身只读取数据。即使分类为 `recoverable_partial_apply`，也必须由用户批准精确恢复目标及哈希后才能调用 Checkpoint 恢复。

### 1.5 可恢复与不可恢复步骤

允许跨进程继续：

- 完整持久化的 Change Set 审批；
- 已应用文件后的验证命令审批；
- 已应用文件后的剩余验证命令；
- 经批准的确定性 Checkpoint 恢复。

不允许从中间点继续：

- 正在进行的模型请求；
- 模型工具循环中的任意临时消息；
- 未完整持久化的 Change Set 构建；
- 正在运行的外部验证进程；
- 无法确认是否到达服务器的供应商请求。

这些情况在没有工作区副作用时归为 `safe_to_abandon`；存在不确定写入时按文件哈希归入部分恢复或人工处理。用户可以使用原目标启动新 run，但系统不能声称它是原模型轮次的精确续跑。

### 1.6 幂等性

- 重复扫描不得修改 Journal、快照或工作区。
- 已处理过的 `ResumeRun` 不能重复执行同一文件应用或验证步骤。
- 恢复操作必须绑定恢复计划哈希；计划变化后原审批失效。
- 终止 Event 已存在时，重复终止只返回当前终态，不追加相互矛盾的结果。
- 原子恢复中断后再次扫描，仍通过文件哈希重新分类，而不是信任内存标记。

## 二、版本兼容与非破坏迁移

### 2.1 三种独立版本

- `schema_version`：公共 Command/Event 语义版本；
- `journal_format_version`：Journal 文件组织和编码版本；
- `snapshot_version`：恢复快照结构版本。

Vera 产品版本只用于诊断，不能替代以上数据格式版本。

### 2.2 Codec 边界

新增统一 `ContractCodec` 和 `StateCodec`：

- 根据版本选择明确 Decoder；
- 把已支持旧结构迁移为当前内存模型；
- 对缺失字段使用该版本规范定义的默认值；
- 对损坏数据返回结构化错误和具体文件，不部分解析；
- 对高于当前支持版本返回 `unsupported_version`；
- 不允许业务模块自行猜测或静默忽略版本。

公共 Pydantic 模型仍负责当前版本校验，Codec 负责版本分派和迁移。迁移函数是纯函数，可使用冻结 Fixture 确定性测试。

### 2.3 历史数据

- 现有 `schema_version=1` Command/Event 继续可读取；
- 没有 run manifest 或恢复快照的旧目录标记为 `legacy_not_resumable`；
- 旧 run 继续支持 `/runs`、`/show` 和满足既有哈希规则的手动回滚；
- 不为旧 run 伪造当时不存在的可恢复内存状态；
- Event Journal 永远不因迁移被重排、删除或原地重写。

### 2.4 磁盘迁移

只有新版本不能通过只读 Decoder 工作时，才执行磁盘迁移。迁移流程必须支持：

1. dry-run 扫描；
2. 列出来源版本、目标版本和受影响文件；
3. 在同一状态目录创建恢复副本；
4. 写入新的派生文件或原子替换目标；
5. 验证迁移结果可完整读取；
6. 失败时保持原数据并输出报告。

阶段二建立迁移接口和 Fixture，但不为了证明接口而随意把公共协议升级到版本 2。

## 三、统一 PolicyEngine

### 3.1 职责

`PolicyEngine` 统一处理：

- 工作区路径访问和敏感文件；
- 模型可调用工具；
- 验证命令；
- Change Set 写入；
- Checkpoint 恢复；
- 恢复 run 的继续、放弃和人工处理边界。

它只做判定，不执行工具、命令、文件写入或恢复。

### 3.2 结构化决定

```text
PolicyDecision
├── decision: allow | approval_required | deny
├── reason_code: 稳定机器码
├── reason: 面向用户且不含秘密的解释
├── matched_rule: 命中规则标识
└── policy_hash: 当前有效策略指纹
```

`reason_code` 和 `matched_rule` 属于可测试协议；自然语言 `reason` 可以优化措辞，但不能改变决定语义。

### 3.3 规则优先级

规则按固定顺序计算：

1. 硬性禁止；
2. 工作区边界和敏感资源保护；
3. 用户级明确授权；
4. 内置安全规则；
5. 要求本次审批。

项目配置只能降低资源限制、增加禁止项或建议验证命令，不能授予权限。用户授权也不能覆盖硬性禁止、工作区逃逸、提权、Shell 解释器或宽泛破坏性命令。

### 3.4 策略指纹与审批

`policy_hash` 根据规范化的有效规则、内置策略版本和相关工作区身份生成，不包含秘密值。

Change Set、验证命令和恢复计划的审批绑定：

- 审批 ID；
- 目标 ID 与目标内容哈希；
- `workspace_identity`；
- `policy_hash`。

恢复时必须重新计算决定。策略、工作区或目标变化时，旧审批失效并产生结构化 Event；不能沿用更宽松的历史授权。

### 3.5 权限展示

`/permissions` 和未来桌面客户端从同一个 `PolicyEngine.snapshot()` 获取状态。若某条配置没有注入实际引擎，不能显示为已生效。

阶段二仍不支持：

- 自动批准；
- 项目级授权白名单；
- 通配命令规则；
- Shell 字符串执行；
- 在会话内临时关闭硬性规则。

## 四、ModelAdapter 兼容性与韧性

### 4.1 能力声明

每个 Model Profile 装配时产生 `ModelCapabilities`，至少声明：

- 是否支持 Tool Calling；
- 是否支持并行 Tool Call；
- 可用上下文和输出限制是否已知；
- 是否返回标准化 usage；
- 供应商请求标识是否可获得。

编码 run 在调用模型前验证必要能力。缺少 Tool Calling 时返回 `capability_mismatch`，不进入可能误导用户的降级文本模式。

### 4.2 标准化错误

供应商异常统一映射为：

| 错误码 | 是否默认重试 |
|---|---|
| `provider_configuration_error` | 否 |
| `provider_authentication_error` | 否 |
| `provider_network_error` | 是，有限次数 |
| `provider_timeout` | 是，有限次数 |
| `provider_rate_limited` | 是，尊重合法 Retry-After |
| `provider_service_error` | 仅 5xx 等明确瞬时错误 |
| `provider_invalid_response` | 否 |
| `capability_mismatch` | 否 |

错误 Event 只包含稳定错误码、脱敏说明、attempt 和可选供应商请求标识。不得写入认证头、API Key、完整请求正文或未经清洗的供应商异常对象。

### 4.3 重试边界

- 默认最多两次请求尝试；
- 退避时间有上限，并可注入时钟以便测试；
- 自动重试只包围一次 ModelAdapter 请求；
- 不重复执行本地工具、文件应用、验证命令或审批；
- 已解析出 Tool Call 的响应不因后续展示或持久化错误重新请求模型；
- 超时后无法确认供应商是否完成生成时，可以重试模型请求，但必须记录新的 attempt；这不会被描述为同一供应商请求的续传；
- 第一版不自动切换 Profile 或供应商。

### 4.4 用量证据

`model.completed` 或对应失败 Event 记录可获得的：

- 输入 Token；
- 输出 Token；
- 总 Token；
- 请求耗时；
- attempt；
- 供应商请求标识。

缺失值使用 `null/unavailable`，不能填零。阶段二只提供单 run 证据，不建立计费系统。

### 4.5 供应商验证

DeepSeek 与 GLM 继续通过 OpenAI-compatible 适配边界接入。默认测试使用脱敏的固定响应 Fixture，覆盖文本、Tool Call、usage、限流、超时和格式错误。

live 测试必须显式选择且默认排除。自动验收不得读取或使用用户真实 DeepSeek、GLM Key。

## 五、Core Command、Event 与 CLI

### 5.1 新增 Command

阶段二计划引入版本化 Command：

- `InspectRecovery(run_id: str | None)`：只读扫描全部或指定 run；
- `ResumeRun(run_id: str)`：请求继续 Core 判定为可恢复的稳定流程；
- `AbandonRun(run_id: str)`：结束可以证明没有未解决写入的 run；
客户端不能自行选择恢复分类、跳过重新校验或直接调用 CheckpointStore。

`ResumeRun` 遇到 `recoverable_partial_apply` 时只提出带哈希的恢复计划，并复用现有 `approval.required(kind="recovery")` 与 `ResolveApproval` 完成批准或拒绝。

### 5.2 新增 Event

- `recovery.detected`：报告分类、证据和允许动作；
- `recovery.resume_started`、`recovery.resumed`；
- `recovery.abandoned`；
- `recovery.restore_proposed`；
- `recovery.restored`；
- `recovery.manual_required`；
- `approval.invalidated`；
- `state.migration_planned`、`state.migration_completed`、`state.migration_failed`；
- `model.retrying`、`model.failed`。

恢复审批继续使用 `approval.required`、`approval.resolved` 和 `approval.invalidated`，其中 `kind="recovery"`。以上事件名称由本规格固定，契约测试必须覆盖，CLI 文本不能成为协议。

### 5.3 Interactive CLI

- 启动时调用只读恢复扫描；只有发现未完成 run 时显示数量和最高风险；
- `/recover`：列出待处理 run；
- `/recover <run-id>`：显示分类、文件证据和允许动作；
- `/resume <run-id>`：继续安全的审批或验证流程；
- `/abandon <run-id>`：结束未产生工作区副作用的中断 run；
- 部分写入恢复在 `/recover <run-id>` 中展示恢复计划，并进入独立审批；
- `/resume` 不恢复已退出的普通对话，会话内存规则保持不变。

### 5.4 一次性 CLI 与 JSON

提供对应的 `vera recover list/show/resume/abandon` 命令。人类模式展示证据和建议，`--json` 只输出 Event JSON Lines，不包含提示符或 ANSI。

非交互环境遇到恢复审批时安全取消。退出码沿用现有语义：`0` 表示命令完成，`2` 表示用户拒绝或取消且不存在未解决写入，`3` 表示恢复后的验证失败，`4` 表示请求或 Runtime 失败且不存在未解决写入，`5` 表示恢复失败或仍存在需要人工处理的写入风险。

## 六、失败行为

- Journal 损坏：隔离该 run，报告确切路径和最后可验证 sequence；其他 run 继续可用。
- 快照损坏：尝试只读 Journal 与文件哈希降级分类，证据不足则 `manual_required`。
- Checkpoint 缺失或哈希不符：禁止自动恢复。
- 工作区不存在、移动或越界：禁止 resume；不自动搜索工程。
- 策略变化：废止旧审批，按当前策略重新判定。
- 恢复验证再次失败：保留已应用现场和 Checkpoint，输出新验证证据。
- 恢复操作中断：下次重新扫描文件哈希，不能仅依赖“恢复中”标记。
- 供应商重试耗尽：run 明确失败；审批前不修改工作区，应用后验证阶段保持可恢复。
- 状态版本过新：只报告 `unsupported_version`，不写回文件。
- 单个损坏 run 不能阻止 Vera 查看其他历史或启动新任务。

## 七、安全与隐私

- 恢复快照和迁移副本位于 Vera 私有状态目录，不进入用户项目或 Git。
- 状态目录和敏感文件在 POSIX 平台使用仅当前用户可读写权限。
- 快照、Journal、错误和展示统一经过秘密字段拒绝与值脱敏。
- 恢复计划列出相对路径、操作和哈希，不输出不必要的完整文件正文。
- 启动扫描不执行项目脚本、Git Hook、Shell 或模型请求。
- Git 和文件探测使用固定参数、无 Shell、只读且有超时的实现。
- 迁移备份不能自动进入模型上下文。
- 任何恢复写入都重新执行 WorkspacePaths、Checkpoint 和 PolicyEngine 校验。

## 八、测试与验证

### 8.1 确定性故障注入

通过注入式 failpoint 覆盖：

- Change Set 持久化前后中断；
- 等待审批时重启；
- Checkpoint 创建前后中断；
- 每个文件应用前后中断；
- 全部应用完成但终止 Event 未写入；
- 验证命令审批前后中断；
- 验证进程启动、超时和完成后中断；
- Checkpoint 恢复每一步中断。

每个场景重建 Runtime/RecoveryCoordinator，不能复用原进程内对象冒充重启。

### 8.2 兼容性 Fixture

- 当前阶段一 `schema_version=1` Command/Event；
- 无恢复快照的 legacy run；
- 当前 snapshot v1；
- 阶段一无 manifest 的 legacy run Fixture；
- 未支持未来版本；
- 截断 JSONL、sequence 不连续、快照 JSON 损坏和哈希矛盾。

Fixture 不包含真实工程数据或供应商凭据。

### 8.3 策略矩阵

覆盖每种动作、规则优先级、用户授权、项目收紧、硬性禁止、策略指纹变化、审批失效和恢复重新判定。

### 8.4 ModelAdapter 契约

所有适配器运行同一套 conformance tests。固定响应覆盖普通文本、单/并行 Tool Call、usage 缺失、限流、超时、5xx、认证失败和无效响应。

### 8.5 CLI 与进程测试

- 从仓库外启动 `vera`；
- 进程退出后使用同一私有测试状态目录扫描恢复；
- 人类模式和 JSON 模式；
- 恢复审批批准、拒绝、取消和 EOF；
- legacy run 查看与回滚；
- 单个损坏 run 隔离；
- 输出不包含测试秘密、Base URL 或恢复快照正文。

### 8.6 必需检查

- 完整非 live pytest；
- Ruff lint；
- Ruff format check；
- Mypy strict；
- Python 包构建；
- `git diff --check`；
- 仓库外 editable CLI 验收。

自动验收不读取真实供应商 Key，不修改 `/Users/admin/Desktop/VeraTestDemo`。

## 九、阶段二施工拆分

阶段二按依赖顺序拆为五个可独立验收的增量：

1. **恢复事实与分类：** RecoverySnapshot、原子持久化、启动扫描和只读报告；
2. **安全续跑与恢复：** 审批续跑、验证续跑、部分应用恢复和幂等性；
3. **兼容性基础：** Codec、冻结 Fixture、legacy 读取和非破坏迁移接口；
4. **统一策略：** PolicyEngine、策略指纹、审批失效和权限展示；
5. **供应商韧性与阶段验收：** capabilities、错误分类、有限重试、usage、CLI 收口和完整故障矩阵。

每个增量使用一个主实现 Agent，按规格、失败测试、最小实现、局部验证、文档同步和独立提交推进。禁止多个 Agent 同时编辑同一工作树。

## 十、阶段退出条件

只有同时满足以下条件，阶段二才算完成：

1. 所有规定中断点都能在新进程中得到确定恢复分类；
2. 等待审批和应用后验证可以安全续跑；
3. 部分写入只在完整哈希证据和明确批准后恢复；
4. 未知或矛盾状态始终停止并提供人工处理证据；
5. 重复扫描、resume 和恢复动作具备幂等性；
6. 旧 run 仍可查看和安全回滚，未知未来版本失败关闭；
7. 策略优先级、指纹和审批失效由同一个 Core 引擎执行；
8. DeepSeek/GLM 固定 Fixture 通过统一 ModelAdapter conformance tests；
9. 瞬时供应商错误有限重试且不会重复本地副作用；
10. Interactive CLI 与一次性 CLI 都只消费结构化 Command/Event；
11. 完整非 live 测试、静态检查、构建和仓库外 CLI 验收通过；
12. 没有读取真实 Key、修改真实验收工程或引入桌面框架。

## 关联文档

- [产品定义](../PRODUCT.md)
- [路线图](../ROADMAP.md)
- [Core 安全编辑垂直切片规格](2026-09-10-core-safe-editing-vertical-slice.md)
- [普通对话、会话上下文与状态命令规格](2026-09-11-conversational-cli-and-session-status.md)
- [ADR-0002：Command → VeraRuntime → Event](../decisions/ADR-0002-command-event-contract.md)
- [ADR-0003：私有状态、Event Journal 与 Checkpoint](../decisions/ADR-0003-private-state-and-checkpoints.md)
- [ADR-0005：确定性 Run 恢复边界](../decisions/ADR-0005-deterministic-run-recovery.md)
- [ADR-0006：版本化 Codec 与非破坏迁移](../decisions/ADR-0006-versioned-state-codecs.md)
- [ADR-0007：统一 PolicyEngine 与策略指纹](../decisions/ADR-0007-unified-policy-engine.md)
- [ADR-0008：ModelAdapter 能力、错误与有限重试](../decisions/ADR-0008-model-capabilities-and-errors.md)
- [阶段二执行顺序](../tasks/phase-2-execution-order.md)
- [任务 0005：恢复事实与只读分类](../tasks/0005-recovery-facts-and-classification.md)
- [任务 0006：安全续跑与部分写入恢复](../tasks/0006-safe-run-resume-and-recovery.md)
- [任务 0007：版本化 Codec 与兼容迁移](../tasks/0007-versioned-codecs-and-migration.md)
- [任务 0008：统一 PolicyEngine 与审批指纹](../tasks/0008-unified-policy-engine.md)
- [任务 0009：ModelAdapter 韧性与阶段二验收](../tasks/0009-model-resilience-and-phase-2-acceptance.md)
