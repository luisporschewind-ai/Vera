# Task 0001: Bootstrap Vera Repository

**Status:** Done
**Date:** 2026-09-10

## Goal

Create Vera's first governance and SDD baseline without adding Agent runtime code.

## Scope

- Add repository-level guidance and ignore rules.
- Record the product boundary, roadmap, current status, and documentation conventions.
- Keep `/Users/admin/Coding-harness` read-only and outside this repository.
- Leave technology, provider, desktop shell, license, and public-release details open until separate decisions are accepted.

## Acceptance checks

- [x] All approved files and directories exist.
- [x] Root documentation links resolve.
- [x] Decided direction and open decisions are clearly separated.
- [x] No Agent feature code or dependency manifest is added.
- [x] `git diff --check` passes and final Git status is reported.
- [x] Commit remains a separate, explicitly authorized action.

## Verification evidence

- Required-file and link-target checks passed.
- Placeholder and trailing-whitespace scan returned no matches.
- `git diff --check` exited successfully.
- Source-code and dependency-manifest scan returned no files.
