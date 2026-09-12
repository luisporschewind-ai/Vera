# Vera 路线图

**状态：** Active
**更新日期：** 2026-09-13

路线图规定阶段顺序和退出条件，不提前锁定尚未完成决策的技术方案。

## 阶段 0——仓库治理

**状态：** Complete

- 建立正式仓库、共享 Agent 指引、产品边界、路线图、状态记录、规格、决策和任务记录。
- 在没有 Agent 功能代码的前提下，建立第一个可恢复的 Git 检查点。

**退出条件：** 基线完成审阅、验证通过，并提交 `chore: bootstrap Vera repository`。

## 阶段 1——Core 契约与安全编辑垂直切片

**状态：** Complete

- 固化 Python 3.12 Core 边界、生命周期、Command、结构化 Event 和可替换 ModelAdapter。
- 完成一条 CLI 驱动的安全编辑闭环：上下文收集 → Change Set 审批 → Checkpoint → 写入 → 验证 → 手动回滚。
- 让 Runtime 状态、审批、工作区边界、Diff、验证证据和私有日志由同一个 Core 权威统一管理。

**退出条件：** 内部 CLI 通过面向未来桌面客户端的同一套公共 Core 契约，完成一个有界安全编辑任务，并具备确定性离线测试和可审阅的审批证据。

## 阶段 2——恢复、兼容性与策略扩展

**状态：** Complete

- 增加重启恢复、Journal resume、兼容性迁移、取消流程加固、策略扩展和更完整的失败路径覆盖。
- 扩展供应商兼容性与评测证据，同时不削弱 Core 安全边界。
- 按任务 0005–0009 依次完成恢复事实、安全续跑、版本 Codec、统一策略和供应商韧性。

**退出条件：** Core 在中断后可恢复，跨版本行为可检查，并在代表性本地仓库上完成验证。

## 阶段 3——富交互 Terminal UI

**状态：** Complete

- 以 Typer + Textual + Rich 实现默认 TUI、`--plain` 与 `--json` Session，三者共用 SessionController 与 Vera Core。
- 完成流式 RuntimeOutput、时间线披露、Composer/审批焦点、模式兼容与 15 条规格验收证据。
- 不引入 prompt_toolkit，不提前桌面框架。

**退出条件：** 任务 0010–0014 全部合并，规格 15 条验收标准均有自动或人工证据。

## 阶段 4——评测与内部就绪

**状态：** Complete

- 定义可重复的评测工具和固定的 10–20 个编码任务集合。
- 跟踪正确性、安全性、恢复能力、延迟和模型成本。
- 通过规格、测试和聚焦实施任务解决失败项。
- 第一版固定 14 个内置 Fake Model case，每个 case 在临时目录和独立 Worker 中运行，不调用真实 Provider。

**退出条件：** CLI 能重复完成已接受的评测集合，并提供日志、Diff、审批和验证证据。

## 阶段 5——Core 安全、权限与可靠性加固

**状态：** Ready for manual acceptance

- 对阶段四交付执行独立安全、权限、路线和文档审查，关闭阻断项。
- 在 Swift/Xcode、Python、Node/TypeScript 代表性工程上验证完整 CLI 工作流。
- 加固文件、命令、审批、凭据、进程、恢复、安装升级和长会话边界。
- 在任务 0024 冻结契约前完成[任务 0030：不可信内容与提示词投毒防御](tasks/0030-untrusted-content-and-prompt-injection.md)。
- 形成经真实工程验证的稳定 Core，并冻结后续客户端可依赖的结构化契约。
- 按[阶段五执行顺序](tasks/phase-5-execution-order.md)实施任务 0020–0023、0030、0024。

**退出条件：** 阶段五规格的安全、权限、真实工程、稳定性、安装升级和提示词投毒对抗门禁全部通过，没有未关闭的 Critical/High 问题。

## 阶段 6——CLI 产品化与体验完善

**状态：** In progress

- 在阶段三 TUI 基础上完善输入、历史、补全、导航、帮助、诊断、Diff 和审批体验。
- 统一 `vera`、`--plain`、`--json` 与一次性调用的命令语义、错误、退出码和文档。
- 以 Claude Code、Codex CLI、Gemini CLI 的共同交互模式为参考，形成成熟但不照搬的 Vera Terminal 产品体验。
- 消除终端恢复、粘贴、Resize、长输出、Unicode、无色和低速终端中的高频低级问题。
- 展示 Core 提供的内容来源、投毒风险和实际策略结果；CLI 不自行审核内容或决定权限。
- 阶段五完成后按[阶段六执行顺序](tasks/phase-6-execution-order.md)实施任务 0025–0029。
- 任务 0029 的自动部分完成后只能进入 `Ready for manual acceptance`，等待用户在真实 Terminal.app 和真实工程中体验。

**退出条件：** 默认 TUI 和兼容模式完成产品级可用性验收，关键工作流无需记忆隐含操作，没有阻断使用的已知交互缺陷；用户明确确认「CLI 版本达到预期，可以封存」。自动测试通过不能单独将本阶段标为 Complete。

## 阶段 7——桌面集成

**状态：** Not started
**入口条件：** 阶段五 Complete，阶段六 Complete，且用户已确认「CLI 版本达到预期，可以封存」。未满足前不得引入 Wails、Tauri、Electron 或任何桌面端代码。

**预先校准：** [阶段七：桌面 Agent 工作台与 UI](specs/2026-09-12-desktop-agent-workbench-ui.md) 当前为 Draft，只收束产品体验、信息架构与后续增量，不代表阶段七已经启动。“Agent 工作台”四区布局仍待用户确认。

- 基于已加固的 Core 契约制作桌面壳原型。
- 按 [ADR-0013](decisions/ADR-0013-electron-desktop-baseline.md) 使用 Electron 建立首个桌面底版，保持 Python Core 独立并通过结构化 Command/Event 接入。
- 复用 Core 的来源、风险、审批与策略事实，并在真实 Mac 上验证安全提示和操作确认。
- 测量安全边界、打包、进程控制、性能、体积和维护成本；Electron 未达到接受门禁时再以 Tauri 进行同契约对照。
- 通过独立决策确定前端框架、进程传输和发布打包细节后实现桌面工作流。
- 阶段七按“安全桌面壳 → 工作台骨架 → 证据闭环 → 产品体验 → 私有交付”拆分为五个可独立验收的增量。

**退出条件：** 桌面客户端完成 Core 工作流，不复制 Runtime 逻辑，也不解析 CLI 输出。

## 阶段 8——私有预览与公开准备

**状态：** Not started

- 使用可信用户和真实项目进行验证。
- 完成威胁建模、提示词投毒 red-team、公开内容政策、CI、发布打包、文档、远程更新供应链安全、密钥与 Git 历史审计、许可证、安全策略和贡献指南。

**退出条件：** 发布检查清单证明 Vera 安全、可维护、可复现，并适合公开 GitHub 仓库。
