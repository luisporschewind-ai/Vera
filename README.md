# Vera

Vera is a local desktop Coding Agent in development. It is intended to help people inspect, change, verify, and recover work in a local codebase through a transparent, approval-aware workflow.

This repository is Vera's formal product workspace. It currently contains only the project-governance and specification baseline; no Agent runtime has been implemented here yet.

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

Vera is private and pre-implementation. The next product step is to specify the first Core contract and vertical slice before adding dependencies or feature code.

`/Users/admin/Coding-harness` is a retired Vera prototype. It may be inspected for lessons and evidence, but it is not an implementation base and must not be modified from this repository.

No open-source license has been selected. Public release terms remain undecided.
