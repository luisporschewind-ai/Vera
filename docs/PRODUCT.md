# Vera Product Definition

**Status:** Accepted baseline
**Updated:** 2026-09-25
**Core 边界确认：** 2026-09-25 用户确认 Core 为成熟能力中心、CLI/桌面为产品形态，以及受支持平台沙盒行为一致的文档
**平台支持优先级：** 2026-09-25 用户确认 macOS 优先、Linux 其次；Windows 条件性评估，若难以实现或无合适方案，可以不支持。macOS 首发支持 Intel（x86_64）和 Apple Silicon（arm64），须分别在真机验收。

## Purpose

Vera is a local Coding Agent that helps a user safely understand and change a codebase. Its current delivery target is a desktop product, built on a Core shared by CLI and desktop clients. Its value is not merely generating code: it makes the execution chain inspectable, requires approval at meaningful boundaries, verifies results, and provides a recovery path.

Vera is also a long-term learning and portfolio product. It should become maintainable enough for trusted users, interview demonstrations, public learning material, and eventually a real GitHub release.

## Primary workflow

1. The user selects a local workspace and describes a goal.
2. Vera gathers relevant context within that workspace.
3. The Agent proposes and performs permitted tool actions.
4. Vera pauses for approval when an action crosses a defined boundary.
5. The user inspects the resulting Diff and verification evidence.
6. Vera records logs and checkpoints so work can be resumed or rolled back.

## Product principles

- **Local and bounded:** workspace access is explicit and constrained.
- **Transparent:** tool calls, changes, approvals, and verification are inspectable.
- **Recoverable:** checkpoints and rollback are product capabilities, not emergency scripts.
- **Evidence-based:** success means verified outcomes, not plausible model text.
- **No hidden workspace pollution:** verification may read project sources, but build/cache artifacts stay outside the workspace unless an explicit Core file-mutation plan authorizes a persistent file.
- **Untrusted by default:** repository content, tool results, model output, and future external data cannot grant authority; deterministic policy and parameter-bound approval govern actions.
- **Core-first:** product behavior lives outside any specific CLI or desktop shell.
- **Incremental:** specifications, code, tests, and documentation evolve in small accepted slices.

## Core 能力与产品形态

Vera 首先是一个能独立完成 Coding Agent 工作流的 Core。CLI 和桌面端是访问同一能力的不同产品形态：入口、呈现和交互可以不同，执行事实与安全判断必须一致。当前路线仍以桌面端为最终交付目标、CLI 为 Core 开发和验收入口；是否将 CLI 作为独立公开产品，留给后续发布决策。这一区分不改变现有阶段门禁。

Core 必须拥有跨形态稳定的任务与 Run 生命周期、模型适配、上下文管理、工具执行、Workspace、Policy、Approval、沙盒授权、Diff、验证、Checkpoint、恢复和结构化证据。一次操作的允许范围、批准事实、执行结果与失败原因，由 Core 及其受限平台服务给出，不能因用户从 CLI 或桌面端发起而改变。

客户端负责采集意图、呈现事实和承载各自的交互能力。CLI 可以提供终端命令、TUI、Plain 和 JSON；桌面端可以提供可视化时间线、Diff、通知和系统交互。客户端通过版本化 Command/Event 契约调用 Core，不解析另一客户端的人类可读输出，也不复制 Policy、审批、沙盒、恢复或验证逻辑。平台 Broker 可以持有凭据并实施 OS 资源授权，但只提供经过校验的窄服务，不成为第二套 Agent 决策中心。

Core 的成熟度由完整任务和失败路径证明：在受支持的任意软件工程中，能够调查、修改、运行、验证并恢复；权限、沙盒状态、拒绝和副作用可核查；安装态、升级、异常中断和不同客户端得到一致的 Core 事实。沙盒支持顺序为 macOS、Linux，Windows 仅在方案可行且可维护时继续。macOS 的 Intel 与 Apple Silicon 均须满足同一安全基线；当前 Intel 实测不能代替 Apple Silicon 验收。各已支持平台的实现可以不同，但相同授权必须有相同的范围、默认限制、拒绝、取消与恢复语义；做不到共同安全基线的平台明确报不支持，不能静默放宽权限。界面完成度不能替代这些证据，Core 的自动测试也不能替代真实 CLI 与桌面交互验收。开源发布时，用户应能复现主要安全与可靠性声明，并清楚看到尚未支持的能力。

## First-stage capability scope

- Agent loop and model-provider adaptation
- Context collection and budget management
- Read, search, edit, and command tools
- Workspace and permission boundaries
- Human approval and cancellation
- Patch and Diff inspection
- Independent verification
- Checkpoints, rollback, persistence, and recovery
- Structured logs, usage evidence, and fixed-task evals
- Untrusted-content provenance, prompt-injection containment, and adversarial safety evals

## Outside the first stage

- Multi-Agent orchestration
- Complex RAG or a vector database
- Plugin marketplace
- Cloud editing of a user's local workspace
- Full editor or LSP replacement
- Premature desktop-framework optimization

## Accepted decisions

- The formal product and repository name is Vera.
- The final product is a desktop Agent; the early CLI is internal.
- Delivery order is Core-first, CLI-first, desktop-later.
- Desktop integration starts only after Core hardening, CLI product-readiness gates, the user's explicit confirmation that the CLI version meets expectations and may be sealed, Phase 8 Core tooling/Policy/Git, and Phase 9 Core-native Skills.
- Until that confirmation, Wails, Tauri, Electron, and any other desktop-shell code stay out of the repository.
- After the seal and separate implementation authorization, Phase 8 first delivers Pi-aligned Core tools, risk-tiered Policy v2, and native local Git through the CLI.
- Phase 9 then delivers Core-native Skills through the CLI on top of the stable Phase 8 Tool/Policy contracts. Phase 10 uses Electron as the first desktop baseline while preserving the Python Core and structured Command/Event boundary. Tauri remains the fallback if measured gates fail.
- Core clients communicate through structured contracts, not parsed CLI text.
- Core-native Skills use a Core control plane with external packages. v1 supports only built-in, user-local, and workspace-local read-only packages, explicit single-Skill selection, and immutable Run snapshots.
- A Skill describes how to work but cannot register permissions, expand Workspace, modify Policy/Approval, read Provider Keys, declare network access, bypass Core file-mutation planning, or execute package scripts in v1.
- Workspace Skills are always untrusted project content. The Core owns discovery, conflict handling, trust classification, selection, snapshots, recovery, Context assembly, and structured events.
- Development is private until reliability and release-readiness checks are met.
- SDD, small verified changes, and synchronized documentation are required.
- The accepted Phase 4 design fixes 14 bundled offline Fake Model cases and scores only Core facts and file hashes.
- The 14-case offline evaluation suite is an accepted first-stage capability, shipped with `vera eval` and the installable wheel.
- Verification commands are planned before hashing and approval; supported build/cache outputs use Vera-owned external temporary roots, and unknown write-capable verification fails closed.

## Open decisions

- 阶段五结束时公共 Command/Event、错误、审批与恢复契约的兼容承诺
- 阶段六声明支持的终端：macOS Terminal.app 已走查；iTerm2/Warp/Linux/Windows Terminal 保持 `Not run`
- 阶段七 CLI 的最终 Logo、首屏、信息密度与深海主题细节
- 阶段十桌面端是否接受“Agent 工作台”产品形态与四区信息架构
- Vera Logo 从阶段七 CLI 到阶段十桌面图标、菜单栏和小尺寸形态的统一识别系统
- Electron baseline packaging, resource budgets, updater, signing, and distribution details
- License, contribution model, telemetry policy, and public-release criteria
- 阶段十一公开内容安全政策、审核部署、隐私边界和申诉机制
