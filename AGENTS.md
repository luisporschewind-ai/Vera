# Vera Agent Working Agreement

This file applies to the entire repository and is the shared instruction baseline for Codex, Cursor Agent, and Claude Code.

## Authority and sources of truth

Follow, in order:

1. The user's current explicit request.
2. Accepted specifications in `docs/specs/` and accepted decisions in `docs/decisions/`.
3. The active record in `docs/tasks/`.
4. `docs/PRODUCT.md`, `docs/ROADMAP.md`, and `docs/STATUS.md`.

When these disagree, stop and resolve the conflict in the relevant document before implementation. Keep documentation and code changes in the same task.

## Fixed project boundaries

- `/Users/admin/Vera` is the only formal Vera product workspace.
- `/Users/admin/Coding-harness` is a retired prototype. Treat it as read-only evidence: do not modify it, continue its architecture, or copy its code directly.
- Vera is a desktop product. The initial CLI is an internal Core development and acceptance surface.
- Build the UI-independent Core first. CLI and desktop clients must consume the same Core contracts and structured events; the desktop must never parse human-oriented CLI output.
- The first stage covers the Agent loop, model adaptation, context, tools, approvals, workspace boundaries, Diff, verification, checkpoints and rollback, logs, recovery, and evals.
- Multi-Agent orchestration, complex RAG, vector databases, and a plugin marketplace are outside the first-stage scope.
- Do not lock in a desktop framework until the Core is stable enough for measured Electron, Wails, or Tauri experiments.

## Required workflow

Before changing files:

- Run `git status --short --branch` and preserve existing user work.
- Read `docs/STATUS.md`, the active task, and any governing spec or decision.
- Confirm the requested change is inside the current phase and workspace boundary.

While working:

- Use one primary implementation Agent per task. Other tools may research, verify, or review, but must not concurrently edit the same working tree.
- For new behavior, accept a specification before implementation. Record durable architecture choices as decisions.
- Prefer the smallest end-to-end, independently verifiable change.
- Keep provider, framework, transport, and UI details behind explicit interfaces.
- Never commit secrets, credentials, private keys, tokens, or local user data.
- Do not rewrite, discard, or overwrite unrelated changes.

Before declaring completion:

- Run the checks required by the active task and the affected specifications.
- Inspect the final diff and run `git diff --check`.
- Record verified results and unresolved decisions in the task or `docs/STATUS.md`.
- Distinguish verified behavior, blocked verification, and assumptions.

## Approval boundaries

Get explicit user approval before destructive or difficult-to-recover actions, external publication, remote changes, or expanding task scope. Do not create commits, push, or change Git remotes unless the current request authorizes that action.
