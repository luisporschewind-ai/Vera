# Vera Core 安全编辑垂直切片规格

**状态：** 已接受
**日期：** 2026-09-10

## 目标

构建 Vera 第一个可复用的 Python Core 和 CLI 垂直切片。用户向 Vera 提出一个编码目标；Vera 在限定的工作区内收集上下文，请求模型提出一个完整的 Change Set，暂停并等待审批，创建 Checkpoint，应用已批准的文件修改，执行验证，输出结构化证据，并支持手动回滚本次修改。

本增量确立 `VeraRuntime` 的产品权威地位。模型、供应商客户端、CLI 展示层和未来的桌面外壳都是可替换的边缘组件。运行状态、工作区策略、审批、Change Set、Checkpoint、验证和公共事件始终由 Vera Runtime 掌握。

已退役的 `/Users/admin/Coding-harness` 原型仅作为可行性证据。本规格不会把原型已经完成的读写验证重新当作里程碑，也不会复制其架构或代码。

## 非目标

本增量不包含：

- Wails、Electron、Tauri 或其他桌面外壳；
- 多 Agent 或子 Agent 编排；
- MCP、插件市场、RAG、向量数据库或长期记忆；
- 无人值守的写入审批或自动修复循环；
- 崩溃时续跑或跨进程恢复运行；
- 云端同步、账号系统、远程执行沙箱或遥测；
- 高级 Git 分支、提交、Pull Request 或合并自动化；
- 模型逐 Token 流式展示；
- 面向最终用户的公开发布、许可证决策或安装包。

Phase 2 将把这些最小安全语义扩展到更多仓库和故障场景，并进一步加固。特别是，重启恢复仍属于 Phase 2；本增量提供持久化证据和手动回滚，但不承诺进程崩溃后自动续跑。

## 架构

第一版采用一个 Python 发行包，并在内部划分职责清晰的子包：

```text
src/vera/
├── contracts/       # Command、Event、Change Set、审批和结果
├── runtime/         # 状态机和 Agent 编排
├── models/          # 与供应商无关的接口和适配器
├── tools/           # 工具注册、校验和执行策略
├── workspace/       # 路径安全、快照、应用和回滚
├── verification/    # 验证计划和证据
└── cli/             # 人机交互和结构化展示
```

依赖方向始终指向稳定契约。供应商 SDK 类型不能越过 `models/`；终端展示格式不能越过 `cli/`；文件系统和进程细节不能越过各自负责的边界。

```text
用户或未来桌面客户端
            |
            v
CLI 或结构化进程协议
            |
            v
       VeraRuntime ---------> 有序 Event 流
        |   |   |
        |   |   +-----------> Workspace、Checkpoint、Verification
        |   +---------------> Tool Registry 与安全策略
        +-------------------> ModelAdapter -> DeepSeek / GLM
```

初始 CLI 可以在同一进程内直接调用 Core Python API，但公共 Core 接口仍必须表示为带版本号、可序列化为 JSON 的 Command 和 Event。未来由桌面壳管理的 Core 子进程可以通过 JSON Lines 或其他分帧协议传递同一份契约，不需要解析面向人的 CLI 文本。本增量不要求实现子进程服务。

## 组件职责

### VeraRuntime

`VeraRuntime` 是唯一的协调者，也是运行事实的唯一来源。它负责：

- 校验启动命令并构建受限的运行上下文；
- 掌握状态机及全部合法状态转换；
- 调用 `ModelAdapter` 并校验模型返回的每一个 Tool Call；
- 只分派已经注册且符合本地策略的工具；
- 构建权威 Change Set 及其内容哈希；
- 在命令审批和 Change Set 审批边界暂停；
- 要求目标文件写入前必须成功完成 Checkpoint；
- 应用文件、启动验证并记录结果；
- 写入过程在本进程内失败时协调自动恢复；
- 为已经完成的写入提供手动回滚；
- 为每个重要状态转换输出有序、带版本号的 Event。

模型或客户端都不能直接设置 Runtime 状态，也不能自行宣称审批、Checkpoint、写入、验证或回滚已经成功。

### ModelAdapter

与供应商无关的适配器接收 Vera 消息和工具定义，并返回标准化的模型轮次：

```text
assistant_text
tool_calls[]
finish_reason
usage
provider_metadata
```

首个供应商实现是可配置的 OpenAI-compatible Adapter，通过不同配置连接 DeepSeek 和 GLM。一个维护良好的供应商客户端负责 HTTP、认证、序列化和供应商流式协议，Vera 不手写这些传输细节。Runtime 不依赖供应商响应类。

供应商输出是不可信输入。即使供应商声称返回了合法的结构化 Tool Call，Runtime 仍必须重新校验工具名称、参数 Schema、资源限制、路径和权限策略。

### 工具

第一版 Tool Registry 支持：

- 列出工作区内的目录；
- 搜索工作区内的文本；
- 读取允许访问的文本文件；
- 为 Change Set 提议创建、更新或删除操作；
- 提议一个以参数数组表示的验证命令。

不存在向模型开放的直接写入工具。模型只提供期望的修改后内容或删除意图；Runtime 负责读取当前状态、计算哈希并生成统一 Diff。

第一版不把重命名定义为独立操作。重命名表示为同一个 Change Set 中的一次创建和一次删除，因此会作为一个整体接受审批和 Checkpoint 保护。

### Workspace 与 Checkpoint

Workspace 负责规范化路径解析和文件系统副作用。公共路径全部使用经过规范化的工作区相对路径。读取符号链接时，只有解析后的目标仍在工作区内才可以继续；修改操作永远不跟随符号链接。

应用 Change Set 前，Workspace 必须使用记录的修改前哈希核对全部受影响文件，预检全部操作，并创建 Checkpoint 清单和原始文件字节。Checkpoint 和运行记录存放在 Vera 私有且可配置的状态目录中，不写入用户项目。在平台支持时，状态目录和文件必须设置为仅当前系统用户可读写。

Checkpoint 内容是本地恢复数据，不能自动加入模型上下文。

### Verification

Verification 在文件应用后执行已经批准的验证计划，并返回结构化证据。命令使用参数数组表示，不经过 Shell 解释器。每个命令都包含工作区相对工作目录、超时时间、退出码、执行时长以及受大小限制的 stdout 和 stderr。

安全策略把命令分为自动允许、需要单独审批和禁止执行。项目配置可以建议验证命令，但不能自行把命令标记为安全，也不能削弱用户级或内置限制。

## Runtime 生命周期

正常状态路径为：

```text
CREATED
  -> DISCOVERING
  -> GENERATING
  -> CHANGESET_PROPOSED
  -> AWAITING_APPROVAL
  -> CHECKPOINTING
  -> APPLYING
  -> VERIFYING
  -> COMPLETED | VERIFICATION_FAILED | FAILED
```

本增量中，一次运行最多生成一个 Change Set。验证失败不会触发第二轮模型写入。

`CANCELLED`、`STALE` 和 `RECOVERY_REQUIRED` 是额外的终止状态，分别表示明确取消、修改前哈希不匹配和恢复失败。`run.completed` 携带 `COMPLETED` 或 `VERIFICATION_FAILED`；`run.failed` 携带 `FAILED` 或 `RECOVERY_REQUIRED`。取消和 Change Set 过期分别使用各自的终止 Event。

命令审批可以在发现阶段或验证阶段中断流程。Runtime 输出审批请求，并保持暂停，直到该次精确命令请求被批准、拒绝或取消。非必要命令被拒绝后，Runtime 向模型返回拒绝结果；必要验证命令被拒绝后，验证阶段结束且不执行该命令。

Change Set 审批与其精确的规范化内容哈希绑定。该哈希覆盖受影响路径、操作、修改前和修改后哈希以及验证计划。任何内容变化都会使原审批失效。

Runtime 在创建 Checkpoint 前以及实际应用前，都会再次比较当前文件和记录的修改前哈希。如果不一致，Change Set 标记为过期，运行结束且不写入目标文件。

## Core 契约

所有 Command 和 Event 都包含 `schema_version: 1`。标识符是不透明值，并且在本地 Vera 安装范围内唯一。

### Command

第一版契约需要：

- `StartRun`：目标、工作区根目录、模型配置和请求的验证策略覆盖项；
- `ResolveApproval`：审批标识、被批准目标的哈希，以及批准或拒绝决定；
- `CancelRun`：运行标识；
- `RollbackRun`：运行标识或 Checkpoint 标识。

Runtime 分配运行、Change Set、Checkpoint、Event 和审批标识。客户端不能选择具有权威性的标识符。Runtime 同样负责计算最终生效的安全策略；客户端不能把自己请求的策略标记为权威策略。

### Change Set

一个 Change Set 包含：

- `changeset_id` 和 `run_id`；
- 面向用户的摘要；
- 一个或多个有序文件修改；
- 建议的验证计划；
- 规范化的 `content_hash`。

每个文件修改包含一个操作（`create`、`update` 或 `delete`）、规范化的相对路径、修改前哈希或文件不存在标记、修改后哈希或文件删除标记，以及 Runtime 生成的统一 Diff。Runtime 在终端展示之外单独保留预期写入的精确字节。

### Approval

审批请求包含审批类型（`command` 或 `changeset`）、目标标识、不变的目标哈希、面向用户的说明和风险信息。只有审批标识和目标哈希同时匹配 Runtime 当前暂停等待的请求，审批决定才有效。

### Checkpoint 清单

Checkpoint 清单记录：

- Checkpoint 和运行标识；
- 每一个受影响的相对路径；
- 每个路径在修改前是否存在；
- 原始文件哈希、字节和平台支持的权限元数据；
- 成功应用后预期出现的哈希。

手动回滚只有在路径的当前状态与记录的应用后状态一致时才进行恢复。如果任一路径在 Vera 写入后又发生变化，回滚必须在覆盖前停止并报告冲突。强制覆盖冲突不属于本增量。

### VerificationResult

每个结果记录精确的参数数组、相对工作目录、开始和结束时间、执行时长、退出码或超时、受大小限制的 stdout 和 stderr，以及一个终止状态：`passed`、`failed`、`timed_out`、`rejected` 或 `error`。

### Event 信封

每个 Event 使用以下信封：

```json
{
  "schema_version": 1,
  "event_id": "evt_...",
  "run_id": "run_...",
  "sequence": 12,
  "timestamp": "2026-09-10T12:00:00Z",
  "type": "changeset.proposed",
  "payload": {}
}
```

序号在同一次运行中单调递增。Event 先追加到本次运行的本地 JSON Lines 记录，然后才把对应状态转换暴露给客户端。

必须支持的 Event 类型包括：

- `run.started`、`run.cancelled`、`run.completed` 和 `run.failed`；
- `model.requested` 和 `model.completed`；
- `tool.started` 和 `tool.completed`；
- `changeset.proposed`、`changeset.stale` 和 `changeset.applied`；
- `approval.required` 和 `approval.resolved`；
- `checkpoint.created`、`checkpoint.restored` 和 `checkpoint.restore_failed`；
- `verification.started` 和 `verification.completed`；
- `rollback.completed` 和 `rollback.conflicted`。

供应商原生对象和 CLI 格式不属于 Event 契约。Event Payload 和错误在持久化或展示前必须经过统一脱敏。

## 工具与上下文策略

### 权限级别

工具和命令有四种执行判定：

| 判定 | 含义 | 示例 |
|---|---|---|
| 自动允许 | 完成 Schema 和工作区校验后执行 | 列目录、受限代码搜索、读取普通文本 |
| 策略允许 | 精确参数形式符合已接受的安全规则，因此可以执行 | 配置的测试或 Lint 命令 |
| 需要审批 | 暂停并请求用户批准精确的命令哈希 | 未进入允许清单但可以在本地执行的命令 |
| 禁止执行 | 直接拒绝，不向模型提供改变限制的入口 | 工作区逃逸、提权、宽泛破坏性操作 |

命令执行永远不调用 Shell。Shell 运算符、重定向、管道、命令替换和复合命令字符串都不会被解释。安全策略拒绝提权工具、工作目录逃出工作区的命令和宽泛的破坏性操作。在本增量中，即使用户明确批准，也不能削弱这些硬性禁令。

### 敏感文件

敏感凭据、私钥和真实环境变量文件默认禁止访问。`.env.example` 等安全模板可以读取。配置可以增加受保护模式，但不能移除内置凭据保护。

配置、Event、日志、终端输出和异常文本中不得写入秘密值。脱敏覆盖已经配置的秘密值和常见凭据字段名。

### 资源限制

初始生效策略使用以下有限默认值：

- 每次运行最多 20 个模型轮次；
- 每次运行最多 50 次工具调用；
- 单次文件读取最多 1,000,000 字节；
- 单次工具调用最多返回 100,000 字节；
- 每次运行最多收集 2,000,000 字节的工作区上下文；
- 每条验证命令最多执行 120 秒。

项目策略只能降低这些限制。用户级策略或显式 CLI 参数可以设置其他有限正值，但不能彻底关闭限制。Runtime 必须在对应工具或验证结果中明确标记每一次截断。

Runtime 检测参数完全相同的连续重复工具调用。如果相同结果未发生变化，连续三次后以失败结束循环。Agent 轮次、工具调用和上下文限制作用于审批前，因此触发时不会写入目标文件。验证阶段在应用后使用独立的命令数量和超时限制；验证失败时仍可使用手动回滚。

## 失败行为

- 模型、解析、读取或搜索在审批前失败时，目标文件保持不变。
- 拒绝或取消 Change Set 时，运行结束且不写入目标文件。
- Checkpoint 创建失败时，禁止进入应用阶段。
- 修改前哈希过期时，禁止应用，必须重新生成 Change Set。
- 应用过程中失败时，立即在当前进程内尝试恢复 Checkpoint，并明确报告恢复是否成功。
- 恢复失败时，以 `RECOVERY_REQUIRED` 结束并列出确切受影响路径，绝不宣称已经安全恢复。
- 验证失败时保留已应用文件和 Checkpoint，输出 `verification.completed`，并以 `VERIFICATION_FAILED` 结束。
- 手动回滚发生冲突时，不覆盖用户后续修改。
- 进程崩溃后可能留下持久化 Checkpoint 和不完整 Event 历史，但本增量不承诺重启后自动检查或续跑。

Runtime 没有获得本地可观察证据时，不能把供应商响应、进程退出或文件系统调用描述为成功。

## CLI 行为

第一版 CLI 表面为：

```text
vera run <goal>
vera runs list
vera runs show <run-id>
vera rollback <run-id>
vera config show
```

`vera run` 接受工作区和模型配置选项。人类模式展示进度、Change Set 摘要、受影响文件、完整 Diff、风险信息、验证计划、最终证据、运行标识和回滚命令。审批必须由用户明确选择批准或拒绝。第一版不提供 `--yes` 或同类写入自动批准参数。

`--json` 输出不含 ANSI 格式的 JSON Lines Event 信封。在非交互环境中，Runtime 输出 `approval.required`，记录取消，以状态码 `2` 退出，并且不写入目标文件。跨进程继续审批属于未来的结构化 Sidecar 协议；CLI 绝不能根据终端缺失推断用户已经批准。

`vera config show` 展示生效的非秘密配置，并对秘密值脱敏。供应商配置引用环境变量名称，不保存真实密钥：

```toml
[providers.deepseek]
base_url = "https://provider.example/v1"
api_key_env = "DEEPSEEK_API_KEY"
```

具体 Base URL 属于本地配置，不是编译进产品的固定值。

配置优先级依次为 CLI 参数、环境变量、项目 `.vera/config.toml`、用户配置、内置默认值，但只在各来源获准设置的字段内比较优先级。工作区可由用户显式选择；供应商、模型、Provider endpoint、Key 引用、模型目录启用状态、顺序与默认项只接受用户可信配置或用户显式 CLI 操作。项目配置不能定义、覆盖或选择这些字段，只能收紧获准的低信任项目选项与资源限制；用户配置和显式 CLI 参数可以设置其他有限正值。任何配置来源都不能关闭限制、提供项目秘密、自行声明命令安全或削弱内置安全规则。BYOK 配置的具体边界见 [ADR-0022](../decisions/ADR-0022-user-owned-byok-provider-configuration.md) 与 [BYOK 多厂商模型配置](2026-09-25-byok-model-configuration.md)。

退出状态码为：

- `0`：修改已应用且验证通过；
- `2`：已拒绝或取消，不存在未解决写入；
- `3`：修改已应用，但验证失败；
- `4`：模型、工具、策略或 Runtime 失败，且不存在未解决的部分写入；
- `5`：恢复失败，需要人工处理。

## 测试策略

默认测试是确定性的，不发起供应商网络请求。使用脚本化的 `FakeModelAdapter` 驱动 Runtime 完成精确的工具调用和结果流转。

### 单元测试与组件测试

测试覆盖：

- 全部合法状态转换和具有代表性的非法转换；
- Command 与 Event Schema 校验和事件顺序；
- Change Set 规范化哈希和审批失效；
- 路径穿越、绝对路径、符号链接逃逸和受保护文件拒绝；
- 命令分类、参数处理、超时和 Shell 元字符不解释；
- 上下文、输出、轮次、工具调用和重复调用限制；
- 配置、错误、日志和 Event 中的秘密脱敏；
- Checkpoint 清单、平台支持的文件权限和逐字节精确恢复；
- 应用失败恢复和恢复失败报告；
- 验证成功、失败、超时和拒绝；
- 回滚成功和应用后冲突拒绝。

### CLI 集成测试

子进程测试覆盖人类模式和 JSON 模式、交互式批准和拒绝、非交互审批取消、命令输出、运行记录查看、回滚和退出状态码。

### 一次性 Git 测试项目

自动化端到端测试创建一个临时 Git 仓库并执行以下链路：

```text
创建测试项目
-> 启动运行
-> FakeModelAdapter 读取并搜索
-> 提议 Change Set
-> 批准
-> 创建 Checkpoint
-> 应用修改
-> 执行验证
-> 检查 Git Diff
-> 回滚
-> 确认逐字节恢复
```

拒绝分支需要证明项目文件和 Git 状态都没有变化。

### 供应商冒烟测试

DeepSeek 和 GLM 各自提供一个可选、低成本的 Adapter 冒烟测试，并排除在默认测试套件和 CI 之外。测试在供应商提供相关数据时验证认证、一次标准化响应、Tool Call 转换和 Usage 记录。本增量实现完成前，至少一个供应商必须跑通一次正式 Vera Runtime 全链路。旧原型的连通性是辅助证据，不是 Vera 正式实现的验收证据。

### 人工验收

自动化检查通过后，用户在一个可恢复的真实项目副本中运行一次 Vera。用户检查并批准 Change Set、观察验证证据、执行回滚，并确认项目恢复。第一次人工验收不能使用有价值且不可轻易恢复的工作副本。

## 验收标准

只有以下条件全部获得证据支持，本规格对应的实现才算完成：

1. 可安装的 Python CLI 通过公共 Core Command/Event 契约完成已接受的运行生命周期。
2. 所有权威状态变化和副作用均由 Runtime 掌握，而不是模型、客户端或供应商 Adapter。
3. 拒绝 Change Set 不产生目标文件写入；提议后文件发生变化会使原审批不可用。
4. 确定性测试证明路径逃逸、受保护文件访问、禁止命令和无 Checkpoint 写入都会被拒绝。
5. 已批准的多文件 Change Set 创建 Checkpoint、写入精确的预期字节，并暴露 Runtime 生成的 Diff 和有序 Event。
6. 验证生成命令、超时、退出码、stdout、stderr、执行时长和终止状态证据。
7. 手动回滚逐字节恢复原始内容，并拒绝覆盖应用后的用户修改。
8. 自动化单元测试、集成测试、CLI 测试、临时仓库测试、静态分析和类型检查全部通过。
9. JSON 模式输出通过带版本号的 Event Model 校验，并且不包含任何已配置秘密值。
10. DeepSeek 或 GLM 至少完成一次可选的真实供应商端到端运行，随后完成可恢复真实项目副本的人工验收。

## 文档与决策后续

本规格是其增量的已接受产品规格和最高约束来源。功能实现开始前，实施计划必须：

- 创建并链接本规格的 Phase 1 任务记录；
- 把 Python Runtime 和依赖选择记录为架构决策；
- 把 Command/Event 边界和私有 Checkpoint 存储记录为架构决策；
- 调整 `docs/ROADMAP.md` 和 `docs/STATUS.md`，使 Phase 1 包含本规格定义的最小安全循环，并明确 Phase 2 负责扩展与加固；
- 在行为发生变化的同一个检查点内同步更新相关文档。

仅接受本规格不会添加任何功能实现或依赖清单。
