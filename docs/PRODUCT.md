# Vera Product Definition

**Status:** Accepted baseline
**Updated:** 2026-09-26

## Purpose

Vera is a local desktop Coding Agent that helps a user safely understand and change a codebase. Its value is not merely generating code: it makes the execution chain inspectable, requires approval at meaningful boundaries, verifies results, and provides a recovery path.

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
- 阶段七 CLI 已于 2026-09-17 封存；后续 Logo V4、四行信息与五套主题已定向验收（0073、0076–0081）。桌面 Logo 适配仍属开放决策。
- 用户于 2026-09-21 单独授权阶段九与阶段八剩余验收并行；不放宽阶段十门禁。
- BYOK 配置遵循 [ADR-0022](decisions/ADR-0022-user-owned-byok-provider-configuration.md)：Provider、endpoint、默认模型与 Key 引用由可信用户配置控制，工程配置不能覆盖。

## Open decisions

- 阶段五结束时公共 Command/Event、错误、审批与恢复契约的兼容承诺
- 阶段六声明支持的终端：macOS Terminal.app 已走查；iTerm2/Warp/Linux/Windows Terminal 保持 `Not run`
- 阶段十桌面端是否接受“Agent 工作台”产品形态与四区信息架构
- Vera Logo 从阶段七 CLI 到阶段十桌面图标、菜单栏和小尺寸形态的统一识别系统
- Electron baseline packaging, resource budgets, updater, signing, and distribution details
- License, contribution model, telemetry policy, and public-release criteria
- 阶段十一公开内容安全政策、审核部署、隐私边界和申诉机制
