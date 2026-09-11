# Vera

Vera is a local desktop Coding Agent in development. It is intended to help people inspect, change, verify, and recover work in a local codebase through a transparent, approval-aware workflow.

This repository is Vera's formal product workspace. The first Python Core safe-editing slice and an internal CLI are implemented on the active development branch; real-provider and human acceptance remain explicit gates.

## Direction

The accepted delivery order is:

1. Build a UI-independent Vera Agent Core.
2. Use an internal `vera-cli` to develop, test, and accept the Core.
3. Connect the desktop application to the same Core through a structured protocol.
4. Validate privately, then prepare a stable public GitHub release.

The CLI is an internal development surface, not Vera's final product identity. The desktop framework will be selected later using working prototypes and measured trade-offs.

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
uv run vera
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
- `/exit` — leave the session

The one-shot `vera run "goal"` command remains available, including `--json`
for non-interactive Event output. Use `vera recover list` and `vera recover show <run-id>`
to inspect recovery reports; `--json` emits Event JSON Lines only.

Provider credentials and live tests are intentionally opt-in; no API key is printed by the CLI. Verification commands run with the current system user's permissions and always retain a separate approval boundary when required by policy.

`/Users/admin/Coding-harness` is a retired Vera prototype. It may be inspected for lessons and evidence, but it is not an implementation base and must not be modified from this repository.

No open-source license has been selected. Public release terms remain undecided.
