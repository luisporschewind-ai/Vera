# ADR-0014：桌面壳与 Python Core 采用受监督 sidecar 进程边界

**状态：** Accepted
**日期：** 2026-09-12
**编号说明：** 任务 0024 已预留 `ADR-0013` 给 Core 客户端兼容性契约；若该任务最终改变编号，本 ADR 在接受前顺延校准。

## 背景

Vera Core 使用 Python 3.12，已经以 `Command → VeraRuntime → Event`、`SessionAction → SessionController → RuntimeOutput` 表达安全编辑、审批、验证、恢复和回滚。桌面端需要复用这些结构化事实，同时增加窗口生命周期、进程启动、崩溃、重附着、打包、签名和更新。

如果把 Python 嵌入桌面壳进程，Python ABI、GIL、原生依赖和壳崩溃会共享一个故障域。如果直接启动 `vera` 并解析 TUI/Plain 文本，Presenter 变化会变成协议变化。如果开放 localhost 服务，又会额外引入端口发现、鉴权、其他本机进程访问和残留服务生命周期。

因此需要先确定与具体 Wails/Tauri/Electron 无关的进程边界。

## 决策

### 1. 独立、受监督的 Python Core sidecar

- 桌面可信后端从签名应用包内的固定绝对路径启动一个自包含 Python Core sidecar。
- Renderer 不直接启动或连接 Core。
- Core sidecar 保持 `VeraRuntime`、`PolicyEngine`、Workspace、Provider、Journal、Checkpoint 和 Recovery 的唯一权威。
- 桌面可信后端只监督进程并转发结构化消息，不解释审批或恢复业务。
- 首版一个应用实例只拥有一个 Core、一个 Workspace 和一个 Session；不做 daemon、多窗口并行或后台继续。

### 2. framed stdio，而不是网络端口

- v1 使用 stdin/stdout 上的长度前缀 UTF-8 JSON 帧。
- stdout 专用于协议，stderr 专用于有界脱敏诊断。
- 不监听 TCP、Unix socket 或 named pipe，不需要端口发现和本机客户端鉴权。
- 帧大小、Header、队列和 stderr 都有硬上限；持久 Event 不丢，瞬时 StreamFrame 可在背压时合并。

### 3. 分离传输协议与 Core 契约

- 外层 `DesktopEnvelope` 提供 handshake、版本、request/response 关联、`process_instance_id`、`transport_sequence` 和 `operation_id`。
- 内层复用阶段五冻结后的 `SessionAction`、`EventEnvelope`、`StreamFrame` 与结构化查询结果。
- 桌面 UI 不拼接 Slash Command，不解析 TUI/Plain/Presenter 文本。
- 现有 `vera --json` 的 model 和 Fixture 可以复用，但 CLI entrypoint、提示词、stderr 和生命周期不是桌面 API。

### 4. 崩溃后只读恢复，不自动重放

- Renderer 重载时重附着到仍存活的桌面后端，由 bounded buffer、Session snapshot 和持久 Event 分页恢复 UI。
- Core 退出时，后端可启动新 Core，但只握手并扫描持久恢复事实。
- 不自动重发 prompt、approval、write、verification、rollback 或任何结果未知的动作。
- side-effect request 必须携带可持久核对的 `operation_id`；重复输入返回相同回执，不重复副作用。

### 5. Core 与工具子进程不是 OS 沙箱

- Renderer sandbox 或框架 capabilities 只保护前端到后端边界。
- Core 和经批准的工具仍以当前用户权限运行。
- 所有工具继续使用 Core 的结构化 argv、`shell=False`、Workspace cwd、环境 allowlist、审批和进程组清理。
- UI 必须明确展示该真实边界。

## 进程与信任关系

| 组件 | 信任级别 | 可拥有能力 | 明确禁止 |
|---|---|---|---|
| Renderer | 低 | 本地 UI、输入、View Model | 文件、Shell、进程、Key、私有状态 |
| 桌面可信后端 | 中 | 窗口、原生选择器、CoreSupervisor、更新 | Runtime 决策、Workspace 写入、代替审批 |
| Python Core | 高/业务权威 | Provider、Policy、Workspace、状态、恢复 | 依赖 Renderer 文本判断 |
| 工具子进程 | 低/受控 | 已批准 argv/cwd/环境 | 未经 Core Policy/Approval 的执行 |

## 协议不变量

1. 没有成功握手就不能打开 Session。
2. major 版本无交集必须失败关闭。
3. Event 的 run sequence 与传输 sequence 分离，任一缺口都不能被猜测补齐。
4. `StreamFrame` 不参与完成、审批或恢复判断。
5. 结果未知的 side-effect action 不自动重试。
6. 大 Diff/日志通过 Core 分页或明确截断，不允许无限帧。
7. stdout 污染、重复 JSON key、超限或非法 Content-Length 视为协议损坏。
8. 后端不能通过直接读 Workspace 或私有状态“修复”协议缺口。

## 备选方案

### 方案 A：把 Python 嵌入桌面壳进程

优点：

- 没有 IPC 序列化和子进程管理；
- 小消息调用延迟最低。

拒绝原因：

- Python ABI、解释器、原生依赖和壳语言绑定会扩大框架锁定；
- UI 后端崩溃与 Runtime/持久写入共享故障域；
- 打包、线程/GIL、升级和故障注入更难独立验证；
- Wails、Tauri、Electron 无法共享同一集成边界。

### 方案 B：受监督 sidecar + framed stdio

优点：

- 与桌面框架无关，Python Core 可独立测试和打包；
- 无监听端口，连接所有者和生命周期清晰；
- 进程崩溃、stdout 污染、半帧、EOF、TERM/KILL 可确定性注入；
- Wails Go、Tauri Rust、Electron Node 都能以普通子进程 API 实现。

代价：

- 需要 framing、handshake、背压、idempotency 和 Supervisor；
- App、Core 和 State Codec 的版本兼容必须显式管理；
- Core 崩溃后不能伪装成无缝续跑。

本 ADR 选择该方案。

### 方案 C：localhost HTTP/WebSocket 服务

优点：

- 浏览器工具、调试和多客户端接入方便；
- WebSocket 天然适合流式消息。

首版拒绝原因：

- 需要端口选择、鉴权、来源校验、CSRF/Origin、残留服务和防止其他本机进程连接；
- 容易滑向 daemon、多窗口和远程访问，超出阶段七；
- 对单应用单 Core 没有抵消安全与运维复杂度的收益。

当未来明确需要后台服务、多窗口或独立客户端时重审。

### 方案 D：直接复用 CLI 人类输出或 Slash 文本

拒绝。Presenter、翻译、折叠和终端控制不是业务协议；桌面按钮也不应拼接 `/diff` 或 `/rollback` 让 CLI parser 再解释。

## 后果

- 阶段七必须新增桌面进程协议与 conformance harness，但不新增第二套 Runtime。
- 三个桌面壳 Spike 可以复用完全相同的 fake/real Core sidecar。
- Core 包必须自包含 Python runtime，并作为应用签名的一部分。
- Renderer 安全可以独立于 Core 命令权限验证。
- Core crash 体验会诚实显示“状态待核对”，而不是自动重发。
- 若最终框架无法可靠完成双向 stdin/stdout、进程组清理、嵌套签名或 Renderer 能力收窄，该框架直接不合格。

## 验证

- 跨语言 golden frame 和 Pydantic round-trip。
- 半帧、超限、重复 key、stdout 污染、未知 major/minor/capability。
- 10 秒握手超时、stdin EOF、正常 shutdown、TERM/KILL、父进程死亡和 crash loop。
- Renderer 重载时不重发 action，Event gap 通过 snapshot/page 恢复。
- Core 在 prompt、审批、写入、验证和回滚边界崩溃后只读分类。
- canary secret 不进入 argv、stdout/stderr、Envelope 日志、Renderer cache 或 crash report。
- Wails 执行完整 conformance harness；若 ADR-0015 被重审，其他壳也必须复用同一 harness，不能修改 Core 协议迁就框架。

## 重审触发器

- 产品确认需要后台常驻、多窗口并行或多个独立客户端；
- framed stdio 无法满足经测量的流量、背压或调试要求；
- 目标 OS 的子进程/签名模型无法可靠收割 sidecar；
- Python Core 被正式替换为与桌面壳同语言且故障隔离仍可证明；
- Core 公共契约发生 breaking change；
- 引入 PTY、远程访问或真正的 OS sandbox。

## 关联文档

- [阶段七桌面集成规格](../specs/2026-09-12-desktop-integration.md)
- [ADR-0001：Python Core](ADR-0001-python-core-runtime.md)
- [ADR-0002：Command/Event](ADR-0002-command-event-contract.md)
- [ADR-0005：确定性恢复](ADR-0005-deterministic-run-recovery.md)
- [ADR-0006：版本化 Codec](ADR-0006-versioned-state-codecs.md)
- [ADR-0010：Event 与 StreamFrame](ADR-0010-transient-stream-frames.md)
- [ADR-0012：延后桌面集成](ADR-0012-delay-desktop-until-cli-hardening.md)
- [ADR-0015：选择 Wails 作为 Vera 桌面壳](ADR-0015-select-wails-desktop-shell.md)
