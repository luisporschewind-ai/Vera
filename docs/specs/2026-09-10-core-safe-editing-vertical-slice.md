# Vera Core Safe Editing Vertical Slice

**Status:** Accepted
**Date:** 2026-09-10

## Goal

Build Vera's first reusable Python Core and CLI vertical slice. A user gives Vera a coding goal; Vera gathers bounded workspace context, asks a model to propose one complete Change Set, pauses for approval, creates a checkpoint, applies the approved files, runs verification, emits structured evidence, and can manually roll the change back.

This increment establishes `VeraRuntime` as the product authority. Models, provider clients, CLI rendering, and the future desktop shell are replaceable edges. Runtime state, workspace policy, approvals, Change Sets, checkpoints, verification, and public events remain owned by Vera.

The retired `/Users/admin/Coding-harness` prototype is feasibility evidence only. This specification does not repeat its read/write demonstrations as a milestone and does not copy its architecture or code.

## Non-goals

This increment does not include:

- Wails, Electron, Tauri, or another desktop shell;
- multi-Agent or sub-Agent orchestration;
- MCP, a plugin marketplace, RAG, a vector database, or long-term memory;
- unattended write approval or an automatic repair loop;
- crash-time continuation or cross-process run resumption;
- cloud synchronization, accounts, a remote execution sandbox, or telemetry;
- advanced Git branch, commit, pull-request, or merge automation;
- per-token model streaming; or
- a public release, license decision, or packaging for end users.

Phase 2 will extend and harden these minimum safety semantics across broader repositories and failure modes. In particular, restart recovery remains Phase 2 work; this increment provides durable evidence and manual rollback, not automatic continuation after a crash.

## Architecture

The first implementation is one Python distribution with focused internal packages:

```text
src/vera/
├── contracts/       # Commands, events, Change Sets, approvals, results
├── runtime/         # State machine and Agent orchestration
├── models/          # Provider-independent interface and adapters
├── tools/           # Tool registry, validation, and execution policy
├── workspace/       # Path safety, snapshots, apply, and rollback
├── verification/    # Verification plans and evidence
└── cli/             # Human interaction and structured rendering
```

The dependency direction points inward to stable contracts. Provider SDK types do not cross `models/`; terminal formatting does not cross `cli/`; file-system and process details do not cross their owned boundaries.

```text
User or future Wails client
            |
            v
CLI or structured process transport
            |
            v
       VeraRuntime ---------> ordered Event stream
        |   |   |
        |   |   +-----------> Workspace, checkpoint, verification
        |   +---------------> Tool registry and policy
        +-------------------> ModelAdapter -> DeepSeek / GLM
```

The initial CLI may call the Core Python API in-process. The public Core interface is nevertheless expressed as versioned, JSON-serializable Commands and Events. A future Wails-managed sidecar may carry the same contract over JSON Lines or another framed transport without parsing human CLI text. Implementing that sidecar server is not required in this increment.

## Component responsibilities

### VeraRuntime

`VeraRuntime` is the sole coordinator and source of run truth. It:

- validates a start command and constructs the bounded run context;
- owns the state machine and all legal transitions;
- invokes `ModelAdapter` and validates every returned tool call;
- dispatches only registered tools allowed by local policy;
- constructs the canonical Change Set and its content hash;
- suspends at command and Change Set approval boundaries;
- requires a completed checkpoint before target-file writes;
- applies files, starts verification, and records outcomes;
- coordinates automatic restoration after an in-process apply failure;
- exposes manual rollback for completed writes; and
- emits ordered, versioned Events for every material transition.

No model or client may set Runtime state directly or assert that an approval, checkpoint, write, verification, or rollback succeeded.

### ModelAdapter

The provider-independent adapter accepts Vera messages and tool definitions and returns a normalized model turn:

```text
assistant_text
tool_calls[]
finish_reason
usage
provider_metadata
```

The first provider implementation is a configurable OpenAI-compatible adapter used for DeepSeek and GLM profiles. A maintained provider client handles HTTP, authentication, serialization, and provider streaming details; Vera does not hand-write that transport. Runtime does not depend on provider response classes.

Provider output is untrusted. Runtime validates tool names, argument schemas, limits, paths, and policy even when the provider reports a valid structured tool call.

### Tools

The first tool registry supports:

- listing a directory within the workspace;
- searching text within the workspace;
- reading an allowed text file;
- proposing create, update, or delete operations for a Change Set; and
- proposing a verification command represented as an argument array.

There is no model-facing direct-write tool. The model supplies the intended post-change content or deletion intent; Runtime reads the current state, calculates hashes, and generates the unified Diff.

Rename is not a distinct first-version operation. It is represented as a create plus delete in the same Change Set and is therefore approved and checkpointed as one unit.

### Workspace and checkpoints

Workspace owns canonical path resolution and file-system side effects. All public paths are normalized workspace-relative paths. Reads may follow a symbolic link only when its resolved target remains inside the workspace. Mutations never follow symbolic links.

Before applying a Change Set, Workspace verifies every affected file against its recorded pre-change hash, preflights every operation, and creates a checkpoint manifest plus the original file bytes. Checkpoints and run records live in Vera's private, configurable state directory rather than in the project. State directories and files must be created with current-user-only permissions where the platform supports them.

Checkpoint payloads are local recovery data. They are never added to model context automatically.

### Verification

Verification executes an approved plan after file application and returns structured evidence. Commands are argument arrays and run without a shell interpreter. Each command has a workspace-relative working directory, timeout, exit code, duration, and bounded stdout and stderr.

The policy classifies commands as automatically allowed, separately approvable, or forbidden. Project configuration may suggest verification commands but cannot mark a command safe or weaken a user-level or built-in restriction.

## Runtime lifecycle

The normal state path is:

```text
CREATED
  -> DISCOVERING
  -> GENERATING
  -> CHANGESET_PROPOSED
  -> AWAITING_APPROVAL
  -> CHECKPOINTING
  -> APPLYING
  -> VERIFYING
  -> COMPLETED | VERIFICATION_FAILED | FAILED
```

One run produces at most one Change Set in this increment. Verification failure does not trigger another model-write cycle.

`CANCELLED`, `STALE`, and `RECOVERY_REQUIRED` are additional terminal states for an explicit cancellation, a pre-change hash mismatch, and an unsuccessful restoration. `run.completed` carries either `COMPLETED` or `VERIFICATION_FAILED`; `run.failed` carries `FAILED` or `RECOVERY_REQUIRED`. Cancellation and staleness have their dedicated terminal Events.

Command approval is an interrupt inside discovery or verification. Runtime emits an approval request and remains suspended until the exact command request is approved, rejected, or cancelled. A rejected optional command returns a denied result to the model; a rejected required verification command ends verification without executing it.

Change Set approval binds to its exact canonical content hash. The hash covers affected paths, operations, pre-change and post-change hashes, and the verification plan. Any change invalidates the prior approval.

Immediately before checkpointing and again before applying, Runtime compares all current files with the recorded pre-change hashes. A mismatch marks the Change Set stale and ends the run without target-file writes.

## Core contract

All Commands and Events include `schema_version: 1`. Identifiers are opaque and unique within the local Vera installation.

### Commands

The first contract requires:

- `StartRun`: goal, workspace root, model profile, and requested verification-policy overrides;
- `ResolveApproval`: approval identifier, approved target hash, and approve or reject decision;
- `CancelRun`: run identifier; and
- `RollbackRun`: run identifier or checkpoint identifier.

Runtime assigns run, Change Set, checkpoint, event, and approval identifiers. Clients cannot choose authoritative identifiers.
Runtime also computes the effective policy; a client cannot label its requested policy as authoritative.

### Change Set

A Change Set contains:

- `changeset_id` and `run_id`;
- a user-readable summary;
- one or more ordered file changes;
- a proposed verification plan; and
- the canonical `content_hash`.

Each file change contains an operation (`create`, `update`, or `delete`), a normalized relative path, a pre-change hash or absent-file marker, a post-change hash or deleted-file marker, and the Runtime-generated unified Diff. Runtime retains the exact intended post-change bytes separately from terminal rendering.

### Approval

An approval request identifies its kind (`command` or `changeset`), target identifier, immutable target hash, user-visible description, and risk information. A decision is valid only when its approval identifier and target hash match the currently suspended Runtime request.

### Checkpoint manifest

The checkpoint manifest records:

- checkpoint and run identifiers;
- every affected relative path;
- whether each path existed before the change;
- original file hashes, bytes, and supported permission metadata; and
- hashes expected after a successful apply.

Manual rollback restores a path only when its current state matches the recorded applied state. If any path has changed since Vera's apply, rollback stops before overwriting it and reports a conflict. Forced conflict overwrite is outside this increment.

### Verification result

Each result records the exact argument array, relative working directory, start and completion time, duration, exit code or timeout, bounded stdout and stderr, and one terminal status: `passed`, `failed`, `timed_out`, `rejected`, or `error`.

### Event envelope

Every Event uses this envelope:

```json
{
  "schema_version": 1,
  "event_id": "evt_...",
  "run_id": "run_...",
  "sequence": 12,
  "timestamp": "2026-09-10T12:00:00Z",
  "type": "changeset.proposed",
  "payload": {}
}
```

Sequence numbers increase monotonically within one run. Events are appended to that run's local JSON Lines record before the corresponding state transition is exposed to a client.

Required event types are:

- `run.started`, `run.cancelled`, `run.completed`, and `run.failed`;
- `model.requested` and `model.completed`;
- `tool.started` and `tool.completed`;
- `changeset.proposed`, `changeset.stale`, and `changeset.applied`;
- `approval.required` and `approval.resolved`;
- `checkpoint.created`, `checkpoint.restored`, and `checkpoint.restore_failed`;
- `verification.started` and `verification.completed`; and
- `rollback.completed` and `rollback.conflicted`.

Provider-native objects and CLI formatting are not part of the event contract. Event payloads and errors pass through centralized redaction before persistence or display.

## Tool and context policy

### Permission levels

Tools and commands have four enforcement outcomes:

| Outcome | Meaning | Examples |
|---|---|---|
| Automatically allowed | Execute after schema and workspace validation | directory listing, bounded code search, ordinary text read |
| Policy allowed | Execute because the exact argument shape matches an accepted safe rule | configured test or lint command |
| Approval required | Suspend and request approval for the exact command hash | a non-allowlisted, locally executable command |
| Forbidden | Reject without offering model-controlled escalation | workspace escape, privilege elevation, broad destructive action |

Command execution never invokes a shell. Shell operators, redirects, pipes, substitutions, and compound command strings are not interpreted. The policy rejects privilege-elevation tools, commands whose working directory escapes the workspace, and broadly destructive operations. An explicit user approval cannot weaken these hard prohibitions in this increment.

### Sensitive files

Sensitive credentials, private keys, and real environment files are denied by default. Safe templates such as `.env.example` may be read. Configuration may add protected patterns but may not remove built-in credential protections.

Secrets are not written to configuration, Events, logs, terminal output, or exception text. Redaction covers configured secret values and common credential field names.

### Resource limits

The initial effective policy uses these finite defaults:

- 20 model turns per run;
- 50 total tool calls per run;
- 1,000,000 bytes per file read;
- 100,000 bytes returned by one tool invocation;
- 2,000,000 bytes of collected workspace context per run; and
- 120 seconds per verification command.

A project policy may only lower these limits. A user-level policy or explicit CLI option may set another finite positive value but may not disable a limit entirely. Runtime marks every truncation in the corresponding tool or verification result.

Runtime detects consecutive identical tool calls with identical arguments. Three such calls without a changed result end the loop as failed. Agent-turn, tool-call, and context limits apply before approval and therefore terminate without target-file writes. Verification has its own command-count and timeout enforcement after apply, and manual rollback remains available when it fails.

## Failure behavior

- A model, parsing, read, or search failure before approval leaves target files unchanged.
- Rejecting or cancelling a Change Set ends the run without target-file writes.
- A checkpoint failure prevents apply.
- A stale pre-change hash prevents apply and requires a newly generated Change Set.
- An apply failure triggers an immediate in-process attempt to restore the checkpoint. Runtime reports whether restoration succeeded.
- A restoration failure ends with a recovery-required status and exact affected paths; it never reports the run as safely restored.
- Verification failure preserves the applied files and checkpoint, emits `verification.completed`, and ends as `VERIFICATION_FAILED`.
- Manual rollback conflicts do not overwrite later user edits.
- A process crash may leave a durable checkpoint and partial event history, but automatic inspection and continuation after restart are not promised by this increment.

Runtime never describes a provider response, process exit, or file-system call as successful without locally observed evidence.

## CLI behavior

The first CLI surface is:

```text
vera run <goal>
vera runs list
vera runs show <run-id>
vera rollback <run-id>
vera config show
```

`vera run` accepts workspace and model-profile options. Human mode renders progress, Change Set summary, affected files, full Diff, risk details, verification plan, final evidence, run identifier, and rollback instruction. Approval requires an explicit approve or reject response. The first version has no `--yes` or equivalent write auto-approval flag.

`--json` emits newline-delimited Event envelopes without ANSI formatting. In a non-interactive environment, Runtime emits `approval.required`, records a cancellation, exits with status `2`, and performs no target-file write. Cross-process approval continuation belongs to the future structured sidecar transport; the CLI never infers approval from the absence of a terminal.

`vera config show` displays effective non-secret configuration and redacts secret values. Provider entries refer to an environment-variable name, not a stored key:

```toml
[providers.deepseek]
base_url = "https://provider.example/v1"
api_key_env = "DEEPSEEK_API_KEY"
```

The exact base URL is local configuration rather than a compiled product invariant.

Configuration precedence is CLI option, environment variable, project `.vera/config.toml`, user configuration, then built-in default. Higher-precedence values may select workspace, provider, and model. Project configuration may only lower resource limits; user configuration and an explicit CLI option may set another finite positive value. No configuration source may disable limits, provide project secrets, declare commands intrinsically safe, or weaken built-in security rules.

Exit statuses are:

- `0`: applied and verification passed;
- `2`: rejected or cancelled without an unresolved write;
- `3`: applied but verification failed;
- `4`: model, tool, policy, or Runtime failure with no unresolved partial write; and
- `5`: restoration failed and manual recovery is required.

## Testing strategy

Default tests are deterministic and make no provider-network calls. A scripted `FakeModelAdapter` drives Runtime through exact tool calls and outcomes.

### Unit and component tests

Tests cover:

- every legal state transition and representative illegal transitions;
- Command and Event schema validation and event ordering;
- canonical Change Set hashes and approval invalidation;
- path traversal, absolute paths, symbolic-link escape, and protected-file denial;
- command classification, argument handling, timeouts, and shell-metacharacter non-interpretation;
- context, output, turn, tool-call, and repeated-call limits;
- secret redaction in configuration, errors, logs, and Events;
- checkpoint manifests, file modes where supported, and byte-exact restoration;
- apply failure restoration and restoration-failure reporting;
- successful verification, failure, timeout, and rejection; and
- rollback success and post-apply conflict refusal.

### CLI integration tests

Subprocess tests cover human and JSON modes, interactive approval and rejection, non-interactive approval cancellation, command output, run inspection, rollback, and exit statuses.

### Disposable Git fixture

An automated end-to-end test creates a temporary Git repository and performs this chain:

```text
create fixture
-> start run
-> FakeModelAdapter reads and searches
-> propose Change Set
-> approve
-> checkpoint
-> apply
-> verify
-> inspect Git Diff
-> rollback
-> confirm byte-identical restoration
```

A rejection variant proves that repository files and Git status remain unchanged.

### Provider smoke tests

DeepSeek and GLM each have an opt-in, low-cost adapter smoke test excluded from the default suite and CI. They verify authentication, one normalized response, tool-call translation, and usage capture when supplied by the provider. At least one provider must complete the full formal Vera Runtime chain before implementation of this increment is considered complete. Prior prototype connectivity is supporting evidence, not formal Vera implementation evidence.

### Manual acceptance

After automated checks pass, the user runs Vera once against a recoverable copy of a real project. The user inspects and approves the Change Set, observes verification evidence, invokes rollback, and confirms the project is restored. No valuable working copy is used as the first manual target.

## Acceptance criteria

This specification is implemented only when all of the following are evidenced:

1. The installable Python CLI completes the accepted run lifecycle through the public Core Command/Event contract.
2. Runtime, not the model, client, or provider adapter, owns every authoritative state change and side effect.
3. Rejecting a Change Set produces no target-file write, and changing a file after proposal makes approval unusable.
4. Path escape, protected-file access, forbidden commands, and write-without-checkpoint attempts are rejected by deterministic tests.
5. An approved multi-file Change Set creates a checkpoint, applies exact intended bytes, and exposes the Runtime-generated Diff and ordered Events.
6. Verification produces command, timeout, exit, stdout, stderr, duration, and terminal-status evidence.
7. Manual rollback restores byte-identical originals and refuses to overwrite post-apply user changes.
8. Automated unit, integration, CLI, disposable-repository, static-analysis, and type checks all pass.
9. JSON-mode output validates against the versioned event models and contains no configured secret value.
10. DeepSeek or GLM completes one opt-in real-provider end-to-end run, followed by the recoverable real-project-copy manual acceptance.

## Documentation and decision follow-up

This accepted product specification is the governing source for its increment. Before feature implementation begins, the implementation plan must:

- create a Phase 1 task record linked to this specification;
- record the Python Runtime and dependency selection as an architecture decision;
- record the Command/Event boundary and private checkpoint storage as architecture decisions;
- reconcile `docs/ROADMAP.md` and `docs/STATUS.md` so Phase 1 contains the minimum safe loop defined here and Phase 2 clearly means expansion and hardening; and
- keep documentation updates in the same checkpoints as the behavior they govern.

No feature implementation or dependency manifest is added by accepting this specification alone.
