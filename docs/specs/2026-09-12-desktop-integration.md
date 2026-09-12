# Vera 阶段七：桌面集成

**状态：** Accepted
**日期：** 2026-09-12
**规划性质：** 已接受的未来实施基线；阶段五、阶段六完成前不授权 Spike 或产品实现

## 结论摘要

阶段七不应把 CLI 包进窗口，也不应让桌面端解析 CLI 文本。建议的稳定边界是：

```text
本地打包 UI（低信任）
    ↓ 窄化、类型化的桌面桥
桌面可信后端（窗口、原生对话框、CoreSupervisor）
    ↓ 有界、版本化、双向结构化协议
独立 Python Vera Core sidecar（Runtime/Policy/Workspace/Provider/Recovery 权威）
    ↓ 结构化 argv、shell=False、Core 审批和 ProcessSupervisor
工具子进程（当前系统用户权限；默认没有 OS 沙箱）
```

桌面壳已由用户明确选定为 Wails，见 ADR-0015。任务 0031 不再通过 Wails、Tauri、Electron 横向排名选择框架，而是在相同 Core、无框架前端夹具、Intel macOS release artifact 和固定验收脚本下验证 Wails。选择不等于免验证：Wails 若不能通过 Core sidecar、权限收窄、进程清理、打包签名和原子升级硬门禁，阶段七必须暂停并重新请求用户决策。

## 当前事实与规划基线

本规格接受时的文件基线为 `ccf5e409f138b21046e46bea95425767ca1bb9bc`：阶段五任务 0020、0021 已合并，任务 0022 正由 Cursor 在独立工作树实施且不包含在本分支。阶段七执行前仍必须基于届时最终干净 `main` 重新核对阶段五、阶段六的冻结契约。

当前已验证：

- Python 3.12 Core、`VeraRuntime`、`PolicyEngine`、Workspace、审批、Checkpoint、恢复和 Event Journal 是业务权威。
- TUI、Plain 和 JSON 通过 `SessionController` 发送结构化 `SessionAction`，消费 `EventEnvelope | StreamFrame`。
- `EventEnvelope` 是持久事实，`StreamFrame` 只是可丢弃、可合并的进程内流式显示。
- `vera --json` 是现有 CLI Session 协议，但尚未具备桌面 sidecar 所需的独立握手、进程实例、生命周期、背压和重连契约。
- 任务 0024 计划产生 `ADR-0013` 和 Core 客户端兼容性清单；阶段七必须消费它，不能提前猜测最终字段。

当前文档存在一处需要区分的语义：已合并的阶段六门禁禁止用户封存前“开始阶段七”；用户本轮明确授权的是提前完成并接受阶段七规划，不授权技术测量或实现。按权威顺序，本规格采用：

- 允许在独立规划分支接受规格与 ADR，并保留未来任务为 `Planned`；
- 阶段七状态继续保持 `Not started`；
- 不运行 Wails、Python freezer、签名或桌面 UI Spike；
- 不写桌面产品代码；
- 本规格已获用户审阅并改为 `Accepted`；`Accepted` 只表示设计基线获准，不会打开执行门禁。任何测量、Spike 或实现仍必须等待阶段五、阶段六完成及用户原文确认「CLI 版本达到预期，可以封存」。

## 目标

- 为桌面壳与 Python Vera Core 建立可版本化、可测量、可恢复的进程边界。
- 保持 Core 对 Workspace、权限、审批、Diff、验证、恢复与回滚的唯一权威。
- 让桌面应用能明确展示启动、运行、等待审批、取消、崩溃、重启和恢复状态。
- 让 Provider Key、本地配置、私有状态、日志和崩溃证据各有明确保管者与最小披露面。
- 用固定夹具验证 Wails 的发布可行性，并把 UI 技术选择与桌面壳选择分开。
- 在 Intel macOS 上形成真实证据，同时避免据此宣称 Apple Silicon、Windows 或 Linux 已受支持。
- 形成可由 Cursor 严格顺序执行、每项可独立验证和提交的任务。

## 非目标

- 不引入 Multi-Agent、复杂 RAG、向量数据库或插件市场。
- 不引入账号、计费、云端编辑、后台云服务或自动上传遥测。
- 不让桌面 Renderer 直接调用 Provider、读写 Workspace、执行命令或读取 Vera 私有状态。
- 不把 WebView/Chromium Renderer sandbox、macOS Hardened Runtime 或 Vera Workspace 策略误称为命令的 OS 沙箱。
- 不在首版嵌入通用终端、PTY、任意 Shell、`!shell` 或全局自动批准。
- 不支持后台常驻 Agent、多窗口并行 Workspace 或退出后继续执行。
- 不把 Intel 开发机的一次成功推断为全部平台支持。
- 不在本规格中锁定前端框架、Python 打包器、更新服务或发布渠道；桌面壳已由 ADR-0015 锁定为 Wails。

## 阶段入口门禁

只有以下事实全部有书面证据，阶段七才可从 `Not started` 进入执行：

1. 阶段五为 `Complete`，没有未关闭的 Critical/High，任务 0024 的兼容性清单与 `docs/protocol.md` 已合并。
2. 阶段六为 `Complete`，任务 0029 的自动与人工验收均通过。
3. 用户原文确认「CLI 版本达到预期，可以封存」。
4. `main` 干净，阶段五、阶段六代码和文档已合并；阶段七分支先基于最终 `main` 重新核对。
5. 本规格、进程边界 ADR 和 Wails 选择 ADR 均为 `Accepted`。
6. Spike 只使用 Fake Model、临时 Workspace、隔离私有状态和无真实 Key 环境。

任一门禁缺失时，只能继续审阅规划；不得下载或引入桌面框架依赖，不得运行桌面测量。

## 总体结构

### Renderer

Renderer 只负责本地打包 UI、用户输入和 View Model。它必须：

- 只加载随应用签名打包的本地资源；默认禁用任意远程页面、动态代码和不受控导航。
- 只调用显式列入允许表的桌面桥方法。
- 不获得 Node/Go/Rust 通用文件系统、进程、Shell、Keychain 或网络能力。
- 不持有恢复判断、审批是否有效、命令是否允许或文件是否可写等业务规则。
- 不缓存 Provider Key；密码输入提交后立即清空，后台永不返回已保存明文。

### 桌面可信后端

桌面可信后端属于选定壳的原生部分，职责限于：

- 窗口、菜单、目录选择器和必要的 OS 集成；
- 从应用包内固定路径启动、监督和停止 Python Core；
- 校验 Renderer 调用来源、方法、参数、大小和当前状态；
- 在 Core 与 Renderer 之间转发结构化消息并维护有界重附着缓冲；
- 执行应用包签名/升级相关的壳层动作；
- 不解释 Event 业务语义，不直接写 Workspace，不替 Core 批准命令。

所有暴露给 Renderer 的方法都必须是窄化业务意图，例如 `choose_workspace`、`attach_ui`、`send_session_action`、`request_shutdown`。禁止暴露 `spawn(command)`、`read_file(path)`、`write_file(path, data)` 或任意 shell 插件。

### Python Core sidecar

Python Core 作为独立 sidecar 进程：

- 由桌面可信后端唯一拥有；首版每个应用实例最多一个 Core、一个打开的 Workspace、一个会话。
- 使用打包内绝对路径和固定参数启动，不经 `PATH` 搜索，不经 Shell。
- stdout 仅承载结构化协议；stderr 只允许有界、脱敏的进程诊断。
- 继续由 `SessionController/VeraRuntime` 驱动业务，不复制 Runtime。
- 读取/写入 Vera 私有状态，调用 Provider，并监督经过 Core 审批的工具子进程。
- 收到 stdin EOF、父进程死亡或显式 shutdown 后停止；不得变成后台守护进程。

### 工具子进程

工具子进程仍由 Core 的 `PolicyEngine`、审批和 `ProcessSupervisor` 控制：

- 结构化 argv、`shell=False`、cwd 位于已批准 Workspace；
- 最小环境 allowlist，不继承 Provider Key 或桌面签名凭据；
- 有界 stdout/stderr、超时、取消、TERM → KILL 和进程组清理；
- 在默认分发模型下以当前系统用户权限执行，不是 OS 隔离容器。

## 需要决策的问题

| 编号 | 问题 | 已接受方案或决策路径 | 决策时点 |
|---|---|---|---|
| D7-01 | Python Core 是否独立进程 | 独立 sidecar，不嵌入 Go/Rust/Node 进程 | 接受进程 ADR |
| D7-02 | 传输方式 | 首版使用 framed stdio，不监听 TCP | 接受进程 ADR |
| D7-03 | 桌面公共动作层 | 复用阶段六冻结后的结构化 SessionAction/Core 结果，不发送 Slash 文本 | 任务 0030 |
| D7-04 | Renderer 重连 | 重附着到仍存活的可信后端；Core 崩溃则新进程只读恢复 | 任务 0030/0032 |
| D7-05 | 桌面壳 | Wails 已由用户选定；任务 0031 只验证硬门禁，不再横向选型 | 任务 0031、ADR-0015 |
| D7-06 | UI 框架 | Vue 3 与 React 独立浏览器夹具测量；不与壳绑定 | 任务 0031、必要时 ADR-0016 |
| D7-07 | Python 打包 | 优先测 PyInstaller onedir，再测一个可维护备选；禁用临时解压型 onefile 作为默认 | 任务 0031 |
| D7-08 | Provider Key | Core 侧 `SecretStore` 抽象接 OS credential store；没有安全存储时失败关闭 | 任务 0035 |
| D7-09 | macOS 分发 | 先测 Developer ID + Hardened Runtime 直接分发；App Sandbox/Mac App Store 可行性单独记录 | 任务 0031/0036 |
| D7-10 | 更新 | 壳、Core、资源和迁移清单作为一个签名原子版本升级 | 任务 0036 |
| D7-11 | 嵌入终端 | 首版不做 PTY/通用终端，只展示 Core 结构化命令与输出 | 新需求触发新 ADR |
| D7-12 | 平台范围 | Intel macOS 只形成已测证据；其他平台保持 `Not tested` | 任务 0037 |

## 桌面 Core 结构化协议

### 协议与业务契约分层

进程协议只解决“消息如何安全跨进程、如何协商版本、如何关联请求和恢复连接”。它不得重新定义 Runtime 业务。

- 外层：`DesktopEnvelope`，负责进程协议。
- 内层：阶段五冻结的 `SessionAction`、`EventEnvelope`、`StreamFrame` 和结构化查询结果。
- 持久状态：仍由 Journal/Snapshot/Checkpoint/OperationReceipt 决定。
- UI：只消费结构化 View Model，不解析 CLI、Presenter 或异常文本。

`vera --json` 的 Pydantic model、Fixture 和语义可复用，但桌面应用不得启动人类 CLI 模式，也不得把 NDJSON CLI 行当成桌面生命周期 API。

### 帧格式

协议 v1 建议使用 UTF-8 JSON 的长度前缀帧：

```text
Content-Length: <十进制 UTF-8 字节数>\r\n
Content-Type: application/json; charset=utf-8\r\n
\r\n
<严格 JSON object 字节>
```

规则：

- 单帧上限 8 MiB；Header 上限 8 KiB；超过限制时在分配完整 payload 前拒绝并关闭连接。
- 禁止 NaN/Infinity、重复 JSON key、非对象顶层、负长度和未知 Content-Type。
- v1 不压缩、不传二进制；Diff、日志和超大输出必须由 Core 结构化分页或截断，不能扩大无限帧。
- stdout 不得混入日志、traceback、提示词、ANSI 或 CLI 文案。
- stderr 每行脱敏，单行与总缓冲均有上限；Renderer 默认不显示原始 stderr。

### Envelope

```json
{
  "protocol": {"major": 1, "minor": 0},
  "process_instance_id": "core_...",
  "message_id": "msg_...",
  "in_reply_to": null,
  "transport_sequence": 1,
  "kind": "request",
  "type": "session.action",
  "session_id": "session_...",
  "operation_id": "op_...",
  "payload": {}
}
```

- `message_id` 在当前 Core 进程实例内唯一。
- Response 使用 `in_reply_to` 关联请求。
- Core 发出的消息拥有当前进程内单调 `transport_sequence`；它不替代 run 内 `EventEnvelope.sequence`。
- 会产生副作用或改变会话状态的请求必须带 `operation_id`。同一输入重放返回原回执；相同 ID 不同输入失败关闭。
- 未知操作结果不能由桌面端自动重发。Core 崩溃后先查询持久 OperationReceipt/Run 恢复事实。

### 最小消息集合

| 消息 | 方向 | 性质 |
|---|---|---|
| `client.hello` | Backend → Core | 声明协议区间、App 版本、平台、期望能力 |
| `server.hello` | Core → Backend | 选择版本、返回 Core 版本、兼容清单 hash、能力 |
| `session.open` | Backend → Core | 打开用户刚选择且经 Core 核对的 Workspace |
| `session.action` | Backend → Core | 承载结构化 prompt、审批、取消、Diff/状态/恢复动作 |
| `runtime.output` | Core → Backend | 承载 `EventEnvelope` 或 `StreamFrame` |
| `session.snapshot` | Backend ↔ Core | 只读重附着事实，不执行恢复 |
| `run.events.page` | Backend ↔ Core | 按 run/sequence 读取持久 Event 页 |
| `core.health` | Backend ↔ Core | I/O loop 处理的无副作用健康检查 |
| `core.shutdown` | Backend → Core | 有界优雅停止 |
| `protocol.error` | 双向 | 稳定错误 code、影响和可行动建议 |

如果阶段六最终没有为按钮动作提供结构化 `SessionAction`，任务 0030 必须先扩展契约与 round-trip 测试；桌面端禁止拼接 `/diff`、`/rollback` 等 Slash 字符串。

### 版本协商

- `protocol.major` 无交集：拒绝打开 Session，显示“应用组件版本不兼容”，不尝试降级执行。
- major 相同：选择双方支持的最高 minor；发送方只能使用握手明确协商的 capability。
- 嵌入业务对象的 `schema_version` 与协议版本独立，必须出现在任务 0024 的兼容清单中。
- 任何字段含义变化、审批/恢复语义变化或副作用边界变化都属于 breaking change，不能伪装成新增 optional 字段。
- 更新包必须声明 App、Core、协议、State Codec 的兼容矩阵；启动时 hash 不匹配即失败关闭。

## 生命周期与重连

### 状态机

```text
stopped → starting → handshaking → ready → session_open
   ↑          ↓            ↓          ↓
   └──── stopping ← draining/cancelling
                ↘ crashed → recovery_scan → ready 或 blocked
```

### 启动

1. 桌面后端验证 sidecar 位于签名应用包内，并以绝对路径、固定参数、最小环境启动。
2. 10 秒内完成握手；期间 UI 可显示启动状态，但不得接受会产生副作用的操作。
3. 用户通过原生目录选择器选择 Workspace；路径选择本身不等于读写或命令批准。
4. Core 规范化路径、计算 Workspace identity、读取权限/Git/恢复事实并返回结构化快照。
5. 发现恢复项时只展示，不自动 resume、rollback、调用 Provider 或执行验证。

### 正常停止

- 默认关闭按钮在存在 active run 或 pending approval 时显示“留在 Vera”“取消任务并退出”；默认焦点为留在 Vera。
- “取消任务并退出”必须先发送一次结构化 cancel，等待持久终态，再关闭 Session 和 Core。
- idle Core 在 `core.shutdown` 后 10 秒仍未退出时发送 TERM；再等 3 秒后 KILL，并记录脱敏生命周期事实。
- 首版不提供“关闭窗口后后台继续”。

### Renderer 重载或崩溃

- Core 与桌面后端仍存活时，新的 Renderer 通过 `attach_ui(last_transport_sequence)` 重附着。
- 后端只缓存有界的最近消息；持久 Event 不得因 Renderer 缺席而丢失，瞬时 `StreamFrame` 可以合并或丢弃。
- 缓冲存在缺口时，UI 请求 `session.snapshot` 与 `run.events.page` 重建权威状态，不猜测、不重发旧动作。

### Core 崩溃或失联

- Core 进程退出时立即标记 `crashed`，展示退出 code/signal 和“副作用状态待核对”，不把最后一条流式文本当作完成。
- 后端可自动启动一次新 Core，但新实例只执行握手和只读恢复扫描，不自动重放 prompt、审批、写入、验证或回滚。
- 5 分钟内发生 3 次异常退出后进入 `blocked`，停止自动重启，提供诊断文件预览和手工重试。
- 健康检查 15 秒无响应只标记 `unresponsive`；由于进程可能正处于系统调用或副作用边界，不自动 kill。用户可等待、请求取消或明确强制重启。

### 桌面后端崩溃

- Core 监听 stdin EOF 与父进程存活租约；后端死亡后不得长期孤儿运行。
- POSIX 必须验证进程组、关闭继承 fd 和父 PID/pipe 监测；Windows 必须验证 Job Object 或等价 kill-on-close。
- 下次启动创建全新 Core，再根据持久事实分类恢复。

## Workspace、权限与主要界面

### Workspace 选择

- 使用原生目录选择器，不接受 Renderer 自由输入任意路径调用文件 API。
- 首屏展示用户选择值、Core 规范化值、Git 分支/clean 状态、可读/可写事实、Workspace identity 和“当前用户权限/OS 沙箱状态”。
- 选择 Home、文件系统根、符号链接异常、设备/网络卷或过大目录时展示风险或拒绝；最终判断来自 Core。
- 切换 Workspace 前必须结束当前 run、处理未决审批并关闭当前 Session；首版不并行打开多个 Workspace。
- 不自动恢复上次 Workspace 或执行上次任务。若保存最近路径，只能保存在私有状态并允许用户清除。

### 时间线和输入

- UI 只渲染结构化 `RuntimeOutput` 和阶段六冻结的 View Model。
- 用户消息和最终回答展开；普通工具/日志折叠；Diff、审批、失败、恢复和回滚默认突出。
- `StreamFrame` 显示为未持久完成的临时文本；只有最终 `assistant.message` 可作为完成事实。
- 一个 Session 同时最多一个 active run；未决审批期间禁止新任务。

### 权限与审批

- 权限面板读取 `PolicyEngine` 快照，展示允许、需批准、禁止、Workspace、策略 hash 和“不是 OS 沙箱”。
- 审批卡展示动作、目标、风险、结构化 argv 或权威 Diff、Workspace identity、事实 hash、policy hash 和批准后的实际效果。
- 默认按钮是取消/拒绝；Approve 不使用易误触单键。
- 任何 hash、Workspace 或策略变化都显示过期并要求重新生成，Renderer 不得自行继续。

### Diff 与验证

- Diff 由 Core 的结构化 Change Set/查询结果提供；Renderer 不直接重新读文件生成“自己的 Diff”作为审批依据。
- 大 Diff 使用文件列表、hunk/页索引和明确截断标记；复制纯文本不改变审批对象。
- 验证卡展示 argv、cwd、风险、批准状态、退出码、耗时和截断事实。
- 展示命令输出不等于提供交互终端；首版不接 PTY stdin。

### 恢复与回滚

- 启动恢复中心展示 `resumable_approval`、`resumable_verification`、`safe_to_abandon`、`recoverable_partial_apply`、`manual_required`、`legacy_not_resumable`。
- Resume、恢复计划、Rollback 和 Abandon 都发送既有结构化命令并消费 Event。
- `manual_required` 不提供伪装成安全的一键修复。
- 回滚冲突优先保护用户在 Vera 之后的修改。

## Provider Key、本地配置、私有状态与日志

- Provider Key 不得出现在 argv、普通环境、Envelope 日志、Event、StreamFrame、Snapshot、Checkpoint、崩溃报告或前端持久化。
- 新增 UI 无关 `SecretStore` 抽象，优先使用各 OS 的 credential store。若目标平台没有经过验证的安全实现，桌面设置页只能展示不可用和现有 CLI 安全配置路径，不能回退到明文文件。
- Renderer 只能得到 `configured/provider/source/last_validated_at` 等元数据，不能读取已保存 secret。
- 本地非秘密配置继续由 Core 解析、校验、标明来源；项目配置只能收紧权限。
- Core 私有状态继续位于 `platformdirs` 路径，桌面后端不得直接遍历或修改。
- WebView 自身 cache/localStorage 不保存 Key、源码、完整 Diff、Journal 或 Provider 请求。
- 桌面壳日志与 Core 日志分开，均有大小/保留期上限、`0600` 文件和 `0700` 目录；删除是显式精确范围操作。
- 阶段七不自动上传崩溃或遥测。用户只能先预览脱敏诊断，再手工导出。

## 子进程、终端和 OS 沙箱真实边界

- Renderer sandbox/capabilities 只限制 Web 内容能调用什么，不限制 Python Core 或工具子进程拥有的当前用户权限。
- macOS Hardened Runtime 保护签名进程完整性，不等价于文件/命令 sandbox。
- macOS App Sandbox 能否与任意用户工程、子进程和开发工具兼容必须实测；未通过前不得宣称启用。
- Vera 的 Workspace、PolicyEngine、审批和 ProcessSupervisor 是应用层安全边界，不是恶意代码隔离环境。
- 首版“终端集成”仅包括：展示结构化 argv/cwd/output、复制命令、在验证卡中取消。不得嵌入通用终端或把用户输入透传给 Shell。
- “在外部 Terminal 打开”或 PTY 交互会改变权限、环境、审计和恢复语义，必须另立规格与 ADR。

## 打包、签名、升级、迁移与卸载

### 打包

- 安装包必须自带与当前平台/架构匹配的 Python 3.12 Core 和依赖，不要求用户安装 Python。
- 优先测可审计的 onedir sidecar；onefile 临时解压型打包不能作为默认，除非安全、启动和崩溃清理证据反转该结论。
- 壳、前端资源、Core、Python runtime、兼容清单、许可证和迁移工具共同生成 `artifact-manifest.json` 与 hash。
- GUI 启动不能依赖用户 shell dotfiles 或隐式 `PATH`。

### 签名与分发

- macOS 直接分发候选使用 Developer ID、Hardened Runtime、secure timestamp、notarization 和 stapling。
- 所有嵌套可执行文件、动态库和 Core sidecar 必须按平台要求签名；禁止为省事启用不必要的 JIT、unsigned executable memory、disable library validation 或 DYLD entitlement。
- App Sandbox/Mac App Store 是独立可行性项，不是阶段七默认承诺。
- 签名凭据只进入受保护的本地/CI 签名环境，不进入 Vera runtime 或测试日志。

### 更新和迁移

- 更新单位必须是完整签名应用，不允许只替换 Core 或只替换前端。
- 下载、签名验证、兼容预检和空间检查完成后，必须等待无 active run/approval 的静止点。
- 更新前对私有状态做非破坏备份；未知未来 schema 或迁移失败保留原字节并停止。
- 首次新版本启动执行 dry-run/显式迁移和结果校验；不能边运行 Agent 边迁移。
- 应用回退只有在状态向后兼容或可恢复副本存在时才允许，不能让旧 Core 读取未知新状态。
- 阶段七可用本地离线 update fixture 验证；真实在线发布属于阶段八。

### 卸载

- 删除应用不能修改任何 Workspace。
- 常规卸载默认保留 Vera 私有状态和 OS credential，避免不可恢复丢失。
- “清除 Vera 本地数据”必须是卸载前独立、显式、可预览的破坏性动作，只列出精确私有目录和 credential ID，永不包含 Workspace。
- 各平台无法自动执行的卸载后清理必须有手工文档，不伪装成已清除。

## 平台声明

- 当前开发与首轮实测环境是 Intel macOS；所有数值记录具体 CPU、RAM、macOS、WebView、框架和 Core build。
- `darwin/amd64` 成功只能声明该组合已测。
- Universal binary 构建成功不等于 Apple Silicon 运行已测。
- Windows、Linux、Apple Silicon 必须在各自原生环境完成安装、权限、进程组、Key store、签名/更新和真实 UI 验收后，才进入支持矩阵。
- 不能用框架官网的“支持平台”替代 Vera 整包证据。

## 自动验证

- DesktopEnvelope/帧 codec golden、round-trip、fuzz、重复 key、超限、截断和未知版本测试。
- Fake Core 与真实 Core conformance：动作、Event、StreamFrame、错误、审批、恢复和 operation idempotency。
- Core 启动、EOF、优雅关闭、TERM/KILL、崩溃、crash loop、孤儿进程和 Renderer 重附着测试。
- Renderer API allowlist 与负例：禁止自由文件、Shell、进程、Key 读取和不受控导航。
- 临时 Workspace 上的 prompt、审批、Diff、验证、取消、恢复、回滚闭环。
- 秘密 canary 覆盖 Renderer、Backend、Core stdout/stderr、日志、Crash fixture、State 和打包产物扫描。
- onedir Core、应用包、artifact manifest、迁移、离线升级和卸载不修改 Workspace 测试。
- Wails 使用固定自动场景与测量脚本，不允许因框架已选定而降低门禁。
- 完整 Python 非 live、Ruff、format、Mypy、build、前端 lint/typecheck/unit/e2e 和 `git diff --check`。

## 人工验证

- Intel macOS 原生目录选择、权限/TCC 提示、窗口重载、强制退出、崩溃重启和恢复。
- Workspace、权限、审批、Diff、验证、失败、取消、恢复和回滚的视觉与键盘流程。
- CJK、缩放、高对比、VoiceOver 基础、复制、多屏/休眠唤醒和大 Diff。
- 从 Finder 启动，确认不依赖 Terminal `PATH`；在未安装 Python 的干净账户/机器验证整包。
- Developer ID 签名、notarization、stapling、Gatekeeper、升级和卸载。
- 若缺少证书、Apple Silicon、Windows 或 Linux 环境，明确记录 `Blocked/Not tested`，不能推断通过。

## 阶段退出条件

1. 进程边界 ADR 和 Wails 选择 ADR 均为 `Accepted`。
2. Renderer、桌面后端、Python Core、工具子进程的权限与所有者清晰，负例可证明。
3. 桌面端只发送结构化动作、消费结构化输出，不解析 CLI 人类文本或 Slash 字符串。
4. 握手、版本不兼容、启动失败、停止、Renderer 重附着、Core 崩溃和 crash loop 有确定行为。
5. Workspace、权限、审批、Diff、验证、恢复与回滚完成同一 Core 工作流。
6. Provider Key、配置、私有状态和日志满足最小披露与 canary 扫描。
7. 工具命令继续经过 Core Policy/Approval/ProcessSupervisor，UI 不拥有 Shell。
8. Wails 使用固定夹具完成硬门禁和测量；用户选择依据与技术验证证据分开记录。
9. Vue/React 或其他 UI 选择与桌面壳分开记录，不由模板默认值决定。
10. Intel macOS 的 App、Core sidecar 和嵌套依赖完成打包、签名结构验证；真实 notarization 若受凭据阻塞必须明确记录。
11. 离线升级、状态迁移、崩溃恢复和卸载不修改 Workspace、不丢失唯一状态。
12. 自动门禁全部通过；人工项逐项为 Passed、Blocked 或 Not tested，没有伪造平台支持。
13. 没有未关闭的 Critical/High；Medium 有处置记录。
14. 文档、兼容清单、实现、测试、打包 manifest 和实际 UI 行为一致。
15. 未引入 Multi-Agent、复杂 RAG、插件市场、账号、计费或云端编辑。

## 失败行为

- Core/协议版本不兼容：停止在启动页，不打开 Workspace，不自动替换组件。
- 帧损坏、超限或 stdout 污染：终止协议连接，保留脱敏证据，进入只读恢复路径。
- Workspace 事实变化：使旧审批过期，不执行原动作。
- Core 崩溃：不重发不确定动作；新实例只读扫描持久事实。
- Secret store 不可用：不保存明文，不通过 argv/环境降级传递。
- 签名/更新/迁移失败：保留旧应用或原私有状态，提供人工恢复建议。
- 无法证明 OS sandbox：明确显示“当前用户权限、未验证 OS 沙箱”，不使用模糊安全文案。

## 关联文档

- [产品定义](../PRODUCT.md)
- [路线图](../ROADMAP.md)
- [阶段五 Core 加固](2026-09-12-core-security-and-reliability-hardening.md)
- [阶段六 CLI 产品化](2026-09-12-cli-productization-and-polish.md)
- [ADR-0012：延后桌面集成](../decisions/ADR-0012-delay-desktop-until-cli-hardening.md)
- [ADR-0014：桌面与 Core 进程边界](../decisions/ADR-0014-desktop-core-process-boundary.md)
- [ADR-0015：选择 Wails 作为 Vera 桌面壳](../decisions/ADR-0015-select-wails-desktop-shell.md)
- [阶段七执行顺序](../tasks/phase-7-execution-order.md)
- [框架测量与 Spike](../tasks/0031-desktop-framework-measurement-spikes.md)
