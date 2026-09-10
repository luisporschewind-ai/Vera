# Vera Roadmap

**Status:** Active
**Updated:** 2026-09-10

The roadmap defines order and exit criteria. It does not preselect technologies that still require an accepted decision.

## Phase 0 — Repository governance

**State:** Complete

- Establish the formal repository, shared Agent instructions, product boundary, roadmap, status log, specifications, decisions, and task records.
- Make the first recoverable Git checkpoint without Agent feature code.

**Exit:** The baseline is reviewed, validation passes, and `chore: bootstrap Vera repository` is committed.

## Phase 1 — Core contract and vertical slice

**State:** Design in progress

- Specify the Core boundary, lifecycle, commands, structured events, and model adapter.
- Select the minimum runtime and dependency set through accepted decisions.
- Build one CLI-driven, end-to-end coding task with durable logs and deterministic tests around owned logic.

**Exit:** The internal CLI runs one fixed task through the same public Core contract intended for the desktop client.

## Phase 2 — Safe coding loop

**State:** Not started

- Add context controls, workspace-constrained tools, approvals, Diff review, verification, checkpoints, rollback, cancellation, persistence, and recovery.
- Test failure paths and restart behavior, not only happy paths.

**Exit:** Core behavior is recoverable, inspectable, and verified across representative local repositories.

## Phase 3 — Evals and internal readiness

**State:** Not started

- Define a repeatable eval harness and a fixed set of 10–20 coding tasks.
- Track correctness, safety, recovery, latency, and model cost.
- Resolve failures through specs, tests, and focused implementation tasks.

**Exit:** The CLI repeatedly completes the accepted eval set with logs, Diff, approval, and verification evidence.

## Phase 4 — Desktop integration

**State:** Not started

- Prototype desktop shells against the stable Core contract.
- Compare security boundary, packaging, process control, performance, size, and maintenance cost.
- Select a framework through an accepted decision and build the desktop workflow.

**Exit:** The desktop client completes the Core workflow without duplicating runtime logic or parsing CLI output.

## Phase 5 — Private preview and public preparation

**State:** Not started

- Validate with trusted users and real projects.
- Complete threat modeling, CI, release packaging, documentation, update strategy, secret and Git-history audits, license, security policy, and contribution guidance.

**Exit:** A release checklist demonstrates that Vera is safe, maintainable, reproducible, and suitable for a public GitHub repository.
