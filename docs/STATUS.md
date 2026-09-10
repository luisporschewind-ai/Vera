# Vera Status

**Updated:** 2026-09-10
**Current phase:** Phase 1 — Core contract and vertical slice
**Repository state:** Governance baseline is the initial `main` checkpoint; no remote exists.

## Verified baseline

- Working directory: `/Users/admin/Vera`
- Git branch: `main`
- Initial checkpoint: repository governance and SDD baseline
- Agent implementation: none
- Dependency manifests: none

## Completed task

- [Task 0001: Bootstrap Vera Repository](tasks/0001-bootstrap-repository.md)

The Phase 1 Core contract is in architectural design. Its task record will be created after the first vertical-slice scope is accepted.

## Latest verification

- Required files and documented link targets: passed
- Placeholder and trailing-whitespace scan: passed
- `git diff --check`: passed
- Agent source and dependency-manifest scan: no files found
- Git state: initial governance checkpoint on `main`

## Accepted direction

- Formal development happens only in this repository.
- `/Users/admin/Coding-harness` remains a read-only prototype reference.
- Product delivery follows Core-first, internal CLI-first, desktop-later.
- Private stability and eval evidence precede public release.

## Decisions still open

- Core runtime and dependencies
- Provider and protocol contracts
- Storage, checkpoint, and recovery design
- Eval corpus and thresholds
- Desktop framework
- License and release policy

## Next checkpoint

Agree on the first Core vertical-slice boundary, then write and accept its specification before adding feature code or dependencies.
