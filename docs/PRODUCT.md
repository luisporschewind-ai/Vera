# Vera Product Definition

**Status:** Accepted baseline
**Updated:** 2026-09-12

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
- Desktop integration starts only after Core hardening and CLI product-readiness gates are complete.
- Core clients communicate through structured contracts, not parsed CLI text.
- Development is private until reliability and release-readiness checks are met.
- SDD, small verified changes, and synchronized documentation are required.
- The accepted Phase 4 design fixes 14 bundled offline Fake Model cases and scores only Core facts and file hashes.

## Open decisions

- Core implementation language, runtime, and dependency policy
- Initial model providers and adapter contract
- Core command and event protocol
- Session, checkpoint, and recovery storage design
- Desktop framework and packaging approach
- License, contribution model, telemetry policy, and public-release criteria
