# Vera

Vera is a local desktop Coding Agent in development. It is intended to help people inspect, change, verify, and recover work in a local codebase through a transparent, approval-aware workflow.

This repository is Vera's formal product workspace. `main` contains the Core, internal CLI, persistent sessions, Skills, BYOK model configuration, and cache-usage reporting. Phase 8 tooling/Policy v2/native Git remains on its isolated branch awaiting acceptance and integration. Real-provider, installation, and human acceptance are tracked separately in [Current status](docs/STATUS.md).

## Direction

The accepted delivery order is:

1. Build a UI-independent Vera Agent Core.
2. Use an internal `vera-cli` to develop, test, and accept the Core.
3. Harden Core safety and reliability on representative projects.
4. Productize the CLI and TUI until everyday workflows are mature and predictable.
5. Connect the desktop application to the same Core through a structured protocol.
6. Validate privately, then prepare a stable public GitHub release.

The CLI is an internal development surface, not Vera's final product identity. Electron is the accepted first desktop baseline, with Tauri as a fallback if measured gates fail. Desktop implementation remains gated on the preceding acceptance milestones; see [ADR-0013](docs/decisions/ADR-0013-electron-desktop-baseline.md) and the [roadmap](docs/ROADMAP.md).

## Documentation

- [Product definition](docs/PRODUCT.md)
- [Roadmap](docs/ROADMAP.md)
- [Current status](docs/STATUS.md)
- [Specifications](docs/specs/README.md)
- [Architecture decisions](docs/decisions/README.md)
- [Execution tasks](docs/tasks/README.md)
- [Agent working agreement](AGENTS.md)

## Development state

Vera is private and in Core-first implementation. The current CLI is an internal development surface for inspecting, proposing, approving, applying, verifying, and rolling back changes.

## CLI quick start

```bash
uv sync --extra dev
uv run vera                 # TTY 默认 TUI
uv run vera --plain          # 逐行人类模式
uv run vera --json           # NDJSON Session
uv run vera run "goal" --json
uv run vera eval validate --json
uv run vera eval list
uv run vera eval run --suite offline --json
uv run vera config show
```

To expose the command outside this checkout during development:

```bash
uv tool install --editable /Users/admin/Vera
cd /path/to/your/project
vera
```

Run `vera` from the project directory you want to edit. The bare command opens a
persistent `Vera >` session with a compact status panel (version, model,
workspace, Git, session, and approval boundary). You can ask ordinary questions,
keep in-process conversation context, or request safe code changes. Review any
emitted Diff and explicitly type `approve`, `reject`, or `cancel` at each
approval boundary.

Useful session commands:

- `/help` — list commands
- `/status` / `/context` / `/permissions` — inspect session state
- `/new` / `/clear` — reset conversation context
- `/compact [focus]` — summarize context through Core without tools
- `/model [profile]` — show or switch the current model profile
- `/runs` / `/show` / `/rollback` — inspect or roll back prior runs
- `/recover [run-id]` — inspect interrupted runs without writing
- `/resume <run-id>` — continue a safe approval or verification boundary
- `/abandon <run-id>` — abandon an interrupted run with no workspace side effects
- `/exit` — leave the session

The one-shot `vera run "goal"` command remains available, including `--json`
for non-interactive Event output. Use `vera recover list|show|resume|abandon`
to inspect or continue recovery; `--json` emits Event JSON Lines only.

Offline evaluations are a Core client, not a live-model quality score. They use
the bundled Fake Model corpus (14 frozen cases) and never call a real provider:

```bash
uv run vera eval validate --json
uv run vera eval list --json
uv run vera eval run plain-answer --json --output ./eval-evidence
uv run vera eval run --suite offline --json --output ./eval-suite
```

`--json` prints exactly one report document. Evidence is written under the given
`--output` parent (default: the Vera private state `evals/` directory) as
`<evaluation_id>/{report.json,files.json,events.jsonl}` with directory mode
`0700` and file mode `0600`. Exit codes: `0` pass, `2` Ctrl+C, `4` case
fail/timeout, `5` config/corpus/protocol/evidence error.

Local wheel install, upgrade, and configuration errors: [INSTALL.md](docs/INSTALL.md).
Representative-project manual steps (user-run only): [phase-5-representative-project-manual-checklist.md](docs/evals/phase-5-representative-project-manual-checklist.md).


Provider credentials and live tests are intentionally opt-in; no API key is printed by the CLI. Verification commands run with the current system user's permissions and always retain a separate approval boundary when required by policy.

`/Users/admin/Coding-harness` is a retired Vera prototype. It may be inspected for lessons and evidence, but it is not an implementation base and must not be modified from this repository.

No open-source license has been selected. Public release terms remain undecided.
