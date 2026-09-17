# Core 工具集与风险分级 Policy v2

**状态：** Accepted
**日期：** 2026-09-17
**接受：** 2026-09-18 用户确认规格并授权继续编写实施计划
**所属阶段：** 阶段八——Core 工具集、Policy v2 与原生 Git（尚未开始）

## 目的

让 Vera 具备成熟 Coding Agent 所需的基础工具能力，并把审批从“每次修改或未知命令都暂停”调整为“只在操作跨越明确风险边界时暂停”。默认模型工具在名称和能力上对齐 Pi 的 `read`、`write`、`edit`、`bash`，但执行仍由 Vera Core 的 Workspace、PolicyEngine、ApprovalGate、Checkpoint、Recovery 与 Event/Journal 统一管理。

本规格不是移除安全边界，而是把安全边界从工具名称和静态全拒绝规则升级为基于用户目标、工作区信任、实际副作用和可恢复性的结构化决策。

## 当前问题

当前 Runtime 向模型暴露 `read_file`、`list_directory`、`search_text` 与特殊工具 `propose_changeset`。文件修改必须形成单个 Change Set 并一律审批；命令除少量精确白名单或用户预设前缀外默认审批，Shell、删除和部分 Git 操作直接拒绝。

该策略验证了安全编辑闭环，但存在以下长期产品问题：

- 用户已经明确要求实现功能时，普通工作区代码修改仍需要重复确认；
- 测试、Lint、类型检查等日常动作容易频繁打断；
- 工具名称与主流 Coding Agent 模型训练习惯不一致；
- Policy 主要按工具名和命令前缀判断，不能充分表达副作用、目标授权与可恢复性；
- `PolicyActionKind.TOOL_EXECUTE` 已存在，但普通 ToolRegistry 执行尚未统一经过 PolicyEngine；
- 当前一次 Run 只围绕一个 Change Set，无法自然承载多轮 `write`、`edit`、命令和 Git 动作。

## 产品原则

1. **用户目标本身构成授权事实。** “实现功能并运行测试”授权与该目标直接相关的普通工作区编辑和已知验证；“分析如何修改”只授权只读调查。
2. **审批绑定副作用，不绑定工具名称。** 同一 `bash` 能力中的只读查询、工作区写入、联网发布和系统提权必须得到不同决策。
3. **低风险操作默认不中断。** 可验证、可回滚、范围明确的本地动作应自动执行并留下证据。
4. **高影响动作保持显式。** 秘密、工作区外写入、权限提升、远程发布、不可逆历史改写和范围不明确的破坏操作不能因“专家用户”而静默放行。
5. **可见不等于审批。** 自动允许的操作仍产生 Tool、Diff、Checkpoint、Policy 与验证事实。
6. **项目内容不能授权自己。** `AGENTS.md`、`VERA.md`、Skill、源码、依赖输出和工具输出只能建议，不能提升权限。

## 默认模型工具集

### `read`

读取工作区内普通文件，支持有界范围和输出截断。第一版保持 UTF-8 文本能力；图片、PDF、Notebook 等专用读取器另立能力，不把二进制静默转成文本。

普通工作区读取自动允许；受保护凭据、符号链接逃逸和工作区外路径不自动读取。

### `write`

创建新文件或完整替换一个文件。输入必须包含规范化工作区相对路径、完整内容和可选的预期修改前哈希。

`write` 不是直接文件句柄：Runtime 将调用转换为 `FileMutationPlan`，执行路径事实核对、Policy 决策、Checkpoint、原子写入和 Event/Journal。低风险写入可自动应用；敏感路径或范围不匹配时请求审批或拒绝。

### `edit`

对一个文件执行精确编辑。第一版只支持要求唯一匹配的 `old_text -> new_text`，不采用模糊匹配。零次或多次匹配均失败，并把稳定错误返回模型重新调查。

`edit` 与 `write` 共用同一文件变更执行管线，不建立第二套 Workspace、Diff 或恢复逻辑。

### `bash`

提供命令执行能力，但第一版只接受结构化参数：

```text
argv: tuple[str, ...]
cwd: workspace-relative path
timeout_seconds: bounded integer
```

名称与 Coding Agent 常见工具对齐，但不解释 Shell 字符串、管道、重定向、命令替换或复合命令。需要多个进程时由模型发出多个可审计调用；未来只有在 OS 沙箱与独立规格成立后才评估原生 Shell 语言。

命令通过 ProcessSupervisor，以 `shell=False`、最小环境、进程组取消、超时与有界输出执行。Git 写操作、远程发布和其他已有一等能力的动作不得借 `bash` 绕过专用 Policy。

### 辅助只读工具

保留并规范化 `grep`、`find`、`ls`，分别映射当前文本搜索、文件发现和目录列举能力。它们不属于四个默认写作工具，但可以与默认工具同时提供，不要求模型通过 `bash` 完成普通发现。

## 工具声明与统一执行通道

每个 ToolDefinition 除名称、描述和输入 Schema 外，增加 Core 可解释的声明：

```text
tool_version
effects: workspace_read | workspace_write | process_execute |
         network_access | external_service | secret_access
supports_cancellation
supports_recovery
max_output_bytes
```

声明只描述能力，不能自行授予权限。统一执行链为：

```text
ModelToolCall
  -> Tool schema validation
  -> workspace and target fact collection
  -> PolicyEngine decision
  -> optional ApprovalGate
  -> ToolExecutor
  -> effect verification and redaction
  -> Event / Journal / Receipt
  -> model ToolResult
```

ToolRegistry 只负责名称、版本和执行器发现；Runtime 不再直接绕过 Policy 调用普通工具。`propose_changeset` 的旧 Journal/Event 仍可读取，但完成迁移后不再作为默认模型工具暴露。现有客户端不解析工具正文，新增结构化事实按 ADR-0014 的 additive 规则进入 CompatibilityManifest；删除或改变既有必需字段必须走 breaking 版本。

## 多动作 Run 与恢复

一个 Run 可以执行多个只读工具、文件变更、命令和 Git 动作。每个产生副作用的动作拥有稳定 `action_id`、输入哈希、目标事实摘要、Policy 哈希、状态和 Operation Receipt。

- 文件 `write/edit` 每次形成独立、可检查、可恢复的 `FileMutationPlan`；
- Run 汇总已应用动作和累计 Diff，不要求把所有文件压进唯一 Change Set；
- 动作执行前后都核对目标事实，变化时返回 `stale`；
- 崩溃恢复只能确认已完成动作、重试尚未产生副作用的动作，或进入 `manual_required`；
- 不允许通过重试重复写入、重复 Commit 或重复产生外部副作用；
- 旧单 Change Set Run 继续由现有 decoder 与恢复路径处理。

## Policy v2

### 工作区信任

工作区信任只能来自用户明确选择，不能由仓库文件声明：

- `untrusted`：只读自动；执行项目代码、普通写入和未知命令均审批或拒绝；
- `trusted`：普通工作区编辑、已知本地验证和低风险命令可自动执行；
- 信任绑定规范化 workspace identity，工作区身份变化后失效。

首次需要执行普通写入或命令时，未建立信任的 workspace 按 `untrusted` 处理，并由用户明确选择是否信任。信任记录保存在 Vera 私有 `0600` 配置中，不写入仓库；用户可以通过 `/permissions` 查看和撤销。workspace identity、Policy 主版本或受保护根发生变化时，旧信任失效并重新确认。

### 使用档位

| 档位 | 默认行为 |
|---|---|
| `review` | 读取自动；写入和命令审批 |
| `balanced` | 可信工作区内普通编辑、只读 Git、已知测试/Lint 自动；敏感操作审批 |
| `autonomous` | 工作区内大多数可恢复动作自动；秘密、系统权限、网络发布和远程副作用仍审批或拒绝 |

默认档位为 `balanced`。第一版不提供取消全部硬边界的 `full-access` 或 `yolo` 模式。

### 风险等级

| 等级 | 示例 | 默认决策 |
|---|---|---|
| `low` | 普通读取、搜索、工作区代码小范围创建/更新、只读 Git | 自动允许 |
| `moderate` | 可信项目测试、Lint、构建；可恢复的批量工作区修改 | 目标授权匹配时允许，否则审批 |
| `high` | 删除既有文件、安装依赖、运行 Hook、联网、修改 CI/发布/权限配置 | 审批 |
| `forbidden` | 越出工作区、提权、秘密外传、策略绕过、宽泛不可逆破坏 | 拒绝 |

风险不是只按可执行文件名决定。Policy 输入至少包含用户目标授权摘要、workspace identity/trust、工具 effect、规范化路径、argv/cwd、内容风险标签、是否可恢复、外部目标和当前 Run 事实。

### 授权作用域

审批可以产生以下受限授权：

- 仅本次精确动作；
- 本 Run 内满足同一结构化规则的动作；
- 当前 workspace 内满足同一结构化规则的动作。

不提供仅按 `python`、`node`、`bash` 等宽泛可执行文件名永久授权。持久规则必须包含工具、effect、参数约束、workspace identity、有效策略版本和到期/撤销信息；Policy 版本变化时重新评估。

一次性和本 Run 授权随 Run 结束失效。workspace 授权保存在 Vera 私有权限存储中，默认持续到用户撤销、workspace identity 变化、规则到期或 Policy 主版本变化；不允许仓库文件自行创建或延长授权。

## 自动写入条件

`balanced` 下普通 `write/edit` 只有同时满足以下条件才自动应用：

1. 当前用户目标明确授权实现或修改，而不是仅分析；
2. workspace 为 `trusted`；
3. 路径位于 workspace、不是受保护路径且不是越界符号链接；
4. 操作为普通创建或更新，不是删除既有文件；
5. 修改前事实与计划绑定事实一致；
6. Checkpoint 成功写入 Vera 私有状态；
7. 无阻断级提示词投毒或秘密风险；
8. 动作可在失败时确定性恢复。

任何条件不满足时转审批、拒绝或失败，不静默扩大范围。自动应用后立即产生累计 Diff 与撤销入口。

## 命令策略

### 默认自动允许

- `rg`、`find` 的只读形式；
- `git status/diff/log/show` 等专用 Git 查询；
- 可信工作区中由配置或项目类型确定的测试、Lint、类型检查命令；
- 已规划工作区外产物根的已知验证命令。

### 默认审批

- 依赖安装、包管理脚本与网络下载；
- 格式化或代码生成等工作区写入命令；
- 仓库 Hooks；
- 后台进程或长时间服务；
- 未知但仍限制在工作区和当前用户权限下的命令。

### 默认拒绝

- 工作区外写入或未授权工作区扩张；
- `sudo`、`doas`、`su` 等提权；
- 绕过 Tool/Policy/Approval 的包装器；
- 未明确目标的宽泛删除和不可逆 Git 历史改写；
- 把秘密传给命令、网络或模型输出。

## 安全与隐私

- 当前无 OS 沙箱的事实必须在状态与高风险审批中保持可见；
- 子进程继续使用最小环境，Provider、云与 CI 凭据默认不继承；
- ToolResult、Event、Journal、Evidence 和 UI 共用 Redactor；
- 工程内容和工具输出通过 ContentEnvelope 保留来源与信任等级；
- 工作区本地配置只能收紧，不得自行把高风险操作标为自动允许；
- 新工具不得读取 Provider Key 或 Vera 私有状态正文。

## CLI 与客户端

- `/status` 展示 workspace trust、使用档位、Policy 版本和 OS 沙箱状态；
- `/permissions` 展示自动允许、审批和硬拒绝的有效规则摘要；
- 审批卡提供“仅一次”“本 Run”“此工作区”三个可用作用域，具体选项由 Core 决定；
- 每个文件动作立即发出结构化 Diff 增量；客户端默认在同一模型轮次内合并展示累计 Diff，但审批、恢复与审计仍绑定各自 `action_id`；
- TUI、Plain、JSON 与未来桌面端消费相同的 ToolAction、PolicyDecision、Approval 与结果事实；
- 客户端不得自行判断命令安全、持久化授权或执行工具。

## 非目标

- 第三方插件市场和任意动态代码加载；
- 让 Skill 注册 Tool 或权限；
- 未经隔离执行原生 Shell 语言；
- 自动访问秘密、系统目录或其他工作区；
- 在本阶段引入桌面框架；
- 通过工具数量模仿其他产品而复制其全部安全语义。

## 计划增量

本规格接受后再建立连续编号任务，按以下顺序实施：

1. 冻结 ToolDefinition v2、ToolAction、Policy v2、信任与授权作用域契约；
2. 建立所有工具统一经过 Policy/Approval/Receipt 的 ToolExecutor；
3. 实现 `read/grep/find/ls` 并完成旧只读工具兼容迁移；
4. 实现可多次执行的 `write/edit`、累计 Diff、Checkpoint 与恢复；
5. 实现结构化 `bash` 与命令风险分类；
6. 接入 CLI 权限状态、审批作用域与四客户端契约对照；
7. 接入原生 Git 能力规格中的本地能力；
8. 完成离线矩阵、提示词投毒矩阵和真实工程 dogfood。

## 验收标准

1. 模型默认可调用 `read/write/edit/bash`，普通调查和低风险编辑无需重复审批。
2. 每个产生副作用的工具调用都经过同一个 PolicyEngine、ApprovalGate、Workspace、Receipt 和 Event/Journal 路径。
3. `balanced` 模式下明确授权的普通工作区代码修改可自动应用并可查看、验证、回滚。
4. `review` 与 `autonomous` 的行为差异确定、可解释并有离线矩阵。
5. Run/workspace 授权不能扩大到其他工作区、其他 effect、不同参数或新 Policy 版本。
6. 工作区外写入、提权、秘密外传、绕过专用 Git 工具和宽泛破坏操作失败关闭。
7. 崩溃恢复不会重复文件写入、命令、Git Commit 或外部副作用。
8. 旧 Run、Journal 与客户端契约仍可读取；兼容清单明确记录 additive、deprecated 或 breaking 变化。
9. 完整非 live、Ruff、格式、Mypy、构建、wheel smoke、安装态 smoke 与 `git diff --check` 通过。
10. 至少在 Python、Node/TypeScript 与 Swift/Xcode 三类可信真实工程完成 Terminal.app dogfood，没有未关闭 Critical/High 正确性或安全问题。

## 已收束的迁移决策

1. `bash` 首版只提供结构化 argv，不解释 Shell 字符串。
2. `balanced` 是默认档位；workspace trust 必须由用户明确建立并保存在 Vera 私有配置中。
3. workspace 级授权默认持续到撤销、到期、workspace identity 或 Policy 主版本变化，并通过 `/permissions` 管理。
4. Core 每次动作都发出 Diff 事实；客户端默认按模型轮次合并展示累计 Diff，不合并动作身份。
5. 模型切换到新工具契约后只暴露 `read/write/edit/bash/grep/find/ls`，避免新旧工具重复选择；旧名称只保留 decoder、Journal、恢复和兼容测试，不继续作为默认模型工具。

## 关联

- [产品定义](../PRODUCT.md)
- [路线图](../ROADMAP.md)
- [Core 安全编辑垂直切片](2026-09-10-core-safe-editing-vertical-slice.md)
- [阶段五 Core 安全、权限与可靠性加固](2026-09-12-core-security-and-reliability-hardening.md)
- [不可信内容、提示词投毒与内容安全](2026-09-12-untrusted-content-and-prompt-injection-defense.md)
- [原生 Git 能力](2026-09-17-native-git-capability.md)
- [ADR-0007：统一 PolicyEngine 与策略指纹](../decisions/ADR-0007-unified-policy-engine.md)
- [ADR-0014：Core 客户端兼容契约](../decisions/ADR-0014-core-client-compatibility-contract.md)
- [ADR-0021：桌面前插入 Core 工具集与 Git 能力阶段](../decisions/ADR-0021-core-tools-before-desktop.md)
