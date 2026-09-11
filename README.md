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

Run `vera` from the project directory you want to edit. The bare command opens a
persistent `Vera >` session; enter a natural-language task, review the emitted
Diff, and explicitly type `approve`, `reject`, or `cancel` at each approval
boundary. Use `/help` inside the session to list `/runs`, `/show`, `/rollback`,
and exit commands. The one-shot `vera run "goal"` command remains available.

Provider credentials and live tests are intentionally opt-in; no API key is printed by the CLI.

`/Users/admin/Coding-harness` is a retired Vera prototype. It may be inspected for lessons and evidence, but it is not an implementation base and must not be modified from this repository.

No open-source license has been selected. Public release terms remain undecided.
