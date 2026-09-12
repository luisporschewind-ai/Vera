# ADR-0013：阶段七首个桌面底版采用 Electron

**状态：** Accepted
**日期：** 2026-09-12

## 背景

Vera 已使用 Python 3.12 实现 UI 无关的 Core，并以版本化 `Command -> VeraRuntime -> Event` 作为 CLI、评测工具和未来桌面客户端的共享边界。桌面端需要承载长对话时间线、工具过程、Diff、审批、验证证据和本地进程状态，但不能复制 Runtime 逻辑、解析 CLI 文本或扩大权限。

Electron、Tauri 与 Wails 都能承载 Web 前端。Electron 的成熟产品和桌面生态最完整，适合先验证复杂 Agent 工作台；Tauri 的体积和权限模型有吸引力，但会增加 Rust、系统 WebView 和 Python Sidecar 的首版集成成本；Wails 的主要优势建立在 Go 后端上，与当前 Python Core 不匹配。

用户已确认 Electron 作为 Vera 阶段七的首个桌面底版。本决策只提前固定未来实施方向，不改变阶段五、阶段六和人工封存门禁。

## 决策

- 阶段七满足入口条件后，首个 Vera 桌面底版使用 Electron。
- Python `VeraRuntime` 继续是唯一业务与安全权威；Electron 主进程和 Renderer 只负责桌面生命周期、受限桥接与展示。
- 桌面端只发送版本化 Command、消费结构化 Event，不解析 CLI/TUI 文本，不把 Runtime、审批、策略、Checkpoint、验证或恢复逻辑复制到 JavaScript。
- Core 作为独立受管进程运行。进程封装、分帧传输和打包细节在阶段七规格中确定，但不得改变公共契约语义。
- Renderer 不直接访问文件系统、Shell、凭据或 Core 进程；通过窄化且显式允许的 Preload API 请求 Electron 主进程。
- Electron 必须关闭 Renderer 的 Node.js 集成，启用 `contextIsolation` 与进程沙箱，验证全部 IPC 调用来源，并禁止不可信远程内容获得本地能力。
- 前端使用 Vue、React 或其他方案仍是独立决策；本 ADR 不借 Electron 选择锁定 UI 框架。
- Tauri 保留为 Electron 无法满足已接受资源、安全或发布门禁时的首要备选。除非 Python Core 经独立 ADR 改为 Go，否则不采用 Wails。
- 未满足阶段七入口条件前，不添加 Electron 依赖、桌面代码、打包配置或技术 Spike。

## 非目标

- 不开始阶段七实施或把路线图状态改为进行中。
- 不确认尚在讨论的桌面信息架构、视觉主题或前端框架。
- 不直接迁移、复制或续写 `/Users/admin/Coding-harness` 原型代码。
- 不在当前阶段实现安装器、自动更新、签名、公证或发布渠道。

## 后果

- 阶段七不再重复进行无边界的框架选型，先以 Electron 建立可测量的完整桌面工作流。
- 可以使用成熟 Chromium 与 Node.js 桌面生态承载复杂时间线、Diff、终端和调试表面，同时保留现有 Python Core。
- 安装体积、空闲内存和 Chromium/Node.js 更新成本高于轻量 WebView 方案，必须形成明确基线并持续维护安全更新。
- Electron 桥接层成为新的高风险边界，需要独立威胁建模、IPC 允许列表和端到端权限测试。
- 若 Electron 底版未达到门禁，优先用同一前端与公共 Core 契约测量 Tauri，而不是修改 Core 迎合桌面框架。

## 被拒绝的方案

- **继续保持三个框架完全开放：** 会把首个底版的设计、打包和安全边界继续推迟，增加阶段七启动成本。
- **直接采用 Tauri：** 体积和能力边界更有优势，但第一版需要同时承担 Rust、系统 WebView 差异和 Python Sidecar 多架构打包。
- **采用 Wails：** 适合 Go 后端，但 Vera 已有 Python Core；额外增加 Go 桥接层不能带来足够收益。
- **让 Electron Renderer 直接操作文件或 Shell：** 会绕开 VeraRuntime、PolicyEngine 与 ApprovalGate，破坏既有安全模型。
- **迁移原型的 Electron/React 实现：** 原型只作为需求证据，不能成为正式 Vera 架构基础。

## 验证与重审触发器

阶段七底版必须记录并验证：

1. 冷启动时间、空闲内存、安装包体积和窗口恢复；
2. Core 启停、崩溃、取消、重连和应用退出时不存在遗留进程；
3. Command/Event 分帧、顺序、背压和协议版本失败路径；
4. Renderer 无 Node.js、文件系统、Shell、凭据或未授权 IPC 能力；
5. Diff、审批、验证、恢复和内容来源只展示 Core 权威事实；
6. macOS Intel 与 Apple Silicon 的签名、公证和 Core 打包路径，并为后续 Windows 验证保留边界。

出现以下任一情况时，必须重审本决策并优先测量 Tauri：

- Electron 无法达到阶段七接受的启动、空闲内存或安装体积预算；
- Renderer 与主进程隔离无法满足 Vera 威胁模型；
- Python Core 生命周期或跨平台打包长期不稳定；
- 安全更新、签名、公证或发布维护成本不可接受。

## 与现有决策的关系

- 本 ADR 补充 [ADR-0012](ADR-0012-delay-desktop-until-cli-hardening.md)，只取代其中“桌面框架保持开放直到阶段七”的条款。
- ADR-0012 的阶段五、阶段六、人工 CLI 封存和禁止提前引入桌面代码的门禁继续完整有效。
- [ADR-0001](ADR-0001-python-core-runtime.md) 的 Python Core 与 [ADR-0002](ADR-0002-command-event-contract.md) 的公共契约继续有效。

## 参考

- [Electron Process Model](https://www.electronjs.org/docs/latest/tutorial/process-model)
- [Electron Security](https://www.electronjs.org/docs/latest/tutorial/security)
- [Tauri Sidecar](https://v2.tauri.app/develop/sidecar/)
- [Wails Introduction](https://wails.io/docs/introduction/)
