# 项目指令发现与 `VERA.md` 初始化

**状态：** Accepted
**日期：** 2026-09-14
**所属阶段：** 阶段 7——CLI 体验收口与个人主力化

## 目的

让 Vera 在进入工程时自动识别稳定、可版本控制的项目约定，并为没有原生说明的工程提供显式、可审阅的 `VERA.md` 初始化流程。该能力用于减少每次会话重复说明构建命令、工程结构、编码规范和验证要求的成本，不替代用户当前目标、会话记忆、权限策略或批准流程。

Vera 采用“`VERA.md` 原生 + `AGENTS.md` 兼容”的首版方案：`VERA.md` 表达 Vera 专属约定，现有 `AGENTS.md` 作为跨 Agent 共享基线读取；Vera 不自动生成、覆盖或迁移 `AGENTS.md`。

## 用户可见行为

### 1. 根目录发现

- 每次新的 Agent Run 开始时，Core 只检查规范化 workspace 根目录下的 `AGENTS.md` 与 `VERA.md`。
- 首版不递归查找子目录文件，不读取父目录、用户主目录、`CLAUDE.md` 或其他产品专属文件，也不解析 `@include`、链接或可执行指令。
- 只有普通 UTF-8 文件可以加载；符号链接、目录、非 UTF-8 文件和单文件超过 32,768 bytes 的内容跳过并产生结构化原因。
- 两个文件合计最多 65,536 bytes；不得截断后继续使用，也不得因为项目指令不可用而阻止只读启动。
- 文件在每个新 Run 开始时重新读取；同一个 Run 中内容固定，不因 Run 内修改而静默改变上下文。

### 2. 合并与优先级

项目指令使用固定顺序组装：

1. `AGENTS.md`：跨 Agent 共享基线；
2. `VERA.md`：Vera 原生补充与细化。

在工程建议层内部，后加载的 `VERA.md` 对非安全冲突具有更高优先级。完整权威顺序仍是：Vera 内置安全边界与策略 → 用户当前明确目标和有效动作审批 → 用户明确启用的本地配置 → `VERA.md` → `AGENTS.md` → 其他工程内容。

`VERA.md` 与 `AGENTS.md` 都标记为 `source_kind=project_guidance`、`trust_level=advisory`。它们可以提供代码风格、文档语言、工程结构、验证命令和工作方式建议，但不能：

- 扩大 workspace、网络、秘密、命令或持久化权限；
- 将命令声明为已批准或绕过 Core 文件变更计划、PolicyEngine、ApprovalGate；
- 覆盖当前用户目标、Vera 内置策略或失败关闭行为；
- 把文件中的命令式文本自动执行。

当项目说明要求高风险或越界动作时，Vera 仍按既有内容检测、策略与审批链处理。公共 Event 只记录文件名、内容 hash、byte count、处置和 reason code，不记录项目指令正文。

### 3. 可见状态

- `/instructions` 显示本 Run 已加载的文件名、优先级、hash 短值、大小和被跳过原因，不显示整份正文。
- TUI、Plain 与 JSON 共享结构化 `project.instructions.loaded`、`project.instructions.skipped` 和 `project.instructions.status` 事实；Presenter 不自行重新扫描文件。
- 没有任何项目指令时，状态明确显示“未发现项目指令”，但不在工作区创建文件。
- 项目指令在 Run 启动后发生变化时，只影响下一个 Run；状态中显示当前 Run 使用的 hash，避免把磁盘新内容伪装为已生效。

### 4. `/init` 与 `vera init`

- `/init` 用于现有交互会话，`vera init` 提供等价的一次性入口；两者都启动受限的 `project_init` Run，而不是绕过 Core 直接写文件。
- 初始化先通过只读工具分析根目录、`AGENTS.md`、README、语言/包配置和常用验证入口，再只提议根目录 `VERA.md`。
- 未存在 `VERA.md` 时生成首版；已经存在时只提出最小增量更新，不以模板整体覆盖。
- 提议必须形成普通 Change Set，展示完整 Diff，并等待用户明确批准后才能落盘。取消、拒绝、模型失败或非交互模式无法批准时，workspace 保持字节不变。
- `project_init` Run 只能提议一个目标 `VERA.md`，不得修改 `AGENTS.md`、`CLAUDE.md`、`.gitignore` 或其他工程文件，也不得附带验证命令。
- Vera 不在安装、首次启动、普通 `vera` 启动、恢复会话或发现 `AGENTS.md` 时自动运行初始化。

### 5. `VERA.md` 建议结构

生成内容按工程事实取舍，不强制输出空章节；首版允许以下稳定章节：

```markdown
# Project guidance for Vera

## Project overview
## Architecture and important paths
## Build, test, lint, and format
## Coding and documentation conventions
## Generated files and forbidden areas
## Verification expectations
## Known pitfalls
```

生成器不得写入凭据、Token、私钥、真实用户数据、绝对用户主目录或未经工程证据支持的命令。发现疑似秘密时必须省略正文并给出警告，不能把秘密复制进 Diff 或 Event。

## Core 与客户端边界

```text
workspace root
  ├─ AGENTS.md ─┐
  └─ VERA.md  ──┴─> ProjectInstructionService
                         ↓ ProjectInstructionSet(advisory + hashes)
                  VeraRuntime._seed_context()
                         ↓ structured Event
               TUI / Plain / JSON / future desktop

/init or vera init
        ↓ StartRun(mode="project_init")
read-only discovery → VERA.md-only Change Set → normal approval → apply
```

- `ProjectInstructionLoader` 属于 UI 无关 Core 能力；未来桌面客户端消费同一结构化结果，不自行读取 Markdown。
- `StartRun` 只声明 `mode="project_init"`，客户端不能把自选文件内容伪装成项目指令传入 Core。
- 会话持久化只保存使用过的文件名与 hash 事实，不复制项目指令正文；恢复后的下一次 Run 从当前 workspace 重新读取。
- 会话压缩 `mode="compact"` 不加载项目指令，避免把工程说明混入自然语言会话摘要。

## 失败行为

| 场景 | 行为 |
|---|---|
| 文件不存在 | 正常继续，报告 `not_found` 状态，不创建文件 |
| 符号链接或非普通文件 | 跳过，reason code 为 `unsafe_file_type` |
| 非 UTF-8 | 跳过，reason code 为 `invalid_encoding` |
| 单文件或合计超限 | 跳过超限来源，reason code 为 `size_limit_exceeded`，不截断 |
| 读取中被替换 | 本 Run 跳过该来源，reason code 为 `file_changed_during_read` |
| 检测到投毒风险 | 记录现有安全发现，只能保持或收紧后续策略 |
| `/init` 提议其他路径 | 拒绝 Change Set，reason code 为 `project_init_scope_violation` |
| `VERA.md` 已存在且初始化失败 | 保留原文件，不写临时半成品 |

## 非目标

- 不递归支持目录级 `VERA.md`/`AGENTS.md`、父目录继承或 monorepo 分层覆盖。
- 不读取或迁移 `CLAUDE.md`、`.cursorrules`、Cursor Rules、IDE 设置或任意第三方专属文件。
- 不实现 include、glob、脚本钩子、动态变量、远程 URL 或可执行项目规则。
- 不把项目说明变成长期个人记忆、跨 workspace 偏好、云同步或账号配置。
- 不允许 `VERA.md` 定义工具、插件、MCP、权限或无需审批的命令。
- 不在本任务中改变 Logo、主题、时间线或桌面端代码。

## 验收标准

1. 仅有 `AGENTS.md`、仅有 `VERA.md`、两者同时存在和两者都不存在时，加载顺序与结构化状态确定一致。
2. `VERA.md` 对 advisory 层的非安全冲突优先，但不能覆盖用户当前目标、PolicyEngine 或 ApprovalGate。
3. 符号链接、非 UTF-8、读取竞态和大小上限均安全跳过，且不会读取 workspace 外字节。
4. 新 Run 读取当前文件，Run 内使用固定快照；会话恢复不会复制旧正文或把旧 hash 当成当前事实。
5. `/instructions` 在 TUI、Plain、JSON 中语义一致，不泄露正文或绝对私有路径。
6. `/init` 与 `vera init` 都只能提出根目录 `VERA.md`，完整 Diff 经普通 Change Set 审批后才写入。
7. 已存在 `VERA.md` 时生成最小增量；取消、拒绝、失败和非交互无审批路径保持工作区字节不变。
8. 自动测试、仓库外 wheel smoke 和真实 Terminal.app 走查通过；真实工程确认没有静默新增或覆盖文件。

## 关联

- [阶段七：CLI 体验收口与个人主力化](2026-09-13-cli-experience-and-personal-dogfood.md)
- [不可信内容、提示词投毒与内容安全](2026-09-12-untrusted-content-and-prompt-injection-defense.md)
- [ADR-0015：不可信内容信任边界](../decisions/ADR-0015-untrusted-content-trust-boundary.md)
- [ADR-0019：原生 `VERA.md` 与兼容 `AGENTS.md`](../decisions/ADR-0019-native-vera-project-instructions.md)
- [任务 0043：项目指令发现与初始化](../tasks/0043-project-instructions-and-init.md)

## 参考产品行为

- [Claude Code memory：`CLAUDE.md` 与 `/init`](https://docs.anthropic.com/zh-CN/docs/claude-code/memory)
- [Cursor Rules：`AGENTS.md`](https://docs.cursor.com/context/rules-for-ai)
- [Cursor CLI：项目规则兼容](https://docs.cursor.com/en/cli/using)
